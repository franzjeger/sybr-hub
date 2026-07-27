"""Enhanced UniFi API service layer.

Provides high-level operations on top of the low-level controller/device clients:
  - Enhanced per-device stats (model, firmware, uptime, CPU/mem, clients, status)
  - Site Manager cloud API (ui.com authentication, cross-account site listing)
  - Device adoption with controller URL validation
  - Firmware audit using the local firmware database
  - Aggregate controller summary (sites, devices, clients, WLANs, alarms)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx

from app.core.credentials import get_secret, store_secret
from app.core.customer import CustomerManager
from app.modules.unifi_audit.client import UniFiControllerClient, UniFiDirectDevice
from app.modules.unifi_audit.firmware_db import check_firmware

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper — build a controller client from stored customer credentials
# ═══════════════════════════════════════════════════════════════════════════════


async def _controller_for_customer(customer_id: str) -> UniFiControllerClient:
    """Instantiate an authenticated UniFiControllerClient from saved config."""
    from app.core.exceptions import NotFoundError, ValidationError
    cust = CustomerManager.get_customer(customer_id)
    if not cust:
        raise NotFoundError(f"Customer {customer_id} not found")

    host = cust.get("UniFiHost")
    if not host:
        raise ValidationError("No UniFi host configured for this customer")

    username = get_secret(customer_id, "unifi_username")
    password = get_secret(customer_id, "unifi_password")
    if not username or not password:
        raise ValidationError("UniFi credentials not stored for this customer")

    client = UniFiControllerClient(
        host=host,
        username=username,
        password=password,
        is_unifi_os=cust.get("UniFiIsUniFiOS", False),
    )
    try:
        await client._login()
    except Exception:
        await client.close()
        raise
    return client


def _default_site(customer_id: str) -> str:
    cust = CustomerManager.get_customer(customer_id)
    return (cust or {}).get("UniFiSite", "default")


def wlan_security_label(security: Any) -> str:
    """Map a UniFi WLAN security string to a human label.

    Anything unrecognised comes back as "Unknown (<value>)" rather than
    falling through to "Open". Reporting an unrecognised cipher as an open
    network is a false finding either way — it sends a technician to fix a
    network that is already encrypted, and it would hide a genuinely open one
    behind the same label. WEP is called out by name because "Open" flatters
    it and "WPA2" would be badly wrong.
    """
    if not isinstance(security, str) or not security.strip():
        return "Unknown"
    s = security.strip().lower()
    if s == "open":
        return "Open"
    # SAE is WPA3-Personal's handshake; some firmware reports it on its own.
    if "wpa3" in s or "sae" in s:
        return "WPA3-Enterprise" if "eap" in s else "WPA3"
    if "eap" in s:                       # wpaeap, wpa2eap
        return "WPA2-Enterprise"
    if "wpapsk" in s or "wpa2" in s or "wpa" in s:
        return "WPA2"
    if "wep" in s:
        return "WEP (insecure)"
    return f"Unknown ({security})"


def is_open_wlan_security(security: Any) -> bool:
    """True only when the value positively identifies an unencrypted WLAN.

    Absent, null, and unrecognised values return False. Callers use this to
    decide whether to raise an "open WiFi" finding, and an open-WiFi finding
    is the most alarming thing the network audit emits — it must rest on a
    reading, never on a default. Anything we cannot classify is Unknown, and
    Unknown is not a finding.
    """
    return wlan_security_label(security) == "Open"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Enhanced device stats
# ═══════════════════════════════════════════════════════════════════════════════


async def get_enhanced_device_stats(customer_id: str) -> list[dict[str, Any]]:
    """Return detailed per-device info for every device the controller manages.

    Fields per device: name, model, firmware, uptime, cpu/mem (if available),
    connected clients, IP, MAC, status, upgrade_available.
    """
    client = await _controller_for_customer(customer_id)
    site = _default_site(customer_id)

    try:
        devices_raw = await client.get_devices(site)
        clients_raw = await client.get_clients(site)

        # Build a MAC → client-count map for more accurate numbers
        clients_by_ap: dict[str, int] = {}
        for c in clients_raw:
            ap_mac = c.get("ap_mac", "")
            if ap_mac:
                clients_by_ap[ap_mac] = clients_by_ap.get(ap_mac, 0) + 1

        enriched: list[dict[str, Any]] = []
        for d in devices_raw:
            mac = d.get("mac", "")
            state = d.get("state", 0)
            sys_stats = d.get("sys_stats", {}) or {}
            uptime_sec = d.get("uptime", 0)

            # Human-readable uptime
            uptime_str = ""
            if uptime_sec:
                days, rem = divmod(int(uptime_sec), 86400)
                hours, rem = divmod(rem, 3600)
                mins, _ = divmod(rem, 60)
                parts = []
                if days:
                    parts.append(f"{days}d")
                if hours:
                    parts.append(f"{hours}h")
                parts.append(f"{mins}m")
                uptime_str = " ".join(parts)

            enriched.append({
                "name": d.get("name", d.get("hostname", mac or "unknown")),
                "model": d.get("model", ""),
                "model_long": d.get("model_in_lts", d.get("model_in_eol", "")),
                "type": d.get("type", ""),
                "firmware": d.get("version", ""),
                "ip": d.get("ip", ""),
                "mac": mac,
                "status": "online" if state == 1 else "offline",
                "uptime_seconds": uptime_sec,
                "uptime": uptime_str,
                "cpu_percent": sys_stats.get("cpu", None),
                "mem_percent": sys_stats.get("mem", None),
                "load_1m": sys_stats.get("loadavg_1", None),
                "connected_clients": clients_by_ap.get(mac, d.get("num_sta", 0)),
                "upgrade_available": d.get("upgrade_to_firmware") or None,
                "serial": d.get("serial", ""),
                "adopted": d.get("adopted", False),
                "config_network": d.get("config_network", {}),
            })

        return enriched
    finally:
        await client.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 1b. Client inventory
# ═══════════════════════════════════════════════════════════════════════════════


async def get_client_inventory(customer_id: str) -> list[dict[str, Any]]:
    """Return all connected clients for a customer's UniFi site.

    Each client includes: hostname/name, MAC, IP, type (wired/wireless),
    signal strength, experience score, uptime, rx/tx bytes, connected device.
    Sorted: wireless clients first (by signal strength), then wired.
    """
    client = await _controller_for_customer(customer_id)
    site = _default_site(customer_id)

    try:
        clients_raw = await client.get_clients(site)
        devices_raw = await client.get_devices(site)

        # Build MAC -> device name map
        device_names: dict[str, str] = {}
        for d in devices_raw:
            mac = d.get("mac", "")
            name = d.get("name", d.get("hostname", mac))
            if mac:
                device_names[mac] = name

        result: list[dict[str, Any]] = []
        for c in clients_raw:
            is_wired = c.get("is_wired", False)
            signal = c.get("rssi", c.get("signal", None)) if not is_wired else None
            # Normalise signal: UniFi sometimes returns positive rssi, sometimes negative
            if signal is not None and signal > 0:
                signal = -signal

            uptime_sec = c.get("uptime", 0)
            uptime_str = ""
            if uptime_sec:
                days, rem = divmod(int(uptime_sec), 86400)
                hours, rem = divmod(rem, 3600)
                mins, _ = divmod(rem, 60)
                parts = []
                if days:
                    parts.append(f"{days}d")
                if hours:
                    parts.append(f"{hours}h")
                parts.append(f"{mins}m")
                uptime_str = " ".join(parts)

            # Connected-to device name
            ap_mac = c.get("ap_mac", "")
            sw_mac = c.get("sw_mac", "")
            connected_to = device_names.get(ap_mac, "") or device_names.get(sw_mac, "")

            result.append({
                "hostname": c.get("hostname", c.get("name", c.get("oui", ""))),
                "name": c.get("name", ""),
                "mac": c.get("mac", ""),
                "ip": c.get("ip", ""),
                "type": "wired" if is_wired else "wireless",
                "signal": signal,
                "experience": c.get("satisfaction", c.get("score", None)),
                "uptime_seconds": uptime_sec,
                "uptime": uptime_str,
                "rx_bytes": c.get("rx_bytes", 0),
                "tx_bytes": c.get("tx_bytes", 0),
                "connected_to": connected_to,
                "network": c.get("essid", c.get("network", "")),
                "channel": c.get("channel", None),
                "radio": c.get("radio", ""),
                "sw_port": c.get("sw_port", None),
            })

        # Sort: wireless first (worst signal first), then wired
        result.sort(key=lambda x: (
            1 if x["type"] == "wired" else 0,
            x["signal"] if x["signal"] is not None else 0,
        ))

        return result
    finally:
        await client.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 1c. WiFi health overview
# ═══════════════════════════════════════════════════════════════════════════════


async def get_wifi_health(customer_id: str) -> dict[str, Any]:
    """Return WiFi health overview for a customer's UniFi site.

    Includes per-AP stats, per-SSID info, and alerts for rogue APs,
    interference, and poor satisfaction scores.
    """
    client = await _controller_for_customer(customer_id)
    site = _default_site(customer_id)

    try:
        import asyncio
        devices_raw, clients_raw, wlans_raw, health_raw, rogues_raw = await asyncio.gather(
            client.get_devices(site),
            client.get_clients(site),
            client.get_wlans(site),
            client.get_health(site),
            client.get_rogueaps(site),
        )

        # ── Per-AP stats ──
        # Count clients per AP
        clients_by_ap: dict[str, int] = {}
        for c in clients_raw:
            ap_mac = c.get("ap_mac", "")
            if ap_mac:
                clients_by_ap[ap_mac] = clients_by_ap.get(ap_mac, 0) + 1

        aps: list[dict[str, Any]] = []
        for d in devices_raw:
            if d.get("type") != "uap":
                continue
            mac = d.get("mac", "")
            radio_table = d.get("radio_table_stats", d.get("radio_table", []))
            channels = []
            interferences = []
            for radio in radio_table:
                ch = radio.get("channel")
                if ch:
                    channels.append(str(ch))
                cu = radio.get("cu_total", radio.get("interference", None))
                if cu is not None:
                    interferences.append(cu)

            satisfaction = d.get("satisfaction", None)
            aps.append({
                "name": d.get("name", d.get("hostname", mac)),
                "mac": mac,
                "model": d.get("model", ""),
                "status": "online" if d.get("state", 0) == 1 else "offline",
                "clients": clients_by_ap.get(mac, d.get("num_sta", 0)),
                "channels": ", ".join(channels) if channels else "",
                "interference": max(interferences) if interferences else None,
                "satisfaction": satisfaction,
                "uptime_seconds": d.get("uptime", 0),
            })

        # ── Per-SSID info ──
        ssids: list[dict[str, Any]] = []
        # Count clients per SSID
        clients_by_ssid: dict[str, int] = {}
        for c in clients_raw:
            essid = c.get("essid", "")
            if essid:
                clients_by_ssid[essid] = clients_by_ssid.get(essid, 0) + 1

        for w in wlans_raw:
            name = w.get("name", "")
            sec_label = wlan_security_label(w.get("security"))

            ssids.append({
                "name": name,
                "enabled": w.get("enabled", True),
                "security": sec_label,
                "clients": clients_by_ssid.get(name, 0),
                "is_guest": w.get("is_guest", False),
                "band": w.get("wlan_band", "both"),
            })

        # ── Alerts ──
        alerts: list[dict[str, Any]] = []

        # Rogue APs
        for r in rogues_raw[:20]:  # Limit to top 20
            alerts.append({
                "type": "rogue_ap",
                "severity": "high",
                "message": f"Rogue AP: {r.get('essid', 'hidden')} ({r.get('bssid', '?')}) "
                           f"ch {r.get('channel', '?')} signal {r.get('rssi', '?')}dBm",
                "details": {
                    "essid": r.get("essid", ""),
                    "bssid": r.get("bssid", ""),
                    "channel": r.get("channel"),
                    "signal": r.get("rssi"),
                },
            })

        # High interference APs
        for ap in aps:
            if ap["interference"] is not None and ap["interference"] > 50:
                alerts.append({
                    "type": "high_interference",
                    "severity": "medium",
                    "message": f"{ap['name']}: {ap['interference']}% interference",
                    "details": {"ap_name": ap["name"], "interference": ap["interference"]},
                })

        # Poor satisfaction APs
        for ap in aps:
            if ap["satisfaction"] is not None and ap["satisfaction"] < 70:
                alerts.append({
                    "type": "poor_satisfaction",
                    "severity": "medium",
                    "message": f"{ap['name']}: {ap['satisfaction']}% satisfaction",
                    "details": {"ap_name": ap["name"], "satisfaction": ap["satisfaction"]},
                })

        # WiFi subsystem health from stat/health
        wifi_health = {}
        for h in health_raw:
            if h.get("subsystem") == "wlan":
                wifi_health = {
                    "status": h.get("status", "unknown"),
                    "num_ap": h.get("num_ap", 0),
                    "num_adopted": h.get("num_adopted", 0),
                    "num_user": h.get("num_user", 0),
                    "num_guest": h.get("num_guest", 0),
                    "tx_bytes": h.get("tx_bytes-r", 0),
                    "rx_bytes": h.get("rx_bytes-r", 0),
                }
                break

        return {
            "aps": aps,
            "ssids": ssids,
            "alerts": alerts,
            "health": wifi_health,
            "total_wireless_clients": sum(1 for c in clients_raw if not c.get("is_wired", False)),
            "total_wired_clients": sum(1 for c in clients_raw if c.get("is_wired", False)),
            "rogue_ap_count": len(rogues_raw),
        }
    finally:
        await client.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Site Manager (ui.com cloud API)
# ═══════════════════════════════════════════════════════════════════════════════

_UI_SSO_URL = "https://sso.ui.com/api/sso/v1/login"
_UI_SSO_2FA_URL = "https://sso.ui.com/api/sso/v1/login/totp"
# Use v1 stable API (10,000 req/min) instead of EA (100 req/min)
_UI_SITES_URL = "https://api.ui.com/v1/sites"
_UI_HOSTS_URL = "https://api.ui.com/v1/hosts"
_UI_DEVICES_URL = "https://api.ui.com/v1/devices"
_UI_ISP_METRICS_URL = "https://api.ui.com/v1/isp-metrics"


# In-memory SSO token cache — avoids re-authenticating on every call.
# Keyed by (username, store_for_customer); TTL = 1 hour.
_token_cache: dict[str, Any] = {"token": None, "expires": 0, "result": None}
_TOKEN_TTL = 3600  # seconds


async def site_manager_authenticate(
    username: Optional[str] = None,
    password: Optional[str] = None,
    api_key: Optional[str] = None,
    *,
    store_for_customer: Optional[str] = None,
) -> dict[str, Any]:
    """Authenticate with UniFi Site Manager via API key or SSO credentials.

    API key is preferred — it's a long-lived token that works directly
    with the Site Manager API.  SSO login is a fallback for accounts
    without an API key.

    SSO tokens are cached in-memory for 1 hour to avoid redundant
    round-trips to sso.ui.com.

    If *store_for_customer* is provided, the token/key is persisted.
    """
    # For SSO logins, return cached token if still valid
    if not api_key and username and password:
        if (
            _token_cache["token"]
            and _token_cache["expires"] > time.monotonic()
            and _token_cache.get("_username") == username
        ):
            log.debug("Returning cached SSO token (expires in %ds)",
                      int(_token_cache["expires"] - time.monotonic()))
            cached = _token_cache["result"]
            # Still honour store_for_customer on cache hit
            if store_for_customer and cached.get("ok"):
                store_secret(store_for_customer, "ui_cloud_token", cached["token"])
            return cached

    # API key path — just validate it works
    if api_key:
        async with httpx.AsyncClient(timeout=30.0) as http:
            try:
                r = await http.get(
                    _UI_SITES_URL,
                    headers={"X-API-KEY": api_key, "Accept": "application/json"},
                )
                if r.status_code in (200, 201):
                    if store_for_customer:
                        store_secret(store_for_customer, "ui_cloud_token", api_key)
                    # Also store globally in app settings
                    from app.core.config import load_app_settings, save_app_settings
                    settings = load_app_settings()
                    settings["unifi_site_manager_api_key"] = api_key
                    save_app_settings(settings)
                    log.info("UniFi Site Manager API key saved")
                    return {"ok": True, "token": api_key, "method": "api_key"}
                return {"ok": False, "error": f"API key invalid — HTTP {r.status_code}"}
            except Exception as e:
                return {"ok": False, "error": str(e)}

    # SSO login fallback
    if not username or not password:
        return {"ok": False, "error": "API-nøkkel eller brukernavn/passord er påkrevd"}

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
        try:
            r = await http.post(
                _UI_SSO_URL,
                json={"user": username, "password": password},
                headers={"Content-Type": "application/json"},
            )

            if r.status_code == 200:
                body = r.json() if r.content else {}

                # Check if 2FA is required — ui.com returns a partial auth
                # token and signals that TOTP verification is needed.
                if body.get("twoFactorRequired") or body.get("twoFactorType"):
                    session_token = (
                        body.get("ubpiAuthToken")
                        or body.get("token")
                        or body.get("unique_id", "")
                    )
                    log.info("ui.com SSO requires 2FA (type=%s)", body.get("twoFactorType", "totp"))
                    return {
                        "ok": False,
                        "requires_2fa": True,
                        "session_token": session_token,
                        "error": "2FA-kode påkrevd",
                        # Pass along credentials so the verify step can
                        # optionally store the final token.
                        "_store_for_customer": store_for_customer,
                        "_username": username,
                    }

                token = r.cookies.get("TOKEN") or r.headers.get("x-token", "")
                if not token:
                    token = body.get("token", body.get("access_token", ""))

                if not token:
                    return {"ok": False, "error": "Autentisering OK men ingen token mottatt"}

                if store_for_customer:
                    store_secret(store_for_customer, "ui_cloud_token", token)
                    log.info("Stored ui.com cloud token for customer %s", store_for_customer)

                result = {"ok": True, "token": token, "method": "sso"}
                # Cache the SSO token
                _token_cache.update({
                    "token": token,
                    "expires": time.monotonic() + _TOKEN_TTL,
                    "result": result,
                    "_username": username,
                })
                return result

            # Better error messages for known status codes
            body = {}
            try:
                body = r.json()
            except Exception:
                pass
            detail = body.get("detail", body.get("error", ""))
            if r.status_code == 403:
                return {"ok": False, "error": "Feil brukernavn eller passord"}
            if r.status_code == 423:
                return {"ok": False, "error": "Kontoen er låst — prøv igjen senere"}
            if r.status_code == 429:
                return {"ok": False, "error": "For mange forsøk — vent litt"}
            return {"ok": False, "error": f"ui.com SSO: HTTP {r.status_code}" + (f" — {detail}" if detail else "")}
        except Exception as e:
            log.warning("ui.com SSO authentication failed: %s", e)
            return {"ok": False, "error": str(e)}


async def site_manager_verify_2fa(
    session_token: str,
    totp_code: str,
    *,
    store_for_customer: Optional[str] = None,
    username: Optional[str] = None,
) -> dict[str, Any]:
    """Complete UniFi SSO 2FA verification with a TOTP code.

    *session_token* is the partial auth token returned by the initial
    login attempt when 2FA is required.
    """
    if not session_token or not totp_code:
        return {"ok": False, "error": "Session-token og 2FA-kode er påkrevd"}

    async with httpx.AsyncClient(timeout=30.0) as http:
        try:
            r = await http.post(
                _UI_SSO_2FA_URL,
                json={"ubpiAuthToken": session_token, "token": totp_code},
                headers={"Content-Type": "application/json"},
            )

            if r.status_code == 200:
                body = r.json() if r.content else {}
                token = (
                    r.cookies.get("TOKEN")
                    or r.headers.get("x-token", "")
                    or body.get("token", body.get("access_token", ""))
                )

                if not token:
                    return {"ok": False, "error": "2FA OK men ingen token mottatt"}

                if store_for_customer:
                    store_secret(store_for_customer, "ui_cloud_token", token)
                    log.info("Stored ui.com cloud token for customer %s (2FA)", store_for_customer)

                result = {"ok": True, "token": token, "method": "sso"}
                _token_cache.update({
                    "token": token,
                    "expires": time.monotonic() + _TOKEN_TTL,
                    "result": result,
                    "_username": username or "",
                })
                return result

            return {"ok": False, "error": f"2FA-verifisering feilet — HTTP {r.status_code}"}
        except Exception as e:
            log.warning("ui.com SSO 2FA verification failed: %s", e)
            return {"ok": False, "error": str(e)}


def _build_api_headers(token: str) -> dict[str, str]:
    """Build auth headers — X-API-KEY for short keys, Bearer for SSO tokens."""
    headers: dict[str, str] = {"Accept": "application/json"}
    if len(token) > 100:
        headers["Authorization"] = f"Bearer {token}"
    else:
        headers["X-API-KEY"] = token
    return headers


def _resolve_token(token: Optional[str], customer_id: Optional[str]) -> Optional[str]:
    if token:
        return token
    if customer_id:
        t = get_secret(customer_id, "ui_cloud_token")
        if t:
            return t
    from app.core.config import load_app_settings
    return load_app_settings().get("unifi_site_manager_api_key", "") or None


async def site_manager_list_sites(
    token: Optional[str] = None,
    *,
    customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """List all cloud-managed hosts (consoles) with their sites.

    Uses the /ea/hosts endpoint which returns the actual console names
    (not "Default"), WAN IPs, hardware info, and firmware versions.
    Falls back to /ea/sites for per-site device counts.
    """
    token = _resolve_token(token, customer_id)
    if not token:
        return {"ok": False, "error": "Ingen API-nøkkel eller cloud-token tilgjengelig"}

    headers = _build_api_headers(token)

    async with httpx.AsyncClient(timeout=30.0) as http:
        try:
            # Fetch hosts (consoles) — has real names and WAN IPs
            r_hosts = await http.get(_UI_HOSTS_URL, headers=headers)
            if r_hosts.status_code == 401:
                return {"ok": False, "error": "API-nøkkel ugyldig eller utløpt"}
            r_hosts.raise_for_status()
            hosts = r_hosts.json().get("data", [])

            # Fetch sites for device/client counts
            r_sites = await http.get(_UI_SITES_URL, headers=headers)
            sites_by_host: dict[str, list] = {}
            if r_sites.status_code == 200:
                for s in r_sites.json().get("data", []):
                    hid = s.get("hostId", "")
                    sites_by_host.setdefault(hid, []).append(s)

            result = []
            for h in hosts:
                rs = h.get("reportedState", {})
                hw = rs.get("hardware", {})
                fu = rs.get("firmwareUpdate", {})

                name = rs.get("name", "") or hw.get("shortname", "") or h.get("id", "")[:12]
                wan_ip = h.get("ipAddress", "")
                host_id = h.get("id", "")
                internal_ip = rs.get("ip", "")
                # Check multiple state fields — deviceState, state, or infer from lastConnectionStateChange
                state = rs.get("deviceState") or rs.get("state") or "unknown"
                is_online = state in ("connected", "ready", "online", "setup")

                # Aggregate device counts from all sites on this host
                host_sites = sites_by_host.get(host_id, [])
                total_devices = 0
                offline_devices = 0
                total_clients = 0
                site_names = []
                for s in host_sites:
                    counts = s.get("statistics", {}).get("counts", {})
                    total_devices += counts.get("totalDevice", 0)
                    offline_devices += counts.get("offlineDevice", 0)
                    total_clients += counts.get("wifiClient", 0) + counts.get("wiredClient", 0)
                    site_meta = s.get("meta", {})
                    sn = site_meta.get("desc", site_meta.get("name", ""))
                    if sn and sn not in ("Default", "default"):
                        site_names.append(sn)

                isp_name = ""
                for s in host_sites:
                    isp_info = s.get("statistics", {}).get("ispInfo", {})
                    if isp_info.get("name"):
                        isp_name = isp_info["name"]
                        break

                # Build sub-sites list with per-site detail
                sub_sites = []
                for s in host_sites:
                    s_meta = s.get("meta", {})
                    s_stats = s.get("statistics", {})
                    s_counts = s_stats.get("counts", {})
                    s_gw = s_stats.get("gateway", {})
                    s_pct = s_stats.get("percentages", {})
                    s_isp_sub = s_stats.get("ispInfo", {})
                    s_issues = s_stats.get("internetIssues", [])
                    s_name = s_meta.get("desc", s_meta.get("name", ""))
                    # Skip empty "Default" sites with 0 devices
                    if s_name in ("Default", "default", "") and s_counts.get("totalDevice", 0) == 0:
                        continue
                    sub_sites.append({
                        "site_id": s.get("siteId", ""),
                        "name": s_name or "(Standard)",
                        "timezone": s_meta.get("timezone", ""),
                        "country": s_meta.get("country", ""),
                        "device_count": s_counts.get("totalDevice", 0),
                        "wifi_devices": s_counts.get("wifiDevice", 0),
                        "wired_devices": s_counts.get("wiredDevice", 0),
                        "gateway_devices": s_counts.get("gatewayDevice", 0),
                        "offline_devices": s_counts.get("offlineDevice", 0),
                        "offline_wifi": s_counts.get("offlineWifiDevice", 0),
                        "offline_wired": s_counts.get("offlineWiredDevice", 0),
                        "pending_updates": s_counts.get("pendingUpdateDevice", 0),
                        "wifi_clients": s_counts.get("wifiClient", 0),
                        "wired_clients": s_counts.get("wiredClient", 0),
                        "client_count": s_counts.get("wifiClient", 0) + s_counts.get("wiredClient", 0),
                        "guest_count": s_counts.get("guestClient", 0),
                        "wifi_networks": s_counts.get("wifiConfiguration", 0),
                        "lan_networks": s_counts.get("lanConfiguration", 0),
                        "wan_interfaces": s_counts.get("wanConfiguration", 0),
                        "critical_notifications": s_counts.get("criticalNotification", 0),
                        "tx_retry_pct": round(s_pct.get("txRetry", 0), 1),
                        "wan_uptime_pct": round(s_pct.get("wanUptime", 0), 1),
                        "gateway_model": s_gw.get("shortname", ""),
                        "gateway_version": s_gw.get("version", ""),
                        "gateway_uptime": s_gw.get("uptime", 0),
                        "gateway_mac": s_gw.get("mac", ""),
                        "isp": s_isp_sub.get("name", ""),
                        "isp_org": s_isp_sub.get("organization", ""),
                        "isp_asn": s_isp_sub.get("asn", ""),
                        "internet_issues": s_issues if isinstance(s_issues, list) else [],
                    })
                sub_sites.sort(key=lambda x: x["name"].lower())

                result.append({
                    "id": host_id,
                    "name": name,
                    "wan_ip": wan_ip,
                    "type": h.get("type", "console"),
                    "model": hw.get("shortname") or hw.get("name") or (
                        "Cloud Controller" if h.get("type") == "network-server" else ""
                    ),
                    "model_full": hw.get("name") or (
                        "UniFi Network Server (Unihosted)" if h.get("type") == "network-server" else ""
                    ),
                    "firmware": hw.get("firmwareVersion") or "",
                    "firmware_update": fu.get("latestAvailableVersion"),
                    "mac": hw.get("mac", ""),
                    "serial": hw.get("serialno", ""),
                    "hw_rev": hw.get("hwrev", ""),
                    "cpu_id": hw.get("cpu.id", ""),
                    "state": state,
                    "status": "online" if is_online else "offline",
                    "internal_ip": internal_ip,
                    "hostname": rs.get("hostname", ""),
                    "version": rs.get("version", ""),  # UniFi OS version
                    "uptime": rs.get("uptime") or 0,
                    "app_version": rs.get("applicationVersion", ""),
                    "release_channel": rs.get("releaseChannel", ""),
                    "timezone": rs.get("timezone", ""),
                    "country": rs.get("country", ""),
                    "direct_connect_domain": rs.get("directConnectDomain", ""),
                    "internet_issues_5min": rs.get("internetIssues5min", {}),
                    "auto_update": rs.get("autoUpdate", {}),
                    "unadopted_devices": rs.get("unadoptedUnifiOSDevices", 0),
                    "device_error": rs.get("deviceErrorCode", 0),
                    "is_stacked": rs.get("isStacked", False),
                    "host_type": rs.get("host_type", 0),
                    "is_blocked": h.get("isBlocked", False),
                    "isp": isp_name,
                    "device_count": total_devices,
                    "offline_devices": offline_devices,
                    "client_count": total_clients,
                    "site_count": len(host_sites),
                    "site_names": site_names,
                    "sub_sites": sub_sites,
                    "is_owner": h.get("owner", False),
                    "registered": h.get("registrationTime", ""),
                    "last_connection": h.get("lastConnectionStateChange", ""),
                    "last_backup": h.get("latestBackupTime", ""),
                })

            # Filter out hosts with 0 sites — these are sub-devices (NAS, etc.)
            # adopted into another controller's site, not standalone consoles
            result = [r for r in result if r["site_count"] > 0]

            # Sort: offline first, then by name
            result.sort(key=lambda x: (0 if x["status"] == "offline" else 1, x["name"].lower()))

            return {"ok": True, "sites": result, "count": len(result)}
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            log.warning("Failed to list ui.com cloud sites: %s", e)
            return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. All devices across all sites (v1/devices)
# ═══════════════════════════════════════════════════════════════════════════════


async def get_all_devices(host_id: Optional[str] = None) -> dict[str, Any]:
    """Fetch all devices across all hosts/sites from Site Manager API.

    Returns per-device: name, model, firmware, status, IP, startup time,
    adoption time, firmware update status.
    Optionally filter by host_id.
    """
    token = _resolve_token(None, None)
    if not token:
        return {"ok": False, "error": "Ingen API-nøkkel tilgjengelig"}

    headers = _build_api_headers(token)

    async with httpx.AsyncClient(timeout=30.0) as http:
        try:
            url = _UI_DEVICES_URL
            if host_id:
                url += f"?hostIds[]={host_id}"
            r = await http.get(url, headers=headers)
            if r.status_code == 401:
                return {"ok": False, "error": "API-nøkkel ugyldig"}
            r.raise_for_status()

            raw = r.json().get("data", [])
            result = []
            for host_group in raw:
                h_name = host_group.get("hostName", "")
                h_id = host_group.get("hostId", "")
                for d in host_group.get("devices", []):
                    # Calculate uptime from startupTime
                    uptime_str = ""
                    startup = d.get("startupTime", "")
                    if startup:
                        try:
                            from datetime import datetime, timezone

                            from app.core.utils import format_uptime
                            st = datetime.fromisoformat(startup.replace("Z", "+00:00"))
                            delta = datetime.now(timezone.utc) - st
                            uptime_str = format_uptime(delta.total_seconds())
                        except Exception:
                            pass

                        result.append({
                        "host_id": h_id,
                        "host_name": h_name,
                        "id": d.get("id", ""),
                        "mac": d.get("mac", ""),
                        "name": d.get("name", d.get("shortname", "")),
                        "model": d.get("shortname", ""),
                        "model_full": d.get("model", ""),
                        "ip": d.get("ip", ""),
                        "status": d.get("status", "offline"),
                        "firmware": d.get("version", ""),
                        "firmware_status": d.get("firmwareStatus", ""),
                        "update_available": d.get("updateAvailable", ""),
                        "is_console": d.get("isConsole", False),
                        "is_managed": d.get("isManaged", False),
                        "product_line": d.get("productLine", "network"),
                        "note": d.get("note", ""),
                        "uptime": uptime_str,
                        "startup_time": startup,
                        "adoption_time": d.get("adoptionTime", ""),
                    })

            # Sort: offline first, then by host, then by name
            result.sort(key=lambda x: (
                0 if x["status"] == "offline" else 1,
                x["host_name"].lower(),
                x["name"].lower(),
            ))

            return {"ok": True, "devices": result, "count": len(result)}
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ISP metrics (v1/isp-metrics)
# ═══════════════════════════════════════════════════════════════════════════════


async def get_isp_metrics(
    metric_type: str = "1h",
    duration: str = "24h",
) -> dict[str, Any]:
    """Fetch ISP performance metrics (bandwidth, latency, packet loss, uptime).

    metric_type: '5m' (last 24h) or '1h' (last 7d/30d)
    duration: '24h', '7d', '30d'
    """
    token = _resolve_token(None, None)
    if not token:
        return {"ok": False, "error": "Ingen API-nøkkel tilgjengelig"}

    headers = _build_api_headers(token)

    async with httpx.AsyncClient(timeout=60.0) as http:
        try:
            url = f"{_UI_ISP_METRICS_URL}/{metric_type}?duration={duration}"
            r = await http.get(url, headers=headers)
            if r.status_code == 401:
                return {"ok": False, "error": "API-nøkkel ugyldig"}
            r.raise_for_status()

            raw = r.json().get("data", [])

            # Group by site/host and extract latest + summary
            by_site: dict[str, list] = {}
            for entry in raw:
                site_id = entry.get("siteId", entry.get("hostId", "unknown"))
                by_site.setdefault(site_id, []).append(entry)

            sites_summary = []
            for site_id, entries in by_site.items():
                # Get latest entry
                latest = entries[-1] if entries else {}
                wan_data = latest.get("data", {}).get("wan", {})

                # Calculate averages over period
                latencies = [e.get("data", {}).get("wan", {}).get("avgLatency", 0) for e in entries if e.get("data", {}).get("wan", {}).get("avgLatency")]
                packet_losses = [e.get("data", {}).get("wan", {}).get("packetLoss", 0) for e in entries if e.get("data", {}).get("wan", {})]
                uptimes = [e.get("data", {}).get("wan", {}).get("uptime", 100) for e in entries if e.get("data", {}).get("wan", {})]

                sites_summary.append({
                    "site_id": site_id,
                    "isp": wan_data.get("ispName", ""),
                    "latest": {
                        "download_mbps": round(wan_data.get("download_kbps", 0) / 1000, 1),
                        "upload_mbps": round(wan_data.get("upload_kbps", 0) / 1000, 1),
                        "latency_ms": wan_data.get("avgLatency", 0),
                        "packet_loss": wan_data.get("packetLoss", 0),
                        "uptime_pct": wan_data.get("uptime", 0),
                    },
                    "averages": {
                        "latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
                        "packet_loss": round(sum(packet_losses) / len(packet_losses), 2) if packet_losses else 0,
                        "uptime_pct": round(sum(uptimes) / len(uptimes), 1) if uptimes else 0,
                    },
                    "data_points": len(entries),
                })

            return {"ok": True, "sites": sites_summary, "metric_type": metric_type, "duration": duration}
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Enhanced site detail with WAN info from statistics
# ═══════════════════════════════════════════════════════════════════════════════


async def get_site_wan_details(site_id: str) -> dict[str, Any]:
    """Get WAN/ISP details for a specific site from the sites endpoint."""
    token = _resolve_token(None, None)
    if not token:
        return {"ok": False, "error": "Ingen API-nøkkel tilgjengelig"}

    headers = _build_api_headers(token)

    async with httpx.AsyncClient(timeout=30.0) as http:
        try:
            r = await http.get(_UI_SITES_URL, headers=headers)
            r.raise_for_status()

            for s in r.json().get("data", []):
                if s.get("siteId") == site_id:
                    stats = s.get("statistics", {})
                    wans_raw = stats.get("wans", {})
                    gw = stats.get("gateway", {})

                    wans = []
                    for wan_name, wan_data in wans_raw.items():
                        isp = wan_data.get("ispInfo", {})
                        wans.append({
                            "name": wan_name,
                            "external_ip": wan_data.get("externalIp", ""),
                            "isp": isp.get("name", ""),
                            "isp_org": isp.get("organization", ""),
                            "uptime_pct": wan_data.get("wanUptime", 0),
                            "issues": wan_data.get("wanIssues", []),
                        })

                    return {
                        "ok": True,
                        "wans": wans,
                        "gateway": {
                            "model": gw.get("shortname", ""),
                            "hardware_id": gw.get("hardwareId", ""),
                            "ids_mode": gw.get("ipsMode", "off"),
                            "inspection": gw.get("inspectionState", "off"),
                            "ips_rules": gw.get("ipsSignature", {}).get("rulesCount", 0),
                        },
                    }

            return {"ok": False, "error": "Site ikke funnet"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# 4. Firmware check
# ═══════════════════════════════════════════════════════════════════════════════


async def firmware_check_all(customer_id: str) -> dict[str, Any]:
    """Check every device on the controller against the firmware database.

    Returns a per-device firmware report and an aggregate summary.
    """
    client = await _controller_for_customer(customer_id)
    site = _default_site(customer_id)

    try:
        devices = await client.get_devices(site)
    finally:
        await client.close()

    results: list[dict[str, Any]] = []
    counts = {"ok": 0, "warning": 0, "critical": 0, "unknown": 0}

    for d in devices:
        model = d.get("model", "")
        firmware = d.get("version", "")
        name = d.get("name", d.get("hostname", d.get("mac", "?")))
        upgrade_avail = d.get("upgrade_to_firmware") or None

        fw = check_firmware(model, firmware)
        fw["device_name"] = name
        fw["mac"] = d.get("mac", "")
        fw["upgrade_available"] = upgrade_avail
        results.append(fw)

        severity = fw.get("severity", "unknown")
        counts[severity] = counts.get(severity, 0) + 1

    return {
        "devices": results,
        "total": len(results),
        "summary": counts,
        "all_up_to_date": counts["warning"] == 0 and counts["critical"] == 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Controller summary
# ═══════════════════════════════════════════════════════════════════════════════


async def get_controller_summary(customer_id: str) -> dict[str, Any]:
    """Aggregate overview of the entire controller: sites, devices, clients,
    WLANs and alarms across all sites (or the configured site).
    """
    client = await _controller_for_customer(customer_id)

    try:
        sites = await client.list_sites()
        site_key = _default_site(customer_id)

        total_devices = 0
        total_clients = 0
        total_wlans = 0
        total_alarms = 0
        site_summaries: list[dict[str, Any]] = []

        # If the customer has a specific site configured, only query that one.
        # Otherwise iterate all sites on the controller.
        target_sites = [site_key] if site_key != "all" else [
            s.get("name", "default") for s in sites
        ]

        for s_name in target_sites:
            devices, clients, wlans, alarms = await asyncio.gather(
                client.get_devices(s_name),
                client.get_clients(s_name),
                client.get_wlans(s_name),
                client.get_alarms(s_name),
            )

            online = sum(1 for d in devices if d.get("state", 0) == 1)
            offline = len(devices) - online

            site_summaries.append({
                "site": s_name,
                "devices": len(devices),
                "devices_online": online,
                "devices_offline": offline,
                "clients": len(clients),
                "wlans": len(wlans),
                "alarms": len(alarms),
            })

            total_devices += len(devices)
            total_clients += len(clients)
            total_wlans += len(wlans)
            total_alarms += len(alarms)

        # Find the site description for human-friendly names
        site_desc_map = {s.get("name", ""): s.get("desc", s.get("name", "")) for s in sites}

        return {
            "total_sites": len(sites),
            "total_devices": total_devices,
            "total_clients": total_clients,
            "total_wlans": total_wlans,
            "total_alarms": total_alarms,
            "sites_queried": len(target_sites),
            "site_details": [
                {**sd, "description": site_desc_map.get(sd["site"], sd["site"])}
                for sd in site_summaries
            ],
            "controller_type": "UniFi OS" if client.is_unifi_os else "Classic",
        }
    finally:
        await client.close()
