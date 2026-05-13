"""VPN manager — profile CRUD and connection state machine."""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.config import DATA_DIR
from app.core.database import get_db
from app.core.encryption import encrypted_read_bytes, encrypted_write_bytes
from app.models.vpn import VpnProfile, VpnProtocol, VpnState

logger = logging.getLogger(__name__)

VPN_SECRETS_DIR = DATA_DIR / "vpn_secrets"

# Connection registry — supports multiple simultaneous VPN connections
# {profile_id: {"state": VpnState, "interface": str|None, "lock": asyncio.Lock}}
_connections: dict[str, dict] = {}
_registry_lock = asyncio.Lock()


def _get_conn(profile_id: str) -> dict | None:
    """Get connection state for a profile, or None."""
    return _connections.get(profile_id)


def _is_connected(profile_id: str) -> bool:
    conn = _connections.get(profile_id)
    return conn is not None and conn["state"] in (VpnState.connected, VpnState.connecting)



# ── Profile CRUD ──

async def list_profiles() -> list[VpnProfile]:
    async with get_db() as conn:
        async with conn.execute("SELECT * FROM vpn_profiles ORDER BY name") as cur:
            return [_row_to_profile(r) for r in await cur.fetchall()]

async def get_profile(profile_id: str) -> Optional[VpnProfile]:
    async with get_db() as conn:
        async with conn.execute("SELECT * FROM vpn_profiles WHERE id = ?", (profile_id,)) as cur:
            row = await cur.fetchone()
            return _row_to_profile(row) if row else None

async def create_profile(name, protocol, config, description="", full_tunnel=False, customer_id=None, created_by=None) -> VpnProfile:
    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    # Store secrets separately
    secrets = _extract_secrets(config, protocol)
    if secrets:
        _store_secrets(pid, secrets)
    config_clean = _strip_secrets(config, protocol)

    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO vpn_profiles (id,name,description,protocol,config,full_tunnel,auto_connect,kill_switch,customer_id,created_at,updated_at,created_by) VALUES (?,?,?,?,?,?,0,0,?,?,?,?)",
            (pid, name, description, protocol.value if hasattr(protocol,'value') else protocol,
             json.dumps(config_clean), int(full_tunnel), customer_id, now, now, created_by))
        await conn.commit()
    return await get_profile(pid)

ALLOWED_VPN_FIELDS = frozenset({"name", "description", "config", "full_tunnel", "auto_connect", "kill_switch", "protocol", "customer_id"})


async def update_profile(profile_id, **kwargs) -> Optional[VpnProfile]:
    fields, values = [], []
    for k, v in kwargs.items():
        if k not in ALLOWED_VPN_FIELDS:
            continue
        if v is None and k != "customer_id": continue
        if k == "config":
            fields.append("config = ?"); values.append(json.dumps(v))
        elif k in ("full_tunnel","auto_connect","kill_switch"):
            fields.append(k + " = ?"); values.append(int(v))
        elif k == "protocol":
            fields.append("protocol = ?"); values.append(v.value if hasattr(v,'value') else v)
        else:
            fields.append(k + " = ?"); values.append(v)
    if not fields: return await get_profile(profile_id)
    fields.append("updated_at = ?"); values.append(datetime.now(timezone.utc).isoformat())
    values.append(profile_id)
    async with get_db() as conn:
        await conn.execute(f"UPDATE vpn_profiles SET {','.join(fields)} WHERE id = ?", values)
        await conn.commit()
    return await get_profile(profile_id)

async def delete_profile(profile_id) -> bool:
    if _is_connected(profile_id):
        await disconnect(profile_id)
    async with get_db() as conn:
        cur = await conn.execute("DELETE FROM vpn_profiles WHERE id = ?", (profile_id,))
        await conn.commit()
    import shutil
    sd = VPN_SECRETS_DIR / profile_id
    if sd.exists(): shutil.rmtree(str(sd))
    return cur.rowcount > 0

# ── Connect / Disconnect ──

