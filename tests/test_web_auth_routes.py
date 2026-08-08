"""End-to-end tests for the auth routes: setup, login, refresh, logout.

Enforcing authentication is only half a fix — without these endpoints a
fresh install has no way to create its first account, and no way to obtain a
token afterwards.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.auth import create_initial_admin, create_user, delete_user_sessions
from app.core.database import run_migrations
from app.core.exceptions import ConflictError
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.routes.auth import _cookie_secure
from app.web.server import create_app

GOOD_PASSWORD = "Test1234!xyz"


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
def client():
    with TestClient(create_app()) as c:
        yield c


def _setup_payload(**over) -> dict:
    return {
        "username": "admin",
        "password": GOOD_PASSWORD,
        "display_name": "Admin",
        **over,
    }


# ---------------------------------------------------------------------------
# First-run setup
# ---------------------------------------------------------------------------


def test_status_reports_setup_required_on_a_fresh_install(client):
    resp = client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json()["setup_required"] is True


def test_browser_security_headers_are_present(client):
    resp = client.get("/api/auth/status")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "SAMEORIGIN"
    assert resp.headers["referrer-policy"] == "no-referrer"
    csp = resp.headers["content-security-policy"]
    assert "object-src 'none'" in csp
    assert "script-src 'self';" in csp
    assert "script-src-elem 'self'" in csp
    assert "script-src-attr 'unsafe-inline'" in csp
    assert "style-src-elem 'self'" in csp
    assert "style-src-attr 'unsafe-inline'" in csp
    assert "cdn.jsdelivr.net" not in csp
    assert resp.headers["cache-control"] == "no-store"


def test_openapi_csp_relaxation_is_path_scoped(client):
    docs_csp = client.get("/docs").headers["content-security-policy"]
    app_csp = client.get("/").headers["content-security-policy"]

    assert "cdn.jsdelivr.net" in docs_csp
    assert "'unsafe-inline'" not in docs_csp
    assert "cdn.jsdelivr.net" not in app_csp


def test_http_cookie_exception_is_limited_to_loopback(monkeypatch):
    monkeypatch.delenv("SYBR_COOKIE_SECURE", raising=False)

    def request(client_host: str, host: str) -> Request:
        return Request({
            "type": "http",
            "scheme": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [(b"host", host.encode())],
            "client": (client_host, 12345),
            "server": (host, 80),
        })

    assert _cookie_secure(request("127.0.0.1", "localhost")) is False
    assert _cookie_secure(request("192.0.2.10", "hub.example.com")) is True


def test_setup_creates_the_first_admin_and_returns_tokens(client):
    resp = client.post("/api/auth/setup", json=_setup_payload())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["role"] == "admin"
    assert body["access_token"] and body["refresh_token"]
    assert client.get("/api/auth/status").json()["setup_required"] is False


def test_setup_is_refused_once_an_account_exists(client):
    assert client.post("/api/auth/setup", json=_setup_payload()).status_code == 200
    resp = client.post("/api/auth/setup", json=_setup_payload(username="second"))
    assert resp.status_code == 409
    assert resp.json()["error_type"] == "conflict"


async def test_simultaneous_setup_creates_exactly_one_admin():
    results = await asyncio.gather(
        create_initial_admin("admin-a", GOOD_PASSWORD, "Admin A"),
        create_initial_admin("admin-b", GOOD_PASSWORD, "Admin B"),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ConflictError) for result in results) == 1


def test_setup_enforces_the_password_policy(client):
    resp = client.post("/api/auth/setup", json=_setup_payload(password="short1!"))
    assert resp.status_code == 422  # pydantic min_length rejects it first


def test_setup_rejects_a_weak_but_long_password(client):
    resp = client.post("/api/auth/setup", json=_setup_payload(password="passwordpassword"))
    assert resp.status_code == 400
    assert resp.json()["error_type"] == "validation_error"


def test_setup_closes_the_first_run_window(client):
    """After setup, unauthenticated requests must be rejected again."""
    client.post("/api/auth/setup", json=_setup_payload())
    client.cookies.clear()
    assert client.get("/api/network-devices").status_code == 401


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


async def test_login_returns_tokens_and_cookies(client):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    resp = client.post("/api/auth/login", json={"username": "tech", "password": GOOD_PASSWORD})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["username"] == "tech"
    assert "access_token" in resp.cookies or "access_token" in client.cookies


async def test_login_sets_hardened_cookies(client):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    resp = client.post("/api/auth/login", json={"username": "tech", "password": GOOD_PASSWORD})
    cookie_header = " ".join(resp.headers.get_list("set-cookie")).lower()
    # SameSite=Strict is the CSRF defence for cookie-authenticated requests.
    assert "httponly" in cookie_header
    assert "samesite=strict" in cookie_header
    assert "secure" in cookie_header


async def test_login_with_wrong_password_is_rejected(client):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    resp = client.post("/api/auth/login", json={"username": "tech", "password": "Wrong1234!x"})
    assert resp.status_code == 401


async def test_login_does_not_reveal_whether_a_username_exists(client):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    known = client.post("/api/auth/login", json={"username": "tech", "password": "Wrong1234!x"})
    unknown = client.post("/api/auth/login", json={"username": "nope", "password": "Wrong1234!x"})
    assert known.status_code == unknown.status_code == 401
    assert known.json()["error"] == unknown.json()["error"]


async def test_login_rejects_a_deactivated_account(client):
    from app.core.auth import update_user

    user = await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    await update_user(user.id, is_active=False)
    resp = client.post("/api/auth/login", json={"username": "tech", "password": GOOD_PASSWORD})
    assert resp.status_code == 401


async def test_login_token_reaches_a_protected_route(client):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    token = client.post(
        "/api/auth/login", json={"username": "tech", "password": GOOD_PASSWORD}
    ).json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["user"]["username"] == "tech"


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


async def test_refresh_issues_a_new_access_token(client):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    login = client.post(
        "/api/auth/login", json={"username": "tech", "password": GOOD_PASSWORD}
    ).json()
    resp = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


async def test_refresh_rejects_an_access_token(client):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    login = client.post(
        "/api/auth/login", json={"username": "tech", "password": GOOD_PASSWORD}
    ).json()
    resp = client.post("/api/auth/refresh", json={"refresh_token": login["access_token"]})
    assert resp.status_code == 401


async def test_refresh_fails_once_the_session_is_revoked(client):
    """Regression: sessions existed but nothing ever checked them."""
    user = await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    login = client.post(
        "/api/auth/login", json={"username": "tech", "password": GOOD_PASSWORD}
    ).json()

    await delete_user_sessions(user.id)

    resp = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Session revocation
# ---------------------------------------------------------------------------


async def test_revoking_sessions_invalidates_outstanding_access_tokens(client):
    """Regression: 'log out everywhere' left access tokens usable for an hour."""
    user = await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    token = client.post(
        "/api/auth/login", json={"username": "tech", "password": GOOD_PASSWORD}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    await delete_user_sessions(user.id)

    assert client.get("/api/auth/me", headers=headers).status_code == 401


async def test_logout_revokes_the_current_token(client):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    token = client.post(
        "/api/auth/login", json={"username": "tech", "password": GOOD_PASSWORD}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    client.cookies.clear()
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_logout_requires_authentication(client):
    assert client.post("/api/auth/logout").status_code == 401


def test_me_requires_authentication(client):
    assert client.get("/api/auth/me").status_code == 401
