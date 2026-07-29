"""Authentication manager for M365 + Azure + EXO (via PS helper)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from app.core.credentials import get_secret, load_cert_bytes
from app.core.pwsh import find_pwsh
from app.modules.m365_audit.httpx_credential import HttpxClientSecretCredential


class AuthError(Exception):
    pass


class AuthManager:
    """Holds all authenticated clients for one audit run."""

    def __init__(
        self,
        tenant_id:       str,
        client_id:       str,
        client_secret:   str,
        subscription_id: str,
        org_domain:      str,
        cert_path:       Path,
        cert_password:   str,
    ):
        self.tenant_id       = tenant_id
        self.client_id       = client_id
        self.client_secret   = client_secret
        self.subscription_id = subscription_id
        self.org_domain      = org_domain
        self.cert_path       = cert_path
        self.cert_password   = cert_password

        # Azure identity credential (async, httpx-based)
        self._credential: Optional[HttpxClientSecretCredential] = None

    @classmethod
    def from_config(cls) -> "AuthManager":
        """Build AuthManager from saved config + keyring secrets."""
        from app.core.credentials import load_config

        cfg = load_config()
        if not cfg:
            raise AuthError("No customer config found. Run setup first.")

        tenant_id = cfg["TenantId"]
        secret    = get_secret(tenant_id, "client_secret")
        cert_pwd  = get_secret(tenant_id, "cert_password")

        if not secret:
            raise AuthError(
                "Client secret not found in keyring. "
                "Re-run setup or choose 'Renew Credentials'."
            )
        if not cert_pwd:
            raise AuthError("Certificate password not found in keyring.")

        from app.core.credentials import cert_path
        return cls(
            tenant_id       = tenant_id,
            client_id       = cfg["ClientId"],
            client_secret   = secret,
            subscription_id = cfg.get("SubscriptionId", ""),
            org_domain      = cfg.get("PrimaryDomain", ""),
            cert_path       = cert_path(),
            cert_password   = cert_pwd,
        )

    @classmethod
    def from_gdap(cls, customer_tenant_id: str) -> "AuthManager":
        """Build AuthManager using GDAP partner credentials for a customer tenant.

        Uses the single partner app registration to access any GDAP-linked
        customer tenant.  No per-customer cert or secret needed.
        """
        partner_client = get_secret("gdap", "partner_client_id")
        partner_secret = get_secret("gdap", "partner_client_secret")

        if not partner_client or not partner_secret:
            raise AuthError(
                "GDAP partner credentials not configured. "
                "Go to Settings → GDAP to set up Partner Center integration."
            )

        return cls(
            tenant_id       = customer_tenant_id,
            client_id       = partner_client,
            client_secret   = partner_secret,
            subscription_id = "",
            org_domain      = "",
            cert_path       = Path(),
            cert_password   = "",
        )

    @classmethod
    def from_customer(cls, customer: dict, customer_cert_path: Path) -> "AuthManager":
        """Build AuthManager directly from a customer dict — no global state needed.

        This enables parallel audit execution for multiple customers.
        """
        tenant_id = customer.get("TenantId", "")
        client_id = customer.get("ClientId", "")
        if not tenant_id or not client_id:
            raise AuthError(f"Customer missing TenantId/ClientId")

        secret   = get_secret(tenant_id, "client_secret")
        cert_pwd = get_secret(tenant_id, "cert_password")

        if not secret:
            raise AuthError(f"Client secret not found for tenant {tenant_id}")
        if not cert_pwd:
            raise AuthError(f"Certificate password not found for tenant {tenant_id}")

        return cls(
            tenant_id       = tenant_id,
            client_id       = client_id,
            client_secret   = secret,
            subscription_id = customer.get("SubscriptionId", ""),
            org_domain      = customer.get("PrimaryDomain", ""),
            cert_path       = customer_cert_path,
            cert_password   = cert_pwd,
        )

    async def __aenter__(self) -> "AuthManager":
        self._credential = HttpxClientSecretCredential(
            tenant_id     = self.tenant_id,
            client_id     = self.client_id,
            client_secret = self.client_secret,
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._credential:
            await self._credential.close()

    @property
    def credential(self) -> HttpxClientSecretCredential:
        # Explicit raise rather than `assert` so the check survives `python -O`
        # (asserts are stripped). Without the check a missing context-manager
        # entry would surface as a confusing AttributeError on .get_token later.
        if self._credential is None:
            raise RuntimeError("AuthManager not entered as async context manager")
        return self._credential

    # ── Azure SDK clients ─────────────────────────────────────────────────────

    def _az_credential(self):
        from azure.identity import ClientSecretCredential as SyncCred
        return SyncCred(self.tenant_id, self.client_id, self.client_secret)

    def compute_client(self):
        from azure.mgmt.compute import ComputeManagementClient
        return ComputeManagementClient(self._az_credential(), self.subscription_id)

    def network_client(self):
        from azure.mgmt.network import NetworkManagementClient
        return NetworkManagementClient(self._az_credential(), self.subscription_id)

    def resource_client(self):
        from azure.mgmt.resource import ResourceManagementClient
        return ResourceManagementClient(self._az_credential(), self.subscription_id)

    def storage_client(self):
        from azure.mgmt.storage import StorageManagementClient
        return StorageManagementClient(self._az_credential(), self.subscription_id)

    def monitor_client(self):
        from azure.mgmt.monitor import MonitorManagementClient
        return MonitorManagementClient(self._az_credential(), self.subscription_id)

    def advisor_client(self):
        from azure.mgmt.advisor import AdvisorManagementClient
        return AdvisorManagementClient(self._az_credential(), self.subscription_id)

    def recovery_client(self):
        from azure.mgmt.recoveryservices import RecoveryServicesClient
        return RecoveryServicesClient(self._az_credential(), self.subscription_id)

    def log_analytics_client(self):
        from azure.mgmt.loganalytics import LogAnalyticsManagementClient
        return LogAnalyticsManagementClient(self._az_credential(), self.subscription_id)

    def avd_client(self):
        from azure.mgmt.desktopvirtualization import DesktopVirtualizationMgmtClient
        return DesktopVirtualizationMgmtClient(self._az_credential(), self.subscription_id)

    # ── Multi-subscription support ─────────────────────────────────────────────

    def list_subscriptions(self) -> list[dict]:
        """List all Azure subscriptions accessible by the service principal."""
        from azure.mgmt.resource.subscriptions import SubscriptionClient
        client = SubscriptionClient(self._az_credential())
        subs = []
        for sub in client.subscriptions.list():
            subs.append({
                "id": sub.subscription_id,
                "name": sub.display_name,
                "state": str(sub.state),
            })
        return subs

    def compute_client_for(self, sub_id: str):
        from azure.mgmt.compute import ComputeManagementClient
        return ComputeManagementClient(self._az_credential(), sub_id)

    def network_client_for(self, sub_id: str):
        from azure.mgmt.network import NetworkManagementClient
        return NetworkManagementClient(self._az_credential(), sub_id)

    def resource_client_for(self, sub_id: str):
        from azure.mgmt.resource import ResourceManagementClient
        return ResourceManagementClient(self._az_credential(), sub_id)

    def storage_client_for(self, sub_id: str):
        from azure.mgmt.storage import StorageManagementClient
        return StorageManagementClient(self._az_credential(), sub_id)

    def monitor_client_for(self, sub_id: str):
        from azure.mgmt.monitor import MonitorManagementClient
        return MonitorManagementClient(self._az_credential(), sub_id)

    def advisor_client_for(self, sub_id: str):
        from azure.mgmt.advisor import AdvisorManagementClient
        return AdvisorManagementClient(self._az_credential(), sub_id)

    def recovery_client_for(self, sub_id: str):
        from azure.mgmt.recoveryservices import RecoveryServicesClient
        return RecoveryServicesClient(self._az_credential(), sub_id)

    def log_analytics_client_for(self, sub_id: str):
        from azure.mgmt.loganalytics import LogAnalyticsManagementClient
        return LogAnalyticsManagementClient(self._az_credential(), sub_id)

    def avd_client_for(self, sub_id: str):
        from azure.mgmt.desktopvirtualization import DesktopVirtualizationMgmtClient
        return DesktopVirtualizationMgmtClient(self._az_credential(), sub_id)

    # ── EXO via PowerShell helper ─────────────────────────────────────────────

    async def collect_exo_data(self, out_dir: Path) -> dict:
        """Run the PowerShell EXO helper and return parsed JSON output."""
        # GDAP customers have no per-customer cert — EXO requires cert-based auth
        if not self.cert_path or not str(self.cert_path) or not self.cert_password:
            return {"skipped": True, "error": "EXO data not available via GDAP — requires per-customer certificate"}

        helper = Path(__file__).parent.parent.parent / "helpers" / "exo_collector.ps1"
        if not helper.exists():
            return {"error": "EXO helper script not found"}

        config_payload = json.dumps({
            "TenantId":     self.tenant_id,
            "ClientId":     self.client_id,
            "CertPath":     str(self.cert_path),
            "CertPassword": self.cert_password,
            "OrgDomain":    self.org_domain,
            "OutDir":       str(out_dir),
        })

        ps_exe = find_pwsh()
        if not ps_exe:
            return {"error": "PowerShell 7 (pwsh) not found — Exchange data skipped"}

        proc = await asyncio.create_subprocess_exec(
            ps_exe, "-NonInteractive", "-NoProfile", "-File", str(helper),
            stdin  = asyncio.subprocess.PIPE,
            stdout = asyncio.subprocess.PIPE,
            stderr = asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=config_payload.encode()),
                timeout=300
            )
        except asyncio.TimeoutError:
            proc.kill()
            return {"error": "EXO helper timed out after 5 minutes"}

        if proc.returncode != 0:
            # The helper writes its real failure reason as JSON on stdout
            # (e.g. {"error":"Certificate not found: ..."} or a Connect-
            # ExchangeOnline auth error). stderr is usually empty, so reading
            # it alone produced the useless "EXO helper exited 1:" with no
            # detail. Prefer the stdout reason.
            detail = ""
            try:
                detail = (json.loads(stdout.decode() or "{}") or {}).get("error", "")
            except json.JSONDecodeError:
                detail = stdout.decode()[:500].strip()
            if not detail:
                detail = stderr.decode()[:500].strip() or "(no output captured)"
            return {"error": f"EXO helper exited {proc.returncode}: {detail}"}

        try:
            return json.loads(stdout.decode())
        except json.JSONDecodeError:
            return {"error": "EXO helper returned invalid JSON", "raw": stdout.decode()[:500]}


# ── Helper: pick auth mode per customer ──────────────────────────────────────

def get_auth_for_customer(customer: dict, cert_path: Path) -> AuthManager:
    """Return the right AuthManager based on customer's AuthMode setting."""
    if customer.get("AuthMode") == "gdap":
        return AuthManager.from_gdap(customer["TenantId"])
    return AuthManager.from_customer(customer, cert_path)


