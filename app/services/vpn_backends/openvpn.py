"""OpenVPN backend — supports multiple simultaneous connections via tags."""
import asyncio
import logging
import re
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
    "up", "down", "route-up", "route-pre-down", "ipchange", "client-connect",
    "client-disconnect", "learn-address", "auth-user-pass-verify",
    "tls-verify", "script-security", "plugin",
)
# Longest-first so `route-up` isn't shadowed by `up`, and the lookahead
# requires whitespace or end-of-line rather than a word boundary — otherwise
# legitimate options like `up-delay` and `up-restart` would be rejected.
_SCRIPT_DIRECTIVE_RE = re.compile(
    r"^[ \t]*(%s)(?=[ \t]|$)"
    % "|".join(re.escape(d) for d in sorted(_SCRIPT_DIRECTIVES, key=len, reverse=True)),
    re.IGNORECASE | re.MULTILINE,
)


def _reject_script_directives(content: str) -> str | None:
    """Return the offending directive if *content* can execute programs."""
    match = _SCRIPT_DIRECTIVE_RE.search(content)
    return match.group(1) if match else None


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
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def connect(config: dict, tag: str = "default") -> dict:
    if tag in _processes and _processes[tag].returncode is None:
        return {"ok": False, "error": "This connection is already active"}

    # Write config to temp file
    content = config.get("config_content", "")
    if not content and config.get("config_file"):
        p = Path(config["config_file"])
        if p.exists():
            content = p.read_text()
    if not content:
        return {"ok": False, "error": "No OpenVPN config provided"}

    offending = _reject_script_directives(content)
    if offending:
        logger.warning("Refused OpenVPN profile %s: contains '%s' directive", tag, offending)
        return {
            "ok": False,
            "error": (
                f"Konfigurasjonen inneholder direktivet '{offending}', som lar "
                f"OpenVPN kjøre vilkårlige kommandoer på serveren. Fjern det og "
                f"prøv igjen."
            ),
        }

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
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await asyncio.sleep(5)
        if proc.returncode is not None:
            err_detail = ""
            if log_path.exists():
                err_detail = log_path.read_text()[-500:]
            _cleanup_tempfiles(tag)
            return {"ok": False, "error": f"OpenVPN exited (rc={proc.returncode})", "log": err_detail}
        _processes[tag] = proc
        return {"ok": True}
    except FileNotFoundError:
        _cleanup_tempfiles(tag)
        return {"ok": False, "error": "openvpn ikke funnet — installer med: sudo apt install openvpn"}


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
        return {"connected": proc is not None and proc.returncode is None, "log_tail": content[-500:]}
    except OSError:
        return {"connected": False}
