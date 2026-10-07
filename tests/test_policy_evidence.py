"""Names, report-only policies and partial scopes cannot establish alignment."""

import copy

from app.core.policy_evidence import captured_checks


def rule(control="mfa", clients=None):
    return {
        "id": "p",
        "displayName": "Unrelated name",
        "state": "enabledForReportingButNotEnforced",
        "conditions": {
            "users": {"includeUsers": ["All"]},
            "applications": {"includeApplications": ["All"]},
            "clientAppTypes": clients or ["all"],
        },
        "grantControls": {"operator": "OR", "builtInControls": [control]},
    }


def test_capture_is_setting_evidence_not_an_alignment_verdict():
    check = captured_checks([rule()])["ca-mfa"]
    assert check["state"] == "settings_found"
    assert check["matches"][0]["state"] == "enabledForReportingButNotEnforced"
    assert captured_checks(None)["ca-mfa"]["state"] == "unmeasured"
    assert captured_checks([])["ca-mfa"]["state"] == "no_match"


def test_weaker_or_control_and_conditional_scopes_are_not_baseline_candidates():
    p = rule()
    p["grantControls"]["builtInControls"].append("compliantDevice")
    assert captured_checks([p])["ca-mfa"]["state"] == "no_match"
    for key, value in (
        ("locations", {"includeLocations": ["trusted"]}),
        ("signInRiskLevels", ["high"]),
        ("devices", {"deviceFilter": {"mode": "include", "rule": "x"}}),
    ):
        p = copy.deepcopy(rule())
        p["conditions"][key] = value
        assert captured_checks([p])["ca-mfa"]["state"] == "no_match"
    p = rule("block", ["exchangeActiveSync", "other"])
    assert captured_checks([p])["ca-legacy"]["state"] == "settings_found"
    p["conditions"]["users"]["includeUsers"] = ["pilot"]
    assert captured_checks([p])["ca-legacy"]["state"] == "no_match"
