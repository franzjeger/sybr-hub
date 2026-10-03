"""SSH key and host management service.

Handles key generation/import, host CRUD, key push/revoke (3 strategies),
batch execution, health checks, and audit logging.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import shlex
import uuid
from datetime import UTC, datetime

from sqlmodel import delete, select

from app.core.config import DATA_DIR
from app.core.encryption import encrypted_read_bytes, encrypted_write_bytes
from app.core.orm import get_session
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

# Ceiling on simultaneous SSH connections for the fan-out helpers. These
# paths raised TypeError on every call until recently, so nothing bounded
# them; now they genuinely open sockets to customer machines.
_MAX_CONCURRENT_HOSTS = 10

SSH_KEYS_DIR = DATA_DIR / "ssh_keys"


# ═══════════════════════════════════════════════════════════════════════════
# KEY GENERATION & IMPORT
# ═══════════════════════════════════════════════════════════════════════════


async def generate_key(
    name: str,
    key_type: SshKeyType = SshKeyType.ed25519,
    description: str = "",
    tags: list[str] | None = None,
    created_by: str | None = None,
    customer_id: str | None = None,
) -> SshKey:
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

    key_data = base64.b64decode(public_key.split()[1])
    digest = hashlib.sha256(key_data).digest()
    fingerprint = "SHA256:" + base64.b64encode(digest).rstrip(b"=").decode("ascii")

    key_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    key_dir = SSH_KEYS_DIR / key_id
    key_dir.mkdir(parents=True, exist_ok=True)
    encrypted_write_bytes(key_dir / "private_key", private_pem.encode("utf-8"))

    async with get_session() as db_session:
        key_obj = SshKey(
            id=key_id,
            name=name,
            description=description,
            key_type=key_type,
            public_key=public_key,
            fingerprint=fingerprint,
            tags=tags or [],
            created_at=now,
            updated_at=now,
            created_by=created_by,
            customer_id=customer_id,
        )
        db_session.add(key_obj)
        await db_session.commit()
        await db_session.refresh(key_obj)

    logger.info("Generated %s key: %s (%s)", key_type.value, name, fingerprint)
    return key_obj


async def import_key(
    name: str,
    private_key_pem: str,
    description: str = "",
    tags: list[str] | None = None,
    created_by: str | None = None,
    customer_id: str | None = None,
) -> SshKey:
    import hashlib

    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        load_ssh_private_key,
    )

    private = load_ssh_private_key(private_key_pem.encode("utf-8"), password=None)
    public_bytes = private.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
    public_key = public_bytes.decode("utf-8")

    from cryptography.hazmat.primitives.asymmetric import ed25519 as ed_mod
    from cryptography.hazmat.primitives.asymmetric import rsa as rsa_mod

    if isinstance(private, ed_mod.Ed25519PrivateKey):
        key_type = SshKeyType.ed25519
    elif isinstance(private, rsa_mod.RSAPrivateKey):
        bits = private.key_size
        key_type = SshKeyType.rsa4096 if bits >= 4096 else SshKeyType.rsa2048
    else:
        key_type = SshKeyType.ed25519

    key_data = base64.b64decode(public_key.split()[1])
    digest = hashlib.sha256(key_data).digest()
    fingerprint = "SHA256:" + base64.b64encode(digest).rstrip(b"=").decode("ascii")

    key_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    key_dir = SSH_KEYS_DIR / key_id
    key_dir.mkdir(parents=True, exist_ok=True)
    encrypted_write_bytes(key_dir / "private_key", private_key_pem.encode("utf-8"))

    async with get_session() as db_session:
        key_obj = SshKey(
            id=key_id,
            name=name,
            description=description,
            key_type=key_type,
            public_key=public_key,
            fingerprint=fingerprint,
            tags=tags or [],
            created_at=now,
            updated_at=now,
            created_by=created_by,
            customer_id=customer_id,
        )
        db_session.add(key_obj)
        await db_session.commit()
        await db_session.refresh(key_obj)

    logger.info("Imported key: %s (%s)", name, fingerprint)
    return key_obj


def _load_private_key(key_id: str) -> str:
    """Load private key PEM from encrypted storage."""
    key_path = SSH_KEYS_DIR / key_id / "private_key"
    return encrypted_read_bytes(key_path).decode("utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# KEY CRUD
# ═══════════════════════════════════════════════════════════════════════════


async def list_keys() -> list[SshKey]:
    async with get_session() as db_session:
        result = await db_session.execute(select(SshKey).order_by(SshKey.created_at.desc()))
        return list(result.scalars().all())


async def get_key(key_id: str) -> SshKey | None:
    async with get_session() as db_session:
        result = await db_session.execute(select(SshKey).where(SshKey.id == key_id))
        return result.scalars().first()


async def delete_key(key_id: str) -> bool:
    import shutil

    async with get_session() as db_session:
        result = await db_session.execute(delete(SshKey).where(SshKey.id == key_id))
        await db_session.commit()
        deleted = result.rowcount > 0

    key_dir = SSH_KEYS_DIR / key_id
    if key_dir.exists():
        shutil.rmtree(str(key_dir))
    return deleted


async def get_key_deployments(key_id: str) -> list[SshKeyDeployment]:
    async with get_session() as db_session:
        result = await db_session.execute(
            select(SshKeyDeployment).where(SshKeyDeployment.key_id == key_id)
        )
        return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════════════
# HOST CRUD
# ═══════════════════════════════════════════════════════════════════════════


async def list_hosts(
    group_name: str | None = None,
    device_type: DeviceType | None = None,
    customer_id: str | None = None,
) -> list[SshHost]:
    async with get_session() as db_session:
        stmt = select(SshHost)
        if group_name:
            stmt = stmt.where(SshHost.group_name == group_name)
        if device_type:
            stmt = stmt.where(SshHost.device_type == device_type)
        if customer_id:
            stmt = stmt.where(SshHost.customer_id == customer_id)
        stmt = stmt.order_by(SshHost.group_name, SshHost.label)

        result = await db_session.execute(stmt)
        return list(result.scalars().all())


async def get_host(host_id: str) -> SshHost | None:
    async with get_session() as db_session:
        result = await db_session.execute(select(SshHost).where(SshHost.id == host_id))
        return result.scalars().first()


async def create_host(
    label: str,
    hostname: str,
    username: str,
    port: int = 22,
    password: str | None = None,
    group_name: str = "",
    device_type: DeviceType = DeviceType.linux,
    auth_method: AuthMethod = AuthMethod.key,
    auth_key_id: str | None = None,
    customer_id: str | None = None,
    tags: list[str] | None = None,
    notes: str = "",
    created_by: str | None = None,
) -> SshHost:
    host_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    async with get_session() as db_session:
        host_obj = SshHost(
            id=host_id,
            label=label,
            hostname=hostname,
            port=port,
            username=username,
            group_name=group_name,
            device_type=device_type,
            auth_method=auth_method,
            auth_key_id=auth_key_id,
            customer_id=customer_id,
            tags=tags or [],
            notes=notes,
            created_at=now,
            updated_at=now,
            created_by=created_by,
        )
        db_session.add(host_obj)
        await db_session.commit()
        await db_session.refresh(host_obj)

    if password:
        _store_host_secret(host_id, password)

    return host_obj


ALLOWED_SSH_FIELDS = frozenset(
    {
        "label",
        "hostname",
        "port",
        "username",
        "password",
        "device_type",
        "auth_method",
        "auth_key_id",
        "group_name",
        "notes",
        "tags",
        "customer_id",
        "jump_host_id",
    }
)


def host_target_changed(host: SshHost, updates: dict) -> bool:
    """Whether *updates* would send this host's stored credentials somewhere new.

    The stored password was entered for one hostname, port and account. Any of
    the three changing means the next connection presents it to a different
    party, and TOFU host-key pinning does not help: a new host:port is a first
    use by definition.
    """
    hostname = updates.get("hostname")
    if hostname is not None and hostname.strip().casefold() != host.hostname.strip().casefold():
        return True
    port = updates.get("port")
    if port is not None and int(port) != host.port:
        return True
    username = updates.get("username")
    return username is not None and username != host.username


async def update_host(host_id: str, **kwargs) -> SshHost | None:
    """Apply *kwargs* to a host.

    Repointing a host (see host_target_changed) without supplying a password
    in the same call deletes the stored one, so it has to be re-entered by
    someone who knows it rather than following the host to its new address.
    """
    password = kwargs.pop("password", None)
    _nullable_ssh_fields = {"customer_id", "auth_key_id", "jump_host_id"}

    async with get_session() as db_session:
        result = await db_session.execute(select(SshHost).where(SshHost.id == host_id))
        host_obj = result.scalars().first()
        if not host_obj:
            return None

        # Before the new target is committed, so no connection can pair the
        # new address with the old password in between.
        if not password and host_target_changed(host_obj, kwargs):
            _delete_host_password(host_id)

        updated = False
        for k, v in kwargs.items():
            if k not in ALLOWED_SSH_FIELDS:
                continue
            if v is not None or k in _nullable_ssh_fields:
                setattr(host_obj, k, v)
                updated = True

        if updated:
            host_obj.updated_at = datetime.now(UTC)
            db_session.add(host_obj)
            await db_session.commit()
            await db_session.refresh(host_obj)

    if password:
        _store_host_secret(host_id, password)

    return host_obj


async def delete_host(host_id: str) -> bool:
    async with get_session() as db_session:
        result = await db_session.execute(delete(SshHost).where(SshHost.id == host_id))
        await db_session.commit()
        deleted = result.rowcount > 0

    secret_path = SSH_KEYS_DIR / "hosts" / host_id
    if secret_path.exists():
        import shutil

        shutil.rmtree(str(secret_path))
    return deleted


def _store_host_secret(host_id: str, password: str) -> None:
    secret_dir = SSH_KEYS_DIR / "hosts" / host_id
    secret_dir.mkdir(parents=True, exist_ok=True)
    encrypted_write_bytes(secret_dir / "password", password.encode("utf-8"))


def _delete_host_password(host_id: str) -> None:
    (SSH_KEYS_DIR / "hosts" / host_id / "password").unlink(missing_ok=True)


def has_host_password(host_id: str) -> bool:
    return (SSH_KEYS_DIR / "hosts" / host_id / "password").exists()


def _load_host_password(host_id: str) -> str | None:
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
    #
    # None here is load-bearing and is *not* the careless value it looks like.
    # asyncssh reads None as "offer nothing, and no agent either"; an empty
    # list — or omitting the argument — falls through to load_default_keypairs()
    # and offers the hub's own ~/.ssh identity to the customer's device. Do not
    # "tidy" this to [].
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
    user_id: str | None = None,
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
            now = datetime.now(UTC).isoformat()
            now = datetime.now(UTC)
            async with get_session() as db_session:
                dep = SshKeyDeployment(
                    key_id=key_id, host_id=hid, deployed_at=now, deployed_by=user_id
                )
                await db_session.merge(dep)
                await db_session.commit()

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
        f"grep -qF \"$(printf '%s' {b64} | base64 -d)\" {q_ak} 2>/dev/null",
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
    user_id: str | None = None,
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
            async with get_session() as db_session:
                await db_session.execute(
                    delete(SshKeyDeployment)
                    .where(SshKeyDeployment.key_id == key_id)
                    .where(SshKeyDeployment.host_id == hid)
                )
                await db_session.commit()

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
    filtered = [line for line in lines if pub_trimmed not in line]
    if len(filtered) == len(lines):
        return  # Key not found

    await session.sftp_write(ak_path, ("\n".join(filtered) + "\n").encode("utf-8"))
    await session.exec(f"chmod 600 {shlex.quote(ak_path)}", timeout=5)


def _revoke_script(ak_path: str, pub_line: str) -> str:
    """Shell script that removes *pub_line* from *ak_path*.

    Two things the previous one-liner got wrong, both of them on the customer's
    machine:

     * ``grep -vF`` exits 1 when nothing matches — which here means the file
       held only the key being revoked, the most ordinary revoke there is.
       Chained with ``&&`` that skipped the replacement and reported "revoke
       failed" on exactly the case that mattered. Only rc >= 2 is a grep error.
     * The staging file was ``mktemp /tmp/...``, created as the *login* user,
       and the sudo variant then ``sudo mv``-ed it over
       /root/.ssh/authorized_keys — handing an unprivileged account ownership
       of root's key file, which lets it authorise any key it likes and makes
       sshd's StrictModes refuse the file at the same time. Staging beside the
       target keeps the replacement atomic, on the same filesystem, and owned
       by whoever is running the script.
    """
    q_ak = shlex.quote(ak_path)
    b64 = base64.b64encode(pub_line.strip().encode("utf-8")).decode("ascii")
    return (
        f"tmp={q_ak}.revoke.$$\n"
        f'grep -vF "$(printf \'%s\' {b64} | base64 -d)" {q_ak} > "$tmp"\n'
        f"rc=$?\n"
        f'if [ "$rc" -gt 1 ]; then rm -f "$tmp"; exit "$rc"; fi\n'
        f'chmod 600 "$tmp" && mv "$tmp" {q_ak}\n'
    )


def _sh_script_command(script: str, *, sudo: bool = False) -> str:
    """Wrap a multi-line script so it survives one trip through the remote shell.

    Base64 for the same reason the key material uses it: the script then
    contains no quoting the outer shell can misread, and there is exactly one
    level of interpretation to reason about.
    """
    b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
    runner = "sudo sh" if sudo else "sh"
    return f"printf '%s' {b64} | base64 -d | {runner}"


async def _revoke_via_exec(session: SshSession, pub_line: str) -> None:
    home = await session.get_home()
    ak_path = f"{home}/.ssh/authorized_keys"

    check = await session.exec(f"test -f {shlex.quote(ak_path)}", timeout=5)
    if check.exit_code != 0:
        return

    result = await session.exec(_sh_script_command(_revoke_script(ak_path, pub_line)), timeout=15)
    if result.exit_code != 0:
        raise RuntimeError(f"Revoke failed (rc={result.exit_code}): {result.stderr}")


async def _revoke_with_sudo(session: SshSession, pub_line: str) -> None:
    target_file = "/root/.ssh/authorized_keys"

    check = await session.exec(f"sudo test -f {shlex.quote(target_file)}", timeout=5)
    if check.exit_code != 0:
        return

    # The whole script runs under sudo, so the staging file is created by root
    # in root's own .ssh — the ownership never leaves root's hands.
    result = await session.exec(
        _sh_script_command(_revoke_script(target_file, pub_line), sudo=True), timeout=15
    )
    if result.exit_code != 0:
        raise RuntimeError(f"Sudo revoke failed (rc={result.exit_code}): {result.stderr}")


# ═══════════════════════════════════════════════════════════════════════════
# BATCH EXECUTION
# ═══════════════════════════════════════════════════════════════════════════


async def batch_exec(
    host_ids: list[str],
    command: str,
    user_id: str | None = None,
) -> list[ExecResult]:
    """Execute a command on multiple hosts in parallel."""

    async def _run_one(hid: str) -> ExecResult:
        host = await get_host(hid)
        if not host:
            return ExecResult(
                host_id=hid,
                host_label="?",
                hostname="?",
                exit_code=-1,
                stdout="",
                stderr="",
                error="Host not found",
            )
        try:
            async with await _connect_to_host(host) as session:
                out = await session.exec(command)
                await _log_ssh_action(
                    "exec", None, host, out.exit_code == 0, user_id, command[:200]
                )
                return ExecResult(
                    host_id=hid,
                    host_label=host.label,
                    hostname=host.hostname,
                    exit_code=out.exit_code,
                    stdout=out.stdout,
                    stderr=out.stderr,
                )
        except Exception as e:
            await _log_ssh_action("exec", None, host, False, user_id, str(e))
            return ExecResult(
                host_id=hid,
                host_label=host.label,
                hostname=host.hostname,
                exit_code=-1,
                stdout="",
                stderr="",
                error=str(e),
            )

    # Same bound as health_check: a batch over the whole estate would otherwise
    # open one connection per host at once.
    sem = asyncio.Semaphore(_MAX_CONCURRENT_HOSTS)

    async def _bounded(hid: str) -> ExecResult:
        async with sem:
            return await _run_one(hid)

    return list(await asyncio.gather(*[_bounded(hid) for hid in host_ids]))


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
            now = datetime.now(UTC)
            async with get_session() as db_session:
                result = await db_session.execute(select(SshHost).where(SshHost.id == hid))
                h_obj = result.scalars().first()
                if h_obj:
                    h_obj.last_seen = now
                    h_obj.is_reachable = reachable
                    db_session.add(h_obj)
                    await db_session.commit()

            return {"host_id": hid, "host_label": host.label, "reachable": reachable}
        except Exception as e:
            async with get_session() as db_session:
                result = await db_session.execute(select(SshHost).where(SshHost.id == hid))
                h_obj = result.scalars().first()
                if h_obj:
                    h_obj.is_reachable = False
                    db_session.add(h_obj)
                    await db_session.commit()
            return {"host_id": hid, "host_label": host.label, "reachable": False, "error": str(e)}

    # Bounded. This path did no network I/O at all until _connect_to_host was
    # fixed, so an unbounded gather was harmless; now one request opens an SSH
    # connection per host simultaneously across the estate. The MFA collector
    # bounds its own fan-out the same way.
    sem = asyncio.Semaphore(_MAX_CONCURRENT_HOSTS)

    async def _bounded(hid: str) -> dict:
        async with sem:
            return await _check_one(hid)

    return list(await asyncio.gather(*[_bounded(hid) for hid in host_ids]))


# ═══════════════════════════════════════════════════════════════════════════
# SSH CONFIG GENERATION
# ═══════════════════════════════════════════════════════════════════════════


async def generate_ssh_config(host_ids: list[str] | None = None) -> str:
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
    key: SshKey | None,
    host: SshHost | None,
    success: bool,
    user_id: str | None = None,
    detail: str = "",
) -> None:
    now = datetime.now(UTC)
    async with get_session() as db_session:
        entry = SshAuditEntry(
            timestamp=now,
            action=action,
            key_name=key.name if key else None,
            key_fingerprint=key.fingerprint if key else None,
            host_label=host.label if host else None,
            hostname=host.hostname if host else None,
            port=host.port if host else None,
            success=success,
            user_id=user_id,
            detail=detail[:1000],
        )
        db_session.add(entry)
        await db_session.commit()


async def get_audit_log(limit: int = 100, offset: int = 0) -> list[SshAuditEntry]:
    async with get_session() as db_session:
        result = await db_session.execute(
            select(SshAuditEntry).order_by(SshAuditEntry.id.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())
