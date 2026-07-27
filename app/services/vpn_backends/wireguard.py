"""WireGuard VPN backend.

Uses `wg` and `ip` CLI tools. On systems where the web server lacks
CAP_NET_ADMIN, operations fall back to a privileged helper at
/usr/local/bin/msp-vpn-helper (if installed).
"""
import asyncio
import json
import logging
import tempfile
from pathlib import Path

from app.core.validation import validate_identifier

logger = logging.getLogger(__name__)

HELPER_PATH = Path("/usr/local/bin/msp-vpn-helper")

async def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a subprocess and return (rc, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    return proc.returncode or 0, stdout.decode(), stderr.decode()

async def _helper_cmd(action: str, **kwargs) -> dict:
    """Send a command to the privileged helper."""
    if not HELPER_PATH.exists():
        raise RuntimeError("VPN helper not installed at " + str(HELPER_PATH))
    payload = json.dumps({"action": action, **kwargs})
    rc, out, err = await _run([str(HELPER_PATH), "--json", payload])
    if rc != 0:
        raise RuntimeError(f"Helper failed: {err}")
    return json.loads(out) if out.strip() else {}

async def connect(config: dict, interface: str = "wg-msp0") -> dict:
    # Try direct first, fall back to helper
    try:
        return await _connect_direct(config, interface)
    except PermissionError:
        return await _helper_cmd("wg_connect", config=config, interface=interface)

async def _connect_direct(config: dict, interface: str) -> dict:
    # Check if wg-quick is available
    rc, _, _ = await _run(["which", "wg-quick"])
    if rc != 0:
        return {"ok": False, "error": "WireGuard (wg-quick) er ikke installert. Installer med: sudo pacman -S wireguard-tools"}

    validate_identifier(interface, "interface", max_length=15)

    # wg-quick derives the interface name from the config *filename*, so the
    # file has to be named after the interface we intend to create. Using a
    # random tempfile name (the previous behaviour) created an interface with
    # an unrelated name, which meant disconnect() and get_stats() both looked
    # up a device that never existed and the tunnel was left up.
    workdir = Path(tempfile.mkdtemp(prefix="msp-wg-"))
    conf_path = workdir / f"{interface}.conf"
    conf_path.write_text(_build_conf(config))
    conf_path.chmod(0o600)  # contains the private key
    try:
        # Try with sudo first (most common case for web server)
        rc, out, err = await _run(["sudo", "wg-quick", "up", str(conf_path)])
        if rc != 0:
            # Try without sudo as fallback
            rc, out, err = await _run(["wg-quick", "up", str(conf_path)])
            if rc != 0:
                if "permission" in err.lower() or "operation not permitted" in err.lower():
                    raise PermissionError(err)
                return {"ok": False, "error": f"wg-quick up feilet: {err}"}
        return {"ok": True, "interface": interface}
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)

async def disconnect(interface: str = "wg-msp0") -> dict:
    validate_identifier(interface, "interface", max_length=15)
    try:
        rc, out, err = await _run(["wg-quick", "down", interface])
        if rc != 0 and "not found" not in err.lower():
            return await _helper_cmd("wg_disconnect", interface=interface)
        return {"ok": True}
    except Exception:
        return await _helper_cmd("wg_disconnect", interface=interface)

async def get_status(interface: str = "wg-msp0") -> dict:
    rc, out, err = await _run(["wg", "show", interface, "dump"])
    if rc != 0:
        return {"connected": False}
    lines = out.strip().split('\n')
    if len(lines) < 2:
        return {"connected": True, "peers": 0}
    return {
        "connected": True,
        "peers": len(lines) - 1,
        "raw": out,
    }

async def get_stats(interface: str = "wg-msp0") -> dict:
    rc, out, err = await _run(["wg", "show", interface, "transfer"])
    if rc != 0:
        return {"bytes_sent": 0, "bytes_received": 0}
    total_rx, total_tx = 0, 0
    for line in out.strip().split('\n'):
        parts = line.split('\t')
        if len(parts) >= 3:
            total_rx += int(parts[1])
            total_tx += int(parts[2])
    return {"bytes_sent": total_tx, "bytes_received": total_rx}

def _build_conf(config: dict) -> str:
    lines = ["[Interface]"]
    for addr in config.get("addresses", []):
        lines.append(f"Address = {addr}")
    if config.get("dns"):
        lines.append(f"DNS = {', '.join(config['dns'])}")
    if config.get("mtu"):
        lines.append(f"MTU = {config['mtu']}")
    if config.get("listen_port"):
        lines.append(f"ListenPort = {config['listen_port']}")
    private_key = config.get("private_key")
    if not private_key:
        from app.core.exceptions import ValidationError
        raise ValidationError("WireGuard private key is required but not provided — inject from secrets before building config")
    lines.append(f"PrivateKey = {private_key}")
    for peer in config.get("peers", []):
        lines.append("\n[Peer]")
        lines.append(f"PublicKey = {peer['public_key']}")
        if peer.get("endpoint"):
            lines.append(f"Endpoint = {peer['endpoint']}")
        if peer.get("allowed_ips"):
            lines.append(f"AllowedIPs = {', '.join(peer['allowed_ips'])}")
        if peer.get("preshared_key"):
            lines.append(f"PresharedKey = {peer['preshared_key']}")
        if peer.get("persistent_keepalive"):
            lines.append(f"PersistentKeepalive = {peer['persistent_keepalive']}")
    return "\n".join(lines) + "\n"
