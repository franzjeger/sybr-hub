"""Azure P2S VPN backend (Entra ID + OpenVPN).

Uses PKCE authorization-code flow (like SuperManager) with a local
redirect URI handled by our web server. Opens a popup for MFA login.
"""
import asyncio
import base64
import hashlib
import json
import logging
import os
import pathlib
import secrets
from typing import Optional

import httpx

from app.core.utils import fire_and_forget

logger = logging.getLogger(__name__)

# Pending auth state — stores code_verifier keyed by state parameter
_pending_auth: dict[str, dict] = {}


def get_auth_url(config: dict, redirect_uri: str) -> dict:
    """Generate OAuth2 PKCE authorization URL for popup login.

    Returns {url, state} — open url in popup, state is used to match callback.
    """
    tenant_id = config.get("tenant_id", "")
    # Use the audience as client_id (SuperManager approach — avoids AADSTS650057)
    client_id = config.get("client_id", "")

    # PKCE
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    state = secrets.token_urlsafe(32)

    # Store for callback
    _pending_auth[state] = {
        "code_verifier": code_verifier,
        "config": config,
        "redirect_uri": redirect_uri,
    }

    scope = f"{client_id}/.default openid offline_access profile"

    url = (
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?"
        f"client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope.replace(' ', '+')}"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&login_hint={_load_login_hint(client_id, tenant_id) or config.get('login_hint', '')}"
    )

    return {"url": url, "state": state}


async def exchange_code(state: str, code: str) -> dict:
    """Exchange authorization code for access token after user completes MFA."""
    pending = _pending_auth.pop(state, None)
    if not pending:
        return {"ok": False, "error": "Ugyldig eller utløpt auth-forespørsel"}

    config = pending["config"]
    code_verifier = pending["code_verifier"]
    redirect_uri = pending["redirect_uri"]

    tenant_id = config.get("tenant_id", "")
    client_id = config.get("client_id", "")

    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        data = resp.json()

        if "access_token" in data:
            # Cache refresh token for silent re-auth later
            refresh = data.get("refresh_token", "")
            if refresh:
                _save_refresh_token(client_id, tenant_id, refresh)

            # Extract UPN from id_token for login_hint
            id_token = data.get("id_token", "")
            if id_token:
                try:
                    # Decode JWT payload (no verification needed, just for UPN)
                    payload_b64 = id_token.split(".")[1]
                    payload_b64 += "=" * (4 - len(payload_b64) % 4)
                    import json as _json
                    claims = _json.loads(base64.urlsafe_b64decode(payload_b64))
                    upn = claims.get("preferred_username", claims.get("upn", claims.get("email", "")))
                    if upn:
                        _save_login_hint(client_id, tenant_id, upn)
                except Exception as e:
                    logger.debug("Failed to extract UPN from id_token: %s", e)

            return {
                "ok": True,
                "access_token": data["access_token"],
                "refresh_token": refresh,
                "expires_in": data.get("expires_in", 3600),
            }

        return {
            "ok": False,
            "error": data.get("error_description", data.get("error", "Token exchange feilet")),
        }


# ── Device Code Flow via MSAL (headless servers) ────────────────────────────

_device_code_pending: dict[str, dict] = {}

async def start_device_code_flow(config: dict) -> dict:
    """Start device code flow for Azure P2S VPN using MSAL.

    Uses the VPN gateway's audience (c632b3df) directly as client_id
    via MSAL PublicClientApplication. MSAL handles it as a public client
    even though raw HTTP calls fail with 'client_secret required'.
    """
    import msal

    tenant_id = config.get("tenant_id", "")
    # Use the VPN gateway's audience as both client_id and scope
    # For device code to work, this app must be a public client (isFallbackPublicClient=true)
    # If c632b3df doesn't work (confidential), use vpn_client_id from config
    client_id = config.get("vpn_client_id", config.get("client_id", ""))
    authority = f"https://login.microsoftonline.com/{tenant_id}"

    app = msal.PublicClientApplication(client_id, authority=authority)
    flow = app.initiate_device_flow(scopes=[f"{client_id}/.default"])

    if "user_code" not in flow:
        error = flow.get("error_description", flow.get("error", "Device code request failed"))
        return {"ok": False, "error": error}

    device_code = flow.get("device_code", "")

    _device_code_pending[device_code] = {
        "config": config,
        "flow": flow,
        "msal_app": app,
        "status": "pending",
        "token": None,
        "error": None,
    }

    # Poll in background — MSAL blocks, so run in executor
    fire_and_forget(_poll_device_code_msal(device_code))

    return {
        "ok": True,
        "user_code": flow["user_code"],
        "verification_uri": flow.get("verification_uri", "https://microsoft.com/devicelogin"),
        "message": flow.get("message", ""),
        "expires_in": flow.get("expires_in", 900),
        "device_code": device_code,
    }


