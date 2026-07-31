"""Web-layer authentication tests.

These exist because the app previously shipped with ``AuthMiddleware`` and
``RateLimitMiddleware`` written but never registered, and five routes with no
auth dependency at all. Nothing caught it: the suite covered parsers, crypto
and RBAC helpers, but never issued an HTTP request. The tests below assert the
wiring itself, so that failure mode can't come back silently.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocketDisconnect

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
    get_current_user_ws,
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


def _walk_routes(app) -> tuple[list, list, list]:
    """Return ``(http, websocket, raw_websocket)`` route lists for the app.

    FastAPI >= 0.140 wraps each ``include_router`` call in an internal
    ``_IncludedRouter`` rather than flattening its routes into ``app.routes``,
    so a naive walk over ``app.routes`` sees only ``/api/health``. Handle both
    shapes; ``test_route_walk_finds_the_whole_api`` guards against this
    silently returning nothing if the internals change again.

    WebSocket routes are collected separately because ``APIWebSocketRoute`` is
    *not* a subclass of ``APIRoute``. The original walk tested only for the
    latter, so all three WebSocket routes were skipped in silence — which is
    how an unauthenticated terminal shipped past a suite that asserts every
    route is guarded.
    """
    http: list[tuple[str, APIRoute]] = []
    ws: list[tuple[str, APIWebSocketRoute]] = []
    raw_ws: list[tuple[str, object]] = []

    def walk(routes, prefix: str) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                http.append((prefix + route.path, route))
                continue
            if isinstance(route, APIWebSocketRoute):
                ws.append((prefix + route.path, route))
                continue
            if isinstance(route, WebSocketRoute):
                # Raw Starlette route: cannot carry Depends() at all, so it can
                # never be audited. Collected so the test below can reject it.
                raw_ws.append((prefix + route.path, route))
                continue
            ctx = getattr(route, "include_context", None)
            if ctx is not None:  # FastAPI >= 0.140
                walk(ctx.included_router.routes, prefix + (ctx.prefix or ""))
                continue
            sub = getattr(route, "routes", None)
            if sub:
                walk(sub, prefix)

    walk(app.routes, "")
    return http, ws, raw_ws


def _iter_api_routes(app) -> list[tuple[str, APIRoute]]:
    """Yield ``(effective_path, route)`` for every HTTP APIRoute in the app."""
    return _walk_routes(app)[0]


def _iter_ws_routes(app) -> list[tuple[str, "APIWebSocketRoute"]]:
    """Yield ``(effective_path, route)`` for every WebSocket route in the app."""
    return _walk_routes(app)[1]


def _auth_dependencies(route: APIRoute) -> list:
    """Return the auth-related dependency callables reachable from *route*."""
    from tests.fastapi_introspect import flat_dependency_calls

    def _is_auth_dep(call) -> bool:
        # require_role() returns a closure named `_check` defined inside it,
        # so match on the enclosing function's qualname. The trailing dot
        # matters: without it `require_role_ws` also matches, and a
        # WebSocket-only guard would satisfy the HTTP audit.
        qualname = getattr(call, "__qualname__", "")
        return call is get_current_user or qualname.startswith("require_role.")

    return [call for call in flat_dependency_calls(route) if _is_auth_dep(call)]


def _ws_auth_dependencies(route) -> list:
    """Return the auth-related dependency callables on a WebSocket route."""
    from tests.fastapi_introspect import flat_dependency_calls

    def _is_ws_auth_dep(call) -> bool:
        return call is get_current_user_ws or getattr(
            call, "__qualname__", ""
        ).startswith("require_role_ws.")

    return [call for call in flat_dependency_calls(route) if _is_ws_auth_dep(call)]


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


# ── WebSocket routes ─────────────────────────────────────────────────────────
#
# AuthMiddleware is a BaseHTTPMiddleware, and Starlette skips those for any
# scope that is not "http". Nothing above this line covers a handshake.


def test_ws_route_walk_finds_the_websocket_routes(app):
    """Canary: the WebSocket audit is vacuous if the walk finds nothing."""
    paths = {path for path, _ in _iter_ws_routes(app)}
    assert paths == {
        "/guacamole/{path:path}",
        "/api/ws/dashboard",
        "/api/ws/terminal",
    }, f"unexpected WebSocket route set: {sorted(paths)}"


def test_every_ws_route_has_an_auth_dependency(app):
    """Regression: all three WebSocket routes shipped unguarded by the audit.

    APIWebSocketRoute is not an APIRoute, so the HTTP walk skipped them
    entirely — the terminal route reached production able to hand out a local
    shell with no token whenever the users table was empty.
    """
    unguarded = [
        path for path, route in _iter_ws_routes(app) if not _ws_auth_dependencies(route)
    ]
    assert not unguarded, (
        "WebSocket routes reachable without an auth dependency:\n  "
        + "\n  ".join(unguarded)
    )


def test_no_raw_starlette_websocket_routes(app):
    """A raw WebSocketRoute cannot carry Depends(), so it can never be audited."""
    raw = [path for path, _ in _walk_routes(app)[2]]
    assert not raw, f"raw Starlette WebSocket routes cannot be guarded: {raw}"


def test_public_paths_do_not_exempt_websockets(app):
    """The public-path list is an HTTP concept and must not leak into WS auth."""
    for path, _ in _iter_ws_routes(app):
        assert not _is_public(path), f"{path} is both a WebSocket route and public"


@pytest.mark.parametrize(
    "path",
    ["/guacamole/websocket-tunnel", "/api/ws/dashboard", "/api/ws/terminal?mode=ssh"],
)
def test_ws_rejects_unauthenticated_handshake(client, existing_user, path):
    """No token, no socket — on every WebSocket route."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(path):
            pass
    assert exc.value.code == 1008


