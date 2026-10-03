"""Authentication routes — first-run setup, login, refresh, logout.

These paths are listed in ``app.web.middleware.auth._PUBLIC_PATHS`` (and
``_SETUP_PATHS`` for the two first-run endpoints), so they are reachable
without a token. Everything else in the app requires one.

Tokens are returned in the response body *and* set as HttpOnly cookies, so
both a scripted client and a browser front-end can use the same endpoints.
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, Request, Response

from app.core.activity_log import log_activity
from app.core.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    RefreshResult,
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
    rotate_refresh_token,
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
    CustomerAccessUpdate,
    LoginRequest,
    PasswordChange,
    ReauthenticateRequest,
    Role,
    SetupRequest,
    TokenResponse,
    User,
    UserCreate,
    UserUpdate,
)
from app.web.i18n import refusal
from app.web.middleware.auth import get_current_user, require_role
from app.web.transport import client_ip, is_local_quickstart, is_secure_transport

logger = logging.getLogger(__name__)
router = APIRouter()

_ACCESS_MAX_AGE = ACCESS_TOKEN_EXPIRE_MINUTES * 60
_REFRESH_MAX_AGE = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
_setup_lock = asyncio.Lock()


def _cookie_secure(request: Request) -> bool:
    """Require Secure cookies except for an explicitly local HTTP quick-start.

    Note this is a *different* question from the one ``credentials_may_cross``
    answers, and the predicates in ``app.web.transport`` are shared rather than
    duplicated so the difference stays visible. A request arriving from
    loopback with a public Host header is a local TLS terminator: its
    credentials may cross, and its cookies must still be marked Secure.
    """
    override = os.environ.get("SYBR_COOKIE_SECURE")
    if override is not None:
        return override == "1"
    if is_secure_transport(request):
        return True
    return not is_local_quickstart(request)


def _set_auth_cookies(
    response: Response,
    access: str,
    refresh: str,
    request: Request,
) -> None:
    """Attach both tokens as HttpOnly cookies.

    ``samesite="strict"`` is what stops a third-party page from driving the
    state-changing endpoints with the browser's cookie attached — the app has
    no separate CSRF token, so this is the CSRF defence.
    """
    _set_cookie(response, "access_token", access, _ACCESS_MAX_AGE, request)
    _set_cookie(response, "refresh_token", refresh, _REFRESH_MAX_AGE, request)


def _set_cookie(response: Response, name: str, value: str, max_age: int, request: Request) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="strict",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


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


@router.get("/auth/mfa")
async def mfa_status(user: User = Depends(get_current_user)) -> dict:
    from app.core import mfa

    return {"enabled": await mfa.enabled(user.id)}


async def _verify_current_password(user: User, password: str) -> None:
    verified = await authenticate(user.username, password)
    if verified is None or verified.id != user.id:
        raise refusal(AuthError, "err_auth_wrong_password")


@router.post("/auth/mfa/enroll")
async def mfa_enroll(body: ReauthenticateRequest, user: User = Depends(get_current_user)):
    from app.core import mfa

    await _verify_current_password(user, body.password)
    return await mfa.begin_enrollment(user.id, user.username)


@router.post("/auth/mfa/confirm")
async def mfa_confirm(
    body: ReauthenticateRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    from app.core import mfa
    from app.core.auth import delete_user_sessions

    await _verify_current_password(user, body.password)
    valid, codes = await mfa.verify(user.id, body.otp, enroll=True)
    if not valid:
        raise refusal(AuthError, "err_auth_mfa_setup_invalid")
    await delete_user_sessions(user.id)
    tokens = await _issue_tokens(user, request)
    payload = await decode_token(tokens.access_token)
    await mfa.mark_recent(payload.session_id)
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token, request)
    log_activity("mfa_enabled", user=user.username)
    return {"ok": True, "recovery_codes": codes}


@router.post("/auth/step-up")
async def auth_step_up(
    body: ReauthenticateRequest, request: Request, user: User = Depends(get_current_user)
):
    from app.core import mfa

    await _verify_current_password(user, body.password)
    if await mfa.enabled(user.id) and not (await mfa.verify(user.id, body.otp))[0]:
        raise refusal(AuthError, "err_auth_invalid_otp")
    session_id = getattr(request.state, "session_id", None)
    if not session_id:
        raise refusal(AuthError, "err_auth_session_unverifiable")
    await mfa.mark_recent(session_id)
    return {"ok": True, "expires_in": 300}


@router.post("/auth/mfa/disable")
async def mfa_disable(
    body: ReauthenticateRequest, response: Response, user: User = Depends(get_current_user)
):
    from app.core import mfa
    from app.core.auth import delete_user_sessions

    await _verify_current_password(user, body.password)
    if not (await mfa.verify(user.id, body.otp))[0]:
        raise refusal(AuthError, "err_auth_invalid_otp")
    from sqlmodel import delete

    from app.core.orm import get_session
    from app.models.user import UserMfa

    async with get_session() as session:
        await session.execute(delete(UserMfa).where(UserMfa.user_id == user.id))
        await session.commit()
    await delete_user_sessions(user.id)
    _clear_auth_cookies(response)
    log_activity("mfa_disabled", user=user.username)
    return {"ok": True}


@router.post("/auth/login")
async def auth_login(body: LoginRequest, request: Request, response: Response) -> dict:
    """Exchange username + password for an access and refresh token."""
    user = await authenticate(body.username, body.password)
    if not user:
        # Deliberately identical for "no such user", "wrong password" and
        # "account disabled" — anything more specific is an oracle.
        logger.info("Failed login for %r from %s", body.username, client_ip(request))
        raise refusal(AuthError, "err_auth_bad_credentials")

    from app.core import mfa

    mfa_enabled = await mfa.enabled(user.id)
    if mfa_enabled and not (await mfa.verify(user.id, body.otp))[0]:
        raise refusal(AuthError, "err_auth_bad_mfa_code")
    tokens = await _issue_tokens(user, request)
    if mfa_enabled:
        payload = await decode_token(tokens.access_token)
        await mfa.mark_recent(payload.session_id)
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token, request)
    return {"ok": True, "user": _public_user(user), **tokens.model_dump()}


@router.post("/auth/refresh")
async def auth_refresh(request: Request, response: Response) -> dict:
    """Trade the refresh token for a new access token and a new refresh token.

    Every refusal is a 401. A missing, expired, revoked or retired refresh
    token all mean "sign in again", and the browser reads any other status as
    "the server is unreachable".
    """
    token, from_body = await _refresh_token_from(request)
    payload = await decode_token(token)
    if not payload or payload.token_type != "refresh":
        raise refusal(AuthError, "err_auth_invalid_refresh")
    # A token that names no session can be neither rotated nor revoked.
    if not payload.session_id:
        raise refusal(AuthError, "err_auth_invalid_refresh")

    user = await get_user_by_id(payload.sub)
    if not user or not user.is_active:
        raise refusal(AuthError, "err_auth_account_disabled")
    from app.core import mfa

    if await mfa.enabled(user.id) and not await mfa.session_verified(user.id, payload.session_id):
        raise refusal(AuthError, "err_mfa_verification_required")

    replacement = await create_refresh_token(user, session_id=payload.session_id)
    outcome = await rotate_refresh_token(payload.session_id, user.id, token, replacement)
    if outcome is RefreshResult.REUSED:
        log_activity(
            "refresh_token_reused",
            detail="Et utgått refresh-token ble brukt på nytt; sesjonen er logget ut",
            user=user.username,
        )
    if outcome in (RefreshResult.INVALID, RefreshResult.REUSED):
        raise refusal(AuthError, "err_auth_session_expired")

    access = await create_access_token(user, session_id=payload.session_id)
    result = {
        "ok": True,
        "access_token": access,
        "token_type": "bearer",
        "expires_in": _ACCESS_MAX_AGE,
    }
    if outcome is RefreshResult.ROTATED:
        _set_auth_cookies(response, access, replacement, request)
        # Back through the channel it came in on. A cookie-only caller is the
        # browser, where the refresh token is HttpOnly precisely so that no
        # script on the page, injected or not, ever holds it.
        if from_body:
            result["refresh_token"] = replacement
    else:
        # A late duplicate: the request that rotated is delivering the new
        # refresh cookie, and this response must not overwrite it.
        _set_cookie(response, "access_token", access, _ACCESS_MAX_AGE, request)
    return result


@router.post("/auth/logout")
async def auth_logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
) -> dict:
    """Revoke the current access token and drop its session."""
    token = _access_token_from(request)
    if token:
        payload = await decode_token(token)
        if payload and payload.session_id:
            await delete_session(payload.session_id)
        await blacklist_token(token)
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/auth/me")
async def auth_me(user: User = Depends(get_current_user)) -> dict:
    """The account, what it may reach, and the paths that stay open without write.

    The list travels rather than being restated in JavaScript. A client-side
    copy of it would be a second source of truth for the one question the
    middleware exists to answer, and the copy is the one that goes stale.
    """
    from app.core import mfa, modules
    from app.core.features import available_to, views_for
    from app.web.middleware.write_guard import ALLOWED_WITHOUT_WRITE

    return {
        "user": _public_user(user),
        "mfa_required": mfa.required_for(user) and not await mfa.enabled(user.id),
        "write_exempt": sorted(ALLOWED_WITHOUT_WRITE),
        # What this account reaches, resolved server-side. The interface hides
        # what is not here rather than holding its own copy of the rules.
        "features": available_to(user),
        "views": views_for(user),
        "modules": sorted(modules.enabled()),
    }


@router.post("/auth/change-password")
async def auth_change_password(
    body: PasswordChange,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Change your own password, confirming the current one first.

    Every other session of the account is signed out; the one making the
    change stays. The path is what the front-end calls. The ported branch
    served this as ``/auth/me/password``, which no client ever requested.
    """
    pw_hash = await get_password_hash(user.username)
    from app.core.password_work import run_password_work

    if not pw_hash or not await run_password_work(verify_password, body.current_password, pw_hash):
        raise refusal(ValidationError, "err_auth_current_password_wrong")

    revoked = await change_password(
        user.id,
        body.new_password,
        keep_session_id=getattr(request.state, "session_id", None),
    )
    log_activity(
        "password_changed",
        detail=f"Bruker {user.username} endret passord; andre sesjoner logget ut: {revoked}",
        user=user.username,
    )
    return {"ok": True, "sessions_revoked": revoked}


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
        raise refusal(ConflictError, "err_auth_username_taken", username=body.username)

    user = await create_user(
        username=body.username,
        password=body.password,
        display_name=body.display_name,
        email=body.email,
        role=body.role,
        all_customers=body.all_customers,
    )
    logger.info("User created by %s: %s (%s)", admin.username, user.username, user.role.value)
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
        raise refusal(NotFoundError, "err_auth_user_not_found")

    if body.role and body.role != Role.admin and target.role == Role.admin:
        await _guard_last_admin(refusal(ValidationError, "err_auth_last_admin_demote"))

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
        raise refusal(ValidationError, "err_auth_cannot_delete_self")

    target = await get_user_by_id(user_id)
    if not target:
        raise refusal(NotFoundError, "err_auth_user_not_found")
    if target.role == Role.admin:
        await _guard_last_admin(refusal(ValidationError, "err_auth_last_admin_delete"))

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

    target = await get_user_by_id(user_id)
    if target is None:
        raise refusal(NotFoundError, "err_auth_user_not_found")
    return {
        "customer_ids": await get_user_customer_ids(user_id),
        "access_mode": "all" if target.all_customers else "scoped",
        "effective_access_mode": "all"
        if target.role == Role.admin or target.all_customers
        else "scoped",
        "is_admin": target.role == Role.admin,
    }


