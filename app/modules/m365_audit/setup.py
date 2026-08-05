"""First-run setup: App Registration, permissions, cert, secret, Azure role.

Python generates the certificate (cross-platform), then delegates all
Microsoft 365 / Azure work to a PowerShell 7 subprocess (setup_helper.ps1)
which uses the Microsoft Graph PowerShell public-client app for device-code
auth — no MSAL, no separate app registration required.

Usage:
    setup = FirstRunSetup(on_device_code=callback)
    async for event in setup.run():
        # event = {"step": str, "status": "ok|warn|error", "msg": str}
        yield event
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import re
from pathlib import Path
from typing import AsyncGenerator, Callable, Optional

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mK]")

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from app.core.config import REQUIRED_GRAPH_PERMISSIONS, AUDIT_APP_NAME
from app.core.credentials import (
    generate_cert_password,
    save_cert,
    save_config,
    store_secret,
)
from app.core.pwsh import ensure_pwsh, find_pwsh

_HELPERS_DIR = Path(__file__).parent.parent.parent / "helpers"
_SETUP_PS1   = _HELPERS_DIR / "setup_helper.ps1"

SetupEvent = dict  # {"step": str, "status": str, "msg": str}


class FirstRunSetup:
    """Orchestrates the full first-run setup flow via a PS7 subprocess."""

    def __init__(self, on_device_code: Optional[Callable[[str, str], None]] = None):
        """
        on_device_code: called with (user_code, verification_url) when a
                        device-code prompt is needed — use this to show the
                        code in the TUI.
        """
        self.on_device_code = on_device_code

    # ── Entry point ───────────────────────────────────────────────────────────

    async def run(self) -> AsyncGenerator[SetupEvent, None]:
        """Yield setup events. Completes when the script exits."""

        # 1. Generate certificate locally (cross-platform cryptography)
        yield {"step": "Cert", "status": "ok", "msg": "Generating self-signed certificate (2 years)..."}
        try:
            cert_der_b64, cert_expiry_iso, cert_start_iso, pfx_bytes, cert_password = _generate_cert()
        except Exception as e:
            yield {"step": "Cert", "status": "error", "msg": f"Certificate generation failed: {e}"}
            return

        save_cert(pfx_bytes)

        # 2. Ensure PowerShell 7 is available (auto-install if needed)
        async for event in ensure_pwsh():
            yield event
            if event["status"] == "error":
                return

        pwsh_exe = find_pwsh()
        if not pwsh_exe:
            yield {"step": "PwshInstall", "status": "error",
                   "msg": "PowerShell 7 not available. Install from https://aka.ms/install-powershell"}
            return

        # 3. Launch the PowerShell helper
        stdin_payload = json.dumps({
            "cert_der_b64": cert_der_b64,
            "cert_expiry":  cert_expiry_iso,
            "cert_start":   cert_start_iso,
            "app_name":     AUDIT_APP_NAME,
            # The helper grants exactly what GraphClient later checks for.
            "required_permissions": list(REQUIRED_GRAPH_PERMISSIONS),
        }).encode()

        # app/helpers/*.ps1 has never been committed to the repository, so a
        # clone gets a wizard that cannot run. Without this check pwsh is
        # handed a path that does not exist and reports it in its own words,
        # which reads like a PowerShell problem rather than a missing file.
        if not _SETUP_PS1.exists():
            yield {"step": "Setup", "status": "error",
                   "msg": f"Setup helper not found: {_SETUP_PS1} — the "
                          "app/helpers/*.ps1 scripts are not part of the "
                          f"repository. Copy them into {_HELPERS_DIR} on this host."}
            return

        try:
            proc = await asyncio.create_subprocess_exec(
                pwsh_exe, "-NoProfile", "-NonInteractive", "-File", str(_SETUP_PS1),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            yield {"step": "Setup", "status": "error",
                   "msg": f"Could not launch {pwsh_exe} — check your installation."}
            return

        proc.stdin.write(stdin_payload)
        await proc.stdin.drain()
        proc.stdin.close()

        result_json: Optional[dict] = None

        # 3. Stream stdout, parse structured lines
        async for raw in proc.stdout:
            line = _ANSI_RE.sub("", raw.decode("utf-8", errors="replace").rstrip())
            if not line:
                continue

            if line.startswith("[STEP] "):
                yield {"step": "PS", "status": "ok", "msg": line[7:]}

            elif line.startswith("[DEVICE_CODE_1] ") or line.startswith("[DEVICE_CODE_2] "):
                # Format: [DEVICE_CODE_N] url=<url> code=<code>
                rest = line.split("] ", 1)[1]   # everything after "[DEVICE_CODE_N]"
                url  = ""
                code = ""
                for part in rest.split():
                    if part.startswith("url="):
                        url = part[4:]
                    elif part.startswith("code="):
                        code = part[5:]
                slot = "Microsoft 365" if "[DEVICE_CODE_1]" in line else "Azure"
                # Fire callback FIRST so the UI can show the code card before log lines
                if self.on_device_code and code and url:
                    self.on_device_code(code, url)
                yield {"step": "Auth", "status": "ok",
                       "msg": f"──────────────────────────────────────"}
                yield {"step": "Auth", "status": "ok",
                       "msg": f"  {slot} sign-in required"}
                yield {"step": "Auth", "status": "ok",
                       "msg": f"  1. Open:  {url}"}
                yield {"step": "Auth", "status": "ok",
                       "msg": f"  2. Enter: {code}"}
                yield {"step": "Auth", "status": "ok",
                       "msg": f"  Sign in as Global Admin, then wait here..."}
                yield {"step": "Auth", "status": "ok",
                       "msg": f"──────────────────────────────────────"}

            elif line.startswith("[RESULT] "):
                try:
                    result_json = json.loads(line[9:])
                except json.JSONDecodeError as e:
                    yield {"step": "Result", "status": "error", "msg": f"Failed to parse result JSON: {e}"}
                    return

            elif line.startswith("[ERROR] "):
                yield {"step": "PS", "status": "error", "msg": line[8:]}
                await proc.wait()
                return

            else:
                # Unexpected output — surface as info
                yield {"step": "PS", "status": "ok", "msg": line}

        await proc.wait()

        if proc.returncode != 0 and result_json is None:
            yield {"step": "Setup", "status": "error", "msg": f"Setup script exited with code {proc.returncode}"}
            return

        if result_json is None:
            yield {"step": "Setup", "status": "error", "msg": "Setup script completed but no result was returned"}
            return

        # 4. Persist config + secrets from PS result
        try:
            tenant_id = result_json["tenant_id"]
            config = {
                "CustomerName":   result_json["customer_name"],
                "PrimaryDomain":  result_json["primary_domain"],
                "InitialDomain":  result_json.get("initial_domain", ""),
                "TenantId":       tenant_id,
                "ClientId":       result_json["client_id"],
                "AppObjectId":    result_json["app_object_id"],
                "SubscriptionId": result_json.get("subscription_id", ""),
                "SetupDate":      datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "SecretExpiry":   result_json.get("secret_expiry", ""),
                "CertExpiry":     cert_expiry_iso,
            }
            save_config(config)
            store_secret(tenant_id, "client_secret", result_json["client_secret"])
            store_secret(tenant_id, "cert_password",  cert_password)
        except Exception as e:
            yield {"step": "Save", "status": "error", "msg": f"Failed to save config: {e}"}
            return

        yield {"step": "Save", "status": "ok", "msg": f"Configuration saved for {result_json['customer_name']}"}


# ── Certificate generation ────────────────────────────────────────────────────

def _generate_cert() -> tuple[str, str, str, bytes, str]:
    """
    Returns (cert_der_b64, cert_expiry_iso, cert_start_iso, pfx_bytes, password).
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    now    = datetime.datetime.now(datetime.timezone.utc)
    expiry = now + datetime.timedelta(days=730)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME,       AUDIT_APP_NAME),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MSP Audit"),
        x509.NameAttribute(NameOID.COUNTRY_NAME,      "NO"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(expiry)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False,   key_cert_sign=False,
                crl_sign=False,        encipher_only=False,
                decipher_only=False,
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    password = generate_cert_password()
    pfx_bytes = pkcs12.serialize_key_and_certificates(
        name=AUDIT_APP_NAME.encode(),
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
    )

    der_b64     = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()
    expiry_iso  = expiry.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_iso   = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    return der_b64, expiry_iso, start_iso, pfx_bytes, password