@pytest.mark.parametrize(
    "path",
    ["/guacamole/websocket-tunnel", "/api/ws/dashboard", "/api/ws/terminal?mode=ssh"],
)
def test_ws_rejects_garbage_token(client, existing_user, path):
    client.cookies.set("access_token", "not-a-jwt")
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(path):
            pass
    assert exc.value.code == 1008


async def test_ws_first_run_does_not_bypass_auth(client):
    """With zero accounts the terminal must still refuse — it hands out a shell.

    This is the exact state a fresh install sits in, and the old code took it
    as licence to skip the token check *and* the role gate.
    """
    _reset_users_exist_cache()
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/ws/terminal?mode=local"):
            pass
    assert exc.value.code == 1008


async def test_ws_rejects_a_revoked_session(client, existing_user):
    """Logging out everywhere must close the WebSocket door too.

    The HTTP middleware checks validate_session; before this the WebSocket
    paths did not, so a revoked session kept working over WS until the access
    token expired on its own.
    """
    import uuid

    from app.core.auth import create_refresh_token, create_session, delete_session

    session_id = str(uuid.uuid4())
    refresh = await create_refresh_token(existing_user, session_id=session_id)
    await create_session(
        user_id=existing_user.id,
        refresh_token=refresh,
        ip_address="",
        user_agent="",
        session_id=session_id,
    )
    client.cookies.set(
        "access_token", await create_access_token(existing_user, session_id=session_id)
    )

    # Positive control: the same token opens a socket while the session lives.
    with client.websocket_connect("/api/ws/dashboard") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}

    await delete_session(session_id)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/ws/dashboard"):
            pass
    assert exc.value.code == 1008


async def test_ws_rejects_a_refresh_token(client, existing_user):
    """Only access tokens open a socket; a refresh token must not."""
    from app.core.auth import create_refresh_token

    client.cookies.set("access_token", await create_refresh_token(existing_user))
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/ws/dashboard"):
            pass
    assert exc.value.code == 1008


