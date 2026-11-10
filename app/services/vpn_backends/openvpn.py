"""OpenVPN backend — supports multiple simultaneous connections via tags."""

import asyncio
import logging
import re
import shlex
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Connection registry: tag → subprocess
_processes: dict[str, asyncio.subprocess.Process] = {}
# Temp files owned by each connection, removed on disconnect. Without this,
# the config and the plaintext `username\npassword` auth file were written to
# /tmp with delete=False and never cleaned up.
_tempfiles: dict[str, list[Path]] = {}

# Config directives that make OpenVPN execute an external program. A profile
# is operator-supplied data, not code — an uploaded .ovpn carrying
# `script-security 2` plus an `up` hook would otherwise run arbitrary
# commands on the host.
_SCRIPT_DIRECTIVES = (
    "up",
    "down",
    "route-up",
    "route-pre-down",
    "ipchange",
    "client-connect",
    "client-disconnect",
    "learn-address",
    "auth-user-pass-verify",
    "tls-verify",
    "script-security",
    "plugin",
)
# Longest-first so `route-up` isn't shadowed by `up`, and the lookahead
# requires whitespace or end-of-line rather than a word boundary — otherwise
# legitimate options like `up-delay` and `up-restart` would be rejected.
_SCRIPT_DIRECTIVE_RE = re.compile(
    r"^[ \t]*({})(?=[ \t]|$)".format(
        "|".join(re.escape(d) for d in sorted(_SCRIPT_DIRECTIVES, key=len, reverse=True))
    ),
    re.IGNORECASE | re.MULTILINE,
)


# Every directive a client profile may contain. Anything else is refused: a
# denylist missed directives hidden inside <connection> blocks and quoted
# names, and every OpenVPN release adds options. Hooks (_SCRIPT_DIRECTIVES)
# and path-taking options (_FILE_DIRECTIVES) are absent on purpose; the
# key-material options stay subject to _INLINE_ONLY.
_ALLOWED = frozenset(
    {
        "allow-compression",
        "allow-pull-fqdn",
        "allow-recursive-routing",
        "auth",
        "auth-nocache",
        "auth-retry",
        "auth-user-pass",
        "bind",
        "block-ipv6",
        "block-outside-dns",
        "ca",
        "cert",
        "cipher",
        "client",
        "comp-lzo",
        "compress",
        "connect-retry",
        "connect-retry-max",
        "connect-timeout",
        "crl-verify",
        "data-ciphers",
        "data-ciphers-fallback",
        "dev",
        "dev-type",
        "dh",
        "dhcp-option",
        "disable-dco",
        "down-pre",
        "ecdh-curve",
        "explicit-exit-notify",
        "extra-certs",
        "float",
        "fragment",
        "hand-window",
        "http-proxy",
        "http-proxy-option",
        "http-proxy-retry",
        "http-proxy-timeout",
        "http-proxy-user-pass",
        "ifconfig",
        "ifconfig-ipv6",
        "ifconfig-nowarn",
        "ignore-unknown-option",
        "inactive",
        "keepalive",
        "key",
        "key-direction",
        "key-method",
        "link-mtu",
        "local",
        "lport",
        "mssfix",
        "mtu-disc",
        "mtu-test",
        "mute",
        "mute-replay-warnings",
        "ncp-ciphers",
        "ncp-disable",
        "nobind",
        "ns-cert-type",
        "peer-fingerprint",
        "persist-key",
        "persist-local-ip",
        "persist-remote-ip",
        "persist-tun",
        "ping",
        "ping-exit",
        "ping-restart",
        "ping-timer-rem",
        "pkcs12",
        "port",
        "proto",
        "proto-force",
        "pull",
        "pull-filter",
        "push-peer-info",
        "rcvbuf",
        "redirect-gateway",
        "redirect-private",
        "remote",
        "remote-cert-eku",
        "remote-cert-ku",
        "remote-cert-tls",
        "remote-random",
        "remote-random-hostname",
        "reneg-bytes",
        "reneg-pkts",
        "reneg-sec",
        "replay-window",
        "resolv-retry",
        "route",
        "route-delay",
        "route-gateway",
        "route-ipv6",
        "route-metric",
        "route-nopull",
        "rport",
        "secret",
        "server-poll-timeout",
        "setenv",
        "setenv-safe",
        "single-session",
        "sndbuf",
        "socks-proxy",
        "socks-proxy-retry",
        "static-challenge",
        "tls-auth",
        "tls-cert-profile",
        "tls-cipher",
        "tls-ciphersuites",
        "tls-client",
        "tls-crypt",
        "tls-crypt-v2",
        "tls-exit",
        "tls-groups",
        "tls-remote",
        "tls-timeout",
        "tls-version-max",
        "tls-version-min",
        "topology",
        "tran-window",
        "tun-ipv6",
        "tun-mtu",
        "tun-mtu-extra",
        "txqueuelen",
        "up-delay",
        "up-restart",
        "verb",
        "verify-hash",
        "verify-x509-name",
        "x509-username-field",
    }
)
# <tag> blocks that carry inline file content, not directives.
_INLINE_BLOCKS = frozenset(
    {
        "auth-user-pass",
        "ca",
        "cert",
        "crl-verify",
        "dh",
        "extra-certs",
        "http-proxy-user-pass",
        "key",
        "peer-fingerprint",
        "pkcs12",
        "secret",
        "tls-auth",
        "tls-crypt",
        "tls-crypt-v2",
    }
)


