"""VPN management routes."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.validation import validate_identifier
from app.models.user import Role, User
from app.models.vpn import (
    AzureConnectWithToken,
    AzurePkceComplete,
    ProfileCreateRequest,
    ProfileImportRequest,
    ProfileUpdateRequest,
    VpnDisconnectRequest,
    VpnProfileRef,
)
from app.web.i18n import refusal, ui_t
from app.web.middleware.auth import get_current_user, require_feature, require_role

logger = logging.getLogger(__name__)
# The whole module is the 'vpn' feature (app/core/features.py); per-route
# floors below only ever raise it.
router = APIRouter(dependencies=[Depends(require_feature("vpn"))])


# ── Profiles ─────────────────────────────────────────────────────────────────


async def _may_use_profile(user: User, profile) -> bool:
    """Whether *user* may see or connect this VPN profile.

    Profiles carry customer_id (vpn_profiles table), but nothing consulted it,
    so a technician scoped to one customer could list every tunnel and bring
    one up into another customer's network. A profile with no customer is
    shared infrastructure and stays with unrestricted callers only.
    """
    from app.core.rbac import check_customer_access, get_accessible_customer_ids

    if profile is None:
        return False
    if profile.customer_id:
        return await check_customer_access(user, profile.customer_id)
    return await get_accessible_customer_ids(user) is None


@router.get("/vpn/profiles")
async def list_profiles(user: User = Depends(get_current_user)):
    from app.services.vpn_manager import list_profiles

    profiles = [p for p in await list_profiles() if await _may_use_profile(user, p)]
    return {
        "profiles": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "protocol": p.protocol.value,
                "full_tunnel": p.full_tunnel,
                "auto_connect": p.auto_connect,
                "kill_switch": p.kill_switch,
                "customer_id": p.customer_id,
                "created_at": p.created_at.isoformat(),
            }
            for p in profiles
        ]
    }


@router.get("/vpn/profiles/{profile_id}")
async def get_profile(profile_id: str, user: User = Depends(require_feature("vpn"))):
    """One profile's settings, for technicians and up.

    The config never carries secret material: passwords, PSKs, private keys
    and inline OpenVPN key blocks live in the encrypted store, and ``secrets``
    reports only whether each one is there.
    """
    from app.services.vpn_manager import describe_secrets, get_profile, stored_config

    profile = await get_profile(profile_id)
    if not profile:
        raise refusal(NotFoundError, "err_vpn_profile_not_found")
    if not await _may_use_profile(user, profile):
        raise refusal(ForbiddenError, "err_vpn_profile_forbidden")
    return {
        "profile": {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "protocol": profile.protocol.value,
            "config": stored_config(profile),
            "secrets": describe_secrets(profile),
            "full_tunnel": profile.full_tunnel,
            "auto_connect": profile.auto_connect,
            "kill_switch": profile.kill_switch,
            "customer_id": profile.customer_id,
            "created_at": profile.created_at.isoformat(),
            "updated_at": profile.updated_at.isoformat(),
        }
    }


@router.post("/vpn/profiles")
async def create_profile(
    body: ProfileCreateRequest,
    user: User = Depends(require_role(Role.technician)),
):
    if "customer_id" in body.model_fields_set and body.customer_id:
        from app.core.rbac import check_customer_access

        if not await check_customer_access(user, body.customer_id):
            raise refusal(ForbiddenError, "err_customer_access_denied")
    elif "customer_id" in body.model_fields_set and body.customer_id is None:
        from app.core.rbac import get_accessible_customer_ids

        if await get_accessible_customer_ids(user) is not None:
            raise refusal(ForbiddenError, "err_vpn_share_admin_only")
    else:
        from app.core.rbac import get_accessible_customer_ids

        if await get_accessible_customer_ids(user) is not None:
            raise refusal(ForbiddenError, "err_vpn_create_shared_admin_only")
    from app.services.vpn_manager import create_profile

    profile = await create_profile(
        name=body.name,
        protocol=body.protocol,
        config=body.config,
        description=body.description,
        full_tunnel=body.full_tunnel,
        customer_id=body.customer_id,
        created_by=user.id,
    )
    return {"ok": True, "profile": {"id": profile.id, "name": profile.name}}


@router.post("/vpn/profiles/import")
async def import_profile(
    body: ProfileImportRequest,
    user: User = Depends(require_role(Role.admin)),
):
    from app.services.vpn_manager import import_profile

    try:
        profile = await import_profile(
            name=body.name,
            file_content=body.file_content,
            file_type=body.file_type,
            created_by=user.id,
        )
        return {
            "ok": True,
            "profile": {"id": profile.id, "name": profile.name, "protocol": profile.protocol.value},
        }
    except Exception as e:
        raise ValidationError(str(e)) from e


@router.put("/vpn/profiles/{profile_id}")
async def update_profile(
    profile_id: str,
    body: ProfileUpdateRequest,
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.vpn_manager import get_profile, secret_labels, update_profile

    existing = await get_profile(profile_id)
    if not existing:
        raise refusal(NotFoundError, "err_vpn_profile_not_found")
    if not await _may_use_profile(user, existing):
        raise refusal(ForbiddenError, "err_vpn_profile_forbidden")
    if "customer_id" in body.model_fields_set and body.customer_id:
        from app.core.rbac import check_customer_access

        if not await check_customer_access(user, body.customer_id):
            raise refusal(ForbiddenError, "err_customer_access_denied")
    elif "customer_id" in body.model_fields_set:
        from app.core.rbac import get_accessible_customer_ids

        if await get_accessible_customer_ids(user) is not None:
            raise refusal(ForbiddenError, "err_vpn_share_admin_only")
    # exclude_unset, not exclude_none: an explicit customer_id of null is how
    # an administrator makes a profile shared.
    updates = body.model_dump(exclude_unset=True)
    profile, wiped = await update_profile(profile_id, **updates)
    if not profile:
        raise refusal(NotFoundError, "err_vpn_profile_not_found")
    if not wiped:
        return {"ok": True}
    cleared = secret_labels(wiped)
    return {
        "ok": True,
        "secrets_cleared": cleared,
        "message": ui_t("msg_vpn_secrets_cleared", request) + ": " + ", ".join(cleared),
    }


@router.delete("/vpn/profiles/{profile_id}")
async def delete_profile(
    profile_id: str,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.vpn_manager import delete_profile, get_profile

    await _refuse_if_system_holds_tunnels(user)
    profile = await get_profile(profile_id)
    if not profile:
        raise refusal(NotFoundError, "err_vpn_profile_not_found")
    if not await _may_use_profile(user, profile):
        raise refusal(ForbiddenError, "err_vpn_profile_forbidden")
    if not await delete_profile(profile_id):
        raise refusal(NotFoundError, "err_vpn_profile_not_found")
    return {"ok": True}


async def _refuse_if_system_holds_tunnels(user: User | None = None) -> None:
    """Refuse a manual VPN action while the collectors are using the link.

    A hard refusal rather than a hidden menu. Hiding it leaves the server
    willing, so an old browser tab or a direct call still tears down a tunnel
    something depends on — the guard would exist only where somebody looked for
    it. The message names the profiles *user* may see so it is actionable, and
    only counts the others, which belong to customers they cannot reach.
    """
    from app.services.vpn_manager import get_profile, system_held

    held = system_held()
    if not held:
        return
    names, hidden = [], 0
    for pid in held:
        profile = await get_profile(pid)
        if user is not None and (profile is None or not await _may_use_profile(user, profile)):
            hidden += 1
            continue
        names.append(getattr(profile, "name", None) or pid)
    # One key per shape of the sentence: a clause assembled here in Norwegian
    # would reach an English reader untranslated inside the English text.
    visible = ", ".join(names)
    if names and hidden == 1:
        raise refusal(ForbiddenError, "err_vpn_held_names_and_one", names=visible)
    if names and hidden:
        raise refusal(ForbiddenError, "err_vpn_held_names_and_many", names=visible, count=hidden)
    if names:
        raise refusal(ForbiddenError, "err_vpn_held_names", names=visible)
    if hidden == 1:
        raise refusal(ForbiddenError, "err_vpn_held_one")
    raise refusal(ForbiddenError, "err_vpn_held_many", count=hidden)


# ── Connect / Disconnect ────────────────────────────────────────────────────


def _translated(result: dict, request: Request) -> dict:
    """Swap a manager error for the caller's language when it names a key."""
    key = result.get("error_key")
    if key and not result.get("ok"):
        missing = result.get("missing_secrets") or []
        result["error"] = ui_t(key, request) + (": " + ", ".join(missing) if missing else "")
    return result


