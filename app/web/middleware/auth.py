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
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import Depends, Request
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
        return await call_next(request)


def _extract_token(request: Request) -> Optional[str]:
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
        created_at=datetime.now(timezone.utc),
        is_active=True,
    )


async def get_current_user(request: Request) -> User:
    """FastAPI dependency — returns the authenticated user.

    Raises 401 if not authenticated.  The AuthMiddleware must run first
    to populate ``request.state.user``.
    """
    user: Optional[User] = getattr(request.state, "user", None)
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


# Convenience shortcuts
require_admin = require_role(Role.admin)
require_technician = require_role(Role.technician)
require_viewer = require_role(Role.viewer)
