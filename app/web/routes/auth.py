"""Authentication routes — first-run setup, login, refresh, logout.

These paths are listed in ``app.web.middleware.auth._PUBLIC_PATHS`` (and
``_SETUP_PATHS`` for the two first-run endpoints), so they are reachable
without a token. Everything else in the app requires one.

Tokens are returned in the response body *and* set as HttpOnly cookies, so
both a scripted client and a browser front-end can use the same endpoints.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os

from fastapi import APIRouter, Depends, Request, Response

from app.core.activity_log import log_activity
from app.core.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    authenticate,
    blacklist_token,
    change_password,
    create_access_token,
    create_initial_admin,
    create_refresh_token,
    create_session,
    create_user,
    decode_token,
    delete_session,
    delete_user,
    get_password_hash,
    get_user_by_id,
    get_user_by_username,
    get_user_count,
    list_users,
    update_user,
    verify_password,
)
from app.core.exceptions import (
    AuthError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.user import (
    LoginRequest,
    PasswordChange,
    Role,
    SetupRequest,
    TokenResponse,
    User,
    UserCreate,
    UserUpdate,
)
from app.web.middleware.auth import get_current_user, require_role

logger = logging.getLogger(__name__)
router = APIRouter()

_ACCESS_MAX_AGE = ACCESS_TOKEN_EXPIRE_MINUTES * 60
_REFRESH_MAX_AGE = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
_setup_lock = asyncio.Lock()


def _cookie_secure(request: Request) -> bool:
    """Require Secure cookies except for an explicitly local HTTP quick-start."""
    override = os.environ.get("SYBR_COOKIE_SECURE")
    if override is not None:
        return override == "1"
    if request.url.scheme == "https":
        return True
    if request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip() == "https":
        return True

    def is_loopback(value: str) -> bool:
        try:
            return ipaddress.ip_address(value).is_loopback
        except ValueError:
            return value.lower() in {"localhost", "testclient"}

    client_is_loopback = bool(request.client and is_loopback(request.client.host))
    host_is_loopback = is_loopback(request.url.hostname or "")
    return not (client_is_loopback and host_is_loopback)


def _set_auth_cookies(
    response: Response, access: str, refresh: str, request: Request,
) -> None:
    """Attach both tokens as HttpOnly cookies.

    ``samesite="strict"`` is what stops a third-party page from driving the
    state-changing endpoints with the browser's cookie attached — the app has
    no separate CSRF token, so this is the CSRF defence.
    """
    common = {
        "httponly": True,
        "secure": _cookie_secure(request),
        "samesite": "strict",
        "path": "/",
    }
    response.set_cookie("access_token", access, max_age=_ACCESS_MAX_AGE, **common)
    response.set_cookie("refresh_token", refresh, max_age=_REFRESH_MAX_AGE, **common)


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


# ── First-run setup ──────────────────────────────────────────────────────────


@router.get("/auth/status")
async def auth_status() -> dict:
    """Report whether the first admin account still needs creating."""
    return {"setup_required": await get_user_count() == 0}


@router.post("/auth/setup")
async def auth_setup(body: SetupRequest, request: Request, response: Response) -> dict:
    """Create the first admin account. Refuses once any account exists."""
    # Avoid duplicate Argon2 work inside one process; create_initial_admin also
    # takes a SQLite write lock, which closes the race across workers.
    async with _setup_lock:
        user = await create_initial_admin(
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            email=body.email,
        )

        # Close the first-run window immediately for this process, so no
        # request can slip through the setup path between here and the next DB read.
        from app.web.middleware.auth import users_exist
        await users_exist()

    tokens = await _issue_tokens(user, request)
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token, request)
    logger.info("Initial admin account created: %s", user.username)
    return {"ok": True, "user": _public_user(user), **tokens.model_dump()}


# ── Login / logout ───────────────────────────────────────────────────────────


@router.post("/auth/login")
async def auth_login(body: LoginRequest, request: Request, response: Response) -> dict:
    """Exchange username + password for an access and refresh token."""
    user = await authenticate(body.username, body.password)
    if not user:
        # Deliberately identical for "no such user", "wrong password" and
        # "account disabled" — anything more specific is an oracle.
        logger.info("Failed login for %r from %s", body.username, _client_ip(request))
        raise AuthError("Feil brukernavn eller passord")

    tokens = await _issue_tokens(user, request)
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token, request)
    return {"ok": True, "user": _public_user(user), **tokens.model_dump()}


@router.post("/auth/refresh")
async def auth_refresh(request: Request, response: Response) -> dict:
    """Exchange a valid refresh token for a fresh access token."""
    token = await _refresh_token_from(request)
    payload = await decode_token(token)
    if not payload or payload.token_type != "refresh":
        raise AuthError("Ugyldig refresh-token")

    # A refresh token is only good while its session still exists — that is
    # what makes "log out everywhere" actually revoke access.
    from app.core.auth import validate_session
    if payload.session_id and not await validate_session(payload.session_id):
        raise AuthError("Sesjonen er utløpt — logg inn på nytt")

    user = await get_user_by_id(payload.sub)
    if not user or not user.is_active:
        raise AuthError("Kontoen er deaktivert")

    access = await create_access_token(user, session_id=payload.session_id)
    response.set_cookie(
        "access_token", access, max_age=_ACCESS_MAX_AGE,
        httponly=True, secure=_cookie_secure(request), samesite="strict", path="/",
    )
    return {
        "ok": True,
        "access_token": access,
        "token_type": "bearer",
        "expires_in": _ACCESS_MAX_AGE,
    }


@router.post("/auth/logout")
async def auth_logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
) -> dict:
    """Revoke the current access token and drop its session."""
    token = _access_token_from(request)
    if token:
        await blacklist_token(token)
        payload = await decode_token(token)
        if payload and payload.session_id:
            await delete_session(payload.session_id)
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/auth/me")
async def auth_me(user: User = Depends(get_current_user)) -> dict:
    """The account, what it may reach, and the paths that stay open without write.

    The list travels rather than being restated in JavaScript. A client-side
    copy of it would be a second source of truth for the one question the
    middleware exists to answer, and the copy is the one that goes stale.
    """
    from app.core.features import available_to, views_for
    from app.web.middleware.write_guard import ALLOWED_WITHOUT_WRITE

    return {
        "user": _public_user(user),
        "write_exempt": sorted(ALLOWED_WITHOUT_WRITE),
        # What this account reaches, resolved server-side. The interface hides
        # what is not here rather than holding its own copy of the rules.
        "features": available_to(user),
        "views": views_for(user),
    }


@router.post("/auth/change-password")
async def auth_change_password(
    body: PasswordChange,
    user: User = Depends(get_current_user),
) -> dict:
    """Change your own password, confirming the current one first.

    The path is what the front-end calls. The ported branch served this as
    ``/auth/me/password``, which no client ever requested — the change-password
    dialog has been posting to ``/auth/change-password`` and getting a 404.
    """
    pw_hash = await get_password_hash(user.username)
    if not pw_hash or not verify_password(body.current_password, pw_hash):
        raise ValidationError("Nåværende passord er feil")

    await change_password(user.id, body.new_password)
    log_activity(
        "password_changed",
        detail=f"Bruker {user.username} endret passord",
        user=user.username,
    )
    return {"ok": True}


# ── User management (admin only) ─────────────────────────────────────────────


@router.get("/auth/users")
async def auth_list_users(user: User = Depends(require_role(Role.admin))) -> dict:
    users = await list_users()
    return {
        "users": [
            {
                **_public_user(u),
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat(),
                "last_login": u.last_login.isoformat() if u.last_login else None,
            }
            for u in users
        ]
    }


@router.post("/auth/users")
async def auth_create_user(
    body: UserCreate,
    admin: User = Depends(require_role(Role.admin)),
) -> dict:
    if await get_user_by_username(body.username):
        raise ConflictError(f"Brukernavnet '{body.username}' finnes allerede")

    user = await create_user(
        username=body.username,
        password=body.password,
        display_name=body.display_name,
        email=body.email,
        role=body.role,
    )
    logger.info(
        "User created by %s: %s (%s)", admin.username, user.username, user.role.value
    )
    log_activity(
        "user_created",
        detail=f"Bruker {user.username} opprettet (rolle: {user.role.value})",
        user=admin.username,
    )
    return {"ok": True, "user": _public_user(user)}


@router.put("/auth/users/{user_id}")
async def auth_update_user(
    user_id: str,
    body: UserUpdate,
    admin: User = Depends(require_role(Role.admin)),
) -> dict:
    target = await get_user_by_id(user_id)
    if not target:
        raise NotFoundError("Bruker ikke funnet")

    if body.role and body.role != Role.admin and target.role == Role.admin:
        await _guard_last_admin("Kan ikke nedgradere siste administrator")

    updated = await update_user(
        user_id,
        display_name=body.display_name,
        email=body.email,
        role=body.role,
        is_active=body.is_active,
    )

    # Handled separately from the fields above, and only when the caller
    # actually sent it. A capability that can be turned on by a request that
    # meant to rename someone is not one you can reason about afterwards.
    if body.can_write is not None:
        from app.core.rbac import set_can_write

        await set_can_write(user_id, body.can_write)
        log_activity(
            "write_granted" if body.can_write else "write_revoked",
            user=admin.username,
            detail=f"target={updated.username}",
        )
        updated = await get_user_by_id(user_id)

    if body.tenant_write is not None:
        from app.core.rbac import set_tenant_write

        await set_tenant_write(user_id, body.tenant_write)
        log_activity(
            "tenant_write_granted" if body.tenant_write else "tenant_write_revoked",
            user=admin.username,
            detail=f"target={updated.username}",
        )
        updated = await get_user_by_id(user_id)

    return {"ok": True, "user": {**_public_user(updated), "is_active": updated.is_active}}


@router.delete("/auth/users/{user_id}")
async def auth_delete_user(
    user_id: str,
    admin: User = Depends(require_role(Role.admin)),
) -> dict:
    if user_id == admin.id:
        raise ValidationError("Kan ikke slette deg selv")

    target = await get_user_by_id(user_id)
    if not target:
        raise NotFoundError("Bruker ikke funnet")
    if target.role == Role.admin:
        await _guard_last_admin("Kan ikke slette siste administrator")

    await delete_user(user_id)
    logger.info("User deleted by %s: %s", admin.username, target.username)
    log_activity(
        "user_deleted",
        detail=f"Bruker {target.username} slettet",
        user=admin.username,
    )
    return {"ok": True}


# ── Customer access (RBAC) ───────────────────────────────────────────────────


@router.get("/auth/users/{user_id}/customers")
async def auth_get_user_customers(
    user_id: str,
    admin: User = Depends(require_role(Role.admin)),
) -> dict:
    from app.core.rbac import get_user_customer_ids

    return {"customer_ids": await get_user_customer_ids(user_id)}


@router.put("/auth/users/{user_id}/customers")
async def auth_set_user_customers(
    user_id: str,
    request: Request,
    admin: User = Depends(require_role(Role.admin)),
) -> dict:
    from app.core.rbac import set_user_customers

    body = await request.json()
    customer_ids = (body or {}).get("customer_ids", [])
    await set_user_customers(user_id, customer_ids)
    log_activity(
        "rbac_updated",
        detail=f"Kundetilgang oppdatert for bruker {user_id}: {len(customer_ids)} kunder",
        user=admin.username,
    )
    return {"ok": True, "count": len(customer_ids)}


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _guard_last_admin(message: str) -> None:
    """Refuse an edit that would leave the install with no active admin."""
    users = await list_users()
    if sum(1 for u in users if u.role == Role.admin and u.is_active) <= 1:
        raise ValidationError(message)


async def _issue_tokens(user: User, request: Request) -> TokenResponse:
    """Create a session plus the access/refresh token pair bound to it.

    The session id is minted first so it can be embedded in both tokens, and
    the session record then stores the hash of the *actual* refresh token the
    client receives.
    """
    import uuid

    session_id = str(uuid.uuid4())
    access = await create_access_token(user, session_id=session_id)
    refresh = await create_refresh_token(user, session_id=session_id)
    await create_session(
        user_id=user.id,
        refresh_token=refresh,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:256],
        session_id=session_id,
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=_ACCESS_MAX_AGE,
    )


def _access_token_from(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return request.cookies.get("access_token")


async def _refresh_token_from(request: Request) -> str:
    """Read the refresh token from the JSON body or the cookie."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    token = (body or {}).get("refresh_token") or request.cookies.get("refresh_token")
    if not token:
        raise ValidationError("refresh_token er påkrevd")
    return token


def _public_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role.value,
        # Surfaced so the UI can show which accounts hold it. It is the one
        # capability here that reaches outside this tool.
        "can_write": bool(getattr(user, "can_write", False)),
        "tenant_write": bool(getattr(user, "tenant_write", False)),
    }
