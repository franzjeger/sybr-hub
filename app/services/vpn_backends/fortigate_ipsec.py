"""FortiGate IPsec VPN backend using strongSwan swanctl.

Uses sudo for privileged operations (writing config, loading/initiating).
On production servers, configure passwordless sudo for swanctl commands
or use the msp-vpn-helper systemd service.
"""
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CONF_DIR = Path("/etc/swanctl/conf.d")


async def _run(cmd, timeout=30):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def _sudo_run(cmd, timeout=30):
    """Run command with sudo prefix."""
    return await _run(["sudo"] + cmd, timeout)


async def _write_conf(conf_text: str, conn_name: str) -> Optional[str]:
    """Write swanctl config, trying direct first then sudo."""
    conf_path = CONF_DIR / f"{conn_name}.conf"

    # Try direct write first
    try:
        conf_path.parent.mkdir(parents=True, exist_ok=True)
        conf_path.write_text(conf_text)
        return None
    except PermissionError:
        pass

    # Fallback: write via sudo tee
    try:
        await _sudo_run(["mkdir", "-p", str(CONF_DIR)])
        proc = await asyncio.create_subprocess_exec(
            "sudo", "tee", str(conf_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(conf_text.encode()), timeout=10
        )
        if proc.returncode != 0:
            return f"Kunne ikke skrive config: {stderr.decode()}"
        return None
    except Exception as e:
        return f"Kunne ikke skrive config: {e}"


async def connect(config: dict, conn_name: str = "msp-fg") -> dict:
    """Connect FortiGate IPsec VPN via strongSwan."""
    # Check if swanctl is available
    rc, _, _ = await _run(["which", "swanctl"])
    if rc != 0:
        return {"ok": False, "error": "strongSwan (swanctl) er ikke installert. Installer med: sudo pacman -S strongswan"}

    # Kill any existing connection with same name first
    await _sudo_run(["swanctl", "--terminate", "--ike", conn_name], timeout=5)

    conf = _build_swanctl_conf(config, conn_name)
    err = await _write_conf(conf, conn_name)
    if err:
        return {"ok": False, "error": err}

    rc, out, err = await _sudo_run(["swanctl", "--load-all"])
    if rc != 0:
        return {"ok": False, "error": f"swanctl load feilet: {err}"}

    try:
        rc, out, err = await _sudo_run(["swanctl", "--initiate", "--child", conn_name], timeout=20)
    except (asyncio.TimeoutError, TimeoutError):
        # Terminate the stuck IKE SA, but keep config for retry
        await _sudo_run(["swanctl", "--terminate", "--ike", conn_name], timeout=5)
        return {"ok": False, "error": "Tilkobling timet ut etter 20s — FortiGate svarer ikke. Sjekk host/PSK/ruter."}

    if rc != 0:
        return {"ok": False, "error": f"swanctl initiate feilet: {err}"}

    # Add routes to main routing table so normal apps can reach remote networks
    await _install_routes(config, conn_name)

    logger.info("FortiGate IPsec VPN connected: %s", conn_name)
    return {"ok": True, "connection": conn_name}


async def _install_routes(config: dict, conn_name: str) -> None:
    """Install routes in main table after connection.

    strongSwan puts routes in table 220, but normal apps use the main table.
    We find the virtual IP and tunnel interface from swanctl output and add
    routes with the correct source IP.
    """
    try:
        rc, sas_out, _ = await _sudo_run(["swanctl", "--list-sas", "--ike", conn_name], timeout=5)
        if rc != 0:
            return

        # Parse virtual IP (e.g., [10.212.135.1])
        import re
        vip_match = re.search(r'\[(\d+\.\d+\.\d+\.\d+)\]', sas_out)
        if not vip_match:
            return
        vip = vip_match.group(1)

        # Get tunnel interface from table 220
        rc, rt_out, _ = await _sudo_run(["ip", "route", "show", "table", "220"], timeout=5)
        if rc != 0:
            return

        # Parse interface name (e.g., "dev tmpyf2u2sgl")
        iface_match = re.search(r'dev (\S+)', rt_out)
        if not iface_match:
            return
        iface = iface_match.group(1)

        # Add routes for each remote network
        routes = config.get("routes", [])
        for route in routes:
            route = route.strip()
            if route and route != "0.0.0.0/0":
                await _sudo_run(["ip", "route", "replace", route, "dev", iface, "src", vip], timeout=5)
                logger.debug("Added route: %s via %s src %s", route, iface, vip)
    except Exception as e:
        logger.warning("Failed to install routes: %s", e)


async def disconnect(conn_name: str = "msp-fg") -> dict:
    """Disconnect FortiGate IPsec VPN."""
    await _sudo_run(["swanctl", "--terminate", "--ike", conn_name])

    # Remove config
    conf_path = CONF_DIR / f"{conn_name}.conf"
    try:
        conf_path.unlink(missing_ok=True)
    except PermissionError:
        await _sudo_run(["rm", "-f", str(conf_path)])

    await _sudo_run(["swanctl", "--load-all"])
    logger.info("FortiGate IPsec VPN disconnected: %s", conn_name)
    return {"ok": True}


async def get_status(conn_name: str = "msp-fg") -> dict:
    rc, out, err = await _sudo_run(["swanctl", "--list-sas", "--ike", conn_name])
    if rc != 0 or not out.strip():
        return {"connected": False}
    return {"connected": True, "raw": out}


async def get_stats(conn_name: str = "msp-fg") -> dict:
    status = await get_status(conn_name)
    return {"connected": status.get("connected", False)}


def _build_swanctl_conf(config: dict, conn_name: str) -> str:
    """Generate swanctl config matching SuperManager's proven format.

    Key differences from naive config:
    - vips = 0.0.0.0 for mode-config virtual IP assignment
    - Multiple proposals including ECP groups (not just modp2048)
    - remote auth = psk (not pubkey)
    - start_action = none (initiate manually)
    - IKE PSK secret listed before EAP secret
    """
    host = config.get("host", "")
    username = config.get("username", "")
    password = config.get("password", "")
    psk = config.get("psk", "")

    routes = config.get("routes", [])
    if not routes:
        remote_ts = "0.0.0.0/0,::/0"
    else:
        remote_ts = ",".join(routes)

    return f"""connections {{
  {conn_name} {{
    remote_addrs = {host}
    vips = 0.0.0.0
    proposals = aes128-sha256-ecp384,aes256-sha256-ecp384,aes128gcm16-prfsha256-ecp384,aes256gcm16-prfsha384-ecp521,chacha20poly1305-prfsha256-ecp384
    local {{
      auth = eap-mschapv2
      id = {username}
      eap_id = {username}
    }}
    remote {{
      auth = psk
    }}
    children {{
      {conn_name} {{
        remote_ts = {remote_ts}
        start_action = none
      }}
    }}
  }}
}}
secrets {{
  ike-{conn_name} {{
    secret = "{psk}"
  }}
  eap-{conn_name} {{
    id = {username}
    secret = "{password}"
  }}
}}
"""
