"""Async SSH session wrapper with trust-on-first-use host-key verification.

Used to reach network devices (FortiGate CLI, UniFi APs) that don't expose
the operation over a REST API.

Host keys are pinned on first connection and stored in
``DATA_DIR/known_hosts``. A *changed* key is refused — that is the signal
that something is intercepting the connection, and these sessions carry
firewall admin passwords. Passing ``known_hosts=None`` to asyncssh (the
previous behaviour at every call site) disables the check entirely and
accepts any key, every time.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.core.config import DATA_DIR
from app.core.exceptions import IntegrationError

log = logging.getLogger(__name__)

KNOWN_HOSTS_PATH = DATA_DIR / "known_hosts"

# Guards the read-modify-write of the known_hosts file.
_known_hosts_lock = asyncio.Lock()


@dataclass
class CommandResult:
    """Outcome of a single remote command."""
    exit_code: int
    stdout: str
    stderr: str = ""


def _host_entry(hostname: str, port: int) -> str:
    """Return the known_hosts host token for *hostname*:*port*."""
    return hostname if port == 22 else f"[{hostname}]:{port}"


def _read_known_hosts() -> dict[str, str]:
    """Return {host_token: "keytype key"} from the pinned host-key store."""
    if not KNOWN_HOSTS_PATH.exists():
        return {}
    entries: dict[str, str] = {}
    for line in KNOWN_HOSTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 2)
        if len(parts) >= 3:
            entries[parts[0]] = f"{parts[1]} {parts[2]}"
    return entries


def _append_known_host(host_token: str, key_line: str) -> None:
    KNOWN_HOSTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(KNOWN_HOSTS_PATH, "a", encoding="utf-8") as fh:
        fh.write(f"{host_token} {key_line}\n")
    KNOWN_HOSTS_PATH.chmod(0o600)


def forget_host(hostname: str, port: int = 22) -> bool:
    """Drop the pinned key for a host. Returns True if an entry was removed.

    Needed after a legitimate device replacement or firmware reflash, which
    is the honest way to accept a new key — rather than disabling the check.
    """
    if not KNOWN_HOSTS_PATH.exists():
        return False
    token = _host_entry(hostname, port)
    lines = KNOWN_HOSTS_PATH.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if ln.split(None, 1)[:1] != [token]]
    if len(kept) == len(lines):
        return False
    KNOWN_HOSTS_PATH.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    KNOWN_HOSTS_PATH.chmod(0o600)
    log.info("Removed pinned host key for %s", token)
    return True


async def _pin_host_key(conn, host_token: str) -> None:
    """Record the server's key so subsequent connections are verified."""
    key = conn.get_server_host_key()
    if key is None:
        log.warning("No server host key available for %s — nothing pinned", host_token)
        return
    key_line = key.export_public_key().decode().strip()
    async with _known_hosts_lock:
        if host_token in _read_known_hosts():
            return  # another task pinned it first
        _append_known_host(host_token, key_line)
    log.info("Pinned SSH host key for %s (trust on first use)", host_token)


async def open_verified_connection(
    hostname: str,
    username: str,
    password: str | None = None,
    port: int = 22,
    client_keys: list | None = None,
    connect_timeout: int = 20,
):
    """Open a raw asyncssh connection with host-key verification applied.

    Exposed separately from :class:`SshSession` for the call sites that need
    an interactive shell (``conn.create_process``) rather than one-shot
    commands — they get the same pinning instead of ``known_hosts=None``.
    """
    import asyncssh

    from app.core.validation import validate_host

    validate_host(hostname, "ssh_host")
    host_token = _host_entry(hostname, port)

    async with _known_hosts_lock:
        pinned = _read_known_hosts().get(host_token)

    common = {
        "host": hostname,
        "port": port,
        "username": username,
        "password": password,
        "client_keys": client_keys,
        "connect_timeout": connect_timeout,
    }

    try:
        if pinned:
            keytype, keydata = pinned.split(None, 1)
            return await asyncssh.connect(
                known_hosts=([_import_key(keytype, keydata)], [], []), **common
            )
        # Trust on first use: accept whatever key the device presents, then
        # pin it so any later change is caught.
        conn = await asyncssh.connect(known_hosts=None, **common)
        await _pin_host_key(conn, host_token)
        return conn
    except asyncssh.HostKeyNotVerifiable as e:
        log.error("Host key mismatch for %s — refusing to connect: %s", host_token, e)
        raise IntegrationError(
            f"Vertsnøkkelen for {host_token} har endret seg siden forrige "
            f"tilkobling. Hvis enheten er byttet eller reinstallert, fjern "
            f"den lagrede nøkkelen og prøv igjen."
        ) from e


