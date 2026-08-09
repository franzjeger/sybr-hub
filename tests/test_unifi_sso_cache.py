"""The SSO cache must not answer for credentials it never checked.

site_manager_authenticate exists to say whether a set of UniFi credentials
works. It cached the result for an hour against the *username alone*, so once
one login succeeded, every password under that name came back "ok" without a
round-trip to ui.com — and on that cache hit the token was stored against
whichever customer was being configured. An operator who mistyped a password
got a green tick and a customer record pointing at someone else's session.
"""

from __future__ import annotations

import httpx
import pytest

from app.services import unifi_api


@pytest.fixture(autouse=True)
def clean_cache():
    unifi_api._token_cache.clear()
    yield
    unifi_api._token_cache.clear()


@pytest.fixture
def sso(monkeypatch):
    """Count round-trips to ui.com and let the test decide each verdict."""
    calls: list[dict] = []
    verdicts: dict[tuple[str, str], bool] = {}

    class _Response:
        def __init__(self, ok: bool):
            self.status_code = 200 if ok else 403
            self.content = b"{}"
            self.cookies = {"TOKEN": "tok-" + ("good" if ok else "bad")}
            self.headers = {}

        def json(self):
            return {}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            calls.append(json)
            ok = verdicts.get((json["user"], json["password"]), False)
            return _Response(ok)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    monkeypatch.setattr(unifi_api, "store_secret", lambda *a, **k: None)
    return calls, verdicts


async def test_a_correct_login_succeeds(sso):
    calls, verdicts = sso
    verdicts[("ops@sybr.no", "right")] = True
    result = await unifi_api.site_manager_authenticate("ops@sybr.no", "right")
    assert result["ok"] is True
    assert len(calls) == 1


async def test_the_same_credentials_are_served_from_cache(sso):
    calls, verdicts = sso
    verdicts[("ops@sybr.no", "right")] = True
    await unifi_api.site_manager_authenticate("ops@sybr.no", "right")
    result = await unifi_api.site_manager_authenticate("ops@sybr.no", "right")
    assert result["ok"] is True
    assert len(calls) == 1, "the cache stopped working"


async def test_a_wrong_password_is_still_asked_about(sso):
    calls, verdicts = sso
    verdicts[("ops@sybr.no", "right")] = True
    await unifi_api.site_manager_authenticate("ops@sybr.no", "right")

    result = await unifi_api.site_manager_authenticate("ops@sybr.no", "WRONG")
    assert result["ok"] is False, (
        "a password that was never checked was accepted because the username "
        "matched a cached login"
    )
    assert len(calls) == 2, "the wrong password never reached ui.com"


async def test_a_wrong_password_is_not_stored_against_a_customer(sso):
    _calls, verdicts = sso
    verdicts[("ops@sybr.no", "right")] = True
    stored: list[tuple] = []
    import app.services.unifi_api as mod
    mod.store_secret = lambda cid, name, val: stored.append((cid, name, val))
    try:
        await unifi_api.site_manager_authenticate("ops@sybr.no", "right")
        await unifi_api.site_manager_authenticate(
            "ops@sybr.no", "WRONG", store_for_customer="cust-b"
        )
    finally:
        mod.store_secret = lambda *a, **k: None
    assert not [s for s in stored if s[0] == "cust-b"], (
        "the good account's token was written to a customer configured with a "
        "password nobody verified"
    )


async def test_two_accounts_do_not_evict_each_other(sso):
    calls, verdicts = sso
    verdicts[("a@sybr.no", "pw-a")] = True
    verdicts[("b@sybr.no", "pw-b")] = True
    await unifi_api.site_manager_authenticate("a@sybr.no", "pw-a")
    await unifi_api.site_manager_authenticate("b@sybr.no", "pw-b")
    await unifi_api.site_manager_authenticate("a@sybr.no", "pw-a")
    assert len(calls) == 2, "one flat slot again — the second login evicted the first"


async def test_the_cache_does_not_grow_without_bound(sso):
    _calls, verdicts = sso
    for i in range(unifi_api._TOKEN_CACHE_MAX + 10):
        verdicts[(f"u{i}@sybr.no", "pw")] = True
        await unifi_api.site_manager_authenticate(f"u{i}@sybr.no", "pw")
    assert len(unifi_api._token_cache) <= unifi_api._TOKEN_CACHE_MAX


async def test_an_expired_entry_is_re_checked(sso, monkeypatch):
    calls, verdicts = sso
    verdicts[("ops@sybr.no", "right")] = True
    await unifi_api.site_manager_authenticate("ops@sybr.no", "right")
    for entry in unifi_api._token_cache.values():
        entry["expires"] = 0
    await unifi_api.site_manager_authenticate("ops@sybr.no", "right")
    assert len(calls) == 2


def test_the_password_is_not_held_in_module_state(sso):
    unifi_api._token_cache[unifi_api._sso_cache_key("ops@sybr.no", "hunter2")] = {
        "token": "t", "expires": 1e18, "result": {"ok": True, "token": "t"},
    }
    assert "hunter2" not in repr(unifi_api._token_cache)
