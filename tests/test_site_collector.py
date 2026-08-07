"""Visiting each customer's site over VPN to read what is there.

The job the system account exists for, and most of what follows is about the
tunnel coming down again. A collector that dies holding one leaves the toolkit
inside somebody's network with nobody aware of it, until a human notices VPN
refusing to work and asks why.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services import site_collector as sc


class _Profile:
    def __init__(self, pid, name, customer_id="Acme"):
        self.id, self.name, self.customer_id = pid, name, customer_id


@pytest.fixture()
def site(monkeypatch, tmp_path):
    """Wire the collector to fakes and record the tunnel's ups and downs."""
    events: list[str] = []
    connected: set[str] = set()

    async def _connect(profile_id, *, owned_by=""):
        events.append(f"connect:{profile_id}:{owned_by}")
        connected.add(profile_id)
        return {"state": "connected"}

    async def _disconnect(profile_id=None):
        events.append(f"disconnect:{profile_id}")
        connected.discard(profile_id)
        return {"ok": True}

    async def _audit(customer, customer_id):
        events.append(f"audit:{customer_id}")
        return {"fortigate": {"model": "FG-60F"}, "unifi": None}

    monkeypatch.setattr("app.services.vpn_manager.connect", _connect)
    monkeypatch.setattr("app.services.vpn_manager.disconnect", _disconnect)
    monkeypatch.setattr("app.services.vpn_manager._is_connected", lambda pid: pid in connected)
    monkeypatch.setattr("app.services.vpn_manager.owner_of", lambda pid: "")
    monkeypatch.setattr("app.services.vpn_manager.system_held", lambda: sorted(connected))
    monkeypatch.setattr("app.services.network_audit.run_quick_network_audit", _audit)
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer",
        staticmethod(lambda cid: {"CustomerName": cid, "FortiGateHost": "10.0.0.1"}),
    )
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path)
    return {"events": events, "connected": connected, "dir": tmp_path}


# ── The tunnel comes down ────────────────────────────────────────────────────

async def test_a_site_is_visited_and_left_closed(site):
    result = await sc.collect_site(_Profile("p1", "Fonnafly"))

    assert result.outcome == sc.COLLECTED
    assert site["connected"] == set(), "the tunnel was left open"
    assert site["events"] == ["connect:p1:sybr-system", "audit:Acme", "disconnect:p1"]


async def test_the_tunnel_comes_down_even_when_the_audit_raises(site, monkeypatch):
    async def _boom(customer, customer_id):
        raise RuntimeError("the firewall stopped answering")

    monkeypatch.setattr("app.services.network_audit.run_quick_network_audit", _boom)

    result = await sc.collect_site(_Profile("p1", "Fonnafly"))

    assert result.outcome == sc.FAILED
    assert "stopped answering" in result.detail
    assert site["connected"] == set()


async def test_the_tunnel_comes_down_when_the_site_times_out(site, monkeypatch):
    async def _hang(customer, customer_id):
        await asyncio.sleep(10)

    monkeypatch.setattr("app.services.network_audit.run_quick_network_audit", _hang)

    result = await sc.collect_site(_Profile("p1", "Fonnafly"), timeout=1)

    assert result.outcome == sc.FAILED
    assert "Gave up" in result.detail
    assert site["connected"] == set(), "a timed-out site is the likeliest to hold a tunnel"


async def test_a_tunnel_that_never_came_up_is_not_disconnected(site, monkeypatch):
    async def _fail(profile_id, *, owned_by=""):
        site["events"].append(f"connect:{profile_id}")
        return {"state": "error", "error": "no route to host"}

    monkeypatch.setattr("app.services.vpn_manager.connect", _fail)

    result = await sc.collect_site(_Profile("p1", "Fonnafly"))

    assert result.outcome == sc.FAILED
    assert "no route" in result.detail
    assert not any(e.startswith("disconnect") for e in site["events"])


# ── It does not take a tunnel from a person ──────────────────────────────────

async def test_a_tunnel_a_human_is_using_is_left_alone(site, monkeypatch):
    """The other direction of the lock. A background job that disconnects
    somebody mid-session to gather statistics has its priorities backwards."""
    site["connected"].add("p1")
    monkeypatch.setattr("app.services.vpn_manager.owner_of", lambda pid: "frank")

    result = await sc.collect_site(_Profile("p1", "Fonnafly"))

    assert result.outcome == sc.SKIPPED
    assert "frank" in result.detail
    assert site["events"] == [], "it touched a tunnel somebody was using"