class SshSession:
    """An open SSH connection to one device.

    Use via the classmethod::

        async with await SshSession.connect(hostname=..., username=...) as s:
            result = await s.exec("get system status", timeout=15)
    """

    def __init__(self, conn, hostname: str, port: int) -> None:
        self._conn = conn
        self.hostname = hostname
        self.port = port

    # ── Lifecycle ────────────────────────────────────────────────────────────

    @classmethod
    async def connect(
        cls,
        hostname: str,
        username: str,
        password: str | None = None,
        port: int = 22,
        client_keys: list | None = None,
        connect_timeout: int = 20,
    ) -> SshSession:
        """Open a session, verifying the host key against the pinned store."""
        conn = await open_verified_connection(
            hostname=hostname,
            username=username,
            password=password,
            port=port,
            client_keys=client_keys,
            connect_timeout=connect_timeout,
        )
        return cls(conn, hostname, port)

    async def close(self) -> None:
        self._conn.close()
        try:
            await self._conn.wait_closed()
        except Exception as e:  # pragma: no cover - best-effort teardown
            log.debug("Error while closing SSH connection to %s: %s", self.hostname, e)

    async def __aenter__(self) -> SshSession:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # ── Commands ─────────────────────────────────────────────────────────────

    async def exec(self, command: str, timeout: int = 30) -> CommandResult:
        """Run *command* and return its exit code plus captured output."""
        try:
            result = await asyncio.wait_for(
                self._conn.run(command, check=False), timeout=timeout
            )
        except TimeoutError as e:
            raise IntegrationError(
                f"SSH-kommandoen mot {self.hostname} timet ut etter {timeout}s"
            ) from e

        return CommandResult(
            exit_code=result.exit_status if result.exit_status is not None else -1,
            stdout=_as_text(result.stdout),
            stderr=_as_text(result.stderr),
        )

    # ── Remote filesystem ────────────────────────────────────────────────────
    #
    # ssh_manager's key push and revoke have always called these four methods.
    # They were never implemented, so every non-sudo push raised AttributeError
    # in the SFTP strategy, fell through to the exec strategy, and raised it
    # again on the very first line — the feature could not work at all, and the
    # per-host result simply reported the AttributeError as the host's error.

    async def get_home(self) -> str:
        """Return the connected user's home directory on the remote host."""
        result = await self.exec('printf "%s\\n" "$HOME"', timeout=10)
        home = result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else ""
        if result.exit_code != 0 or not home.startswith("/"):
            raise IntegrationError(
                f"Fant ikke hjemmekatalogen til brukeren på {self.hostname}"
            )
        return home

    @asynccontextmanager
    async def _sftp(self):
        """Open a short-lived SFTP client.

        Devices without an SFTP subsystem — BusyBox, UniFi, OpenWrt — raise
        here, which is exactly what the exec fallback in ssh_manager expects.
        """
        client = await self._conn.start_sftp_client()
        try:
            yield client
        finally:
            client.exit()
            try:
                await client.wait_closed()
            except Exception as e:  # pragma: no cover - best-effort teardown
                log.debug("Error closing SFTP client to %s: %s", self.hostname, e)

    async def sftp_mkdir(self, path: str, mode: int = 0o700) -> None:
        """Create *path*, including parents. Existing directories are fine."""
        import asyncssh

        async with self._sftp() as sftp:
            try:
                await sftp.makedirs(path, mode=mode, exist_ok=True)
            except asyncssh.SFTPFailure:
                # Some servers report an existing directory as a plain failure
                # rather than SFTPFileAlreadyExists; confirm before giving up.
                if not await sftp.isdir(path):
                    raise

    async def sftp_read(self, path: str) -> bytes | None:
        """Return the contents of *path*, or None if it does not exist."""
        import asyncssh

        async with self._sftp() as sftp:
            try:
                async with sftp.open(path, "rb") as f:
                    return await f.read()
            except (asyncssh.SFTPNoSuchFile, asyncssh.SFTPNoSuchPath):
                return None

    async def sftp_write(self, path: str, data: bytes, mode: int = 0o600) -> None:
        """Write *data* to *path*, replacing whatever is there."""
        async with self._sftp() as sftp:
            async with sftp.open(path, "wb") as f:
                await f.write(data)
            try:
                await sftp.chmod(path, mode)
            except Exception as e:  # pragma: no cover - best-effort
                log.debug("Could not chmod %s on %s: %s", path, self.hostname, e)


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _import_key(keytype: str, keydata: str):
    import asyncssh

    return asyncssh.import_public_key(f"{keytype} {keydata}")