class _Unparseable(ValueError):
    """The profile cannot be read the way OpenVPN would read it."""


def _directives(content: str) -> list[tuple[str, list[str]]]:
    """Every directive in *content* as OpenVPN sees it: name and arguments.

    Tokenised with OpenVPN's quoting rules, so a quoted name ("status") is the
    name OpenVPN acts on. Directives inside <connection> blocks are included;
    inline file blocks are skipped. A block that is unknown, nested where it
    cannot be, or unterminated makes the whole profile unparseable.
    """
    found: list[tuple[str, list[str]]] = []
    block: str | None = None
    in_connection = False
    for raw in content.splitlines():
        line = raw.strip()
        if block:
            if line.lower() == f"</{block}>":
                block = None
            continue
        if not line or line[0] in "#;":
            continue
        if line.startswith("<"):
            tag = line[1:-1].strip().lower() if line.endswith(">") else ""
            if tag == "connection" and not in_connection:
                in_connection = True
            elif tag == "/connection" and in_connection:
                in_connection = False
            elif tag in _INLINE_BLOCKS:
                block = tag
            else:
                raise _Unparseable(line)
            continue
        try:
            words = shlex.split(line, posix=True)
        except ValueError as e:
            raise _Unparseable(line) from e
        if not words:
            continue
        name = words[0][2:] if words[0].startswith("--") else words[0]
        found.append((name, words[1:]))
    if block or in_connection:
        raise _Unparseable(f"<{block or 'connection'}>")
    return found


def _reject_script_directives(content: str) -> str | None:
    """Return the offending directive if *content* can execute programs."""
    match = _SCRIPT_DIRECTIVE_RE.search(content)
    if match:
        return match.group(1)
    try:
        directives = _directives(content)
    except _Unparseable:
        return None  # refused by _reject_unknown_directives
    for name, _ in directives:
        if name.lower() in _SCRIPT_DIRECTIVES:
            return name
    return None


# Directives that read or write files on the hub, or run a program, by path.
# A profile can name any file the service can read: `auth-user-pass <file>`
# and a proxy auth file send its first lines to the remote end, `config`
# pulls another file in, and the log tail shown on a failed connect echoes
# what was read.
_FILE_DIRECTIVES = frozenset(
    {
        "askpass",
        "auth-gen-token-secret",
        "cd",
        "chroot",
        "client-config-dir",
        "config",
        "daemon",
        "ifconfig-pool-persist",
        "iproute",
        "log",
        "log-append",
        "management",
        "replay-persist",
        "status",
        "tmp-dir",
        "writepid",
    }
)
# Key material is accepted only inline: `ca [inline]` with a <ca> block.
_INLINE_ONLY = frozenset(
    {
        "ca",
        "capath",
        "cert",
        "crl-verify",
        "dh",
        "extra-certs",
        "http-proxy-user-pass",
        "key",
        "pkcs12",
        "secret",
        "tls-auth",
        "tls-crypt",
        "tls-crypt-v2",
    }
)


def _reject_file_directives(content: str) -> str | None:
    """Return the first directive that reaches the hub's filesystem by path."""
    try:
        directives = _directives(content)
    except _Unparseable:
        return None  # refused by _reject_unknown_directives
    for directive, args in directives:
        name = directive.lower()
        if name in _FILE_DIRECTIVES:
            return directive
        if name in _INLINE_ONLY and args and args[0].lower() != "[inline]":
            return directive
        if name == "auth-user-pass" and args:
            return directive
        if name == "http-proxy" and len(args) >= 3 and args[2].lower() not in ("auto", "auto-nct"):
            return directive
        if name == "socks-proxy" and len(args) >= 3:
            return directive
    return None


def _reject_unknown_directives(content: str) -> str | None:
    """Return the first line or directive outside the client allowlist."""
    try:
        directives = _directives(content)
    except _Unparseable as e:
        return str(e)
    for directive, _ in directives:
        if directive.lower() not in _ALLOWED:
            return directive
    return None


