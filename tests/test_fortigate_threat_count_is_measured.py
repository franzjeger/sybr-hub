"""A threat count nobody counted.

Two halves of the same fiction, in different files:

* ``_check_fortigate_threats`` read ``threat_count`` off
  ``poll_all_fortigates()``. That function has never returned the key — not
  for an online device, not for a failed one. Every firewall counted zero, so
  the rule, enabled by default with a threshold of 50 since it was written,
  could not fire. An MSP watching for threat spikes was watching a check that
  was structurally incapable of raising one.

* The infrastructure dashboard set ``threat_count = 0`` for every online
  FortiGate — a literal, not a reading; nothing in that route opens a threat
  log. The card rendered it green, because the frontend colours the number by
  ``> 0``. Every customer showed a green zero for a figure nobody had
  measured.

The data was there the whole time: ``get_threat_summary()`` queries the IPS,
antivirus and webfilter logs, and the FortiGate page has been calling it.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.services import alert_engine as ae
from app.services import fortigate_api

ROOT = Path(__file__).resolve().parents[1]


# ── The check reads something that exists ────────────────────────────────────

def test_it_no_longer_reads_a_key_nothing_writes():
    source = inspect.getsource(ae._check_fortigate_threats)
    assert 'get("threat_count"' not in source, (
        "poll_all_fortigates() has never returned threat_count; reading it "
        "makes every device count zero"
    )


def test_poll_all_fortigates_really_does_not_return_it():
    # The premise of the fix. If this ever changes, the check could go back to
    # the cheaper source — but it must be a fact, not an assumption.
    source = inspect.getsource(fortigate_api.poll_all_fortigates)
    assert '"threat_count"' not in source


def test_it_uses_the_function_that_reads_the_logs():
    assert "get_threat_summary" in inspect.getsource(ae._check_fortigate_threats)


# ── What it does with what it finds ──────────────────────────────────────────

@pytest.fixture
def firewalls(monkeypatch):
    """Two customers with FortiGates, and a threat total per host."""
    totals: dict[str, int | Exception] = {}

    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        lambda: [
            {"_id": "c1", "CustomerName": "Acme AS", "FortiGateHost": "fg1.acme.no"},
            {"_id": "c2", "CustomerName": "Bedrift AS", "FortiGateHost": "fg2.bedrift.no"},
            {"_id": "c3", "CustomerName": "Uten brannmur", "FortiGateHost": ""},
        ],
    )
    monkeypatch.setattr("app.core.credentials.get_secret",
                        lambda cid, name: "tok" if cid in ("c1", "c2") else None)

    async def _summary(config, token, days=7):
        value = totals.get(config["FortiGateHost"], 0)
        if isinstance(value, Exception):
            raise value
        return {"summary": {"total": value}}
    monkeypatch.setattr(fortigate_api, "get_threat_summary", _summary)
    return totals


async def test_a_spike_raises_an_alert(firewalls):
    firewalls["fg1.acme.no"] = 120
    alerts = await ae._check_fortigate_threats(50)
    assert [a["customer"] for a in alerts] == ["Acme AS"]
    assert "120 trusler" in alerts[0]["detail"]


async def test_the_threshold_is_respected(firewalls):
    firewalls["fg1.acme.no"] = 50
    assert await ae._check_fortigate_threats(50) == []
    firewalls["fg1.acme.no"] = 51
    assert len(await ae._check_fortigate_threats(50)) == 1


async def test_double_the_threshold_is_critical(firewalls):
    firewalls["fg1.acme.no"] = 101
    assert (await ae._check_fortigate_threats(50))[0]["severity"] == "critical"
    firewalls["fg1.acme.no"] = 60
    assert (await ae._check_fortigate_threats(50))[0]["severity"] == "warning"


async def test_an_unreachable_firewall_is_not_reported_as_calm(firewalls):
    firewalls["fg1.acme.no"] = TimeoutError("no route to host")
    firewalls["fg2.bedrift.no"] = 200
    alerts = await ae._check_fortigate_threats(50)
    assert [a["customer"] for a in alerts] == ["Bedrift AS"], (
        "one unreachable firewall ended the sweep and hid the other's spike"
    )


async def test_a_customer_without_a_firewall_is_skipped(firewalls):
    firewalls["fg1.acme.no"] = 200
    firewalls["fg2.bedrift.no"] = 200
    assert len(await ae._check_fortigate_threats(50)) == 2


async def test_a_broken_customer_list_names_the_check(monkeypatch):
    def _boom():
        raise RuntimeError("customer store unreadable")
    monkeypatch.setattr("app.core.customer.CustomerManager.list_customers", _boom)
    with pytest.raises(ae.AlertCheckFailed) as exc:
        await ae._check_fortigate_threats(50)
    assert exc.value.check == "fortigate_threats"


# ── The dashboard stops claiming a number it never read ──────────────────────

def test_the_dashboard_does_not_hardcode_a_threat_count():
    source = (ROOT / "app/web/routes/dashboard_infra.py").read_text(encoding="utf-8")
    assert "threat_count = 0" not in source, (
        "a literal zero was rendered as a green '0 threats' for every online "
        "firewall — the route never opens a threat log"
    )
    assert "threat_count = None" in source


def test_the_card_omits_a_count_it_does_not_have():
    source = (ROOT / "app/web/static/app-dashboard.js").read_text(encoding="utf-8")
    assert "c.threat_count !== null && c.threat_count !== undefined" in source, (
        "null must fall through to the em-dash placeholder rather than being "
        "coloured as a measured zero"
    )
