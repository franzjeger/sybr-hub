"""A test run must not reach a third party.

`validate_password` looks a password up against Have I Been Pwned, and almost
every test that touches an account calls it. `tests/conftest.py` disables that
for the whole session; this is what fails if the fixture is removed or renamed,
rather than the suite quietly resuming outbound requests.
"""

from __future__ import annotations

import os

import httpx
import pytest

from app.core.auth import ENV_DISABLE_HIBP, validate_password


def test_the_session_fixture_is_active():
    assert os.environ.get(ENV_DISABLE_HIBP) == "1", (
        "the breached-password lookup is enabled inside the test suite — "
        "conftest._no_breached_password_lookup is missing or not autouse"
    )


async def test_a_password_check_opens_no_connection(monkeypatch):
    """Prove it by making any outbound HTTP call an error."""

    def explode(*_args, **_kwargs):
        raise AssertionError("a test made an outbound HTTP request")

    monkeypatch.setattr(httpx.AsyncClient, "get", explode)
    assert await validate_password("Fjord-Kompani-2026!") is None


async def test_the_local_rules_still_decide_without_the_lookup(monkeypatch):
    """Disabling the lookup must not turn validate_password into a no-op."""

    def explode(*_args, **_kwargs):
        raise AssertionError("a test made an outbound HTTP request")

    monkeypatch.setattr(httpx.AsyncClient, "get", explode)
    for weak in ("kort1!", "abcdefghij!", "abcdefgh12", "password1!"):
        assert await validate_password(weak) is not None, weak


@pytest.mark.parametrize("value", ["0", ""])
async def test_the_lookup_is_only_skipped_for_an_explicit_1(monkeypatch, value):
    """An opt-out that triggers on any value would disable it by accident."""
    monkeypatch.setenv(ENV_DISABLE_HIBP, value)

    seen: list[str] = []

    async def record(self, url, *_args, **_kwargs):
        seen.append(str(url))
        raise httpx.ConnectError("blocked in tests")

    monkeypatch.setattr(httpx.AsyncClient, "get", record)
    await validate_password("Fjord-Kompani-2026!")
    assert seen, f"{ENV_DISABLE_HIBP}={value!r} skipped the lookup"
