"""Uniweb scrapes a portal that owes it no API contract.

Every selector is a guess that was true once, so the interesting question is
not whether a parse fails but what it says when it does. It used to say
`return []` — which turned "the markup changed" into "this customer has no
domains", a claim about the customer drawn from a page that never parsed.
"""

from __future__ import annotations

import json

import pytest

from app.services.uniweb_client import (
    UniwebClient,
    UniwebScrapeError,
    _classify_login_outcome,
)


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


# ── Login outcome: a blind "feilet" is replaced by a reason ──────────────────


def test_login_success_when_the_form_is_gone_and_off_the_login_page():
    ok, reason = _classify_login_outcome(
        {"url": "https://uniweb.no/controlpanel/principal/?showExpanded=true",
         "form_present": False, "error": ""}
    )
    assert ok is True and reason == ""


def test_login_success_is_robust_to_an_unusual_landing_url():
    # Left the login page and the password field is gone → logged in, whatever
    # the panel's landing URL happens to be.
    ok, _ = _classify_login_outcome({"url": "https://uniweb.no/cp/dashboard", "form_present": False})
    assert ok is True


def test_login_reports_the_page_error_verbatim():
    ok, reason = _classify_login_outcome(
        {"url": "https://uniweb.no/controlpanel/login/", "form_present": True,
         "error": "Feil brukernavn eller passord"}
    )
    assert ok is False and "Feil brukernavn eller passord" in reason


def test_login_reblank_submit_is_named_not_left_as_feilet():
    # Still on the login page, form present, no visible error — the blank-submit
    # / wrong-credentials signature, which used to be an opaque "feilet".
    ok, reason = _classify_login_outcome(
        {"url": "https://uniweb.no/controlpanel/login/", "form_present": True, "error": ""}
    )
    assert ok is False and "på nytt" in reason


def test_login_names_a_chromium_start_failure_instead_of_a_bare_feilet(monkeypatch):
    """The one path that could still fail with no stated reason: the headless
    browser never started (Chromium missing or unable to launch in the
    deployment). It now sets last_login_error, so the card shows the real cause
    instead of a bare "feilet" that reads like bad credentials."""
    client = UniwebClient()

    def _boom():
        raise RuntimeError("chromium binary not found")

    monkeypatch.setattr(client, "_start_chromium", _boom)
    assert client.login("user@example.com", "pw") is False
    assert client.last_login_error and "Chromium" in client.last_login_error


# ── Locating the Chromium binary: /snap/bin/chromium is not the only place ───


def test_find_chromium_prefers_the_env_override(monkeypatch, tmp_path):
    from app.services.uniweb_client import _find_chromium

    fake = tmp_path / "my-chromium"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("SYBR_CHROMIUM_PATH", str(fake))
    assert _find_chromium() == str(fake)


def test_find_chromium_probes_fixed_locations_when_nothing_is_on_path(monkeypatch):
    from app.services import uniweb_client as uc

    monkeypatch.delenv("SYBR_CHROMIUM_PATH", raising=False)
    monkeypatch.delenv("CHROMIUM_PATH", raising=False)
    monkeypatch.setattr(uc.shutil, "which", lambda _name: None)          # nothing on PATH
    monkeypatch.setattr(uc.os.path, "isfile", lambda p: p == "/usr/bin/chromium")
    monkeypatch.setattr(uc.os, "access", lambda p, _mode: p == "/usr/bin/chromium")
    assert uc._find_chromium() == "/usr/bin/chromium"


def test_find_chromium_raises_naming_what_it_tried(monkeypatch):
    """The deployment bug: none found. The error must be actionable, not Errno 2."""
    from app.services import uniweb_client as uc

    for var in ("SYBR_CHROMIUM_PATH", "CHROMIUM_PATH", "PLAYWRIGHT_BROWSERS_PATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(uc.shutil, "which", lambda _name: None)
    monkeypatch.setattr(uc.os.path, "isfile", lambda _p: False)

    with pytest.raises(RuntimeError) as ei:
        uc._find_chromium()
    msg = str(ei.value)
    assert "ble ikke funnet" in msg          # names the problem
    assert "SYBR_CHROMIUM_PATH" in msg        # names the override
    assert "/snap/bin/chromium" in msg        # names what it probed
