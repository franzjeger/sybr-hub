"""Web-layer authentication tests.

These exist because the app previously shipped with ``AuthMiddleware`` and
``RateLimitMiddleware`` written but never registered, and five routes with no
auth dependency at all. Nothing caught it: the suite covered parsers, crypto
and RBAC helpers, but never issued an HTTP request. The tests below assert the
wiring itself, so that failure mode can't come back silently.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.models.user import Role, User
from app.web.middleware.auth import (
    _PUBLIC_PATHS,
    _PUBLIC_PREFIXES,
    _SETUP_PATHS,
    AuthMiddleware,
    _reset_users_exist_cache,
    get_current_user,
)
from app.web.middleware.rate_limit import RateLimitMiddleware
from app.web.server import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_middleware_state():
    """Clear module-level caches that would otherwise leak between tests."""
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
    """Point the app at a throwaway SQLite file for each test."""
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
def client(app):
    # The lifespan runs migrations against the patched DB_PATH.
    with TestClient(app) as c:
        yield c


@pytest.fixture()
async def existing_user() -> User:
    return await create_user(
        username="tech",
        password="Test1234!xyz",
        display_name="Tech User",
        role=Role.technician,
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES)


def _call(client: TestClient, method: str, path: str):
    """Issue *method* against *path*, sending a body only where one is valid."""
    if method in ("post", "put", "patch"):
        return getattr(client, method)(path, json={})
    return getattr(client, method)(path)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_auth_middleware_is_registered(app):
    """Regression: AuthMiddleware existed but was never added to the app."""
    classes = [m.cls for m in app.user_middleware]
    assert AuthMiddleware in classes


def test_rate_limit_middleware_is_registered(app):
    classes = [m.cls for m in app.user_middleware]
    assert RateLimitMiddleware in classes


def test_rate_limit_runs_outside_auth(app):
    """Rate limiting must reject floods before auth spends a DB round-trip.

    ``add_middleware`` prepends, so ``user_middleware`` is ordered
    outermost-first: RateLimit has to come before Auth in that list.
    """
    classes = [m.cls for m in app.user_middleware]
    assert classes.index(RateLimitMiddleware) < classes.index(AuthMiddleware)


# ---------------------------------------------------------------------------
# Every route is guarded
# ---------------------------------------------------------------------------


def _iter_api_routes(app) -> list[tuple[str, APIRoute]]:
    """Yield ``(effective_path, route)`` for every APIRoute in the app.

    FastAPI >= 0.140 wraps each ``include_router`` call in an internal
    ``_IncludedRouter`` rather than flattening its routes into ``app.routes``,
    so a naive walk over ``app.routes`` sees only ``/api/health``. Handle both
    shapes; ``test_route_walk_finds_the_whole_api`` guards against this
    silently returning nothing if the internals change again.
    """
    found: list[tuple[str, APIRoute]] = []

    def walk(routes, prefix: str) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                found.append((prefix + route.path, route))
                continue
            ctx = getattr(route, "include_context", None)
            if ctx is not None:  # FastAPI >= 0.140
                walk(ctx.included_router.routes, prefix + (ctx.prefix or ""))
                continue
            sub = getattr(route, "routes", None)
            if sub:
                walk(sub, prefix)

    walk(app.routes, "")
    return found


def _auth_dependencies(route: APIRoute) -> list:
    """Return the auth-related dependency callables reachable from *route*."""
    from fastapi.dependencies.utils import get_flat_dependant

    def _is_auth_dep(call) -> bool:
        # require_role() returns a closure named `_check` defined inside it,
        # so match on the enclosing function's qualname.
        return call is get_current_user or getattr(
            call, "__qualname__", ""
        ).startswith("require_role")

    flat = get_flat_dependant(route.dependant, skip_repeats=True)
    return [dep.call for dep in flat.dependencies if _is_auth_dep(dep.call)]


def test_route_walk_finds_the_whole_api(app):
    """Canary: if the walk stops finding routes, the guard below is vacuous."""
    paths = {path for path, _ in _iter_api_routes(app)}
    assert len(paths) > 30, f"route walk only found {len(paths)} routes: {sorted(paths)}"
    # Spot-check one route from each included router.
    for expected in (
        "/api/health",
        "/api/hub/{customer_id}",
        "/api/vpn/profiles",
        "/api/fortigate/all",
        "/api/network-devices",
    ):
        assert expected in paths, f"{expected} missing from route walk"


def test_every_route_has_an_auth_dependency(app):
    """Regression: five UniFi/network routes shipped with no auth dependency.

    A route is exempt only if it is explicitly listed as public in the
    middleware — that list is the single place a route may be opened up.
    """
    unguarded = []
    for path, route in _iter_api_routes(app):
        if _is_public(path):
            continue
        if not _auth_dependencies(route):
            unguarded.append(f"{sorted(route.methods)} {path}")

    assert not unguarded, (
        "routes reachable without an auth dependency:\n  " + "\n  ".join(unguarded)
    )


def test_public_paths_do_not_require_auth(client):
    assert client.get("/api/health").status_code == 200


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/vpn/profiles"),
        ("get", "/api/vpn/status"),
        ("post", "/api/vpn/force-disconnect"),
        ("get", "/api/network-devices"),
        ("get", "/api/network/config-backups"),
        ("post", "/api/unifi/save"),
        ("post", "/api/network/quick-audit"),
        ("post", "/api/network/save-config-backup"),
        ("get", "/api/fortigate/all"),
        ("get", "/api/hub/some-customer"),
    ],
)
async def test_unauthenticated_request_is_rejected(client, existing_user, method, path):
    resp = _call(client, method, path)
    assert resp.status_code == 401, f"{method.upper()} {path} returned {resp.status_code}"


async def test_invalid_token_is_rejected(client, existing_user):
    resp = client.get("/api/vpn/profiles", headers=_auth_headers("not-a-jwt"))
    assert resp.status_code == 401


async def test_valid_token_reaches_the_route(client, existing_user):
    token = await create_access_token(existing_user)
    resp = client.get("/api/vpn/profiles", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert "profiles" in resp.json()


async def test_token_in_cookie_is_accepted(client, existing_user):
    token = await create_access_token(existing_user)
    client.cookies.set("access_token", token)
    resp = client.get("/api/vpn/profiles")
    assert resp.status_code == 200


async def test_refresh_token_cannot_be_used_as_access_token(client, existing_user):
    from app.core.auth import create_refresh_token

    token = await create_refresh_token(existing_user)
    resp = client.get("/api/vpn/profiles", headers=_auth_headers(token))
    assert resp.status_code == 401


async def test_blacklisted_token_is_rejected(client, existing_user):
    from app.core.auth import blacklist_token

    token = await create_access_token(existing_user)
    assert client.get("/api/vpn/profiles", headers=_auth_headers(token)).status_code == 200

    blacklist_token(token)
    assert client.get("/api/vpn/profiles", headers=_auth_headers(token)).status_code == 401


async def test_deactivated_user_is_rejected(client, existing_user):
    from app.core.auth import update_user

    token = await create_access_token(existing_user)
    await update_user(existing_user.id, is_active=False)
    resp = client.get("/api/vpn/profiles", headers=_auth_headers(token))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Role enforcement
# ---------------------------------------------------------------------------


async def test_viewer_cannot_reach_technician_route(client):
    viewer = await create_user(
        username="viewer",
        password="Test1234!xyz",
        display_name="Viewer",
        role=Role.viewer,
    )
    token = await create_access_token(viewer)
    resp = client.post("/api/vpn/profiles", headers=_auth_headers(token), json={
        "name": "p", "protocol": "wireguard", "config": {},
    })
    assert resp.status_code == 403


async def test_technician_cannot_reach_admin_route(client, existing_user):
    token = await create_access_token(existing_user)
    resp = client.post("/api/fortigate/backup-all", headers=_auth_headers(token))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# First-run bypass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/vpn/profiles"),
        ("post", "/api/vpn/force-disconnect"),
        ("get", "/api/network-devices"),
        ("post", "/api/unifi/save"),
        ("get", "/api/hub/some-customer"),
    ],
)
def test_first_run_does_not_open_the_whole_app(client, method, path):
    """Regression: with zero users the middleware used to allow *everything*.

    On a fresh install anyone reaching the port could connect VPNs, bootstrap
    firewalls and read stored credentials. Only the setup paths may be open.
    """
    resp = _call(client, method, path)
    assert resp.status_code == 401, f"{method.upper()} {path} returned {resp.status_code}"


def test_setup_paths_are_the_only_first_run_exception():
    """Guard the size of the first-run hole — it should stay tiny."""
    assert sorted(_SETUP_PATHS) == ["/api/auth/setup", "/api/auth/status"]


async def test_get_current_user_refuses_synthetic_admin_off_setup_path():
    """The synthetic setup admin must not leak onto ordinary routes."""
    from fastapi import HTTPException
    from starlette.datastructures import Headers
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/vpn/profiles",
        "headers": Headers({}).raw,
        "query_string": b"",
    }
    request = Request(scope)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request)
    assert exc.value.status_code == 401


async def test_get_current_user_allows_synthetic_admin_on_setup_path():
    from starlette.datastructures import Headers
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/auth/setup",
        "headers": Headers({}).raw,
        "query_string": b"",
    }
    user = await get_current_user(Request(scope))
    assert user.role == Role.admin
    assert user.id == "__setup__"


async def test_synthetic_admin_disappears_once_a_user_exists(existing_user):
    from fastapi import HTTPException
    from starlette.datastructures import Headers
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/auth/setup",
        "headers": Headers({}).raw,
        "query_string": b"",
    }
    with pytest.raises(HTTPException) as exc:
        await get_current_user(Request(scope))
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


async def test_toolkit_error_maps_to_its_status_code(client, existing_user):
    """Regression: ValidationError surfaced as a 500 with a stack trace.

    exceptions.py documented a global handler in server.py that didn't exist.
    """
    token = await create_access_token(existing_user)
    # device_code is required — the route raises ValidationError (400).
    resp = client.get(
        "/api/vpn/azure/device-code/status", headers=_auth_headers(token)
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert body["error_type"] == "validation_error"


async def test_not_found_error_maps_to_404(client, existing_user):
    token = await create_access_token(existing_user)
    resp = client.get("/api/vpn/profiles/does-not-exist", headers=_auth_headers(token))
    assert resp.status_code == 404
    assert resp.json()["error_type"] == "not_found"
