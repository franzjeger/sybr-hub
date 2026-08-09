"""Credentials stored is not the same claim as credentials that work.

/api/gdap/setup saves what it was given, then asks Partner Center whether the
credentials are real. When that failed it still wrote the config and returned
``ok: True`` with a warning — honest in the response, but the response is read
once, and the integration card is repainted from the stored config on every
page load. The config recorded only that a setup had been attempted.

So a client secret Partner Center had just rejected showed a green dot reading
"Konfigurert", counted towards "n of m integrations configured", and revealed
the discovery button. Reload and the orange warning was gone; the green
remained. For the one integration whose failure mode is a broken delegation to
every customer tenant, that is the wrong direction to round.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "app/web/static/app.js").read_text(encoding="utf-8")
GDAP_PY = (ROOT / "app/web/routes/gdap.py").read_text(encoding="utf-8")
SETTINGS_PY = (ROOT / "app/web/routes/settings.py").read_text(encoding="utf-8")


# ── The outcome is written, not only returned ────────────────────────────────

def _setup_bodies() -> tuple[str, str]:
    """The failure block and the success block of gdap_setup, split apart."""
    start = GDAP_PY.index("async def gdap_setup")
    end = GDAP_PY.index("# ── Validate Graph access", start)
    body = GDAP_PY[start:end]
    marker = 'return {\n            "ok": True,\n            "validated": False,'
    assert marker in body, "the failure branch moved; this test needs updating"
    cut = body.index(marker)
    return body[:cut], body[cut:]


def test_a_rejected_setup_records_that_it_was_rejected():
    failure, _ = _setup_bodies()
    assert '"validated": False' in failure, (
        "the failure path saves the config without recording that Partner "
        "Center refused it, so nothing downstream can tell the two apart"
    )


def test_it_keeps_the_reason():
    failure, _ = _setup_bodies()
    assert '"validation_error": str(exc)' in failure


def test_a_successful_setup_records_that_too():
    _, success = _setup_bodies()
    assert '"validated": True' in success
    assert '"validated_at": now_iso' in success


def test_the_three_timestamps_come_from_one_clock_read():
    _, success = _setup_bodies()
    assert success.count("datetime.now(timezone.utc)") <= 1, (
        "separate now() calls can straddle a second boundary and file one "
        "event as three"
    )


# ── The settings endpoint distinguishes three answers ────────────────────────

def test_validation_is_reported_separately_from_configuration():
    assert '"gdap_validated": gdap_cfg.get("validated")' in SETTINGS_PY, (
        "reported as bool(), null and False collapse — and a config written "
        "before this field existed would be painted as broken"
    )
    assert '"gdap_configured": gdap_configured()' in SETTINGS_PY, (
        "the precondition the API routes check must keep its own meaning"
    )


def test_gdap_configured_still_means_credentials_present():
    import inspect

    from app.core.credentials import gdap_configured
    assert "validated" not in inspect.getsource(gdap_configured), (
        "gdap_configured() gates the API routes; folding the validation "
        "result into it would block calls whose whole purpose is to re-test "
        "credentials that failed"
    )


# ── The card ─────────────────────────────────────────────────────────────────

def test_the_card_has_a_third_state():
    assert "function setStatusWarn(" in APP_JS


def test_a_rejected_config_does_not_paint_green():
    assert "d.gdap_validated === false" in APP_JS, (
        "the card is repainted from the stored config on every load; without "
        "reading the validation result it can only show configured or not"
    )


def test_an_unrecorded_result_is_not_treated_as_a_failure():
    # `=== false`, not `!d.gdap_validated`: a config written before the field
    # existed says nothing, and claiming it is broken is the same overclaim in
    # the other direction.
    assert "!d.gdap_validated" not in APP_JS


def test_a_rejected_config_does_not_count_as_an_active_integration():
    assert "if (d.gdap_configured && d.gdap_validated !== false) _integActive++" in APP_JS


def test_saving_repaints_from_what_just_happened():
    # The immediate response carries `validated`; the save handler used to set
    # green unconditionally, three lines below the branch that had just told
    # the operator validation failed.
    handler = APP_JS[APP_JS.index("/api/gdap/setup"):]
    handler = handler[:handler.index("async function gdapTestConnection")]
    assert "setStatusWarn(" in handler
    assert "'gdap-integ-dot').style.background = 'var(--green)'" not in handler


# ── The label exists in both languages ───────────────────────────────────────

@pytest.mark.parametrize("lang", ["no", "en"])
def test_the_status_label_is_translated(lang):
    data = json.loads((ROOT / "app/web/static/ui_i18n.json").read_text(encoding="utf-8"))
    assert data[lang]["gdap_status_unverified"].strip()


def test_every_t_key_in_the_new_code_is_defined():
    data = json.loads((ROOT / "app/web/static/ui_i18n.json").read_text(encoding="utf-8"))
    for key in re.findall(r"t\('(gdap_status_[a-z_]+)'", APP_JS):
        assert key in data["no"] and key in data["en"], f"{key} is not translated"
