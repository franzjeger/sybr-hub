"""SSH key and host management service.

Handles key generation/import, host CRUD, key push/revoke (3 strategies),
batch execution, health checks, and audit logging.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import shlex
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import DATA_DIR
from app.core.database import get_db
from app.core.encryption import encrypted_read_bytes, encrypted_write_bytes
from app.models.ssh import (
    AuthMethod,
    DeviceType,
    ExecResult,
    SshAuditEntry,
    SshHost,
    SshKey,
    SshKeyDeployment,
    SshKeyType,
)
from app.services.ssh_connection import SshSession

logger = logging.getLogger(__name__)

SSH_KEYS_DIR = DATA_DIR / "ssh_keys"


# ═══════════════════════════════════════════════════════════════════════════
# KEY GENERATION & IMPORT
# ═══════════════════════════════════════════════════════════════════════════

async def generate_key(
    name: str,
    key_type: SshKeyType = SshKeyType.ed25519,
    description: str = "",
    tags: list[str] | None = None,
    created_by: Optional[str] = None,
) -> SshKey:
    """Generate an SSH key pair and store it in the database + encrypted file."""
    import hashlib

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

    if key_type == SshKeyType.ed25519:
        private = ed25519.Ed25519PrivateKey.generate()
    elif key_type == SshKeyType.rsa2048:
        private = rsa.generate_private_key(65537, 2048)
    elif key_type == SshKeyType.rsa4096:
        private = rsa.generate_private_key(65537, 4096)
    else:
        from app.core.exceptions import ValidationError
        raise ValidationError(f"Unsupported key type: {key_type}")

    # Serialize
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption(),
    ).decode("utf-8")

    public_bytes = private.public_key().public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH,
    )
    public_key = public_bytes.decode("utf-8")

    # Compute SHA256 fingerprint
    # OpenSSH format: "ssh-ed25519 AAAA...base64... comment"
    key_data = base64.b64decode(public_key.split()[1])
    digest = hashlib.sha256(key_data).digest()
    fingerprint = "SHA256:" + base64.b64encode(digest).rstrip(b"=").decode("ascii")

    # Store
    key_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Save private key encrypted on disk
    key_dir = SSH_KEYS_DIR / key_id
    key_dir.mkdir(parents=True, exist_ok=True)
    encrypted_write_bytes(key_dir / "private_key", private_pem.encode("utf-8"))

    # Save to DB
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO ssh_keys
               (id, name, description, key_type, public_key, fingerprint, tags, created_at, updated_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (key_id, name, description, key_type.value, public_key, fingerprint,
             json.dumps(tags or []), now, now, created_by),
        )
        await conn.commit()

    logger.info("Generated %s key: %s (%s)", key_type.value, name, fingerprint)

    return SshKey(
        id=key_id, name=name, description=description, key_type=key_type,
        public_key=public_key, fingerprint=fingerprint, tags=tags or [],
        created_at=datetime.fromisoformat(now), updated_at=datetime.fromisoformat(now),
        created_by=created_by,
    )


async def import_key(
    name: str,
    private_key_pem: str,
    description: str = "",
    tags: list[str] | None = None,
    created_by: Optional[str] = None,
) -> SshKey:
    """Import an existing private key."""
    import hashlib

    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        load_ssh_private_key,
    )

    private = load_ssh_private_key(private_key_pem.encode("utf-8"), password=None)
    public_bytes = private.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
    public_key = public_bytes.decode("utf-8")

    # Detect type
    from cryptography.hazmat.primitives.asymmetric import ed25519 as ed_mod
    from cryptography.hazmat.primitives.asymmetric import rsa as rsa_mod
    if isinstance(private, ed_mod.Ed25519PrivateKey):
        key_type = SshKeyType.ed25519
    elif isinstance(private, rsa_mod.RSAPrivateKey):
        bits = private.key_size
        key_type = SshKeyType.rsa4096 if bits >= 4096 else SshKeyType.rsa2048
    else:
        key_type = SshKeyType.ed25519  # fallback

    # Fingerprint
    key_data = base64.b64decode(public_key.split()[1])
    digest = hashlib.sha256(key_data).digest()
    fingerprint = "SHA256:" + base64.b64encode(digest).rstrip(b"=").decode("ascii")

    key_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    key_dir = SSH_KEYS_DIR / key_id
    key_dir.mkdir(parents=True, exist_ok=True)
    encrypted_write_bytes(key_dir / "private_key", private_key_pem.encode("utf-8"))

    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO ssh_keys
               (id, name, description, key_type, public_key, fingerprint, tags, created_at, updated_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (key_id, name, description, key_type.value, public_key, fingerprint,
             json.dumps(tags or []), now, now, created_by),
        )
        await conn.commit()

    logger.info("Imported key: %s (%s)", name, fingerprint)
    return SshKey(
        id=key_id, name=name, description=description, key_type=key_type,
        public_key=public_key, fingerprint=fingerprint, tags=tags or [],
        created_at=datetime.fromisoformat(now), updated_at=datetime.fromisoformat(now),
        created_by=created_by,
    )


def _load_private_key(key_id: str) -> str:
    """Load private key PEM from encrypted storage."""
    key_path = SSH_KEYS_DIR / key_id / "private_key"
    return encrypted_read_bytes(key_path).decode("utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# KEY CRUD
# ═══════════════════════════════════════════════════════════════════════════

async def list_keys() -> list[SshKey]:
    async with get_db() as conn:
        async with conn.execute("SELECT * FROM ssh_keys ORDER BY created_at DESC") as cur:
            return [_row_to_key(r) for r in await cur.fetchall()]


async def get_key(key_id: str) -> Optional[SshKey]:
    async with get_db() as conn:
        async with conn.execute("SELECT * FROM ssh_keys WHERE id = ?", (key_id,)) as cur:
            row = await cur.fetchone()
            return _row_to_key(row) if row else None


async def delete_key(key_id: str) -> bool:
    import shutil
    async with get_db() as conn:
        cursor = await conn.execute("DELETE FROM ssh_keys WHERE id = ?", (key_id,))
        await conn.commit()
    # Remove encrypted private key
    key_dir = SSH_KEYS_DIR / key_id
    if key_dir.exists():
        shutil.rmtree(str(key_dir))
    return cursor.rowcount > 0


async def get_key_deployments(key_id: str) -> list[SshKeyDeployment]:
    async with get_db() as conn:
        async with conn.execute(
            "SELECT * FROM ssh_key_deployments WHERE key_id = ?", (key_id,)
        ) as cur:
            return [
                SshKeyDeployment(
                    key_id=r["key_id"], host_id=r["host_id"],
                    deployed_at=datetime.fromisoformat(r["deployed_at"]),
                    deployed_by=r["deployed_by"],
                )
                for r in await cur.fetchall()
            ]


# ═══════════════════════════════════════════════════════════════════════════
# HOST CRUD
# ═══════════════════════════════════════════════════════════════════════════

async def list_hosts(
    group_name: Optional[str] = None,
    device_type: Optional[DeviceType] = None,
    customer_id: Optional[str] = None,
) -> list[SshHost]:
    query = "SELECT * FROM ssh_hosts WHERE 1=1"
    params: list = []
    if group_name:
        query += " AND group_name = ?"
        params.append(group_name)
    if device_type:
        query += " AND device_type = ?"
        params.append(device_type.value)
    if customer_id:
        query += " AND customer_id = ?"
        params.append(customer_id)
    query += " ORDER BY group_name, label"

    async with get_db() as conn:
        async with conn.execute(query, params) as cur:
            return [_row_to_host(r) for r in await cur.fetchall()]


async def get_host(host_id: str) -> Optional[SshHost]:
    async with get_db() as conn:
        async with conn.execute("SELECT * FROM ssh_hosts WHERE id = ?", (host_id,)) as cur:
            row = await cur.fetchone()
            return _row_to_host(row) if row else None


async def create_host(
    label: str, hostname: str, username: str,
    port: int = 22,
    password: Optional[str] = None,
    group_name: str = "",
    device_type: DeviceType = DeviceType.linux,
    auth_method: AuthMethod = AuthMethod.key,
    auth_key_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    tags: list[str] | None = None,
    notes: str = "",
    created_by: Optional[str] = None,
) -> SshHost:
    host_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO ssh_hosts
               (id, label, hostname, port, username, group_name, device_type,
                auth_method, auth_key_id, customer_id, tags, notes, created_at, updated_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (host_id, label, hostname, port, username, group_name, device_type.value,
             auth_method.value, auth_key_id, customer_id,
             json.dumps(tags or []), notes, now, now, created_by),
        )
        await conn.commit()

    # Store password if provided (encrypted)
    if password:
        _store_host_secret(host_id, password)

    return await get_host(host_id)  # type: ignore


ALLOWED_SSH_FIELDS = frozenset({"label", "hostname", "port", "username", "password", "device_type", "auth_method", "auth_key_id", "group_name", "notes", "tags", "customer_id", "jump_host_id"})


async def update_host(host_id: str, **kwargs) -> Optional[SshHost]:
    password = kwargs.pop("password", None)
    fields = []
    values = []
    _nullable_ssh_fields = {"customer_id", "auth_key_id", "jump_host_id"}
    for k, v in kwargs.items():
        if k not in ALLOWED_SSH_FIELDS:
            continue
        if v is not None or k in _nullable_ssh_fields:
            if k == "tags":
                fields.append(k + " = ?")
                values.append(json.dumps(v))
            elif k == "device_type" or k == "auth_method":
                fields.append(k + " = ?")
                values.append(v.value if hasattr(v, "value") else v)
            else:
                fields.append(k + " = ?")
                values.append(v)
    if fields:
        fields.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())
        values.append(host_id)
        async with get_db() as conn:
            await conn.execute(f"UPDATE ssh_hosts SET {', '.join(fields)} WHERE id = ?", values)
            await conn.commit()
    if password:
        _store_host_secret(host_id, password)
    return await get_host(host_id)


async def delete_host(host_id: str) -> bool:
    async with get_db() as conn:
        cursor = await conn.execute("DELETE FROM ssh_hosts WHERE id = ?", (host_id,))
        await conn.commit()
    # Remove stored password
    secret_path = SSH_KEYS_DIR / "hosts" / host_id
    if secret_path.exists():
        import shutil
        shutil.rmtree(str(secret_path))
    return cursor.rowcount > 0


def _store_host_secret(host_id: str, password: str) -> None:
    secret_dir = SSH_KEYS_DIR / "hosts" / host_id
    secret_dir.mkdir(parents=True, exist_ok=True)
    encrypted_write_bytes(secret_dir / "password", password.encode("utf-8"))


def _load_host_password(host_id: str) -> Optional[str]:
    secret_path = SSH_KEYS_DIR / "hosts" / host_id / "password"
    if not secret_path.exists():
        return None
    try:
        return encrypted_read_bytes(secret_path).decode("utf-8")
    except Exception as e:
        logger.debug("Failed to load password for host %s: %s", host_id, e)
        return None


# ═══════════════════════════════════════════════════════════════════════════
# SSH CONNECTION HELPER
# ═══════════════════════════════════════════════════════════════════════════

async def _connect_to_host(host: SshHost) -> SshSession:
    """Open an SSH session to a host using its configured auth method."""
    password = None
    private_key = None

    if host.auth_method == AuthMethod.password:
        password = _load_host_password(host.id)
    elif host.auth_method == AuthMethod.key and host.auth_key_id:
        try:
            private_key = _load_private_key(host.auth_key_id)
        except Exception as e:
            logger.warning("Failed to load private key %s: %s", host.auth_key_id, e)

    # SshSession.connect takes `client_keys` (asyncssh key objects), not a
    # `private_key` PEM string. Passing the latter raised TypeError on every
    # call — including password-auth hosts, since the keyword was unexpected
    # regardless of its value — and each caller swallowed it into a per-host
    # {"ok": False, "error": ...}, so host test, batch exec, key push, key
    # revoke and health check have never worked. Convert the PEM properly.
    client_keys = None
    if private_key:
        import asyncssh
        try:
            client_keys = [asyncssh.import_private_key(private_key)]
        except Exception as e:
            logger.warning("Could not parse private key for host %s: %s", host.id, e)

    return await SshSession.connect(
        hostname=host.hostname,
        port=host.port,
        username=host.username,
        password=password,
        client_keys=client_keys,
    )


# ═══════════════════════════════════════════════════════════════════════════
# KEY PUSH — 3-strategy deployment (from SuperManager push.rs)
# ═══════════════════════════════════════════════════════════════════════════

async def push_key(
    key_id: str,
    host_ids: list[str],
    use_sudo: bool = False,
    user_id: Optional[str] = None,
) -> list[dict]:
    """Push a public key to one or more hosts.  Returns per-host results."""
    from app.core.activity_log import log_activity

    key = await get_key(key_id)
    if not key:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(f"Key {key_id} not found")

    results = []
    for hid in host_ids:
        host = await get_host(hid)
        if not host:
            results.append({"host_id": hid, "ok": False, "error": "Host not found"})
            continue
        try:
            async with await _connect_to_host(host) as session:
                if use_sudo:
                    await _push_with_sudo(session, key.public_key)
                else:
                    try:
                        await _push_via_sftp(session, key.public_key)
                    except Exception:
                        await _push_via_exec(session, key.public_key)

            # Record deployment
            now = datetime.now(timezone.utc).isoformat()
            async with get_db() as conn:
                await conn.execute(
                    """INSERT OR REPLACE INTO ssh_key_deployments
                       (key_id, host_id, deployed_at, deployed_by) VALUES (?, ?, ?, ?)""",
                    (key_id, hid, now, user_id),
                )
                await conn.commit()

            await _log_ssh_action("key_push", key, host, True, user_id)
            log_activity(
                "ssh_key_push",
                detail=f"Pushed key '{key.name}' ({key.fingerprint}) to {host.label} ({host.hostname}) — success",
                user=user_id or "",
            )
            results.append({"host_id": hid, "host_label": host.label, "ok": True})

        except Exception as e:
            await _log_ssh_action("key_push", key, host, False, user_id, str(e))
            log_activity(
                "ssh_key_push",
                detail=f"Pushed key '{key.name}' ({key.fingerprint}) to {host.label} ({host.hostname}) — failed: {str(e)[:200]}",
                user=user_id or "",
            )
            results.append({"host_id": hid, "host_label": host.label, "ok": False, "error": str(e)})

    return results


async def _push_via_sftp(session: SshSession, pub_line: str) -> None:
    """Strategy 1: SFTP — preferred, most reliable."""
    home = await session.get_home()
    ssh_dir = f"{home}/.ssh"
    ak_path = f"{home}/.ssh/authorized_keys"

    # Ensure .ssh dir
    await session.sftp_mkdir(ssh_dir)

    # Read existing
    existing_bytes = await session.sftp_read(ak_path)
    existing = existing_bytes.decode("utf-8", errors="replace") if existing_bytes else ""

    # Duplicate check
    pub_trimmed = pub_line.strip()
    if pub_trimmed in existing:
        return

    # Build updated content
    content = existing.rstrip("\n")
    if content:
        content += "\n"
    content += pub_trimmed + "\n"

    await session.sftp_write(ak_path, content.encode("utf-8"))

    # Fix permissions (best-effort)
    await session.exec(f"chmod 700 {shlex.quote(ssh_dir)}", timeout=5)
    await session.exec(f"chmod 600 {shlex.quote(ak_path)}", timeout=5)


async def _push_via_exec(session: SshSession, pub_line: str) -> None:
    """Strategy 2: exec with base64 — BusyBox/UniFi/OpenWrt compatible."""
    home = await session.get_home()
    ssh_dir = f"{home}/.ssh"
    ak_path = f"{home}/.ssh/authorized_keys"

    # Ensure dir/file (best-effort)
    q_dir = shlex.quote(ssh_dir)
    q_ak = shlex.quote(ak_path)
    await session.exec(f"mkdir -p {q_dir} && chmod 700 {q_dir}", timeout=10)
    await session.exec(f"touch {q_ak} && chmod 600 {q_ak}", timeout=10)

    # Base64 encode to avoid shell quoting issues
    b64 = base64.b64encode(pub_line.strip().encode("utf-8")).decode("ascii")

    # Duplicate check
    check = await session.exec(
        f'grep -qF "$(printf \'%s\' {b64} | base64 -d)" {q_ak} 2>/dev/null',
        timeout=10,
    )
    if check.exit_code == 0:
        return  # Already present

    # Append
    result = await session.exec(
        f"printf '%s\\n' {b64} | base64 -d >> {q_ak}",
        timeout=10,
    )
    if result.exit_code != 0:
        raise RuntimeError(f"Append failed (rc={result.exit_code}): {result.stderr}")


async def _push_with_sudo(session: SshSession, pub_line: str) -> None:
    """Strategy 3: sudo — for non-root users deploying to /root."""
    target_dir = "/root/.ssh"
    target_file = "/root/.ssh/authorized_keys"

    q_dir = shlex.quote(target_dir)
    q_file = shlex.quote(target_file)
    await session.exec(f"sudo mkdir -p {q_dir} && sudo chmod 700 {q_dir}", timeout=10)
    await session.exec(f"sudo touch {q_file} && sudo chmod 600 {q_file}", timeout=10)

    b64 = base64.b64encode(pub_line.strip().encode("utf-8")).decode("ascii")

    check = await session.exec(
        f'sudo grep -qF "$(echo {b64} | base64 -d)" {q_file} 2>/dev/null',
        timeout=10,
    )
    if check.exit_code == 0:
        return

    result = await session.exec(
        f"echo {b64} | base64 -d | sudo tee -a {q_file} > /dev/null",
        timeout=10,
    )
    if result.exit_code != 0:
        raise RuntimeError(f"Sudo append failed (rc={result.exit_code}): {result.stderr}")


# ═══════════════════════════════════════════════════════════════════════════
# KEY REVOKE — mirror of push with line removal
# ═══════════════════════════════════════════════════════════════════════════

async def revoke_key(
    key_id: str,
    host_ids: list[str],
    use_sudo: bool = False,
    user_id: Optional[str] = None,
) -> list[dict]:
    """Revoke a public key from one or more hosts."""
    from app.core.activity_log import log_activity

    key = await get_key(key_id)
    if not key:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(f"Key {key_id} not found")

    results = []
    for hid in host_ids:
        host = await get_host(hid)
        if not host:
            results.append({"host_id": hid, "ok": False, "error": "Host not found"})
            continue
        try:
            async with await _connect_to_host(host) as session:
                if use_sudo:
                    await _revoke_with_sudo(session, key.public_key)
                else:
                    try:
                        await _revoke_via_sftp(session, key.public_key)
                    except Exception:
                        await _revoke_via_exec(session, key.public_key)

            # Remove deployment record
            async with get_db() as conn:
                await conn.execute(
                    "DELETE FROM ssh_key_deployments WHERE key_id = ? AND host_id = ?",
                    (key_id, hid),
                )
                await conn.commit()

            await _log_ssh_action("key_revoke", key, host, True, user_id)
            log_activity(
                "ssh_key_revoke",
                detail=f"Revoked key '{key.name}' ({key.fingerprint}) from {host.label} ({host.hostname}) — success",
                user=user_id or "",
            )
            results.append({"host_id": hid, "host_label": host.label, "ok": True})

        except Exception as e:
            await _log_ssh_action("key_revoke", key, host, False, user_id, str(e))
            log_activity(
                "ssh_key_revoke",
                detail=f"Revoked key '{key.name}' ({key.fingerprint}) from {host.label} ({host.hostname}) — failed: {str(e)[:200]}",
                user=user_id or "",
            )
            results.append({"host_id": hid, "host_label": host.label, "ok": False, "error": str(e)})

    return results


async def _revoke_via_sftp(session: SshSession, pub_line: str) -> None:
    home = await session.get_home()
    ak_path = f"{home}/.ssh/authorized_keys"

    existing_bytes = await session.sftp_read(ak_path)
    if not existing_bytes:
        return  # No file = nothing to revoke

    existing = existing_bytes.decode("utf-8", errors="replace")
    pub_trimmed = pub_line.strip()

    lines = existing.splitlines()
    filtered = [l for l in lines if pub_trimmed not in l]
    if len(filtered) == len(lines):
        return  # Key not found

    await session.sftp_write(ak_path, ("\n".join(filtered) + "\n").encode("utf-8"))
    await session.exec(f"chmod 600 {shlex.quote(ak_path)}", timeout=5)


async def _revoke_via_exec(session: SshSession, pub_line: str) -> None:
    home = await session.get_home()
    ak_path = f"{home}/.ssh/authorized_keys"
    q_ak = shlex.quote(ak_path)

    check = await session.exec(f"test -f {q_ak}", timeout=5)
    if check.exit_code != 0:
        return

    b64 = base64.b64encode(pub_line.strip().encode("utf-8")).decode("ascii")
    cmd = (
        f'tmp=$(mktemp /tmp/.ak_revoke_XXXXXX) && '
        f'grep -vF "$(printf \'%s\' {b64} | base64 -d)" {q_ak} > "$tmp" '
        f'&& mv "$tmp" {q_ak} && chmod 600 {q_ak}'
    )
    result = await session.exec(cmd, timeout=15)
    if result.exit_code != 0:
        raise RuntimeError(f"Revoke failed (rc={result.exit_code}): {result.stderr}")


async def _revoke_with_sudo(session: SshSession, pub_line: str) -> None:
    target_file = "/root/.ssh/authorized_keys"
    q_file = shlex.quote(target_file)

    check = await session.exec(f"sudo test -f {q_file}", timeout=5)
    if check.exit_code != 0:
        return

    b64 = base64.b64encode(pub_line.strip().encode("utf-8")).decode("ascii")
    cmd = (
        f'tmp=$(mktemp /tmp/.ak_revoke_XXXXXX) && '
        f'sudo grep -vF "$(printf \'%s\' {b64} | base64 -d)" {q_file} > "$tmp" '
        f'&& sudo mv "$tmp" {q_file} && sudo chmod 600 {q_file}'
    )
    result = await session.exec(cmd, timeout=15)
    if result.exit_code != 0:
        raise RuntimeError(f"Sudo revoke failed (rc={result.exit_code}): {result.stderr}")


# ═══════════════════════════════════════════════════════════════════════════
# BATCH EXECUTION
# ═══════════════════════════════════════════════════════════════════════════

async def batch_exec(
    host_ids: list[str],
    command: str,
    user_id: Optional[str] = None,
) -> list[ExecResult]:
    """Execute a command on multiple hosts in parallel."""

    async def _run_one(hid: str) -> ExecResult:
        host = await get_host(hid)
        if not host:
            return ExecResult(host_id=hid, host_label="?", hostname="?",
                              exit_code=-1, stdout="", stderr="", error="Host not found")
        try:
            async with await _connect_to_host(host) as session:
                out = await session.exec(command)
                await _log_ssh_action("exec", None, host, out.exit_code == 0, user_id, command[:200])
                return ExecResult(
                    host_id=hid, host_label=host.label, hostname=host.hostname,
                    exit_code=out.exit_code, stdout=out.stdout, stderr=out.stderr,
                )
        except Exception as e:
            await _log_ssh_action("exec", None, host, False, user_id, str(e))
            return ExecResult(
                host_id=hid, host_label=host.label, hostname=host.hostname,
                exit_code=-1, stdout="", stderr="", error=str(e),
            )

    return list(await asyncio.gather(*[_run_one(hid) for hid in host_ids]))


# ═══════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════

async def health_check(host_ids: list[str]) -> list[dict]:
    """Check SSH reachability for multiple hosts in parallel."""

    async def _check_one(hid: str) -> dict:
        host = await get_host(hid)
        if not host:
            return {"host_id": hid, "reachable": False, "error": "Host not found"}
        try:
            async with await _connect_to_host(host) as session:
                out = await session.exec("echo ok", timeout=5)
                reachable = out.exit_code == 0

            # Update DB
            now = datetime.now(timezone.utc).isoformat()
            async with get_db() as conn:
                await conn.execute(
                    "UPDATE ssh_hosts SET last_seen = ?, is_reachable = ? WHERE id = ?",
                    (now, int(reachable), hid),
                )
                await conn.commit()

            return {"host_id": hid, "host_label": host.label, "reachable": reachable}
        except Exception as e:
            async with get_db() as conn:
                await conn.execute(
                    "UPDATE ssh_hosts SET is_reachable = 0 WHERE id = ?", (hid,)
                )
                await conn.commit()
            return {"host_id": hid, "host_label": host.label, "reachable": False, "error": str(e)}

    return list(await asyncio.gather(*[_check_one(hid) for hid in host_ids]))


# ═══════════════════════════════════════════════════════════════════════════
# SSH CONFIG GENERATION
# ═══════════════════════════════════════════════════════════════════════════

async def generate_ssh_config(host_ids: Optional[list[str]] = None) -> str:
    """Generate ~/.ssh/config entries for selected (or all) hosts.

    ``None`` means every host; an empty list means no hosts. The distinction
    matters because the caller now passes the hosts the requester may see —
    and a falsy check turned "you may see none" into "here is the entire
    estate", in paste-ready form with hostnames, ports, users and key paths.
    """
    hosts = await list_hosts()
    if host_ids is not None:
        wanted = set(host_ids)
        hosts = [h for h in hosts if h.id in wanted]

    lines = ["# Generated by MSP Toolkit", ""]
    for h in hosts:
        lines.append(f"Host {h.label.replace(' ', '-').lower()}")
        lines.append(f"    HostName {h.hostname}")
        lines.append(f"    Port {h.port}")
        lines.append(f"    User {h.username}")
        if h.auth_method == AuthMethod.key and h.auth_key_id:
            lines.append(f"    IdentityFile ~/.ssh/msp_toolkit_{h.auth_key_id[:8]}")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════

async def _log_ssh_action(
    action: str,
    key: Optional[SshKey],
    host: Optional[SshHost],
    success: bool,
    user_id: Optional[str] = None,
    detail: str = "",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO ssh_audit_log
               (timestamp, action, key_name, key_fingerprint, host_label, hostname, port, success, user_id, detail)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, action,
             key.name if key else None, key.fingerprint if key else None,
             host.label if host else None, host.hostname if host else None,
             host.port if host else None,
             int(success), user_id, detail[:1000]),
        )
        await conn.commit()


async def get_audit_log(limit: int = 100, offset: int = 0) -> list[SshAuditEntry]:
    async with get_db() as conn:
        async with conn.execute(
            "SELECT * FROM ssh_audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            return [
                SshAuditEntry(
                    id=r["id"], timestamp=datetime.fromisoformat(r["timestamp"]),
                    action=r["action"], key_name=r["key_name"],
                    key_fingerprint=r["key_fingerprint"], host_label=r["host_label"],
                    hostname=r["hostname"], port=r["port"], success=bool(r["success"]),
                    user_id=r["user_id"], detail=r["detail"],
                )
                for r in await cur.fetchall()
            ]


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _row_to_key(row) -> SshKey:
    return SshKey(
        id=row["id"], name=row["name"], description=row["description"],
        key_type=SshKeyType(row["key_type"]), public_key=row["public_key"],
        fingerprint=row["fingerprint"], tags=json.loads(row["tags"] or "[]"),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        created_by=row["created_by"],
    )


def _row_to_host(row) -> SshHost:
    return SshHost(
        id=row["id"], label=row["label"], hostname=row["hostname"],
        port=row["port"], username=row["username"],
        group_name=row["group_name"], device_type=DeviceType(row["device_type"]),
        auth_method=AuthMethod(row["auth_method"]),
        auth_key_id=row["auth_key_id"], customer_id=row["customer_id"],
        tags=json.loads(row["tags"] or "[]"), notes=row["notes"],
        last_seen=datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else None,
        is_reachable=bool(row["is_reachable"]) if row["is_reachable"] is not None else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        created_by=row["created_by"],
    )
