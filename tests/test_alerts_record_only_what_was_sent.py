"""An alert that reached nobody must not be marked as sent.

The history is what ``_is_duplicate`` suppresses against for the next 24
hours, and ``run_alert_check`` wrote it whether or not a channel had accepted
anything. A webhook URL left blank, an SMTP server refusing, or notifications
simply switched off marked every new alert as sent — and the next run
deduplicated it away. A critical certificate-expiry alert whose only channel
was broken was raised once, delivered nowhere, and never mentioned again.

Two smaller versions of the same habit sat beside it. ``send_email_alert``
returned None and swallowed its exception, so the caller counted a channel as
notified on the strength of having called it. And every check logged its
failure and returned an empty list, so "Fant 0 varsler" was the same sentence
whether every certificate was healthy or the table holding them had gone
missing.
"""

from __future__ import annotations

import pytest

from app.services import alert_engine as ae


@pytest.fixture
def engine(monkeypatch, tmp_path):
    """run_alert_check with every side effect under the test's control."""
    history: list[dict] = []
    monkeypatch.setattr(ae, "_load_alert_history", lambda: list(history))
    monkeypatch.setattr(ae, "_save_alert_history",
                        lambda h: (history.clear(), history.extend(h)))
    monkeypatch.setattr(ae, "load_app_settings",
                        lambda: {"scheduler": {"webhook_url": "https://example.invalid/hook"}})
    monkeypatch.setattr(ae, "get_alert_config", lambda: {
        "enabled": True, "notify_teams": True, "notify_email": False,
        "rules": {"ssl_expiry": {"enabled": True, "days": 14},
                  "policy_drift": {"enabled": False},
                  "pentest_critical": {"enabled": False}},
    })

    alert = {
        "type": "ssl_expiry", "severity": "critical", "customer": "Acme AS",
        "item": "acme.no", "detail": "SSL-sertifikat utløper om 2 dager",
        "days_remaining": 2,
    }

    async def _ssl(_days):
        return [dict(alert)]
    monkeypatch.setattr(ae, "_check_ssl_expiry", _ssl)
    return history


def _webhook(monkeypatch, ok: bool):
    async def _send(*a, **k):
        return ok
    import app.services.webhook_sender as ws
    monkeypatch.setattr(ws, "send_webhook", _send)


# ── The suppression ──────────────────────────────────────────────────────────

async def test_a_delivered_alert_is_recorded(engine, monkeypatch):
    _webhook(monkeypatch, True)
    result = await ae.run_alert_check()
    assert result["new_alerts"] == 1
    assert result["channels_notified"] == 1
    assert len(engine) == 1, "a delivered alert must be remembered, or it repeats"


async def test_an_undelivered_alert_is_not_recorded(engine, monkeypatch):
    _webhook(monkeypatch, False)
    result = await ae.run_alert_check()
    assert result["new_alerts"] == 1
    assert result["channels_notified"] == 0
    assert engine == [], (
        "the alert reached nobody and was written to history anyway — the next "
        "run will deduplicate it away"
    )


async def test_and_so_the_next_run_raises_it_again(engine, monkeypatch):
    _webhook(monkeypatch, False)
    await ae.run_alert_check()
    second = await ae.run_alert_check()
    assert second["new_alerts"] == 1, (
        "a critical alert that was never delivered went quiet on the second run"
    )


async def test_once_it_lands_it_stops_repeating(engine, monkeypatch):
    _webhook(monkeypatch, False)
    await ae.run_alert_check()
    _webhook(monkeypatch, True)
    assert (await ae.run_alert_check())["new_alerts"] == 1
    assert (await ae.run_alert_check())["new_alerts"] == 0


async def test_no_channel_configured_is_not_delivery(engine, monkeypatch):
    monkeypatch.setattr(ae, "load_app_settings", lambda: {"scheduler": {"webhook_url": ""}})
    result = await ae.run_alert_check()
    assert result["channels_notified"] == 0
    assert engine == [], "notifications switched off silently consumed the alert"


# ── The email channel ────────────────────────────────────────────────────────

async def test_a_failed_email_is_not_counted_as_a_channel(monkeypatch):
    import app.core.email_sender as es

    def _boom(**kwargs):
        raise OSError("SMTP server refused the connection")
    monkeypatch.setattr(es, "send_report_email", _boom)
    sent = await ae.send_email_alert({}, "drift@sybr.no", [
        {"severity": "critical", "type": "ssl_expiry", "customer": "Acme",
         "item": "acme.no", "detail": "x"},
    ])
    assert sent is False