async def _poll_device_code_msal(device_code: str):
    """Background: MSAL polls Azure until user completes login."""
    pending = _device_code_pending.get(device_code)
    if not pending:
        return

    app = pending["msal_app"]
    flow = pending["flow"]
    config = pending["config"]
    tenant_id = config.get("tenant_id", "")

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, lambda: app.acquire_token_by_device_flow(flow)
        )
    except Exception as e:
        pending["status"] = "error"
        pending["error"] = str(e)
        return

    if "access_token" in result:
        pending["status"] = "complete"
        pending["token"] = result["access_token"]
        logger.info("Device code flow completed via MSAL")

        refresh = result.get("refresh_token", "")
        client_id = config.get("vpn_client_id", config.get("client_id", ""))
        if refresh:
            _save_refresh_token(client_id, tenant_id, refresh)
    else:
        pending["status"] = "error"
        pending["status"] = "error"
        pending["error"] = result.get("error_description", result.get("error", "Authentication failed"))


def get_device_code_status(device_code: str) -> dict:
    """Check the status of a device code flow."""
    pending = _device_code_pending.get(device_code)
    if not pending:
        return {"status": "unknown", "error": "Device code not found"}
    return {
        "status": pending["status"],
        "token": pending.get("token"),
        "error": pending.get("error"),
    }


async def get_token_silent(config: dict) -> Optional[str]:
    """Try to get a new access token using a cached refresh token.

    Returns access_token if successful, None if re-auth needed.
    """
    tenant_id = config.get("tenant_id", "")
    client_id = config.get("client_id", "")

    refresh_token = _load_refresh_token(client_id, tenant_id)
    if not refresh_token:
        return None

    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
                "scope": f"{client_id}/.default openid offline_access profile",
            },
        )
        data = resp.json()

        if "access_token" in data:
            # Update cached refresh token
            new_refresh = data.get("refresh_token", "")
            if new_refresh:
                _save_refresh_token(client_id, tenant_id, new_refresh)
            logger.info("Azure VPN token refreshed silently (no MFA needed)")
            return data["access_token"]

        # Refresh token expired — need interactive login
        logger.info("Azure refresh token expired, interactive login needed")
        return None


def _save_refresh_token(client_id: str, tenant_id: str, token: str):
    from app.core.config import DATA_DIR
    from app.core.encryption import encrypted_write_bytes
    token_dir = DATA_DIR / "azure_vpn_tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{client_id}:{tenant_id}".encode()).hexdigest()[:16]
    encrypted_write_bytes(token_dir / f"{key}.token", token.encode())


def _load_refresh_token(client_id: str, tenant_id: str) -> Optional[str]:
    from app.core.config import DATA_DIR
    from app.core.encryption import encrypted_read_bytes
    key = hashlib.sha256(f"{client_id}:{tenant_id}".encode()).hexdigest()[:16]
    token_path = DATA_DIR / "azure_vpn_tokens" / f"{key}.token"
    if not token_path.exists():
        return None
    try:
        return encrypted_read_bytes(token_path).decode()
    except Exception as e:
        logger.warning("Failed to load refresh token: %s", e)
        return None


def _save_login_hint(client_id: str, tenant_id: str, upn: str):
    from app.core.config import DATA_DIR
    from app.core.encryption import encrypted_write_bytes
    token_dir = DATA_DIR / "azure_vpn_tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{client_id}:{tenant_id}".encode()).hexdigest()[:16]
    encrypted_write_bytes(token_dir / f"{key}.hint", upn.encode())


def _load_login_hint(client_id: str, tenant_id: str) -> str:
    from app.core.config import DATA_DIR
    from app.core.encryption import encrypted_read_bytes
    key = hashlib.sha256(f"{client_id}:{tenant_id}".encode()).hexdigest()[:16]
    hint_path = DATA_DIR / "azure_vpn_tokens" / f"{key}.hint"
    if not hint_path.exists():
        return ""
    try:
        return encrypted_read_bytes(hint_path).decode()
    except Exception as e:
        logger.debug("Failed to load login hint: %s", e)
        return ""


def _cidr_to_netmask(prefix_len: int) -> str:
    """Convert CIDR prefix length to dotted netmask."""
    mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
    return f"{(mask >> 24) & 0xFF}.{(mask >> 16) & 0xFF}.{(mask >> 8) & 0xFF}.{mask & 0xFF}"


