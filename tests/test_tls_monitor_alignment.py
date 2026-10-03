"""scan_customer_endpoints must keep each result paired with its endpoint.

Host-less entries are skipped, so the results list is shorter than the input
endpoints list. The labels used to be read with endpoints[idx] against the
original (longer) list, so a single blank host shifted every later result onto
the wrong endpoint: a successful scan wore another host's label, and a
gather-exception reported the wrong host/port. These pin the alignment.
"""

from __future__ import annotations

import pytest

from app.services import tls_monitor


@pytest.fixture(autouse=True)
def _patch_check(monkeypatch):
    async def _fake(host, port=443, timeout=5.0):
        if host == "boom.example":
            raise RuntimeError("handshake failed")
        # Echo the host/port so a mislabelled result is visible.
        return {"host": host, "port": port, "valid": True}

    monkeypatch.setattr(tls_monitor, "check_endpoint_tls", _fake)


def _by_label(results: list[dict]) -> dict[str, dict]:
    return {r.get("label", ""): r for r in results}


async def test_a_blank_host_in_the_middle_does_not_shift_labels():
    endpoints = [
        {"host": "a.example", "port": 443, "label": "A"},
        {"host": "", "label": "BLANK"},  # skipped — used to shift the rest
        {"host": "b.example", "port": 8443, "label": "B"},
    ]
    out = await tls_monitor.scan_customer_endpoints(endpoints)

    results = out["results"]
    assert len(results) == 2  # the blank one is not scanned
    by_label = _by_label(results)
    # Each result carries its own host/port, not the next endpoint's.
    assert by_label["A"]["host"] == "a.example" and by_label["A"]["port"] == 443
    assert by_label["B"]["host"] == "b.example" and by_label["B"]["port"] == 8443


async def test_a_gather_exception_reports_the_right_host_after_a_skip():
    endpoints = [
        {"host": "", "label": "BLANK"},  # skipped first
        {"host": "boom.example", "port": 9443, "label": "BOOM"},
        {"host": "ok.example", "port": 443, "label": "OK"},
    ]
    out = await tls_monitor.scan_customer_endpoints(endpoints)

    by_label = _by_label(out["results"])
    # The failure is attributed to boom.example:9443, not to the OK endpoint.
    assert by_label["BOOM"]["host"] == "boom.example"
    assert by_label["BOOM"]["port"] == 9443
    assert by_label["BOOM"]["error"] and not by_label["BOOM"]["valid"]
    assert by_label["OK"]["valid"] and by_label["OK"]["host"] == "ok.example"


async def test_all_hosts_present_still_aligns():
    endpoints = [
        {"host": "one.example", "label": "1"},
        {"host": "two.example", "label": "2"},
    ]
    out = await tls_monitor.scan_customer_endpoints(endpoints)
    by_label = _by_label(out["results"])
    assert by_label["1"]["host"] == "one.example"
    assert by_label["2"]["host"] == "two.example"
