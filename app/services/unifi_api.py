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
import hashlib
import logging
import time
from typing import Any, Optional

import httpx

from app.core.credentials import get_secret, store_secret
from app.core.customer import CustomerManager
from app.core.name_match import (
    MATCH_AMBIGUOUS_GAP,
    MATCH_AUTO,
    normalise_org_name,
    score_name_match,
)
from app.integrations.http_retry import send_with_retry
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
#
# Keyed by the credentials, not by the username. The comment here used to
# claim (username, store_for_customer) while the code kept one flat slot and
# compared the username alone, so for an hour after a successful login *any*
# password under that name came back "ok" without a round-trip to ui.com. The
# whole job of this function is to say whether these credentials work; the
# cache made it unable to say no. An operator who mistyped a password saw a
# green tick, and the cached token was then stored against the customer they
# were configuring.
#
# The password is hashed rather than held: a wrong one must miss the cache,
# which needs no more than that, and module-level state is the last place a
# plaintext password should sit.
_token_cache: dict[str, dict[str, Any]] = {}
_TOKEN_TTL = 3600  # seconds
_TOKEN_CACHE_MAX = 32


def _sso_cache_key(username: str, password: str) -> str:
    return hashlib.sha256(f"{username}\0{password}".encode()).hexdigest()


def _sso_cache_get(key: str) -> dict[str, Any] | None:
    entry = _token_cache.get(key)
    if entry and entry["expires"] > time.monotonic():
        return entry
    _token_cache.pop(key, None)
    return None


def _sso_cache_put(key: str, token: str, result: dict[str, Any]) -> None:
    now = time.monotonic()
    for stale in [k for k, v in _token_cache.items() if v["expires"] <= now]:
        del _token_cache[stale]
    if len(_token_cache) >= _TOKEN_CACHE_MAX:
        del _token_cache[min(_token_cache, key=lambda k: _token_cache[k]["expires"])]
    _token_cache[key] = {"token": token, "expires": now + _TOKEN_TTL, "result": result}


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
        entry = _sso_cache_get(_sso_cache_key(username, password))
        if entry:
            log.debug("Returning cached SSO token (expires in %ds)",
                      int(entry["expires"] - time.monotonic()))
            cached = entry["result"]
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
                _sso_cache_put(_sso_cache_key(username, password), token, result)
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
            # ui.com rate-limits, and this is the first call of a sync.
            # One attempt meant a throttled tenant reported "no consoles".
            r_hosts = await send_with_retry(
                lambda: http.get(_UI_HOSTS_URL, headers=headers),
                method="GET", target="UniFi Site Manager hosts",
            )
            if r_hosts.status_code == 401:
                return {"ok": False, "error": "API-nøkkel ugyldig eller utløpt"}
            r_hosts.raise_for_status()
            hosts = r_hosts.json().get("data", [])

            # Fetch sites for device/client counts
            r_sites = await send_with_retry(
                lambda: http.get(_UI_SITES_URL, headers=headers),
                method="GET", target="UniFi Site Manager sites",
            )
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


