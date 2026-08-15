"""A device the audit could not read is never a device with a clean bill.

This is the defect the architecture doc names — "a refusal is not a zero" —
still living in the FortiGate and UniFi clients after the M365 pipeline was
rebuilt around it. Both clients answered a failed read with a sentinel a
consumer could not tell from an empty result: UniFi returned ``[]``, FortiGate
returned ``{"error":...}``. So a controller that answered 403 became "0
devices", a firewall the audit could not reach scored 100, and a CIS control
whose config could not be read was silently dropped — or worse, given a
fabricated verdict.

Every test here drives a *failed* read into a customer-facing audit and asserts
it does not render as clean. Every one has a sibling asserting a *genuinely
empty* read still renders as empty — because flagging a healthy tenant as
unavailable would be the same defect pointed the other way.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.modules.api_result import ApiDict, ApiList

# ── Mock clients ─────────────────────────────────────────────────────────────

def _fg(handler):
    """A real FortiGateClient whose transport answers `handler`."""
    from app.modules.fortigate_audit.client import FortiGateClient

    fg = FortiGateClient("10.0.0.1", api_token="t", verify_ssl=False)
    fg._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=fg.base_url,
        headers=fg._client.headers,
    )
    return fg


def _fg_all(status: int = 200, *, json_body=None):
    """Handler: every FortiGate request answers `status` with `json_body`."""
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, text="nope")
        return httpx.Response(200, json=json_body if json_body is not None else {"results": []})
    return handler


def _unifi_class(*, fail: bool = False, data=None):
    """A UniFiControllerClient subclass with a mock transport and no-op login."""
    from app.modules.unifi_audit.client import UniFiControllerClient

    def handler(request: httpx.Request) -> httpx.Response:
        if "login" in request.url.path:
            return httpx.Response(200, json={})
        if fail:
            return httpx.Response(403, text="forbidden")
        return httpx.Response(200, json={"data": data or [], "meta": {"rc": "ok"}})

    class _Patched(UniFiControllerClient):
        def __init__(self, *a, **k):
            super().__init__("https://ctrl", "u", "p")
            self._client = httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url=self.host,
            )

        async def _login(self):
            self._logged_in = True

    return _Patched


def _unifi_partial_class(*, fail_suffixes: tuple[str, ...]):
    """A controller client that 403s only on endpoints ending in one of
    ``fail_suffixes`` (e.g. "/stat/alarm"), and answers everything else 200.

    Models the real failure mode the sentinel fix has to survive: the anchor
    device read succeeds while an independent secondary read refuses.
    """
    from app.modules.unifi_audit.client import UniFiControllerClient

    def handler(request: httpx.Request) -> httpx.Response:
        if "login" in request.url.path:
            return httpx.Response(200, json={})
        if any(request.url.path.endswith(s) for s in fail_suffixes):
            return httpx.Response(403, text="forbidden")
        return httpx.Response(200, json={"data": [], "meta": {"rc": "ok"}})

    class _Patched(UniFiControllerClient):
        def __init__(self, *a, **k):
            super().__init__("https://ctrl", "u", "p")
            self._client = httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url=self.host,
            )

        async def _login(self):
            self._logged_in = True

    return _Patched


@pytest.fixture()
def _fg_build(monkeypatch):
    """Route fortigate_api._build_client to a chosen handler."""
    def _install(handler):
        monkeypatch.setattr(
            "app.services.fortigate_api._build_client", lambda config, token: _fg(handler)
        )
    return _install


@pytest.fixture()
def _unifi_customer(monkeypatch):
    """A customer whose UniFi controller answers through a chosen client class."""
    from app.core.customer import CustomerManager

    monkeypatch.setattr(
        CustomerManager, "get_customer",
        staticmethod(lambda cid: {
            "CustomerId": cid, "CustomerName": "Acme", "UniFiHost": "https://ctrl",
            "UniFiSite": "default",
        }),
    )
    monkeypatch.setattr("app.services.unifi_api.get_secret", lambda cid, k: "x")

    def _install(cls):
        async def _controller(customer_id):
            c = cls()
            c._logged_in = True
            return c
        monkeypatch.setattr("app.services.unifi_api._controller_for_customer", _controller)
        monkeypatch.setattr("app.services.unifi_api._default_site", lambda cid: "default")

    return _install


# ═══════════════════════════════════════════════════════════════════════════
# FortiGate CIS compliance — the worst offender: dropped findings AND
# fabricated verdicts from the error sentinel.
# ═══════════════════════════════════════════════════════════════════════════

async def test_cis_compliance_marks_unread_controls_unknown_not_dropped(_fg_build):
    from app.services.fortigate_api import check_compliance

    _fg_build(_fg_all(403))
    result = await check_compliance({}, "t")

    ids = {f["id"] for f in result["findings"]}
    # Every control still appears — none silently dropped.
    for cid in ("CIS-1.1", "CIS-1.2", "CIS-2.1", "CIS-3.1", "CIS-4.1", "CIS-5.1", "CIS-5.2"):
        assert cid in ids, f"{cid} was dropped on a failed read"
    # And every one is unknown — none given a fabricated pass/fail/warn.
    assert all(f["status"] == "unknown" for f in result["findings"])
    assert result["complete"] is False


async def test_cis_compliance_does_not_fabricate_a_password_policy_fail(_fg_build):
    """The concrete lie: a failed password-policy read used to manufacture
    'CIS-5.1 fail: password policy is not enabled'."""
    from app.services.fortigate_api import check_compliance

    _fg_build(_fg_all(403))
    result = await check_compliance({}, "t")

    pp = next(f for f in result["findings"] if f["id"] == "CIS-5.1")
    assert pp["status"] == "unknown"
    assert "not enabled" not in pp["detail"]


async def test_cis_compliance_score_is_not_inflated_by_unread_controls(_fg_build):
    """An unread control neither passes nor fails, so the score reflects only
    what was assessed — never a firewall that refused every read."""
    from app.services.fortigate_api import check_compliance

    _fg_build(_fg_all(403))
    result = await check_compliance({}, "t")
    s = result["summary"]

    assert s["pass"] == 0
    assert s["unknown"] == len(result["findings"])
    assert s["score"] == 0  # 0 assessable → 0, not 100


async def test_cis_compliance_still_scores_a_readable_firewall(_fg_build):
    """The other half: a firewall that answers with real (empty) config is
    assessed normally, not flagged unavailable."""
    from app.services.fortigate_api import check_compliance

    # admins/policies empty, single-object configs present and compliant-ish.
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("password-policy"):
            return httpx.Response(200, json={"results": {"status": "enable", "min-length": 12}})
        if path.endswith("system/global"):
            return httpx.Response(200, json={"results": {"admintimeout": 10}})
        if path.endswith("log/setting"):
            return httpx.Response(200, json={"results": {"log-disk": "enable"}})
        if path.endswith("system/ha"):
            return httpx.Response(200, json={"results": {"mode": "standalone"}})
        return httpx.Response(200, json={"results": []})

    _fg_build(handler)
    result = await check_compliance({}, "t")

    assert result["complete"] is True
    assert result["summary"]["unknown"] == 0
    assert result["summary"]["pass"] >= 1  # password policy, logging, timeout


# ═══════════════════════════════════════════════════════════════════════════
# FortiGate audit_firewall_rules — a failed policy read scored 100.
# ═══════════════════════════════════════════════════════════════════════════

async def test_firewall_rule_audit_does_not_score_a_firewall_it_never_read(_fg_build):
    from app.services.fortigate_api import audit_firewall_rules

    _fg_build(_fg_all(403))
    result = await audit_firewall_rules({}, "t")

    assert result["unavailable"] is True
    assert result["score"] is None, "a refused read must not score 100"
    assert result["total_rules"] is None


async def test_firewall_rule_audit_still_scores_a_readable_empty_firewall(_fg_build):
    from app.services.fortigate_api import audit_firewall_rules

    _fg_build(_fg_all(200, json_body={"results": []}))
    result = await audit_firewall_rules({}, "t")

    assert result["unavailable"] is False
    assert result["total_rules"] == 0
    assert result["score"] == 100  # genuinely no policies → perfect, honestly


# ═══════════════════════════════════════════════════════════════════════════
# FortiGate quick audit + fleet poll — "green when broken".
# ═══════════════════════════════════════════════════════════════════════════

async def test_quick_audit_reports_unavailable_when_the_status_read_fails(_fg_build):
    from app.services.fortigate_api import quick_audit_fortigate

    _fg_build(_fg_all(403))
    result = await quick_audit_fortigate({}, "t")

    assert result["unavailable"] is True
    assert result.get("policy_count") in (None, result.get("policy_count"))  # no false 0
    assert "admin_count" not in result or result.get("admin_count") is None


async def test_quick_audit_of_a_readable_firewall_reports_real_counts(_fg_build):
    from app.services.fortigate_api import quick_audit_fortigate

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("system/status"):
            return httpx.Response(200, json={"results": {"hostname": "fw1", "version": "7.4"}})
        return httpx.Response(200, json={"results": []})

    _fg_build(handler)
    result = await quick_audit_fortigate({}, "t")

    assert result["unavailable"] is False
    assert result["policy_count"] == 0
    assert result["admin_count"] == 0
    assert result["hostname"] == "fw1"


# ═══════════════════════════════════════════════════════════════════════════
# UniFi network audit report section — a clean bill for an unreachable ctrl.
# ═══════════════════════════════════════════════════════════════════════════

async def test_unifi_audit_section_is_unavailable_not_zero_devices(monkeypatch):
    import app.modules.unifi_audit.client as client_mod
    from app.services.network_audit import _audit_unifi_controller

    monkeypatch.setattr(client_mod, "UniFiControllerClient", _unifi_class(fail=True))
    monkeypatch.setattr("app.core.credentials.get_secret", lambda cid, k: "x")

    result = await _audit_unifi_controller("acme", {"UniFiHost": "https://ctrl"})

    assert result["unavailable"] is True
    assert result["device_count"] is None, "must not report device_count 0"
    assert result["eol_count"] is None
    assert result["outdated_firmware_count"] is None


async def test_unifi_audit_section_of_an_empty_controller_reports_zero(monkeypatch):
    import app.modules.unifi_audit.client as client_mod
    from app.services.network_audit import _audit_unifi_controller

    monkeypatch.setattr(client_mod, "UniFiControllerClient", _unifi_class(fail=False, data=[]))
    monkeypatch.setattr("app.core.credentials.get_secret", lambda cid, k: "x")

    result = await _audit_unifi_controller("acme", {"UniFiHost": "https://ctrl"})

    assert result["unavailable"] is False
    assert result["device_count"] == 0
    assert result["eol_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# UniFi firmware currency — all_up_to_date on an empty list was True.
# ═══════════════════════════════════════════════════════════════════════════

async def test_firmware_currency_does_not_pass_a_controller_it_never_read(_unifi_customer):
    from app.services.unifi_api import firmware_check_all

    _unifi_customer(_unifi_class(fail=True))
    result = await firmware_check_all("acme")

    assert result["unavailable"] is True
    assert result["all_up_to_date"] is None, "a refused read must not read as all-current"
    assert result["total"] is None


async def test_firmware_currency_of_an_empty_controller_is_all_up_to_date(_unifi_customer):
    from app.services.unifi_api import firmware_check_all

    _unifi_customer(_unifi_class(fail=False, data=[]))
    result = await firmware_check_all("acme")

    assert result.get("unavailable") is not True
    assert result["all_up_to_date"] is True
    assert result["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# UniFi WiFi health — a refused rogue-AP scan read as "0 rogue APs".
# ═══════════════════════════════════════════════════════════════════════════

async def test_wifi_health_does_not_report_zero_rogue_aps_on_a_failed_scan(_unifi_customer):
    from app.services.unifi_api import get_wifi_health

    _unifi_customer(_unifi_class(fail=True))
    result = await get_wifi_health("acme")

    assert result["unavailable"] is True
    assert result["rogue_ap_count"] is None, "a refused scan must not say the air is clear"


async def test_wifi_health_of_a_clean_controller_reports_no_rogues(_unifi_customer):
    from app.services.unifi_api import get_wifi_health

    _unifi_customer(_unifi_class(fail=False, data=[]))
    result = await get_wifi_health("acme")

    assert result.get("unavailable") is not True
    assert result["rogue_ap_count"] == 0


async def test_wifi_health_nulls_client_totals_when_only_the_client_read_refuses(_unifi_customer):
    """Devices and rogue-AP scans answer, but /stat/sta refuses. The client
    totals are computed by summing that failed (empty) list — 0 would read as an
    idle network beside a populated AP table. They must be None."""
    from app.services.unifi_api import get_wifi_health

    _unifi_customer(_unifi_partial_class(fail_suffixes=("/stat/sta",)))
    result = await get_wifi_health("acme")

    assert result.get("unavailable") is not True  # devices+rogues read fine
    assert result["total_wireless_clients"] is None
    assert result["total_wired_clients"] is None


# ═══════════════════════════════════════════════════════════════════════════
# UniFi controller summary — a refused secondary read counted as 0 alarms.
# ═══════════════════════════════════════════════════════════════════════════

async def test_controller_summary_flags_unavailable_when_alarms_refuse(_unifi_customer):
    from app.services.unifi_api import get_controller_summary

    _unifi_customer(_unifi_partial_class(fail_suffixes=("/stat/alarm",)))
    result = await get_controller_summary("acme")

    # The device read answered, but the alarm read refused. len() of the failed
    # list would be 0 — "0 active alarms" for a log nobody could read. The
    # refusal must trip the unavailable flag and the per-site count must be None.
    assert result["unavailable"] is True
    assert result["site_details"][0]["alarms"] is None


async def test_controller_summary_of_a_clean_controller_is_not_unavailable(_unifi_customer):
    from app.services.unifi_api import get_controller_summary

    _unifi_customer(_unifi_class(fail=False, data=[]))
    result = await get_controller_summary("acme")

    assert result.get("unavailable") is False
    assert result["total_alarms"] == 0
    assert result["site_details"][0]["alarms"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# FortiGate threat summary — "0 threats" for logs it could not read.
# ═══════════════════════════════════════════════════════════════════════════

async def test_threat_summary_is_unavailable_when_no_log_reads_succeed(_fg_build):
    from app.services.fortigate_api import get_threat_summary

    _fg_build(_fg_all(403))
    result = await get_threat_summary({}, "t")

    assert result["unavailable"] is True
    assert result["summary"]["total"] is None, "must not report 0 threats for unread logs"


async def test_threat_summary_of_a_quiet_firewall_reports_zero(_fg_build):
    from app.services.fortigate_api import get_threat_summary

    _fg_build(_fg_all(200, json_body={"results": []}))
    result = await get_threat_summary({}, "t")

    assert result.get("unavailable") is not True
    assert result["summary"]["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# FortiGate live dashboard — an unreachable firewall read as healthy-and-idle.
# ═══════════════════════════════════════════════════════════════════════════

async def test_fg_dashboard_is_unavailable_when_status_refuses(_fg_build):
    from app.services.fortigate_api import get_dashboard

    _fg_build(_fg_all(403))
    result = await get_dashboard({}, "t")

    assert result["unavailable"] is True
    # No reassuring zeros for an unreachable device.
    assert result["cpu_percent"] is None
    assert result["memory_percent"] is None
    assert result["vpn_tunnels"] is None
    assert result["ha_mode"] is None


async def test_fg_dashboard_of_a_readable_firewall_reports_real_values(_fg_build):
    from app.services.fortigate_api import get_dashboard

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("system/status"):
            return httpx.Response(200, json={"results": {"hostname": "fw1", "version": "7.4"}})
        return httpx.Response(200, json={"results": []})

    _fg_build(handler)
    result = await get_dashboard({}, "t")

    assert result.get("unavailable") is not True
    assert result["hostname"] == "fw1"
    assert result["vpn_tunnels"] == 0  # genuinely no tunnels, read honestly


async def test_fg_dashboard_nulls_a_count_whose_subread_refused(_fg_build):
    """status answers, but the tunnel read 403s: vpn_tunnels must be None, not 0."""
    from app.services.fortigate_api import get_dashboard

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("system/status"):
            return httpx.Response(200, json={"results": {"hostname": "fw1"}})
        if "vpn/ipsec" in request.url.path:
            return httpx.Response(403, text="nope")
        return httpx.Response(200, json={"results": []})

    _fg_build(handler)
    result = await get_dashboard({}, "t")

    assert result.get("unavailable") is not True
    assert result["vpn_tunnels"] is None, "a refused tunnel read must not read as 0 tunnels"


# ═══════════════════════════════════════════════════════════════════════════
# UniFi enhanced device stats + client inventory — "0 devices/clients" clean.
# These feed the AI console and the live infra panel.
# ═══════════════════════════════════════════════════════════════════════════

async def test_enhanced_device_stats_are_unavailable_on_a_failed_read(_unifi_customer):
    from app.modules.api_result import read_failed
    from app.services.unifi_api import get_enhanced_device_stats

    _unifi_customer(_unifi_class(fail=True))
    result = await get_enhanced_device_stats("acme")

    assert read_failed(result) is True, "a refused controller read must not be an empty fleet"


async def test_enhanced_device_stats_of_an_empty_controller_are_clean(_unifi_customer):
    from app.modules.api_result import read_failed
    from app.services.unifi_api import get_enhanced_device_stats

    _unifi_customer(_unifi_class(fail=False, data=[]))
    result = await get_enhanced_device_stats("acme")

    assert read_failed(result) is False
    assert result == []


async def test_client_inventory_is_unavailable_on_a_failed_read(_unifi_customer):
    from app.modules.api_result import read_failed
    from app.services.unifi_api import get_client_inventory

    _unifi_customer(_unifi_class(fail=True))
    result = await get_client_inventory("acme")

    assert read_failed(result) is True, "a refused read must not read as 0 clients connected"


async def test_client_inventory_of_an_empty_site_is_clean(_unifi_customer):
    from app.modules.api_result import read_failed
    from app.services.unifi_api import get_client_inventory

    _unifi_customer(_unifi_class(fail=False, data=[]))
    result = await get_client_inventory("acme")

    assert read_failed(result) is False
    assert result == []


async def test_wifi_health_unavailable_branch_keeps_the_success_shape(_unifi_customer):
    """The unavailable branch must carry the same keys the success branch does,
    or a consumer reading health/total_*_clients hits a KeyError instead of a
    clean 'unavailable'."""
    from app.services.unifi_api import get_wifi_health

    _unifi_customer(_unifi_class(fail=True))
    result = await get_wifi_health("acme")

    assert result["unavailable"] is True
    for key in ("aps", "ssids", "alerts", "health",
                "total_wireless_clients", "total_wired_clients", "rogue_ap_count"):
        assert key in result, f"unavailable branch is missing '{key}'"
    assert result["total_wireless_clients"] is None
    assert result["total_wired_clients"] is None


# ═══════════════════════════════════════════════════════════════════════════
# Network inventory row — a customer whose only device source refused the read
# must stay in the inventory (with the alert), not vanish as "no network".
# ═══════════════════════════════════════════════════════════════════════════

async def test_inventory_keeps_a_unifi_only_customer_whose_controller_refused(monkeypatch):
    from app.web.routes import dashboard_infra

    class _Ctrl:
        async def get_devices(self, site):
            return ApiList(error="HTTP 403")
        async def get_clients(self, site):
            return ApiList([])
        async def close(self):
            pass

    async def _controller(cid):
        return _Ctrl()

    monkeypatch.setattr("app.services.unifi_api._controller_for_customer", _controller)
    monkeypatch.setattr("app.services.unifi_api._default_site", lambda cid: "default")

    cust = {"_id": "acme", "CustomerName": "Acme",
            "UniFiHost": "https://ctrl", "UniFiMode": "controller"}
    result = await dashboard_infra._build_network_inventory_for_customer(cust)

    assert result is not None, "a UniFi-only customer whose controller refused was dropped"
    assert result["unavailable"] is True
    assert any("UniFi" in a for a in result["alerts"])


async def test_inventory_does_not_add_a_healthy_row_for_an_unreachable_firewall(monkeypatch):
    from app.web.routes import dashboard_infra

    async def _fg_dash(cust, token):
        return {"unavailable": True, "error": "HTTP 403", "hostname": "",
                "vpn_tunnels": None, "cpu_percent": None}

    monkeypatch.setattr("app.services.fortigate_api.get_dashboard", _fg_dash)
    monkeypatch.setattr("app.core.credentials.get_secret", lambda cid, k: "token")

    cust = {"_id": "acme", "CustomerName": "Acme", "FortiGateHost": "10.0.0.1"}
    result = await dashboard_infra._build_network_inventory_for_customer(cust)

    assert result is not None
    assert result["unavailable"] is True
    # No misleading online-looking firewall row was appended for the refused read.
    assert result["devices"]["firewalls"] == []
    assert any("FortiGate" in a for a in result["alerts"])


async def test_inventory_still_drops_a_customer_with_no_network_configured():
    from app.web.routes import dashboard_infra

    result = await dashboard_infra._build_network_inventory_for_customer(
        {"_id": "x", "CustomerName": "X"}
    )
    assert result is None, "a customer with nothing configured is still dropped"


# ═══════════════════════════════════════════════════════════════════════════
# The report generator must survive an unavailable network section.
# Found by adversarial verification: device_count=None was summed into an int.
# ═══════════════════════════════════════════════════════════════════════════

def test_save_audit_metrics_survives_an_unavailable_unifi_section(tmp_path):
    """A refused UniFi read makes the section carry device_count=None. The
    metrics writer summed that into `network_devices` — None + 1 → TypeError,
    aborting the whole report for a customer whose controller merely blinked."""
    from app.reports.generator import save_audit_metrics

    context = {
        "network": {
            "has_data": True,
            "unifi": {"mode": "controller", "unavailable": True,
                      "error": "HTTP 403", "device_count": None,
                      "outdated_firmware_count": None, "eol_count": None},
            "fortigate": {"admins": []},
        },
        "risk": {"grade": "B", "score": 80},
    }
    out = tmp_path / "Acme" / "2026-01-01_0900"
    out.mkdir(parents=True)

    save_audit_metrics(out, context)  # must not raise

    from app.core.encryption import encrypted_read_json
    saved = encrypted_read_json(out / "_audit_metrics.json")
    # The unavailable section contributes no device count, and is not summed.
    assert saved["network_devices"] in (None, 1)  # 1 = the FortiGate, if counted
    assert saved["network_outdated_fw"] is None


def test_build_recommendations_survives_an_unavailable_unifi_section():
    """The recommendation builder reads eol/outdated counts; None must not
    fabricate a finding nor raise."""
    from app.reports.generator import _build_recommendations

    recs = _build_recommendations(
        mfa={"has_data": True, "no_mfa": 0, "pct": 100.0, "total": 5,
             "users": [], "mfa_registered": 5, "ca_covered": 5},
        spf_dmarc=[], secure_score={}, ext_fwd="", risky_users="", licenses=[],
        file_contents={},
        network={"has_data": True,
                 "unifi": {"mode": "controller", "unavailable": True,
                           "error": "HTTP 403", "eol_count": None,
                           "outdated_firmware_count": None}},
    )
    # No UniFi EOL/firmware recommendation was fabricated from the failed read.
    ids = {r.get("finding_id") for r in recs}
    assert "finding-uf-eol" not in ids
    assert "finding-uf-outdated-fw" not in ids


async def test_quick_audit_flags_an_unrestricted_admin_trusthost(_fg_build):
    # trusthost1 is a native "address mask" string; an unrestricted admin (the
    # FortiGate default) is "0.0.0.0 0.0.0.0", which the old != "0.0.0.0" test
    # read as restricted, so the finding never fired (accuracy sweep).
    from app.services.fortigate_api import quick_audit_fortigate

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p.endswith("system/status"):
            return httpx.Response(200, json={"results": {"hostname": "fw1", "version": "7.4"}})
        if p.endswith("system/admin"):
            return httpx.Response(200, json={"results": [
                {"name": "openadmin", "accprofile": "super_admin",
                 "trusthost1": "0.0.0.0 0.0.0.0", "two-factor": "disable"},
                {"name": "safeadmin", "accprofile": "super_admin",
                 "trusthost1": "192.168.1.0 255.255.255.0", "two-factor": "enable"},
            ]})
        return httpx.Response(200, json={"results": []})

    _fg_build(handler)
    result = await quick_audit_fortigate({}, "t")
    by_name = {a["name"]: a for a in result["admins"]}
    assert by_name["openadmin"]["trusthost"] is False, "unrestricted admin must read as no trust host"
    assert by_name["safeadmin"]["trusthost"] is True, "a real subnet must read as restricted"
