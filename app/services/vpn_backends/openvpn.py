"""OpenVPN backend — supports multiple simultaneous connections via tags."""
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Connection registry: tag → subprocess
_processes: dict[str, asyncio.subprocess.Process] = {}


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

    conf_fd = tempfile.NamedTemporaryFile(suffix=f"-{tag[:8]}.ovpn", delete=False)
    conf_path = Path(conf_fd.name)
    conf_fd.write(content.encode())
    conf_fd.close()

    # Write credentials if provided
    auth_path = None
    if config.get("username") and config.get("password"):
        auth_fd = tempfile.NamedTemporaryFile(suffix=".auth", delete=False)
        auth_path = Path(auth_fd.name)
        auth_fd.write(f"{config['username']}\n{config['password']}\n".encode())
        auth_fd.close()

    log_path = Path(f"/tmp/msp-openvpn-{tag[:8]}.log")
    cmd = ["openvpn", "--config", str(conf_path), "--log", str(log_path)]
    if auth_path:
        cmd.extend(["--auth-user-pass", str(auth_path)])
    if not config.get("full_tunnel"):
        cmd.extend(["--pull-filter", "ignore", "redirect-gateway"])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await asyncio.sleep(5)
        if proc.returncode is not None:
            err_detail = ""
            if log_path.exists():
                err_detail = log_path.read_text()[-500:]
            return {"ok": False, "error": f"OpenVPN exited (rc={proc.returncode})", "log": err_detail}
        _processes[tag] = proc
        return {"ok": True}
    except FileNotFoundError:
        return {"ok": False, "error": "openvpn ikke funnet — installer med: sudo apt install openvpn"}


async def disconnect(tag: str = "default") -> dict:
    proc = _processes.pop(tag, None)
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
    return {"ok": True}


async def get_status(tag: str = "default") -> dict:
    proc = _processes.get(tag)
    if proc and proc.returncode is None:
        return {"connected": True, "pid": proc.pid}
    return {"connected": False}


async def get_stats(tag: str = "default") -> dict:
    log = Path(f"/tmp/msp-openvpn-{tag[:8]}.log")
    if not log.exists():
        return {"bytes_sent": 0, "bytes_received": 0}
    try:
        content = log.read_text()
        proc = _processes.get(tag)
        return {"connected": proc is not None and proc.returncode is None, "log_tail": content[-500:]}
    except Exception:
        return {"connected": False}
