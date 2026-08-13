"""A secret must not survive into a log line or an API response.

The bug these were written against: ``factory_bootstrap`` masked the FortiGate
API key it had just parsed, then — in the branch where parsing *failed* —
returned the same terminal output verbatim as ``raw_output``. Masking was
attached to the branch somebody thought about rather than to the value leaving
the function, so the failure path, which is the likeliest place for an
unrecognised key to still be sitting in the text, was the one that leaked.

So the tests below drive the failure branch on purpose.
"""

from __future__ import annotations

import pytest

from app.core.redact import MASK, redact, redact_mapping

_KEY = "9xQhZ3mNbVcXwErTyUiOpAsDfGhJkL2z"
_PASSWORD = "Tr0ub4dor&3xKcd1234"


# ── The helper ───────────────────────────────────────────────────────────────

def test_a_named_secret_is_replaced_everywhere_it_appears():
    text = f"key={_KEY} again={_KEY}"
    out = redact(text, _KEY)
    assert _KEY not in out
    assert out.count(MASK) == 2


def test_a_secret_shaped_run_is_replaced_even_when_nobody_named_it():
    """The property the FortiGate fix depends on."""
    out = redact(f"New API key: {_KEY}")
    assert _KEY not in out


def test_ordinary_prose_survives():
    text = "Kunne ikke parse API-nøkkel fra output, prøv igjen."
    assert redact(text) == text


def test_a_dotted_hostname_survives():
    """`.` breaks the run, so host names are not collateral damage."""
    text = "connecting to fortigate-01.customer.example.no on port 22"
    assert redact(text) == text


def test_a_file_path_survives():
    """Redaction that eats tracebacks is redaction somebody turns off.

    `/` is kept out of the pattern for exactly this: with it in,
    `/home/user/sybr-hub/app/web/` is a single 28-character run.
    """
    text = 'File "/home/user/sybr-hub/app/web/routes/settings.py", line 325'
    assert redact(text) == text


def test_a_jwt_is_still_masked():
    """Urlsafe base64 has no `/`, so dropping it costs nothing that matters."""
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ."
        "dQw4w9WgXcQrTyUiOpAsDfGhJkLzXcVbNm"
    )
    out = redact(f"token={jwt}")
    for segment in jwt.split("."):
        assert segment not in out


def test_none_and_empty_known_values_are_tolerated():
    assert redact("hello", None, "") == "hello"


def test_a_short_known_value_is_not_masked_character_by_character():
    """An empty or near-empty factory password must not shred the text.

    `"".replace()` inserts between every character, which would turn a
    diagnostic string into unreadable mush and hide the actual problem.
    """
    assert redact("admin login failed", "") == "admin login failed"
    assert redact("admin login failed", "a") == "admin login failed"


def test_redact_mapping_leaves_non_strings_alone():
    out = redact_mapping({"ok": False, "steps": ["a"], "error": _KEY}, _KEY)
    assert out["ok"] is False
    assert out["steps"] == ["a"]
    assert _KEY not in out["error"]


# ── The branch that leaked ───────────────────────────────────────────────────

class _FakeProcess:
    """An interactive FortiOS shell that answers the command it was given.

    Keyed on the command rather than on a positional script: an earlier
    version counted reads, and the hardening steps ate the entry holding the
    key, so the assertion below passed against output that never contained a
    key at all. Answering `execute api-user generate-key` specifically means
    the test cannot drift out of alignment when a step is added.
    """

    def __init__(self, reply_to: str, reply: str):
        self._reply_to = reply_to
        self._reply = reply
        self.written: list[str] = []
        self._pending: str | None = None
        self.stdout = self
        self.stdin = self

    def write(self, data: str) -> None:
        self.written.append(data)
        if self._reply_to in data:
            self._pending = self._reply

    async def read(self, _n: int = 8192) -> str:
        if self._pending is not None:
            out, self._pending = self._pending, None
            return out
        return "# "


class _FakeConnection:
    def __init__(self, process: _FakeProcess):
        self._process = process
        self.closed = False

    async def create_process(self, **_kw):
        return self._process

    def close(self):
        self.closed = True


# A key the parser cannot read: hyphens break every run of alphanumerics below
# the 20 the last-resort regex needs, which is what an unexpected FortiOS build
# looks like — and the branch the old code returned verbatim.
_UNPARSEABLE_KEY = "9xQhZ3mN-bVcXwErT-yUiOpAsD-fGhJkL2z-QqWwEeRrTtYy"


async def _bootstrap_with(reply: str, monkeypatch):
    from app.services import fortigate_api as fg

    process = _FakeProcess("execute api-user generate-key", reply)
    monkeypatch.setattr(
        "app.services.ssh_connection.open_verified_connection",
        lambda **_kw: _async(_FakeConnection(process)),
    )
    result = await fg.factory_bootstrap(
        host="10.0.0.1", new_password=_PASSWORD, hostname="fg-test"
    )
    return result


async def test_the_failure_branch_does_not_return_the_key(monkeypatch):
    """Run the real bootstrap to the point where key parsing fails."""
    result = await _bootstrap_with(f"New-API-Key-Is: {_UNPARSEABLE_KEY}\n# ", monkeypatch)

    # Prove the fixture landed where it was aimed before asserting on it.
    assert "api_token_FAILED" in result["steps"]
    assert result["api_token"] is None
    raw = result["raw_output"]
    assert "New-API-Key-Is" in raw, "the generate-key output must have been read"

    assert _UNPARSEABLE_KEY not in raw
    assert MASK in raw
    assert _PASSWORD not in raw


async def test_the_success_branch_still_returns_the_key_to_the_caller(monkeypatch):
    """Redaction must not take the token away from the thing that needs it.

    The caller stores this to talk to the firewall. A fix that scrubbed it out
    of the return value too would be silently useless.
    """
    result = await _bootstrap_with(f"New API key: {_KEY}\n# ", monkeypatch)

    assert result["ok"] is True
    assert result["api_token"] == _KEY
    assert result["admin_password"] == _PASSWORD


def _async(value):
    async def _coro():
        return value

    return _coro()


def test_the_new_admin_password_never_reaches_an_error_string():
    """asyncssh puts the failing command in the exception, and commands carry it."""
    exc_text = f'set password "{_PASSWORD}" failed: command not found'
    assert _PASSWORD not in redact(exc_text, _PASSWORD)


def test_raw_output_is_built_from_the_redacted_text():
    """Guards the ordering: redact first, slice second.

    Slicing first and redacting the slice leaves the tail of a key in the
    untouched remainder the moment somebody widens the window.
    """
    import inspect

    from app.services.fortigate_api import factory_bootstrap

    src = inspect.getsource(factory_bootstrap)
    assert "safe_output = redact(" in src
    assert 'result["raw_output"] = safe_output' in src
    assert 'result["raw_output"] = output' not in src