def summarise_devices(raw: list[dict]) -> list[dict[str, Any]]:
    """Flatten the per-host device payload into one row per device.

    Pure, so the shape can be tested without a network call.

    Note on firmware: ``updateAvailable`` is an empty string on every device in
    a live account, including the ones whose ``firmwareStatus`` says an update
    is waiting. It is carried through for compatibility but must not be read as
    "the version on offer" — ``firmware_status`` is the field with the signal.
    """
    from datetime import datetime, timezone

    from app.core.utils import format_uptime

    result: list[dict[str, Any]] = []
    for host_group in raw:
        h_name = host_group.get("hostName", "")
        h_id = host_group.get("hostId", "")
        for d in host_group.get("devices", []):
            # An offline device has no startupTime, because it is not up. The
            # append used to sit inside `if startup:`, so those devices were
            # dropped from the list entirely — 5 of 260 in a live account, all
            # of them offline. The sort below promises "offline first"; this
            # bug is what stopped it ever having anything to promote.
            uptime_str = ""
            startup = d.get("startupTime", "")
            if startup:
                try:
                    st = datetime.fromisoformat(startup.replace("Z", "+00:00"))
                    uptime_str = format_uptime((datetime.now(timezone.utc) - st).total_seconds())
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

    # Offline first, then firmware waiting, then by host and name: the order a
    # technician reads it in.
    result.sort(key=lambda x: (
        0 if x["status"] == "offline" else 1,
        0 if x["firmware_status"] == "updateAvailable" else 1,
        x["host_name"].lower(),
        x["name"].lower(),
    ))
    return result


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
            r = await send_with_retry(
                lambda: http.get(url, headers=headers),
                method="GET", target="UniFi Site Manager devices",
            )
            if r.status_code == 401:
                return {"ok": False, "error": "API-nøkkel ugyldig"}
            r.raise_for_status()

            raw = r.json().get("data", [])
            result = summarise_devices(raw)

            return {"ok": True, "devices": result, "count": len(result)}
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ISP metrics (v1/isp-metrics)
# ═══════════════════════════════════════════════════════════════════════════════


def _isp_mean(wans: list[dict], field: str, digits: int) -> float | None:
    """Average a WAN field across readings, or None when nothing reported it."""
    values = [w.get(field) for w in wans if w.get(field) is not None]
    return round(sum(values) / len(values), digits) if values else None


def _isp_mean_mbps(wans: list[dict], field: str) -> float | None:
    """Average a kbps field and return Mbps, or None when nothing reported it."""
    mean_kbps = _isp_mean(wans, field, 0)
    return round(mean_kbps / 1000, 1) if mean_kbps is not None else None


def _isp_max(wans: list[dict], field: str) -> float | None:
    """The worst reading in the window, or None when nothing reported it."""
    values = [w.get(field) for w in wans if w.get(field) is not None]
    return max(values) if values else None


def _kbps_to_mbps(value: Any) -> float | None:
    return round(value / 1000, 1) if isinstance(value, (int, float)) else None


def summarise_isp_sites(raw: list[dict]) -> list[dict[str, Any]]:
    """Reduce the ISP metrics payload to one summary per site.

    Pure, so the shape this parses can be tested without a network call —
    the previous parser read a path that did not exist and nothing caught
    it, because the only way to exercise it was against the live API.
    """
    # One entry per site, each carrying its readings under "periods".
    # This used to read entry["data"]["wan"] — a path that does not
    # exist on a site entry, so wan_data was always {} and every field
    # collapsed to zero. Confirmed against the live API: the readings
    # are at entry["periods"][]["data"]["wan"], 283 of them per site
    # for 5m/24h, and data_points was counting sites rather than
    # readings, which is why the panel said "1 reading".
    sites_summary = []
    for site_entry in raw:
        site_id = site_entry.get("siteId") or site_entry.get("hostId") or "unknown"
        wans = [
            period.get("data", {}).get("wan")
            for period in site_entry.get("periods") or []
            if period.get("data", {}).get("wan")
        ]
        latest_wan = wans[-1] if wans else {}

        sites_summary.append({
            "site_id": site_id,
            "host_id": site_entry.get("hostId"),
            "isp": latest_wan.get("ispName") or "",
            "isp_asn": latest_wan.get("ispAsn"),
            # Distinguishes "the API returned nothing for this site"
            # from "the API returned genuine zeros".
            "has_readings": bool(wans),
            "latest": {
                "download_mbps": _kbps_to_mbps(latest_wan.get("download_kbps")),
                "upload_mbps": _kbps_to_mbps(latest_wan.get("upload_kbps")),
                "latency_ms": latest_wan.get("avgLatency"),
                "max_latency_ms": latest_wan.get("maxLatency"),
                "packet_loss": latest_wan.get("packetLoss"),
                "uptime_pct": latest_wan.get("uptime"),
            },
            "averages": {
                "download_mbps": _isp_mean_mbps(wans, "download_kbps"),
                "upload_mbps": _isp_mean_mbps(wans, "upload_kbps"),
                "latency_ms": _isp_mean(wans, "avgLatency", 1),
                "max_latency_ms": _isp_mean(wans, "maxLatency", 1),
                "packet_loss": _isp_mean(wans, "packetLoss", 2),
                "uptime_pct": _isp_mean(wans, "uptime", 1),
            },
            "worst": {
                # A 24-hour average hides a five-minute outage. The
                # worst reading in the window is what a technician
                # actually needs to see.
                "max_latency_ms": _isp_max(wans, "maxLatency"),
                "packet_loss": _isp_max(wans, "packetLoss"),
                "downtime": _isp_max(wans, "downtime"),
            },
            "data_points": len(wans),
        })
    return sites_summary


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

            sites_summary = summarise_isp_sites(raw)

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