async def connect(profile_id: str) -> dict:
    async with _registry_lock:
        if _is_connected(profile_id):
            return {"ok": False, "error": "This profile is already connected."}

        profile = await get_profile(profile_id)
        if not profile:
            return {"ok": False, "error": "Profile not found"}

        # Register connection as connecting
        _connections[profile_id] = {"state": VpnState.connecting, "interface": None, "lock": asyncio.Lock()}

    config = json.loads(profile.config) if isinstance(profile.config, str) else profile.config
    secrets = _load_secrets(profile_id)
    config.update(secrets)

    try:
        if profile.protocol == VpnProtocol.wireguard:
            from app.services.vpn_backends.wireguard import connect as wg_connect
            iface = f"wg-{profile_id[:8]}"
            result = await wg_connect(config, interface=iface)
        elif profile.protocol == VpnProtocol.fortigate_ipsec:
            from app.services.vpn_backends.fortigate_ipsec import connect as fg_connect
            conn_name = config.get("conn_name", "msp-fg")
            result = await fg_connect(config, conn_name=conn_name)
        elif profile.protocol == VpnProtocol.openvpn:
            from app.services.vpn_backends.openvpn import connect as ovpn_connect
            result = await ovpn_connect(config, tag=profile_id)
        elif profile.protocol == VpnProtocol.azure:
            del _connections[profile_id]
            return {"ok": False, "error": "Azure VPN krever innlogging — klikk 'Koble til' for å åpne innloggingsvinduet"}
        else:
            result = {"ok": False, "error": f"Unknown protocol: {profile.protocol}"}

        if result.get("ok"):
            _connections[profile_id]["state"] = VpnState.connected
            _connections[profile_id]["interface"] = result.get("interface")
            logger.info("VPN connected: %s (%s)", profile.name, profile.protocol.value)
        else:
            _connections[profile_id]["state"] = VpnState.error
            logger.warning("VPN connect failed: %s — %s", profile.name, result.get("error"))
        return result
    except Exception as e:
        _connections[profile_id]["state"] = VpnState.error
        return {"ok": False, "error": str(e)}

async def disconnect(profile_id: str | None = None) -> dict:
    """Disconnect a specific VPN profile, or the first active one if not specified."""
    # Find the target connection
    if profile_id and profile_id in _connections:
        target_id = profile_id
    elif profile_id is None:
        # Backwards compat: disconnect first active connection
        target_id = next((pid for pid, c in _connections.items() if c["state"] == VpnState.connected), None)
    else:
        return {"ok": True, "msg": "Not connected"}

    if not target_id or target_id not in _connections:
        return {"ok": True, "msg": "Already disconnected"}

    conn = _connections[target_id]
    conn["state"] = VpnState.disconnecting

    profile = await get_profile(target_id)
    try:
        protocol = profile.protocol if profile else None
        iface = conn.get("interface")

        if protocol == VpnProtocol.wireguard:
            from app.services.vpn_backends.wireguard import disconnect as wg_disc
            result = await wg_disc(iface or "wg-msp0")
        elif protocol == VpnProtocol.fortigate_ipsec:
            from app.services.vpn_backends.fortigate_ipsec import disconnect as fg_disc
            profile_cfg = json.loads(profile.config) if isinstance(profile.config, str) else profile.config
            conn_name = profile_cfg.get("conn_name", "msp-fg")
            result = await fg_disc(conn_name)
        elif protocol in (VpnProtocol.openvpn, VpnProtocol.azure):
            from app.services.vpn_backends.openvpn import disconnect as ovpn_disc
            result = await ovpn_disc(tag=target_id)
        else:
            result = {"ok": True}

        del _connections[target_id]
        logger.info("VPN disconnected: %s", profile.name if profile else target_id)
        return result
    except Exception as e:
        conn["state"] = VpnState.error
        return {"ok": False, "error": str(e)}

async def get_status() -> dict:
    """Return status of all VPN connections."""
    active = []
    for pid, conn in _connections.items():
        active.append({
            "profile_id": pid,
            "state": conn["state"].value,
            "interface": conn.get("interface"),
        })

    # Backwards compat: also return primary connection fields
    primary = next((c for c in active if c["state"] == "connected"), None)
    return {
        "state": primary["state"] if primary else "disconnected",
        "profile_id": primary["profile_id"] if primary else None,
        "interface": primary["interface"] if primary else None,
        "connections": active,
    }

async def get_stats(profile_id: str | None = None) -> dict:
    """Get stats for a specific connection, or the first active one."""
    if profile_id and profile_id in _connections:
        conn = _connections[profile_id]
    else:
        # Find first connected
        conn = None
        for pid, c in _connections.items():
            if c["state"] == VpnState.connected:
                conn = c
                profile_id = pid
                break
    if not conn or conn["state"] != VpnState.connected:
        return {}
    profile = await get_profile(profile_id) if profile_id else None
    if not profile:
        return {}

    import asyncio
    import os
    import subprocess
    import time

    iface = conn.get("interface")
    # Auto-detect interface if not set or not found
    if not iface or not os.path.exists(f"/sys/class/net/{iface}"):
        for candidate in ["tun0", "tun1", "wg-msp0", "wg0", "ipsec0", "ppp0"]:
            if os.path.exists(f"/sys/class/net/{candidate}"):
                iface = candidate
                break
    stats = {"protocol": profile.protocol.value, "profile_name": profile.name}

    # Protocol-specific stats (async backends)
    if profile.protocol == VpnProtocol.wireguard:
        from app.services.vpn_backends.wireguard import get_stats as wg_stats
        wg = await wg_stats(iface or "wg-msp0")
        stats.update(wg)

    # ── Collect remaining stats via executor (blocking subprocess/file I/O) ──
    loop = asyncio.get_event_loop()
    sync_stats = await loop.run_in_executor(
        None, _collect_interface_stats_sync, profile, iface,
    )
    stats.update(sync_stats)
    return stats


