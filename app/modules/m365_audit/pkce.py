import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.exceptions import ToolkitError
from app.core.messages import MESSAGES

logger = logging.getLogger(__name__)

# The same Microsoft Graph PowerShell public client used by setup_helper.ps1.
# Its registered nativeclient redirect supports manual PKCE sign-in.
BOOTSTRAP_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
DEFAULT_SCOPE = (
    "Application.ReadWrite.All AppRoleAssignment.ReadWrite.All "
    "RoleManagement.ReadWrite.Directory Organization.Read.All openid profile offline_access"
)


@dataclass
class _PkceAttempt:
    verifier: str
    expires_at: float
    owner_user_id: str | None
    busy: bool = False


class PkceSetupError(ToolkitError):
    error_type = "integration_error"

    def __init__(self, key: str, status: int, *, restart_required: bool, **params: str):
        super().__init__(MESSAGES[key][0].format(**params), message_key=key, params=params)
        self.status_code = status
        self.restart_required = restart_required

    def to_dict(self) -> dict:
        return {**super().to_dict(), "restart_required": self.restart_required}


_pkce_store: dict[str, _PkceAttempt] = {}


def generate_pkce_challenge(owner_user_id: str | None = None) -> tuple[str, str, str]:
    """Generates (state, code_verifier, code_challenge)"""
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode("ascii").rstrip("=")

    now = time.time()
    for old_state, entry in list(_pkce_store.items()):
        if entry.expires_at <= now and not entry.busy:
            del _pkce_store[old_state]
    _pkce_store[state] = _PkceAttempt(code_verifier, now + 600, owner_user_id)
    return state, code_verifier, code_challenge


async def exchange_code_for_token(
    code: str, state: str, redirect_uri: str, *, owner_user_id: str | None = None
) -> str:
    """Exchanges the authorization code for an access token."""
    entry = _pkce_store.get(state)
    if not entry or entry.owner_user_id != owner_user_id:
        raise PkceSetupError("err_setup_pkce_expired", 400, restart_required=True)
    if entry.busy:
        raise PkceSetupError("err_setup_pkce_busy", 409, restart_required=False)
    if entry.expires_at <= time.time():
        del _pkce_store[state]
        raise PkceSetupError("err_setup_pkce_expired", 400, restart_required=True)
    entry.busy = True
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                    data={
                        "client_id": BOOTSTRAP_CLIENT_ID,
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "code_verifier": entry.verifier,
                        "scope": DEFAULT_SCOPE,
                    },
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # DNS/TCP/TLS never established a connection: the request was
                # not delivered. Keep the verifier for an explicit retry.
                raise PkceSetupError("err_setup_pkce_connect", 503, restart_required=False) from exc
            except BaseException:
                # Once delivery is uncertain, including cancellation, the
                # one-use code must not be sent again automatically.
                _pkce_store.pop(state, None)
                raise
        _pkce_store.pop(state, None)
        if not resp.is_success:
            try:
                codes = resp.json().get("error_codes", [])
                diagnostic = (
                    ", ".join(f"AADSTS{v}" for v in codes[:3] if isinstance(v, int))
                    if isinstance(codes, list)
                    else ""
                )
            except (ValueError, AttributeError):
                diagnostic = ""
            raise PkceSetupError(
                "err_setup_pkce_rejected",
                400,
                restart_required=True,
                code=diagnostic or f"HTTP {resp.status_code}",
            )
        try:
            token = resp.json()["access_token"]
            if not isinstance(token, str) or not token:
                raise ValueError("Missing access token")
            return token
        except (ValueError, KeyError, TypeError) as exc:
            raise PkceSetupError(
                "err_setup_pkce_rejected",
                502,
                restart_required=True,
                code="invalid token response",
            ) from exc
    except httpx.RequestError as exc:
        raise PkceSetupError("err_setup_pkce_delivery", 502, restart_required=True) from exc
    finally:
        entry.busy = False


def registration_failure() -> PkceSetupError:
    return PkceSetupError("err_setup_pkce_registration", 502, restart_required=True)


async def create_sybr_app(
    access_token: str,
    *,
    allowed_customer_ids: set[str] | None = None,
    renew_config: dict | None = None,
) -> dict[str, Any]:
    from app.modules.m365_audit.app_setup import provision_app

    return await provision_app(
        access_token, allowed_customer_ids=allowed_customer_ids, renew_config=renew_config
    )
