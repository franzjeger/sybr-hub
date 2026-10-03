"""A refusal from the route layer reaches the reader in the reader's language.

The route modules raised their refusals as literals, Norwegian in most and
English in some, so an operator with the English interface was told "Ingen
funn å rapportere" and one with the Norwegian interface "No template named".
Each now goes through ``refusal(cls, key, **params)`` in app/web/i18n.py: the
exception keeps the Norwegian text as its message, for the log, and the error
handler answers with the reader's translation of the key.

Some routes answer with a 200 and an ``error`` or ``reason`` in the body
instead of raising. Those go through ``keyed(field, key, request, **params)``,
which gives the text in the reader's language and the key beside it as
``error_key`` or ``reason_key``.

The front-end shows ``t(error_key, error)``, so a key that ui_i18n.json also
defines is shown from there. That table cannot fill placeholders, which is why
a route key must either be absent from it or say exactly the same thing.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest
from starlette.requests import Request

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.exceptions import NotFoundError, ToolkitError, ValidationError
from app.core.rbac import set_can_write
from app.models.user import Role
from app.web.i18n import _ROUTE_REFUSALS, _UI_STRINGS, keyed, refusal
from app.web.server import create_app
from tests.test_web_auth_routes import GOOD_PASSWORD, _init_db, _reset_middleware_state, client

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROUTES = ROOT / "app" / "web" / "routes"
WEB_STRINGS = json.loads((ROOT / "app" / "web" / "static" / "ui_i18n.json").read_text("utf-8"))

# Words, in either language. A literal with none, such as the "{}: {}" around
# an already translated text and an exception, has nothing to translate.
_WORDS = re.compile(r"[^\W\d_]{2,}")

# A value that is a code for the SPA to look up, not a sentence for a person.
_MACHINE_CODE = re.compile(r"[a-z0-9_]+")

# A raise that cannot go through refusal(), with the reason. Empty: every site
# could be converted, and a new one should be converted rather than listed.
ALLOWLIST: dict[tuple[str, str], str] = {}

# The body fields a person reads when a route answers instead of raising.
_BODY_FIELDS = {"error", "reason", "warning"}

# A literal a route returns under one of those fields, with the reason it stays.
_STATIC_FILE = "answers a request for a file (a script, an image), which no person reads"
_GUACAMOLE_ASSET = "answers the Guacamole client fetching its own static assets"
RETURNED_ALLOWLIST: dict[tuple[str, str], str] = {
    ("frontend.py", "Not found"): _STATIC_FILE,
    ("frontend.py", "Forbidden"): _STATIC_FILE,
    ("guacamole.py", "Guacamole API is not exposed"): _GUACAMOLE_ASSET,
    ("guacamole.py", "Guacamole backend unreachable"): _GUACAMOLE_ASSET,
    ("guacamole.py", "Guacamole backend timeout"): _GUACAMOLE_ASSET,
    ("policy_deploy.py", "taken immediately before a policy deployment"): (
        "written into the restore point on disk as its provenance, not returned to anyone"
    ),
}


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def _route_modules():
    for path in sorted(ROUTES.glob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def _calls_to(name: str):
    for path, tree in _route_modules():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == name
            ):
                yield path.name, node


def _refusal_calls():
    return _calls_to("refusal")


def _keyed_calls():
    return _calls_to("keyed")


def _used_keys() -> set[str]:
    return {call.args[1].value for _, call in (*_refusal_calls(), *_keyed_calls())}


def _text(node: ast.AST, constants: dict[str, str]) -> str | None:
    """The literal text an expression spells, with its f-string holes as {}."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left, constants), _text(node.right, constants)
        if left is not None or right is not None:
            return (left or "") + (right or "")
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and len(node.args) == 2
    ):
        # result.get("error", "Failed to fetch hosts"): the default is the
        # message whenever the service gave none.
        return _text(node.args[1], constants)
    return None


def _module_constants(tree: ast.Module) -> dict[str, str]:
    found = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            found[node.targets[0].id] = node.value.value
    return found


