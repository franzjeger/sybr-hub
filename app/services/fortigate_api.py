"""Enhanced FortiGate API service.

Extends the base FortiGateClient with dashboard aggregation, encrypted config
backup/diff, SSH key deployment, API token generation via SSH, CIS compliance
checking, and multi-device fleet polling.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import get_audit_dir
from app.core.encryption import encrypted_read_text, encrypted_write_text
from app.core.validation import (
    validate_cidr_list,
    validate_identifier,
    validate_ssh_public_key,
)
from app.modules.fortigate_audit.client import FortiGateClient

log = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _backup_dir(customer_id: str) -> Path:
    """Return the directory for FortiGate config backups for a customer."""
    d = get_audit_dir() / customer_id / "fortigate_backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _build_client(config: dict, token: str) -> FortiGateClient:
    """Build a FortiGateClient from a customer config dict + token."""
    return FortiGateClient(
        host=config.get("FortiGateHost", ""),
        api_token=token,
        port=int(config.get("FortiGatePort", 443)),
        vdom=config.get("FortiGateVDOM", "root"),
        verify_ssl=config.get("FortiGateVerifySSL", True),
    )


# ── 1. Dashboard data ───────────────────────────────────────────────────────

async def get_dashboard(config: dict, token: str) -> dict:
    """Fetch a consolidated dashboard snapshot from the FortiGate.

    Returns hostname, firmware, model, serial, uptime, CPU%, memory%,
    WAN IP, active sessions, VPN tunnel count, and HA mode.
    """
    async with _build_client(config, token) as fg:
        status = await fg.get_monitor("system/status")
        perf = await fg.get_monitor("system/performance/status")
        iface = await fg.get_monitor("system/interface")
        vpn = await fg.get_monitor("vpn/ipsec")
        ha = await fg.get_monitor("system/ha/status")

        # Extract WAN IP from interface list (look for wan1 or first non-loopback)
        wan_ip = ""
        if isinstance(iface, list):
            for ifc in iface:
                name = ifc.get("name", "")
                if name.lower() in ("wan1", "wan", "port1"):
                    wan_ip = ifc.get("ip", "")
                    break
        elif isinstance(iface, dict):
            for name, detail in iface.items():
                if name.lower() in ("wan1", "wan", "port1"):
                    wan_ip = detail.get("ip", "") if isinstance(detail, dict) else ""
                    break

        # VPN tunnel count
        vpn_count = 0
        if isinstance(vpn, list):
            vpn_count = len(vpn)
        elif isinstance(vpn, dict):
            vpn_count = len(vpn.get("tunnel", vpn.get("results", [])))

        # CPU and memory from performance status
        cpu = perf.get("cpu", perf.get("cpu-usage", 0)) if isinstance(perf, dict) else 0
        mem = perf.get("memory", perf.get("mem-usage", 0)) if isinstance(perf, dict) else 0
        sessions = perf.get("session", {}).get("total", 0) if isinstance(perf, dict) else 0

        # HA mode
        ha_mode = "standalone"
        if isinstance(ha, dict):
            ha_mode = ha.get("mode", ha.get("ha-mode", "standalone"))

        return {
            "hostname": status.get("hostname", ""),
            "firmware": status.get("version", ""),
            "model": status.get("model", status.get("model-name", "")),
            "serial": status.get("serial", ""),
            "uptime": status.get("uptime", ""),
            "cpu_percent": cpu,
            "memory_percent": mem,
            "wan_ip": wan_ip,
            "active_sessions": sessions,
            "vpn_tunnels": vpn_count,
            "ha_mode": ha_mode,
        }


# ── 2. Config backup ────────────────────────────────────────────────────────

async def backup_config(config: dict, token: str, customer_id: str) -> dict:
    """Download full FortiGate config via REST API and store encrypted.

    Returns {"ok": True, "filename": "...", "size": N} on success.
    FortiOS 7.6+ requires POST for config backup; older uses GET.
    """
    async with _build_client(config, token) as fg:
        # Try POST first (FortiOS 7.6+), fall back to GET (older firmware)
        try:
            path = "/api/v2/monitor/system/config/backup"
            r = await fg._client.post(path, params={"scope": "global"})
            if r.status_code == 405:
                r = await fg._client.get(path, params={"scope": "global"})
            try:
                data = r.json()
            except Exception:
                data = r.text
        except Exception as e:
            return {"ok": False, "error": str(e)}

        # The backup endpoint may return raw text or JSON-wrapped text
        if isinstance(data, dict) and "error" in data:
            return {"ok": False, "error": data["error"]}

        # Some firmware versions return the config as raw text
        # httpx may have already decoded it; handle both cases
        if isinstance(data, dict):
            config_text = data.get("results", data.get("config", ""))
            if isinstance(config_text, dict):
                import json
                config_text = json.dumps(config_text, indent=2)
        else:
            config_text = str(data)

    if not config_text:
        return {"ok": False, "error": "Empty config received from FortiGate"}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    hostname = config.get("FortiGateHost", "fortigate").replace(".", "_")
    filename = f"fg_backup_{hostname}_{ts}.conf"
    dest = _backup_dir(customer_id) / filename

    encrypted_write_text(dest, config_text)
    log.info("FortiGate config backed up: %s (%d bytes)", dest, len(config_text))

    return {"ok": True, "filename": filename, "size": len(config_text)}


async def list_backups(customer_id: str) -> list[dict]:
    """List all encrypted backup files for a customer.

    Returns sorted list of {"filename", "size", "modified"} dicts.
    """
    d = _backup_dir(customer_id)
    backups = []
    for f in sorted(d.glob("fg_backup_*.conf"), reverse=True):
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        })
    return backups


async def read_backup(customer_id: str, filename: str) -> Optional[str]:
    """Read and decrypt a backup file. Returns None if not found."""
    # Sanitize filename to prevent directory traversal
    safe = Path(filename).name
    path = _backup_dir(customer_id) / safe
    if not path.exists():
        return None
    return encrypted_read_text(path)


# ── 3. Config diff ──────────────────────────────────────────────────────────

async def diff_configs(
    customer_id: str, file1: str, file2: str
) -> dict:
    """Compare two backup files using unified diff.

    Returns {"ok": True, "diff": "..."} or {"ok": False, "error": "..."}.
    """
    text1 = await read_backup(customer_id, file1)
    text2 = await read_backup(customer_id, file2)

    if text1 is None:
        return {"ok": False, "error": f"Backup not found: {file1}"}
    if text2 is None:
        return {"ok": False, "error": f"Backup not found: {file2}"}

    diff_lines = list(difflib.unified_diff(
        text1.splitlines(keepends=True),
        text2.splitlines(keepends=True),
        fromfile=file1,
        tofile=file2,
    ))

    return {
        "ok": True,
        "diff": "".join(diff_lines),
        "changes": len([l for l in diff_lines if l.startswith("+") or l.startswith("-")]),
    }


# ── 4. SSH key deployment via REST API ───────────────────────────────────────

async def deploy_ssh_key(
    config: dict, token: str, admin_user: str, public_key: str
) -> dict:
    """Push an SSH public key to a FortiGate admin user via REST API.

    Uses PUT /api/v2/cmdb/system/admin/{admin_user} to set the
    ssh-public-key1 field.
    """
    # Both values land in a URL path and a FortiOS config field respectively,
    # so neither may carry separators or quotes.
    validate_identifier(admin_user, "admin_user", max_length=35)
    public_key = validate_ssh_public_key(public_key)

    async with _build_client(config, token) as fg:
        path = f"/api/v2/cmdb/system/admin/{admin_user}"
        try:
            r = await fg._client.put(
                path,
                json={"ssh-public-key1": f'"{public_key}"'},
                params={"vdom": fg.vdom},
            )
            r.raise_for_status()
            result = r.json()
            if result.get("status") == "success" or result.get("http_status") == 200:
                log.info("SSH key deployed for admin '%s' on %s", admin_user, fg.host)
                return {"ok": True, "message": f"SSH key deployed for {admin_user}"}
            return {"ok": False, "error": result.get("error", "Unknown error")}
        except Exception as e:
            log.warning("SSH key deploy failed: %s", e)
            return {"ok": False, "error": str(e)}


# ── 5. API token generation via SSH ─────────────────────────────────────────

async def generate_api_token(
    ssh_host: str,
    ssh_port: int,
    ssh_user: str,
    ssh_password: str,
    api_admin_name: str = "msp_api_admin",
    vdom: str = "root",
    trusted_hosts: str = "0.0.0.0/0",
    accprofile: str = "super_admin",
) -> dict:
    """Create an API admin account on FortiGate via SSH and return the token.

    Connects via SSH, runs FortiOS CLI commands to create a REST API
    administrator, and parses the generated token from the output.
    """
    # These values are interpolated into a CLI script executed on the
    # customer's firewall. Validate before doing anything else — a quote or
    # newline here would append arbitrary FortiOS commands. Deliberately
    # outside the try/except below so a bad value surfaces as a 400, not as
    # {"ok": False}.
    validate_identifier(api_admin_name, "api_admin_name", max_length=35)
    validate_identifier(accprofile, "accprofile", max_length=35)
    validate_identifier(vdom, "vdom", max_length=31)
    trusthosts = validate_cidr_list(trusted_hosts, "trusted_hosts")

    from app.services.ssh_connection import SshSession

    trusthost_entries = "\n".join(
        f"""            edit {i}
                set ipv4-trusthost {host}
            next"""
        for i, host in enumerate(trusthosts, start=1)
    )

    commands = f"""config system api-user
    edit "{api_admin_name}"
        set accprofile "{accprofile}"
        set vdom "{vdom}"
        config trusthost
{trusthost_entries}
        end
    next
