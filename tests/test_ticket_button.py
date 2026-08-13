"""The button, and the two things about it that are easy to get wrong.

A control built at runtime out of ``innerHTML`` has no markup for
``tests/test_write_controls_are_marked.py`` to find, so the ``data-write``
half of the read-only defence does not apply here — ``apiFetch`` is what
refuses for an account without the grant. What *does* need asserting is that
the button knows when a ticket already exists, because a second click on a
finding that already has one is the whole failure this feature had to avoid.

Static assertions against the script, because the alternative is a browser.
They check the wiring, not the rendering: that the ticket state is fetched,
that the row reads it, and that the duplicate case is surfaced rather than
swallowed.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

STATIC = pathlib.Path("app/web/static")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")


def _function(name: str) -> str:
    """Source of one top-level function, up to the next one."""
    start = re.search(rf"^(?:async\s+)?function\s+{re.escape(name)}\b", APP_JS, re.M)
    assert start, f"{name} not found in app.js"
    nxt = re.search(r"^(?:async\s+)?function\s+\w+", APP_JS[start.end():], re.M)
    return APP_JS[start.start():start.end() + (nxt.start() if nxt else len(APP_JS))]


# ── The state the button depends on ──────────────────────────────────────────

def test_the_ticket_state_is_fetched_once_not_per_row():
    """One request for the customer, not one per finding.

    The remediation list renders every recommendation at once; asking per row
    is how a list view becomes twenty round-trips.
    """
    src = _function("loadRemediation")
    assert src.count("/tickets") == 1
    assert "_findingTickets" in src


def test_the_customer_id_comes_from_the_server_not_a_second_copy():
    """`/api/remediation` already resolved the active customer. A client-side
    copy of that would drift in exactly one direction: wrong customer."""
    src = _function("loadRemediation")
    assert "remData.customer_id" in src


def test_a_failed_ticket_lookup_does_not_take_the_list_with_it():
    """The findings still matter when the ticket cache is unavailable."""
    src = _function("loadRemediation")
    ticket_block = src[src.index("/tickets"):]
    assert "catch" in ticket_block, "ticket lookup is not guarded"


# ── The control ──────────────────────────────────────────────────────────────

def test_a_finding_with_a_ticket_shows_the_ticket_not_the_button():
    src = _function("_ticketControl")
    assert "_findingTickets[recId]" in src
    # The early return is what stops a second button being offered at all.
    assert re.search(r"if\s*\(tk\)", src), "no branch for an existing ticket"


def test_the_ticket_link_opens_safely():
    """target=_blank without noopener hands the opener to the linked page."""
    src = _function("_ticketControl")
    assert 'target="_blank"' in src
    assert "noopener" in src


def test_a_missing_url_still_shows_the_ticket_number():
    """ticket_url is best-effort. Losing the id because the link could not be
    built would be worse than a missing link."""
    src = _function("_ticketControl")
    assert "external_id" in src
    assert "tk.external_url" in src and "?" in src, "no fallback for a missing url"


def test_no_button_without_a_customer():
    src = _function("_ticketControl")
    assert "if (!_ticketCustomerId) return ''" in src


# ── Submitting ───────────────────────────────────────────────────────────────

def test_the_submit_button_is_disabled_while_the_request_is_in_flight():
    """The server's idempotency is the safety net, not the first line."""
    src = _function("createTicketFromFinding")
    assert "btn.disabled = true" in src


def test_a_failed_submit_re_enables_the_button():
    """Otherwise one network blip costs the operator the control entirely."""
    src = _function("createTicketFromFinding")
    assert src.count("btn.disabled = false") >= 2


def test_the_duplicate_case_is_surfaced():
    """A real ticket exists in Autotask that nothing owns. Silence leaves it
    for a customer to find."""
    src = _function("createTicketFromFinding")
    assert "duplicate_ticket_id" in src
    assert "msg_ticket_duplicate" in src


def test_created_and_already_existed_say_different_things():
    src = _function("createTicketFromFinding")
    assert "msg_ticket_created" in src
    assert "msg_ticket_exists" in src