def test_every_refusal_names_a_key_both_languages_define():
    calls = list(_refusal_calls())
    assert len(calls) > 200, "the walk found too few refusal() calls to be looking right"
    for name, call in calls:
        where = f"{name}:{call.lineno}"
        assert len(call.args) == 2, f"{where}: refusal(cls, key, **params)"
        key = call.args[1]
        assert isinstance(key, ast.Constant) and isinstance(key.value, str), (
            f"{where}: the key must be a literal so this test can check it"
        )
        key = key.value
        assert key in _UI_STRINGS["no"] and key in _UI_STRINGS["en"], f"{where}: {key}"
        no, en = _UI_STRINGS["no"][key], _UI_STRINGS["en"][key]
        assert _placeholders(no) == _placeholders(en), f"{where}: {key}"
        assert all(kw.arg for kw in call.keywords), f"{where}: no **params"
        passed = {kw.arg for kw in call.keywords}
        assert passed == _placeholders(no), (
            f"{where}: {key} fills {sorted(_placeholders(no))}, the call passes {sorted(passed)}"
        )


def test_every_returned_message_names_a_key_both_languages_define():
    calls = list(_keyed_calls())
    assert len(calls) > 20, "the walk found too few keyed() calls to be looking right"
    for name, call in calls:
        where = f"{name}:{call.lineno}"
        assert len(call.args) == 3, f"{where}: keyed(field, key, request, **params)"
        field, key = call.args[0], call.args[1]
        assert isinstance(field, ast.Constant) and field.value in _BODY_FIELDS, where
        assert isinstance(key, ast.Constant) and isinstance(key.value, str), (
            f"{where}: the key must be a literal so this test can check it"
        )
        key = key.value
        # ui_t falls back to ui_i18n.json, so a key only the front-end table
        # defines is answered from there, as err_device_test_auth already is.
        table = _UI_STRINGS if key in _UI_STRINGS["no"] else WEB_STRINGS
        assert key in table["no"] and key in table["en"], f"{where}: {key}"
        no, en = table["no"][key], table["en"][key]
        assert _placeholders(no) == _placeholders(en), f"{where}: {key}"
        assert all(kw.arg for kw in call.keywords), f"{where}: no **params"
        passed = {kw.arg for kw in call.keywords}
        assert passed == _placeholders(no), (
            f"{where}: {key} fills {sorted(_placeholders(no))}, the call passes {sorted(passed)}"
        )


def test_the_route_table_is_level_and_every_entry_is_used():
    used = _used_keys()
    for key, (no, en) in _ROUTE_REFUSALS.items():
        assert _placeholders(no) == _placeholders(en), key
        assert "\u2014" not in no and "\u2013" not in no, f"{key}: an em or en dash in Norwegian"
        # An older entry with the same key would win the merge silently.
        assert _UI_STRINGS["no"][key] == no and _UI_STRINGS["en"][key] == en, key
        assert key in used, f"{key} is in the table but no route raises or returns it"


def test_the_front_end_cannot_show_a_route_refusal_unfilled():
    for key in sorted(_used_keys()):
        for lang in ("no", "en"):
            if key not in WEB_STRINGS[lang]:
                continue
            server = _UI_STRINGS[lang].get(key, WEB_STRINGS[lang][key])
            assert WEB_STRINGS[lang][key] == server, (
                f"{key} ({lang}) says something else in ui_i18n.json, which the front-end prefers"
            )
            assert not _placeholders(WEB_STRINGS[lang][key]), (
                f"{key} ({lang}) has placeholders the front-end's t() cannot fill"
            )


def test_no_route_raises_a_literal_in_one_language():
    offenders = []
    for path, tree in _route_modules():
        constants = _module_constants(tree)
        # Every exception built with a literal, raised on the spot or not.
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            func = ast.unparse(call.func)
            if not (func.endswith("Error") or func.endswith("Exception")):
                continue
            keywords = {kw.arg: kw.value for kw in call.keywords}
            if "message_key" in keywords:
                continue  # the handler translates it already
            message = call.args[0] if call.args else keywords.get("detail", keywords.get("message"))
            text = _text(message, constants) if message is not None else None
            if text and _WORDS.search(text) and (path.name, text) not in ALLOWLIST:
                offenders.append(f"{path.name}:{call.lineno}: {func}({text!r})")
    assert not offenders, "raise these through refusal():\n" + "\n".join(offenders)