def refusal_reason(content: str) -> str | None:
    """A message for an operator if *content* must not be run, else None."""
    offending = _reject_script_directives(content)
    if offending:
        return (
            f"Konfigurasjonen inneholder direktivet '{offending}', som lar "
            f"OpenVPN kjøre vilkårlige kommandoer på serveren. Fjern det og "
            f"prøv igjen."
        )
    offending = _reject_file_directives(content)
    if offending:
        return (
            f"Konfigurasjonen inneholder direktivet '{offending}', som lar "
            f"OpenVPN lese eller skrive filer på serveren. Lim inn nøkler og "
            f"sertifikater som innebygde blokker, og fjern direktivet."
        )
    offending = _reject_unknown_directives(content)
    if offending:
        return (
            f"Konfigurasjonen inneholder '{offending}', som huben ikke godtar i "
            f"en klientprofil. Fjern linjen, eller be om at direktivet vurderes "
            f"for listen over tillatte direktiver."
        )
    return None


def _cleanup_tempfiles(tag: str) -> None:
    """Remove the temp files belonging to *tag* — they hold credentials."""
    import shutil

    owned = _tempfiles.pop(tag, [])
    workdirs = {p.parent for p in owned}
    for path in owned:
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Could not remove OpenVPN temp file %s: %s", path, e)
    for workdir in workdirs:
        shutil.rmtree(workdir, ignore_errors=True)


async def _run(cmd, timeout=30):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def connect(config: dict, tag: str = "default") -> dict:
    if tag in _processes and _processes[tag].returncode is None:
        return {"ok": False, "error": "This connection is already active"}

    # Content only: a server-side config_file path would let a profile read
    # any file the service can.
    content = config.get("config_content", "")
    if not content:
        return {"ok": False, "error": "No OpenVPN config provided"}

    reason = refusal_reason(content)
    if reason:
        logger.warning("Refused OpenVPN profile %s: %s", tag, reason)
        return {"ok": False, "error": reason}

    # Everything lives in one private directory (0700) rather than loose in
    # /tmp, so the auth file's credentials aren't world-listable and the log
    # path can't be pre-created as a symlink by another local user.
    workdir = Path(tempfile.mkdtemp(prefix=f"msp-openvpn-{tag[:8]}-"))
    owned: list[Path] = []
    _tempfiles[tag] = owned

    conf_path = workdir / "profile.ovpn"
    conf_path.write_text(content)
    conf_path.chmod(0o600)
    owned.append(conf_path)

    # Write credentials if provided
    auth_path = None
    if config.get("username") and config.get("password"):
        auth_path = workdir / "auth.txt"
        auth_path.write_text(f"{config['username']}\n{config['password']}\n")
        auth_path.chmod(0o600)
        owned.append(auth_path)

    log_path = workdir / "openvpn.log"
    owned.append(log_path)

    cmd = ["openvpn", "--config", str(conf_path), "--log", str(log_path)]
    if auth_path:
        cmd.extend(["--auth-user-pass", str(auth_path)])
    if not config.get("full_tunnel"):
        cmd.extend(["--pull-filter", "ignore", "redirect-gateway"])
    # Belt and braces alongside the directive check above: passed after
    # --config so it overrides anything the profile tried to set.
    cmd.extend(["--script-security", "0"])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await asyncio.sleep(5)
        if proc.returncode is not None:
            err_detail = ""
            if log_path.exists():
                err_detail = log_path.read_text()[-500:]
            _cleanup_tempfiles(tag)
            return {
                "ok": False,
                "error": f"OpenVPN exited (rc={proc.returncode})",
                "log": err_detail,
            }
        _processes[tag] = proc
        return {"ok": True}
    except FileNotFoundError:
        _cleanup_tempfiles(tag)
        return {
            "ok": False,
            "error": "openvpn ikke funnet — installer med: sudo apt install openvpn",
        }


async def disconnect(tag: str = "default") -> dict:
    proc = _processes.pop(tag, None)
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except TimeoutError:
            proc.kill()
    _cleanup_tempfiles(tag)
    return {"ok": True}


async def get_status(tag: str = "default") -> dict:
    proc = _processes.get(tag)
    if proc and proc.returncode is None:
        return {"connected": True, "pid": proc.pid}
    return {"connected": False}


async def get_stats(tag: str = "default") -> dict:
    logs = [p for p in _tempfiles.get(tag, []) if p.name == "openvpn.log"]
    if not logs or not logs[0].exists():
        return {"bytes_sent": 0, "bytes_received": 0}
    try:
        content = logs[0].read_text()
        proc = _processes.get(tag)
        return {
            "connected": proc is not None and proc.returncode is None,
            "log_tail": content[-500:],
        }
    except OSError:
        return {"connected": False}
