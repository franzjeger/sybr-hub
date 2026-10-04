"""Where UniFi devices report in is a setting, not one MSP's host in the code.

Set-Inform on the scan results offered "unifi.sybr.no" as its only preset, the
quick check's cards asked with a browser prompt(), and provisioning pointed
DHCP option 43 at the same host whenever the wizard left it blank. The host is
``unifi_inform_host`` in the app settings now (Administrasjon > Integrasjoner >
UniFi): Set-Inform starts from it and provisioning falls back to it.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.services import provisioning
from tests.request_body_fixtures import (  # autouse fixtures apply to this module
    _init_db,
    _reset_middleware_state,
    admin_client,
    tech_client,
)


def _stored() -> dict:
    from app.core.config import load_app_settings

    return load_app_settings()


async def test_the_inform_host_is_saved_read_back_and_cleared(admin_client):
    r = admin_client.post("/api/settings", json={"unifi_inform_host": " unifi.example.com "})
    assert r.status_code == 200, r.text
    assert _stored()["unifi_inform_host"] == "unifi.example.com"
    assert admin_client.get("/api/settings").json()["unifi_inform_host"] == "unifi.example.com"

    # Another card saving leaves it alone; sent empty, it goes.
    admin_client.post("/api/settings", json={"itglue_region": "eu"})
    assert _stored()["unifi_inform_host"] == "unifi.example.com"
    admin_client.post("/api/settings", json={"unifi_inform_host": ""})
    assert "unifi_inform_host" not in _stored()


async def test_an_inform_host_that_is_not_a_host_is_refused(admin_client):
    r = admin_client.post("/api/settings", json={"unifi_inform_host": "x; reboot"})
    assert r.status_code == 400, r.text
    assert "unifi_inform_host" not in _stored()


async def test_only_an_admin_sets_it(tech_client):
    r = tech_client.post("/api/settings", json={"unifi_inform_host": "unifi.example.com"})
    assert r.status_code == 403, r.text
    assert "unifi_inform_host" not in _stored()


def _plan(services: dict):
    return provisioning._build_rest_plan(
        {1: {"name": "Acme"}, 2: {"lan_subnet": "192.0.2.0/24"}, 3: services, 4: {}},
        {"host": "192.0.2.1", "port": 443, "customer_id": "acme"},
    )


def test_provisioning_points_option_43_at_the_setting(monkeypatch):
    monkeypatch.setattr(
        "app.core.config.load_app_settings", lambda: {"unifi_inform_host": "unifi.example.com"}
    )
    assert _plan({}).unifi_controller_host == "unifi.example.com"
    # The wizard's own value still wins.
    assert _plan({"unifi_controller_host": "192.0.2.50"}).unifi_controller_host == "192.0.2.50"


def test_with_no_host_there_is_no_option_43(monkeypatch):
    monkeypatch.setattr("app.core.config.load_app_settings", lambda: {})
    assert _plan({}).unifi_controller_host == ""
    # gethostbyname("") is 0.0.0.0: devices would be told to inform nowhere.
    assert provisioning._unifi_option43("") == ""


def test_no_company_domain_is_written_into_the_application():
    """An installation's own hosts are settings. Comments may say what they replaced."""
    pattern = re.compile(r"\bsybr\.no\b|unihosted\.com")
    offenders = []
    for path in Path("app").rglob("*"):
        if path.suffix not in {".py", ".js", ".html", ".json", ".j2"} or "vendor" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path}:{number}: {line.strip()[:100]}")
    assert not offenders, "\n".join(offenders)