def _without_request(node: ast.AST) -> list[ast.Call]:
    """The ui_t() calls in an expression that were not given the request."""
    return [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "ui_t"
        and len(call.args) < 2
        and not any(kw.arg == "request" for kw in call.keywords)
    ]


def test_no_route_raises_a_text_ui_t_could_only_give_in_norwegian():
    """ui_t() without the request has no reader to ask, so it answers in Norwegian."""
    offenders = [
        f"{name}:{call.lineno}: {ast.unparse(call)}"
        for path, tree in _route_modules()
        for name in [path.name]
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and ast.unparse(call.func).endswith(("Error", "Exception"))
        and call.args
        and _without_request(call.args[0])
    ]
    assert not offenders, "raise these through refusal():\n" + "\n".join(offenders)


def test_the_guard_sees_the_shapes_it_is_meant_to():
    source = (
        "X = 'Profil ikke funnet'\n"
        "raise NotFoundError('Feil passord')\n"
        "raise ValidationError(f'{label}: mappen finnes ikke')\n"
        "raise ForbiddenError('Systemkontoen holder VPN-tunneler åpne: ' + held)\n"
        "raise NotFoundError(X)\n"
        "raise HTTPException(status_code=404, detail='Kunde ikke funnet')\n"
        "raise NotFoundError('No such run')\n"
        "raise ValidationError(f'{customer_id!r} has no tenant id')\n"
        "raise ValidationError(result.get('error', 'Failed to fetch hosts'))\n"
        # Already in the reader's language, around an exception's own text.
        "raise IntegrationError(f\"{ui_t('err_backup_failed', request)}: {e}\")\n"
        "raise ValidationError(str(exc))\n"
    )
    tree = ast.parse(source)
    constants = _module_constants(tree)
    seen = [
        _text(n.exc.args[0] if n.exc.args else n.exc.keywords[1].value, constants)
        for n in tree.body
        if isinstance(n, ast.Raise)
    ]
    assert [bool(t and _WORDS.search(t)) for t in seen] == [True] * 8 + [False] * 2


def _flagged(value: ast.AST, constants: dict[str, str]) -> str | None:
    """The text of a body value that is a sentence in one language, if it is one."""
    text = _text(value, constants)
    if text and _WORDS.search(text) and not _MACHINE_CODE.fullmatch(text):
        return text
    return None


def _returned_literals():
    """Every literal a route module puts under a body field a person reads."""
    for path, tree in _route_modules():
        constants = _module_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in _BODY_FIELDS:
                    text = _flagged(value, constants)
                    if text:
                        yield path.name, value.lineno, key.value, text


def test_no_route_returns_a_literal_in_one_language():
    offenders = [
        f"{name}:{line}: {{{field!r}: {text!r}}}"
        for name, line, field, text in _returned_literals()
        if (name, text) not in RETURNED_ALLOWLIST
    ]
    assert not offenders, "return these through keyed():\n" + "\n".join(offenders)


def test_every_returned_allowlist_entry_is_still_there():
    found = {(name, text) for name, _, _, text in _returned_literals()}
    stale = sorted(set(RETURNED_ALLOWLIST) - found)
    assert not stale, f"no longer in the code, drop them from the allowlist: {stale}"


def test_the_body_guard_sees_the_shapes_it_is_meant_to():
    source = (
        "a = {'ok': False, 'error': 'Tilkoblingstest feilet'}\n"
        "b = {'name': n, 'reason': f'Kunden har allerede tenant {t}…'}\n"
        "c = {'error': result.get('error', '2FA-kode påkrevd')}\n"
        "d = {'warning': f'Credentials saved but validation failed: {exc}'}\n"
        "e = {'reason': 'not_packaged'}\n"
        "f = {'error': str(e)}\n"
        "g = {'ok': False, **keyed('error', 'err_ssh_test_failed', request)}\n"
    )
    tree = ast.parse(source)
    constants = _module_constants(tree)
    flagged = [
        bool(_flagged(value, constants))
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(key, ast.Constant) and key.value in _BODY_FIELDS
    ]
    assert flagged == [True] * 4 + [False] * 2