def _collect_interface_stats_sync(profile, iface) -> dict:
    """Blocking I/O for VPN interface stats — runs in thread pool."""
    import os
    import subprocess
    import time
    stats = {}

    # ── strongSwan/IPsec stats (FortiGate IPsec) ──
    if profile.protocol == VpnProtocol.fortigate_ipsec:
        try:
            r = subprocess.run(["sudo", "swanctl", "--list-sas"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                for line in r.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("local") and "[" in line and "@" in line:
                        # local 'user' @ 1.2.3.4[4500] [10.x.x.x]
                        if "[" in line.split("@")[-1]:
                            parts = line.split("[")
                            if len(parts) >= 3:
                                stats["local_ip"] = parts[-1].rstrip("]")
                            stats["public_ip"] = line.split("@")[1].split("[")[0].strip()
                    elif line.startswith("remote") and "@" in line:
                        stats["remote_ip"] = line.split("@")[-1].split("[")[0].strip()
                    elif "established" in line and "ago" in line:
                        stats["uptime"] = line.split("established")[1].split(",")[0].strip()
                    elif line.startswith("in ") and "bytes" in line:
                        for p in line.split(","):
                            p = p.strip()
                            if "bytes" in p:
                                try: stats["rx_bytes"] = int(p.split()[0])
                                except (ValueError, IndexError) as e: logger.debug("Failed to parse IPsec rx_bytes: %s", e)
                            if "packets" in p:
                                try: stats["rx_packets"] = int(p.split()[0])
                                except (ValueError, IndexError) as e: logger.debug("Failed to parse IPsec rx_packets: %s", e)
                    elif line.startswith("out ") and "bytes" in line:
                        for p in line.split(","):
                            p = p.strip()
                            if "bytes" in p:
                                try: stats["tx_bytes"] = int(p.split()[0])
                                except (ValueError, IndexError) as e: logger.debug("Failed to parse IPsec tx_bytes: %s", e)
                            if "packets" in p:
                                try: stats["tx_packets"] = int(p.split()[0])
                                except (ValueError, IndexError) as e: logger.debug("Failed to parse IPsec tx_packets: %s", e)
                    elif line.startswith("remote") and "/" in line and "@" not in line:
                        stats["remote_subnets"] = line.replace("remote", "").strip().split()
                    elif line.startswith("local") and "/" in line and "@" not in line:
                        stats["local_subnet"] = line.replace("local", "").strip()
                    elif "AES" in line and "/" in line and "established" not in line and line.startswith("AES"):
                        stats["encryption"] = line
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            logger.debug("Failed to parse strongSwan/IPsec stats: %s", e)

    # ── Common: Interface IP, peer, MTU ──
    if iface:
        try:
            r = subprocess.run(["ip", "-d", "addr", "show", iface],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("inet "):
                        parts = line.split()
                        stats["local_ip"] = parts[1].split("/")[0]
                        stats["subnet"] = parts[1]
                        if "peer" in parts:
                            stats["remote_ip"] = parts[parts.index("peer") + 1].split("/")[0]
                    if "mtu" in line:
                        for i, w in enumerate(line.split()):
                            if w == "mtu" and i + 1 < len(line.split()):
                                stats["mtu"] = line.split()[i + 1]
                    if line.startswith("link/") and "peer" in line:
                        # point-to-point peer
                        pass
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            logger.debug("Failed to parse interface IP/MTU stats: %s", e)

        # TX/RX bytes
        try:
            tx_path = f"/sys/class/net/{iface}/statistics/tx_bytes"
            rx_path = f"/sys/class/net/{iface}/statistics/rx_bytes"
            if os.path.exists(tx_path):
                stats["tx_bytes"] = int(open(tx_path).read().strip())
                stats["rx_bytes"] = int(open(rx_path).read().strip())
        except (OSError, ValueError) as e:
            logger.debug("Failed to read sysfs TX/RX bytes: %s", e)

        # Interface uptime (from operstate change time)
        try:
            carrier_path = f"/sys/class/net/{iface}/carrier"
            if os.path.exists(carrier_path):
                mtime = os.path.getmtime(carrier_path)
                up_secs = int(time.time() - mtime)
                from app.core.utils import format_uptime
                stats["uptime"] = format_uptime(up_secs)
        except (OSError, ValueError) as e:
            logger.debug("Failed to determine interface uptime: %s", e)

    # ── Routes via this interface ──
    if iface:
        try:
            r = subprocess.run(["ip", "route", "show", "dev", iface],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                routes = [l.strip().split()[0] for l in r.stdout.strip().splitlines() if l.strip()]
                stats["routes"] = routes[:10]  # Max 10
                stats["route_count"] = len(routes)
        except (subprocess.SubprocessError, OSError) as e:
            logger.debug("Failed to parse routes: %s", e)

    # ── DNS servers (from resolv.conf or systemd-resolved) ──
    try:
        r = subprocess.run(["resolvectl", "dns", iface or ""],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            dns_line = r.stdout.strip().split(":", 1)[-1].strip()
            stats["dns_servers"] = dns_line
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("Failed to query DNS servers: %s", e)

    # ── Default gateway ──
    try:
        r = subprocess.run(["ip", "route", "show", "default"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.strip().splitlines():
                if iface and iface in line:
                    parts = line.split()
                    if "via" in parts:
                        stats["gateway"] = parts[parts.index("via") + 1]
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("Failed to query default gateway: %s", e)

    return stats

# ── Profile Import ──

async def import_profile(name: str, file_content: str, file_type: str = "auto", created_by=None) -> VpnProfile:
    if file_type == "auto":
        file_type = _detect_type(file_content)

    if file_type == "wireguard":
        config = _parse_wireguard_conf(file_content)
        protocol = VpnProtocol.wireguard
    elif file_type == "openvpn":
        config = {"config_content": file_content}
        protocol = VpnProtocol.openvpn
    elif file_type == "azure":
        config = _parse_azure_xml(file_content)
        protocol = VpnProtocol.azure
    else:
        from app.core.exceptions import ValidationError
        raise ValidationError(f"Unknown file type: {file_type}")

    return await create_profile(name, protocol, config, created_by=created_by)

def _detect_type(content: str) -> str:
    if "[Interface]" in content and "[Peer]" in content:
        return "wireguard"
    # Azure VPN — check for azurevpnconfig.xml tags
    if any(tag in content for tag in ("<AzVpnProfile>", "<VpnProfile>", "<audience>", "<serversecret>", "<VpnServer>", "VPN_SETTINGS_SEPARATOR")):
        return "azure"
    if "client" in content and ("remote " in content or "proto " in content):
        return "openvpn"
    return "openvpn"

def _parse_wireguard_conf(content: str) -> dict:
    config = {"addresses": [], "dns": [], "peers": []}
    current_peer = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#") or not line: continue
        if line == "[Interface]": current_peer = None; continue
        if line == "[Peer]": current_peer = {}; config["peers"].append(current_peer); continue
        if "=" not in line: continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if current_peer is None:
            if key == "Address": config["addresses"].extend(v.strip() for v in val.split(","))
            elif key == "DNS": config["dns"].extend(v.strip() for v in val.split(","))
            elif key == "MTU": config["mtu"] = int(val)
            elif key == "ListenPort": config["listen_port"] = int(val)
            elif key == "PrivateKey": config["private_key"] = val
        else:
            if key == "PublicKey": current_peer["public_key"] = val
            elif key == "Endpoint": current_peer["endpoint"] = val
            elif key == "AllowedIPs": current_peer["allowed_ips"] = [v.strip() for v in val.split(",")]
            elif key == "PresharedKey": current_peer["preshared_key"] = val
            elif key == "PersistentKeepalive": current_peer["persistent_keepalive"] = int(val)
    return config

def _parse_azure_xml(content: str) -> dict:
    """Parse Azure VPN config from one or two XML files.

    Supports:
    - Combined: azurevpnconfig.xml + VPN_SETTINGS_SEPARATOR + VpnSettings.xml
    - Single azurevpnconfig.xml (basic — no CA cert or routes)

    Matches SuperManager's parse_azure_xml logic.
    """
    import re

    azure_xml = content
    vpn_settings_xml = ""
    if "<!-- VPN_SETTINGS_SEPARATOR -->" in content:
        parts = content.split("<!-- VPN_SETTINGS_SEPARATOR -->", 1)
        azure_xml = parts[0].strip()
        vpn_settings_xml = parts[1].strip()

    def xml_tag(xml, tag):
        m = re.search(f"<{tag}[^>]*>([^<]+)</{tag}>", xml, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def xml_tags_all(xml, tag):
        return [m.group(1).strip() for m in re.finditer(f"<{tag}[^>]*>([^<]+)</{tag}>", xml, re.IGNORECASE)]

    # azurevpnconfig.xml fields
    client_id = xml_tag(azure_xml, "audience") or ""
    tenant_url = xml_tag(azure_xml, "tenant") or xml_tag(azure_xml, "issuer") or ""
    tenant_id = tenant_url.rstrip("/").rsplit("/", 1)[-1] if "/" in tenant_url else tenant_url
    gateway_fqdn = xml_tag(azure_xml, "fqdn") or xml_tag(vpn_settings_xml, "VpnServer") or ""
    server_secret_hex = xml_tag(azure_xml, "serversecret") or ""

    # DNS
    dns_servers = []
    csv_dns = xml_tag(vpn_settings_xml, "CustomDnsServers") if vpn_settings_xml else None
    if csv_dns:
        dns_servers = [s.strip() for s in csv_dns.split(",") if s.strip()]
    if not dns_servers:
        dns_servers = xml_tags_all(azure_xml, "dnsserver")

    # CA certificate from VpnSettings.xml
    ca_cert_pem = ""
    if vpn_settings_xml:
        for s in xml_tags_all(vpn_settings_xml, "string"):
            if len(s) > 100:
                import base64
                import textwrap
                try:
                    base64.b64decode(s)
                    ca_cert_pem = f"-----BEGIN CERTIFICATE-----\n{textwrap.fill(s, 64)}\n-----END CERTIFICATE-----"
                except Exception as e:
                    logger.debug("Failed to decode CA cert as base64: %s", e)
                break

    # Routes from VpnSettings.xml
    routes = []
    routes_csv = xml_tag(vpn_settings_xml, "Routes") if vpn_settings_xml else None
    if routes_csv:
        routes = [r.strip() for r in routes_csv.split(",") if r.strip()]

    return {
        "gateway_fqdn": gateway_fqdn,
        "tenant_id": tenant_id,
        "client_id": client_id,
        "server_secret_hex": server_secret_hex,
        "ca_cert_pem": ca_cert_pem,
        "routes": routes,
        "dns_servers": dns_servers,
    }

# ── Secrets ──

def _extract_secrets(config: dict, protocol) -> dict:
    secrets = {}
    p = protocol.value if hasattr(protocol, 'value') else protocol
    if p == "wireguard":
        if "private_key" in config: secrets["private_key"] = config["private_key"]
        for i, peer in enumerate(config.get("peers", [])):
            if "preshared_key" in peer: secrets[f"peer_{i}_psk"] = peer["preshared_key"]
    elif p == "fortigate_ipsec":
        for k in ("password", "psk"):
            if k in config: secrets[k] = config[k]
    elif p == "openvpn":
        if "password" in config: secrets["password"] = config["password"]
    elif p == "azure":
        if "server_secret_hex" in config: secrets["server_secret_hex"] = config["server_secret_hex"]
    return secrets

def _strip_secrets(config: dict, protocol) -> dict:
    c = dict(config)
    p = protocol.value if hasattr(protocol, 'value') else protocol
    for k in ("private_key", "password", "psk", "server_secret_hex"):
        c.pop(k, None)
    if "peers" in c:
        c["peers"] = [{kk: vv for kk, vv in peer.items() if kk != "preshared_key"} for peer in c["peers"]]
    return c

def _store_secrets(profile_id: str, secrets: dict):
    d = VPN_SECRETS_DIR / profile_id
    d.mkdir(parents=True, exist_ok=True)
    encrypted_write_bytes(d / "secrets.json", json.dumps(secrets).encode())

def _load_secrets(profile_id: str) -> dict:
    p = VPN_SECRETS_DIR / profile_id / "secrets.json"
    if not p.exists(): return {}
    try:
        return json.loads(encrypted_read_bytes(p).decode())
    except Exception as e:
        logger.warning("Failed to load VPN secrets for %s: %s", profile_id, e)
        return {}

def _row_to_profile(row) -> VpnProfile:
    return VpnProfile(
        id=row["id"], name=row["name"], description=row["description"],
        protocol=VpnProtocol(row["protocol"]),
        config=json.loads(row["config"]),
        full_tunnel=bool(row["full_tunnel"]),
        auto_connect=bool(row["auto_connect"]),
        kill_switch=bool(row["kill_switch"]),
        customer_id=row["customer_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        created_by=row["created_by"],
    )
