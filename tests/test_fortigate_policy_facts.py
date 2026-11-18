"""FortiGate checks that reported something the firewall did not say.

* A disabled policy passes no traffic, but an any/any/ALL accept rule that had
  been switched off still failed CIS-3.1 and was listed as an allow-all warning
  in the quick audit (which costs points in the customer report).
* The password policy's length was read from "min-length". FortiOS sends
  "minimum-length", so the length was always 0 and an enabled policy failed.
* The configuration API returns no hit counter. "No counter" was read as "0
  hits", so every enabled rule was reported as unused.
"""

from __future__ import annotations

import httpx
import pytest

from app.services import fortigate_api
from tests.test_device_reads_are_not_clean import _fg


def _policy(pid: int, *, status: str = "enable", log: str = "all", **extra) -> dict:
    return {
        "policyid": pid,
        "name": f"rule-{pid}",
        "status": status,
        "action": "accept",
        "srcaddr": [{"name": "all"}],
        "dstaddr": [{"name": "all"}],
        "service": [{"name": "ALL"}],
        "logtraffic": log,
        **extra,
    }


def _narrow(pid: int, **extra) -> dict:
    return _policy(pid, **extra) | {"srcaddr": [{"name": "LAN"}], "service": [{"name": "HTTPS"}]}


@pytest.fixture()
def firewall(monkeypatch):
    """A FortiGate answering with the given policies and password policy."""

    def _install(
        policies: list[dict],
        password_policy: dict | None = None,
        *,
        logging: dict[str, dict] | None = None,
        status: dict | None = None,
        performance: dict | None = None,
    ):
        log_targets = {f"/api/v2/cmdb/{k}/setting": v for k, v in (logging or {}).items()}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("monitor/system/status") and status is not None:
                return httpx.Response(200, json=status)
            if path.endswith("system/performance/status") and performance is not None:
                return httpx.Response(200, json={"results": performance})
            if path.endswith("firewall/policy"):
                return httpx.Response(200, json={"results": policies})
            if path.endswith("password-policy"):
                return httpx.Response(200, json={"results": password_policy or {}})
            if path.endswith("/setting"):
                return httpx.Response(200, json={"results": log_targets.get(path, {})})
            if path.endswith(("system/global", "system/ha")):
                return httpx.Response(200, json={"results": {}})
            return httpx.Response(200, json={"results": []})

        monkeypatch.setattr(fortigate_api, "_build_client", lambda config, token: _fg(handler))

    return _install


def _finding(result: dict, cis_id: str) -> list[dict]:
    return [f for f in result["findings"] if f["id"] == cis_id]


async def test_a_disabled_allow_all_policy_does_not_fail_the_firewall(firewall):
    firewall([_policy(1, status="disable", log="disable"), _narrow(2)])

    compliance = await fortigate_api.check_compliance({}, "t")
    quick = await fortigate_api.quick_audit_fortigate({}, "t")

    assert [f["status"] for f in _finding(compliance, "CIS-3.1")] == ["pass"]
    assert quick["policy_warnings"] == []


async def test_an_enabled_allow_all_policy_still_does(firewall):
    firewall([_policy(1, log="disable"), _narrow(2)])

    compliance = await fortigate_api.check_compliance({}, "t")
    quick = await fortigate_api.quick_audit_fortigate({}, "t")

    assert [f["status"] for f in _finding(compliance, "CIS-3.1")] == ["fail"]
    assert len(quick["policy_warnings"]) == 2, "allow-all, and logging disabled"


@pytest.mark.parametrize(
    ("password_policy", "status"),
    [
        ({"status": "enable", "minimum-length": 12}, "pass"),  # what FortiOS sends
        ({"status": "enable", "min-length": 12}, "pass"),  # the old spelling still reads
        ({"status": "enable", "minimum-length": 6}, "fail"),
        ({"status": "enable"}, "unknown"),  # enabled, length not in the answer
        ({"status": "disable", "minimum-length": 12}, "fail"),
    ],
)
async def test_the_password_policy_length_is_read_under_fortios_own_name(
    firewall, password_policy, status
):
    firewall([], password_policy)

    compliance = await fortigate_api.check_compliance({}, "t")

    assert [f["status"] for f in _finding(compliance, "CIS-5.1")] == [status]


async def test_rules_without_a_hit_counter_are_not_reported_as_unused(firewall):
    firewall([_narrow(1), _narrow(2), _narrow(3, status="disable")])

    audit = await fortigate_api.audit_firewall_rules({}, "t")

    assert audit["enabled"] == 2
    assert audit["unused_rules"] is None, "no counter in the answer: not measured"


async def test_rules_with_a_hit_counter_are_counted(firewall):
    firewall([_narrow(1, hitcount=0), _narrow(2, hitcount=41), _narrow(3, hitcount=0)])

    audit = await fortigate_api.audit_firewall_rules({}, "t")

    assert audit["unused_rules"] == 2


# ── One definition of allow-all ──────────────────────────────────────────────


async def test_the_rule_audit_uses_the_same_allow_all_definition(firewall):
    """Any source and destination on HTTPS only is not an any-any rule."""
    firewall([_policy(1), _policy(2) | {"service": [{"name": "HTTPS"}]}])

    audit = await fortigate_api.audit_firewall_rules({}, "t")
    compliance = await fortigate_api.check_compliance({}, "t")

    assert [i["policy_id"] for i in audit["issues"] if i["issue"] == "any_any"] == [1]
    assert len([f for f in _finding(compliance, "CIS-3.1") if f["status"] == "fail"]) == 1


# ── Logging is judged by the log targets ─────────────────────────────────────


@pytest.mark.parametrize(
    ("logging", "status"),
    [
        ({"log.disk": {"status": "enable"}}, "pass"),
        # No disk, as on most desktop models: logging to FortiAnalyzer counts.
        (
            {"log.disk": {"status": "disable"}, "log.fortianalyzer": {"status": "enable"}},
            "pass",
        ),
        ({"log.disk": {"status": "disable"}}, "warn"),
    ],
)
async def test_logging_passes_when_any_log_target_is_enabled(firewall, logging, status):
    firewall([], logging=logging)

    compliance = await fortigate_api.check_compliance({}, "t")

    assert [f["status"] for f in _finding(compliance, "CIS-2.1")] == [status]


# ── Facts FortiOS puts beside "results" ──────────────────────────────────────

STATUS = {
    "http_method": "GET",
    "results": {"model_name": "FortiGate", "model": "FGT60F", "hostname": "fw-oslo"},
    "vdom": "root",
    "status": "success",
    "serial": "FGT60FTK00000001",
    "version": "v7.4.5",
    "build": 2702,
}


async def test_firmware_and_serial_are_read_from_the_response_envelope(firewall):
    firewall(
        [],
        status=STATUS,
        performance={"cpu": {"user": 3, "system": 2}, "mem": {"total": 200, "used": 50}},
    )

    dashboard = await fortigate_api.get_dashboard({}, "t")

    assert dashboard["hostname"] == "fw-oslo"
    assert dashboard["firmware"] == "v7.4.5"
    assert dashboard["serial"] == "FGT60FTK00000001"
    # And the load is a percentage, read as the fleet view reads it.
    assert dashboard["cpu_percent"] == 5
    assert dashboard["memory_percent"] == 25.0
