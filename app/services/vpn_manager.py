"""VPN manager — profile CRUD and connection state machine."""

import asyncio
import base64
import copy
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import select

from app.core.config import DATA_DIR
from app.core.encryption import encrypted_read_bytes, encrypted_write_bytes
from app.core.exceptions import ConflictError, ValidationError
from app.core.messages import invalid
from app.core.orm import get_session
from app.core.validation import reject_line_breaks
from app.models.vpn import VpnProfile, VpnProtocol, VpnState
from app.services.vpn_backends import azure as azure_backend
from app.services.vpn_backends import openvpn as ovpn_backend
from app.services.vpn_backends import wireguard as wg_backend

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
    async with get_session() as session:
        result = await session.execute(select(VpnProfile).order_by(VpnProfile.name))
        profiles = list(result.scalars().all())
    return [await _migrate_plaintext_secrets(p) for p in profiles]


async def get_profile(profile_id: str) -> VpnProfile | None:
    async with get_session() as session:
        profile = await session.get(VpnProfile, profile_id)
    return await _migrate_plaintext_secrets(profile) if profile else None


async def create_profile(
    name, protocol, config, description="", full_tunnel=False, customer_id=None, created_by=None
) -> VpnProfile:
    pid = str(uuid.uuid4())
    now = datetime.now(UTC)
    config = _validate_config(protocol, config, creating=True)
    config_clean, supplied, _carried = _split_secrets(config, strict=True)
    if supplied:
        _store_secrets(pid, supplied)

    profile = VpnProfile(
        id=pid,
        name=name,
        description=description,
        protocol=protocol,
        config=config_clean,
        full_tunnel=full_tunnel,
        customer_id=customer_id,
        created_at=now,
        updated_at=now,
        created_by=created_by,
    )
    async with get_session() as session:
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    return profile


ALLOWED_VPN_FIELDS = frozenset(
    {
        "name",
        "description",
        "config",
        "full_tunnel",
        "auto_connect",
        "kill_switch",
        "customer_id",
    }
)


async def update_profile(profile_id, **kwargs) -> tuple[VpnProfile | None, list[str]]:
    """Apply *kwargs* to a profile; return it and the secrets that were wiped.

    A new config replaces the stored one, but its secrets go through the same
    split as on create: a secret the request supplies replaces the stored one,
    and one it leaves out is kept, unless the config now points somewhere else
    (see _targets). Then the stored secret is wiped instead, so an edit cannot
    send a credential it never knew to a server of its choosing.
    """
    if await get_profile(profile_id) is None:  # migrates a legacy row first
        return None, []
    changes = {
        k: v
        for k, v in kwargs.items()
        if k in ALLOWED_VPN_FIELDS and (v is not None or k == "customer_id")
    }
    async with _secrets_lock, get_session() as session:
        profile = await session.get(VpnProfile, profile_id)
        if not profile:
            return None, []
        wiped: list[str] = []
        if "config" in changes:
            config = _validate_config(profile.protocol, changes["config"], creating=False)
            old_clean = _as_dict(profile.config)
            try:
                stored = _stored_values(_read_secrets(profile_id), old_clean)
            except Exception as e:
                logger.warning("Could not read VPN secrets for %s: %s", profile_id, e)
                raise ConflictError(
                    "De lagrede hemmelighetene for profilen kunne ikke leses, "
                    "så profilen ble ikke endret."
                ) from e
            clean, supplied, carried = _split_secrets(config, strict=True)
            retargeted = _targets(old_clean, profile.protocol) != _targets(clean, profile.protocol)
            new_store, wiped = _resolve_secrets(supplied, carried, stored, retargeted=retargeted)
            # Secrets before the row: if the row write fails, the old
            # target is left with at most fewer secrets, never a new
            # target with the old ones.
            _store_secrets(profile_id, new_store)
            changes["config"] = clean
        for k, v in changes.items():
            setattr(profile, k, v)
        if changes:
            profile.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(profile)
        return profile, wiped


