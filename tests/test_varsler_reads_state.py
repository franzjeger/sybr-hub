"""Varsler shows certificates and firmware from state, with or without a channel.

It used to show them only through the alert engine's history, and the engine
records an alert only once a Teams or e-mail channel accepted it. With no
channel set up, which is how every install starts, an expired certificate or
an end-of-life firewall appeared nowhere on the page meant to list exactly
that. /dashboard/alerts now reads the stored TLS and firmware state directly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services import alert_engine, firmware_inventory, tls_inventory
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    BETA,
    _reset_middleware_state,
    _scope_env,
    assert_no_foreign,
    client,
    login,
)


def _cert(host: str, days: float, customer_id: str | None, **extra) -> dict:
    return {
        "host": host,
        "port": 443,
        "customer_id": customer_id,
        "subject": {"commonName": host},
        "issuer": {"organizationName": "Example CA"},
        "not_after": (datetime.now(UTC) + timedelta(days=days)).isoformat(),
        "chain_valid": True,
        **extra,
    }


def _device(key: str, status: str, **extra) -> dict:
    return {
        "key": key,
        "name": key,
        "model": "M",
        "version": "1.0.0",
        "status": status,
        "reason": "",
        "latest": "1.2.0" if status == "outdated" else "",
        "source": "test",
        **extra,
    }


async def _seed():
    await tls_inventory.record_results(
        [
            _cert("shop.acme.example", 3, ACME),
            _cert("www.acme.example", 20, ACME),
            _cert("fine.acme.example", 300, ACME),
            _cert("fw.acme.example", 300, ACME, chain_valid=False, chain_problem="self_signed"),
            _cert(
                "api.acme.example", 300, ACME, chain_valid=False, chain_problem="incomplete_chain"
            ),
            {"host": "down.acme.example", "port": 443, "customer_id": ACME, "error": "refused"},
            _cert("shop.beta.example", 2, BETA),
        ],
        allowed=None,
        may_add=True,
    )
    await firmware_inventory.record(
        ACME,
        "unifi",
        [
            _device("eol-ap", "eol"),
            _device("old-switch", "outdated"),
            _device("good-ap", "current"),
            _device("mystery", "unknown"),
        ],
    )
    await firmware_inventory.record(BETA, "fortigate", [_device("fw.beta.example", "eol")])


async def test_varsler_lists_stored_certificates_and_firmware_with_no_channel(
    client, monkeypatch, tmp_path
):
    monkeypatch.setattr(alert_engine, "_ALERT_HISTORY_PATH", tmp_path / "alert_history.json")
    await _seed()
    config = alert_engine.get_alert_config()
    assert config["enabled"] is False and not config["email_recipient"]
    assert alert_engine.get_alert_history() == [], "nothing was ever sent"

    headers = await login("tech-acme", customers=(ACME,))
    r = client.get("/api/dashboard/alerts", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    certs = {c["host"]: c for c in body["certificates"]}
    assert set(certs) == {
        "shop.acme.example",
        "www.acme.example",
        "fw.acme.example",
        "api.acme.example",
    }, "a healthy certificate and an unreachable endpoint are not Varsler items"
    assert certs["shop.acme.example"]["category"] == "critical"
    assert certs["shop.acme.example"]["kind"] == "expiring"
    assert certs["shop.acme.example"]["customer_name"] == "Acme AS"
    assert certs["www.acme.example"]["category"] == "warning"
    assert certs["fw.acme.example"]["category"] == "info", "self-signed is usually deliberate"
    assert certs["api.acme.example"]["category"] == "warning"
    assert certs["api.acme.example"]["chain_problem"] == "incomplete_chain"

    devices = {d["device_key"]: d for d in body["firmware"]}
    assert set(devices) == {"eol-ap", "old-switch"}, "current and unknown are not alerts"
    assert devices["eol-ap"]["category"] == "critical"
    assert devices["old-switch"]["category"] == "warning"
    assert devices["old-switch"]["latest"] == "1.2.0"

    assert body["coverage"]["tls"]["endpoints"] == 6
    assert body["coverage"]["tls"]["unreachable"] == 1
    assert body["coverage"]["firmware"] == {
        "devices": 4,
        "unknown": 1,
        "last_read": body["coverage"]["firmware"]["last_read"],
    }
    assert body["total_alerts"] == len(body["certificates"]) + len(body["firmware"])
    assert_no_foreign(r.text)


async def test_an_unrestricted_account_sees_every_customers_state(client):
    await _seed()
    headers = await login("boss", all_customers=True)
    body = client.get("/api/dashboard/alerts", headers=headers).json()
    assert {c["customer_id"] for c in body["certificates"]} == {ACME, BETA}
    assert ("fw.beta.example", BETA) in {
        (d["device_key"], d["customer_id"]) for d in body["firmware"]
    }


async def test_a_broken_store_narrows_varsler_instead_of_emptying_it(client, monkeypatch):
    await _seed()

    async def _broken(*args, **kwargs):
        raise RuntimeError("no such table")

    monkeypatch.setattr("app.services.tls_inventory.attention", _broken)
    headers = await login("tech-acme", customers=(ACME,))
    body = client.get("/api/dashboard/alerts", headers=headers).json()
    assert body["certificates"] == []
    assert body["coverage"]["tls"] == {"unavailable": True}
    assert {d["device_key"] for d in body["firmware"]} == {"eol-ap", "old-switch"}


async def test_the_alert_config_says_whether_teams_can_actually_be_reached(client):
    from app.core.config import update_app_settings

    headers = await login("tech", all_customers=True)
    cfg = client.get("/api/alerts/config", headers=headers).json()
    assert cfg["notify_teams"] is True, "the default switch is on"
    assert cfg["teams_webhook_set"] is False, "but nothing is stored to send to"

    update_app_settings(
        lambda s: s.setdefault("scheduler", {}).update({"webhook_url": "https://hook.example/x"})
    )
    cfg = client.get("/api/alerts/config", headers=headers).json()
    assert cfg["teams_webhook_set"] is True
    assert "hook.example" not in str(cfg), "whether one is set, never the URL"


async def test_renewals_are_not_listed_while_the_billing_module_is_off(client, monkeypatch):
    """With billing off its ALSO sync no longer runs; what is stored only ages
    and is not Varsler material. Certificates and firmware are core and stay."""
    from app.core import modules
    from app.core.orm import get_session
    from app.models.integrations import AlsoRenewal

    await _seed()
    async with get_session() as s:
        s.add(
            AlsoRenewal(
                customer_id=ACME,
                customer_name="Acme AS",
                subscription_id="sub-1",
                service_name="M365",
                service_display="Microsoft 365",
                contract_end=(datetime.now(UTC) + timedelta(days=3)).isoformat(),
                scanned_at=datetime.now(UTC).isoformat(),
            )
        )
        await s.commit()
    headers = await login("tech-acme", customers=(ACME,))
    assert len(client.get("/api/dashboard/alerts", headers=headers).json()["renewals"]) == 1

    others = {m.key: m.key != "billing" for m in modules.MODULES}
    monkeypatch.setattr(modules, "_stored", lambda: dict(others))
    body = client.get("/api/dashboard/alerts", headers=headers).json()
    assert body["renewals"] == []
    assert body["certificates"] and body["firmware"]
