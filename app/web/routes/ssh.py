"""SSH key and host management routes."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile

from cryptography.exceptions import UnsupportedAlgorithm
from fastapi import APIRouter, Depends, Query, Request

from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.rbac import check_customer_access, get_accessible_customer_ids
from app.core.validation import validate_identifier, validate_login_name
from app.models.ssh import (
    BatchExecRequest,
    HostCreateRequest,
    HostSelection,
    HostUpdateRequest,
    KeyGenerateRequest,
    KeyImportRequest,
    KeyPushRequest,
    RdpLaunchRequest,
)
from app.models.user import Role, User
from app.web.i18n import keyed, refusal
from app.web.middleware.auth import (
    get_current_user,
    require_feature,
    require_host_access,
    require_module,
    require_role,
)

logger = logging.getLogger(__name__)
# The 'remote' module (app/core/modules.py) and feature (app/core/features.py);
# per-route floors below only ever raise them.
router = APIRouter(
    dependencies=[Depends(require_module("remote")), Depends(require_feature("remote"))]
)


# ── Tenancy helpers ──────────────────────────────────────────────────────────
# Hosts name their customer through ssh_hosts.customer_id rather than a
# {customer_id} path segment, so none of the per-customer plumbing reached
# this router. A host with no customer is estate-wide infrastructure and stays
# visible only to unrestricted callers — "unset" must not read as "unowned,
# therefore free".


async def _may_see_host(user: User, host) -> bool:
    from app.core.rbac import check_customer_access, get_accessible_customer_ids

    if host is None:
        return False
    if host.customer_id:
        return await check_customer_access(user, host.customer_id)
    return await get_accessible_customer_ids(user) is None


async def _scope_hosts(user: User, hosts: list) -> list:
    """Filter a host list down to the ones this caller may see."""
    from app.core.rbac import get_accessible_customer_ids

    allowed = await get_accessible_customer_ids(user)
    if allowed is None:
        return hosts
    return [h for h in hosts if h.customer_id and h.customer_id in allowed]


async def _assert_hosts_in_scope(user: User, host_ids: list[str]) -> None:
    """Refuse the whole request if any named host is out of scope.

    Whole-request rather than per-host filtering: silently dropping the hosts
    a caller may not touch would report a batch as successful while some of it
    never ran, which is worse than a clear refusal.
    """
    from app.services.ssh_manager import get_host

    for hid in host_ids or []:
        if not await _may_see_host(user, await get_host(hid)):
            logger.info("403 host-access: user=%s host=%s", user.username, hid)
            raise refusal(ForbiddenError, "err_ssh_hosts_forbidden")


# ── Key tenancy ──────────────────────────────────────────────────────────────
# A key is what the hub authenticates with, so whoever can attach a key to a
# host they control can reach every device that key is authorised on. A key
# bound to a customer is usable by anyone with access to that customer. A key
# with no customer is MSP-wide and likely authorised across the estate, so
# only callers who already have access to every customer may use it.


async def _is_unrestricted(user: User) -> bool:
    return await get_accessible_customer_ids(user) is None


async def _may_use_key(user: User, key) -> bool:
    if key is None:
        return False
    if key.customer_id:
        return await check_customer_access(user, key.customer_id)
    return await _is_unrestricted(user)


async def _visible_key(user: User, key_id: str):
    """The key, or 404/403. For routes that act on the key itself."""
    from app.services.ssh_manager import get_key

    key = await get_key(key_id)
    if key is None:
        raise refusal(NotFoundError, "err_ssh_key_not_found")
    if not await _may_use_key(user, key):
        logger.info("403 key-access: user=%s key=%s", user.username, key_id)
        raise refusal(ForbiddenError, "err_ssh_key_forbidden")
    return key


async def _attachable_key(user: User, key_id: str):
    """The key a host is about to authenticate with, or 400/403."""
    from app.services.ssh_manager import get_key

    key = await get_key(key_id)
    if key is None:
        raise refusal(ValidationError, "err_ssh_key_missing")
    if not await _may_use_key(user, key):
        logger.info("403 key-attach: user=%s key=%s", user.username, key_id)
        raise refusal(ForbiddenError, "err_ssh_key_forbidden")
    return key


async def _check_new_key_owner(user: User, customer_id: str | None) -> None:
    if customer_id:
        if not await check_customer_access(user, customer_id):
            raise refusal(ForbiddenError, "err_customer_access_denied")
    elif not await _is_unrestricted(user):
        # The caller could never use a key without a customer, so creating one
        # would only leave key material behind that someone else can use.
        raise refusal(ForbiddenError, "err_ssh_key_choose_customer")


def _key_summary(k) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "description": k.description,
        "key_type": k.key_type.value,
        "fingerprint": k.fingerprint,
        "tags": k.tags,
        "customer_id": k.customer_id,
        "created_at": k.created_at.isoformat(),
        "updated_at": k.updated_at.isoformat(),
    }


# ── Keys ─────────────────────────────────────────────────────────────────────


@router.get("/ssh/keys")
async def list_keys(user: User = Depends(require_role(Role.technician))):
    """The keys this caller may attach to a host. Nobody else needs the list."""
    from app.services.ssh_manager import list_keys

    keys = [k for k in await list_keys() if await _may_use_key(user, k)]
    return {"keys": [_key_summary(k) for k in keys]}


@router.get("/ssh/keys/{key_id}")
async def get_key(key_id: str, user: User = Depends(require_role(Role.technician))):
    from app.services.ssh_manager import get_key_deployments

    key = await _visible_key(user, key_id)
    deployments = await get_key_deployments(key_id)
    return {
        "key": {**_key_summary(key), "public_key": key.public_key},
        "deployments": [
            {"host_id": d.host_id, "deployed_at": d.deployed_at.isoformat()} for d in deployments
        ],
    }


@router.post("/ssh/keys")
async def create_key(
    body: KeyGenerateRequest,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import generate_key

    customer_id = body.customer_id or None
    await _check_new_key_owner(user, customer_id)
    key = await generate_key(
        name=body.name,
        key_type=body.key_type,
        description=body.description,
        tags=body.tags,
        created_by=user.id,
        customer_id=customer_id,
    )
    return {
        "ok": True,
        "key": {
            "id": key.id,
            "name": key.name,
            "key_type": key.key_type.value,
            "public_key": key.public_key,
            "fingerprint": key.fingerprint,
            "customer_id": key.customer_id,
        },
    }


@router.post("/ssh/keys/import")
async def import_key(
    body: KeyImportRequest,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import import_key

    customer_id = body.customer_id or None
    await _check_new_key_owner(user, customer_id)

    # Validate the key before attempting to save it
    try:
        from cryptography.hazmat.primitives.serialization import (
            load_pem_private_key,
            load_ssh_private_key,
        )

        pem_bytes = body.private_key_pem.encode("utf-8")
        # Try OpenSSH format first, then PEM
        try:
            load_ssh_private_key(pem_bytes, password=None)
        except (ValueError, TypeError):
            load_pem_private_key(pem_bytes, password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm) as e:
        # Log the underlying crypto exception for the operator's debug log
        # but never echo it to the client — those messages can leak parser
        # internals or even bytes from the rejected key.
        logger.warning("SSH key validation failed: %s", e)
        raise refusal(ValidationError, "err_ssh_key_invalid") from e
    except Exception as e:
        logger.warning("SSH key validation failed: %s", e)
        raise refusal(ValidationError, "err_ssh_key_unreadable") from e

    try:
        key = await import_key(
            name=body.name,
            private_key_pem=body.private_key_pem,
            description=body.description,
            tags=body.tags,
            created_by=user.id,
            customer_id=customer_id,
        )
        return {
            "ok": True,
            "key": {
                "id": key.id,
                "name": key.name,
                "key_type": key.key_type.value,
                "public_key": key.public_key,
                "fingerprint": key.fingerprint,
                "customer_id": key.customer_id,
            },
        }
    except Exception as e:
        logger.warning("SSH key import failed: %s", e)
        raise refusal(ValidationError, "err_ssh_key_import_failed") from e


@router.delete("/ssh/keys/{key_id}")
async def delete_key(
    key_id: str,
    # Admin-only: deleting a key unhooks it from every host that uses it,
    # across customers, and destroys the only copy of the private key.
    user: User = Depends(require_role(Role.admin)),
):
    from app.core.activity_log import log_activity
    from app.services.ssh_manager import delete_key

    deleted = await delete_key(key_id)
    if not deleted:
        raise refusal(NotFoundError, "err_ssh_key_not_found")
    log_activity("ssh_key_deleted", detail=f"Slettet SSH-nøkkel {key_id}", user=user.username)
    return {"ok": True}


@router.get("/ssh/keys/{key_id}/public")
async def export_public_key(key_id: str, user: User = Depends(require_role(Role.technician))):
    """Return the public key in OpenSSH format for copy/paste."""
    key = await _visible_key(user, key_id)
    return {"public_key": key.public_key}


# ── Key push / revoke ────────────────────────────────────────────────────────


@router.post("/ssh/keys/{key_id}/push")
async def push_key(
    key_id: str,
    body: KeyPushRequest,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import push_key

    await _visible_key(user, key_id)
    await _assert_hosts_in_scope(user, body.host_ids)
    try:
        results = await push_key(key_id, body.host_ids, body.use_sudo, user.id)
        return {"ok": True, "results": results}
    except ValueError as e:
        raise NotFoundError(str(e)) from e


@router.post("/ssh/keys/{key_id}/revoke")
async def revoke_key(
    key_id: str,
    body: KeyPushRequest,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import revoke_key

    await _visible_key(user, key_id)
    await _assert_hosts_in_scope(user, body.host_ids)
    try:
        results = await revoke_key(key_id, body.host_ids, body.use_sudo, user.id)
        return {"ok": True, "results": results}
    except ValueError as e:
        raise NotFoundError(str(e)) from e


# ── Hosts ────────────────────────────────────────────────────────────────────


@router.get("/ssh/hosts")
async def list_hosts(
    group: str = Query("", description="Filter by group name"),
    device_type: str = Query("", description="Filter by device type"),
    customer_id: str = Query("", description="Filter by customer ID"),
    user: User = Depends(get_current_user),
):
    from app.models.ssh import DeviceType
    from app.services.ssh_manager import list_hosts

    dt = DeviceType(device_type) if device_type else None
    hosts = await list_hosts(
        group_name=group or None,
        device_type=dt,
        customer_id=customer_id or None,
    )
    # The customer_id query parameter is a caller-supplied *filter*, not a
    # permission, so the result still has to be scoped to the caller's grants.
    hosts = await _scope_hosts(user, hosts)
    return {
        "hosts": [
            {
                "id": h.id,
                "label": h.label,
                "hostname": h.hostname,
                "port": h.port,
                "username": h.username,
                "group_name": h.group_name,
                "device_type": h.device_type.value,
                "auth_method": h.auth_method.value,
                "auth_key_id": h.auth_key_id,
                "customer_id": h.customer_id,
                "tags": h.tags,
                "notes": h.notes,
                "last_seen": h.last_seen.isoformat() if h.last_seen else None,
                "is_reachable": h.is_reachable,
            }
            for h in hosts
        ]
    }


@router.get("/ssh/hosts/{host_id}")
async def get_host(host_id: str, user: User = Depends(require_host_access())):
    from app.services.ssh_manager import get_host

    host = await get_host(host_id)
    if not host:
        raise refusal(NotFoundError, "err_host_not_found")
    return {
        "host": {
            "id": host.id,
            "label": host.label,
            "hostname": host.hostname,
            "port": host.port,
            "username": host.username,
            "group_name": host.group_name,
            "device_type": host.device_type.value,
            "auth_method": host.auth_method.value,
            "auth_key_id": host.auth_key_id,
            "customer_id": host.customer_id,
            "tags": host.tags,
            "notes": host.notes,
            "last_seen": host.last_seen.isoformat() if host.last_seen else None,
            "is_reachable": host.is_reachable,
            "created_at": host.created_at.isoformat(),
            "updated_at": host.updated_at.isoformat(),
        }
    }


@router.get("/ssh/hosts/{host_id}/password")
async def get_host_password(host_id: str, user: User = Depends(require_host_access(Role.admin))):
    """Return the stored password for a host.

    Admin-only and audited, matching /fortigate/credentials/{customer_id},
    which is the reference implementation for handing a stored credential back
    over the API. This route previously answered any technician for any host,
    and left no record that a device password had been read.

    The RDP flow does not need this: /rdp/launch resolves the password
    server-side from host_id, so the client never has to hold it.
    """
    from app.core.activity_log import log_activity
    from app.services.ssh_manager import _load_host_password

    password = _load_host_password(host_id) or ""
    log_activity(
        "ssh_password_viewed",
        detail=f"Leste lagret passord for host {host_id}",
        user=user.username,
    )
    return {"password": password}


@router.post("/ssh/hosts")
async def create_host(
    body: HostCreateRequest,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import create_host

    if body.customer_id and not await check_customer_access(user, body.customer_id):
        raise refusal(ForbiddenError, "err_customer_access_denied")
    auth_key_id = body.auth_key_id or None
    if auth_key_id:
        await _attachable_key(user, auth_key_id)
    host = await create_host(
        label=body.label,
        hostname=body.hostname,
        username=body.username,
        port=body.port,
        password=body.password,
        group_name=body.group_name,
        device_type=body.device_type,
        auth_method=body.auth_method,
        auth_key_id=auth_key_id,
        customer_id=body.customer_id,
        tags=body.tags,
        notes=body.notes,
        created_by=user.id,
    )
    return {"ok": True, "host": {"id": host.id, "label": host.label}}


@router.put("/ssh/hosts/{host_id}")
async def update_host(
    host_id: str,
    body: HostUpdateRequest,
    user: User = Depends(require_host_access(Role.technician)),
):
    """Edit a host.

    Repointing it (hostname, port or username) without re-entering the
    password deletes the stored one; see ssh_manager.update_host. That holds
    for admins too: one rule, and an admin who wants to keep the password can
    read it from the audited /password route and send it along.
    """
    from app.core.activity_log import log_activity
    from app.services.ssh_manager import (
        get_host,
        get_key,
        has_host_password,
        host_target_changed,
        update_host,
    )

    updates = body.model_dump(exclude_none=True)
    if updates.get("auth_key_id") == "":
        updates["auth_key_id"] = None  # an explicit "no key"
    existing = await get_host(host_id)

    # Moving a host to another customer is creating it there: the same check
    # create_host makes. require_host_access only vouched for the current one.
    if "customer_id" in updates:
        new_customer = updates["customer_id"] or None
        updates["customer_id"] = new_customer
        if new_customer != existing.customer_id:
            allowed = (
                await check_customer_access(user, new_customer)
                if new_customer
                else await _is_unrestricted(user)
            )
            if not allowed:
                raise refusal(ForbiddenError, "err_customer_access_denied")

    retargeted = host_target_changed(existing, updates)
    new_key_id = updates.get("auth_key_id")
    if new_key_id and new_key_id != existing.auth_key_id:
        await _attachable_key(user, new_key_id)
    elif retargeted and existing.auth_key_id:
        # Repointing a host that authenticates with a key aims that key at the
        # new address, which is attaching it all over again.
        key = await get_key(existing.auth_key_id)
        if key is not None and not await _may_use_key(user, key):
            logger.info("403 key-retarget: user=%s host=%s", user.username, host_id)
            raise refusal(ForbiddenError, "err_ssh_host_key_forbidden")

    password_cleared = retargeted and not updates.get("password") and has_host_password(host_id)
    host = await update_host(host_id, **updates)
    if not host:
        raise refusal(NotFoundError, "err_host_not_found")

    if retargeted:
        detail = (
            f"Endret {host.label} fra {existing.username}@{existing.hostname}:{existing.port}"
            f" til {host.username}@{host.hostname}:{host.port}"
        )
        if password_cleared:
            detail += "; lagret passord slettet"
        elif updates.get("password"):
            detail += "; nytt passord lagret"
        log_activity(
            "ssh_host_retargeted",
            detail=detail,
            customer=host.customer_id or "",
            user=user.username,
        )
    return {
        "ok": True,
        "host": {"id": host.id, "label": host.label},
        "password_cleared": password_cleared,
    }


@router.delete("/ssh/hosts/{host_id}")
async def delete_host(
    host_id: str,
    user: User = Depends(require_host_access(Role.technician)),
):
    from app.services.ssh_manager import delete_host

    deleted = await delete_host(host_id)
    if not deleted:
        raise refusal(NotFoundError, "err_host_not_found")
    return {"ok": True}


@router.post("/ssh/hosts/{host_id}/test")
async def test_host(
    host_id: str,
    request: Request,
    user: User = Depends(require_host_access(Role.technician)),
):
    from app.services.ssh_manager import _connect_to_host
    from app.services.ssh_manager import get_host as _get

    host = await _get(host_id)
    if not host:
        raise refusal(NotFoundError, "err_host_not_found")
    try:
        async with await _connect_to_host(host) as session:
            out = await session.exec("echo ok", timeout=10)
            return {"ok": out.exit_code == 0, "output": out.stdout}
    except Exception as e:
        logger.warning("SSH connection test failed for host %s: %s", host_id, e)
        return {"ok": False, **keyed("error", "err_ssh_test_failed", request)}


# ── Batch execution ──────────────────────────────────────────────────────────


@router.post("/ssh/exec")
async def exec_command(
    body: BatchExecRequest,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import batch_exec

    await _assert_hosts_in_scope(user, body.host_ids)
    results = await batch_exec(body.host_ids, body.command, user.id)
    return {
        "results": [
            {
                "host_id": r.host_id,
                "host_label": r.host_label,
                "hostname": r.hostname,
                "exit_code": r.exit_code,
                "stdout": r.stdout,
                "stderr": r.stderr,
                "error": r.error,
            }
            for r in results
        ]
    }


# ── Health check ─────────────────────────────────────────────────────────────


@router.post("/ssh/hosts/health")
async def health_check(
    body: HostSelection,
    # Opens a real SSH connection to every host in scope — that is an action on
    # customer infrastructure, not a read, so it sits at the same floor as the
    # other host operations rather than at viewer.
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import health_check, list_hosts

    host_ids = body.host_ids
    if not host_ids:
        # Omitting host_ids fans an SSH connection out across the estate, so
        # the default set is the caller's hosts, not every host on the box.
        hosts = await _scope_hosts(user, await list_hosts())
        host_ids = [h.id for h in hosts]
    else:
        await _assert_hosts_in_scope(user, host_ids)
    results = await health_check(host_ids)
    return {"results": results}


# ── SSH config generation ────────────────────────────────────────────────────


@router.post("/ssh/config/generate")
async def gen_ssh_config(body: HostSelection, user: User = Depends(require_role(Role.technician))):
    from app.services.ssh_manager import generate_ssh_config, list_hosts

    host_ids = body.host_ids
    if host_ids:
        await _assert_hosts_in_scope(user, host_ids)
    else:
        # Otherwise this exports the whole estate as a ready-made SSH config.
        host_ids = [h.id for h in await _scope_hosts(user, await list_hosts())]
    config = await generate_ssh_config(host_ids)
    return {"config": config}


# ── Audit log ────────────────────────────────────────────────────────────────


@router.get("/ssh/audit-log")
async def ssh_audit_log(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_role(Role.admin)),
):
    """Every SSH action taken from this hub, across all customers.

    Admin-only rather than scoped: ``ssh_audit_log`` rows record host_label and
    hostname but neither host_id nor customer_id, so there is nothing reliable
    to filter on. Restricting the whole log is the fail-closed reading; giving
    technicians a per-customer view needs the customer stamped on the row.
    """
    from app.services.ssh_manager import get_audit_log

    entries = await get_audit_log(limit, offset)
    return {
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "action": e.action,
                "key_name": e.key_name,
                "key_fingerprint": e.key_fingerprint,
                "host_label": e.host_label,
                "hostname": e.hostname,
                "port": e.port,
                "success": e.success,
                "detail": e.detail,
            }
            for e in entries
        ]
    }


# ── RDP ──────────────────────────────────────────────────────────────────────


@router.post("/rdp/launch")
async def rdp_launch(
    body: RdpLaunchRequest,
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Launch an RDP client on the hub's desktop for a registered host.

    xfreerdp is the supported client (FreeRDP 3, then 2); macOS and Windows
    fall back to their built-in clients. There is no Remmina path: its profile
    is an INI file, so a newline in any field becomes a new key, including the
    pre/post-connection commands Remmina runs.

    The password is resolved server-side and given to xfreerdp on stdin
    (/from-stdin:force), never as /p: on the command line, where any local
    account could read it from /proc while the session is open.
    """
    host_id = (body.host_id or "").strip()
    if not host_id:
        raise refusal(ValidationError, "err_host_choose_registered")

    from app.services.ssh_manager import _load_host_password, get_host

    host_record = await get_host(host_id)
    if not await _may_see_host(user, host_record):
        logger.info("403 host-access: user=%s host=%s (rdp)", user.username, host_id)
        raise refusal(ForbiddenError, "err_host_forbidden")

    host = host_record.hostname
    username = validate_login_name(
        (body.username or "").strip() or host_record.username, "username"
    )
    port = body.port
    if not 1 <= port <= 65535:
        raise refusal(ValidationError, "err_rdp_invalid_port")
    domain = (body.domain or "").strip()
    if domain:
        validate_identifier(domain, "domain", max_length=255)

    # The stored password belongs to the stored account. Logging in as someone
    # else gets only a password the caller typed.
    password = body.password or ""
    if not password and username == host_record.username:
        password = _load_host_password(host_id) or ""
    if any(ch in password for ch in "\r\n\x00"):
        # Read line by line from stdin; anything after a newline would be lost.
        raise refusal(ValidationError, "err_ssh_password_line_breaks")

    # Ensure GUI apps can find the display (Wayland/X11)
    gui_env = os.environ.copy()
    for var in (
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "XDG_SESSION_TYPE",
        "DBUS_SESSION_BUS_ADDRESS",
    ):
        if var in os.environ:
            gui_env[var] = os.environ[var]

    def _launch_xfreerdp(binary: str, cert_flag: str) -> None:
        """Start xfreerdp in its own session, with the password on stdin."""
        cmd = [
            binary,
            f"/v:{host}:{port}",
            f"/u:{username}",
            "/dynamic-resolution",
            "+clipboard",
            cert_flag,
        ]
        if domain:
            cmd.append(f"/d:{domain}")
        if password:
            # "force" reads the password before connecting rather than when
            # the server asks, so the pipe can be written and closed now.
            cmd.append("/from-stdin:force")
        proc = subprocess.Popen(
            ["setsid", *cmd],
            stdin=subprocess.PIPE if password else subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=gui_env,
            start_new_session=True,
        )
        if password:
            try:
                proc.stdin.write(password.encode("utf-8") + b"\n")
            except BrokenPipeError:
                logger.warning("xfreerdp exited before reading the password")
            finally:
                proc.stdin.close()

    xfree3 = shutil.which("xfreerdp3")
    if xfree3:
        _launch_xfreerdp(xfree3, "/cert:tofu")
        return {"ok": True, "client": "xfreerdp3"}

    xfree = shutil.which("xfreerdp")
    if xfree:
        # /cert-ignore accepts any server certificate, so this path is open to
        # a man in the middle; FreeRDP 3 above pins on first use instead.
        _launch_xfreerdp(xfree, "/cert-ignore")
        return {"ok": True, "client": "xfreerdp"}

    # macOS
    if sys.platform == "darwin":
        # Generate .rdp file and open it
        # delete=False: `open` hands the file to Remote Desktop, which reads it
        # after this handler has returned.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rdp", delete=False) as rdp_file:
            rdp_file.write(f"full address:s:{host}:{port}\nusername:s:{username}\n")
        subprocess.Popen(["open", rdp_file.name])
        return {"ok": True, "client": "Microsoft Remote Desktop"}

    # Windows
    if sys.platform == "win32":
        subprocess.Popen(["mstsc", f"/v:{host}:{port}"])
        return {"ok": True, "client": "mstsc"}

    return {"ok": False, **keyed("error", "err_rdp_no_client", request)}
