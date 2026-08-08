"""FastAPI dependencies for authentication and role-based access control.

Usage in route modules::

    from app.web.middleware.auth import get_current_user, require_role
    from app.models.user import Role

    @router.get("/protected")
    async def protected(user: User = Depends(get_current_user)):
        ...

    @router.post("/admin-only")
    async def admin_only(user: User = Depends(require_role(Role.admin))):
        ...

WebSocket routes must use the ``_ws`` variants instead. ``AuthMiddleware`` is a
``BaseHTTPMiddleware``, and Starlette returns early from those for any scope
that is not ``http`` — so none of the middleware below, authentication or rate
limiting, runs for a WebSocket handshake::

    @router.websocket("/ws/thing")
    async def thing(websocket: WebSocket, user: User = Depends(get_current_user_ws)):
        await websocket.accept()
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Depends, Request, WebSocket, WebSocketException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.auth import (
    decode_token,
    get_user_by_id,
    get_user_count,
    validate_session,
)
from app.models.user import Role, User

logger = logging.getLogger(__name__)

# Paths that never require authentication.
_PUBLIC_PATHS: set[str] = {
    "/",
    "/favicon.ico",
    "/api/version",
    "/api/health",
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/setup",
    "/api/auth/status",
    "/api/changelog",
    "/api/settings/logo",      # branding displayed on the login page
    "/api/settings/branding",  # same — non-sensitive UI metadata
    "/api/vpn/azure/callback",
}

# Path prefixes that never require authentication.
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/static/",
    "/branding/",
)

# Paths that may run *before any account exists*, so the first admin can be
# created. This set is deliberately tiny: on a fresh install these are the
# only endpoints reachable without a token. Everything else answers 401 until
# setup completes.
_SETUP_PATHS: set[str] = {
    "/api/auth/setup",
    "/api/auth/status",
}


def _is_public(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


# ── First-run detection ──────────────────────────────────────────────────────
# Latched: once any account exists the app can never re-enter first-run mode,
# so we stop paying for a COUNT(*) on every single request. Deleting the last
# user does not reopen setup — that would be a privilege-escalation path, not
# a feature.
_users_exist: bool = False


async def users_exist() -> bool:
    """Return True once at least one account has ever been observed."""
    global _users_exist
    if _users_exist:
        return True
    if await get_user_count() > 0:
        _users_exist = True
    return _users_exist


def _reset_users_exist_cache() -> None:
    """Test hook — clear the first-run latch between test cases."""
    global _users_exist
    _users_exist = False


# ── Middleware: attach user to request state ─────────────────────────────────

class AuthMiddleware(BaseHTTPMiddleware):
    """Extract JWT from Authorization header or cookie and attach user to request.

    Public paths bypass authentication.  When no users exist (first-run), the
    handful of paths in ``_SETUP_PATHS`` — and only those — are reachable so
    the first admin account can be created.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Always allow public paths
        if _is_public(request.url.path):
            return await call_next(request)

        # First-run: only the setup endpoints are open, and only while no
        # account exists. Any other path falls through to the normal token
        # checks below and gets a 401.
        if request.url.path in _SETUP_PATHS and not await users_exist():
            return await call_next(request)

        # Extract token
        token = _extract_token(request)
        if not token:
            logger.info(
                "401 missing-token: %s %s (auth hdr=%s, cookie=%s)",
                request.method, request.url.path,
                "yes" if request.headers.get("authorization") else "no",
                "yes" if request.cookies.get("access_token") else "no",
            )
            return JSONResponse(
                {"error": "Authentication required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Decode & validate
        payload = await decode_token(token)
        if not payload or payload.token_type != "access":
            logger.info(
                "401 invalid-token: %s %s (reason=%s)",
                request.method, request.url.path,
                "decode-failed" if not payload else f"wrong-type:{payload.token_type}",
            )
            return JSONResponse(
                {"error": "Invalid or expired token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        # A token bound to a session dies with that session, so revoking
        # sessions ("log out everywhere") actually revokes access instead of
        # leaving outstanding access tokens valid for their full lifetime.
        if payload.session_id and not await validate_session(payload.session_id):
            logger.info(
                "401 dead-session: %s %s (sid=%s)",
                request.method, request.url.path, payload.session_id,
            )
            return JSONResponse(
                {"error": "Session expired"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Load full user record
        user = await get_user_by_id(payload.sub)
        if not user or not user.is_active:
            logger.info(
                "403 user-disabled: %s %s (sub=%s, found=%s)",
                request.method, request.url.path, payload.sub,
                "no" if not user else "inactive",
            )
            return JSONResponse(
                {"error": "User account is disabled"},
                status_code=403,
            )

        # Attach to request state for downstream dependencies
        request.state.user = user
        from app.core.customer import (
            bind_request_customer_scope,
            reset_request_customer_scope,
        )
        from app.core.rbac import get_accessible_customer_ids

        allowed = await get_accessible_customer_ids(user)
        customer_scope = bind_request_customer_scope(user.id, allowed)
        try:
            return await call_next(request)
        finally:
            reset_request_customer_scope(customer_scope)


def _extract_token(request: Request) -> str | None:
    """Extract JWT from Authorization header or session cookie."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get("access_token")


# ── Dependencies ─────────────────────────────────────────────────────────────

def _setup_user() -> User:
    """Synthetic admin used only by the first-run setup endpoints."""
    return User(
        id="__setup__",
        username="setup",
        display_name="Initial Setup",
        role=Role.admin,
        created_at=datetime.now(UTC),
        is_active=True,
    )


async def get_current_user(request: Request) -> User:
    """FastAPI dependency — returns the authenticated user.

    Raises 401 if not authenticated.  The AuthMiddleware must run first
    to populate ``request.state.user``.
    """
    user: User | None = getattr(request.state, "user", None)
    if user:
        return user

    # First-run: the setup endpoints run before any account exists, so they
    # get a synthetic admin. Every other path requires a real token — a
    # blanket fallback here would hand admin to anyone who reached the port.
    if request.url.path in _SETUP_PATHS and not await users_exist():
        return _setup_user()

    from fastapi import HTTPException
    raise HTTPException(status_code=401, detail="Not authenticated")


def require_role(min_role: Role) -> Callable:
    """FastAPI dependency factory — requires at least ``min_role``."""

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role < min_role:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail=f"Requires {min_role.value} role or higher",
            )
        return user

    return _check


# ── WebSocket dependencies ───────────────────────────────────────────────────
#
# These exist because AuthMiddleware cannot see a WebSocket handshake at all
# (Starlette skips BaseHTTPMiddleware for non-http scopes), so every guard the
# middleware applies to HTTP has to be repeated here.

# A browser cannot set headers on a WebSocket handshake, so the token rides in
# the subprotocol list when there is no usable cookie. The JWT itself contains
# dots, hence partitioning on the first one only.
_WS_TOKEN_PREFIX = "access_token."


def _extract_ws_token(websocket: WebSocket) -> str | None:
    """Pull the access token off a handshake: cookie, subprotocol, then query.

    Cookie first because it is the only channel that does not end up in an
    access log. The query fallback stays for the terminal client, which still
    builds its URL that way; it is the least private of the three.
    """
    token = websocket.cookies.get("access_token")
    if token:
        return token

    for offered in websocket.headers.get("sec-websocket-protocol", "").split(","):
        offered = offered.strip()
        if offered.startswith(_WS_TOKEN_PREFIX):
            return offered[len(_WS_TOKEN_PREFIX):]

    return websocket.query_params.get("token") or None


async def get_current_user_ws(websocket: WebSocket) -> User:
    """Authenticate a WebSocket handshake, or abort it.

    Raises ``WebSocketException`` rather than closing the socket: a dependency
    that calls ``websocket.close()`` and returns does NOT stop the endpoint —
    FastAPI runs the handler anyway, which then blows up on "cannot call send
    once a close message has been sent". Raising aborts before the body runs.

    There is deliberately no first-run bypass. ``_SETUP_PATHS`` is scoped to two
    HTTP endpoints; no WebSocket is a setup path, and handing a synthetic admin
    to an anonymous handshake would open a local shell on a fresh install.
    """
    token = _extract_ws_token(websocket)
    if not token:
        raise WebSocketException(code=1008, reason="Not authenticated")

    payload = await decode_token(token)
    if not payload or payload.token_type != "access":
        raise WebSocketException(code=1008, reason="Invalid token")

    # Same revocation check the middleware does at the HTTP layer — without it
    # "log out everywhere" would leave established sockets working until the
    # access token expired on its own.
    if payload.session_id and not await validate_session(payload.session_id):
        raise WebSocketException(code=1008, reason="Session expired")

    user = await get_user_by_id(payload.sub)
    if not user or not user.is_active:
        raise WebSocketException(code=1008, reason="User disabled")

    return user


def require_role_ws(min_role: Role) -> Callable:
    """WebSocket counterpart of :func:`require_role`."""

    async def _check(user: User = Depends(get_current_user_ws)) -> User:
        if user.role < min_role:
            logger.info(
                "WS role denied: user=%s role=%s required=%s",
                user.username, user.role.value, min_role.value,
            )
            raise WebSocketException(
                code=1008, reason=f"Requires {min_role.value} role or higher"
            )
        return user

    return _check


def require_feature(key: str) -> Callable:
    """Dependency factory for a named feature.

    Preferred over a bare require_role: the requirement then lives in one table
    the interface also reads, so a screen cannot offer what a route refuses.
    Asking for a feature that does not exist raises at import rather than
    granting access to everybody, which is the failure a typo would otherwise
    produce here.
    """
    from app.core.features import allows, get

    feature = get(key)

    async def _check(user: User = Depends(get_current_user)) -> User:
        if not allows(user, feature):
            from fastapi import HTTPException

            logger.warning(
                "403 feature: user=%s role=%s feature=%s",
                user.username, getattr(user.role, "value", user.role), key,
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    "Kontoen din har ikke tilgang til denne delen av verktøyet."
                ),
            )
        return user

    return _check


def require_tenant_write(min_role: Role = Role.technician) -> Callable:
    """Dependency factory for anything that changes a customer's tenant.

    Three checks, and all three have to pass:

      1. the role floor — technician by default, because a viewer has no
         business here whatever else they hold;
      2. access to *this* customer, so the capability does not become a
         skeleton key across the estate;
      3. both capabilities: can_write, and tenant_write on top of it.

    The third is the point. Sybr HUB is read-mostly by design and every Graph
    permission it asks for ends in .Read.All, so until now "write" was
    impossible rather than forbidden — a distinction that stops being
    comforting the moment the first write endpoint lands. Making it an
    explicit per-user grant means the default stays read for everyone,
    including admins, and turning it on is a decision somebody made rather
    than a side effect of a role they already had.

    Every refusal and every use is logged. This is the boundary where a
    mistake reaches a customer's production, so the log should be able to
    answer "who did that" without anyone having anticipated the question.
    """
    access_check = require_customer_access(min_role)

    async def _check(customer_id: str, user: User = Depends(access_check)) -> User:
        # can_write as well: writing into a customer's tenant is the far end of
        # writing at all, and an account that may not save a note here has no
        # business changing configuration there.
        if not (getattr(user, "can_write", False) and getattr(user, "tenant_write", False)):
            from fastapi import HTTPException

            logger.warning(
                "403 tenant-write: user=%s customer=%s role=%s",
                user.username, customer_id, user.role.value,
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    "Denne handlingen skriver til kundens tenant og krever "
                    "skrivetilgang. Kontoen din har lesetilgang."
                ),
            )
        logger.warning(
            "tenant-write exercised: user=%s customer=%s", user.username, customer_id
        )
        return user

    return _check


def require_customer_access(min_role: Role = Role.viewer) -> Callable:
    """Dependency factory for routes scoped to a single customer.

    Enforces the role floor *and* that the caller may see this particular
    customer. ``customer_id`` is taken from the path, so any route with a
    ``{customer_id}`` segment can use this directly.

    Without it, per-customer RBAC was effectively decorative: only one route
    consulted it, so a technician assigned to customer A could read customer
    B's dashboard, backups and threat logs by changing the URL.
    """
    role_check = require_role(min_role)

    async def _check(customer_id: str, user: User = Depends(role_check)) -> User:
        from app.core.rbac import check_customer_access

        if not await check_customer_access(user, customer_id):
            from fastapi import HTTPException
            logger.info(
                "403 customer-access: user=%s customer=%s", user.username, customer_id
            )
            raise HTTPException(
                status_code=403,
                detail="Du har ikke tilgang til denne kunden",
            )
        return user

    return _check


def require_host_access(min_role: Role = Role.viewer) -> Callable:
    """Dependency factory for routes scoped to a single SSH/RDP host.

    The per-customer guard above reads ``customer_id`` out of the path, so it
    only ever attached to routes that spell the customer that way. Hosts name
    their customer indirectly — ``ssh_hosts.customer_id`` — so the entire SSH
    surface, which holds device passwords and hands out interactive shells,
    was left with a role floor and no tenancy check at all.

    A host with no customer is treated as estate-wide infrastructure and
    restricted to callers who are unrestricted, rather than being open to
    everyone: the column is optional in the UI, so "unset" must not read as
    "unowned, therefore free".
    """
    role_check = require_role(min_role)

    async def _check(host_id: str, user: User = Depends(role_check)) -> User:
        from fastapi import HTTPException

        from app.core.rbac import check_customer_access, get_accessible_customer_ids
        from app.services.ssh_manager import get_host

        host = await get_host(host_id)
        if host is None:
            raise HTTPException(status_code=404, detail="Host finnes ikke")

        if host.customer_id:
            ok = await check_customer_access(user, host.customer_id)
        else:
            ok = await get_accessible_customer_ids(user) is None

        if not ok:
            logger.info(
                "403 host-access: user=%s host=%s customer=%s",
                user.username, host_id, host.customer_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Du har ikke tilgang til denne hosten",
            )
        return user

    return _check


def require_audit_path_access(min_role: Role = Role.viewer) -> Callable:
    """Dependency factory for routes serving files out of the audit tree.

    ``path`` is taken from the route, and its first segment identifies the
    customer. See ``check_audit_path_access`` for why this fails closed.
    """
    role_check = require_role(min_role)

    async def _check(path: str, user: User = Depends(role_check)) -> User:
        from fastapi import HTTPException

        from app.core.rbac import check_audit_path_access

        if not await check_audit_path_access(user, path):
            raise HTTPException(
                status_code=403,
                detail="Du har ikke tilgang til denne kundens data",
            )
        return user

    return _check


# Convenience shortcuts
require_admin = require_role(Role.admin)
require_technician = require_role(Role.technician)
require_viewer = require_role(Role.viewer)
