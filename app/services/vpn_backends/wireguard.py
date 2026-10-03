"""WireGuard VPN backend.

Uses `wg` and `ip` CLI tools. The manager refuses the operation before this
module is called when the process lacks CAP_NET_ADMIN; it never passes private
keys to an unshipped executable or attempts privilege elevation with sudo.
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from app.core.exceptions import ValidationError
from app.core.messages import invalid
from app.core.validation import (
    reject_line_breaks,
    validate_cidr,
    validate_hostname,
    validate_identifier,
    validate_int_range,
    validate_ip_interface,
    validate_port,
    validate_wireguard_endpoint,
    validate_wireguard_key,
)

logger = logging.getLogger(__name__)

# Profile fields this backend understands. Anything else is refused rather
# than carried along, so nothing unexpected can reach the config file.
_INTERFACE_FIELDS = frozenset(
    {"addresses", "dns", "mtu", "listen_port", "private_key", "peers", "split_routes"}
)
_PEER_FIELDS = frozenset(
    {"public_key", "endpoint", "allowed_ips", "preshared_key", "persistent_keepalive"}
)

# The only directives _build_conf writes. wg-quick also understands PreUp,
# PostUp, PreDown, PostDown (run through a shell) and SaveConfig (writes the
# file back); none of those may ever appear in a generated config.
_ALLOWED_DIRECTIVES = frozenset(
    {
        "Address",
        "DNS",
        "MTU",
        "ListenPort",
        "PrivateKey",
        "PublicKey",
        "Endpoint",
        "AllowedIPs",
        "PresharedKey",
        "PersistentKeepalive",
    }
)


async def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a subprocess and return (rc, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def connect(config: dict, interface: str = "wg-msp0") -> dict:
    return await _connect_direct(config, interface)


async def _connect_direct(config: dict, interface: str) -> dict:
    # Check if wg-quick is available
    rc, _, _ = await _run(["which", "wg-quick"])
    if rc != 0:
        return {
            "ok": False,
            "error": "WireGuard (wg-quick) er ikke installert. Installer med: sudo pacman -S wireguard-tools",
        }

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
        rc, _out, err = await _run(["wg-quick", "up", str(conf_path)])
        if rc != 0:
            return {"ok": False, "error": f"wg-quick up feilet: {err}"}
        return {"ok": True, "interface": interface}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def disconnect(interface: str = "wg-msp0") -> dict:
    validate_identifier(interface, "interface", max_length=15)
    rc, _out, err = await _run(["wg-quick", "down", interface])
    if rc != 0 and "not found" not in err.lower():
        return {"ok": False, "error": f"wg-quick down feilet: {err}"}
    return {"ok": True}


async def get_status(interface: str = "wg-msp0") -> dict:
    rc, out, _err = await _run(["wg", "show", interface, "dump"])
    if rc != 0:
        return {"connected": False}
    lines = out.strip().split("\n")
    if len(lines) < 2:
        return {"connected": True, "peers": 0}
    return {
        "connected": True,
        "peers": len(lines) - 1,
        "raw": out,
    }


async def get_stats(interface: str = "wg-msp0") -> dict:
    rc, out, _err = await _run(["wg", "show", interface, "transfer"])
    if rc != 0:
        return {"bytes_sent": 0, "bytes_received": 0}
    total_rx, total_tx = 0, 0
    for line in out.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 3:
            total_rx += int(parts[1])
            total_tx += int(parts[2])
    return {"bytes_sent": total_tx, "bytes_received": total_rx}


def _string_list(value, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list | tuple):
        raise invalid("err_field_not_list", field=field)
    return [reject_line_breaks(item, field) for item in value]


def _dns_entry(value: str) -> str:
    # wg-quick takes resolver IPs and search domains on the same line.
    return validate_hostname(value, "dns")


def validate_config(config: dict, *, require_private_key: bool) -> dict:
    """Return a normalised copy of a WireGuard profile config, or raise.

    Run when a profile is saved and again when the config file is built, so a
    stored value that predates this check still cannot reach wg-quick.
    """
    if not isinstance(config, dict):
        raise invalid("err_field_not_object", field="WireGuard-konfigurasjonen")
    unknown = sorted(set(config) - _INTERFACE_FIELDS)
    if unknown:
        raise invalid("err_unknown_fields", field="WireGuard", names=", ".join(unknown))

    clean: dict = {
        "addresses": [
            validate_ip_interface(a, "address")
            for a in _string_list(config.get("addresses"), "addresses")
        ],
        "dns": [_dns_entry(d) for d in _string_list(config.get("dns"), "dns")],
        "peers": [],
    }
    if config.get("mtu") not in (None, ""):
        clean["mtu"] = validate_int_range(config["mtu"], "mtu", 576, 9200)
    if config.get("listen_port") not in (None, ""):
        clean["listen_port"] = validate_port(config["listen_port"], "listen_port")
    if config.get("private_key"):
        clean["private_key"] = validate_wireguard_key(config["private_key"], "private_key")
    elif require_private_key:
        raise invalid("err_wg_no_private_key")
    if config.get("split_routes"):
        clean["split_routes"] = [
            validate_cidr(r, "split_routes")
            for r in _string_list(config["split_routes"], "split_routes")
        ]

    peers = config.get("peers") or []
    if not isinstance(peers, list | tuple):
        raise invalid("err_field_not_list", field="peers")
    for peer in peers:
        if not isinstance(peer, dict):
            raise invalid("err_field_not_object", field="peer")
        unknown = sorted(set(peer) - _PEER_FIELDS)
        if unknown:
            raise invalid("err_unknown_fields", field="peer", names=", ".join(unknown))
        out = {"public_key": validate_wireguard_key(peer.get("public_key"), "public_key")}
        if peer.get("endpoint"):
            out["endpoint"] = validate_wireguard_endpoint(peer["endpoint"], "endpoint")
        out["allowed_ips"] = [
            validate_cidr(ip, "allowed_ips")
            for ip in _string_list(peer.get("allowed_ips"), "allowed_ips")
        ]
        if peer.get("preshared_key"):
            out["preshared_key"] = validate_wireguard_key(peer["preshared_key"], "preshared_key")
        if peer.get("persistent_keepalive") not in (None, ""):
            out["persistent_keepalive"] = validate_int_range(
                peer["persistent_keepalive"], "persistent_keepalive", 0, 65535
            )
        clean["peers"].append(out)
    return clean


def _build_conf(config: dict) -> str:
    conf = validate_config(config, require_private_key=True)
    lines = ["[Interface]"]
    for addr in conf["addresses"]:
        lines.append(f"Address = {addr}")
    if conf["dns"]:
        lines.append(f"DNS = {', '.join(conf['dns'])}")
    if "mtu" in conf:
        lines.append(f"MTU = {conf['mtu']}")
    if "listen_port" in conf:
        lines.append(f"ListenPort = {conf['listen_port']}")
    lines.append(f"PrivateKey = {conf['private_key']}")
    for peer in conf["peers"]:
        lines.append("")
        lines.append("[Peer]")
        lines.append(f"PublicKey = {peer['public_key']}")
        if peer.get("endpoint"):
            lines.append(f"Endpoint = {peer['endpoint']}")
        if peer["allowed_ips"]:
            lines.append(f"AllowedIPs = {', '.join(peer['allowed_ips'])}")
        if peer.get("preshared_key"):
            lines.append(f"PresharedKey = {peer['preshared_key']}")
        if "persistent_keepalive" in peer:
            lines.append(f"PersistentKeepalive = {peer['persistent_keepalive']}")
    for line in lines:
        directive = line.split("=", 1)[0].strip()
        if line and line not in ("[Interface]", "[Peer]") and directive not in _ALLOWED_DIRECTIVES:
            raise ValidationError(f"WireGuard-direktivet {directive!r} er ikke tillatt")
    return "\n".join(lines) + "\n"
