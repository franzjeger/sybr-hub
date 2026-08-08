"""Which customers can be reached past the cloud key, and what each one lacks.

The Site Manager key answers for the whole account but stops at counts — it has
no clients endpoint, and the Network API behind a console is not reachable
through it. Per-site clients, firewall zones and ACLs all need a controller
login stored against the customer.

That storage has existed all along. What did not was any way to see where it is
missing: has_credentials was reported for the active customer only, so "which
of my customers can I not audit" could only be answered by clicking through
them one at a time.
"""

from __future__ import annotations

from app.services.unifi_api import (
    classify_controller_access,
    summarise_controller_coverage,
)


def test_a_host_and_a_login_is_full_access():
    state, reason = classify_controller_access({"UniFiHost": "unifi.example.no"}, True)
    assert state == "full"
    assert reason == ""


def test_a_host_without_a_login_is_the_one_fixable_gap():
    state, reason = classify_controller_access({"UniFiHost": "unifi.example.no"}, False)
    assert state == "host_only"
    assert "brukernavn" in reason


def test_a_customer_with_no_unifi_is_not_a_gap():
    # An answer, not a fault. Listing it as missing credentials would pad the
    # backlog with customers who have nothing to connect to.
    state, _ = classify_controller_access({}, False)
    assert state == "none"


def test_direct_device_mode_is_its_own_state():
    # Direct access reads the devices themselves; there is no controller to
    # hold clients or firewall policy, so a credential would not change it.
    state, reason = classify_controller_access(
        {"UniFiMode": "direct", "UniFiDirectDevices": [{"ip": "198.51.100.5"}]}, False
    )
    assert state == "direct"
    assert "controller" in reason


def test_direct_mode_without_devices_falls_back_to_the_host_question():
    state, _ = classify_controller_access({"UniFiMode": "direct", "UniFiHost": "h"}, False)
    assert state == "host_only"


def test_only_a_stored_login_counts_as_actionable():
    rows = [
        {"customer_id": "a", "name": "A", "state": "full", "reason": ""},
        {"customer_id": "b", "name": "B", "state": "host_only", "reason": "..."},
        {"customer_id": "c", "name": "C", "state": "none", "reason": "..."},
        {"customer_id": "d", "name": "D", "state": "direct", "reason": "..."},
        {"customer_id": "e", "name": "E", "state": "host_only", "reason": "..."},
    ]
    summary = summarise_controller_coverage(rows)
    assert summary["total"] == 5
    assert summary["with_full_access"] == 1
    # Only host_only. "none" and "direct" are answers, and counting them as
    # work to do would make the number useless as a to-do list.
    assert summary["needs_credentials"] == 2
    assert summary["counts"]["host_only"] == 2


def test_an_empty_portfolio_summarises_without_raising():
    summary = summarise_controller_coverage([])
    assert summary["total"] == 0
    assert summary["needs_credentials"] == 0
    assert summary["with_full_access"] == 0


def test_whitespace_is_not_a_host():
    state, _ = classify_controller_access({"UniFiHost": "   "}, True)
    assert state == "none"