async def test_ws_accepts_a_valid_access_token(client, existing_user):
    """Positive control — otherwise every assertion above passes vacuously.

    ``mode=ssh`` with no host returns immediately; ``mode=local`` would fork a
    real PTY under CI.
    """
    client.cookies.set("access_token", await create_access_token(existing_user))
    with client.websocket_connect("/api/ws/dashboard") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


async def test_ws_accepts_token_via_subprotocol(client, existing_user):
    """A browser cannot set headers on a handshake, so the subprotocol carries it."""
    token = await create_access_token(existing_user)
    with client.websocket_connect(
        "/api/ws/dashboard", subprotocols=["access_token." + token]
    ) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


async def test_ws_dashboard_filters_customers_the_user_cannot_see(
    client, existing_user, monkeypatch
):
    """Only customers the user may see reach the poller.

    The REST twins gate on require_customer_access; the socket reaches the same
    poller and previously trusted whatever customer_ids the client asked for.

    Asserting on the reply is not enough — an unknown customer yields no
    devices whether or not it was filtered, so that version of this test passed
    with the filter deleted. Record what the poller is actually handed.
    """
    from app.core.rbac import grant_access
    from app.services.dashboard_poller import poller

    await grant_access(existing_user.id, "mine")

    seen: list[list[str]] = []
    original = poller.subscribe

    def _record(ws_id, customer_ids, callback):
        seen.append(list(customer_ids))
        return original(ws_id, customer_ids, callback)

    monkeypatch.setattr(poller, "subscribe", _record)

    client.cookies.set("access_token", await create_access_token(existing_user))
    with client.websocket_connect("/api/ws/dashboard") as ws:
        ws.send_json({"type": "subscribe", "customer_ids": ["mine", "not-mine"]})
        ws.receive_json()

    # The granted one survives, the other never reaches the poller. Both halves
    # matter: filtering everything would satisfy a negative-only assertion.
    assert seen == [["mine"]], f"poller was handed the wrong customer set: {seen}"


async def test_ws_dashboard_set_interval_requires_admin(client, existing_user):
    """set_interval is global; its REST twin is admin-only."""
    client.cookies.set("access_token", await create_access_token(existing_user))
    with client.websocket_connect("/api/ws/dashboard") as ws:
        ws.send_json({"type": "set_interval", "interval": 5})
        reply = ws.receive_json()
        assert reply["type"] == "error"


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

    await blacklist_token(token)
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


# ── Front-end contract ───────────────────────────────────────────────────────


def test_client_reads_the_status_fields_the_server_sends(client):
    """The SPA's first-run branch must read a field /api/auth/status returns.

    Regression: app.js branched on ``data.setup_complete`` while the endpoint
    reports ``setup_required``. ``!undefined`` is true, so checkAuth() sent the
    operator back to the setup form on every call — including the one right
    after setup had succeeded, whose retry then failed with 409. Nothing caught
    it: no test drives the static client, and both halves are individually
    correct. The mismatch arrived when the ported front-end was paired with
    this repo's auth routes.
    """
    import re
    from pathlib import Path

    body = client.get("/api/auth/status").json()
    app_js = Path(__file__).parent.parent / "app" / "web" / "static" / "app.js"
    source = app_js.read_text(encoding="utf-8")

    # Whatever the status handler destructures off its response.
    read = set(re.findall(r"data\.(setup_[A-Za-z_]+)", source))
    assert read, "app.js no longer reads a setup_* field — has the check moved?"

    unknown = read - set(body)
    assert not unknown, (
        f"app.js reads {sorted(unknown)} from /api/auth/status, "
        f"which returns {sorted(body)}"
    )