@router.post("/vpn/connect/{profile_id}")
async def vpn_connect(
    profile_id: str,
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    from app.core.activity_log import log_activity
    from app.services.vpn_manager import connect, get_profile

    await _refuse_if_system_holds_tunnels(user)
    profile = await get_profile(profile_id)
    if not profile:
        raise refusal(NotFoundError, "err_vpn_profile_not_found")
    if not await _may_use_profile(user, profile):
        raise refusal(ForbiddenError, "err_vpn_profile_forbidden")
    result = await connect(profile_id, owned_by=user.username)
    if result.get("ok"):
        # Opening a tunnel into a customer network is worth a record of who did it.
        log_activity(
            "vpn_connect",
            detail=f"Koblet til VPN-profil {profile.name} ({profile_id})",
            customer=profile.customer_id or "",
            user=user.username,
        )
    return _translated(result, request)


@router.post("/vpn/disconnect")
async def vpn_disconnect(
    body: VpnDisconnectRequest | None = None,
    user: User = Depends(require_role(Role.technician)),
):
    await _refuse_if_system_holds_tunnels(user)
    from app.services.vpn_manager import disconnect

    # The body is optional: none at all means the caller's active tunnel.
    profile_id = body.profile_id if body else None
    if profile_id:
        from app.services.vpn_manager import get_profile

        profile = await get_profile(profile_id)
        if not profile or not await _may_use_profile(user, profile):
            raise refusal(ForbiddenError, "err_vpn_profile_forbidden")
    else:
        from app.services.vpn_manager import get_status, list_profiles

        visible_ids = {
            profile.id for profile in await list_profiles() if await _may_use_profile(user, profile)
        }
        status = await get_status(visible_ids)
        profile_id = next(
            (
                connection["profile_id"]
                for connection in status["connections"]
                if connection["state"] in {"connected", "connecting", "error"}
            ),
            None,
        )
    return (
        await disconnect(profile_id) if profile_id else {"ok": True, "msg": "Already disconnected"}
    )


@router.post("/vpn/force-disconnect")
async def vpn_force_disconnect(user: User = Depends(require_role(Role.admin))):
    """Force disconnect — kill VPN processes and reset state."""
    # Guarded too, or it is simply the way around the guard on disconnect.
    await _refuse_if_system_holds_tunnels(user)
    import subprocess

    from app.services import vpn_manager

    # Try graceful first
    try:
        await vpn_manager.disconnect()
    except Exception as e:
        logger.debug("Graceful VPN disconnect failed, proceeding with force: %s", e)

    # Terminate only the processes this app started. `pkill -f openvpn`
    # matched on the whole command line and killed every openvpn on the host,
    # including tunnels belonging to other tools or other operators.
    from app.services.vpn_backends import openvpn as ovpn_backend

    for tag, proc in list(ovpn_backend._processes.items()):
        if proc.returncode is not None:
            continue
        try:
            proc.kill()
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (TimeoutError, ProcessLookupError, OSError) as e:
            logger.debug("Failed to kill OpenVPN process for %s: %s", tag, e)
    for tag in list(ovpn_backend._processes):
        ovpn_backend._processes.pop(tag, None)
        ovpn_backend._cleanup_tempfiles(tag)

    # Clean up all active interfaces
    for _pid, conn in list(vpn_manager._connections.items()):
        iface = conn.get("interface")
        if iface:
            try:
                validate_identifier(iface, "interface", max_length=15)
                await asyncio.to_thread(
                    subprocess.run,
                    ["ip", "link", "delete", iface],
                    capture_output=True,
                    timeout=5,
                )
            except Exception as e:
                logger.debug("Failed to delete interface %s: %s", iface, e)

    # Reset all connections
    vpn_manager._connections.clear()

    return {"ok": True, "msg": "Force disconnected"}


@router.get("/vpn/status")
async def vpn_status(user: User = Depends(get_current_user)):
    from app.services.vpn_manager import get_stats, get_status, list_profiles
    from app.services.vpn_privileges import vpn_capabilities

    visible_ids = {
        profile.id for profile in await list_profiles() if await _may_use_profile(user, profile)
    }
    status = await get_status(visible_ids)
    connected_id = next(
        (
            connection["profile_id"]
            for connection in status["connections"]
            if connection["state"] == "connected"
        ),
        None,
    )
    stats = await get_stats(connected_id) if connected_id else {}
    return {**status, "stats": stats, "capabilities": vpn_capabilities()}


@router.get("/vpn/capabilities")
async def vpn_control_capabilities(user: User = Depends(get_current_user)):
    """Describe which tunnel types this process is permitted to create."""
    from app.services.vpn_privileges import vpn_capabilities

    return vpn_capabilities()


# ── Azure VPN — PKCE + device code auth ──────────────────────────────────────


@router.post("/vpn/azure/try-silent")
async def azure_try_silent(
    body: VpnProfileRef,
    user: User = Depends(require_role(Role.technician)),
):
    """Try silent token refresh — if successful, connect without re-authentication."""
    from app.services.vpn_manager import get_profile, stored_config

    profile_id = body.profile_id

    profile = await get_profile(profile_id)
    if not profile:
        raise refusal(NotFoundError, "err_vpn_profile_not_found")
    if not await _may_use_profile(user, profile):
        raise refusal(ForbiddenError, "err_vpn_profile_forbidden")

    from app.services.vpn_privileges import unavailable_reason

    privilege_error = unavailable_reason(profile.protocol)
    if privilege_error:
        raise ConflictError(privilege_error)

    # Sign-in needs only the tenant and client ids, never the TLS key.
    from app.services.vpn_backends.azure import get_token_silent

    token = await get_token_silent(stored_config(profile))
    if token:
        return {"ok": True, "has_token": True, "access_token": token}

    return {"ok": False, "needs_login": True}


# ── Azure VPN — PKCE paste-back flow (headless compatible) ────────────────────


@router.post("/vpn/azure/pkce-start")
async def azure_pkce_start(
    body: VpnProfileRef,
    user: User = Depends(require_role(Role.technician)),
):
    """Generate PKCE auth URL — user opens it, logs in, pastes redirect URL back."""
    from app.services.vpn_manager import get_profile, stored_config

    profile_id = body.profile_id

    profile = await get_profile(profile_id)
    if not profile:
        raise refusal(NotFoundError, "err_vpn_profile_not_found")
    if not await _may_use_profile(user, profile):
        raise refusal(ForbiddenError, "err_vpn_profile_forbidden")

    from app.services.vpn_privileges import unavailable_reason

    privilege_error = unavailable_reason(profile.protocol)
    if privilege_error:
        raise ConflictError(privilege_error)

    redirect_uri = "http://localhost:2023"
    from app.services.vpn_backends.azure import get_auth_url

    result = get_auth_url(stored_config(profile), redirect_uri)
    return {"ok": True, "url": result["url"], "state": result["state"]}


@router.post("/vpn/azure/pkce-complete")
async def azure_pkce_complete(
    body: AzurePkceComplete,
    user: User = Depends(require_role(Role.technician)),
):
    """Complete PKCE flow — user pastes the redirect URL containing the auth code."""
    callback_url = body.callback_url

    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(callback_url)
    params = parse_qs(parsed.query)
    code = params.get("code", [""])[0]
    state = params.get("state", [""])[0]

    if not code or not state:
        raise refusal(ValidationError, "err_vpn_no_auth_code")

    from app.services.vpn_backends.azure import exchange_code

    result = await exchange_code(state, code)
    return result


# ── Device Code Flow routes (headless servers) ───────────────────────────────


@router.post("/vpn/azure/device-code")
async def azure_device_code_start(
    body: VpnProfileRef | None = None,
    profile_id: str = "",
    user: User = Depends(require_role(Role.technician)),
):
    """Start device code flow — returns a code the user enters at microsoft.com/devicelogin.

    The profile comes from the query or the body; the body may be left out.
    """
    profile_id = profile_id or (body.profile_id if body else "")

    from app.services.vpn_manager import get_profile, stored_config

    profile = await get_profile(profile_id)
    if not profile:
        raise refusal(NotFoundError, "err_vpn_profile_not_found")
    if not await _may_use_profile(user, profile):
        raise refusal(ForbiddenError, "err_vpn_profile_forbidden")

    from app.services.vpn_privileges import unavailable_reason

    privilege_error = unavailable_reason(profile.protocol)
    if privilege_error:
        raise ConflictError(privilege_error)

    from app.services.vpn_backends.azure import start_device_code_flow

    result = await start_device_code_flow(stored_config(profile))
    if result.get("ok"):
        result["profile_id"] = profile_id
        _device_code_owner[result["device_code"]] = str(user.id)
    return result


# device code -> id of the user who started the flow. The status answer
# carries the Entra access token, so only that user may read it.
_device_code_owner: dict[str, str] = {}


@router.get("/vpn/azure/device-code/status")
async def azure_device_code_status(device_code: str = "", user: User = Depends(get_current_user)):
    """Poll the status of a device code flow started by this user."""
    if not device_code:
        raise refusal(ValidationError, "err_vpn_device_code_required")
    if _device_code_owner.get(device_code) != str(user.id):
        raise refusal(NotFoundError, "err_vpn_unknown_device_code")
    from app.services.vpn_backends.azure import get_device_code_status

    status = get_device_code_status(device_code)
    if status.get("status") not in ("pending", None):
        _device_code_owner.pop(device_code, None)
    return status


@router.post("/vpn/azure/connect-with-token")
async def azure_connect_with_token(
    body: AzureConnectWithToken,
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Connect Azure VPN using an access token obtained from PKCE or device code flow.

    Opens a tunnel (and the backend ends any other openvpn3 session first), so
    it takes the same guard and goes through the same locked connect as
    /vpn/connect rather than writing the registry itself.
    """
    from app.core.activity_log import log_activity
    from app.services.vpn_manager import connect, get_profile

    await _refuse_if_system_holds_tunnels(user)
    profile_id = body.profile_id
    access_token = body.access_token

    if not access_token:
        raise refusal(ValidationError, "err_vpn_no_access_token")

    profile = await get_profile(profile_id)
    if not profile:
        raise refusal(NotFoundError, "err_vpn_profile_not_found")
    if not await _may_use_profile(user, profile):
        raise refusal(ForbiddenError, "err_vpn_profile_forbidden")
    if profile.protocol.value != "azure":
        raise refusal(ValidationError, "err_vpn_not_azure")

    from app.services.vpn_privileges import unavailable_reason

    privilege_error = unavailable_reason(profile.protocol)
    if privilege_error:
        raise ConflictError(privilege_error)

    result = await connect(profile_id, owned_by=user.username, access_token=access_token)
    if result.get("ok"):
        log_activity(
            "vpn_connect",
            detail=f"Koblet til VPN-profil {profile.name} ({profile_id})",
            customer=profile.customer_id or "",
            user=user.username,
        )
    return _translated(result, request)
