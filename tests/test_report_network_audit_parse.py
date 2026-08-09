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