async def test_a_successful_email_reports_success(monkeypatch):
    import app.core.email_sender as es
    monkeypatch.setattr(es, "send_report_email", lambda **kw: None)
    sent = await ae.send_email_alert({}, "drift@sybr.no", [
        {"severity": "warning", "type": "ssl_expiry", "customer": "Acme",
         "item": "acme.no", "detail": "x"},
    ])
    assert sent is True


async def test_nothing_to_send_is_not_a_send():
    assert await ae.send_email_alert({}, "drift@sybr.no", []) is False
    assert await ae.send_email_alert({}, "", [{"severity": "critical"}]) is False


# ── The broken check ─────────────────────────────────────────────────────────

async def test_a_check_that_could_not_run_is_named(engine, monkeypatch):
    _webhook(monkeypatch, True)

    async def _boom(_days):
        raise ae.AlertCheckFailed("ssl_expiry")
    monkeypatch.setattr(ae, "_check_ssl_expiry", _boom)

    result = await ae.run_alert_check()
    assert result["total_found"] == 0
    assert result["failed_checks"] == ["ssl_expiry"], (
        "zero alerts and a broken check produced the same summary"
    )


async def test_a_broken_check_does_not_stop_the_others(engine, monkeypatch):
    _webhook(monkeypatch, True)

    async def _boom(_days):
        raise ae.AlertCheckFailed("ssl_expiry")

    async def _drift(_changed):
        return [{"type": "policy_drift", "severity": "warning", "customer": "Acme",
                 "item": "CA-policy", "detail": "endret"}]
    monkeypatch.setattr(ae, "_check_ssl_expiry", _boom)
    monkeypatch.setattr(ae, "_check_policy_drift", _drift)
    monkeypatch.setattr(ae, "get_alert_config", lambda: {
        "enabled": True, "notify_teams": True, "notify_email": False,
        "rules": {"ssl_expiry": {"enabled": True, "days": 14},
                  "policy_drift": {"enabled": True},
                  "pentest_critical": {"enabled": False}},
    })
    result = await ae.run_alert_check()
    assert result["total_found"] == 1
    assert result["failed_checks"] == ["ssl_expiry"]


async def test_a_healthy_run_names_nothing(engine, monkeypatch):
    _webhook(monkeypatch, True)
    assert (await ae.run_alert_check())["failed_checks"] == []


def test_every_check_reports_its_own_name():
    # The wrapper has a fallback, but a check that swallows its exception
    # cannot reach it. This is what makes failed_checks trustworthy.
    import inspect
    source = inspect.getsource(ae)
    for name in ("ssl_expiry", "domain_expiry", "fortigate_threats",
                 "firmware_outdated", "also_license_expiry", "policy_drift",
                 "mfa_coverage"):
        assert f'raise AlertCheckFailed("{name}")' in source, (
            f"_check_{name} still swallows its failure and returns no alerts"
        )


# ── One tenant must not take the others with it ──────────────────────────────
#
# test_policy_drift_alert.py already required that a failure reading one tenant
# does not lose the run, and it was enforced by the check swallowing everything
# — which is the habit this file is about. Making the check raise would have
# traded one silence for another: the loop sits inside the try, so the first
# customer that failed ended the sweep and every tenant sorted after it went
# unexamined, with the partial result returned as the whole answer.

async def test_one_unreadable_tenant_does_not_hide_the_next(tmp_path, monkeypatch):
    from app.core import policy_drift as pd
    from app.services.alert_engine import _check_policy_drift

    root = tmp_path / "audits"
    for name in ("Aaa_AS", "Bbb_AS"):
        (root / name / "2026-01-01_0900").mkdir(parents=True)

    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: root)
    monkeypatch.setattr("app.core.customer.CustomerManager.list_customers", lambda: [])

    def _drift(run):
        if "Aaa_AS" in str(run):
            raise RuntimeError("unreadable snapshot")
        return {
            "measured": True, "compared_with": "2025-12-01_0900",
            "snapshots": [{
                "name": "conditional_access_policies", "comparable": True,
                "removed": [{"name": "Require MFA"}], "changed": [],
            }],
        }
    monkeypatch.setattr(pd, "compute_drift", _drift)

    alerts = await _check_policy_drift()
    assert [a["customer"] for a in alerts] == ["Bbb_AS"], (
        "the tenant sorted after the unreadable one was never examined"
    )