end
"""
    token_cmd = f'execute api-user generate-key "{api_admin_name}"'

    try:
        async with await SshSession.connect(
            hostname=ssh_host,
            port=ssh_port,
            username=ssh_user,
            password=ssh_password,
        ) as session:
            # Create the API admin user
            create_result = await session.exec(commands, timeout=15)
            log.info(
                "API admin create output (exit=%d): %s",
                create_result.exit_code,
                create_result.stdout[:200],
            )

            # Generate the API key
            key_result = await session.exec(token_cmd, timeout=15)
            output = key_result.stdout

            # Parse the token from output like:
            #   New API key: xxxxxxxxxxxxxxxxxxxx
            match = re.search(r"New API key:\s*(\S+)", output)
            if match:
                api_key = match.group(1)
                log.info("API token generated for '%s'", api_admin_name)
                return {"ok": True, "token": api_key, "admin": api_admin_name}

            # Fallback: look for any token-like string
            match = re.search(r"([A-Za-z0-9]{20,})", output)
            if match:
                return {"ok": True, "token": match.group(1), "admin": api_admin_name}

            return {
                "ok": False,
                "error": "Could not parse API token from output",
                "raw_output": output[:500],
            }
    except Exception as e:
        log.warning("API token generation via SSH failed: %s", e)
        return {"ok": False, "error": str(e)}


# ── 6. Factory bootstrap — initial setup of a new FortiGate ─────────────────


async def factory_bootstrap(
    host: str,
    port: int = 22,
    new_password: str | None = None,
    api_admin_name: str = "msp_api_admin",
    hostname: str | None = None,
) -> dict:
    """Bootstrap a factory-default FortiGate via interactive SSH shell.

    Connects with admin / empty password, handles the forced password change
    prompt, applies hardening, creates a REST API admin, and returns credentials.

    Returns:
        {"ok": True, "admin_password": "...", "api_token": "...", "api_admin": "...", "host": "..."}
    """
    # Interpolated into an interactive CLI session below — validate before
    # doing anything else so a bad value can never reach the firewall.
    validate_identifier(api_admin_name, "api_admin_name", max_length=35)
    if hostname:
        validate_identifier(hostname, "hostname", max_length=35)

    import asyncio
    import secrets
    import string

    from app.services.ssh_connection import open_verified_connection

    if not new_password:
        alphabet = string.ascii_letters + string.digits + "!@#$%&*"
        new_password = "".join(secrets.choice(alphabet) for _ in range(20))

    result: dict = {
        "ok": False,
        "host": host,
        "admin_password": new_password,
        "api_token": None,
        "api_admin": api_admin_name,
        "steps": [],
    }

    # ── Helper: read from interactive shell until pattern or timeout ──
    async def _read_until(proc, patterns: list[str], timeout_s: float = 5) -> str:
        buf = ""
        for _ in range(40):
            try:
                chunk = await asyncio.wait_for(proc.stdout.read(8192), timeout=timeout_s)
                buf += chunk
                for p in patterns:
                    if p in buf:
                        return buf
            except asyncio.TimeoutError:
                break
        return buf

    async def _send(proc, cmd: str, wait_for: str = "# ", timeout_s: float = 5) -> str:
        proc.stdin.write(cmd + "\n")
        return await _read_until(proc, [wait_for], timeout_s)

    # ── Step 1: Connect with factory defaults ────────────────────────
    try:
        log.info("Factory bootstrap: connecting to %s:%d", host, port)
        # First contact with a factory-default unit, so its key is pinned here
        # and verified on every later connection.
        conn = await open_verified_connection(
            hostname=host, port=port, username="admin", password="",
            connect_timeout=20,
        )
    except Exception:
        try:
            conn = await open_verified_connection(
                hostname=host, port=port, username="admin",
                connect_timeout=20,
            )
        except Exception as e:
            result["error"] = (
                f"Kan ikke koble til {host}:{port} — er dette en ny FortiGate "
                f"med fabrikkinnstillinger? ({e})"
            )
            return result

    result["steps"].append("connected")

    try:
        proc = await conn.create_process(term_type="xterm", term_size=(200, 50))

        # ── Step 2: Handle forced password change or normal prompt ────
        initial = await _read_until(proc, ["New Password:", "# "], timeout_s=8)

        if "New Password:" in initial:
            log.info("Factory bootstrap: forced password change on %s", host)
            proc.stdin.write(new_password + "\n")
            await _read_until(proc, ["Confirm Password:"], timeout_s=5)
            proc.stdin.write(new_password + "\n")
            await _read_until(proc, ["# "], timeout_s=10)
            result["steps"].append("password_changed_interactive")
        elif "# " in initial:
            # Already past first-login (maybe password was set before)
            log.info("Factory bootstrap: got prompt directly on %s, setting password via CLI", host)
            await _send(proc, "config system admin")
            await _send(proc, "edit admin")
            await _send(proc, f'set password "{new_password}"')
            await _send(proc, "next")
            await _send(proc, "end")
            result["steps"].append("password_set_cli")
        else:
            result["error"] = f"Uventet output fra FortiGate: {initial[:200]}"
            conn.close()
            return result

        # ── Step 3: Set hostname ──────────────────────────────────────
        if hostname:
            await _send(proc, "config system global")
            await _send(proc, f'set hostname "{hostname}"')
            await _send(proc, "end")
            result["steps"].append("hostname_set")

        # ── Step 4: Apply hardening ───────────────────────────────────
        await _send(proc, "config system global")
        await _send(proc, "set admin-sport 8443")
        await _send(proc, "set strong-crypto enable")
        await _send(proc, "set admin-ssh-v2 enable")
        await _send(proc, "set usb-auto-install disable")
        await _send(proc, "set auto-auth-extension-device disable")
        await _send(proc, "set admintimeout 15")
        await _send(proc, "end")
        result["steps"].append("hardening_applied")

        # ── Step 5: Create REST API admin ─────────────────────────────
        # Trust-host left unset — operator configures per environment via GUI/CLI.
        await _send(proc, "config system api-user")
        await _send(proc, f'edit "{api_admin_name}"', "(")
        await _send(proc, "set accprofile super_admin")
        # Skip 'set vdom root' — causes error on non-multi-vdom units
        await _send(proc, "next")
        await _send(proc, "end")
        result["steps"].append("api_user_created")

        # ── Step 6: Generate API key ──────────────────────────────────
        proc.stdin.write(f"execute api-user generate-key {api_admin_name}\n")
        await asyncio.sleep(3)  # FortiGate needs time to generate key
        output = await _read_until(proc, ["# "], timeout_s=8)

        match = re.search(r"New API key:\s*(\S+)", output)
        if not match:
            match = re.search(r"new key:\s*(\S+)", output)
        if not match:
            match = re.search(r"([A-Za-z0-9]{20,})", output)

        # Mask the token before logging — never write it to msp_toolkit.log
        masked_output = output[:400]
        if match:
            masked_output = masked_output.replace(match.group(1), "***REDACTED***")
        log.info("API key output (masked): %s", masked_output)

        if match:
            result["api_token"] = match.group(1)
            result["ok"] = True
            result["steps"].append("api_token_generated")
            log.info("Factory bootstrap complete for %s", host)
        else:
            result["error"] = "Kunne ikke parse API-nøkkel fra output"
            result["raw_output"] = output[:500]
            result["steps"].append("api_token_FAILED")

    except Exception as e:
        log.warning("Factory bootstrap error: %s", e)
        result["error"] = str(e)
    finally:
        conn.close()

    return result


# ── 7. CIS compliance checking ──────────────────────────────────────────────

async def check_compliance(config: dict, token: str) -> dict:
    """Check FortiGate config against common CIS benchmark rules.

    Returns a list of findings, each with id, title, status (pass/fail/warn),
    and detail.
    """
    findings: list[dict] = []

    async with _build_client(config, token) as fg:
        admins = await fg.get_cmdb("system/admin")
        policies = await fg.get_cmdb("firewall/policy")
        log_settings = await fg.get_cmdb("log/setting")
        ha_cfg = await fg.get_cmdb("system/ha")
        password_policy = await fg.get_cmdb("system/password-policy")
        global_settings = await fg.get_cmdb("system/global")

    # --- Rule 1: Admin trust hosts configured ---
    if isinstance(admins, list):
        for admin in admins:
            name = admin.get("name", "unknown")
            trusthosts = admin.get("trusthost1", "0.0.0.0 0.0.0.0")
            is_open = trusthosts in ("0.0.0.0 0.0.0.0", "0.0.0.0/0", "")
            findings.append({
                "id": "CIS-1.1",
                "title": f"Admin trust host — {name}",
                "status": "fail" if is_open else "pass",
                "detail": (
                    f"Admin '{name}' has unrestricted trust host ({trusthosts})"
                    if is_open
                    else f"Admin '{name}' trust host: {trusthosts}"
                ),
            })

    # --- Rule 2: Two-factor authentication ---
    if isinstance(admins, list):
        for admin in admins:
            name = admin.get("name", "unknown")
            two_factor = admin.get("two-factor", "disable")
            findings.append({
                "id": "CIS-1.2",
                "title": f"Two-factor auth — {name}",
                "status": "pass" if two_factor != "disable" else "fail",
                "detail": (
                    f"Admin '{name}' has 2FA enabled ({two_factor})"
                    if two_factor != "disable"
                    else f"Admin '{name}' does not have 2FA enabled"
                ),
            })

    # --- Rule 3: Logging enabled ---
    if isinstance(log_settings, list):
        log_cfg = log_settings[0] if log_settings else {}
    elif isinstance(log_settings, dict):
        log_cfg = log_settings
    else:
        log_cfg = {}

    log_disk = log_cfg.get("log-disk", log_cfg.get("status", "disable"))
    findings.append({
        "id": "CIS-2.1",
        "title": "Logging enabled",
        "status": "pass" if log_disk == "enable" else "warn",
        "detail": (
            "Disk logging is enabled"
            if log_disk == "enable"
            else f"Disk logging status: {log_disk}"
        ),
    })

    # --- Rule 4: No allow-all firewall policies ---
    if isinstance(policies, list):
        allow_all_count = 0
        for pol in policies:
            src = pol.get("srcaddr", [])
            dst = pol.get("dstaddr", [])
            action = pol.get("action", "")
            svc = pol.get("service", [])

            src_all = any(
                a.get("name", "") == "all" for a in src
            ) if isinstance(src, list) else False
            dst_all = any(
                a.get("name", "") == "all" for a in dst
            ) if isinstance(dst, list) else False
            svc_all = any(
                s.get("name", "") == "ALL" for s in svc
            ) if isinstance(svc, list) else False

            if action == "accept" and src_all and dst_all and svc_all:
                allow_all_count += 1
                findings.append({
                    "id": "CIS-3.1",
                    "title": f"Allow-all policy — ID {pol.get('policyid', '?')}",
                    "status": "fail",
                    "detail": (
                        f"Policy {pol.get('policyid', '?')} "
                        f"({pol.get('name', 'unnamed')}) allows all "
                        f"src/dst/service traffic"
                    ),
                })

        if allow_all_count == 0:
            findings.append({
                "id": "CIS-3.1",
                "title": "Allow-all policies",
                "status": "pass",
                "detail": "No allow-all policies found",
            })

    # --- Rule 5: HA configuration ---
    if isinstance(ha_cfg, list):
        ha_data = ha_cfg[0] if ha_cfg else {}
    elif isinstance(ha_cfg, dict):
        ha_data = ha_cfg
    else:
        ha_data = {}

    ha_mode = ha_data.get("mode", "standalone")
    findings.append({
        "id": "CIS-4.1",
        "title": "High availability",
        "status": "pass" if ha_mode != "standalone" else "warn",
        "detail": (
            f"HA mode: {ha_mode}"
            if ha_mode != "standalone"
            else "FortiGate is running in standalone mode (no HA)"
        ),
    })

    # --- Rule 6: Password policy ---
    if isinstance(password_policy, list):
        pp = password_policy[0] if password_policy else {}
    elif isinstance(password_policy, dict):
        pp = password_policy
    else:
        pp = {}

    pp_status = pp.get("status", "disable")
    min_len = pp.get("min-length", 0)
    findings.append({
        "id": "CIS-5.1",
        "title": "Password policy",
        "status": "pass" if pp_status == "enable" and min_len >= 8 else "fail",
        "detail": (
            f"Password policy enabled, min length {min_len}"
            if pp_status == "enable"
            else "Password policy is not enabled or minimum length < 8"
        ),
    })

    # --- Rule 7: Admin timeout (from global settings) ---
    if isinstance(global_settings, list):
        gs = global_settings[0] if global_settings else {}
    elif isinstance(global_settings, dict):
        gs = global_settings
    else:
        gs = {}

    admin_timeout = gs.get("admintimeout", 0)
    findings.append({
        "id": "CIS-5.2",
        "title": "Admin session timeout",
        "status": "pass" if 0 < admin_timeout <= 15 else "warn",
        "detail": (
            f"Admin timeout: {admin_timeout} minutes"
            if admin_timeout > 0
            else "Admin timeout is not configured"
        ),
    })

    # Compute summary
    passed = sum(1 for f in findings if f["status"] == "pass")
    failed = sum(1 for f in findings if f["status"] == "fail")
    warned = sum(1 for f in findings if f["status"] == "warn")

    return {
        "ok": True,
        "summary": {
            "total": len(findings),
            "pass": passed,
            "fail": failed,
            "warn": warned,
            "score": round(passed / len(findings) * 100) if findings else 0,
        },
        "findings": findings,
    }


# ── 7. Multi-device fleet polling ─────────────────────────────────────────────

async def poll_all_fortigates() -> list[dict]:
    """Poll all customers with FortiGate configured and return status for each.

    Returns a sorted list of device status dicts (errors first, then by name).
    """
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager

    customers = CustomerManager.list_customers()
    fg_customers = []
    for c in customers:
        if not c.get("FortiGateHost"):
            continue
        cid = c.get("_id", c.get("customer_id", ""))
        if get_secret(cid, "fortigate_api_token"):
            fg_customers.append(c)

    if not fg_customers:
        return []

    async def _poll_one(cust: dict) -> dict:
        cid = cust.get("_id", cust.get("customer_id", ""))
        name = cust.get("CustomerName", "Unknown")
        fg_host = cust.get("FortiGateHost")
        fg_token = get_secret(cid, "fortigate_api_token")

        try:
            async with FortiGateClient(
                fg_host, fg_token,
                port=int(cust.get("FortiGatePort", 443)),
                vdom=cust.get("FortiGateVDOM", "root"),
                verify_ssl=cust.get("FortiGateVerifySSL", True),
            ) as fg:
                status, perf, firmware, csf, vpn_mon, policies = await asyncio.gather(
                    fg.get_system_status(),
                    fg.get_monitor("system/performance/status"),
                    fg.get_monitor("system/firmware"),
                    fg.get_monitor("system/csf"),
                    fg.get_monitor("vpn/ipsec"),
                    fg.get_cmdb("firewall/policy"),
                    return_exceptions=True,
                )

                hostname = status.get("hostname", fg_host) if isinstance(status, dict) else fg_host
                model = status.get("model", "") if isinstance(status, dict) else ""

                fw_ver = ""
                if isinstance(firmware, dict):
                    fw_ver = firmware.get("current", {}).get("version", "")

                serial = ""
                uptime_str = ""
                if isinstance(csf, dict):
                    devs = csf.get("devices", {}).get("fortigate", [])
                    if devs:
                        serial = devs[0].get("serial", "")
                        state = devs[0].get("state", {})
                        reboot_ms = state.get("utc_last_reboot", 0) if isinstance(state, dict) else 0
                        if reboot_ms > 0:
                            import time

                            from app.core.utils import format_uptime
                            secs = int(time.time()) - (reboot_ms // 1000)
                            if secs > 0:
                                uptime_str = format_uptime(secs)

                cpu = None
                mem = None
                if isinstance(perf, dict):
                    cpu_data = perf.get("cpu", {})
                    if isinstance(cpu_data, dict):
                        user = cpu_data.get("user", 0)
                        system = cpu_data.get("system", 0)
                        cpu = user + system if (user or system) else None
                        if cpu is None and "cores" in cpu_data:
                            cores = cpu_data["cores"]
                            if isinstance(cores, list) and cores:
                                cpu = round(sum(100 - c.get("idle", 100) for c in cores) / len(cores), 1)
                    mem_data = perf.get("mem", {})
                    if isinstance(mem_data, dict):
                        total = mem_data.get("total", 0)
                        used = mem_data.get("used", 0)
                        if total > 0:
                            mem = round((used / total) * 100, 1)

                vpn_count = len(vpn_mon) if isinstance(vpn_mon, list) else 0
                policy_count = len(policies) if isinstance(policies, list) else 0

                return {
                    "customer_id": cid,
                    "customer_name": name,
                    "host": fg_host,
                    "hostname": hostname,
                    "model": model,
                    "serial": serial,
                    "firmware": fw_ver,
                    "uptime": uptime_str,
                    "cpu_pct": cpu,
                    "mem_pct": mem,
                    "vpn_tunnels": vpn_count,
                    "policy_count": policy_count,
                    "status": "online",
                }
        except Exception as e:
            return {"customer_id": cid, "customer_name": name, "host": fg_host, "status": "error", "error": str(e)}

    async def _poll_with_timeout(cust: dict) -> dict:
        try:
            return await asyncio.wait_for(_poll_one(cust), timeout=10)
        except asyncio.TimeoutError:
            return {
                "customer_id": cust.get("_id", ""),
                "customer_name": cust.get("CustomerName", "Unknown"),
                "host": cust.get("FortiGateHost", ""),
                "status": "error",
                "error": "Timeout (10s)",
            }

    all_results = await asyncio.gather(*[_poll_with_timeout(c) for c in fg_customers])
    results = [r for r in all_results if r is not None]
    results.sort(key=lambda x: (0 if x["status"] == "error" else 1, x["customer_name"].lower()))
    return results


# ── 8. Quick FortiGate audit for a single customer ────────────────────────────

async def quick_audit_fortigate(config: dict, token: str) -> dict:
    """Run a quick FortiGate audit — gathers key data for a single customer.

    Returns a dict with hostname, firmware, admins, policies, VPN tunnels, etc.
    """
    async with _build_client(config, token) as fg:
        status = await fg.get_system_status()
        admins = await fg.get_cmdb("system/admin")
        policies = await fg.get_cmdb("firewall/policy")
        interfaces = await fg.get_cmdb("system/interface")
        vpn_phase1 = await fg.get_cmdb("vpn.ipsec/phase1-interface")
        ha = await fg.get_cmdb("system/ha")
        license_status = await fg.get_monitor("license/status")

    admin_list = []
    for a in (admins if isinstance(admins, list) else []):
        admin_list.append({
            "name": a.get("name", ""),
            "profile": a.get("accprofile", ""),
            "trusthost": bool(a.get("trusthost1", "0.0.0.0") != "0.0.0.0"),
            "two_factor": a.get("two-factor", "disable") != "disable",
        })

    policy_warns = []
    for p in (policies if isinstance(policies, list) else []):
        pid = p.get("policyid", "?")
        if p.get("action") == "accept":
            src = [s.get("name", "") for s in p.get("srcaddr", [])]
            dst = [d.get("name", "") for d in p.get("dstaddr", [])]
            svc = [s.get("name", "") for s in p.get("service", [])]
            if "all" in src and "all" in dst and "ALL" in svc:
                policy_warns.append(f"Policy {pid}: allow-all (src=all, dst=all, svc=ALL)")
            if p.get("logtraffic", "") == "disable":
                policy_warns.append(f"Policy {pid}: logging disabled")

    iface_count = len(interfaces) if isinstance(interfaces, list) else 0
    vpn_count = len(vpn_phase1) if isinstance(vpn_phase1, list) else 0

    ha_mode = "Standalone"
    if isinstance(ha, list) and ha:
        ha_mode = ha[0].get("mode", "standalone").capitalize()
    elif isinstance(ha, dict):
        ha_mode = ha.get("mode", "standalone").capitalize()

    return {
        "hostname": status.get("hostname", ""),
        "firmware": status.get("version", ""),
        "serial": status.get("serial", ""),
        "uptime": status.get("uptime", ""),
        "model": status.get("model-name", status.get("model", "")),
        "ha_mode": ha_mode,
        "admins": admin_list,
        "admin_count": len(admin_list),
        "policy_count": len(policies) if isinstance(policies, list) else 0,
        "policy_warnings": policy_warns,
        "interface_count": iface_count,
        "vpn_tunnels": vpn_count,
        "license": license_status if isinstance(license_status, dict) else {},
    }


# ── 9. Threat summary ──────────────────────────────────────────────────────

async def get_threat_summary(config: dict, token: str, days: int = 7) -> dict:
    """Fetch threat logs from FortiGate and return a grouped summary.

    Queries the IPS, antivirus, and webfilter log endpoints, merges
    results, groups by type/severity, and returns the top 10 recent events.
    """
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_epoch = int(since.timestamp())

    severity_map = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "information": "low",
        "info": "low",
        "warning": "medium",
        "alert": "critical",
        "emergency": "critical",
    }

    all_events: list[dict] = []

    async with _build_client(config, token) as fg:
        # Query multiple log categories
        log_queries = [
            ("log/ips/utm/ips", "ips"),
            ("log/virus/utm/virus", "virus"),
            ("log/webfilter/utm/webfilter", "webfilter"),
        ]

        for endpoint, event_type in log_queries:
            try:
                data = await fg.get_monitor(
                    endpoint,
                    params={
                        "rows": 500,
                        "serial_no": "",
                        "session_id": 0,
                        "filter": f"date>={since.strftime('%Y-%m-%d')}",
                    },
                )
                rows = []
                if isinstance(data, list):
                    rows = data
                elif isinstance(data, dict):
                    rows = data.get("logs", data.get("data", []))
                    if not rows and "results" in data:
                        rows = data["results"] if isinstance(data["results"], list) else []

                for row in rows:
                    sev_raw = str(row.get("severity", row.get("level", "low"))).lower()
                    severity = severity_map.get(sev_raw, "low")
                    ts = row.get("date", "") + " " + row.get("time", "")
                    ts = ts.strip() or row.get("timestamp", row.get("eventtime", ""))
                    all_events.append({
                        "timestamp": str(ts),
                        "type": event_type,
                        "severity": severity,
                        "srcip": row.get("srcip", row.get("src", "")),
                        "dstip": row.get("dstip", row.get("dst", "")),
                        "attack": row.get("attack", row.get("msg", row.get("name", ""))),
                        "action": row.get("action", row.get("utmaction", "unknown")),
                    })
            except Exception as exc:
                log.debug("Threat log query %s failed: %s", endpoint, exc)

        # Also try the unified threat log endpoint (available on some firmware)
        try:
            data = await fg.get_monitor(
                "log/threat",
                params={"rows": 500, "filter": f"date>={since.strftime('%Y-%m-%d')}"},
            )
            rows = []
            if isinstance(data, list):
                rows = data
            elif isinstance(data, dict):
                rows = data.get("logs", data.get("data", []))

            for row in rows:
                etype = str(row.get("type", row.get("subtype", "ips"))).lower()
                if etype not in ("ips", "virus", "botnet", "webfilter"):
                    etype = "ips"
                sev_raw = str(row.get("severity", row.get("level", "low"))).lower()
                severity = severity_map.get(sev_raw, "low")
                ts = row.get("date", "") + " " + row.get("time", "")
                ts = ts.strip() or row.get("timestamp", row.get("eventtime", ""))
                all_events.append({
                    "timestamp": str(ts),
                    "type": etype,
                    "severity": severity,
                    "srcip": row.get("srcip", row.get("src", "")),
                    "dstip": row.get("dstip", row.get("dst", "")),
                    "attack": row.get("attack", row.get("msg", row.get("name", ""))),
                    "action": row.get("action", row.get("utmaction", "unknown")),
                })
        except Exception as exc:
            log.debug("Unified threat log query failed: %s", exc)

    # Deduplicate by (timestamp, srcip, attack)
    seen: set[tuple] = set()
    unique: list[dict] = []
    for ev in all_events:
        key = (ev["timestamp"], ev["srcip"], ev["attack"])
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    # Sort by timestamp descending
    unique.sort(key=lambda e: e["timestamp"], reverse=True)

    # Build summary
    summary = {"total": len(unique), "critical": 0, "high": 0, "medium": 0, "low": 0}
    by_type: dict[str, int] = {}
    for ev in unique:
        summary[ev["severity"]] = summary.get(ev["severity"], 0) + 1
        by_type[ev["type"]] = by_type.get(ev["type"], 0) + 1

    return {
        "summary": summary,
        "by_type": by_type,
        "recent": unique[:10],
        "period_days": days,
    }


# ── 10. Firewall rule audit ────────────────────────────────────────────────

async def audit_firewall_rules(config: dict, token: str) -> dict:
    """Audit firewall policies for common security issues.

    Fetches all policies from FortiGate CMDB, analyses each for
    any-any rules, missing logging, disabled/unused rules, and
    computes a security score (100 = perfect).
    """
    async with _build_client(config, token) as fg:
        policies = await fg.get_cmdb("firewall/policy")

    if not isinstance(policies, list):
        policies = []

    total = len(policies)
    enabled = 0
    disabled = 0
    unused = 0
    issues: list[dict] = []
    score = 100

    for pol in policies:
        pid = pol.get("policyid", "?")
        name = pol.get("name", f"Policy {pid}")
        status = pol.get("status", "enable")
        action = pol.get("action", "")

        if status == "disable":
            disabled += 1
            continue
        enabled += 1

        # Check for any-any accept rules
        src = pol.get("srcaddr", [])
        dst = pol.get("dstaddr", [])
        src_all = any(
            a.get("name", "") == "all" for a in src
        ) if isinstance(src, list) else False
        dst_all = any(
            a.get("name", "") == "all" for a in dst
        ) if isinstance(dst, list) else False

        if action == "accept" and src_all and dst_all:
            issues.append({
                "policy_id": pid,
                "name": name,
                "issue": "any_any",
                "severity": "critical",
                "detail": "Source and destination are 'all' with action accept",
            })
            score -= 20

        # Check for no logging
        logtraffic = pol.get("logtraffic", "")
        if logtraffic == "disable":
            issues.append({
                "policy_id": pid,
                "name": name,
                "issue": "no_logging",
                "severity": "warning",
                "detail": "Traffic logging is disabled on this policy",
            })
            score -= 5

        # Count rules with 0 hit count (informational only — counters reset on reboot)
        hit_count = 0
        if isinstance(pol.get("_hitcount"), int):
            hit_count = pol["_hitcount"]
        elif isinstance(pol.get("hit-count"), int):
            hit_count = pol["hit-count"]
        elif isinstance(pol.get("hitcount"), int):
            hit_count = pol["hitcount"]

        if hit_count == 0 and status != "disable":
            unused += 1
            # Don't flag as issue or deduct score — hit counters are unreliable
            # (reset on reboot, firmware upgrade, or may not be returned by API)

        # Note scheduled rules
        schedule = pol.get("schedule", "always")
        if isinstance(schedule, list) and schedule:
            schedule = schedule[0].get("name", "always")
        if schedule and schedule != "always":
            issues.append({
                "policy_id": pid,
                "name": name,
                "issue": "scheduled",
                "severity": "info",
                "detail": f"Rule uses schedule '{schedule}' instead of always",
            })

    score = max(0, score)

    return {
        "total_rules": total,
        "enabled": enabled,
        "disabled": disabled,
        "issues": issues,
        "unused_rules": unused,
        "score": score,
    }
