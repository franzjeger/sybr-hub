"""Regression cases from GR2: secrets, old runs and unavailable measurements."""

from __future__ import annotations

import csv
import io
from unittest.mock import AsyncMock

import pytest

from app.core.customer import CustomerManager
from app.core.encryption import encrypted_read_json, encrypted_write_json, encrypted_write_text
from app.models.user import Role
from app.modules.base import SectionResult, SectionStatus
from app.reports.generator import build_report_context, generate_reports
from tests.request_body_fixtures import (
    _client,
    _init_db,
    _reset_middleware_state,
    _token,
    admin_client,
    tech_client,
)

SECRET = "october-regression-device-password"
WEBHOOK = "https://hooks.example.test/services/october-secret"


@pytest.fixture()
async def viewer_client():
    with _client(await _token("october-viewer", Role.viewer)) as client:
        yield client


@pytest.fixture()
def customer():
    return CustomerManager.save_customer(
        {
            "CustomerName": "October Acme",
            "TenantId": "october-tenant",
            "UniFiMode": "direct",
            "UniFiDirectDevices": [{"host": "192.0.2.10", "password": SECRET}],
            "FutureSecretField": SECRET,
        }
    )


async def test_read_surfaces_never_return_stored_secrets(viewer_client, customer, monkeypatch):
    """The same sentinel is searched in every customer/config GET response."""
    monkeypatch.setattr("app.core.config.get_scheduler_config", lambda: {"webhook_url": WEBHOOK})
    paths = [
        "/api/customers",
        "/api/scheduler",
        "/api/settings",
        f"/api/network-devices/{customer}",
        f"/api/network/config-backups/{customer}",
    ]
    for path in paths:
        response = viewer_client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert SECRET not in response.text, path
        assert WEBHOOK not in response.text, path
    listing = viewer_client.get("/api/customers").json()["customers"][0]
    assert "_dir" not in listing
    assert listing["CustomerName"] == "October Acme"
    assert viewer_client.get("/api/scheduler").json()["webhook_url_set"] is True


@pytest.mark.parametrize("folder", ["fortigate_backups", "network_configs"])
async def test_raw_backup_download_requires_technician(
    viewer_client, tech_client, customer, tmp_path, monkeypatch, folder
):
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path)
    backup = tmp_path / "October_Acme" / folder / "saved.cfg"
    backup.parent.mkdir(parents=True)
    encrypted_write_text(backup, SECRET)
    url = f"/audit_data/October_Acme/{folder}/saved.cfg"
    assert viewer_client.get(url).status_code == 403
    response = tech_client.get(url)
    assert response.status_code == 200 and response.text == SECRET


async def test_admin_scheduler_read_masks_webhook_too(admin_client, monkeypatch):
    monkeypatch.setattr("app.core.config.get_scheduler_config", lambda: {"webhook_url": WEBHOOK})
    response = admin_client.get("/api/scheduler")
    assert WEBHOOK not in response.text
    assert response.json()["webhook_url_set"]
    settings = {"scheduler": {"webhook_url": WEBHOOK}}
    monkeypatch.setattr("app.core.config.update_app_settings", lambda update: update(settings))
    response = admin_client.post("/api/scheduler", json={"webhook_url": "••••••"})
    assert response.status_code == 200, response.text
    assert settings["scheduler"]["webhook_url"] == WEBHOOK
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.webhook_sender.send_simple_message", sender)
    response = admin_client.post("/api/scheduler/test-webhook", json={"webhook_url": "••••••"})
    assert response.status_code == 200, response.text
    assert sender.await_args.args[0] == WEBHOOK
    response = admin_client.post("/api/scheduler", json={"webhook_url": ""})
    assert response.status_code == 200, response.text
    assert settings["scheduler"]["webhook_url"] == ""


