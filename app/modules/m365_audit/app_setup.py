"""Provision the per-tenant audit app and verify consent before reporting success.

Only an app ID already stored locally for this tenant is reused. An encrypted
checkpoint keeps interrupted setup resumable without creating another app or
discarding the customer's current credentials.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import pkcs12

from app.core.config import (
    AUDIT_APP_NAME,
    DATA_DIR,
    EXO_APP_ID,
    EXO_PERMISSION,
    REQUIRED_GRAPH_PERMISSIONS,
)
from app.core.encryption import (
    encrypted_read_bytes,
    encrypted_read_json,
    encrypted_write_bytes,
    encrypted_write_json,
)
from app.modules.m365_audit.pkce import PkceSetupError

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"
EOP_APP_ID = "00000007-0000-0ff1-ce00-000000000000"
EXCHANGE_ADMIN_TEMPLATE = "29232cdf-9323-42fd-ade2-1d097af3e4de"
GLOBAL_READER_TEMPLATE = "f2ef992c-3afb-46b9-b7cf-a126ee74c451"
DIRECTORY_ROLES = {
    "Exchange Online": (EXCHANGE_ADMIN_TEMPLATE, "Exchange Administrator"),
    "Purview": (GLOBAL_READER_TEMPLATE, "Global Reader"),
}
GRAPH_ROLES = sorted(
    set(REQUIRED_GRAPH_PERMISSIONS)
    | {
        "Policy.ReadWrite.ConditionalAccess",
        "DeviceManagementConfiguration.ReadWrite.All",
        "RoleManagement.ReadWrite.Directory",
    }
)
RESOURCES = (
    (GRAPH_APP_ID, "Graph", GRAPH_ROLES, "https://graph.microsoft.com/.default"),
    (EXO_APP_ID, "Exchange Online", [EXO_PERMISSION], "https://outlook.office365.com/.default"),
    (
        EOP_APP_ID,
        "Purview",
        [EXO_PERMISSION],
        "https://ps.compliance.protection.outlook.com/.default",
    ),
)
READINESS_SECONDS = 120
log = logging.getLogger(__name__)
_setup_lock = asyncio.Lock()


def _pending_path(tenant_id: str) -> Path:
    # Microsoft supplies this ID, but it still must not become an arbitrary path.
    return DATA_DIR / "setup_pending" / f"{uuid.UUID(tenant_id)}.enc"


def _known_config(tenant_id: str, allowed_customer_ids: set[str] | None = None) -> dict | None:
    from app.core.credentials import load_global_config
    from app.core.customer import CustomerManager

    configs = CustomerManager.list_customers()
    if allowed_customer_ids is not None and any(
        c.get("TenantId") == tenant_id and c.get("_id") not in allowed_customer_ids for c in configs
    ):
        raise PkceSetupError("err_setup_customer_access", 403, restart_required=True)
    global_config = load_global_config()
    if global_config:
        configs.append(global_config)
    ids = {c["ClientId"] for c in configs if c.get("TenantId") == tenant_id and c.get("ClientId")}
    if len(ids) > 1:
        # Picking a name match would silently repair a potentially unrelated app.
        raise ValueError("Multiple saved application IDs for this tenant")
    return next(
        (dict(c) for c in configs if c.get("TenantId") == tenant_id and c.get("ClientId")), None
    )


def _existing_credentials(saved: dict) -> dict:
    """Permission repair does not need to rotate a still-valid credential pair."""
    from app.core.credentials import get_secret, global_cert_path
    from app.core.customer import CustomerManager

    try:
        for field in ("CertExpiry", "SecretExpiry"):
            if datetime.fromisoformat(saved[field].replace("Z", "+00:00")) <= datetime.now(UTC):
                return {}
    except (KeyError, TypeError, ValueError):
        return {}
    tenant_id = saved["TenantId"]
    secret = get_secret(tenant_id, "client_secret")
    password = get_secret(tenant_id, "cert_password")
    customer_id = saved.get("CustomerId") or saved.get("_id")
    path = CustomerManager.get_cert_path(customer_id) if customer_id else global_cert_path()
    if not secret or not password or not path.exists():
        return {}
    config = {k: v for k, v in saved.items() if not k.startswith("_")}
    config.update(ClientSecret=secret, CertPassword=password)
    return {"Config": config, "Pfx": base64.b64encode(encrypted_read_bytes(path)).decode("ascii")}


async def _request(client: httpx.AsyncClient, method: str, path: str, step: str, **kwargs) -> Any:
    response = await client.request(method, GRAPH + path, **kwargs)
    if not response.is_success:
        log.error("Setup step %s refused: HTTP %s", step, response.status_code)
        raise PkceSetupError(
            "err_setup_grant",
            502,
            restart_required=True,
            step=step,
            http_status=str(response.status_code),
        )
    return response.json() if response.content else {}


async def _values(client: httpx.AsyncClient, path: str, step: str) -> list[dict]:
    """Read every page; existing consent must not be mistaken for missing consent."""
    rows: list[dict] = []
    while path:
        data = await _request(client, "GET", path, step)
        rows.extend(data["value"])
        next_url = data.get("@odata.nextLink", "")
        if next_url and not next_url.startswith(GRAPH + "/"):
            raise ValueError("Unexpected Graph pagination host")
        path = next_url.removeprefix(GRAPH) if next_url else ""
    return rows


def _claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def _certificate_assertion(config: dict, pfx: bytes, token_url: str) -> str:
    key, certificate, _ = pkcs12.load_key_and_certificates(pfx, config["CertPassword"].encode())
    if key is None or certificate is None:
        raise ValueError("Missing setup certificate or private key")
    now = int(time.time())
    thumbprint = (
        base64.urlsafe_b64encode(certificate.fingerprint(hashes.SHA256())).decode().rstrip("=")
    )
    return jwt.encode(
        {
            "aud": token_url,
            "iss": config["ClientId"],
            "sub": config["ClientId"],
            "jti": str(uuid.uuid4()),
            "nbf": now,
            "iat": now,
            "exp": now + 300,
        },
        key,
        algorithm="PS256",
        headers={"x5t#S256": thumbprint},
    )


async def _wait_ready(config: dict, client: httpx.AsyncClient, pfx: bytes) -> None:
    """Inspect fresh tokens on every attempt, then make a real Graph read.

    These claims are diagnostic data from Microsoft's TLS token endpoint, never
    an authorization decision for a local user. No incomplete token is cached.
    """
    deadline = time.monotonic() + READINESS_SECONDS
    while True:
        missing = []
        graph_token = ""
        for _, service, roles, scope in RESOURCES:
            try:
                token_url = (
                    f"https://login.microsoftonline.com/{config['TenantId']}/oauth2/v2.0/token"
                )
                credentials = (
                    {"client_secret": config["ClientSecret"]}
                    if service == "Graph"
                    else {
                        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                        "client_assertion": _certificate_assertion(config, pfx, token_url),
                    }
                )
                response = await client.post(
                    token_url,
                    headers={"Authorization": ""},
                    timeout=min(30, max(0.1, deadline - time.monotonic())),
                    data={
                        "grant_type": "client_credentials",
                        "client_id": config["ClientId"],
                        **credentials,
                        "scope": scope,
                    },
                )
                if not response.is_success:
                    missing.append(f"{service}: HTTP {response.status_code}")
                    continue
                token = response.json()["access_token"]
                claims = _claims(token)
                missing.extend(
                    f"{service}: {role}" for role in roles if role not in claims.get("roles", [])
                )
                if service in DIRECTORY_ROLES:
                    template, role_name = DIRECTORY_ROLES[service]
                    if template not in claims.get("wids", []):
                        missing.append(f"{service}: {role_name}")
                if service == "Graph":
                    graph_token = token
            except (httpx.RequestError, ValueError, KeyError, IndexError, TypeError):
                missing.append(f"{service}: token unavailable")
        if not missing:
            try:
                probe = await client.get(
                    GRAPH + "/organization",
                    headers={"Authorization": f"Bearer {graph_token}"},
                    timeout=min(30, max(0.1, deadline - time.monotonic())),
                )
                organizations = probe.json().get("value", []) if probe.is_success else []
                if any(org.get("id") == config["TenantId"] for org in organizations):
                    return
                missing.append(f"Graph organization: HTTP {probe.status_code}")
            except (httpx.RequestError, ValueError):
                missing.append("Graph organization unavailable")
        if time.monotonic() >= deadline:
            raise PkceSetupError(
                "err_setup_permissions_pending",
                503,
                restart_required=True,
                missing=", ".join(missing),
            )
        log.info("Waiting for Microsoft permission propagation: %s", ", ".join(missing))
        await asyncio.sleep(min(5, max(0, deadline - time.monotonic())))


async def provision_app(
    access_token: str,
    *,
    allowed_customer_ids: set[str] | None = None,
    renew_config: dict | None = None,
) -> dict[str, Any]:
    # Staging config/cert is shared. Serialize the entire setup, not just writes.
    async with (
        _setup_lock,
        httpx.AsyncClient(
            timeout=30, headers={"Authorization": f"Bearer {access_token}"}
        ) as client,
    ):
        org = (await _values(client, "/organization", "organization"))[0]
        tenant_id = org["id"]
        if renew_config and renew_config.get("TenantId") != tenant_id:
            raise PkceSetupError("err_setup_renew_tenant", 400, restart_required=True)
        checkpoint = _pending_path(tenant_id)
        pending = encrypted_read_json(checkpoint) if checkpoint.exists() else {}
        if pending and pending.get("TenantId") != tenant_id:
            raise ValueError("Setup checkpoint belongs to a different tenant")

        saved = _known_config(tenant_id, allowed_customer_ids)
        if renew_config:
            saved = renew_config
        if (
            renew_config
            and pending.get("ClientId")
            and pending["ClientId"] != renew_config.get("ClientId")
        ):
            raise ValueError("Pending app differs from renewal target")
        if renew_config and not pending.get("Renew"):
            pending.pop("Config", None)
            pending.pop("Pfx", None)
            pending["Renew"] = True

        resources = []
        manifest = []
        for resource_id, service, roles, _ in RESOURCES:
            principals = await _values(
                client, f"/servicePrincipals?$filter=appId eq '{resource_id}'", service
            )
            if len(principals) != 1:
                raise PkceSetupError(
                    "err_setup_grant",
                    502,
                    restart_required=True,
                    step=service,
                    http_status="resource unavailable",
                )
            principal = principals[0]
            role_map = {
                r["value"]: r["id"]
                for r in principal.get("appRoles", [])
                if r.get("isEnabled") and "Application" in r.get("allowedMemberTypes", [])
            }
            if any(role not in role_map for role in roles):
                raise PkceSetupError(
                    "err_setup_grant",
                    502,
                    restart_required=True,
                    step=service,
                    http_status="permission unavailable",
                )
            role_ids = [role_map[role] for role in roles]
            resources.append((principal["id"], service, role_ids))
            manifest.append(
                {
                    "resourceAppId": resource_id,
                    "resourceAccess": [{"id": rid, "type": "Role"} for rid in role_ids],
                }
            )

        app_id = pending.get("ClientId") or (saved or {}).get("ClientId")
        if app_id:
            app = await _request(
                client, "GET", f"/applications(appId='{uuid.UUID(app_id)}')", "saved application"
            )
            if app["appId"] != app_id:
                raise ValueError("Saved application identity mismatch")
            # Preserve additional permissions and existing certificates on repair.
            merged = {
                r["resourceAppId"]: r["resourceAccess"]
                for r in app.get("requiredResourceAccess", [])
            }
            for resource in manifest:
                entries = merged.setdefault(resource["resourceAppId"], [])
                for permission in resource["resourceAccess"]:
                    if permission not in entries:
                        entries.append(permission)
            await _request(
                client,
                "PATCH",
                f"/applications/{app['id']}",
                "application permissions",
                json={
                    "requiredResourceAccess": [
                        {"resourceAppId": rid, "resourceAccess": entries}
                        for rid, entries in merged.items()
                    ]
                },
            )
        else:
            app = await _request(
                client,
                "POST",
                "/applications",
                "application registration",
                json={
                    "displayName": AUDIT_APP_NAME,
                    "signInAudience": "AzureADMultipleOrgs",
                    "requiredResourceAccess": manifest,
                },
            )
        app_id = app["appId"]
        pending.update(TenantId=tenant_id, ClientId=app_id, AppObjectId=app["id"])
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        encrypted_write_json(checkpoint, pending)

        principals = await _values(
            client,
            f"/servicePrincipals?$filter=appId eq '{uuid.UUID(app_id)}'",
            "application identity",
        )
        principal = (
            principals[0]
            if principals
            else await _request(
                client, "POST", "/servicePrincipals", "application identity", json={"appId": app_id}
            )
        )
        principal_id = principal["id"]
        assigned = {
            (a["resourceId"], a["appRoleId"])
            for a in await _values(
                client, f"/servicePrincipals/{principal_id}/appRoleAssignments", "existing consent"
            )
        }
        for resource_id, service, role_ids in resources:
            for role_id in role_ids:
                if (resource_id, role_id) not in assigned:
                    await _request(
                        client,
                        "POST",
                        f"/servicePrincipals/{principal_id}/appRoleAssignments",
                        f"{service} admin consent",
                        json={
                            "principalId": principal_id,
                            "resourceId": resource_id,
                            "appRoleId": role_id,
                        },
                    )

        assignments = await _values(
            client,
            f"/roleManagement/directory/roleAssignments?$filter=principalId eq '{principal_id}'",
            "existing directory roles",
        )
        for template_id, role_name in DIRECTORY_ROLES.values():
            definitions = await _values(
                client,
                f"/roleManagement/directory/roleDefinitions?$filter=templateId eq '{template_id}'",
                f"{role_name} definition",
            )
            definition_id = definitions[0]["id"]
            if not any(
                a.get("roleDefinitionId") == definition_id and a.get("directoryScopeId") == "/"
                for a in assignments
            ):
                await _request(
                    client,
                    "POST",
                    "/roleManagement/directory/roleAssignments",
                    role_name,
                    json={
                        "principalId": principal_id,
                        "roleDefinitionId": definition_id,
                        "directoryScopeId": "/",
                    },
                )

        if (
            "Config" not in pending
            and not pending.get("Renew")
            and saved
            and saved.get("ClientId") == app_id
        ):
            pending.update(_existing_credentials(saved))
            encrypted_write_json(checkpoint, pending)

        if "Config" not in pending:
            from app.modules.m365_audit.setup import _generate_cert

            key, expiry, start, pfx, password = _generate_cert()
            # Always select public key material; a default application response
            # can omit keyCredentials entirely, including existing certificates.
            app_keys = await _request(
                client,
                "GET",
                f"/applications/{app['id']}?$select=keyCredentials",
                "existing certificates",
            )
            keys = list(app_keys["keyCredentials"])
            keys.append(
                {
                    "type": "AsymmetricX509Cert",
                    "usage": "Verify",
                    "keyId": str(uuid.uuid4()),
                    "key": key,
                    "endDateTime": expiry,
                    "startDateTime": start,
                    "displayName": "Sybr HUB Setup Cert",
                }
            )
            await _request(
                client,
                "PATCH",
                f"/applications/{app['id']}",
                "certificate",
                json={"keyCredentials": keys},
            )
            secret = await _request(
                client,
                "POST",
                f"/applications/{app['id']}/addPassword",
                "client secret",
                json={
                    "passwordCredential": {
                        "displayName": "Sybr HUB Setup Secret",
                        "endDateTime": expiry,
                    }
                },
            )
            domains = org.get("verifiedDomains", [])
            default = next(
                (d["name"] for d in domains if d.get("isDefault")),
                domains[0]["name"] if domains else "",
            )
            initial = next((d["name"] for d in domains if d.get("isInitial")), "")
            pending.update(
                Config={
                    **{k: v for k, v in (saved or {}).items() if not k.startswith("_")},
                    "CustomerName": (saved or {}).get("CustomerName")
                    or org.get("displayName", "Customer"),
                    "PrimaryDomain": default,
                    "InitialDomain": initial,
                    "TenantId": tenant_id,
                    "ClientId": app_id,
                    "AppObjectId": app["id"],
                    "ClientSecret": secret["secretText"],
                    "CertPassword": password,
                    "CertExpiry": expiry,
                    "SecretExpiry": secret["endDateTime"],
                    "AuthMode": "csp",
                },
                Pfx=base64.b64encode(pfx).decode("ascii"),
            )
            encrypted_write_json(checkpoint, pending)

        config = pending["Config"]
        config["AppObjectId"] = app["id"]
        pfx = base64.b64decode(pending["Pfx"])
        await _wait_ready(config, client, pfx)
        from app.core.credentials import global_cert_path

        encrypted_write_bytes(global_cert_path(), pfx)
        return dict(config)


def finish_setup(tenant_id: str) -> None:
    """Drop the checkpoint only after config and credentials were persisted."""
    _pending_path(tenant_id).unlink(missing_ok=True)
