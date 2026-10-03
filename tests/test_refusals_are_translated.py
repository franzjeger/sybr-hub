"""The refusals every account meets must answer in the reader's language.

Routes raise Norwegian string literals in ~500 places and only a handful carry
a ``message_key``; translating all of them is ongoing work. These four are the
ones an English-speaking operator hits on an ordinary day — signing in over
plain HTTP, being told the account is read-only, being told to enrol in MFA —
and the middleware layer is where they are produced, so they can be translated
without changing the ``detail`` contract the route handlers have.
"""

from __future__ import annotations

import pytest

from app.web.i18n import _UI_STRINGS, ui_t

REFUSAL_KEYS = [
    "err_write_denied",
    "err_insecure_transport",
    "err_mfa_verification_required",
    "err_mfa_enrolment_required",
]


class _Request:
    """Enough of a Request for get_ui_lang: query params and headers."""

    def __init__(self, lang: str):
        self.query_params = {"lang": lang} if lang else {}
        self.headers = {}


@pytest.mark.parametrize("key", REFUSAL_KEYS)
def test_the_key_exists_in_both_languages(key):
    for lang in ("no", "en"):
        assert key in _UI_STRINGS[lang], f"{key} missing from the {lang} table"


@pytest.mark.parametrize("key", REFUSAL_KEYS)
def test_the_two_languages_say_different_things(key):
    """A key present in both tables with one text is an untranslated string."""
    assert _UI_STRINGS["no"][key] != _UI_STRINGS["en"][key]


@pytest.mark.parametrize("key", REFUSAL_KEYS)
def test_ui_t_resolves_rather_than_echoing_the_key(key):
    """ui_t returns the key itself when it cannot resolve — the failure mode."""
    for lang in ("no", "en"):
        assert ui_t(key, _Request(lang)) != key


def test_the_middleware_refusals_carry_their_key():
    """The constants the middleware sends, so a rename cannot go unnoticed."""
    from app.web.middleware.auth import _INSECURE_TRANSPORT_KEY
    from app.web.middleware.write_guard import _DENIED_KEY

    assert _INSECURE_TRANSPORT_KEY in REFUSAL_KEYS
    assert _DENIED_KEY in REFUSAL_KEYS


def test_no_norwegian_literal_is_left_in_those_middleware_responses():
    """The literals these keys replaced must not creep back in beside them."""
    from pathlib import Path

    sources = [
        Path("app/web/middleware/auth.py"),
        Path("app/web/middleware/write_guard.py"),
    ]
    gone = [
        "Denne handlingen endrer noe og krever skrivetilgang",
        "Denne tilkoblingen er ukryptert",
        "MFA verification required; log in again",
    ]
    for path in sources:
        body = path.read_text(encoding="utf-8")
        for literal in gone:
            assert literal not in body, f"{literal!r} is back in {path}"