def test_service_worker_cache_version_tracks_the_build(client):
    """A stale CACHE_VERSION means shipped front-end fixes never land.

    Everything under /static/ is served to the worker cache-first, and it only
    evicts when this string changes. It was a literal that nobody bumped — it
    read v10.6.0 while the app reported 10.10.12 — so a browser that had loaded
    the app once kept running the old bundle no matter what was deployed.
    """
    from app.core.version import get_version

    from app.web.routes.frontend import _static_digest

    body = client.get("/static/sw.js").text
    # Version *and* a digest of the served assets: a release bumps the former,
    # a deploy usually does not, and a dozen front-end fixes shipped under one
    # version otherwise never evict.
    assert f"const CACHE_VERSION = 'msptoolkit-{get_version()}-{_static_digest()}'" in body
    # And the worker script itself must not be cacheable, or the browser never
    # sees the new version in the first place.
    assert "no-cache" in client.get("/static/sw.js").headers.get("cache-control", "")


def test_health_reports_the_database(client):
    """The badge reads db_ok; without it the UI shows "Degradert" forever.

    Same drift as the setup_required case: the ported front-end expects the
    richer shape this repo's slim endpoint never sent, and both halves look
    correct on their own. A health check that says ok while the database is
    unreachable is also just wrong on its own terms.
    """
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db_ok"] is True
    assert body["version"]


def test_health_is_degraded_when_the_database_is_gone(client, monkeypatch):
    """A monitor must be able to alert on this without parsing the body."""
    import app.core.database as db_mod

    def boom():
        raise RuntimeError("no database")

    monkeypatch.setattr(db_mod, "get_db", lambda: boom())

    resp = client.get("/api/health")
    assert resp.status_code == 503
    assert resp.json()["db_ok"] is False


