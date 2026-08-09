"""A network audit file that will not parse is not an absent network audit.

Both used to produce ``has_data: False``, and the report reads that to decide
whether ``_compute_network_risk`` runs at all. So a malformed
``60_fortigate_audit.txt`` dropped every firewall finding *and* its risk
penalty, and the customer scored better for it — an unreadable file made a
tenant look safer than it was.
"""

from __future__ import annotations

import json

from app.reports.generator import _parse_network_audit


def test_valid_json_is_read():
    result = _parse_network_audit({
        "60_fortigate_audit.txt": json.dumps({"admins": [{"two_factor": True}]}),
    })
    assert result["has_data"] is True
    assert result["unreadable"] == []
    assert result["fortigate"]["admins"][0]["two_factor"] is True


def test_a_malformed_file_is_reported_not_swallowed():
    result = _parse_network_audit({"60_fortigate_audit.txt": "{not json at all"})
    assert result["unreadable"] == ["60_fortigate_audit.txt"]
    assert result["fortigate"] is None


def test_an_absent_file_is_not_an_error():
    # Nothing to read is the ordinary case for a customer without network gear,
    # and must stay distinguishable from a file that could not be parsed.
    result = _parse_network_audit({})
    assert result["has_data"] is False
    assert result["unreadable"] == []


def test_an_empty_file_is_absent_rather_than_unreadable():
    result = _parse_network_audit({"61_unifi_audit.txt": "   \n"})
    assert result["unreadable"] == []


def test_one_readable_file_does_not_hide_the_other_being_broken():
    # The dangerous middle case: has_data is True, so the section renders and
    # looks complete, while half the findings are missing.
    result = _parse_network_audit({
        "60_fortigate_audit.txt": json.dumps({"admins": []}),
        "61_unifi_audit.txt": "}broken{",
    })
    assert result["has_data"] is True
    assert result["unreadable"] == ["61_unifi_audit.txt"]


def test_both_broken_reports_both():
    result = _parse_network_audit({
        "60_fortigate_audit.txt": "nope",
        "61_unifi_audit.txt": "also nope",
    })
    assert result["has_data"] is False
    assert result["unreadable"] == ["60_fortigate_audit.txt", "61_unifi_audit.txt"]


# ── The gap is declared where every other unverifiable input is ──────────────

def _score(network):
    from app.reports.generator import _compute_risk
    return _compute_risk(
        secure_score={"has_data": True, "pct": 80},
        mfa={"has_data": True, "pct": 100, "no_mfa": 0},
        spf_dmarc=[], all_warns="", ext_fwd="", risky_users="No risky",
        defender="No active", admin_roles={}, intune={"has_data": True},
        sharepoint={}, oauth={}, network=network, lang="no",
    )


def test_an_unreadable_network_file_is_declared_beside_the_score():
    # data_quality_issues is where every other input this function could not
    # read is announced. A recommendation further down the report is not the
    # same thing: the score is what gets quoted to the customer.
    result = _score({"has_data": False, "unreadable": ["60_fortigate_audit.txt"]})
    joined = " ".join(result.get("data_quality_issues", []))
    assert "60_fortigate_audit.txt" in joined


def test_it_does_not_invalidate_the_whole_grade():
    # Network is worth 15 points against MFA's 35. Refusing to grade a tenant
    # over one corrupt file is heavier than the gap warrants.
    result = _score({"has_data": False, "unreadable": ["61_unifi_audit.txt"]})
    assert result.get("score") is not None
    assert not result.get("blocking_data_gaps")


def test_a_customer_with_no_network_audit_raises_nothing():
    result = _score({"has_data": False, "unreadable": []})
    joined = " ".join(result.get("data_quality_issues", []))
    assert "Nettverksaudit" not in joined
