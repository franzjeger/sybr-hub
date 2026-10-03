import base64
import hashlib
import logging
import secrets
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Azure CLI Client ID - a first-party Microsoft application we "borrow"
# to bootstrap our own application registration.
AZURE_CLI_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
DEFAULT_SCOPE = "Application.ReadWrite.All Directory.AccessAsUser.All openid profile offline_access"

# In-memory store for PKCE state -> (verifier, expires_at)
_pkce_store = {}


def generate_pkce_challenge() -> tuple[str, str, str]:
    """Generates (state, code_verifier, code_challenge)"""
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode("ascii").rstrip("=")

    # Store verifier for 10 minutes
    _pkce_store[state] = (code_verifier, time.time() + 600)
    return state, code_verifier, code_challenge


async def exchange_code_for_token(code: str, state: str, redirect_uri: str) -> str:
    """Exchanges the authorization code for an access token."""
    entry = _pkce_store.pop(state, None)
    if not entry or entry[1] < time.time():
        raise ValueError("Invalid or expired state parameter")
    code_verifier = entry[0]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "client_id": AZURE_CLI_CLIENT_ID,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
                "scope": DEFAULT_SCOPE,
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def create_sybr_app(access_token: str) -> dict[str, Any]:
    from app.core.config import AUDIT_APP_NAME, REQUIRED_GRAPH_PERMISSIONS

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        # 0. Get Microsoft Graph Service Principal
        mg_sp_resp = await client.get(
            "https://graph.microsoft.com/v1.0/servicePrincipals?$filter=appId eq '00000003-0000-0000-c000-000000000000'",
            headers=headers,
        )
        mg_sp_resp.raise_for_status()
        mg_sp_data = mg_sp_resp.json()["value"][0]
        mg_sp_id = mg_sp_data["id"]

        role_map = {r["value"]: r["id"] for r in mg_sp_data.get("appRoles", [])}
        required_roles = [
            *list(REQUIRED_GRAPH_PERMISSIONS),
            "Policy.ReadWrite.ConditionalAccess",
            "DeviceManagementConfiguration.ReadWrite.All",
            "RoleManagement.ReadWrite.Directory",
        ]

        role_access_list = []
        role_ids_to_grant = []
        for role_name in set(required_roles):
            if role_name in role_map:
                role_ids_to_grant.append(role_map[role_name])
                role_access_list.append({"id": role_map[role_name], "type": "Role"})

        # 1. Create Application
        app_resp = await client.post(
            "https://graph.microsoft.com/v1.0/applications",
            headers=headers,
            json={
                "displayName": AUDIT_APP_NAME,
                "signInAudience": "AzureADMultipleOrgs",
                "requiredResourceAccess": [
                    {
                        "resourceAppId": "00000003-0000-0000-c000-000000000000",
                        "resourceAccess": role_access_list,
                    }
                ],
            },
        )
        app_resp.raise_for_status()
        app_data = app_resp.json()
        app_id = app_data["appId"]
        object_id = app_data["id"]

        # Generate Certificate
        import uuid

        from app.modules.m365_audit.setup import _generate_cert

        cert_der_b64, cert_expiry_iso, cert_start_iso, pfx_bytes, cert_password = _generate_cert()

        # 2. Add Key Credential (Certificate) using PATCH
        patch_resp = await client.patch(
            f"https://graph.microsoft.com/v1.0/applications/{object_id}",
            headers=headers,
            json={
                "keyCredentials": [
                    {
                        "type": "AsymmetricX509Cert",
                        "usage": "Verify",
                        "keyId": str(uuid.uuid4()),
                        "key": cert_der_b64,
                        "endDateTime": cert_expiry_iso,
                        "startDateTime": cert_start_iso,
                        "displayName": "Sybr HUB Setup Cert",
                    }
                ]
            },
        )
        try:
            patch_resp.raise_for_status()
        except Exception:
            logging.error(f"PATCH failed: {patch_resp.text}")
            raise

        # Also add a Client Secret just in case for non-cert flows
        pwd_resp = await client.post(
            f"https://graph.microsoft.com/v1.0/applications/{object_id}/addPassword",
            headers=headers,
            json={"passwordCredential": {"displayName": "Sybr HUB Setup Secret"}},
        )
        pwd_resp.raise_for_status()
        secret = pwd_resp.json()["secretText"]

        # 3. Create Service Principal
        import asyncio

        sp_resp = await client.post(
            "https://graph.microsoft.com/v1.0/servicePrincipals",
            headers=headers,
            json={"appId": app_id},
        )
        sp_resp.raise_for_status()
        my_sp_id = sp_resp.json()["id"]

        await asyncio.sleep(3)

        # 4. Grant Admin Consent via appRoleAssignments
        for r_id in role_ids_to_grant:
            await client.post(
                f"https://graph.microsoft.com/v1.0/servicePrincipals/{my_sp_id}/appRoleAssignments",
                headers=headers,
                json={"principalId": my_sp_id, "resourceId": mg_sp_id, "appRoleId": r_id},
            )

        org_resp = await client.get(
            "https://graph.microsoft.com/v1.0/organization", headers=headers
        )
        org_resp.raise_for_status()
        org_data = org_resp.json()["value"][0]
        tenant_id = org_data["id"]
        customer_name = org_data.get("displayName", "Ukjent Kunde")

        domains = org_data.get("verifiedDomains", [])
        primary_domain = next((d["name"] for d in domains if d.get("isDefault")), None)
        if not primary_domain and domains:
            primary_domain = domains[0]["name"]

        # Save PFX to disk
        from app.core.credentials import global_cert_path
        from app.core.encryption import encrypted_write_bytes

        encrypted_write_bytes(global_cert_path(), pfx_bytes)

        return {
            "CustomerName": customer_name,
            "PrimaryDomain": primary_domain,
            "TenantId": tenant_id,
            "ClientId": app_id,
            "ClientSecret": secret,
            "CertPassword": cert_password,
            "SecretExpiry": cert_expiry_iso,
            "CertExpiry": cert_expiry_iso,
            "AuthMode": "csp",
        }
