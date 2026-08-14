"""Network provisioning wizard — 5-step guided setup.

Ported from SuperManager's provisioning wizard.  Walks a technician through
customer details, network topology, services, security hardening, and finally
generates FortiGate CLI / UniFi JSON configs ready for deployment.

Supports deployment via SSH CLI or REST API (PUT /api/v2/cmdb/).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory wizard sessions (session_id -> WizardState)
_sessions: dict[str, dict] = {}
_SESSION_TTL = 3600  # 1 hour
_SESSION_MAX = 50


def _cleanup_sessions() -> None:
    """Remove expired sessions to prevent memory leaks."""
    now = datetime.now(timezone.utc)
    expired = []
    for sid, s in _sessions.items():
        try:
            created = datetime.fromisoformat(s.get("created_at", ""))
            if (now - created).total_seconds() > _SESSION_TTL:
                expired.append(sid)
        except (ValueError, TypeError):
            expired.append(sid)
    for sid in expired:
        _sessions.pop(sid, None)
    # Cap total sessions
    while len(_sessions) > _SESSION_MAX:
        _sessions.pop(next(iter(_sessions)))


_SECRET_KEYS = re.compile(r"password|passphrase|token|secret|api[_-]?key|psk", re.IGNORECASE)


def _redact(value):
    """Mask credential values by key name, recursively; structure preserved.

    The wizard collects a device password and API token in its steps, and the
    client-facing getters used to hand them straight back (SR-001 #4). The raw
    values stay in the server-side session for the deploy that needs them.
    """
    if isinstance(value, dict):
        return {
            k: ("••••••"
                if isinstance(v, str) and v and _SECRET_KEYS.search(str(k))
                else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


class WizardStep:
    CUSTOMER = 1
    NETWORK = 2
    SERVICES = 3
    SECURITY = 4
    REVIEW = 5


# ── Session Lifecycle ────────────────────────────────────────────────────────


def start_session(user_id: str, customer_id: str = "") -> dict:
    """Start a new wizard session, bound to its owner and customer.

    customer_id is the customer active when the wizard began; every later
    operation is checked against it, and the deploy resolves that customer's
    credentials rather than whichever customer happens to be active later
    (SR-001 #1).
    """
    _cleanup_sessions()
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "id": session_id,
        "user_id": user_id,
        "customer_id": customer_id,
        "current_step": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "steps": {1: None, 2: None, 3: None, 4: None, 5: None},
        "generated": None,
    }
    return {"session_id": session_id, "current_step": 1}


def get_session_raw(session_id: str) -> Optional[dict]:
    """The unredacted session, for internal ownership/authorization checks."""
    return _sessions.get(session_id)


def get_session(session_id: str) -> Optional[dict]:
    """Client-facing session state, with step credentials masked (SR-001 #4)."""
    session = _sessions.get(session_id)
    if session is None:
        return None
    view = dict(session)
    view["steps"] = _redact(session.get("steps", {}))
    return view


def submit_step(session_id: str, step: int, data: dict) -> dict:
    """Submit data for a wizard step."""
    from app.core.exceptions import NotFoundError, ValidationError
    session = _sessions.get(session_id)
    if not session:
        raise NotFoundError("Session not found")
    if step < 1 or step > 5:
        raise ValidationError("Invalid step")
    session["steps"][step] = data
    session["current_step"] = min(step + 1, 5)
    return {"ok": True, "current_step": session["current_step"]}


def get_summary(session_id: str) -> dict:
    """Return a summary of all steps for review."""
    from app.core.exceptions import NotFoundError
    session = _sessions.get(session_id)
    if not session:
        raise NotFoundError("Session not found")
    return {
        "session_id": session_id,
        "steps": _redact(session["steps"]),
        "complete": all(session["steps"][i] is not None for i in range(1, 5)),
    }


def delete_session(session_id: str) -> bool:
    return _sessions.pop(session_id, None) is not None


def list_sessions(user_id: Optional[str] = None) -> list[dict]:
    sessions = list(_sessions.values())
    if user_id:
        sessions = [s for s in sessions if s["user_id"] == user_id]
    return [
        {"id": s["id"], "current_step": s["current_step"], "created_at": s["created_at"]}
        for s in sessions
    ]


# ── Config Generation ────────────────────────────────────────────────────────


async def generate_configs(session_id: str, use_ai: bool = False) -> dict:
    """Generate FortiGate CLI and/or UniFi JSON configs from wizard data."""
    from app.core.exceptions import NotFoundError
    session = _sessions.get(session_id)
    if not session:
        raise NotFoundError("Session not found")

    steps = session["steps"]
    customer = steps.get(1, {}) or {}
    network = steps.get(2, {}) or {}
    services = steps.get(3, {}) or {}
    security = steps.get(4, {}) or {}

    device_type = customer.get("device_type", "fortigate")
    result: dict = {"session_id": session_id, "configs": {}}

    if use_ai:
        result["configs"] = await _generate_with_ai(
            customer, network, services, security, device_type,
        )
    else:
        if device_type in ("fortigate", "both"):
            result["configs"]["fortigate_cli"] = _generate_fortigate_cli(
                customer, network, services, security,
            )
        if device_type in ("unifi", "both"):
            result["configs"]["unifi_json"] = _generate_unifi_json(
                customer, network, services, security,
            )

    session["generated"] = result["configs"]
    return result


# ── Deployment ───────────────────────────────────────────────────────────────


def _resolve_fortigate_conn(steps: dict, target_host: str = "", customer_id: str = "") -> dict:
    """Resolve all FortiGate connection variables with consistent precedence.

    Order (most → least specific):
      1. Wizard step 1 (customer) — explicit user input
      2. Active customer config (FortiGateHost/Port/VDOM/VerifySSL/AdminUser/ApiUser)
      3. Keyring secrets (fortigate_api_token, fortigate_admin_password, fortigate_admin_user)
      4. Hardcoded defaults (port 8443 post-bootstrap, vdom root, verify False, user admin)

    Returns a dict with all keys populated — never returns None values.
    """
    customer_step = steps.get(1, {}) or {}
    security_step = steps.get(4, {}) or {}

    # Active customer config + keyring lookups
    active_cfg: dict = {}
    cust_id = ""
    try:
        from app.core.customer import CustomerManager
        # The session's bound customer, not whichever is active now — the deploy
        # must use the credentials of the customer the wizard was started for
        # (SR-001 #1/#5), regardless of what the operator switched to since.
        customer = (
            CustomerManager.get_customer(customer_id) if customer_id
            else CustomerManager.get_active()
        )
        if customer:
            cust_id = customer.get("_id", "")
            active_cfg = customer
    except Exception as e:
        logger.warning("Failed to read customer for FortiGate conn resolve: %s", e)

    def _from_keyring(name: str) -> str:
        if not cust_id:
            return ""
        try:
            from app.core.credentials import get_secret
            return get_secret(cust_id, name) or ""
        except Exception:
            return ""

    # Host.
    #
    # A caller-supplied target_host used to win outright while the admin
    # password and API token below still came from the *customer's* keyring,
    # so pointing a deploy at an attacker-controlled address exfiltrated a
    # stored firewall credential. Reading those secrets directly needs admin
    # plus customer access and is activity-logged; deploy needs only
    # technician, which made this the cheaper route to the same material.
    #
    # The guard keys on whether a *stored credential* will be used, not on
    # whether a host happens to be configured. Those are independent:
    # /fortigate/save writes FortiGateHost unconditionally from the request
    # body, so an omitted "host" field blanks it while the keyring secrets
    # stay — and a host-keyed check would then wave the request through.
    #
    # Only the body-supplied override is constrained. The wizard's own Step 1
    # "Target host" is the operator typing an address into the form in front
    # of them, which is the documented precedence and not the exfiltration
    # path; constraining it too broke provisioning a replacement unit on its
    # management IP.
    configured = (active_cfg.get("FortiGateHost") or "").strip()
    wizard_host = (customer_step.get("target_host") or "").strip()
    requested = (target_host or "").strip()
    host = requested or wizard_host or configured or ""

    stored_secret_in_play = bool(
        (not customer_step.get("api_token") and _from_keyring("fortigate_api_token"))
        or (
            not customer_step.get("password")
            and not security_step.get("admin_password")
            and _from_keyring("fortigate_admin_password")
        )
    )
    # A stored credential belongs to the customer's configured device and must
    # not travel to any other address — whether that address came from the
    # deploy body or from the wizard's own "target host" field. The earlier
    # guard constrained only the body override and exempted the wizard field,
    # which reopened the exfiltration path: a Step 1 target_host pointed at an
    # attacker's IP still received the customer's stored FortiGate token
    # (SR-001 #5). Compared case-insensitively — hostnames are not case
    # sensitive, and a refusal over "FW.ACME.NO" vs "fw.acme.no" is false.
    #
    # For a genuine replacement or bootstrap unit on a different IP, the
    # operator supplies an explicit API token or admin password in the wizard;
    # that flips stored_secret_in_play to False and the deploy proceeds
    # (SR-001 #6).
    if stored_secret_in_play and host:
        if not configured:
            raise ValueError(
                "Kan ikke deploye med kundens lagrede FortiGate-legitimasjon når "
                "kunden ikke har en konfigurert adresse. Sett kundens FortiGate-"
                "adresse først, eller oppgi eksplisitt legitimasjon i wizarden."
            )
        if host.casefold() != configured.casefold():
            raise ValueError(
                f"Kan ikke deploye til {host} med kundens lagrede FortiGate-"
                f"legitimasjon: kunden er konfigurert med {configured}. For en "
                f"erstatnings-/bootstrap-enhet, oppgi eksplisitt API-token eller "
                f"admin-passord i wizarden."
            )

    # Port — bootstrap hardens admin-sport to 8443, that's the default
    raw_port = (customer_step.get("port")
                or active_cfg.get("FortiGatePort")
                or 8443)
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        port = 8443

    # VDOM
    vdom = (customer_step.get("vdom")
            or active_cfg.get("FortiGateVDOM")
            or "root")

    # SSL verify
    verify_ssl = customer_step.get("verify_ssl")
    if verify_ssl is None:
        verify_ssl = active_cfg.get("FortiGateVerifySSL", False)
    verify_ssl = bool(verify_ssl)

    # API token
    api_token = (customer_step.get("api_token")
                 or _from_keyring("fortigate_api_token")
                 or "")

    # SSH admin user — wizard "username" → keyring → "admin"
    admin_user = (customer_step.get("username")
                  or active_cfg.get("FortiGateAdminUser")
                  or _from_keyring("fortigate_admin_user")
                  or "admin")

    # SSH admin password — wizard step 1 "password" → step 4 "admin_password" → keyring
    admin_password = (customer_step.get("password")
                      or security_step.get("admin_password")
                      or _from_keyring("fortigate_admin_password")
                      or "")

    return {
        "host": host,
        "port": port,
        "vdom": vdom,
        "verify_ssl": verify_ssl,
        "api_token": api_token,
        "admin_user": admin_user,
        "admin_password": admin_password,
        "customer_id": cust_id,
        "customer_name": active_cfg.get("CustomerName", ""),
    }


async def deploy_config(
    session_id: str,
    method: str = "ssh",
    target_host: str = "",
) -> dict:
    """Deploy generated config to a device via SSH or REST API."""
    from app.core.exceptions import ValidationError
    session = _sessions.get(session_id)
    if not session or not session.get("generated"):
        raise ValidationError("No generated config to deploy")

    configs = session["generated"]
    results: dict = {}
    customer = session["steps"].get(1, {}) or {}

    conn = _resolve_fortigate_conn(
        session["steps"], target_host, customer_id=session.get("customer_id", "")
    )

    if not conn["host"]:
        return {"ok": False, "error": "Ingen FortiGate-host konfigurert (verken i wizard, kunde-config eller mål)"}

    logger.info(
        "Deploy via %s to %s:%d (vdom=%s, customer=%s, has_token=%s, has_pw=%s)",
        method, conn["host"], conn["port"], conn["vdom"],
        conn["customer_name"] or "(none)",
        bool(conn["api_token"]), bool(conn["admin_password"]),
    )

    if "fortigate_cli" in configs and method == "ssh":
        if not conn["admin_password"]:
            results["fortigate"] = {"ok": False, "error": "Ingen admin-passord tilgjengelig (verken i wizard eller keyring)"}
        else:
            try:
                from app.services.ssh_connection import SshSession

                ssh_conn = await SshSession.connect(
                    conn["host"],
                    username=conn["admin_user"],
                    password=conn["admin_password"],
                )
                # Allowlist: only FortiGate config commands are safe to execute
                _ALLOWED_CLI_PREFIXES = (
                    "config ", "edit ", "set ", "next", "end",
                    "append ", "unset ", "get ", "show ",
                )
                async with ssh_conn as session_ssh:
                    cli_lines = configs["fortigate_cli"].strip().splitlines()
                    executed = 0
                    for line in cli_lines:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if not any(line.startswith(p) or line == p.strip() for p in _ALLOWED_CLI_PREFIXES):
                            logger.warning("Rejected CLI line: %s", line[:80])
                            continue
                        # Replace masked password with real value at deploy time
                        if '********' in line:
                            line = line.replace('********', conn["admin_password"])
                        await session_ssh.exec(line, timeout=10)
                        executed += 1
                    results["fortigate"] = {"ok": True, "commands": executed}
            except Exception as e:
                results["fortigate"] = {"ok": False, "error": str(e)}

    if method == "rest":
        if not conn["api_token"]:
            results["fortigate"] = {"ok": False, "error": "Ingen API-token tilgjengelig for REST-deploy"}
        else:
            results["fortigate"] = await _deploy_via_rest(
                conn["host"], conn["api_token"], session["steps"], conn=conn,
            )

    if "unifi_json" in configs:
        results["unifi"] = await _deploy_unifi(
            conn["host"], configs["unifi_json"], customer,
            customer_id=session.get("customer_id", ""),
        )

    return {"ok": True, "results": results}


# ── UniFi Deployment ─────────────────────────────────────────────────────────


async def _deploy_unifi(
    host: str, unifi_json: str, customer: dict, customer_id: str = ""
) -> dict:
    """Deploy generated UniFi config to a controller via REST API.

    Creates networks (VLANs) via /api/s/{site}/rest/networkconf.

    Credential resolution order:
      1. Per-customer credentials from keyring (UniFiHost + unifi_username/password)
      2. Global controller settings from app settings
      3. Site Manager API key → resolve WAN IP for target host

    A customer's *stored* per-customer credentials only ever go to that
    customer's configured UniFiHost — never to a caller-supplied provisioning
    target — the same boundary the FortiGate path enforces (SR-001 #5). The
    customer is the session's bound one, not whichever is active now.
    """
    from app.core.config import load_app_settings
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager
    from app.modules.unifi_audit.client import UniFiControllerClient

    cust = (
        CustomerManager.get_customer(customer_id) if customer_id
        else CustomerManager.get_active()
    )
    cust_id = cust.get("_id", "") if cust else ""
    settings = load_app_settings()

    # --- Resolve controller host + credentials ---
    unifi_host = ""
    username = ""
    password = ""
    is_unifi_os = False
    site = "default"
    configured_host = ""
    stored_creds = False  # True once we resolve the customer's keyring secret

    # 1. Per-customer credentials
    if cust:
        configured_host = cust.get("UniFiHost", "")
        _u = get_secret(cust_id, "unifi_username") or ""
        _p = get_secret(cust_id, "unifi_password") or ""
        if _u and _p:
            username, password = _u, _p
            stored_creds = True
        unifi_host = configured_host
        is_unifi_os = cust.get("UniFiIsUniFiOS", False)
        site = cust.get("UniFiSite", "default")

    # 2. Global controller settings from app settings
    if not (unifi_host and username and password):
        ctrl_host = settings.get("unifi_controller_host", "")
        ctrl_user = settings.get("unifi_controller_username", "")
        ctrl_pass = settings.get("unifi_controller_password", "")
        if ctrl_host and ctrl_user and ctrl_pass:
            unifi_host = unifi_host or ctrl_host
            username = username or ctrl_user
            password = password or ctrl_pass

    # 3. Site Manager API key → resolve WAN IP for host
    if not unifi_host:
        api_key = settings.get("unifi_site_manager_api_key", "")
        if api_key:
            try:
                from app.services.unifi_api import site_manager_list_sites
                sm_result = await site_manager_list_sites(token=api_key)
                if sm_result.get("ok"):
                    # Match by customer name or use first online host
                    cust_name = (customer.get("name", "") or "").lower()
                    for s in sm_result.get("sites", []):
                        if s.get("wan_ip") and (
                            cust_name and cust_name in s.get("name", "").lower()
                            or s.get("status") == "online"
                        ):
                            unifi_host = s["wan_ip"]
                            break
            except Exception as e:
                logger.warning("Site Manager lookup failed: %s", e)

    # A stored per-customer credential must not travel to the caller-supplied
    # provisioning target (SR-001 #5). Only fall back to `host` when no stored
    # credential is in play, and refuse outright if a stored credential would
    # reach anything but the customer's configured UniFiHost.
    if not stored_creds:
        unifi_host = unifi_host or host
    if stored_creds:
        if not configured_host:
            return {
                "ok": False,
                "error": (
                    "Kundens UniFi-host er ikke konfigurert — kan ikke bruke "
                    "lagret legitimasjon mot en oppgitt adresse. Sett UniFi-host "
                    "først, eller oppgi eksplisitt legitimasjon."
                ),
            }
        if unifi_host.casefold() != configured_host.casefold():
            return {
                "ok": False,
                "error": (
                    f"Kan ikke sende kundens lagrede UniFi-legitimasjon til "
                    f"{unifi_host}: kunden er konfigurert med {configured_host}."
                ),
            }

    if not unifi_host:
        return {"ok": False, "error": "No UniFi controller host found — configure in Settings or per customer"}
    if not (username and password):
        return {"ok": False, "error": "No UniFi credentials available — set per customer or in Settings > UniFi Controller"}

    try:
        config = json.loads(unifi_json) if isinstance(unifi_json, str) else unifi_json
    except (json.JSONDecodeError, TypeError) as e:
        return {"ok": False, "error": f"Invalid UniFi JSON config: {e}"}

    client = UniFiControllerClient(
        host=unifi_host, username=username, password=password,
        is_unifi_os=is_unifi_os,
    )

    results: list[dict] = []
    try:
        await client._login()

        # Deploy networks (LAN + VLANs)
        for net in config.get("networks", []):
            payload = {
                "name": net.get("name", "Unnamed"),
                "purpose": net.get("purpose", "corporate"),
                "ip_subnet": net.get("subnet", ""),
                "dhcpd_enabled": net.get("dhcp_enabled", True),
                "domain_name": net.get("domain_name", ""),
            }
            if net.get("vlan_id"):
                payload["vlan"] = str(net["vlan_id"])
                payload["vlan_enabled"] = True
            if net.get("dhcp_start"):
                payload["dhcpd_start"] = net["dhcp_start"]
            if net.get("dhcp_stop"):
                payload["dhcpd_stop"] = net["dhcp_stop"]

            resp = await client._post(
                f"/api/s/{site}/rest/networkconf", payload,
            )
            meta = resp.get("meta", {})
            if meta.get("rc") == "ok" or resp.get("data"):
                results.append({"step": f"network:{net['name']}", "ok": True})
            else:
                results.append({
                    "step": f"network:{net['name']}",
                    "ok": False,
                    "error": meta.get("msg", "Unknown error"),
                })

        await client._logout()
    except Exception as e:
        return {"ok": False, "error": str(e), "partial_results": results}

    failed = [r for r in results if not r["ok"]]
    return {
        "ok": len(failed) == 0,
        "steps": results,
        "networks_created": len(results) - len(failed),
        "errors": len(failed),
    }


# ── Config Generators ────────────────────────────────────────────────────────


def _sanitize_fortigate_name(name: str) -> str:
    """Replace non-ASCII chars with ASCII equivalents for FortiGate."""
    import unicodedata
    # Explicit Nordic mappings (NFKD decomposition doesn't handle ø/Ø/æ/Æ)
    _map = {"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "å": "a", "Å": "A"}
    mapped = "".join(_map.get(c, c) for c in name)
    nfkd = unicodedata.normalize("NFKD", mapped)
    return nfkd.encode("ascii", "ignore").decode("ascii")


def _cidr_to_mask(cidr: str) -> str:
    """Convert '10.25.0.0/24' to '10.25.0.0 255.255.255.0'. Pass-through if no /."""
    if "/" not in cidr:
        return cidr + " 255.255.255.0"
    network, bits = cidr.rsplit("/", 1)
    try:
        prefix = int(bits)
    except ValueError:
        return network + " 255.255.255.0"
    mask_int = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    mask = ".".join(str((mask_int >> (8 * i)) & 0xFF) for i in range(3, -1, -1))
    return f"{network} {mask}"


def _subnet_gateway(cidr: str) -> str:
    """Return the .1 gateway address for a subnet: '10.25.10.0/24' → '10.25.10.1'."""
    network = cidr.split("/")[0]
    parts = network.rsplit(".", 1)
    return f"{parts[0]}.1"


def _generate_fortigate_cli(
    customer: dict,
    network: dict,
    services: dict,
    security: dict,
) -> str:
    """Generate FortiGate CLI commands following CIS benchmarks."""
    raw_name = customer.get("name", "FW")
    hostname = _sanitize_fortigate_name(raw_name).replace(" ", "-")[:35]

    # Number of physical ports on the FortiGate
    fg_ports = int(network.get("fg_ports", 10))
    # Last port = dedicated MGMT access (untagged, same subnet as VLAN99)
    mgmt_phys_port = f"port{fg_ports}"
    mgmt_subnet = None  # resolved later from VLAN99

    # FortiOS timezone IDs: 26 = Brussels/Copenhagen/Madrid/Paris (CET, Norway).
    # Override via services["fortigate_timezone_id"] if customer is in another TZ.
    tz_id = int(services.get("fortigate_timezone_id", 26))

    lines: list[str] = [
        "# FortiGate Configuration",
        f"# Customer: {raw_name}",
        f"# Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "#",
        f"# MGMT access port: {mgmt_phys_port} — plug laptop here, get IP via DHCP",
        f"# FortiGate admin: https://<mgmt-port-ip>:8443",
        "",
        "# ━━ SYSTEM HARDENING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "config system global",
        f"    set hostname \"{hostname}\"",
        f"    set timezone {tz_id}",
        "    set admin-sport 8443",
        "    set admintimeout 15",
        "    set admin-ssh-grace-time 60",
        "    set admin-ssh-v2 enable",
        "    set admin-scp enable",
        "    set strong-crypto enable",
        "    set auto-auth-extension-device disable",
        "    set usb-auto-install disable",
        "end",
        "",
        "# Pre-login banner (CIS)",
        "config system replacemsg admin pre_admin-disclaimer-text",
        "    set buffer \"ADVARSEL: Uautorisert tilgang er forbudt. All aktivitet logges og overvakes. Ved a fortsette aksepterer du vilkarene for bruk.\"",
        "end",
        "",
        "config system global",
        "    set pre-login-banner enable",
        "end",
        "",
    ]

    # Admin password
    if security.get("admin_password"):
        lines.extend([
            "config system admin",
            "    edit admin",
            "        set password \"********\"",  # actual password injected at deploy time
            "    next",
            "end",
            "",
        ])

    # Password policy (CIS)
    lines.extend([
        "config system password-policy",
        "    set status enable",
        "    set min-length 12",
        "    set min-upper-case-letter 1",
        "    set min-lower-case-letter 1",
        "    set min-number 1",
        "    set min-non-alphanumeric 1",
        "    set expire-status enable",
        "    set expire-day 90",
        "end",
        "",
    ])

    # NOTE: WAN interface is NOT configured here — changing WAN risks bricking
    # the device remotely.  WAN must be set up manually or via console.

    # LAN
    lan_subnet = network.get("lan_subnet", "192.168.1.0/24")
    lan_gw = _subnet_gateway(lan_subnet)
    lan_prefix = lan_subnet.split("/")[-1] if "/" in lan_subnet else "24"
    lan_mask_int = (0xFFFFFFFF << (32 - int(lan_prefix))) & 0xFFFFFFFF
    lan_mask = ".".join(str((lan_mask_int >> (8 * i)) & 0xFF) for i in range(3, -1, -1))

    lines.append("# LAN & VLAN Interfaces")
    lines.append("config system interface")
    lines.extend([
        "    edit port2",
        "        set alias LAN",
        "        set mode static",
        f"        set ip {lan_gw} {lan_mask}",
        "        set allowaccess ping https ssh",
        "    next",
    ])

    # VLANs — uniform interface config; admin access only via dedicated MGMT port.
    for vlan in network.get("vlans", []):
        vid = vlan.get("id", 10)
        vlan_subnet = vlan.get("subnet", "10.0.0.0/24")
        vlan_gw = _subnet_gateway(vlan_subnet)
        vlan_alias = _sanitize_fortigate_name(vlan.get("name", "VLAN"))
        lines.extend([
            f"    edit VLAN{vid}",
            "        set vdom root",
            "        set interface port2",
            f"        set vlanid {vid}",
            f"        set alias \"{vlan_alias}\"",
            "        set mode static",
            f"        set ip {vlan_gw} 255.255.255.0",
            "        set allowaccess ping",
            "    next",
        ])

    # Dedicated MGMT physical port — own /24, only path with admin access (HTTPS/SSH).
    # Default: derive from LAN by adding 100 to third octet (e.g. 10.25.0.0/24 → 10.25.100.0/24).
    # Override via network["mgmt_phys_subnet"].
    if network.get("mgmt_phys_subnet"):
        mgmt_phys_subnet = network["mgmt_phys_subnet"]
    else:
        lan_parts = lan_subnet.split("/")[0].split(".")
        mgmt_phys_subnet = f"{lan_parts[0]}.{lan_parts[1]}.{(int(lan_parts[2]) + 100) % 256}.0/24"
    mgmt_phys_gw = _subnet_gateway(mgmt_phys_subnet)
    mgmt_phys_net_prefix = mgmt_phys_subnet.split("/")[0].rsplit(".", 1)[0]
    lines.extend([
        f"    edit {mgmt_phys_port}",
        "        set alias MGMT-ACCESS",
        "        set mode static",
        f"        set ip {mgmt_phys_gw} 255.255.255.0",
        "        set allowaccess ping https ssh fgfm",
        f"        set description \"Local MGMT port — laptop access via DHCP, isolated /24\"",
        "    next",
    ])
    lines.extend(["end", ""])

    # ── DHCP servers ─────────────────────────────────────────────────────
    dhcp_enabled = services.get("dhcp_enabled", True)
    if dhcp_enabled:
        dhcp_id = 1
        lines.append("# DHCP Servers")

        # LAN DHCP
        lan_net_parts = lan_subnet.split("/")[0].rsplit(".", 1)
        lines.extend([
            "config system dhcp server",
            f"    edit {dhcp_id}",
            "        set interface port2",
            f"        set default-gateway {lan_gw}",
            f"        set netmask {lan_mask}",
            "        config ip-range",
            "            edit 1",
            f"                set start-ip {lan_net_parts[0]}.100",
            f"                set end-ip {lan_net_parts[0]}.250",
            "            next",
            "        end",
            f"        set dns-server1 {lan_gw}",
            "        set lease-time 86400",
            "    next",
        ])
        dhcp_id += 1

        # Per-VLAN DHCP — uniform 24h lease, range .100–.250
        for vlan in network.get("vlans", []):
            vid = vlan.get("id", 10)
            vlan_subnet = vlan.get("subnet", "10.0.0.0/24")
            vlan_gw = _subnet_gateway(vlan_subnet)
            vlan_net_parts = vlan_subnet.split("/")[0].rsplit(".", 1)
            lines.extend([
                f"    edit {dhcp_id}",
                f"        set interface VLAN{vid}",
                f"        set default-gateway {vlan_gw}",
                "        set netmask 255.255.255.0",
                "        config ip-range",
                "            edit 1",
                f"                set start-ip {vlan_net_parts[0]}.100",
                f"                set end-ip {vlan_net_parts[0]}.250",
                "            next",
                "        end",
                f"        set dns-server1 {vlan_gw}",
                "        set lease-time 86400",
                "    next",
            ])
            dhcp_id += 1

        # DHCP for the local MGMT port (port10) — short lease, small range.
        lines.extend([
            f"    edit {dhcp_id}",
            f"        set interface {mgmt_phys_port}",
            f"        set default-gateway {mgmt_phys_gw}",
            "        set netmask 255.255.255.0",
            "        config ip-range",
            "            edit 1",
            f"                set start-ip {mgmt_phys_net_prefix}.100",
            f"                set end-ip {mgmt_phys_net_prefix}.150",
            "            next",
            "        end",
            f"        set dns-server1 {mgmt_phys_gw}",
            "        set lease-time 3600",
            "    next",
        ])
        dhcp_id += 1

        lines.extend(["end", ""])

    # DNS (FortiGate as DNS forwarder for clients)
    dns = services.get("dns_servers", ["1.1.1.1", "1.0.0.1"])
    lines.extend([
        "# ━━ DNS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "config system dns",
        f"    set primary {dns[0] if dns else '1.1.1.1'}",
        f"    set secondary {dns[1] if len(dns) > 1 else '1.0.0.1'}",
        "    set dns-over-tls enforce",
        "end",
        "",
        "# DNS Database — FortiGate forwards DNS for all internal clients",
        "config system dns-database",
        f"    edit \"{hostname}\"",
        # ".local" is reserved for mDNS/Bonjour and breaks Apple/Linux discovery.
        # Use customer-provided domain, else "<hostname>.lan" (RFC-safe internal TLD).
        f"        set domain \"{customer.get('domain') or f'{hostname.lower()}.lan'}\"",
        "        set type master",
        "        set view shadow",
        "        set ttl 600",
        "        set authoritative enable",
        "    next",
        "end",
        "",
    ])

    # NTP — CIS requires ≥2 sources for redundancy
    ntp = services.get("ntp_servers", ["0.pool.ntp.org", "1.pool.ntp.org", "2.pool.ntp.org"])
    lines.extend([
        "config system ntp",
        "    set type custom",
    ])
    for i, server in enumerate(ntp[:3], 1):
        lines.extend([
            "    config ntpserver",
            f"        edit {i}",
            f"            set server \"{server}\"",
            "        next",
            "    end",
        ])
    lines.extend(["end", ""])

    # Logging (CIS benchmark)
    lines.extend([
        "# ━━ LOGGING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "config log setting",
        "    set fwpolicy-implicit-log enable",
        "    set local-in-allow enable",
        "    set local-in-deny-broadcast enable",
        "    set local-out enable",
        "end",
        "",
    ])

    # ── Session helpers — disable unnecessary ALGs (CIS) ────────────────
    lines.extend([
        "# ━━ HARDENING — SESSION HELPERS & FORTIGUARD ━━━━━━━━━━━━━━━━━━━━",
        "",
        "# Disable unnecessary session helpers / ALGs (CIS benchmark)",
        "config system session-helper",
        "    purge",
        "end",
        "",
        "# Session TTL — tighter than defaults",
        "config system session-ttl",
        "    set default 3600",
        "end",
        "",
        "# FortiGuard update schedule — keep AV/IPS definitions current",
        "config system autoupdate schedule",
        "    set status enable",
        "    set frequency every",
        "    set time \"03:00\"",
        "end",
        "",
        # Tunneling disabled by default — only enable if customer has a forwarding
        # proxy. With status=enable and no proxy configured, FortiGuard updates fail.
        "config system autoupdate tunneling",
        "    set status disable",
        "end",
        "",
    ])

    # ── Security profiles ────────────────────────────────────────────────
    lines.extend([
        "# Security Profiles — applied to all allow-policies",
        "# (uses built-in 'default' profiles; customise per customer as needed)",
        "",
    ])

    # Collect security profile lines reused across policies
    sec_profile_lines = [
        "        set utm-status enable",
        "        set av-profile default",
        "        set dnsfilter-profile default",
        "        set application-list default",
        "        set logtraffic all",
        "        set logtraffic-start enable",
    ]
    if security.get("web_filter", True):
        sec_profile_lines.append("        set webfilter-profile default")
    if security.get("ids_ips", True):
        sec_profile_lines.append("        set ips-sensor default")
    sec_profile_lines.append("        set ssl-ssh-profile certificate-inspection")

    # ── Address objects ──────────────────────────────────────────────────
    cust_prefix = _sanitize_fortigate_name(
        customer.get("name", "CUST")
    ).replace(" ", "-").upper()[:12]
    lines.append("# Address Objects")
    lines.append("config firewall address")
    lines.append(f"    edit \"{cust_prefix}_LAN\"")
    lines.append(f"        set subnet {_cidr_to_mask(lan_subnet)}")
    lines.append("    next")
    for vlan in network.get("vlans", []):
        vid = vlan.get("id", 10)
        vname = _sanitize_fortigate_name(
            vlan.get("name", f"VLAN{vid}")
        ).replace(" ", "-").upper()
        lines.append(f"    edit \"{cust_prefix}_{vname}\"")
        lines.append(f"        set subnet {_cidr_to_mask(vlan.get('subnet', '10.0.0.0/24'))}")
        lines.append("    next")
    lines.extend(["end", ""])

    # ── Firewall policies ────────────────────────────────────────────────
    vlans = network.get("vlans", [])
    policy_id = 1

    lines.append("# Firewall Policies")
    lines.append("config firewall policy")

    # Policy: LAN → WAN (full access + security profiles)
    lines.extend([
        f"    edit {policy_id}",
        f"        set name \"{cust_prefix}_LAN-to-WAN\"",
        "        set srcintf port2",
        "        set dstintf port1",
        f"        set srcaddr \"{cust_prefix}_LAN\"",
        "        set dstaddr all",
        "        set action accept",
        "        set schedule always",
        "        set service ALL",
        "        set nat enable",
        *sec_profile_lines,
        "    next",
    ])
    policy_id += 1

    # Per-VLAN → WAN policy — uniform: accept all, NAT, full UTM.
    # Tweak per-VLAN behaviour (web-only, no-UTM, etc.) in FortiGate GUI after generation.
    for vlan in vlans:
        vid = vlan.get("id", 10)
        vname = _sanitize_fortigate_name(
            vlan.get("name", f"VLAN{vid}")
        ).replace(" ", "-").upper()
        addr = f"{cust_prefix}_{vname}"
        lines.extend([
            f"    edit {policy_id}",
            f"        set name \"{cust_prefix}_{vname}-to-WAN\"",
            f"        set srcintf VLAN{vid}",
            "        set dstintf port1",
            f"        set srcaddr \"{addr}\"",
            "        set dstaddr all",
            "        set action accept",
            "        set schedule always",
            "        set service ALL",
            "        set nat enable",
            *sec_profile_lines,
            "    next",
        ])
        policy_id += 1

    # MGMT physical port → all internal + WAN (admin access for tech with laptop).
    # No UTM — clean path for management traffic.
    all_internal_dstintf = ["port2"] + [f"VLAN{v.get('id')}" for v in vlans] + ["port1"]
    lines.extend([
        f"    edit {policy_id}",
        f"        set name \"{cust_prefix}_MGMT-ACCESS-to-ALL\"",
        f"        set srcintf {mgmt_phys_port}",
        "        set dstintf " + " ".join(all_internal_dstintf),
        "        set srcaddr all",
        "        set dstaddr all",
        "        set action accept",
        "        set schedule always",
        "        set service ALL",
        "        set nat enable",
        "        set logtraffic all",
        f"        set comments \"Local MGMT port full access — tech laptop\"",
        "    next",
    ])
    policy_id += 1

    # MGMT-VLAN detection by name (mgmt/management — case-insensitive).
    # MGMT VLAN gets full access to all internal nets + WAN (no UTM).
    # All other VLANs get standard inter-VLAN deny.
    def _is_mgmt(v: dict) -> bool:
        n = (v.get("name", "") or "").lower()
        return "mgmt" in n or "management" in n

    mgmt_vlans = [v for v in vlans if _is_mgmt(v)]
    non_mgmt_vlans = [v for v in vlans if not _is_mgmt(v)]

    # Allow: MGMT VLAN → all internal + WAN (admin from MGMT-tagged network)
    for mv in mgmt_vlans:
        mv_id = mv.get("id", 99)
        mv_name = _sanitize_fortigate_name(mv.get("name", "MGMT")).replace(" ", "-").upper()
        mv_dst = ["port2"] + [f"VLAN{v.get('id')}" for v in vlans if v.get("id") != mv_id] + [mgmt_phys_port, "port1"]
        lines.extend([
            f"    edit {policy_id}",
            f"        set name \"{cust_prefix}_{mv_name}-to-ALL\"",
            f"        set srcintf VLAN{mv_id}",
            "        set dstintf " + " ".join(mv_dst),
            "        set srcaddr all",
            "        set dstaddr all",
            "        set action accept",
            "        set schedule always",
            "        set service ALL",
            "        set nat enable",
            "        set logtraffic all",
            f"        set comments \"MGMT VLAN full access til alt\"",
            "    next",
        ])
        policy_id += 1

    # Deny: every non-MGMT VLAN → LAN, all other VLANs, MGMT port (zero-trust)
    for src_vlan in non_mgmt_vlans:
        src_vid = src_vlan.get("id", 10)
        src_vname = _sanitize_fortigate_name(
            src_vlan.get("name", f"VLAN{src_vid}")
        ).replace(" ", "-").upper()
        deny_dst = ["port2", mgmt_phys_port] + [
            f"VLAN{v.get('id')}" for v in vlans if v.get("id") != src_vid
        ]
        lines.extend([
            f"    edit {policy_id}",
            f"        set name \"{cust_prefix}_{src_vname}-INTERNAL_DENY\"",
            f"        set srcintf VLAN{src_vid}",
            "        set dstintf " + " ".join(deny_dst),
            "        set srcaddr all",
            "        set dstaddr all",
            "        set action deny",
            "        set schedule always",
            "        set service ALL",
            "        set logtraffic all",
            f"        set comments \"Zero-trust: blokker all intern trafikk fra {src_vname}\"",
            "    next",
        ])
        policy_id += 1

    # LAN → all VLANs deny (admin tilgang går via MGMT-port eller MGMT-VLAN)
    if vlans:
        lines.extend([
            f"    edit {policy_id}",
            f"        set name \"{cust_prefix}_LAN-INTERNAL_DENY\"",
            "        set srcintf port2",
            "        set dstintf " + " ".join([f"VLAN{v.get('id')}" for v in vlans] + [mgmt_phys_port]),
            "        set srcaddr all",
            "        set dstaddr all",
            "        set action deny",
            "        set schedule always",
            "        set service ALL",
            "        set logtraffic all",
            f"        set comments \"Zero-trust: LAN kan ikke nå VLANs/MGMT — bruk port10 for admin\"",
            "    next",
        ])
        policy_id += 1

    lines.extend(["end", ""])

    # Syslog
    if services.get("syslog_server"):
        lines.extend([
            "config log syslogd setting",
            "    set status enable",
            f"    set server \"{services['syslog_server']}\"",
            "    set port 514",
            "end",
            "",
        ])

    return "\n".join(lines)


def _generate_unifi_json(
    customer: dict,
    network: dict,
    services: dict,
    security: dict,
) -> str:
    """Generate UniFi network configuration as JSON."""
    config: dict = {
        "site": {
            "name": customer.get("name", "Default"),
            "description": f"Provisioned {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        },
        "networks": [],
        "wlans": [],
    }

    # Default LAN
    config["networks"].append({
        "name": "Default",
        "purpose": "corporate",
        "subnet": network.get("lan_subnet", "192.168.1.0/24"),
        "dhcp_enabled": services.get("dhcp_enabled", True),
        "dhcp_start": network.get("dhcp_start", "192.168.1.100"),
        "dhcp_stop": network.get("dhcp_stop", "192.168.1.254"),
        "domain_name": customer.get("domain", "local"),
    })

    # VLANs
    for vlan in network.get("vlans", []):
        config["networks"].append({
            "name": vlan.get("name", f"VLAN{vlan.get('id')}"),
            "purpose": "corporate",
            "vlan_id": vlan.get("id"),
            "subnet": vlan.get("subnet", "10.0.0.0/24"),
            "dhcp_enabled": True,
        })

    return json.dumps(config, indent=2, ensure_ascii=False)


# ── AI-Assisted Generation ───────────────────────────────────────────────────


async def _generate_with_ai(
    customer: dict,
    network: dict,
    services: dict,
    security: dict,
    device_type: str,
) -> dict:
    """Use Claude to generate production-ready configs."""
    from app.services.claude_console import _get_api_key, is_available

    if not is_available():
        return _fallback_generate(customer, network, services, security, device_type)

    try:
        import anthropic
    except ImportError:
        return _fallback_generate(customer, network, services, security, device_type)

    api_key = _get_api_key()
    client = anthropic.Anthropic(api_key=api_key)

    context = json.dumps(
        {
            "customer": customer,
            "network": network,
            "services": services,
            "security": security,
            "device_type": device_type,
        },
        indent=2,
    )

    system_prompt = (
        "You are a network engineer generating production-ready device configs "
        "following CIS benchmarks. Output FortiGate configs as pure CLI commands "
        "(no markdown). Output UniFi configs as JSON. Use EXACT subnet values from "
        "input. Mark placeholders with CHANGE-ME. Include a deployment checklist at "
        "the end as comments."
    )

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Generate configs for:\n{context}"}],
    )

    content = message.content[0].text if message.content else ""
    result: dict = {}
    if device_type in ("fortigate", "both"):
        result["fortigate_cli"] = content
    if device_type in ("unifi", "both"):
        result["unifi_json"] = content
    return result


def _fallback_generate(
    customer: dict,
    network: dict,
    services: dict,
    security: dict,
    device_type: str,
) -> dict:
    """Template-based fallback when AI is unavailable."""
    result: dict = {}
    if device_type in ("fortigate", "both"):
        result["fortigate_cli"] = _generate_fortigate_cli(customer, network, services, security)
    if device_type in ("unifi", "both"):
        result["unifi_json"] = _generate_unifi_json(customer, network, services, security)
    return result


# ── Subnet Auto-Generation ──────────────────────────────────────────────────


def generate_subnets(customer_name: str) -> dict:
    """Generate deterministic subnets from customer name.

    Uses a hash of the name to pick a unique second octet (10.X.0.0/24).
    Returns LAN subnet + standard VLANs.
    """
    h = int(hashlib.sha256(customer_name.lower().encode()).hexdigest()[:4], 16)
    # Second octet 1-254 (avoid 0 and 255)
    octet2 = (h % 254) + 1

    return {
        "lan_subnet": f"10.{octet2}.0.0/24",
        "lan_gateway": f"10.{octet2}.0.1",
        "vlans": [
            {"name": "Servere", "id": 10, "subnet": f"10.{octet2}.10.0/24"},
            {"name": "Gjest", "id": 20, "subnet": f"10.{octet2}.20.0/24"},
            {"name": "IoT", "id": 30, "subnet": f"10.{octet2}.30.0/24"},
            {"name": "Management", "id": 99, "subnet": f"10.{octet2}.99.0/24"},
        ],
    }


# ── REST API Deployment ─────────────────────────────────────────────────────


async def _deploy_via_rest(
    host: str,
    api_token: str,
    steps: dict,
    conn: dict | None = None,
) -> dict:
    """Deploy full best-practice FortiGate config via REST API.

    Connection variables (host/port/vdom/verify_ssl) come from the resolved `conn`
    dict produced by `_resolve_fortigate_conn()`. If `conn` is None, falls back
    to resolving from `steps` (call-site convenience for older code paths).
    """
    from app.modules.fortigate_audit.client import FortiGateClient

    if conn is None:
        # Never silently resolve here: without the session's customer_id this
        # would fall back to the *active* customer's keyring and skip the
        # host-mismatch guard — the exact SR-001 #5 shape the caller closes.
        raise ValueError(
            "Intern feil: FortiGate-tilkobling ikke oppløst før REST-deploy."
        )

    customer = steps.get(1, {}) or {}
    network = steps.get(2, {}) or {}
    services = steps.get(3, {}) or {}
    security = steps.get(4, {}) or {}

    port = conn["port"]
    vdom = conn["vdom"]
    verify_ssl = conn["verify_ssl"]
    # FortiGate only allows A-Z a-z 0-9 - _ in names
    _NORDIC_MAP = str.maketrans("æøåÆØÅéèêëüöäÉÈÊËÜÖÄ", "aoaAOAeeeeuoaEEEEUOA")
    def _sanitize(s: str) -> str:
        s = s.translate(_NORDIC_MAP)
        return "".join(c if c.isalnum() or c in "-_" else "-" for c in s).strip("-")
    cust_prefix = _sanitize(customer.get("name") or conn.get("customer_name") or "FW")[:15].upper()

    results: list[dict] = []

    async with FortiGateClient(host, api_token, port=port, vdom=vdom, verify_ssl=verify_ssl) as fg:
        client = fg._client

        def _extract_error(r) -> str:
            try:
                body = r.json()
                if isinstance(body, dict):
                    msg = body.get("cli_error", body.get("error", ""))
                    if msg:
                        return str(msg)
            except Exception:
                pass
            return f"HTTP {r.status_code}"

        async def _put(path: str, payload: dict, label: str) -> None:
            try:
                r = await client.put(
                    f"/api/v2/cmdb/{path}", json=payload, params={"vdom": vdom},
                )
                if r.is_success:
                    results.append({"step": label, "ok": True})
                else:
                    results.append({"step": label, "ok": False, "error": _extract_error(r)})
            except Exception as e:
                results.append({"step": label, "ok": False, "error": str(e)})

        async def _post(path: str, payload: dict, label: str) -> None:
            """POST to create, fall back to PUT if object already exists.

            FortiGate returns 500 for duplicates with varying error text:
            - 'already exists' (interfaces, addresses)
            - 'already used by X' (policies)
            - error -651 with empty cli_error (VPN, users, groups)
            All 500s with a name → try PUT update as fallback.
            """
            obj_name = payload.get("name", "")
            try:
                r = await client.post(
                    f"/api/v2/cmdb/{path}", json=payload, params={"vdom": vdom},
                )
                if r.is_success:
                    results.append({"step": label, "ok": True})
                elif r.status_code == 500 and obj_name:
                    # Any 500 with a named object → assume duplicate, try PUT
                    import re
                    body_text = r.text.lower()
                    id_match = re.search(r"already used by \S+ '(\d+)'", body_text)
                    if id_match:
                        await _put(f"{path}/{id_match.group(1)}", payload, label)
                    else:
                        await _put(f"{path}/{obj_name}", payload, label)
                else:
                    results.append({"step": label, "ok": False, "error": _extract_error(r)})
            except Exception as e:
                results.append({"step": label, "ok": False, "error": str(e)})

        # ━━ PHASE 0: DISCOVER DEVICE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        wan_iface = "wan1"
        lan_iface = "internal"
        current_tz = None

        try:
            glob = await fg.get_cmdb("system/global")
            if isinstance(glob, list) and glob:
                glob = glob[0]
            if isinstance(glob, dict):
                current_tz = glob.get("timezone")
        except Exception:
            pass

        try:
            ifaces = await fg.get_cmdb("system/interface")
            if isinstance(ifaces, list):
                wan_candidates = []
                lan_candidates = []
                for iface in ifaces:
                    name = iface.get("name", "")
                    itype = iface.get("type", "")
                    role = (iface.get("role", "") or "").lower()
                    ip = iface.get("ip", "")
                    if role == "wan" and itype == "physical":
                        has_ip = ip and not ip.startswith("0.0.0.0")
                        wan_candidates.append((0 if has_ip else 1, name))
                    if role == "lan" and itype in ("hard-switch", "switch"):
                        lan_candidates.insert(0, name)
                    elif role == "lan" and itype == "physical":
                        lan_candidates.append(name)
                wan_candidates.sort()
                if wan_candidates:
                    wan_iface = wan_candidates[0][1]
                if lan_candidates:
                    lan_iface = lan_candidates[0]
                logger.info("Discovered: WAN=%s LAN=%s tz=%s", wan_iface, lan_iface, current_tz)
        except Exception as e:
            logger.warning("Interface discovery failed: %s", e)

        # ━━ PHASE 1: SYSTEM HARDENING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        hostname = _sanitize(customer.get("name", "FW"))[:35]
        global_cfg: dict = {
            "hostname": hostname,
            "admintimeout": 15,
            "admin-ssh-grace-time": 60,
            "admin-ssh-v2": "enable",
            "admin-scp": "enable",
            "admin-sport": 8443,
            "admin-maintainer": "disable",
            "post-login-banner": "enable",
            "pre-login-banner": "enable",
            "strong-crypto": "enable",
            "auto-auth-extension-device": "disable",
            "usb-auto-install": "disable",
        }
        if isinstance(current_tz, str):
            global_cfg["timezone"] = "Europe/Oslo"
        elif isinstance(current_tz, int):
            # FortiOS timezone 26 = Brussels/Copenhagen/Madrid/Paris (Norway)
            global_cfg["timezone"] = 26
        await _put("system/global", global_cfg, "System hardening")

        # Login banner (not supported on all firmware via REST — skip silently)
        # await _put("system/replacemsg/admin/pre_admin-disclaimer-text", ...)

        # Password policy (CIS 5.1)
        await _put("system/password-policy", {
            "status": "enable",
            "min-length": 14,
            "min-upper-case-letter": 1,
            "min-lower-case-letter": 1,
            "min-number": 1,
            "min-non-alphanumeric": 1,
            "expire-status": "enable",
            "expire-day": 90,
            "reuse-password": "disable",
        }, "Passordpolicy (CIS 5.1)")

        # ━━ PHASE 2: DNS / NTP ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        dns = services.get("dns_servers", ["1.1.1.1", "1.0.0.1"])
        await _put("system/dns", {
            "primary": dns[0] if dns else "1.1.1.1",
            "secondary": dns[1] if len(dns) > 1 else "1.0.0.1",
            "dns-over-tls": "enforce",
        }, "DNS (m/ DoT)")

        # NTP — CIS krever ≥2 kilder. Pad med pool-servere hvis færre gitt.
        ntp = services.get("ntp_servers") or []
        defaults = ["0.pool.ntp.org", "1.pool.ntp.org", "2.pool.ntp.org"]
        while len(ntp) < 3:
            for d in defaults:
                if d not in ntp:
                    ntp.append(d)
                if len(ntp) >= 3:
                    break
        await _put("system/ntp", {
            "type": "custom",
            "ntpserver": [{"id": i + 1, "server": s} for i, s in enumerate(ntp[:3])],
        }, "NTP (3 servere)")

        # ━━ PHASE 3: INTERFACES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        wan_type = network.get("wan_type", "dhcp")
        wan_cfg: dict = {
            "alias": f"{cust_prefix}-WAN",
            "allowaccess": "ping",
            "description": f"WAN uplink — {customer.get('name', '')}",
        }
        if wan_type == "dhcp":
            wan_cfg["mode"] = "dhcp"
        elif wan_type == "static":
            wan_cfg["mode"] = "static"
            if network.get("wan_ip"):
                wan_cfg["ip"] = network["wan_ip"]
        await _put(f"system/interface/{wan_iface}", wan_cfg, f"WAN ({wan_iface})")

        lan_subnet = network.get("lan_subnet", "192.168.1.0/24")
        lan_base = lan_subnet.split("/")[0].rsplit(".", 1)[0]
        lan_gw = f"{lan_base}.1"
        # NOTE: LAN IP change is deferred to the VERY LAST step
        # because changing LAN IP will disconnect our REST API session.
        # We prepare the config here but apply it at the end.
        _deferred_lan_cfg = {
            "alias": f"{cust_prefix}-LAN",
            "mode": "static",
            "ip": f"{lan_gw} 255.255.255.0",
            "allowaccess": "ping https ssh",
            "description": f"LAN — {lan_subnet}",
        }

        # VLANs
        vlans = network.get("vlans", [])
        vlan_iface_names: dict[int, str] = {}
        for vlan in vlans:
            vid = vlan.get("id", 10)
            vname = vlan.get("name", f"VLAN{vid}")
            iface_name = f"V{vid:03d}_{vname.replace(' ', '-')[:12].upper()}"
            vlan_iface_names[vid] = iface_name
            vlan_subnet = vlan.get("subnet", "10.0.0.0/24")
            vlan_base = vlan_subnet.split("/")[0].rsplit(".", 1)[0]
            vlan_gw = f"{vlan_base}.1"
            await _post("system/interface", {
                "name": iface_name,
                "vdom": "root",
                "type": "vlan",
                "interface": lan_iface,
                "vlanid": vid,
                "alias": f"{cust_prefix}-{vname.upper()}",
                "mode": "static",
                "ip": f"{vlan_gw} 255.255.255.0",
                "allowaccess": "ping",
                "description": f"VLAN {vid} — {vname} — {vlan_subnet}",
            }, f"VLAN {vid} ({vname})")

        # ━━ PHASE 4: ADDRESS OBJECTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Named address per subnet — never use raw IPs in policies
        addr_lan = f"NET_{cust_prefix}_LAN"
        await _post("firewall/address", {
            "name": addr_lan,
            "subnet": f"{lan_base}.0 255.255.255.0",
            "comment": f"LAN subnet {lan_subnet}",
        }, f"Adresseobjekt {addr_lan}")

        vlan_addr_names: dict[int, str] = {}
        for vlan in vlans:
            vid = vlan.get("id", 10)
            vname = vlan.get("name", f"VLAN{vid}")
            vlan_subnet = vlan.get("subnet", "10.0.0.0/24")
            vlan_base_v = vlan_subnet.split("/")[0].rsplit(".", 1)[0]
            addr_name = f"NET_{cust_prefix}_{vname.replace(' ', '-').upper()}"
            vlan_addr_names[vid] = addr_name
            await _post("firewall/address", {
                "name": addr_name,
                "subnet": f"{vlan_base_v}.0 255.255.255.0",
                "comment": f"VLAN {vid} — {vname} — {vlan_subnet}",
            }, f"Adresseobjekt {addr_name}")

        # Address group: all internal nets
        all_internal = f"GRP_{cust_prefix}_ALL-INTERNAL"
        members = [{"name": addr_lan}] + [{"name": v} for v in vlan_addr_names.values()]
        await _post("firewall/addrgrp", {
            "name": all_internal,
            "member": members,
            "comment": f"Alle interne nett — {customer.get('name', '')}",
        }, f"Adressegruppe {all_internal}")

        # ━━ PHASE 5: DHCP SERVERS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Resolve UniFi controller hostname → Option 43 hex (sub-option 1, len 4, IP).
        # Format: 01 04 <IPv4 bytes>. Example: 70.34.194.40 → 01044622c228
        unifi_host = services.get("unifi_controller_host") or "unifi.sybr.no"
        unifi_opt43_hex = ""
        try:
            import socket
            unifi_ip = socket.gethostbyname(unifi_host)
            octets = [int(o) for o in unifi_ip.split(".")]
            unifi_opt43_hex = "0104" + "".join(f"{o:02x}" for o in octets)
            logger.info("DHCP Option 43: %s → %s → %s", unifi_host, unifi_ip, unifi_opt43_hex)
        except Exception as e:
            logger.warning("Failed to resolve UniFi controller host %s for Option 43: %s", unifi_host, e)

        async def _create_or_update_dhcp(iface: str, gw: str, base: str, label: str) -> None:
            """Create DHCP server or update existing one for interface.

            dns-server1 = gateway (FortiGate forwards DNS for internal clients).
            Option 43 points UniFi devices at the controller via inform-URL.
            """
            dhcp_cfg: dict = {
                "status": "enable",
                "interface": iface,
                "default-gateway": gw,
                "netmask": "255.255.255.0",
                "dns-service": "specify",
                "dns-server1": gw,
                "ip-range": [{"start-ip": f"{base}.100", "end-ip": f"{base}.250"}],
                "lease-time": 86400,
            }
            if unifi_opt43_hex:
                dhcp_cfg["options"] = [{
                    "id": 1, "code": 43, "type": "hex", "value": unifi_opt43_hex,
                }]
            # Check if a DHCP server already exists for this interface
            try:
                existing = await fg.get_cmdb("system.dhcp/server")
                if isinstance(existing, list):
                    for srv in existing:
                        srv_iface = srv.get("interface", "")
                        if isinstance(srv_iface, dict):
                            srv_iface = srv_iface.get("name", "")
                        if srv_iface == iface:
                            await _put(f"system.dhcp/server/{srv['id']}", dhcp_cfg, label)
                            return
            except Exception:
                pass
            # No existing — create new
            try:
                r = await client.post(
                    "/api/v2/cmdb/system.dhcp/server",
                    json=dhcp_cfg, params={"vdom": vdom},
                )
                if r.is_success:
                    results.append({"step": label, "ok": True})
                else:
                    results.append({"step": label, "ok": False, "error": _extract_error(r)})
            except Exception as e:
                results.append({"step": label, "ok": False, "error": str(e)})

        # LAN DHCP
        await _create_or_update_dhcp(lan_iface, lan_gw, lan_base, f"DHCP server LAN ({lan_iface})")

        # VLAN DHCPs
        for vlan in vlans:
            vid = vlan.get("id", 10)
            vname = vlan.get("name", f"VLAN{vid}")
            iface_name = vlan_iface_names.get(vid, f"VLAN{vid}")
            vlan_subnet = vlan.get("subnet", "10.0.0.0/24")
            vlan_base_v = vlan_subnet.split("/")[0].rsplit(".", 1)[0]
            vlan_gw = f"{vlan_base_v}.1"
            await _create_or_update_dhcp(iface_name, vlan_gw, vlan_base_v, f"DHCP server VLAN {vid} ({vname})")

        # ━━ PHASE 5b: DEDICATED LOCAL MGMT PORT ━━━━━━━━━━━━━━━━━━━━━━━
        # Pick the last physical/switch-member port (not WAN) as dedicated MGMT.
        # On 60F this is typically internal5 (member of the 'internal' hard-switch).
        # On other models it could be port10, port7 etc. If it's a hard-switch
        # member, we remove it from the switch before configuring standalone.
        mgmt_phys_port = ""
        mgmt_phys_subnet = network.get("mgmt_phys_subnet") or ""
        if not mgmt_phys_subnet:
            lan_parts = lan_subnet.split("/")[0].split(".")
            mgmt_phys_subnet = f"{lan_parts[0]}.{lan_parts[1]}.{(int(lan_parts[2]) + 100) % 256}.0/24"
        mgmt_phys_base = mgmt_phys_subnet.split("/")[0].rsplit(".", 1)[0]
        mgmt_phys_gw = f"{mgmt_phys_base}.1"

        try:
            all_ifaces = await fg.get_cmdb("system/interface") or []
            # Candidates: physical ports NOT currently wan/lan/dmz/modem/fortilink/mgmt
            reserved = {wan_iface, lan_iface, "dmz", "modem", "fortilink", "mgmt"}
            phys_candidates = []
            for i in all_ifaces:
                name = i.get("name", "")
                itype = i.get("type", "")
                if itype != "physical" or name in reserved or name.startswith("wan"):
                    continue
                phys_candidates.append(name)
            # Prefer internal-member ports sorted descending (pick highest number)
            phys_candidates.sort(key=lambda n: (not n.startswith("internal"), n), reverse=True)
            if phys_candidates:
                mgmt_phys_port = phys_candidates[0]
                logger.info("MGMT physical port selected: %s (candidates=%s)", mgmt_phys_port, phys_candidates)
        except Exception as e:
            logger.warning("MGMT port detection failed: %s", e)

        if mgmt_phys_port:
            # If it's a member of the 'internal' hard-switch, remove it first.
            try:
                vsw = await fg.get_cmdb(f"system/virtual-switch/{lan_iface}")
                if isinstance(vsw, list) and vsw:
                    vsw = vsw[0]
                if isinstance(vsw, dict):
                    members = [p.get("name") or p.get("interface-name") for p in vsw.get("port", [])]
                    if mgmt_phys_port in members:
                        new_members = [{"name": m} for m in members if m != mgmt_phys_port]
                        await _put(
                            f"system/virtual-switch/{lan_iface}",
                            {"port": new_members},
                            f"Fjern {mgmt_phys_port} fra hard-switch {lan_iface}",
                        )
            except Exception as e:
                logger.warning("hard-switch member removal skipped: %s", e)

            # Configure MGMT port standalone
            await _put(f"system/interface/{mgmt_phys_port}", {
                "alias": "MGMT-ACCESS",
                "mode": "static",
                "ip": f"{mgmt_phys_gw} 255.255.255.0",
                "allowaccess": "ping https ssh fgfm",
                "description": "Local MGMT port — laptop access via DHCP",
            }, f"MGMT port ({mgmt_phys_port}) {mgmt_phys_gw}/24")

            # DHCP for MGMT port — short lease, dedicated small range
            await _create_or_update_dhcp(
                mgmt_phys_port, mgmt_phys_gw, mgmt_phys_base,
                f"DHCP server MGMT port ({mgmt_phys_port})",
            )

        # ━━ PHASE 6: LOGGING (CIS 2.1) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        await _put("log/setting", {
            "fwpolicy-implicit-log": "enable",
            "local-in-allow": "enable",
            "local-in-deny-broadcast": "enable",
            "local-out": "enable",
        }, "Logging (CIS 2.1)")

        if services.get("syslog_server"):
            await _put("log.syslogd/setting", {
                "status": "enable",
                "server": services["syslog_server"],
                "port": 514,
            }, "Syslog")

        # ━━ PHASE 7: FIREWALL POLICIES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Security profiles on all allow-policies.
        # CRITICAL: utm-status must be "enable" or FortiGate ignores all the
        # profile assignments — silently. CIS-baseline stack: AV + IPS + webfilter
        # + DNS-filter + app-list, with certificate-inspection SSL profile.
        sec_profiles: dict = {
            "utm-status": "enable",
            "logtraffic": "all",
            "logtraffic-start": "enable",
            "av-profile": "default",
            "dnsfilter-profile": "default",
            "application-list": "default",
            "ssl-ssh-profile": "certificate-inspection",
        }
        if security.get("web_filter", True):
            sec_profiles["webfilter-profile"] = "default"
        if security.get("ids_ips", True):
            sec_profiles["ips-sensor"] = "default"

        # MGMT policy profile set — no UTM, no SSL inspection. UniFi inform/STUN
        # and similar L3-discovery traffic breaks under UTM/SSL-inspection.
        mgmt_profiles: dict = {
            "utm-status": "disable",
            "logtraffic": "all",
            "ssl-ssh-profile": "no-inspection",
        }

        # Policy 1: LAN → WAN (full access + security profiles)
        await _post("firewall/policy", {
            "name": f"{cust_prefix}_LAN-to-WAN_ALLOW",
            "srcintf": [{"name": lan_iface}],
            "dstintf": [{"name": wan_iface}],
            "srcaddr": [{"name": addr_lan}],
            "dstaddr": [{"name": "all"}],
            "action": "accept",
            "schedule": "always",
            "service": [{"name": "ALL"}],
            "nat": "enable",
            **sec_profiles,
        }, f"Policy: {cust_prefix} LAN→WAN")

        # MGMT VLAN detection by name (mgmt/management — case-insensitive).
        # Moved UP so we can skip MGMT in the per-VLAN-to-WAN loop.
        def _is_mgmt(v: dict) -> bool:
            n = (v.get("name", "") or "").lower()
            return "mgmt" in n or "management" in n

        mgmt_vlans = [v for v in vlans if _is_mgmt(v)]
        non_mgmt_vlans = [v for v in vlans if not _is_mgmt(v)]

        # Per-non-MGMT-VLAN → WAN policy with full UTM.
        for vlan in non_mgmt_vlans:
            vid = vlan.get("id", 10)
            vname = vlan.get("name", f"VLAN{vid}").replace(" ", "-").upper()
            iface_name = vlan_iface_names.get(vid, f"VLAN{vid}")
            addr_name = vlan_addr_names.get(vid, "all")
            await _post("firewall/policy", {
                "name": f"{cust_prefix}_{vname}-to-WAN",
                "srcintf": [{"name": iface_name}],
                "dstintf": [{"name": wan_iface}],
                "srcaddr": [{"name": addr_name}],
                "dstaddr": [{"name": "all"}],
                "action": "accept",
                "schedule": "always",
                "service": [{"name": "ALL"}],
                "nat": "enable",
                **sec_profiles,
            }, f"Policy: {vname}→WAN")

        # Allow: MGMT VLAN → all internal + WAN. NO UTM — UniFi inform/STUN
        # and similar cloud broker traffic breaks under UTM/SSL-inspection.
        for mv in mgmt_vlans:
            mv_id = mv.get("id", 99)
            mv_name = mv.get("name", "MGMT").replace(" ", "-").upper()
            mv_iface = vlan_iface_names.get(mv_id)
            mv_addr = vlan_addr_names.get(mv_id)
            if not mv_iface or not mv_addr:
                continue
            mv_dst_ifaces = [{"name": lan_iface}, {"name": wan_iface}] + [
                {"name": vlan_iface_names[v.get("id")]}
                for v in vlans
                if v.get("id") != mv_id and v.get("id") in vlan_iface_names
            ]
            await _post("firewall/policy", {
                "name": f"{cust_prefix}_{mv_name}-to-ALL",
                "srcintf": [{"name": mv_iface}],
                "dstintf": mv_dst_ifaces,
                "srcaddr": [{"name": mv_addr}],
                "dstaddr": [{"name": "all"}],
                "action": "accept",
                "schedule": "always",
                "service": [{"name": "ALL"}],
                "nat": "enable",
                "comments": "MGMT VLAN full access (ingen UTM — UniFi-vennlig sti)",
                **mgmt_profiles,
            }, f"Policy: {mv_name}→ALL (MGMT)")

        # Local MGMT port (dedicated physical) — full access, no UTM.
        if mgmt_phys_port:
            mgmt_port_dst = [{"name": lan_iface}, {"name": wan_iface}] + [
                {"name": vlan_iface_names[v.get("id")]}
                for v in vlans if v.get("id") in vlan_iface_names
            ]
            await _post("firewall/policy", {
                "name": f"{cust_prefix}_MGMT-PORT-to-ALL",
                "srcintf": [{"name": mgmt_phys_port}],
                "dstintf": mgmt_port_dst,
                "srcaddr": [{"name": "all"}],
                "dstaddr": [{"name": "all"}],
                "action": "accept",
                "schedule": "always",
                "service": [{"name": "ALL"}],
                "nat": "enable",
                "comments": f"Lokal MGMT-port ({mgmt_phys_port}) — tech-laptop full tilgang",
                **mgmt_profiles,
            }, f"Policy: MGMT-PORT ({mgmt_phys_port})→ALL")

        # Deny: each non-MGMT VLAN → LAN + all other VLANs
        for src_vlan in non_mgmt_vlans:
            src_vid = src_vlan.get("id", 10)
            src_vname = src_vlan.get("name", f"VLAN{src_vid}").replace(" ", "-").upper()
            src_iface = vlan_iface_names.get(src_vid)
            src_addr = vlan_addr_names.get(src_vid)
            if not src_iface or not src_addr:
                continue
            deny_dst_ifaces = [{"name": lan_iface}] + [
                {"name": vlan_iface_names[v.get("id")]}
                for v in vlans
                if v.get("id") != src_vid and v.get("id") in vlan_iface_names
            ]
            if not deny_dst_ifaces:
                continue
            await _post("firewall/policy", {
                "name": f"{cust_prefix}_{src_vname}-INTERNAL_DENY",
                "srcintf": [{"name": src_iface}],
                "dstintf": deny_dst_ifaces,
                "srcaddr": [{"name": src_addr}],
                "dstaddr": [{"name": "all"}],
                "action": "deny",
                "schedule": "always",
                "service": [{"name": "ALL"}],
                "logtraffic": "all",
                "comments": f"Zero-trust: blokker all intern trafikk fra {src_vname}",
            }, f"Policy: {src_vname}→INTERNAL DENY")

        # LAN → non-MGMT VLANs deny (admin via MGMT VLAN/port)
        if non_mgmt_vlans:
            lan_deny_dst = [
                {"name": vlan_iface_names[v.get("id")]}
                for v in non_mgmt_vlans if v.get("id") in vlan_iface_names
            ]
            if lan_deny_dst:
                await _post("firewall/policy", {
                    "name": f"{cust_prefix}_LAN-INTERNAL_DENY",
                    "srcintf": [{"name": lan_iface}],
                    "dstintf": lan_deny_dst,
                    "srcaddr": [{"name": addr_lan}],
                    "dstaddr": [{"name": "all"}],
                    "action": "deny",
                    "schedule": "always",
                    "service": [{"name": "ALL"}],
                    "logtraffic": "all",
                    "comments": "Zero-trust: LAN kan ikke nå VLANs (admin via MGMT)",
                }, "Policy: LAN→VLANs DENY")

        # ━━ PHASE 9: IPSEC VPN — SYBR_ADMIN ━━━━━━━━━━━━━━━━━━━━━━━━━━
        # IKEv2 dial-up IPsec VPN with mode-cfg for remote admin access
        def _gen_password(length: int = 24) -> str:
            alphabet = string.ascii_letters + string.digits + "!@#%^&*"
            return "".join(secrets.choice(alphabet) for _ in range(length))

        vpn_psk = _gen_password(32)
        vpn_user_pw = _gen_password(20)
        # FortiOS interface names max 15 chars — keep VPN name short
        vpn_name = f"{cust_prefix[:8]}_VPN"
        vpn_user = "sybr_admin"
        vpn_group = f"{cust_prefix}_VPN-ADMINS"
        # VPN tunnel IP pool — .240-.254 of LAN subnet by default.
        # Override via network["vpn_pool_subnet"] to use a dedicated /24.
        vpn_subnet = network.get("vpn_pool_subnet", "")
        vpn_base = vpn_subnet.split("/")[0].rsplit(".", 1)[0] if vpn_subnet else lan_base
        vpn_start = f"{vpn_base}.240"
        vpn_end = f"{vpn_base}.254"

        # Local user
        await _post("user/local", {
            "name": vpn_user,
            "type": "password",
            "passwd": vpn_user_pw,
            "status": "enable",
            "two-factor": "disable",
        }, f"VPN bruker: {vpn_user}")

        # User group
        await _post("user/group", {
            "name": vpn_group,
            "group-type": "firewall",
            "member": [{"name": vpn_user}],
        }, f"VPN gruppe: {vpn_group}")

        # Address object for VPN pool
        vpn_pool_addr = f"NET_{cust_prefix}_VPN-POOL"
        await _post("firewall/address", {
            "name": vpn_pool_addr,
            "type": "iprange",
            "start-ip": vpn_start,
            "end-ip": vpn_end,
            "comment": f"IPsec VPN client-pool for {vpn_name}",
        }, f"Adresseobjekt {vpn_pool_addr}")

        # Split-tunnel address group (all internal nets)
        vpn_split_addr = f"GRP_{cust_prefix}_VPN-SPLIT"
        split_members = [{"name": addr_lan}] + [{"name": v} for v in vlan_addr_names.values()]
        await _post("firewall/addrgrp", {
            "name": vpn_split_addr,
            "member": split_members,
            "comment": f"Split-tunnel: alle interne nett for VPN-klienter",
        }, f"VPN split-tunnel adressegruppe")

        # Phase 1 — IKEv2, AES256-SHA256, DH group 14+20
        await _post("vpn.ipsec/phase1-interface", {
            "name": vpn_name,
            "type": "dynamic",
            "interface": wan_iface,
            "ike-version": "2",
            "peertype": "any",
            "mode-cfg": "enable",
            "proposal": "aes256-sha256",
            "dhgrp": "14 20",
            "psksecret": vpn_psk,
            "dpd": "on-idle",
            "dpd-retryinterval": 10,
            "ipv4-start-ip": vpn_start,
            "ipv4-end-ip": vpn_end,
            "ipv4-netmask": "255.255.255.0",
            "dns-mode": "auto",
            "ipv4-split-include": vpn_split_addr,
            "save-password": "enable",
            "net-device": "disable",
            "comments": f"SYBR admin VPN — {customer.get('name', '')}",
        }, f"IPsec Phase 1: {vpn_name}")

        # Phase 2 — AES256-SHA256, PFS DH14
        await _post("vpn.ipsec/phase2-interface", {
            "name": f"{vpn_name}_P2",
            "phase1name": vpn_name,
            "proposal": "aes256-sha256",
            "dhgrp": "14 20",
            "auto-negotiate": "enable",
            "comments": f"Phase 2 for {vpn_name}",
        }, f"IPsec Phase 2: {vpn_name}_P2")

        # Allow IKE/ESP on WAN interface
        wan_current = {}
        try:
            wan_data = await fg.get_cmdb(f"system/interface/{wan_iface}")
            if isinstance(wan_data, list) and wan_data:
                wan_current = wan_data[0]
            elif isinstance(wan_data, dict):
                wan_current = wan_data
        except Exception:
            pass
        current_access = wan_current.get("allowaccess", "ping")
        if isinstance(current_access, str) and "ike" not in current_access.lower():
            # Not available via allowaccess on all models — skip if already set
            pass

        # Firewall policy: VPN → all internal nets
        all_dst_ifaces = [{"name": lan_iface}] + [{"name": n} for n in vlan_iface_names.values()]
        await _post("firewall/policy", {
            "name": f"{cust_prefix}_VPN-to-ALL_ADMIN",
            "srcintf": [{"name": vpn_name}],
            "dstintf": all_dst_ifaces,
            "srcaddr": [{"name": vpn_pool_addr}],
            "dstaddr": [{"name": all_internal}],
            "action": "accept",
            "schedule": "always",
            "service": [{"name": "ALL"}],
            "groups": [{"name": vpn_group}],
            "logtraffic": "all",
            "logtraffic-start": "enable",
            "comments": f"SYBR admin full tilgang via IPsec VPN",
        }, f"Policy: VPN→Alle nett (admin)")

        # Firewall policy: VPN → WAN (internet via tunnel)
        await _post("firewall/policy", {
            "name": f"{cust_prefix}_VPN-to-WAN_NAT",
            "srcintf": [{"name": vpn_name}],
            "dstintf": [{"name": wan_iface}],
            "srcaddr": [{"name": vpn_pool_addr}],
            "dstaddr": [{"name": "all"}],
            "action": "accept",
            "schedule": "always",
            "service": [{"name": "ALL"}],
            "nat": "enable",
            "groups": [{"name": vpn_group}],
            "logtraffic": "all",
            **sec_profiles,
        }, f"Policy: VPN→WAN (internett)")

        # ━━ FINAL STEP: LAN IP CHANGE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Detect if LAN IP is actually changing
        lan_ip_changed = False
        try:
            cur_lan = await fg.get_cmdb(f"system/interface/{lan_iface}")
            if isinstance(cur_lan, list) and cur_lan:
                cur_lan = cur_lan[0]
            cur_ip = (cur_lan.get("ip", "") if isinstance(cur_lan, dict) else "").split()[0]
            if cur_ip != lan_gw:
                lan_ip_changed = True
        except Exception:
            lan_ip_changed = True

        old_ip = host
        # This MUST be the very last API call — changing the LAN IP
        # will disconnect our session if we're connected via this subnet.
        await _put(f"system/interface/{lan_iface}", _deferred_lan_cfg,
                   f"LAN IP-endring ({lan_iface} → {lan_gw}) ⚠ SISTE STEG")

        # Update customer config with new FortiGate connection info.
        # Bootstrap moved admin GUI to 8443; LAN IP now = gateway. Persist both.
        try:
            from app.core.customer import CustomerManager
            active = CustomerManager.get_active()
            if active:
                if lan_ip_changed:
                    active["FortiGateHost"] = lan_gw
                active["FortiGatePort"] = 8443
                active["FortiGateVDOM"] = active.get("FortiGateVDOM") or "root"
                active["FortiGateVerifySSL"] = active.get("FortiGateVerifySSL", False)
                save_data = {k: v for k, v in active.items() if not k.startswith("_")}
                CustomerManager.save_customer(save_data)
                logger.info("Updated customer config: FortiGateHost=%s FortiGatePort=8443",
                            active.get("FortiGateHost"))
        except Exception as e:
            logger.warning("Could not update customer FortiGate config: %s", e)

        # ━━ BUILD CONFIG SUMMARY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        config_summary = {
            "customer": customer.get("name", ""),
            "fortigate_host": host,
            "fortigate_port": port,
            "hostname": hostname,
            "wan_interface": wan_iface,
            "wan_mode": wan_type,
            "lan_interface": lan_iface,
            "lan_subnet": lan_subnet,
            "lan_gateway": lan_gw,
            "dns": dns,
            "ntp": ntp,
            "vlans": [
                {
                    "id": v.get("id"),
                    "name": v.get("name"),
                    "interface": vlan_iface_names.get(v.get("id"), ""),
                    "subnet": v.get("subnet"),
                    "gateway": v.get("subnet", "").split("/")[0].rsplit(".", 1)[0] + ".1",
                    "dhcp_range": f".100–.250",
                    "address_object": vlan_addr_names.get(v.get("id"), ""),
                }
                for v in vlans
            ],
            "vpn": {
                "name": vpn_name,
                "type": "IKEv2 IPsec",
                "wan_interface": wan_iface,
                "proposal": "AES256-SHA256",
                "dh_group": "14, 20",
                "psk": vpn_psk,
                "tunnel_pool": f"{vpn_start}–{vpn_end}",
                "split_tunnel": vpn_split_addr,
                "user": vpn_user,
                "user_password": vpn_user_pw,
                "user_group": vpn_group,
            },
            "security_profiles": {
                "antivirus": "default",
                "webfilter": "default" if security.get("web_filter", True) else "none",
                "ips": "default" if security.get("ids_ips", True) else "none",
                "dns_filter": "default",
                "app_control": "default",
                "ssl_inspection": "certificate-inspection",
            },
            "hardening": {
                "password_policy": "14 chars, complexity, 90-day expiry",
                "admin_timeout": "15 min",
                "strong_crypto": "enabled",
                "login_banner": "enabled",
                "implicit_deny_log": "enabled",
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    ok_count = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - ok_count
    return {
        "ok": fail_count == 0,
        "total": len(results),
        "success": ok_count,
        "failed": fail_count,
        "details": results,
        "config_summary": config_summary,
        "lan_ip_changed": lan_ip_changed,
        "old_ip": old_ip,
        "new_ip": lan_gw,
    }
