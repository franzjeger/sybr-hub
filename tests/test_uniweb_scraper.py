"""Uniweb scrapes a portal that owes it no API contract.

Every selector is a guess that was true once, so the interesting question is
not whether a parse fails but what it says when it does. It used to say
`return []` — which turned "the markup changed" into "this customer has no
domains", a claim about the customer drawn from a page that never parsed.
"""

from __future__ import annotations

import json

import pytest

from app.services.uniweb_client import UniwebClient, UniwebScrapeError


def _client(js_result) -> UniwebClient:
    """A client whose browser is replaced by a canned JS result."""
    c = UniwebClient.__new__(UniwebClient)
    c._logged_in = True
    c._nav = lambda *a, **k: None
    c._js = lambda _expr: js_result
    return c


def test_a_missing_account_table_is_an_error_not_an_empty_list():
    """The distinction the whole change is about."""
    c = _client(json.dumps({"found": False, "accounts": []}))
    with pytest.raises(UniwebScrapeError, match="markup change"):
        c.list_accounts()


def test_a_table_with_no_rows_really_is_no_accounts():
    """The counterpart: an empty portal must stay readable as empty."""
    c = _client(json.dumps({"found": True, "accounts": []}))
    assert c.list_accounts() == []


def test_a_blank_response_is_an_error():
    """No value back from the page is not an answer about the portal."""
    c = _client(None)
    with pytest.raises(UniwebScrapeError):
        c.list_accounts()


def test_not_logged_in_raises_rather_than_reporting_no_accounts():
    c = UniwebClient.__new__(UniwebClient)
    c._logged_in = False
    with pytest.raises(UniwebScrapeError, match="Not logged in"):
        c.list_accounts()


def test_partner_rows_are_counted_so_a_renumbered_id_is_visible():
    """The failure that cannot be detected from the page alone.

    Partner accounts are recognised by a JSF component id, and JSF renumbers
    those when a component is added earlier in the page. If it changes, no
    account looks like a partner, the sub-customers under them are never
    visited, and the list comes back shorter with no error at all. The count
    is carried out so the run can be questioned.
    """
    rows = [
        {"id": "1", "name": "Direct", "index": 0, "is_partner": False, "button_id": "x"},
        {"id": "2", "name": "Partner", "index": 1, "is_partner": True, "button_id": "j_idt87:2"},
    ]
    c = _client(json.dumps({"found": True, "accounts": rows}))
    c._get_partner_sub_customers = lambda partner: [
        {"id": "2a", "name": "Sub", "parent_id": partner["id"]}
    ]

    out = c.list_accounts()
    assert c.last_partner_rows == 1
    assert [a["name"] for a in out] == ["Direct", "Sub"]


def test_zero_partner_rows_is_recorded_even_though_it_may_be_legitimate():
    """A tenant may hold no partners, so this cannot fail — only be visible."""
    rows = [{"id": "1", "name": "Direct", "index": 0, "is_partner": False, "button_id": "x"}]
    c = _client(json.dumps({"found": True, "accounts": rows}))

    assert c.list_accounts() == rows
    assert c.last_partner_rows == 0


def test_no_reader_still_answers_an_empty_list_on_failure():
    """Guarding the guard: the pattern must not creep back in."""
    import pathlib
    import re

    src = pathlib.Path("app/services/uniweb_client.py").read_text()
    offenders = []
    for match in re.finditer(r"except [^\n]*\n((?:\s+[^\n]*\n){0,4}?)\s+return \[\]", src):
        offenders.append(match.group(0).strip().splitlines()[0])
    assert not offenders, f"a failure path still returns an empty list: {offenders}"