def test_the_row_updates_without_a_reload():
    """The control has to become the ticket link, or the operator clicks again."""
    src = _function("createTicketFromFinding")
    assert "_findingTickets[recId] = d.ticket" in src
    assert "_ticketControl(" in src


def test_the_request_body_matches_what_the_endpoint_accepts():
    """`extra="forbid"` on the model means a stray field is a 422, not a
    tolerated typo — so the field names have to agree."""
    from app.models.settings import CreateTicketRequest

    src = _function("createTicketFromFinding")
    sent = set(re.findall(r"^\s*(\w+):", src[src.index("JSON.stringify({"):], re.M))
    allowed = set(CreateTicketRequest.model_fields)
    assert sent <= allowed, f"sends fields the model forbids: {sorted(sent - allowed)}"
    assert "rec_id" in sent


# ── The settings form the button depends on ──────────────────────────────────
# The write side was unreachable from the interface: the Autotask card said
# "Kommer snart" behind a disabled button, so nowhere in the product could a
# person enter the credentials the endpoint needs.

INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("field", [
    "input-autotask-code", "input-autotask-user", "input-autotask-secret",
    "input-autotask-queue", "input-autotask-priority", "input-autotask-status",
])
def test_the_settings_form_has_every_field_the_endpoint_reads(field):
    assert f'id="{field}"' in INDEX


def test_the_autotask_card_is_no_longer_disabled():
    card = INDEX[INDEX.index("<!-- Autotask card -->"):INDEX.index("<!-- Halo PSA card -->")]
    assert "status_coming_soon" not in card
    assert "disabled" not in card


def test_the_masked_secret_is_not_written_back():
    """A settings form that saves the bullets destroys the credential."""
    src = _function("_saveAutotaskSettings")
    assert "'••••••'" in src or '"••••••"' in src
    assert "if (code &&" in src and "if (secret &&" in src


def test_the_test_button_saves_before_testing():
    """Zone discovery runs server-side from stored settings. Testing without
    saving tests the previous credentials and reports them working."""
    src = _function("testAutotask")
    save_at = src.index("_saveAutotaskSettings")
    test_at = src.index("/api/autotask/test")
    assert save_at < test_at


def test_the_config_panel_toggles_on_a_computed_style():
    """The panel is hidden by a class, so `el.style.display` is empty for it.
    Reading the inline value made the first click close everything and open
    nothing."""
    src = _function("toggleIntegConfig")
    assert "getComputedStyle" in src
    assert "autotask-config" in src, "the new panel is not in the close-all list"


def test_the_delegated_handler_is_registered():
    """`data-click-handler` resolves through a frozen allowlist, so a handler
    that is not in it silently does nothing."""
    assert "testAutotask: function()" in APP_JS


# ── Translations ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", [
    "btn_create_ticket", "lbl_ticket_exists", "hdr_new_ticket",
    "lbl_ticket_title", "lbl_ticket_queue", "lbl_ticket_priority",
    "lbl_ticket_notes", "tip_ticket_notes", "btn_ticket_submit",
    "msg_ticket_created", "msg_ticket_exists", "msg_ticket_duplicate",
    "prio_critical", "prio_high", "prio_medium", "prio_low",
])
def test_every_new_key_exists_in_both_languages(key):
    d = json.loads((STATIC / "ui_i18n.json").read_text(encoding="utf-8"))
    assert key in d["no"], f"{key} missing from Norwegian"
    assert key in d["en"], f"{key} missing from English"


def test_the_placeholders_survive_translation():
    """A message whose {id} was dropped in one language renders as a sentence
    with a hole in it."""
    d = json.loads((STATIC / "ui_i18n.json").read_text(encoding="utf-8"))
    for key, holes in (
        ("msg_ticket_created", ["{id}"]),
        ("msg_ticket_exists", ["{id}"]),
        ("msg_ticket_duplicate", ["{id}", "{dup}"]),
    ):
        for lang in ("no", "en"):
            for hole in holes:
                assert hole in d[lang][key], f"{lang}.{key} lost {hole}"
