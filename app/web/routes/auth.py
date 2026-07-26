"""Authentication routes — first-run setup, login, refresh, logout.

These paths are listed in ``app.web.middleware.auth._PUBLIC_PATHS`` (and
``_SETUP_PATHS`` for the two first-run endpoints), so they are reachable
without a token. Everything else in the app requires one.

Tokens are returned in the response body *and* set as HttpOnly cookies, so
both a scripted client and a browser front-end can use the same endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response

from app.core.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    authenticate,
    blacklist_token,
    create_access_token,
    create_refresh_token,
    create_session,
    create_user,
    decode_token,
    delete_session,
    get_user_by_id,
    get_user_count,
)
from app.core.exceptions import AuthError, ConflictError, ValidationError
from app.models.user import (
    LoginRequest,
    Role,
    SetupRequest,
    TokenResponse,
    User,
)
from app.web.middleware.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

_ACCESS_MAX_AGE = ACCESS_TOKEN_EXPIRE_MINUTES * 60
_REFRESH_MAX_AGE = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    """Attach both tokens as HttpOnly cookies.

    ``samesite="strict"`` is what stops a third-party page from driving the
    state-changing endpoints with the browser's cookie attached — the app has
    no separate CSRF token, so this is the CSRF defence.
    """
    common = {"httponly": True, "secure": True, "samesite": "strict", "path": "/"}
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
    if await get_user_count() > 0:
        raise ConflictError("Oppsett er allerede fullført")

    user = await create_user(
        username=body.username,
        password=body.password,
        display_name=body.display_name,
        role=Role.admin,
        email=body.email,
    )

    # Close the first-run window immediately for this process, so no request
    # can slip through the setup path between here and the next DB read.
    from app.web.middleware.auth import users_exist
    await users_exist()

    tokens = await _issue_tokens(user, request)
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
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
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
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
        httponly=True, secure=True, samesite="strict", path="/",
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
        blacklist_token(token)
        payload = await decode_token(token)
        if payload and payload.session_id:
            await delete_session(payload.session_id)
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/auth/me")
async def auth_me(user: User = Depends(get_current_user)) -> dict:
    return {"user": _public_user(user)}


# ── Helpers ──────────────────────────────────────────────────────────────────


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
    }
