"""An undelivered token request is retryable; a delivered one is single use."""

import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from app.modules.m365_audit import pkce

REDIRECT = "https://login.microsoftonline.com/common/oauth2/nativeclient"


@pytest.fixture(autouse=True)
def _states():
    pkce._pkce_store.clear()
    yield
    pkce._pkce_store.clear()


def _transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        pkce.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ConnectTimeout])
async def test_connection_failure_keeps_verifier_for_one_explicit_retry(monkeypatch, failure):
    sent = []

    def handler(request):
        sent.append(parse_qs(request.content.decode()))
        if len(sent) == 1:
            raise failure("synthetic DNS/connection failure", request=request)
        return httpx.Response(200, json={"access_token": "synthetic-token"})

    _transport(monkeypatch, handler)
    state, verifier, _ = pkce.generate_pkce_challenge("owner")
    with pytest.raises(pkce.PkceSetupError) as err:
        await pkce.exchange_code_for_token("code", state, REDIRECT, owner_user_id="owner")
    assert err.value.message_key == "err_setup_pkce_connect"
    assert err.value.restart_required is False
    assert state in pkce._pkce_store
    token = await pkce.exchange_code_for_token("code", state, REDIRECT, owner_user_id="owner")
    assert token == "synthetic-token"
    assert [r["code_verifier"] for r in sent] == [[verifier], [verifier]]
    with pytest.raises(pkce.PkceSetupError) as used:
        await pkce.exchange_code_for_token("code", state, REDIRECT, owner_user_id="owner")
    assert used.value.restart_required
    assert len(sent) == 2


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ReadError, httpx.WriteError])
async def test_uncertain_delivery_requires_new_sign_in(monkeypatch, failure):
    def handler(request):
        raise failure("synthetic uncertain delivery", request=request)

    _transport(monkeypatch, handler)
    state, _, _ = pkce.generate_pkce_challenge()
    with pytest.raises(pkce.PkceSetupError) as err:
        await pkce.exchange_code_for_token("code", state, REDIRECT)
    assert err.value.message_key == "err_setup_pkce_delivery"
    assert err.value.restart_required
    assert state not in pkce._pkce_store


async def test_duplicate_submission_never_exchanges_twice(monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def handler(request):
        calls.append(request)
        started.set()
        await release.wait()
        return httpx.Response(200, json={"access_token": "synthetic-token"})

    _transport(monkeypatch, handler)
    state, _, _ = pkce.generate_pkce_challenge()
    task = asyncio.create_task(pkce.exchange_code_for_token("code", state, REDIRECT))
    await started.wait()
    try:
        with pytest.raises(pkce.PkceSetupError) as err:
            await pkce.exchange_code_for_token("code", state, REDIRECT)
        assert err.value.status_code == 409
    finally:
        release.set()
    assert await task == "synthetic-token"
    assert len(calls) == 1


async def test_cancelled_exchange_is_not_replayed(monkeypatch):
    started = asyncio.Event()

    async def handler(_):
        started.set()
        await asyncio.Event().wait()

    _transport(monkeypatch, handler)
    state, _, _ = pkce.generate_pkce_challenge()
    task = asyncio.create_task(pkce.exchange_code_for_token("code", state, REDIRECT))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert state not in pkce._pkce_store


async def test_other_user_cannot_exchange_or_consume_an_attempt(monkeypatch):
    _transport(monkeypatch, lambda _: httpx.Response(200, json={"access_token": "token"}))
    state, _, _ = pkce.generate_pkce_challenge("owner")
    with pytest.raises(pkce.PkceSetupError):
        await pkce.exchange_code_for_token("code", state, REDIRECT, owner_user_id="other")
    assert state in pkce._pkce_store
    assert await pkce.exchange_code_for_token("code", state, REDIRECT, owner_user_id="owner")


async def test_expired_state_is_removed_without_sending_a_request(monkeypatch):
    state, _, _ = pkce.generate_pkce_challenge()
    pkce._pkce_store[state].expires_at = 0
    _transport(monkeypatch, lambda _: pytest.fail("Expired codes must never be sent"))
    with pytest.raises(pkce.PkceSetupError) as err:
        await pkce.exchange_code_for_token("code", state, REDIRECT)
    assert err.value.status_code == 400
    assert state not in pkce._pkce_store


async def test_microsoft_rejection_shows_only_safe_diagnostic_codes(monkeypatch):
    _transport(
        monkeypatch,
        lambda _: httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_codes": [54005, "secret-description"],
                "error_description": "synthetic-secret-and-code-do-not-display",
            },
        ),
    )
    state, _, _ = pkce.generate_pkce_challenge()
    with pytest.raises(pkce.PkceSetupError) as err:
        await pkce.exchange_code_for_token("code", state, REDIRECT)
    assert "AADSTS54005" in str(err.value)
    assert "secret" not in str(err.value)
    assert err.value.restart_required
    assert state not in pkce._pkce_store


@pytest.mark.parametrize("body", [{}, {"access_token": None}, []])
async def test_invalid_success_body_is_terminal(monkeypatch, body):
    _transport(monkeypatch, lambda _: httpx.Response(200, json=body))
    state, _, _ = pkce.generate_pkce_challenge()
    with pytest.raises(pkce.PkceSetupError) as err:
        await pkce.exchange_code_for_token("code", state, REDIRECT)
    assert err.value.status_code == 502
    assert err.value.restart_required
    assert state not in pkce._pkce_store