@pytest.mark.parametrize(
    ("accept", "expected"),
    [
        ("en", {"reason": "The customer already has tenant 8f2c1a9e…"}),
        ("nb-NO", {"reason": "Kunden har allerede tenant 8f2c1a9e…"}),
    ],
)
def test_a_returned_reason_reads_in_the_readers_language(accept, expected):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/gdap/import",
            "query_string": b"",
            "headers": [(b"accept-language", accept.encode())],
        }
    )

    body = keyed("reason", "err_gdap_customer_has_tenant", request, tenant="8f2c1a9e")

    assert body == {**expected, "reason_key": "err_gdap_customer_has_tenant"}


async def _signed_in(role: Role = Role.technician) -> dict[str, str]:
    user = await create_user("reader", GOOD_PASSWORD, "Reader", role=role)
    await set_can_write(user.id, True)
    token = await create_access_token(await get_user_by_id(user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("accept", "expected"),
    [("en", "A sync is already running"), ("nb-NO", "Synkronisering kjører allerede")],
)
async def test_a_sync_already_running_is_said_in_the_readers_language(
    client, monkeypatch, accept, expected
):
    from app.web.routes import uniweb

    monkeypatch.setitem(uniweb._sync_status, "running", True)

    response = client.post(
        "/api/uniweb/sync", headers={**await _signed_in(), "Accept-Language": accept}
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "error": expected,
        "error_key": "err_uniweb_sync_running",
    }


@pytest.mark.parametrize(
    ("accept", "expected"),
    [("en", "Claude CLI not found"), ("nb-NO", "Claude CLI ikke funnet")],
)
async def test_a_missing_claude_cli_is_said_in_the_readers_language(
    client, monkeypatch, accept, expected
):
    import asyncio

    async def _not_installed(*args, **kwargs):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _not_installed)

    response = client.get(
        "/api/claude/cli-status", headers={**await _signed_in(), "Accept-Language": accept}
    )

    assert response.json() == {
        "available": False,
        "error": expected,
        "error_key": "inf_claude_missing",
    }


def test_the_exception_keeps_its_norwegian_message_for_logs():
    err = refusal(ValidationError, "err_auth_username_taken", username="kari")
    assert err.message == "Brukernavnet 'kari' finnes allerede"
    assert err.message_key == "err_auth_username_taken"
    assert err.params == {"username": "kari"}
    assert refusal(NotFoundError, "err_pentest_scan_not_found").params is None


@pytest.mark.parametrize(
    ("accept", "expected"),
    [
        ("en-GB,en;q=0.9", "No findings to report"),
        ("nb-NO,nb;q=0.9", "Ingen funn å rapportere"),
    ],
)
async def test_the_handler_answers_in_the_readers_language(accept, expected):
    handler = create_app().exception_handlers[ToolkitError]
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/pentest/report",
            "query_string": b"",
            "headers": [(b"accept-language", accept.encode())],
        }
    )

    response = await handler(request, refusal(ValidationError, "err_pentest_no_findings"))

    assert response.status_code == 400
    body = json.loads(response.body)
    assert body["error"] == expected
    assert body["error_key"] == "err_pentest_no_findings"


@pytest.mark.parametrize(
    ("accept", "expected"),
    [
        ("en", "Wrong username or password"),
        ("nb-NO", "Feil brukernavn eller passord"),
    ],
)
async def test_a_refused_sign_in_reads_in_the_readers_language(client, accept, expected):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)

    response = client.post(
        "/api/auth/login",
        json={"username": "tech", "password": "Wrong1234!x"},
        headers={"Accept-Language": accept},
    )

    assert response.status_code == 401
    assert response.json()["error"] == expected
    assert response.json()["error_key"] == "err_auth_bad_credentials"


def test_no_access_is_a_403_not_a_401():
    """The SPA reads a 401 as an expired session and signs the user out."""
    import pathlib

    routes = pathlib.Path(__file__).resolve().parent.parent / "app/web/routes"
    offenders = [
        f"{path.name}:{n}"
        for path in sorted(routes.glob("*.py"))
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "AuthError" in line and ("no_access" in line or "access_denied" in line)
    ]
    assert not offenders, offenders
