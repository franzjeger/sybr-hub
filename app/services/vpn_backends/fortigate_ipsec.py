"""FortiGate IPsec VPN backend using strongSwan swanctl.

The manager calls this backend only when the process is already root.  Commands
therefore run directly: privilege elevation from a web request is never a
runtime fallback.
"""

import asyncio
import logging
from pathlib import Path

from app.core.exceptions import ValidationError
from app.core.validation import (
    quote_conf_value,
    validate_cidr,
    validate_host_list,
    validate_identifier,
)

logger = logging.getLogger(__name__)

CONF_DIR = Path("/etc/swanctl/conf.d")


def _conf_path(conn_name: str) -> Path:
    """Resolve the config path for *conn_name*, refusing to escape CONF_DIR.

    ``conn_name`` originates in a user-supplied VPN profile, and the write
    below is root-owned — so an unvalidated name is an arbitrary-file-write
    primitive. Validate the name, then verify
    the resolved path is still inside CONF_DIR as a second line of defence.
    """
    validate_identifier(conn_name, "conn_name", max_length=32)
    path = (CONF_DIR / f"{conn_name}.conf").resolve()
    if path.parent != CONF_DIR.resolve():
        raise ValidationError("Ugyldig conn_name")
    return path


async def _run(cmd, timeout=30):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def _write_conf(conf_text: str, conn_name: str) -> str | None:
    """Write swanctl config as the already-privileged service process."""
    conf_path = _conf_path(conn_name)

    try:
        conf_path.parent.mkdir(parents=True, exist_ok=True)
        conf_path.write_text(conf_text)
        return None
    except OSError as e:
        return f"Kunne ikke skrive config: {e}"


async def connect(config: dict, conn_name: str = "msp-fg") -> dict:
    """Connect FortiGate IPsec VPN via strongSwan."""
    validate_identifier(conn_name, "conn_name", max_length=32)

    # Check if swanctl is available
    rc, _, _ = await _run(["which", "swanctl"])
    if rc != 0:
        return {
            "ok": False,
            "error": "strongSwan (swanctl) er ikke installert. Installer med: sudo pacman -S strongswan",
        }

    # Kill any existing connection with same name first
    await _run(["swanctl", "--terminate", "--ike", conn_name], timeout=5)

    conf = _build_swanctl_conf(config, conn_name)
    err = await _write_conf(conf, conn_name)
    if err:
        return {"ok": False, "error": err}

    rc, _out, err = await _run(["swanctl", "--load-all"])
    if rc != 0:
        return {"ok": False, "error": f"swanctl load feilet: {err}"}

    try:
        rc, _out, err = await _run(["swanctl", "--initiate", "--child", conn_name], timeout=20)
    except TimeoutError:
        # Terminate the stuck IKE SA, but keep config for retry
        await _run(["swanctl", "--terminate", "--ike", conn_name], timeout=5)
        return {
            "ok": False,
            "error": "Tilkobling timet ut etter 20s — FortiGate svarer ikke. Sjekk host/PSK/ruter.",
        }

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
        rc, sas_out, _ = await _run(["swanctl", "--list-sas", "--ike", conn_name], timeout=5)
        if rc != 0:
            return

        # Parse virtual IP (e.g., [10.212.135.1])
        import re

        vip_match = re.search(r"\[(\d+\.\d+\.\d+\.\d+)\]", sas_out)
        if not vip_match:
            return
        vip = vip_match.group(1)

        # Get tunnel interface from table 220
        rc, rt_out, _ = await _run(["ip", "route", "show", "table", "220"], timeout=5)
        if rc != 0:
            return

        # Parse interface name (e.g., "dev tmpyf2u2sgl")
        iface_match = re.search(r"dev (\S+)", rt_out)
        if not iface_match:
            return
        iface = iface_match.group(1)

        # Add routes for each remote network
        routes = config.get("routes", [])
        for route in routes:
            route = route.strip()
            if route and route != "0.0.0.0/0":
                await _run(["ip", "route", "replace", route, "dev", iface, "src", vip], timeout=5)
                logger.debug("Added route: %s via %s src %s", route, iface, vip)
    except Exception as e:
        logger.warning("Failed to install routes: %s", e)


async def disconnect(conn_name: str = "msp-fg") -> dict:
    """Disconnect FortiGate IPsec VPN."""
    conf_path = _conf_path(conn_name)  # validates conn_name before any use
    await _run(["swanctl", "--terminate", "--ike", conn_name])

    # Remove config
    conf_path.unlink(missing_ok=True)

    await _run(["swanctl", "--load-all"])
    logger.info("FortiGate IPsec VPN disconnected: %s", conn_name)
    return {"ok": True}


async def get_status(conn_name: str = "msp-fg") -> dict:
    validate_identifier(conn_name, "conn_name", max_length=32)
    rc, out, _err = await _run(["swanctl", "--list-sas", "--ike", conn_name])
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

    Every interpolated value is validated or escaped first: this text is
    written to /etc/swanctl/conf.d as root, so an unescaped
    quote or newline in a PSK would let a profile inject config directives.
    """
    validate_identifier(conn_name, "conn_name", max_length=32)
    host = validate_host_list(config.get("host", ""), "host")
    username = quote_conf_value(config.get("username", ""), "username")
    password = quote_conf_value(config.get("password", ""), "password")
    psk = quote_conf_value(config.get("psk", ""), "psk")

    routes = config.get("routes", [])
    if not routes:
        remote_ts = "0.0.0.0/0,::/0"
    else:
        remote_ts = ",".join(validate_cidr(r, "routes") for r in routes)

    return f"""connections {{
  {conn_name} {{
    remote_addrs = {host}
    vips = 0.0.0.0
    proposals = aes128-sha256-ecp384,aes256-sha256-ecp384,aes128gcm16-prfsha256-ecp384,aes256gcm16-prfsha384-ecp521,chacha20poly1305-prfsha256-ecp384
    local {{
      auth = eap-mschapv2
      id = "{username}"
      eap_id = "{username}"
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
    id = "{username}"
    secret = "{password}"
  }}
}}
"""