async def delete_profile(profile_id) -> bool:
    if _is_connected(profile_id):
        await disconnect(profile_id)
    async with get_session() as session:
        profile = await session.get(VpnProfile, profile_id)
        if not profile:
            return False
        await session.delete(profile)
        await session.commit()

    import shutil

    sd = VPN_SECRETS_DIR / profile_id
    if sd.exists():
        shutil.rmtree(str(sd))
    return True


# ── Connect / Disconnect ──


def owner_of(profile_id: str) -> str:
    """Who opened this tunnel, or an empty string."""
    return str((_connections.get(profile_id) or {}).get("owned_by") or "")


def system_held() -> list[str]:
    """Profile ids currently held open by the system account.

    The collectors keep tunnels up to read statistics from customer sites. A
    technician tearing one down mid-collection breaks something nobody is
    watching, so the routes refuse while this is non-empty and say which.
    """
    from app.core.system_user import USERNAME

    return sorted(
        pid
        for pid, conn in _connections.items()
        if str(conn.get("owned_by") or "") == USERNAME
        and conn.get("state") in (VpnState.connected, VpnState.connecting)
    )


async def connect(profile_id: str, *, owned_by: str = "", access_token: str = "") -> dict:
    """Bring a profile's tunnel up.

    *access_token* is the Entra ID token an Azure profile needs; Azure goes
    through here too, so it shares the registry lock and state machine and two
    requests cannot both start the same tunnel.
    """
    async with _registry_lock:
        if _is_connected(profile_id):
            return {"ok": False, "error": "This profile is already connected."}

        profile = await get_profile(profile_id)
        if not profile:
            return {"ok": False, "error": "Profile not found"}

        from app.services.vpn_privileges import unavailable_reason

        privilege_error = unavailable_reason(profile.protocol)
        if privilege_error:
            return {
                "ok": False,
                "error": privilege_error,
                "error_type": "vpn_control_unavailable",
            }

        # Register connection as connecting
        _connections[profile_id] = {
            "state": VpnState.connecting,
            "interface": None,
            "lock": asyncio.Lock(),
            "owned_by": owned_by,
        }

    config, missing = _connect_config(profile, _load_secrets(profile_id))
    if missing:
        del _connections[profile_id]
        return _secrets_missing_result(missing)

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
            if not access_token:
                del _connections[profile_id]
                return {
                    "ok": False,
                    "error": "Azure VPN krever innlogging — klikk 'Koble til' for å åpne innloggingsvinduet",
                }
            result = await azure_backend.connect(config, access_token)
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
        target_id = next(
            (pid for pid, c in _connections.items() if c["state"] == VpnState.connected), None
        )
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

            profile_cfg = (
                json.loads(profile.config) if isinstance(profile.config, str) else profile.config
            )
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


