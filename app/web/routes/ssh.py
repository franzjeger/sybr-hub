"""SSH key and host management routes."""

from __future__ import annotations

import logging
import os

from cryptography.exceptions import UnsupportedAlgorithm
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.ssh import (
    BatchExecRequest,
    HostCreateRequest,
    HostUpdateRequest,
    KeyGenerateRequest,
    KeyImportRequest,
    KeyPushRequest,
)
from app.models.user import Role, User
from app.web.middleware.auth import get_current_user, require_host_access, require_role

logger = logging.getLogger(__name__)
router = APIRouter()


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
            raise AuthError("Du har ikke tilgang til en eller flere av disse hostene")


# ── Keys ─────────────────────────────────────────────────────────────────────

@router.get("/ssh/keys")
async def list_keys(user: User = Depends(get_current_user)):
    from app.services.ssh_manager import list_keys
    keys = await list_keys()
    return {
        "keys": [
            {
                "id": k.id, "name": k.name, "description": k.description,
                "key_type": k.key_type.value, "fingerprint": k.fingerprint,
                "tags": k.tags,
                "created_at": k.created_at.isoformat(),
                "updated_at": k.updated_at.isoformat(),
            }
            for k in keys
        ]
    }


@router.get("/ssh/keys/{key_id}")
async def get_key(key_id: str, user: User = Depends(get_current_user)):
    from app.services.ssh_manager import get_key, get_key_deployments
    key = await get_key(key_id)
    if not key:
        raise NotFoundError("Nøkkel ikke funnet")
    deployments = await get_key_deployments(key_id)
    return {
        "key": {
            "id": key.id, "name": key.name, "description": key.description,
            "key_type": key.key_type.value, "public_key": key.public_key,
            "fingerprint": key.fingerprint, "tags": key.tags,
            "created_at": key.created_at.isoformat(),
            "updated_at": key.updated_at.isoformat(),
        },
        "deployments": [
            {"host_id": d.host_id, "deployed_at": d.deployed_at.isoformat()}
            for d in deployments
        ],
    }