async def test_technician_cannot_install_persistent_firewall_credentials(
    tech_client, customer, monkeypatch
):
    bootstrap = AsyncMock()
    monkeypatch.setattr("app.services.fortigate_api.factory_bootstrap", bootstrap)
    monkeypatch.setattr("app.core.credentials.get_secret", lambda *args: SECRET)
    assert (
        tech_client.post(
            f"/api/fortigate/deploy-key/{customer}",
            json={"admin_user": "admin", "public_key": "ssh-ed25519 dummy"},
        ).status_code
        == 403
    )
    assert (
        tech_client.post(
            f"/api/fortigate/generate-token/{customer}",
            json={"ssh_host": "192.0.2.1", "ssh_password": SECRET},
        ).status_code
        == 403
    )
    response = tech_client.post(
        "/api/fortigate/bootstrap", json={"customer_id": customer, "host": "192.0.2.1"}
    )
    assert response.status_code == 403, response.text
    bootstrap.assert_not_awaited()


@pytest.mark.parametrize("path", [".", "October_Acme", "October_Acme/.."])
async def test_archive_deletion_cannot_remove_root_or_customer(
    admin_client, tmp_path, monkeypatch, path
):
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path)
    (tmp_path / "October_Acme").mkdir()
    response = admin_client.post("/api/reports/archive/delete", json={"path": path})
    assert response.status_code == 403, response.text
    assert (tmp_path / "October_Acme").is_dir()


async def test_excel_export_preserves_unknowns_and_neutralises_formulas(
    admin_client, tmp_path, monkeypatch
):
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path)
    CustomerManager.save_customer({"CustomerName": "=HYPERLINK(attacker)", "PrimaryDomain": "+cmd"})
    from app.core.customer import customer_dir_name

    run = tmp_path / customer_dir_name("=HYPERLINK(attacker)") / "2026-10-01_090000"
    run.mkdir(parents=True)
    encrypted_write_json(
        run / "_audit_metrics.json",
        {"mfa_coverage_pct": None, "secure_score_pct": None, "intune_compliance_pct": None},
    )
    response = admin_client.post("/api/export/excel", json={"lang": "no"})
    assert response.status_code == 200, response.text
    header, row = list(csv.reader(io.StringIO(response.text.lstrip("\ufeff")), delimiter=";"))[:2]
    cells = dict(zip(header, row, strict=True))
    # An unknown is left empty and named, never written as 0.
    assert cells["MFA-dekning %"] == "" and cells["Secure Score %"] == ""
    assert "MFA-dekning %" in cells["Ikke målte verdier"]
    assert "'=HYPERLINK" in response.text and "'+cmd" in response.text


def test_report_rendering_does_not_change_metrics_or_latest_row(tmp_path, monkeypatch):
    run = tmp_path / "Acme" / "2026-02-01_090000"
    run.mkdir(parents=True)
    original = {"timestamp": "2026-02-01T09:00:00Z", "mfa_coverage_pct": 50}
    encrypted_write_json(run / "_audit_metrics.json", original)
    monkeypatch.setattr(
        "app.reports.generator.save_audit_metrics",
        lambda *a, **kw: pytest.fail("Rendering persisted metrics"),
    )
    generate_reports("Acme", "", run, [], formats=["html"])
    assert encrypted_read_json(run / "_audit_metrics.json") == original


def test_failed_read_is_absent_from_trends_and_timeline(tmp_path):
    parent = tmp_path / "Acme"
    previous = parent / "2026-01-01_090000"
    current = parent / "2026-02-01_090000"
    previous.mkdir(parents=True)
    current.mkdir()
    encrypted_write_json(
        previous / "_audit_metrics.json",
        {"mfa_coverage_pct": 92, "users_no_mfa": 4, "admin_roles_ga_count": 3},
    )
    context = build_report_context("Acme", "", current, [], persist_metrics=False)
    assert "mfa_coverage_pct" not in context["trends"]
    assert "users_no_mfa" not in context["trends"]
    assert context["metrics_timeline"][-1]["mfa_coverage_pct"] is None