def test_client_reads_the_health_fields_the_server_sends(client):
    """Guard the same contract for /api/health that we guard for auth/status."""
    import re
    from pathlib import Path

    body = client.get("/api/health").json()
    source = (Path(__file__).parent.parent / "app" / "web" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    # The connection monitor destructures its response as `d.<field>`.
    monitor = source[source.index("fetch('/api/health'") :][:900]
    read = set(re.findall(r"\bd\.([A-Za-z_]+)", monitor))
    unknown = read - set(body)
    assert not unknown, f"app.js reads {sorted(unknown)} from /api/health, which returns {sorted(body)}"


def test_the_audit_bar_does_not_derive_its_total_from_its_own_rows():
    """A ratio whose denominator comes from its numerator says nothing.

    The audit view counted the sections that had already announced themselves
    and used that as the total. Sections run one at a time, so the bar read
    n / n after every section and sat at 100% for the whole run — while the
    header, reading the server's figure, correctly said 19%.

    A source-level check, which is all there is without a JS test harness: it
    can show the pattern is gone, not that the replacement is right. The
    server's own counting is covered in tests/test_audit_progress.py.
    """
    import pathlib

    src = pathlib.Path("app/web/static/app.js").read_text()
    assert "sectionTotal = Object.keys(sectionRows).length" not in src, (
        "the total must not be the number of rows rendered so far"
    )
    assert "sectionTotal = d.total_sections" in src, (
        "the total should come from /api/audit/progress"
    )


def test_the_status_label_rule_is_applied_at_every_call_site():
    """Three places write the section status; changing one made it inconsistent.

    The live update, the row template and the final re-render all set it. My
    first attempt changed only the last, which would have shown "Ferdig"
    while the audit ran and blank once it finished — worse than either. Found
    by reading the DOM mid-run rather than trusting that the deploy did what
    was intended.
    """
    import pathlib
    import re

    src = pathlib.Path("app/web/static/app.js").read_text()
    assert src.count("function statusLabel(") == 1, "one rule, defined once"
    # No call site may still take the label straight from the map.
    stale = re.findall(r"status-text[^\n]*\$\{labels\[status\]", src)
    stale += re.findall(r"\.status-text'\)\.textContent = labels\[status\]", src)
    assert not stale, f"call sites bypassing statusLabel: {stale}"
    # Minus the definition line, which matches the same text.
    calls = src.count("statusLabel(status, labels)") - src.count("function statusLabel(status, labels)")
    assert calls == 3, f"expected three call sites, found {calls}"


def test_a_skipped_section_is_not_announced_as_a_failure():
    """_skip() stores its reason in the same field a failure uses.

    "No Azure subscriptions found" is a legitimate skip on a tenant without
    Azure, and the findings summary announced four of them as failures in red
    while the table below correctly said "Hoppet over". Status decides which
    group a section lands in; the reason is only the wording.
    """
    import pathlib

    src = pathlib.Path("app/web/static/app.js").read_text()
    assert "r.error && r.status === 'failed'" in src, "failures gate on status"
    assert "r.error && r.status === 'skipped'" in src, "skips get their own group"


def test_the_cache_version_changes_when_a_static_file_changes():
    """A release bumps the app version; a deploy usually does not.

    Twelve front-end fixes shipped in one day under app version 10.10.12, and
    every browser that had loaded the app once went on serving the app.js it
    already had. Deriving the cache key from the version alone could not evict
    them, so it now includes a digest of the bytes actually served.
    """
    import pathlib

    from app.web.routes import frontend

    before = frontend._static_digest()
    app_js = pathlib.Path("app/web/static/app.js")
    original = app_js.read_bytes()
    try:
        app_js.write_bytes(original + b"\n// touched\n")
        assert frontend._static_digest() != before, (
            "a changed asset must produce a new cache key"
        )
    finally:
        app_js.write_bytes(original)
    assert frontend._static_digest() == before, "and revert to the old one"


def test_the_cache_version_covers_every_cached_asset():
    """Missing one means a change to it never reaches a warm browser."""
    from app.web.routes import frontend

    assert set(frontend._CACHED_ASSETS) >= {"app.js", "app.css", "index.html"}


def test_the_theme_is_set_before_the_stylesheet_loads():
    """Otherwise every load paints in the default palette and then flips.

    :root carries the dark colours, and data-theme was only applied by the
    last line of app.js — after the browser had already painted. The result
    was a dark flash on every load for anyone using the light theme.
    """
    import pathlib

    html = pathlib.Path("app/web/static/index.html").read_text()
    theme_script = html.find("data-theme")
    stylesheet = html.find("/static/app.css")
    assert theme_script != -1 and stylesheet != -1
    assert theme_script < stylesheet, "the theme must be decided before paint"
    assert "sybr-theme" in html[:stylesheet], "and from the same key app.js uses"


def test_autofilled_fields_keep_the_apps_colours():
    """Chrome paints over an autofilled field without knowing the theme."""
    import pathlib

    css = pathlib.Path("app/web/static/app.css").read_text()
    assert "input:-webkit-autofill" in css
    assert "-webkit-text-fill-color: var(--text)" in css, (
        "only text-fill-color wins over Chrome's own colour"
    )


def test_kpi_tiles_render_their_value_not_a_placeholder():
    """The visible number must not depend on an animation finishing.

    The tiles carried a literal 0 with the truth in data-count, and the count-up
    was pinned to start at 0 with no guard against a second loop. The dashboard
    refreshes itself, so a re-render dropped the figure back to zero and raced
    the previous run; requestAnimationFrame is throttled in a background tab,
    so switching away could leave "KUNDER 0" above a table listing one customer.
    Measured on the live dashboard: 0 against 1, 23/100 against 52, 42% against
    97.
    """
    import pathlib
    import re

    src = pathlib.Path("app/web/static/app.js").read_text()
    tiles = re.findall(r'class="kpi-num" data-count="\$\{([^}]+)\}"[^>]*>([^<]*)<', src)
    assert tiles, "the KPI tiles should still be found by this pattern"
    for expr, rendered in tiles:
        assert rendered.strip() not in ("0", ""), (
            f"tile for {expr} renders a placeholder rather than its value"
        )


def test_the_count_up_starts_from_what_is_on_screen():
    """So a re-render is a no-op instead of a reset to zero."""
    import pathlib

    src = pathlib.Path("app/web/static/app.js").read_text()
    assert "var start = 0, startTime = null;" not in src, "start must not be pinned to 0"
    assert "el._countGeneration" in src, "a superseded loop must stop writing"