@router.post("/ssh/keys")
async def create_key(
    body: KeyGenerateRequest,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import generate_key
    key = await generate_key(
        name=body.name, key_type=body.key_type,
        description=body.description, tags=body.tags,
        created_by=user.id,
    )
    return {
        "ok": True,
        "key": {
            "id": key.id, "name": key.name, "key_type": key.key_type.value,
            "public_key": key.public_key, "fingerprint": key.fingerprint,
        },
    }


@router.post("/ssh/keys/import")
async def import_key(
    body: KeyImportRequest,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import import_key

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
        raise ValidationError(
            "Ugyldig SSH-nøkkel — sjekk at den er i PEM- eller OpenSSH-format og uten passord."
        )
    except Exception as e:
        logger.warning("SSH key validation failed: %s", e)
        raise ValidationError(
            "Nøkkelen kunne ikke leses. Sjekk at den er i PEM- eller OpenSSH-format."
        )

    try:
        key = await import_key(
            name=body.name, private_key_pem=body.private_key_pem,
            description=body.description, tags=body.tags,
            created_by=user.id,
        )
        return {
            "ok": True,
            "key": {
                "id": key.id, "name": key.name, "key_type": key.key_type.value,
                "public_key": key.public_key, "fingerprint": key.fingerprint,
            },
        }
    except Exception as e:
        logger.warning("SSH key import failed: %s", e)
        raise ValidationError("Importering av nøkkel feilet")


@router.delete("/ssh/keys/{key_id}")
async def delete_key(
    key_id: str,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import delete_key
    deleted = await delete_key(key_id)
    if not deleted:
        raise NotFoundError("Nøkkel ikke funnet")
    return {"ok": True}


@router.get("/ssh/keys/{key_id}/public")
async def export_public_key(key_id: str, user: User = Depends(get_current_user)):
    """Return the public key in OpenSSH format for copy/paste."""
    from app.services.ssh_manager import get_key
    key = await get_key(key_id)
    if not key:
        raise NotFoundError("Nøkkel ikke funnet")
    return {"public_key": key.public_key}


# ── Key push / revoke ────────────────────────────────────────────────────────

@router.post("/ssh/keys/{key_id}/push")
async def push_key(
    key_id: str,
    body: KeyPushRequest,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import push_key
    await _assert_hosts_in_scope(user, body.host_ids)
    try:
        results = await push_key(key_id, body.host_ids, body.use_sudo, user.id)
        return {"ok": True, "results": results}
    except ValueError as e:
        raise NotFoundError(str(e))


@router.post("/ssh/keys/{key_id}/revoke")
async def revoke_key(
    key_id: str,
    body: KeyPushRequest,
    user: User = Depends(require_role(Role.technician)),
):
    from app.services.ssh_manager import revoke_key
    await _assert_hosts_in_scope(user, body.host_ids)
    try:
        results = await revoke_key(key_id, body.host_ids, body.use_sudo, user.id)
        return {"ok": True, "results": results}
    except ValueError as e:
        raise NotFoundError(str(e))


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
                "id": h.id, "label": h.label, "hostname": h.hostname,
                "port": h.port, "username": h.username,
                "group_name": h.group_name,
                "device_type": h.device_type.value,
                "auth_method": h.auth_method.value,
                "auth_key_id": h.auth_key_id,
                "customer_id": h.customer_id,
                "tags": h.tags, "notes": h.notes,
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
        raise NotFoundError("Host ikke funnet")
    return {
        "host": {
            "id": host.id, "label": host.label, "hostname": host.hostname,
            "port": host.port, "username": host.username,
            "group_name": host.group_name,
            "device_type": host.device_type.value,
            "auth_method": host.auth_method.value,
            "auth_key_id": host.auth_key_id,
            "customer_id": host.customer_id,
            "tags": host.tags, "notes": host.notes,
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
    from app.core.rbac import check_customer_access

    from app.services.ssh_manager import create_host
    if body.customer_id and not await check_customer_access(user, body.customer_id):
        raise AuthError("Du har ikke tilgang til denne kunden")
    host = await create_host(
        label=body.label, hostname=body.hostname, username=body.username,
        port=body.port, password=body.password,
        group_name=body.group_name, device_type=body.device_type,
        auth_method=body.auth_method, auth_key_id=body.auth_key_id,
        customer_id=body.customer_id, tags=body.tags, notes=body.notes,
        created_by=user.id,
    )
    return {"ok": True, "host": {"id": host.id, "label": host.label}}


@router.put("/ssh/hosts/{host_id}")
async def update_host(
    host_id: str,
    body: HostUpdateRequest,
    user: User = Depends(require_host_access(Role.technician)),
):
    from app.services.ssh_manager import update_host
    updates = body.model_dump(exclude_none=True)
    host = await update_host(host_id, **updates)
    if not host:
        raise NotFoundError("Host ikke funnet")
    return {"ok": True, "host": {"id": host.id, "label": host.label}}


@router.delete("/ssh/hosts/{host_id}")
async def delete_host(
    host_id: str,
    user: User = Depends(require_host_access(Role.technician)),
):
    from app.services.ssh_manager import delete_host
    deleted = await delete_host(host_id)
    if not deleted:
        raise NotFoundError("Host ikke funnet")
    return {"ok": True}


@router.post("/ssh/hosts/{host_id}/test")
async def test_host(host_id: str, user: User = Depends(require_host_access(Role.technician))):
    from app.services.ssh_manager import _connect_to_host
    from app.services.ssh_manager import get_host as _get
    host = await _get(host_id)
    if not host:
        raise NotFoundError("Host ikke funnet")
    try:
        async with await _connect_to_host(host) as session:
            out = await session.exec("echo ok", timeout=10)
            return {"ok": out.exit_code == 0, "output": out.stdout}
    except Exception as e:
        logger.warning("SSH connection test failed for host %s: %s", host_id, e)
        return {"ok": False, "error": "Tilkoblingstest feilet"}


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
                "host_id": r.host_id, "host_label": r.host_label,
                "hostname": r.hostname, "exit_code": r.exit_code,
                "stdout": r.stdout, "stderr": r.stderr,
                "error": r.error,
            }
            for r in results
        ]
    }


# ── Health check ─────────────────────────────────────────────────────────────

@router.post("/ssh/hosts/health")
async def health_check(request: Request, user: User = Depends(get_current_user)):
    from app.services.ssh_manager import health_check, list_hosts
    body = await request.json()
    host_ids = body.get("host_ids")
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
async def gen_ssh_config(request: Request, user: User = Depends(get_current_user)):
    from app.services.ssh_manager import generate_ssh_config, list_hosts
    body = await request.json()
    host_ids = body.get("host_ids")
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
                "id": e.id, "timestamp": e.timestamp.isoformat(),
                "action": e.action, "key_name": e.key_name,
                "key_fingerprint": e.key_fingerprint,
                "host_label": e.host_label, "hostname": e.hostname,
                "port": e.port, "success": e.success,
                "detail": e.detail,
            }
            for e in entries
        ]
    }


