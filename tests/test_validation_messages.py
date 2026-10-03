"""A refusal raised below the web layer reaches the reader in their language.

The validators in app/core/validation.py guard values that end up in device
CLIs and config files. Their refusals were Norwegian literals, so an operator
with the English interface was told "host er påkrevd". Each now carries a key
and its parameters (app/core/messages.py), and the error handler fills in the
reader's translation. Services and auth raise through the same table.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from starlette.requests import Request

from app.core import messages, validation
from app.core.exceptions import ToolkitError, ValidationError
from app.web.i18n import _UI_STRINGS, ui_t
from app.web.server import create_app


def test_every_message_has_both_languages_with_the_same_placeholders():
    for key, (no, en) in messages.MESSAGES.items():
        assert set(re.findall(r"\{(\w+)\}", no)) == set(re.findall(r"\{(\w+)\}", en)), key
        assert _UI_STRINGS["no"][key] == no and _UI_STRINGS["en"][key] == en


def test_no_validator_raises_a_bare_literal():
    source = pathlib.Path(validation.__file__).read_text(encoding="utf-8")
    assert "ValidationError(f" not in source and 'ValidationError("' not in source


def test_the_exception_keeps_its_norwegian_message_for_logs():
    with pytest.raises(ValidationError) as caught:
        validation.validate_host("", "host")
    assert caught.value.message == "host er påkrevd"
    assert caught.value.message_key == "err_field_required"
    assert caught.value.params == {"field": "host"}


def test_a_missing_parameter_stays_visible_instead_of_crashing():
    assert ui_t("err_field_range", None, {"field": "port"}) == (
        "port må være mellom {minimum} og {maximum}"
    )


@pytest.mark.parametrize(
    ("accept", "expected"),
    [
        ("en", "Invalid port: must be a whole number"),
        ("nb-NO", "Ugyldig port: må være et heltall"),
    ],
)
async def test_the_handler_answers_in_the_readers_language(accept, expected):
    handler = create_app().exception_handlers[ToolkitError]
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/vpn/profiles",
            "query_string": b"",
            "headers": [(b"accept-language", accept.encode())],
        }
    )
    with pytest.raises(ValidationError) as caught:
        validation.validate_port("eighty")

    response = await handler(request, caught.value)

    assert response.status_code == 400
    body = json.loads(response.body)
    assert body["error"] == expected
    assert body["error_key"] == "err_field_not_integer"


def test_a_keyed_conflict_is_translated_too():
    from app.core.messages import conflict

    err = conflict("err_setup_already_done")
    assert err.status_code == 409 and err.message == "Oppsett er allerede fullført"
    assert ui_t(err.message_key, None, err.params) == "Oppsett er allerede fullført"