# ═══════════════════════════════════════════════════════════════════════════════
# 9. API diagnostics — discover response shapes without handling the key
# ═══════════════════════════════════════════════════════════════════════════════
#
# The Site Manager documentation is rendered client-side and cannot be read by
# a fetch, and the response shapes have drifted from what this module was
# written against — get_isp_metrics was parsing entry["data"]["wan"], found
# nothing, and rendered a full grid of zeros. Guessing the next path is how
# that happens twice.
#
# So: ask the live API what it returns, and report only the *shape*. Key names
# and value types are schema; they are safe to show. Values are customer data
# and never leave this function. That distinction is the whole design.


_SHAPE_MAX_DEPTH = 6
_SHAPE_MAX_KEYS = 400


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def describe_shape(
    value: Any,
    path: str = "",
    out: dict[str, str] | None = None,
    depth: int = 0,
) -> dict[str, str]:
    """Map dotted key paths to value types, carrying no values across.

    A list is described by its first element under a ``[]`` segment, with its
    length recorded on the list itself — enough to tell "no readings" from "a
    reading full of nulls", which is exactly the distinction that was lost.
    """
    if out is None:
        out = {}
    if len(out) >= _SHAPE_MAX_KEYS or depth > _SHAPE_MAX_DEPTH:
        return out

    if isinstance(value, dict):
        if path:
            out[path] = "object"
        for key in sorted(value):
            child = f"{path}.{key}" if path else key
            describe_shape(value[key], child, out, depth + 1)
    elif isinstance(value, list):
        out[path or "(root)"] = f"array[{len(value)}]"
        if value:
            describe_shape(value[0], f"{path}[]", out, depth + 1)
    else:
        out[path or "(root)"] = _type_name(value)
    return out