# ── RDP ──────────────────────────────────────────────────────────────────────

@router.post("/rdp/launch")
async def rdp_launch(request: Request, user: User = Depends(require_role(Role.technician))):
    """Launch an RDP client to connect to a remote host.

    Tries in order: Remmina, xfreerdp, mstsc (Windows), open (macOS).
    Falls back to generating a .rdp file for download.
    """
    import shutil
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    body = await request.json()
    host = body.get("host", "").strip()
    username = body.get("username", "").strip()
    port = body.get("port", 3389)
    domain = body.get("domain", "")
    host_id = body.get("host_id", "")

    if not host:
        raise ValidationError("Host er påkrevd")

    # Load password from host record if host_id provided
    password = body.get("password", "")
    if host_id and not password:
        from app.services.ssh_manager import _load_host_password, get_host
        # Resolving a stored credential from an id is exactly the operation
        # /ssh/hosts/{id}/password performs, so it carries the same check.
        if not await _may_see_host(user, await get_host(host_id)):
            logger.info("403 host-access: user=%s host=%s (rdp)", user.username, host_id)
            raise AuthError("Du har ikke tilgang til denne hosten")
        password = _load_host_password(host_id) or ""

    # Ensure GUI apps can find the display (Wayland/X11)
    gui_env = os.environ.copy()
    for var in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE", "DBUS_SESSION_BUS_ADDRESS"):
        if var in os.environ:
            gui_env[var] = os.environ[var]

    def _launch_gui(cmd):
        """Launch a GUI app in its own session so it gets proper display access."""
        subprocess.Popen(
            ["setsid"] + cmd,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=gui_env, start_new_session=True,
        )

    # xfreerdp3 preferred, Remmina as fallback
    xfree3 = shutil.which("xfreerdp3")
    if xfree3:
        cmd = [xfree3, f"/v:{host}:{port}", f"/u:{username}",
               "/dynamic-resolution", "+clipboard", "/cert:tofu"]
        if domain:
            cmd.append(f"/d:{domain}")
        if password:
            cmd.append(f"/p:{password}")
        _launch_gui(cmd)
        return {"ok": True, "client": "xfreerdp3"}

    # Remmina fallback
    remmina = shutil.which("remmina")
    if remmina:
        profile_dir = Path(tempfile.gettempdir()) / "msp-rdp"
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile_path = profile_dir / f"{host}_{port}.remmina"
        profile_content = (
            f"[remmina]\n"
            f"name={username}@{host}\n"
            f"protocol=RDP\n"
            f"server={host}:{port}\n"
            f"username={username}\n"
            f"resolution_mode=2\n"
            f"colordepth=99\n"
            f"quality=2\n"
            f"shareclipboard=true\n"
            f"disablepasswordstoring=1\n"
        )
        if domain:
            profile_content += f"domain={domain}\n"
        # Never write password to disk — Remmina will prompt
        profile_path.write_text(profile_content)
        os.chmod(profile_path, 0o600)
        _launch_gui([remmina, "-c", str(profile_path)])
        # Schedule cleanup of temp profile
        import threading
        threading.Timer(5.0, lambda: profile_path.unlink(missing_ok=True)).start()
        return {"ok": True, "client": "Remmina"}

    # xfreerdp (older version fallback)
    xfree = shutil.which("xfreerdp")
    if xfree:
        cmd = [xfree, f"/v:{host}:{port}", f"/u:{username}",
               "/dynamic-resolution", "+clipboard", "/cert-ignore"]
        if domain:
            cmd.append(f"/d:{domain}")
        if password:
            cmd.append(f"/p:{password}")
        _launch_gui(cmd)
        return {"ok": True, "client": "xfreerdp"}

    # macOS
    if sys.platform == "darwin":
        # Generate .rdp file and open it
        rdp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.rdp', delete=False)
        rdp_file.write(f"full address:s:{host}:{port}\nusername:s:{username}\n")
        rdp_file.close()
        subprocess.Popen(["open", rdp_file.name])
        return {"ok": True, "client": "Microsoft Remote Desktop"}

    # Windows
    if sys.platform == "win32":
        subprocess.Popen(["mstsc", f"/v:{host}:{port}"])
        return {"ok": True, "client": "mstsc"}

    return {"ok": False, "error": "Ingen RDP-klient funnet. Installer Remmina eller xfreerdp."}
