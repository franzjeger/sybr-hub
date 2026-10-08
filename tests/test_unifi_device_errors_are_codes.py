"""Why a direct UniFi device could not be read: a code the report and the interface word.

The network audit stored the device client's English ("SSH timeout",
"Connection failed"), and the customer report put it in a Norwegian table's
status cell (TODO C15). The audit's own reasons are codes now; an exception's
message is the data it is, and stays as it was.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pytest

from app.reports.i18n import T
from app.reports.parsers.network import device_error_text


class _Device:
    """A UniFiDirectDevice that answers per host: a reading, a client error, or a raise."""

    answers: ClassVar[dict] = {}

    def __init__(self, host, **_kwargs):
        self.host = host

    async def __aenter__(self):
        answer = self.answers[self.host]
        if isinstance(answer, Exception):
            raise answer
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get_device_info_http(self):
        return {}  # no web interface answered

    async def get_device_info_ssh(self):
        return self.answers[self.host] if isinstance(self.answers[self.host], dict) else {}


@pytest.fixture
def audit_direct(monkeypatch):
    from app.modules.unifi_audit import client
    from app.services import firmware_inventory, network_audit

    async def quietly(*_args, **_kwargs):
        return None

    monkeypatch.setattr(client, "UniFiDirectDevice", _Device)
    monkeypatch.setattr(firmware_inventory, "record_quietly", quietly)
    monkeypatch.setattr("app.core.credentials.get_secret", lambda *_a: "")

    async def run(answers: dict) -> dict:
        _Device.answers = answers
        result = await network_audit._audit_unifi_direct(
            "acme", [{"host": host} for host in answers]
        )
        return {d["host"]: d for d in result["devices"]}

    return run


async def test_the_audit_stores_its_own_reasons_as_codes(audit_direct):
    devices = await audit_direct(
        {
            "192.0.2.10": {"error": "SSH timeout"},
            "192.0.2.11": {
                "error": "sshpass not installed — run: brew install hudochenkov/sshpass/sshpass"
            },
            "192.0.2.12": {},
            "192.0.2.13": OSError("No route to host"),
        }
    )

    assert devices["192.0.2.10"]["error"] == "ssh_timeout"
    assert devices["192.0.2.11"]["error"] == "sshpass_missing"
    assert devices["192.0.2.12"]["error"] == "connection_failed"
    # An exception's message is data: kept as it was.
    assert devices["192.0.2.13"]["error"] == "No route to host"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("ssh_timeout", "SSH svarte ikke i tide"),
        ("connection_failed", "Enheten svarte verken på HTTP eller SSH"),
        # An old run's English, read back to the same words.
        ("SSH timeout", "SSH svarte ikke i tide"),
        ("Connection failed", "Enheten svarte verken på HTTP eller SSH"),
        ("No route to host", "No route to host"),
    ],
)
def test_the_report_words_a_code_and_keeps_an_exceptions_message(error, expected):
    assert device_error_text(error, T("no")) == expected


def test_every_reason_is_worded_in_both_tables():
    from app.reports.i18n import TRANSLATIONS
    from app.services.network_audit import DEVICE_READ_ERRORS

    ui = json.loads(Path("app/web/static/ui_i18n.json").read_text(encoding="utf-8"))
    for code in DEVICE_READ_ERRORS:
        for lang in ("no", "en"):
            assert TRANSLATIONS[f"unifi_error_{code}"][lang].strip()
            assert ui[lang][f"unifi_error_{code}"].strip()


@pytest.mark.parametrize("mode", ["controller", "direct"])
def test_the_customer_reports_device_table_words_the_status(tmp_path, mode):
    import re

    from app.reports.generator import _jinja_env, build_report_context

    if mode == "controller":
        devices = [
            {"name": "ap-lager", "model": "U6-Pro", "firmware": "6.6.77", "status": "online"},
            {"name": "ap-kontor", "model": "U6-Pro", "firmware": "6.6.77", "status": "offline"},
        ]
    else:
        devices = [
            {"host": "192.0.2.10", "label": "ap-lager", "ok": True, "mac": "02:00:00:00:00:10"},
            {"host": "192.0.2.11", "label": "ap-kontor", "ok": False, "error": "ssh_timeout"},
        ]
    run = tmp_path / "Acme_AS" / "2026-10-03_0900"
    run.mkdir(parents=True)
    unifi = {"mode": mode, "device_count": 2, "reachable": 1, "devices": devices}
    if mode == "controller":
        unifi.update(wlan_count=0, network_count=1, firewall_rules=0, active_alarms=0)
    (run / "61_unifi_audit.txt").write_text(json.dumps(unifi), encoding="utf-8")
    ctx = build_report_context("Acme AS", "acme.example", run, [], lang="no", persist_metrics=False)
    ctx.update(t=T("no"), lang="no", theme="light")
    page = _jinja_env().get_template("report_customer.html.j2").render(**ctx)

    def status(name: str) -> str:
        row = re.search(rf"<td>{name}</td>(.*?)</tr>", page, re.S)
        assert row, name
        cell = re.findall(r"<td[^>]*>(.*?)</td>", row.group(1), re.S)[-1]
        return " ".join(re.sub(r"<[^>]+>", " ", cell).split())

    assert status("ap-lager") == "Tilkoblet"
    expected = "Frakoblet" if mode == "controller" else "Frakoblet SSH svarte ikke i tide"
    assert status("ap-kontor") == expected