async def probe_site_manager_api() -> dict[str, Any]:
    """Probe the Site Manager endpoints and report status and response shape.

    Returns no field values — only paths, types and counts. The API key is read
    from the store, used, and never echoed.
    """
    token = _resolve_token(None, None)
    if not token:
        return {"ok": False, "error": "Ingen API-nøkkel tilgjengelig"}

    headers = _build_api_headers(token)
    auth_scheme = "Bearer" if "Authorization" in headers else "X-API-KEY"

    probes = [
        ("hosts", _UI_HOSTS_URL),
        ("sites", _UI_SITES_URL),
        ("devices", _UI_DEVICES_URL),
        ("isp-metrics/5m", f"{_UI_ISP_METRICS_URL}/5m?duration=24h"),
        ("isp-metrics/1h", f"{_UI_ISP_METRICS_URL}/1h?duration=7d"),
    ]

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=60.0) as http:
        for name, url in probes:
            entry: dict[str, Any] = {"name": name, "url": url.split("?")[0]}
            try:
                r = await http.get(url, headers=headers)
                entry["status"] = r.status_code
                if r.status_code != 200:
                    # The body may name the reason (bad key, no permission).
                    # It may also carry data, so only its shape is reported.
                    try:
                        entry["shape"] = describe_shape(r.json())
                    except Exception:
                        entry["shape"] = {}
                    entry["ok"] = False
                else:
                    payload = r.json()
                    entry["ok"] = True
                    entry["shape"] = describe_shape(payload)
                    data = payload.get("data") if isinstance(payload, dict) else payload
                    entry["count"] = len(data) if isinstance(data, list) else None
            except Exception as e:
                entry["ok"] = False
                entry["status"] = None
                entry["error"] = type(e).__name__
            results.append(entry)

    return {"ok": True, "auth_scheme": auth_scheme, "probes": results}


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Site overview — the statistics block /v1/sites already returns
# ═══════════════════════════════════════════════════════════════════════════════
#
# One call carries device and client counts, firmware debt, WAN uptime per
# link, external IPs, ISP identity and the gateway's IPS posture for every
# site. The panel was computing a thinner version of this from other calls.


_IPS_POSTURE = {
    # UniFi reports prevention and detection as different modes and the
    # difference matters: IDS raises an alert and lets the traffic through.
    # Reporting both as "enabled" would flatter a gateway that is not blocking
    # anything.
    "ips": ("IPS", "ok"),
    "ids": ("IDS", "warn"),
    "disabled": ("Disabled", "bad"),
}


def classify_ips_mode(mode: Any) -> tuple[str, str]:
    """Map a gateway's ipsMode to a label and a severity.

    An unreported mode is Unknown, never Disabled. Two thirds of the sites in a
    real account report no gateway block at all — rendering those as "IPS off"
    would invent a security finding per site, the same mistake
    :func:`wlan_security_label` exists to avoid for open WiFi.
    """
    if not isinstance(mode, str) or not mode.strip():
        return ("Unknown", "unknown")
    return _IPS_POSTURE.get(mode.strip().lower(), (mode, "unknown"))