def test_no_azure_subscription_is_not_a_score_gap(tmp_path):
    run = tmp_path / "Acme" / "2026-01-01"
    run.mkdir(parents=True)
    results = [
        SectionResult(name=f"Azure {name}", status=SectionStatus.SKIPPED)
        for name in ("Network", "Storage", "Compute", "Governance")
    ]
    context = build_report_context("Acme", "", run, results, persist_metrics=False)
    assert not any("Azure" in str(issue) for issue in context["risk"]["data_quality_issues"])


@pytest.mark.parametrize("section", ["network", "storage", "compute", "governance"])
async def test_azure_rejected_reads_report_failed(tmp_path, section):
    import importlib

    module = importlib.import_module(f"app.modules.m365_audit.sections.azure_{section}")
    cls = getattr(module, f"Azure{section.title()}Section")

    class RefusedAuth:
        def __getattr__(self, key):
            def refused(*args):
                raise RuntimeError("permission denied")

            return refused

    collector = cls(tmp_path, RefusedAuth(), sub_id="subscription")
    result = await collector.collect()
    assert result.status == SectionStatus.FAILED
    assert collector._failures


async def test_huge_subnet_is_rejected_before_enumerating_hosts(monkeypatch):
    from app.modules.unifi_audit.scanner import scan_subnet

    monkeypatch.setattr(
        "ipaddress.IPv4Network.hosts", lambda self: pytest.fail("enumerated huge subnet")
    )
    result = await scan_subnet("10.0.0.0/8")
    assert "error" in result[0]


@pytest.mark.parametrize("value", ["Acme A/S", "x/../../escaped", "a\\b", "a..b"])
def test_imported_customer_names_cannot_be_paths(value):
    from app.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        CustomerManager.save_customer({"CustomerName": value})


@pytest.mark.parametrize("month,hour", [(1, 6), (7, 5)])
def test_weekly_schedule_uses_oslo_wall_clock(monkeypatch, month, hour):
    from datetime import UTC, datetime

    from app.services import scheduler

    now = datetime(2026, month, 5 if month == 1 else 6, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(scheduler, "_now", lambda: now)
    monkeypatch.setattr("app.core.config.load_app_settings", lambda: {"timezone": "Europe/Oslo"})
    due = scheduler._compute_next_run({"type": "weekly", "day": "monday", "time": "07:00"})
    assert due.hour == hour and due.weekday() == 0


async def test_completed_webhook_says_not_measured_and_escapes_name(monkeypatch):
    from app.services.audit_scheduler import AuditScheduler

    monkeypatch.setattr(
        "app.services.audit_scheduler.get_scheduler_config",
        lambda: {"alert_on": {"audit_completed": True}},
    )
    scheduler = AuditScheduler()
    scheduler._send_webhook = AsyncMock()
    await scheduler._notify_audit_completed(
        "[click](https://attacker.test) HTTPS://attacker.test www.attacker.test",
        {"risk": {"grade": "?", "score": None}, "mfa": {"has_data": False, "pct": 0}},
    )
    message = scheduler._send_webhook.await_args.args[0]
    assert "ikke målt" in message
    assert "0%" not in message and "https://attacker" not in message.lower()
    assert "www.attacker" not in message.lower()


def test_failed_forwarding_read_is_visible_in_score_gaps(tmp_path):
    from tests.audit_fixture import FULL_AUDIT

    run = tmp_path / "Acme" / "2026-01-01"
    run.mkdir(parents=True)
    for name, content in FULL_AUDIT.items():
        if name.startswith("28b_"):
            continue
        encrypted_write_text(run / name, content)
    encrypted_write_text(run / "28_exchange_mailbox_forwarding.txt", "Error: permission denied\n")
    context = build_report_context("Acme", "", run, [], persist_metrics=False)
    assert any("Videresending" in issue for issue in context["risk"]["data_quality_issues"])
    assert context["risk"]["has_full_data"] is False