async def connect(config: dict, access_token: str) -> dict:
    """Connect via OpenVPN 3 (openvpn3-client) with Azure AD token.

    OpenVPN 3 handles large JWT tokens and EKM key derivation natively.
    No patching or custom builds needed — just `apt install openvpn3-client`.
    """
    import shutil

    gw = config.get("gateway_fqdn", "")
    ca_cert = config.get("ca_cert_pem", "")
    tls_key_hex = config.get("server_secret_hex", "")
    dns_servers = config.get("dns_servers", [])

    if not gw:
        return {"ok": False, "error": "Ingen gateway FQDN konfigurert"}

    if not shutil.which("openvpn3"):
        return {"ok": False, "error": "openvpn3 ikke installert. Kjør: sudo apt install openvpn3-client"}

    # Write TLS key from hex in OpenVPN static key format
    tls_key_path = pathlib.Path("/tmp/azure_vpn_tls.key")
    if tls_key_hex:
        hex_clean = tls_key_hex.strip()
        lines = [hex_clean[i:i+32] for i in range(0, len(hex_clean), 32)]
        key_text = "-----BEGIN OpenVPN Static key V1-----\n"
        key_text += "\n".join(lines) + "\n"
        key_text += "-----END OpenVPN Static key V1-----\n"
        tls_key_path.write_text(key_text)
        tls_key_path.chmod(0o644)

    # Build config — openvpn3 uses auth-user-pass without file (piped via stdin)
    ovpn_lines = [
        "client", "dev tun", "proto tcp",
        f"remote {gw} 443",
        "resolv-retry infinite", "nobind", "persist-tun",
        "remote-cert-tls server",
        "auth SHA256", "cipher AES-256-GCM", "data-ciphers AES-256-GCM",
        "disable-dco", "verb 3",
        "auth-user-pass",
        f"tls-auth {tls_key_path} 1",
    ]
    if ca_cert:
        ovpn_lines.append(f"<ca>\n{ca_cert.strip()}\n</ca>")

    conf_path = pathlib.Path("/tmp/azure_vpn3.ovpn")
    conf_path.write_text("\n".join(ovpn_lines) + "\n")

    # Disconnect any existing session
    kill_proc = await asyncio.create_subprocess_exec(
        "openvpn3", "sessions-list",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    sessions_out, _ = await kill_proc.communicate()
    for line in sessions_out.decode().split("\n"):
        if "Path:" in line:
            spath = line.split("Path:")[1].strip()
            await (await asyncio.create_subprocess_exec(
                "openvpn3", "session-manage", "--disconnect", "--path", spath,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)).wait()
    await asyncio.sleep(1)

    # Start openvpn3 — pipe credentials via stdin
    proc = await asyncio.create_subprocess_exec(
        "openvpn3", "session-start", "--config", str(conf_path), "--timeout", "15",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(input=f"AzureAD\n{access_token}\n".encode()),
        timeout=20)

    output = stdout.decode() + stderr.decode()
    logger.info("openvpn3 output: %s", output[:300])

    if proc.returncode != 0:
        return {"ok": False, "error": f"openvpn3 feilet: {output[:500]}"}

    # Check tun0
    await asyncio.sleep(2)
    check = await asyncio.create_subprocess_exec(
        "ip", "addr", "show", "dev", "tun0",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    ip_out, _ = await check.communicate()

    if check.returncode != 0 or b"inet " not in ip_out:
        return {"ok": False, "error": f"openvpn3 startet men tun0 kom ikke opp.\n{output[:300]}"}

    ip_line = [l for l in ip_out.decode().split("\n") if "inet " in l]
    local_ip = ip_line[0].strip().split()[1].split("/")[0] if ip_line else "?"
    logger.info("Azure VPN connected via openvpn3: tun0 = %s", local_ip)

    # Set DNS. dns_servers is operator config, but it can be imported from an
    # untrusted .ovpn — and it reaches `sudo resolvectl` as an argument, where
    # a value starting with "-" would be a flag. An IP cannot; validate first.
    import ipaddress
    for dns in dns_servers:
        try:
            ipaddress.ip_address(str(dns).strip())
        except ValueError:
            logger.warning("Ignoring invalid DNS server %r from config", dns)
            continue
        await (await asyncio.create_subprocess_exec(
            "sudo", "resolvectl", "dns", "tun0", str(dns).strip(),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)).wait()

    # Save refresh token for auto-refresh
    client_id = config.get("client_id", "")
    tenant_id = config.get("tenant_id", "")
    refresh = _load_refresh_token(client_id, tenant_id)
    if refresh:
        rt_tmp = pathlib.Path("/tmp/azure_vpn_rt.txt")
        rt_tmp.write_text(refresh)
        await (await asyncio.create_subprocess_exec(
            "sudo", "cp", str(rt_tmp), "/etc/openvpn/msp/refresh_token.txt",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)).wait()
        await (await asyncio.create_subprocess_exec(
            "sudo", "chmod", "644", "/etc/openvpn/msp/refresh_token.txt",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)).wait()
        rt_tmp.unlink(missing_ok=True)

    return {"ok": True, "interface": "tun0", "local_ip": local_ip}


async def disconnect() -> dict:
    """Disconnect all openvpn3 sessions."""
    proc = await asyncio.create_subprocess_exec(
        "openvpn3", "sessions-list",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    disconnected = 0
    for line in out.decode().split("\n"):
        if "Path:" in line:
            spath = line.split("Path:")[1].strip()
            await (await asyncio.create_subprocess_exec(
                "openvpn3", "session-manage", "--disconnect", "--path", spath,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)).wait()
            disconnected += 1

    # Also kill any legacy openvpn processes
    await (await asyncio.create_subprocess_exec(
        "sudo", "pkill", "-f", "openvpn.*azure",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)).wait()

    return {"ok": True, "message": f"Disconnected {disconnected} session(s)"}


async def get_status() -> dict:
    """Check openvpn3 session status."""
    proc = await asyncio.create_subprocess_exec(
        "openvpn3", "sessions-list",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    output = out.decode()
    if "Client connected" in output:
        return {"connected": True}
    return {"connected": False}