async def get_status(profile_ids: set[str] | None = None) -> dict:
    """Return status of all VPN connections."""
    active = []
    for pid, conn in _connections.items():
        if profile_ids is not None and pid not in profile_ids:
            continue
        active.append(
            {
                "profile_id": pid,
                "state": conn["state"].value,
                "interface": conn.get("interface"),
            }
        )

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
    if profile_id is not None:
        conn = _connections.get(profile_id)
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
        None,
        _collect_interface_stats_sync,
        profile,
        iface,
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
            r = subprocess.run(
                ["swanctl", "--list-sas"], capture_output=True, text=True, timeout=10
            )
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
                                try:
                                    stats["rx_bytes"] = int(p.split()[0])
                                except (ValueError, IndexError) as e:
                                    logger.debug("Failed to parse IPsec rx_bytes: %s", e)
                            if "packets" in p:
                                try:
                                    stats["rx_packets"] = int(p.split()[0])
                                except (ValueError, IndexError) as e:
                                    logger.debug("Failed to parse IPsec rx_packets: %s", e)
                    elif line.startswith("out ") and "bytes" in line:
                        for p in line.split(","):
                            p = p.strip()
                            if "bytes" in p:
                                try:
                                    stats["tx_bytes"] = int(p.split()[0])
                                except (ValueError, IndexError) as e:
                                    logger.debug("Failed to parse IPsec tx_bytes: %s", e)
                            if "packets" in p:
                                try:
                                    stats["tx_packets"] = int(p.split()[0])
                                except (ValueError, IndexError) as e:
                                    logger.debug("Failed to parse IPsec tx_packets: %s", e)
                    elif line.startswith("remote") and "/" in line and "@" not in line:
                        stats["remote_subnets"] = line.replace("remote", "").strip().split()
                    elif line.startswith("local") and "/" in line and "@" not in line:
                        stats["local_subnet"] = line.replace("local", "").strip()
                    elif (
                        "AES" in line
                        and "/" in line
                        and "established" not in line
                        and line.startswith("AES")
                    ):
                        stats["encryption"] = line
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            logger.debug("Failed to parse strongSwan/IPsec stats: %s", e)

    # ── Common: Interface IP, peer, MTU ──
    if iface:
        try:
            r = subprocess.run(
                ["ip", "-d", "addr", "show", iface], capture_output=True, text=True, timeout=5
            )
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
                stats["tx_bytes"] = int(Path(tx_path).read_text().strip())
                stats["rx_bytes"] = int(Path(rx_path).read_text().strip())
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
            r = subprocess.run(
                ["ip", "route", "show", "dev", iface], capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                routes = [
                    line.strip().split()[0]
                    for line in r.stdout.strip().splitlines()
                    if line.strip()
                ]
                stats["routes"] = routes[:10]  # Max 10
                stats["route_count"] = len(routes)
        except (subprocess.SubprocessError, OSError) as e:
            logger.debug("Failed to parse routes: %s", e)

    # ── DNS servers (from resolv.conf or systemd-resolved) ──
    try:
        r = subprocess.run(
            ["resolvectl", "dns", iface or ""], capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0 and r.stdout.strip():
            dns_line = r.stdout.strip().split(":", 1)[-1].strip()
            stats["dns_servers"] = dns_line
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("Failed to query DNS servers: %s", e)

    # ── Default gateway ──
    try:
        r = subprocess.run(
            ["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5
        )
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


async def import_profile(
    name: str, file_content: str, file_type: str = "auto", created_by=None
) -> VpnProfile:
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
    if any(
        tag in content
        for tag in (
            "<AzVpnProfile>",
            "<VpnProfile>",
            "<audience>",
            "<serversecret>",
            "<VpnServer>",
            "VPN_SETTINGS_SEPARATOR",
        )
    ):
        return "azure"
    if "client" in content and ("remote " in content or "proto " in content):
        return "openvpn"
    return "openvpn"


# wg-quick runs these through a shell (or, for SaveConfig, writes the running
# state back over the file). An imported profile carrying one is refused:
# dropping the line would import something other than what was uploaded.
_WG_REFUSED_DIRECTIVES = frozenset({"preup", "postup", "predown", "postdown", "saveconfig"})


def _parse_wireguard_conf(content: str) -> dict:
    config = {"addresses": [], "dns": [], "peers": []}
    current_peer = None
    for raw in content.splitlines():
        # wg-quick drops everything after '#' and matches keys without case.
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.lower() == "[interface]":
            current_peer = None
            continue
        if line.lower() == "[peer]":
            current_peer = {}
            config["peers"].append(current_peer)
            continue
        if "=" not in line:
            continue
        name, val = line.split("=", 1)
        name, val = name.strip(), val.strip()
        key = name.lower()
        if key in _WG_REFUSED_DIRECTIVES:
            raise ValidationError(
                f"WireGuard-filen inneholder '{name}', som lar wg-quick kjøre kommandoer "
                f"på serveren. Fjern linjen og prøv igjen."
            )
        if current_peer is None:
            if key == "address":
                config["addresses"].extend(v.strip() for v in val.split(","))
            elif key == "dns":
                config["dns"].extend(v.strip() for v in val.split(","))
            elif key == "mtu":
                config["mtu"] = val
            elif key == "listenport":
                config["listen_port"] = val
            elif key == "privatekey":
                config["private_key"] = val
        else:
            if key == "publickey":
                current_peer["public_key"] = val
            elif key == "endpoint":
                current_peer["endpoint"] = val
            elif key == "allowedips":
                current_peer["allowed_ips"] = [v.strip() for v in val.split(",")]
            elif key == "presharedkey":
                current_peer["preshared_key"] = val
            elif key == "persistentkeepalive":
                current_peer["persistent_keepalive"] = val
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
        return [
            m.group(1).strip()
            for m in re.finditer(f"<{tag}[^>]*>([^<]+)</{tag}>", xml, re.IGNORECASE)
        ]

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
                # b64decode skips non-alphabet characters unless validating,
                # which let text around the certificate into the PEM.
                compact = "".join(s.split())
                try:
                    base64.b64decode(compact, validate=True)
                except ValueError as e:
                    raise ValidationError(
                        "CA-sertifikatet i VpnSettings.xml er ikke gyldig base64"
                    ) from e
                body = "\n".join(compact[i : i + 64] for i in range(0, len(compact), 64))
                ca_cert_pem = f"-----BEGIN CERTIFICATE-----\n{body}\n-----END CERTIFICATE-----"
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


# ── Validation ──

# Fields whose value is a whole file and legitimately spans lines.
_MULTILINE_FIELDS = frozenset({"config_content", "ca_cert_pem"})


def _proto(protocol) -> str:
    return protocol.value if hasattr(protocol, "value") else protocol


def _reject_line_breaks_deep(value, field: str = "config") -> None:
    """Refuse CR, LF and NUL in every single-line value of a config."""
    if isinstance(value, dict):
        for key, item in value.items():
            reject_line_breaks(str(key), field)
            if key in _MULTILINE_FIELDS:
                if isinstance(item, str) and "\x00" in item:
                    raise ValidationError(f"{key} kan ikke inneholde NUL")
                continue
            _reject_line_breaks_deep(item, str(key))
    elif isinstance(value, list | tuple):
        for item in value:
            _reject_line_breaks_deep(item, field)
    elif isinstance(value, str):
        reject_line_breaks(value, field)


def _validate_config(protocol, config: dict, *, creating: bool) -> dict:
    """Return the config to store, or raise ValidationError.

    Runs for every way a config is saved (create, update, import), so a
    backend never receives a value nobody checked.
    """
    if not isinstance(config, dict):
        raise invalid("err_field_not_object", field="Konfigurasjonen")
    _reject_line_breaks_deep(config)
    p = _proto(protocol)
    if p == "wireguard":
        return wg_backend.validate_config(config, require_private_key=creating)
    if p == "azure":
        return azure_backend.validate_config(config)
    if p == "openvpn":
        if "config_file" in config:
            # A server-side path would let a profile read any file the
            # service can, and the OpenVPN log tail echoes it back.
            raise invalid("err_vpn_config_file_unsupported")
        content = config.get("config_content")
        if not isinstance(content, str) or not content.strip():
            raise invalid("err_field_required", field="config_content")
        reason = ovpn_backend.refusal_reason(content)
        if reason:
            raise ValidationError(reason)
    return config


# ── Secrets ──
#
# Secret material never stays in vpn_profiles.config. It lives in an encrypted
# per-profile store (VPN_SECRETS_DIR/<id>/secrets.json) under a slot name and
# is put back only in memory, when a tunnel is brought up:
#   private_key, password, psk, server_secret_hex  top-level config fields
#   peer_psk:<public key>                          a WireGuard peer's PSK
#   ovpn_<tag>_<n>                                 the n-th inline key block in
#                                                  an OpenVPN config_content
# Inline blocks are stored as "{{sybr-secret:<slot>}}" in config_content.

_SECRET_FIELDS = ("private_key", "password", "psk", "server_secret_hex")
_PEER_PSK_PREFIX = "peer_psk:"
# Slots wiped because the profile was pointed somewhere new; connect refuses
# until each one has been entered again.
_REENTER_KEY = "__reenter__"
_LEGACY_PEER_PSK_RE = re.compile(r"^peer_([0-9]+)_psk$")

# Secret fields per protocol, for reporting what is stored.
_PROTOCOL_SECRETS = {
    "wireguard": ("private_key",),
    "fortigate_ipsec": ("password", "psk"),
    "openvpn": ("password",),
    "azure": ("server_secret_hex",),
}

# Inline OpenVPN blocks holding key material or credentials. <ca>, <cert>,
# <extra-certs> and <dh> are public and stay in the config.
_OVPN_SECRET_TAGS = (
    "tls-crypt-v2",
    "tls-crypt",
    "tls-auth",
    "key",
    "pkcs12",
    "secret",
    "auth-user-pass",
    "http-proxy-user-pass",
)
_OVPN_SECRET_BLOCK_RE = re.compile(
    r"<({})>(.*?)</\1>".format("|".join(re.escape(t) for t in _OVPN_SECRET_TAGS)),
    re.DOTALL | re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(r"\{\{sybr-secret:([A-Za-z0-9_:-]+)\}\}")
_OVPN_SLOT_RE = re.compile(r"^ovpn_([a-z0-9-]+)_[0-9]+$")

# Directives naming where an OpenVPN client sends its credentials.
_OVPN_TARGET_RE = re.compile(
    r"^[ \t]*(remote|http-proxy|socks-proxy)[ \t]+([^\r\n#;]*)", re.IGNORECASE | re.MULTILINE
)

# Serialises every read-modify-write of a profile's secret store.
_secrets_lock = asyncio.Lock()


def _as_dict(config) -> dict:
    if isinstance(config, str):
        config = json.loads(config)
    return copy.deepcopy(config) if isinstance(config, dict) else {}


def _split_secrets(config, *, strict: bool) -> tuple[dict, dict, dict]:
    """Separate secret material from a profile config.

    Returns (clean, supplied, carried). *supplied* maps slots to plaintext
    found in the config. *carried* maps each slot the config has room for but
    left empty to the stored slot it inherits. With *strict* a malformed
    placeholder raises; read paths pass False and never fail.
    """
    clean = _as_dict(config)
    supplied: dict = {}
    carried: dict[str, str] = {}

    def take(container: dict, field: str, slot: str) -> None:
        value = container.pop(field, None)
        if value:
            supplied[slot] = value
        else:
            carried[slot] = slot

    for field in _SECRET_FIELDS:
        take(clean, field, field)
    for peer in clean.get("peers") or []:
        if isinstance(peer, dict):
            take(peer, "preshared_key", f"{_PEER_PSK_PREFIX}{peer.get('public_key', '')}")
    content = clean.get("config_content")
    if isinstance(content, str):
        clean["config_content"] = _split_ovpn_blocks(content, supplied, carried, strict=strict)
    return clean, supplied, carried


def _split_ovpn_blocks(content: str, supplied: dict, carried: dict, *, strict: bool) -> str:
    index = 0

    def replace(match: re.Match) -> str:
        nonlocal index
        tag_text, body = match.group(1), match.group(2)
        if not body.strip():
            return match.group(0)
        tag = tag_text.lower()
        slot = f"ovpn_{tag}_{index}"
        index += 1
        ref = _PLACEHOLDER_RE.fullmatch(body.strip())
        if ref:
            # A placeholder inherits only a block of the same kind, so an edit
            # cannot move a private key into <http-proxy-user-pass>.
            source = _OVPN_SLOT_RE.fullmatch(ref.group(1))
            if source and source.group(1) == tag:
                carried[slot] = ref.group(1)
            elif strict:
                raise invalid("err_vpn_placeholder_wrong_block", tag=tag_text)
        elif _PLACEHOLDER_RE.search(body):
            if strict:
                raise ValidationError(f"<{tag_text}> blander en plassholder med annet innhold")
        else:
            supplied[slot] = body.strip()
        return f"<{tag_text}>\n{{{{sybr-secret:{slot}}}}}\n</{tag_text}>"

    return _OVPN_SECRET_BLOCK_RE.sub(replace, content)


def _stored_values(stored: dict, clean: dict) -> dict:
    """Return the store with position-keyed WireGuard PSKs ("peer_0_psk")
    re-keyed by the peer's public key, which survives the peer list being
    reordered.
    """
    values = dict(stored)
    peers = clean.get("peers") or []
    for key in list(values):
        match = _LEGACY_PEER_PSK_RE.fullmatch(key)
        if not match:
            continue
        value = values.pop(key)
        i = int(match.group(1))
        if i < len(peers) and isinstance(peers[i], dict):
            values.setdefault(f"{_PEER_PSK_PREFIX}{peers[i].get('public_key', '')}", value)
    return values


def _resolve_secrets(
    supplied: dict, carried: dict, stored: dict, *, retargeted: bool
) -> tuple[dict, list[str]]:
    """Return the new store for a config, and the slots wiped by a retarget."""
    store = dict(supplied)
    wiped: list[str] = []
    for slot, source in carried.items():
        if source in stored and source != _REENTER_KEY:
            if retargeted:
                wiped.append(slot)
            else:
                store[slot] = stored[source]
    pending = set(stored.get(_REENTER_KEY) or ())
    reenter = sorted(slot for slot, source in carried.items() if slot in wiped or source in pending)
    if reenter:
        store[_REENTER_KEY] = reenter
    return store, sorted(wiped)


def _targets(config: dict, protocol) -> tuple:
    """Where a config sends its credentials. A change here is a retarget."""
    p = _proto(protocol)
    if p == "wireguard":
        return tuple(
            sorted(
                (str(peer.get("public_key") or ""), str(peer.get("endpoint") or "").lower())
                for peer in config.get("peers") or []
                if isinstance(peer, dict)
            )
        )
    if p == "openvpn":
        content = config.get("config_content")
        return tuple(
            sorted(
                (m.group(1).lower(), " ".join(m.group(2).split()).lower())
                for m in _OVPN_TARGET_RE.finditer(content if isinstance(content, str) else "")
            )
        )
    field = {"fortigate_ipsec": "host", "azure": "gateway_fqdn"}.get(p)
    return (str(config.get(field) or "").strip().lower(),) if field else ()


def _secret_values(profile, stored: dict) -> tuple[dict, dict, list[str]]:
    """Return (clean config, available secrets, missing slots) for a profile."""
    clean, supplied, carried = _split_secrets(profile.config, strict=False)
    stored = _stored_values(stored, clean)
    values = {
        slot: stored[source]
        for slot, source in carried.items()
        if source in stored and source != _REENTER_KEY
    }
    # Plaintext still in an unmigrated row is newer than the store.
    values.update(supplied)
    missing = {slot for slot in stored.get(_REENTER_KEY) or () if slot not in values}
    content = clean.get("config_content")
    if isinstance(content, str):
        for match in _OVPN_SECRET_BLOCK_RE.finditer(content):
            ref = _PLACEHOLDER_RE.fullmatch(match.group(2).strip())
            if ref and ref.group(1) not in values:
                missing.add(ref.group(1))
    if _proto(profile.protocol) == "wireguard" and "private_key" not in values:
        missing.add("private_key")
    return clean, values, sorted(missing)


def _inject_secrets(clean: dict, values: dict) -> dict:
    config = copy.deepcopy(clean)
    for field in _SECRET_FIELDS:
        if values.get(field):
            config[field] = values[field]
    for peer in config.get("peers") or []:
        if isinstance(peer, dict):
            psk = values.get(f"{_PEER_PSK_PREFIX}{peer.get('public_key', '')}")
            if psk:
                peer["preshared_key"] = psk
    content = config.get("config_content")
    if isinstance(content, str):

        def restore(match: re.Match) -> str:
            ref = _PLACEHOLDER_RE.fullmatch(match.group(2).strip())
            if not ref or ref.group(1) not in values:
                return match.group(0)
            return f"<{match.group(1)}>\n{values[ref.group(1)]}\n</{match.group(1)}>"

        config["config_content"] = _OVPN_SECRET_BLOCK_RE.sub(restore, content)
    return config


def _connect_config(profile, stored: dict) -> tuple[dict, list[str]]:
    """Return the config with its secrets put back, and any that are missing."""
    clean, values, missing = _secret_values(profile, stored)
    config = _inject_secrets(clean, values)
    # Refused on save (it names a server-side file); ignore one a row still holds.
    config.pop("config_file", None)
    return config, missing


def _secret_label(slot: str) -> str:
    if slot.startswith(_PEER_PSK_PREFIX):
        return "preshared_key"
    match = _OVPN_SLOT_RE.fullmatch(slot)
    return f"<{match.group(1)}>" if match else slot


def secret_labels(slots) -> list[str]:
    """Names to show for secret slots: a field name or an OpenVPN block tag."""
    return sorted({_secret_label(s) for s in slots})


def _secrets_missing_result(missing: list[str]) -> dict:
    labels = secret_labels(missing)
    return {
        "ok": False,
        "error": "Legg inn disse hemmelighetene på nytt før du kobler til: " + ", ".join(labels),
        "error_key": "err_vpn_secret_reentry",
        "missing_secrets": labels,
    }


def stored_config(profile) -> dict:
    """The profile's config with every secret removed, for display and auth flows."""
    return _split_secrets(profile.config, strict=False)[0]


def describe_secrets(profile) -> dict:
    """What is stored for a profile, as booleans and labels only."""
    clean, values, missing = _secret_values(profile, _load_secrets(profile.id))
    p = _proto(profile.protocol)
    flags: dict = {f"has_{field}": field in values for field in _PROTOCOL_SECRETS.get(p, ())}
    if p == "wireguard":
        flags["has_preshared_key"] = [
            f"{_PEER_PSK_PREFIX}{peer.get('public_key', '')}" in values
            for peer in clean.get("peers") or []
            if isinstance(peer, dict)
        ]
    flags["needs_reentry"] = secret_labels(missing)
    return flags


async def _migrate_plaintext_secrets(profile: VpnProfile) -> VpnProfile:
    """Move secrets a stored config still carries into the encrypted store.

    Rows can hold OpenVPN inline keys in config_content and edited secrets in
    plain fields. Done lazily rather than at startup: every path that hands a
    profile out goes through get_profile or list_profiles, so nothing sees an
    unmigrated row, the first listing after an upgrade sweeps them all, and it
    is safe to repeat.
    """
    if not isinstance(profile.config, str) and not _split_secrets(profile.config, strict=False)[1]:
        return profile
    async with _secrets_lock, get_session() as session:
        row = await session.get(VpnProfile, profile.id)
        if row is None:
            return profile
        clean, supplied, carried = _split_secrets(row.config, strict=False)
        try:
            stored = _stored_values(_read_secrets(row.id), clean)
        except Exception as e:
            # Overwriting an unreadable store would lose what it holds.
            logger.warning("VPN profile %s left unmigrated, secrets unreadable: %s", row.id, e)
            return profile
        # Plaintext in the row wins: an edit written to the row is newer than
        # the value the store has held since the profile was created.
        new_store, _ = _resolve_secrets(supplied, carried, stored, retargeted=False)
        _store_secrets(row.id, new_store)
        row.config = clean
        await session.commit()
        await session.refresh(row)
    logger.info("Moved plaintext secrets of VPN profile %s into the encrypted store", row.id)
    return row


def _store_secrets(profile_id: str, secrets: dict) -> None:
    path = VPN_SECRETS_DIR / profile_id / "secrets.json"
    if not secrets:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted_write_bytes(path, json.dumps(secrets).encode())


def _read_secrets(profile_id: str) -> dict:
    """The raw secret store; raises if it exists but cannot be read."""
    path = VPN_SECRETS_DIR / profile_id / "secrets.json"
    if not path.exists():
        return {}
    return json.loads(encrypted_read_bytes(path).decode())


def _load_secrets(profile_id: str) -> dict:
    try:
        return _read_secrets(profile_id)
    except Exception as e:
        logger.warning("Failed to load VPN secrets for %s: %s", profile_id, e)
        return {}
