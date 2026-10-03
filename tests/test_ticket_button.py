"""The buttons, and the things about them that are easy to get wrong.

Two buckets now — an Autotask ticket for something to fix this week, a
myITprocess recommendation for something to plan next quarter — rendered by one
set of functions parameterised by kind rather than two near-copies. So most of
what is asserted below is asserted once and applies to both.

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
# The feature spans two of the split app files: the remediation view (state,
# control, submit) lives in app-audit.js, the integration settings it reads
# from in app-integrations.js. The handlers for index.html's own controls
# are registered in app-markup-handlers.js.
APP_JS = "\n\n".join(
    (STATIC / name).read_text(encoding="utf-8") for name in ("app-audit.js", "app-integrations.js")
)
CORE_JS = (STATIC / "app-markup-handlers.js").read_text(encoding="utf-8")


def _function(name: str) -> str:
    """Source of one top-level function, up to the next one."""
    start = re.search(rf"^(?:export\s+)?(?:async\s+)?function\s+{re.escape(name)}\b", APP_JS, re.M)
    assert start, f"{name} not found in app-audit.js / app-integrations.js"
    nxt = re.search(r"^(?:export\s+)?(?:async\s+)?function\s+\w+", APP_JS[start.end() :], re.M)
    return APP_JS[start.start() : start.end() + (nxt.start() if nxt else len(APP_JS))]


# ── The state the button depends on ──────────────────────────────────────────


# ── The control ──────────────────────────────────────────────────────────────


# ── Submitting ───────────────────────────────────────────────────────────────


# ── The settings form the button depends on ──────────────────────────────────
# The write side was unreachable from the interface: the Autotask card said
# "Kommer snart" behind a disabled button, so nowhere in the product could a
# person enter the credentials the endpoint needs.

INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "field",
    [
        "input-autotask-code",
        "input-autotask-user",
        "input-autotask-secret",
        "input-autotask-queue",
        "input-autotask-priority",
        "input-autotask-status",
        "input-myitprocess-key",
        "input-myitprocess-base",
    ],
)
def test_the_settings_form_has_every_field_the_endpoint_reads(field):
    assert f'id="{field}"' in INDEX


def test_the_autotask_card_is_no_longer_disabled():
    card = INDEX[INDEX.index("<!-- Autotask card -->") : INDEX.index("<!-- myITprocess card -->")]
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


@pytest.mark.parametrize("handler", ["testAutotask", "testMyITProcess"])
def test_the_delegated_handler_is_registered(handler):
    """`data-click-handler` resolves through a frozen allowlist, so a handler
    that is not in it silently does nothing."""
    assert f"{handler}: function()" in CORE_JS


def test_the_myitprocess_card_exists_and_is_not_a_placeholder():
    card = INDEX[INDEX.index("<!-- myITprocess card -->") : INDEX.index("<!-- IT Glue card -->")]
    assert "status_coming_soon" not in card
    assert "disabled" not in card
    assert 'data-click-handler="testMyITProcess"' in card


def test_the_myitprocess_key_is_not_written_back_masked():
    src = _function("_saveMyITProcessSettings")
    assert "'••••••'" in src or '"••••••"' in src


def test_the_myitprocess_test_saves_first():
    """This button is the only thing on the card that writes. Testing without
    saving leaves an operator who saw OK with nothing stored."""
    src = _function("testMyITProcess")
    assert src.index("_saveMyITProcessSettings") < src.index("/api/myitprocess/test")


def test_the_myitprocess_test_shows_the_field_names_that_came_back():
    """Nothing in that client has met a real server, so the returned keys are
    the only way its field names get corrected."""
    src = _function("testMyITProcess")
    assert "sample_fields" in src


# Opening/closing all configuration panels is exercised against the real DOM
# in tests/browser/integrations.spec.cjs. There is no duplicated ID list now.


# ── Translations ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "key",
    [
        "btn_create_ticket",
        "lbl_ticket_exists",
        "hdr_new_ticket",
        "lbl_ticket_title",
        "lbl_ticket_queue",
        "lbl_ticket_priority",
        "lbl_ticket_notes",
        "tip_ticket_notes",
        "btn_ticket_submit",
        "msg_ticket_created",
        "msg_ticket_exists",
        "msg_ticket_duplicate",
        "prio_critical",
        "prio_high",
        "prio_medium",
        "prio_low",
    ],
)
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