@router.put("/auth/users/{user_id}/customers")
async def auth_set_user_customers(
    user_id: str,
    body: CustomerAccessUpdate,
    admin: User = Depends(require_role(Role.admin)),
) -> dict:
    from app.core.rbac import set_user_customers

    if await get_user_by_id(user_id) is None:
        raise refusal(NotFoundError, "err_auth_user_not_found")
    customer_ids = list(dict.fromkeys(body.customer_ids))
    if any(not cid or len(cid) > 255 or any(ord(c) < 32 for c in cid) for cid in customer_ids):
        raise refusal(ValidationError, "err_auth_invalid_customer_id")
    if body.access_mode == "all" and customer_ids:
        raise refusal(ValidationError, "err_auth_choose_access_mode")
    await set_user_customers(user_id, customer_ids, all_customers=body.access_mode == "all")
    log_activity(
        "rbac_updated",
        detail=f"Kundetilgang for bruker {user_id}: {body.access_mode}, {len(customer_ids)} kunder",
        user=admin.username,
    )
    return {"ok": True, "count": len(customer_ids), "access_mode": body.access_mode}


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _guard_last_admin(refused: ValidationError) -> None:
    """Raise *refused* if the edit would leave the install with no active admin."""
    users = await list_users()
    if sum(1 for u in users if u.role == Role.admin and u.is_active) <= 1:
        raise refused


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
        ip_address=client_ip(request),
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


async def _refresh_token_from(request: Request) -> tuple[str, bool]:
    """Read the refresh token from the JSON body or the cookie.

    Returns the token and whether it came in the body.
    """
    try:
        body = await request.json()
    except Exception:
        # No body, or not JSON — the cookie is the other supported source.
        logger.debug("Refresh request carried no JSON body", exc_info=True)
        body = None
    token = body.get("refresh_token") if isinstance(body, dict) else None
    if token:
        from_body = True
    else:
        token, from_body = request.cookies.get("refresh_token"), False
    if not isinstance(token, str) or not token:
        # Signed out, not a malformed request: this is what every page load
        # before login sends, and a 400 here read as a lost connection.
        raise refusal(AuthError, "err_auth_not_signed_in")
    return token, from_body


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