async def test_a_tunnel_the_system_left_up_is_reused_not_refused(site):
    """Its own leftover is not somebody else's session."""
    site["connected"].add("p1")

    result = await sc.collect_site(_Profile("p1", "Fonnafly"))

    assert result.outcome == sc.COLLECTED


# ── What it refuses to guess ─────────────────────────────────────────────────

async def test_a_profile_with_no_customer_is_skipped(site):
    result = await sc.collect_site(_Profile("p1", "Lab", customer_id=""))

    assert result.outcome == sc.SKIPPED
    assert site["events"] == []


async def test_a_site_where_nothing_answered_is_a_failure_not_an_empty_reading(site, monkeypatch):
    """An empty reading filed as data is the mistake this codebase keeps
    finding: "no devices" and "nobody answered" are different claims."""
    async def _nothing(customer, customer_id):
        return {"fortigate": None, "unifi": None}

    monkeypatch.setattr("app.services.network_audit.run_quick_network_audit", _nothing)

    result = await sc.collect_site(_Profile("p1", "Fonnafly"))

    assert result.outcome == sc.FAILED
    stats = site["dir"] / "Acme" / "site_stats"
    assert not stats.is_dir() or not list(stats.glob("*.json")), (
        "an empty reading was filed as data"
    )


async def test_what_was_read_is_stored_beside_the_customers_audits(site):
    await sc.collect_site(_Profile("p1", "Fonnafly"))

    stored = list((site["dir"] / "Acme" / "site_stats").glob("*.json"))
    assert len(stored) == 1

    import json as _json

    from app.core.encryption import encrypted_read_text

    payload = _json.loads(encrypted_read_text(stored[0]))
    assert payload["collected_by"] == "sybr-system"
    assert payload["fortigate"]["model"] == "FG-60F"


# ── The run as a whole ───────────────────────────────────────────────────────

async def test_sites_are_visited_one_at_a_time(site, monkeypatch):
    """Customer sites overlap on RFC1918 — two tunnels up at once means the
    collector reads whichever site won the routing table."""
    overlapping: list[int] = []

    async def _watch(customer, customer_id):
        overlapping.append(len(site["connected"]))
        return {"fortigate": {"ok": True}, "unifi": None}

    monkeypatch.setattr("app.services.network_audit.run_quick_network_audit", _watch)
    monkeypatch.setattr(
        "app.services.vpn_manager.list_profiles",
        lambda: _profiles([_Profile("p1", "A"), _Profile("p2", "B"), _Profile("p3", "C")]),
    )
    monkeypatch.setattr("app.core.system_user.ensure", _noop)

    await sc.collect_all()

    assert overlapping == [1, 1, 1], "more than one tunnel was up at once"


async def test_one_site_failing_does_not_end_the_run(site, monkeypatch):
    async def _flaky(customer, customer_id):
        if customer_id == "B":
            raise RuntimeError("down")
        return {"fortigate": {"ok": True}, "unifi": None}

    monkeypatch.setattr("app.services.network_audit.run_quick_network_audit", _flaky)
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer",
        staticmethod(lambda cid: {"CustomerName": cid}),
    )
    monkeypatch.setattr(
        "app.services.vpn_manager.list_profiles",
        lambda: _profiles([
            _Profile("p1", "A", "A"), _Profile("p2", "B", "B"), _Profile("p3", "C", "C")
        ]),
    )
    monkeypatch.setattr("app.core.system_user.ensure", _noop)

    summary = await sc.collect_all()

    assert (summary["collected"], summary["failed"]) == (2, 1)
    assert summary["sites"] == 3


async def test_a_leftover_tunnel_is_swept_at_the_end(site, monkeypatch):
    """The loop's finally covers the ordinary case; this covers the one where
    the loop itself did not get there."""
    monkeypatch.setattr("app.services.vpn_manager.list_profiles", lambda: _profiles([]))
    monkeypatch.setattr("app.core.system_user.ensure", _noop)
    site["connected"].add("orphan")

    await sc.collect_all()

    assert site["connected"] == set()
    assert "disconnect:orphan" in site["events"]


async def _noop():
    return None


async def _profiles(items):
    return items