def summarise_sites(raw: list[dict]) -> list[dict[str, Any]]:
    """Reduce /v1/sites to one row per site, with the findings made explicit.

    Counts are reported as the API gives them; what this adds is the reading a
    technician would otherwise do by eye — which sites have devices down,
    firmware pending, a WAN with logged issues, or a gateway not blocking.
    """
    rows: list[dict[str, Any]] = []
    for site in raw:
        stats = site.get("statistics") or {}
        counts = stats.get("counts") or {}
        gateway = stats.get("gateway") or {}
        meta = site.get("meta") or {}
        isp = stats.get("ispInfo") or {}

        wans = []
        for name, wan in sorted((stats.get("wans") or {}).items()):
            wan_isp = wan.get("ispInfo") or {}
            issues = wan.get("wanIssues") or []
            wans.append({
                "name": name,
                "external_ip": wan.get("externalIp"),
                "uptime_pct": wan.get("wanUptime"),
                "isp": wan_isp.get("name") or "",
                "isp_asn": wan_isp.get("asn"),
                "issue_count": sum(i.get("count", 1) for i in issues),
                # A logged downtime event is worth more than an issue count:
                # it is the difference between "degraded" and "was down".
                "had_downtime": any(i.get("wanDowntime") for i in issues),
            })

        ips_label, ips_severity = classify_ips_mode(gateway.get("ipsMode"))
        offline = counts.get("offlineDevice") or 0
        pending = counts.get("pendingUpdateDevice") or 0
        critical = counts.get("criticalNotification") or 0

        rows.append({
            "site_id": site.get("siteId"),
            "host_id": site.get("hostId"),
            "name": meta.get("name") or "",
            "description": meta.get("desc") or "",
            "timezone": meta.get("timezone") or "",
            "gateway_mac": meta.get("gatewayMac") or "",
            "devices": {
                "total": counts.get("totalDevice") or 0,
                "offline": offline,
                "wifi": counts.get("wifiDevice") or 0,
                "wifi_offline": counts.get("offlineWifiDevice") or 0,
                "wired": counts.get("wiredDevice") or 0,
                "wired_offline": counts.get("offlineWiredDevice") or 0,
                "gateway": counts.get("gatewayDevice") or 0,
                "gateway_offline": counts.get("offlineGatewayDevice") or 0,
                "pending_update": pending,
            },
            "clients": {
                "wifi": counts.get("wifiClient") or 0,
                "wired": counts.get("wiredClient") or 0,
                "guest": counts.get("guestClient") or 0,
                "total": (counts.get("wifiClient") or 0) + (counts.get("wiredClient") or 0),
            },
            "isp": {
                "name": isp.get("name") or "",
                "asn": isp.get("asn"),
                "organization": isp.get("organization") or "",
            },
            "wan_uptime_pct": (stats.get("percentages") or {}).get("wanUptime"),
            "tx_retry_pct": (stats.get("percentages") or {}).get("txRetry"),
            "gateway": {
                "model": gateway.get("shortname") or "",
                "ips_mode": gateway.get("ipsMode"),
                "ips_label": ips_label,
                "ips_severity": ips_severity,
                "ips_rules": (gateway.get("ipsSignature") or {}).get("rulesCount"),
                "ips_signature": (gateway.get("ipsSignature") or {}).get("type") or "",
                "inspection_state": gateway.get("inspectionState") or "",
            },
            "wans": wans,
            # Ordered by how much a technician cares, so a caller can sort on
            # it without re-deriving the priorities.
            "findings": [
                f
                for f in (
                    f"{critical} kritiske varsler" if critical else None,
                    f"{offline} enheter offline" if offline else None,
                    "gateway blokkerer ikke" if ips_severity == "bad" else None,
                    "IDS varsler men blokkerer ikke" if ips_severity == "warn" else None,
                    f"{pending} venter fastvareoppdatering" if pending else None,
                    "WAN har hatt nedetid" if any(w["had_downtime"] for w in wans) else None,
                )
                if f
            ],
        })
    return rows


async def get_site_overview() -> dict[str, Any]:
    """Fetch /v1/sites and reduce it to one summarised row per site."""
    token = _resolve_token(None, None)
    if not token:
        return {"ok": False, "error": "Ingen API-nøkkel tilgjengelig"}

    async with httpx.AsyncClient(timeout=60.0) as http:
        try:
            r = await http.get(_UI_SITES_URL, headers=_build_api_headers(token))
            if r.status_code == 401:
                return {"ok": False, "error": "API-nøkkel ugyldig"}
            r.raise_for_status()
            return {"ok": True, "sites": summarise_sites(r.json().get("data", []))}
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            log.warning("Site overview failed: %s", e)
            return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Controller coverage — which customers can actually be reached
# ═══════════════════════════════════════════════════════════════════════════════
#
# The cloud key answers for the whole account but stops at counts: it has no
# clients endpoint, and the Network API behind a console is not reachable
# through it. Everything past that — per-site clients, firewall zones, ACLs —
# needs a controller login stored against the customer.
#
# That storage has existed all along (POST /api/unifi/save). What did not was
# any way to see where it is missing: has_credentials was reported for the
# active customer only, one at a time, so "which of my customers can I not
# audit" could only be answered by clicking through them.


_UNIFI_MODE_DIRECT = "direct"


