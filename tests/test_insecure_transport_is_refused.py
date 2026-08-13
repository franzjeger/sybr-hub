"""A password must not travel on a connection that cannot carry one.

The README has said so since the first release. Nothing enforced it. The
function that looked like the enforcement — ``_cookie_secure`` — decides
whether to mark a cookie ``Secure``, and ``/api/auth/login`` also returns both
tokens in the response body, so a client that never touches a cookie
authenticated over cleartext HTTP from anywhere on the network.

These tests pin the enforcement and, just as importantly, the exemptions. The
shipped deployment terminates TLS at ``tailscale serve`` and forwards to
loopback, so a request arriving from 127.0.0.1 with a public Host header must
keep working — a security control that breaks the one supported deployment
gets turned off, and then protects nothing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.models.user import Role, User
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app
from app.web.transport import ENV_ALLOW_INSECURE

_LAN = ("192.168.200.31", 51000)
_LOOPBACK = ("127.0.0.1", 51000)


@pytest.fixture(autouse=True)
def _reset_middleware_state():
    import app.web.middleware.rate_limit as rl

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


@pytest.fixture()
async def user() -> User:
    return await create_user(
        username="tech",
        password="Test1234!xyz",
        display_name="Tech User",
        role=Role.technician,
    )


def _client(*, client=_LAN, base_url="http://hub.example.no") -> TestClient:
    return TestClient(create_app(), base_url=base_url, client=client)


_CREDS = {"username": "tech", "password": "Test1234!xyz"}


# ── Refused ──────────────────────────────────────────────────────────────────

async def test_login_over_plain_http_from_the_lan_is_refused(user):
    with _client() as c:
        r = c.post("/api/auth/login", json=_CREDS)
    assert r.status_code == 403


async def test_the_refusal_does_not_hand_back_a_token(user):
    """The point of the control. A 403 that still returns tokens is theatre."""
    with _client() as c:
        r = c.post("/api/auth/login", json=_CREDS)
    body = r.text
    assert "access_token" not in body
    assert "refresh_token" not in body


async def test_the_refusal_says_what_to_do_about_it(user):
    with _client() as c:
        r = c.post("/api/auth/login", json=_CREDS)
    assert "HTTPS" in r.json()["error"]


async def test_a_bearer_token_is_refused_over_plain_http_from_the_lan(user):
    """Not just the password — the token is a credential on every request."""
    token = await create_access_token(user)
    with _client() as c:
        r = c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


async def test_a_cookie_session_is_refused_over_plain_http_from_the_lan(user):
    token = await create_access_token(user)
    with _client() as c:
        c.cookies.set("access_token", token)
        r = c.get("/api/auth/me")
    assert r.status_code == 403


async def test_first_run_setup_is_refused_over_plain_http_from_the_lan():
    """No account exists yet, so this one both sends *and* mints a credential."""
    with _client() as c:
        r = c.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "Test1234!xyz",
                  "display_name": "Admin", "email": "a@b.no"},
        )
    assert r.status_code == 403


# ── Allowed ──────────────────────────────────────────────────────────────────

async def test_loopback_http_still_works(user):
    """The documented quick-start. Bytes never reach a network interface."""
    with _client(client=_LOOPBACK, base_url="http://localhost:8099") as c:
        r = c.post("/api/auth/login", json=_CREDS)
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_tls_terminated_at_loopback_still_works(user):
    """`tailscale serve` — loopback client, public Host header. The shipped setup."""
    with _client(client=_LOOPBACK, base_url="http://hub.example.ts.net") as c:
        r = c.post("/api/auth/login", json=_CREDS)
    assert r.status_code == 200


async def test_a_forwarded_https_proto_is_accepted_from_the_lan(user):
    with _client() as c:
        r = c.post(
            "/api/auth/login", json=_CREDS,
            headers={"X-Forwarded-Proto": "https"},
        )
    assert r.status_code == 200


async def test_https_is_accepted_from_the_lan(user):
    with _client(base_url="https://hub.example.no") as c:
        r = c.post("/api/auth/login", json=_CREDS)
    assert r.status_code == 200


@pytest.mark.parametrize("proto", ["http", "", "httpsx", "HTTP"])
async def test_a_forwarded_proto_that_is_not_https_is_still_refused(user, proto):
    """Presence of the header is not the signal — its value is.

    Found by mutation: rewriting the check to ``bool(forwarded)`` passed every
    other test here, and would have accepted a proxy that correctly reported
    it had *not* terminated TLS.
    """
    with _client() as c:
        r = c.post(
            "/api/auth/login", json=_CREDS,
            headers={"X-Forwarded-Proto": proto},
        )
    assert r.status_code == 403


async def test_the_escape_hatch_reopens_it(user, monkeypatch):
    monkeypatch.setenv(ENV_ALLOW_INSECURE, "1")
    with _client() as c:
        r = c.post("/api/auth/login", json=_CREDS)
    assert r.status_code == 200


async def test_the_escape_hatch_needs_the_exact_value(user, monkeypatch):
    """A truthy-looking value is not consent — only "1" is."""
    monkeypatch.setenv(ENV_ALLOW_INSECURE, "true")
    with _client() as c:
        r = c.post("/api/auth/login", json=_CREDS)
    assert r.status_code == 403


async def test_the_login_page_still_loads_over_plain_http():
    """So the browser can render the refusal rather than showing raw JSON.

    These carry no credential, so nothing is at risk in letting them through,
    and blocking them would leave a LAN visitor staring at an error code with
    no way to find out what to do.
    """
    with _client() as c:
        for path in ("/api/health", "/api/auth/status", "/api/version"):
            assert c.get(path).status_code == 200, path


# ── The bind, which is the only place this can actually be prevented ─────────
# By the time the middleware refuses, the password is already on the wire. The
# refusal stops a session being established and tells the operator; it cannot
# un-send the bytes. Not publishing the port is the real control.

@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", ""])
def test_the_default_bind_is_loopback(host, monkeypatch):
    from main import _check_exposure, _is_loopback_bind

    monkeypatch.delenv(ENV_ALLOW_INSECURE, raising=False)
    if host == "":
        # The empty string is uvicorn's "all interfaces", not loopback.
        assert _is_loopback_bind(host) is False
        assert _check_exposure(host, None) is not None
    else:
        assert _is_loopback_bind(host) is True
        assert _check_exposure(host, None) is None


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.200.31", "hub.local"])
def test_a_routable_bind_without_tls_refuses_to_start(host, monkeypatch):
    from main import _check_exposure

    monkeypatch.delenv(ENV_ALLOW_INSECURE, raising=False)
    problem = _check_exposure(host, None)
    assert problem is not None
    assert "SYBR_HUB_SSL_CERT" in problem


def test_a_routable_bind_with_tls_is_fine(monkeypatch):
    from main import _check_exposure

    monkeypatch.delenv(ENV_ALLOW_INSECURE, raising=False)
    assert _check_exposure("0.0.0.0", "/etc/ssl/hub.pem") is None


def test_the_escape_hatch_also_reopens_the_bind(monkeypatch):
    from main import _check_exposure

    monkeypatch.setenv(ENV_ALLOW_INSECURE, "1")
    assert _check_exposure("0.0.0.0", None) is None


def test_an_unparseable_bind_is_treated_as_routable(monkeypatch):
    """Wrong in the safe direction: refuse what we cannot understand."""
    from main import _check_exposure

    monkeypatch.delenv(ENV_ALLOW_INSECURE, raising=False)
    assert _check_exposure("not-an-address", None) is not None


# ── The cookie flag keeps its own, different answer ──────────────────────────

def test_a_local_terminator_still_gets_secure_cookies():
    """`credentials_may_cross` and `_cookie_secure` must not collapse into one.

    Loopback client, public host: the credential may cross (a TLS terminator
    is in front), *and* the cookie must be marked Secure (the browser's leg of
    the journey is HTTPS). One predicate cannot answer both.
    """
    from starlette.datastructures import Headers
    from starlette.requests import Request

    from app.web.routes.auth import _cookie_secure
    from app.web.transport import credentials_may_cross

    scope = {
        "type": "http", "method": "GET", "path": "/", "scheme": "http",
        "server": ("hub.example.ts.net", 80), "client": ("127.0.0.1", 5000),
        "headers": Headers({"host": "hub.example.ts.net"}).raw,
        "query_string": b"",
    }
    request = Request(scope)
    assert credentials_may_cross(request) is True
    assert _cookie_secure(request) is True