def classify_controller_access(customer: dict, has_credentials: bool) -> tuple[str, str]:
    """Describe what can be collected for a customer, and why not more.

    Returns ``(state, reason)``. The reason is the missing piece, phrased as
    the next action rather than as a fault — a customer with no UniFi at all is
    not a gap to fix.
    """
    host = (customer.get("UniFiHost") or "").strip()
    direct = customer.get("UniFiDirectDevices") or []
    mode = customer.get("UniFiMode", "controller")

    if mode == _UNIFI_MODE_DIRECT and direct:
        # Direct device access reads the devices themselves; there is no
        # controller to hold clients or firewall policy.
        return ("direct", "per-enhet, ingen controller")
    if not host:
        # A matched console proves UniFi is there and names the box. Filing
        # that under "no UniFi" alongside customers who genuinely have none
        # buried the one list worth acting on — we know what is installed and
        # only lack a way in.
        if (customer.get("UniFiHostId") or "").strip():
            return ("cloud_only", "konsoll kjent i skyen, controller-adresse mangler")
        return ("none", "ingen controller registrert")
    if not has_credentials:
        return ("host_only", "adresse lagret, mangler brukernavn/passord")
    return ("full", "")


def summarise_controller_coverage(rows: list[dict]) -> dict[str, Any]:
    """Aggregate per-customer access into a portfolio answer.

    ``rows`` are dicts of ``{customer_id, name, state, reason, host, site}``.
    """
    by_state: dict[str, int] = {}
    for row in rows:
        by_state[row["state"]] = by_state.get(row["state"], 0) + 1
    # Actionable means a stored credential would change the answer. A known
    # console with no controller address qualifies — more so than the rest,
    # since the box is identified and only access is missing. "none" and
    # "direct" remain answers, not gaps.
    actionable = [r for r in rows if r["state"] in ("host_only", "cloud_only")]
    return {
        "ok": True,
        "customers": rows,
        "counts": by_state,
        "total": len(rows),
        "with_full_access": by_state.get("full", 0),
        "needs_credentials": len(actionable),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Matching cloud sites to customers
# ═══════════════════════════════════════════════════════════════════════════════
#
# An IT Glue import creates customers with a name and nothing else, and the
# cloud lists sites with a name and nothing else. Nothing joins the two, so the
# coverage view cannot say which customer a site belongs to — or, more usefully,
# which customer a controller login would unlock.
#
# Scoring follows the Uniweb matcher already in the tree (exact 1.0, containment
# 0.85, SequenceMatcher otherwise, auto at 0.75) so there is one notion of
# "matched" in this codebase rather than two that disagree.

async def get_hosts_with_names() -> dict[str, Any]:
    """Fetch the consoles and the names they are known by.

    The customer's identity lives here, not on the site. A site is named
    "default" on 29 of 30 consoles in a live account, or an opaque id on the
    rest; the console carries the real name — "A-Tre-Konsult-AS" — because that
    is what a technician typed when adopting it.
    """
    token = _resolve_token(None, None)
    if not token:
        return {"ok": False, "error": "Ingen API-nøkkel tilgjengelig"}

    async with httpx.AsyncClient(timeout=60.0) as http:
        try:
            r = await http.get(_UI_HOSTS_URL, headers=_build_api_headers(token))
            if r.status_code == 401:
                return {"ok": False, "error": "API-nøkkel ugyldig"}
            r.raise_for_status()
            hosts = []
            for h in r.json().get("data", []):
                reported = h.get("reportedState") or {}
                hosts.append({
                    "host_id": h.get("id", ""),
                    "name": reported.get("hostname") or reported.get("name") or "",
                })
            return {"ok": True, "hosts": hosts}
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            log.warning("Host listing failed: %s", e)
            return {"ok": False, "error": str(e)}


def match_hosts_to_customers(
    hosts: list[dict], customers: list[dict], include_linked: bool = False
) -> list[dict[str, Any]]:
    """Propose a customer for each console. Proposes only — writes nothing.

    Matching used to run against site names, which carry no identity: 29 of 30
    are literally "default" and the rest are opaque ids, so it proposed nothing
    for 76 of 77. The console name is what a technician typed at adoption, and
    it is hyphenated rather than spaced — which is why normalise_org_name turns
    a hyphen into a space.

    Every console comes back, including those with no candidate, because "no
    match" is the answer for one belonging to a customer that was never
    imported, and hiding those would make the list look complete when it is not.
    """
    # A customer already carrying a console is not a candidate for another one,
    # the way the Uniweb matcher only considers rows with customer_id IS NULL.
    # UniFiHostId is a single field: proposing a second console for a customer
    # that has one means the later apply overwrites the earlier, and nothing
    # says which link was lost. Re-matching is opt-in for exactly that reason.
    candidates = [
        (c, normalise_org_name(c.get("CustomerName", "")))
        for c in customers
        if normalise_org_name(c.get("CustomerName", ""))
        and (include_linked or not (c.get("UniFiHostId") or "").strip())
    ]

    # A console already linked to a customer is done. Excluding linked
    # *customers* alone left the finished consoles hunting through whatever
    # customers remained and settling on unrelated ones — after linking 19 of
    # 30, a re-run offered 18 spurious proposals that were pure noise.
    linked_hosts = {
        (c.get("UniFiHostId") or "").strip()
        for c in customers
        if (c.get("UniFiHostId") or "").strip()
    }

    proposals: list[dict[str, Any]] = []
    for host in hosts:
        if not include_linked and (host.get("host_id") or host.get("id")) in linked_hosts:
            continue
        host_name = host.get("name") or ""
        normalised = normalise_org_name(host_name)

        scored = sorted(
            ((score_name_match(normalised, cn), c) for c, cn in candidates),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best_score, best = scored[0] if scored else (0.0, None)
        runner_up = scored[1][0] if len(scored) > 1 else 0.0

        if best_score >= MATCH_AUTO and (best_score - runner_up) < MATCH_AMBIGUOUS_GAP:
            confidence = "ambiguous"
        elif best_score >= MATCH_AUTO:
            confidence = "high"
        elif best_score >= 0.5:
            confidence = "low"
        else:
            confidence = "none"

        proposals.append({
            "host_id": host.get("host_id") or host.get("id"),
            "host_name": host_name,
            "customer_id": best.get("_id", "") if best and confidence != "none" else "",
            "customer_name": best.get("CustomerName", "") if best and confidence != "none" else "",
            "score": round(best_score, 3),
            "runner_up_score": round(runner_up, 3),
            "confidence": confidence,
        })

    # Ambiguity was only ever checked one way: is this console's best match
    # close to its runner-up? Nothing asked the reverse — is this customer also
    # the best match for another console? Three customers were proposed twice
    # in a live account, and since UniFiHostId holds one value, accepting both
    # halves of a pair would have overwritten the first without a word.
    claimed: dict[str, int] = {}
    for p in proposals:
        if p["customer_id"]:
            claimed[p["customer_id"]] = claimed.get(p["customer_id"], 0) + 1
    for p in proposals:
        contested = p["customer_id"] and claimed.get(p["customer_id"], 0) > 1
        p["contested"] = bool(contested)
        if contested and p["confidence"] == "high":
            # Still the best name match — but not one to apply unattended.
            p["confidence"] = "ambiguous"

    # Ambiguous first: they need a human before anything else is worth doing.
    order = {"ambiguous": 0, "low": 1, "high": 2, "none": 3}
    proposals.sort(key=lambda p: (order[p["confidence"]], -p["score"]))
    return proposals


def summarise_host_matches(proposals: list[dict]) -> dict[str, Any]:
    """Counts by confidence, so the caller can see the shape before applying."""
    counts: dict[str, int] = {}
    for p in proposals:
        counts[p["confidence"]] = counts.get(p["confidence"], 0) + 1
    return {
        "ok": True,
        "proposals": proposals,
        "counts": counts,
        "total": len(proposals),
        # Only unambiguous matches are safe to apply without a decision.
        "auto_applicable": counts.get("high", 0),
        "needs_review": counts.get("ambiguous", 0) + counts.get("low", 0),
    }
