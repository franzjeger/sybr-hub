"""Lightweight async Microsoft Graph API client (httpx-based).

Uses azure-identity for token acquisition — no heavy Graph SDK required.
Handles automatic pagination, retries, and both v1.0 and beta endpoints.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx
from azure.core.credentials_async import AsyncTokenCredential

log = logging.getLogger(__name__)

_GRAPH_V1   = "https://graph.microsoft.com/v1.0"
_GRAPH_BETA = "https://graph.microsoft.com/beta"
_SCOPE      = "https://graph.microsoft.com/.default"


class GraphClient:
    """Async Graph API client. Use as an async context manager."""

    def __init__(self, credential: AsyncTokenCredential, timeout: int = 120):
        self._credential = credential
        self._timeout    = timeout
        self._http: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "GraphClient":
        self._http = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_) -> None:
        if self._http:
            await self._http.aclose()

    # ── Token ─────────────────────────────────────────────────────────────────

    async def _headers(self) -> dict[str, str]:
        token = await self._credential.get_token(_SCOPE)
        return {
            "Authorization": f"Bearer {token.token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    # ── Core HTTP ─────────────────────────────────────────────────────────────

    async def _get(self, url: str, params: dict | None = None, extra_headers: dict | None = None) -> dict:
        if self._http is None:
            raise RuntimeError("GraphClient is not entered — use as async context manager")
        last_status = None
        for attempt in range(3):
            try:
                hdrs = await self._headers()
                if extra_headers:
                    hdrs.update(extra_headers)
                resp = await self._http.get(url, headers=hdrs, params=params)
                last_status = resp.status_code
                if resp.status_code == 429:          # throttled
                    retry_after = resp.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after else min(2 ** attempt, 30)
                    log.warning("Graph throttled — waiting %ds", wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code in (401, 403):
                    return {"error": resp.status_code, "detail": resp.text}
                resp.raise_for_status()
                return resp.json()
            except httpx.TimeoutException:
                if attempt == 2:
                    raise
                await asyncio.sleep(min(2 ** attempt, 30))
        # Loop exhausted without a successful response — only reachable when
        # every attempt returned 429. Raise instead of returning {} so the
        # caller can't mistake "throttled out" for "no data".
        raise httpx.HTTPError(
            f"Graph request to {url} failed after 3 attempts "
            f"(last status: {last_status})"
        )

    async def get(self, path: str, *, beta: bool = False, params: dict | None = None, extra_headers: dict | None = None) -> dict:
        base = _GRAPH_BETA if beta else _GRAPH_V1
        url  = f"{base}/{path.lstrip('/')}"
        return await self._get(url, params=params, extra_headers=extra_headers)

    async def get_all(
        self,
        path: str,
        *,
        beta: bool = False,
        params: dict | None = None,
        key: str = "value",
        extra_headers: dict | None = None,
    ) -> list[Any]:
        """Fetch all pages and return combined list."""
        base  = _GRAPH_BETA if beta else _GRAPH_V1
        url   = f"{base}/{path.lstrip('/')}"
        items: list[Any] = []

        page_count = 0
        max_pages = 500
        while url and page_count < max_pages:
            data = await self._get(url, params=params, extra_headers=extra_headers)
            params = None                             # params only on first request
            items.extend(data.get(key, []))
            url = data.get("@odata.nextLink", "")
            page_count += 1

        if page_count >= max_pages:
            log.warning(
                "get_all(%s) hit max page limit (%d pages, %d items) — results may be incomplete",
                path, max_pages, len(items),
            )

        return items

    async def post(self, path: str, body: dict, *, beta: bool = False) -> dict:
        if self._http is None:
            raise RuntimeError("GraphClient is not entered — use as async context manager")
        base = _GRAPH_BETA if beta else _GRAPH_V1
        url  = f"{base}/{path.lstrip('/')}"
        resp = await self._http.post(url, headers=await self._headers(), json=body)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def patch(self, path: str, body: dict, *, beta: bool = False) -> None:
        if self._http is None:
            raise RuntimeError("GraphClient is not entered — use as async context manager")
        base = _GRAPH_BETA if beta else _GRAPH_V1
        url  = f"{base}/{path.lstrip('/')}"
        resp = await self._http.patch(url, headers=await self._headers(), json=body)
        resp.raise_for_status()

    async def delete(self, path: str, *, beta: bool = False) -> None:
        if self._http is None:
            raise RuntimeError("GraphClient is not entered — use as async context manager")
        base = _GRAPH_BETA if beta else _GRAPH_V1
        url  = f"{base}/{path.lstrip('/')}"
        resp = await self._http.delete(url, headers=await self._headers())
        resp.raise_for_status()

    # ── Permission validation ──────────────────────────────────────────────────

    # The canonical list of Graph application permissions the audit requires.
    # Sourced from setup_helper.ps1 — keep in sync.
    REQUIRED_PERMISSIONS: list[str] = [
        "AuditLog.Read.All",
        "Application.Read.All",
        "DeviceManagementApps.Read.All",
        "DeviceManagementConfiguration.Read.All",
        "DeviceManagementManagedDevices.Read.All",
        "DeviceManagementServiceConfig.Read.All",
        "Directory.Read.All",
        "Group.Read.All",
        "IdentityRiskyUser.Read.All",
        "Organization.Read.All",
        "Policy.Read.All",
        "RoleManagement.Read.Directory",
        "SecurityEvents.Read.All",
        "Sites.Read.All",
        "SharePointTenantSettings.Read.All",
        "User.Read.All",
        "UserAuthenticationMethod.Read.All",
        "PrivilegedAssignmentSchedule.Read.AzureADGroup",
        "InformationProtectionPolicy.Read.All",
        "AccessReview.Read.All",
        "SecurityAlert.Read.All",
    ]

    # Permissions that merely degrade results (non-critical).
    _WARN_ONLY_PERMISSIONS: set[str] = {
        "PrivilegedAssignmentSchedule.Read.AzureADGroup",
        "InformationProtectionPolicy.Read.All",
        "AccessReview.Read.All",
        "SecurityAlert.Read.All",
    }

    async def validate_permissions(self) -> dict[str, Any]:
        """Check Graph connectivity and compare granted app-role permissions
        against the required set.

        Returns dict with keys: ok, granted, missing, warnings, connectivity.
        """
        result: dict[str, Any] = {
            "ok": False,
            "connectivity": False,
            "granted": [],
            "missing": [],
            "warnings": [],
        }

        # 1. Connectivity check — call /organization
        try:
            org = await self.get("/organization", params={"$top": "1"})
            if "error" in org:
                result["warnings"].append(
                    f"Tilkoblingstest feilet: HTTP {org.get('error')} — {org.get('detail', '')[:200]}"
                )
                return result
            result["connectivity"] = True
        except Exception as exc:
            result["warnings"].append(f"Tilkoblingstest feilet: {exc}")
            return result

        # 2. Discover the service principal for our app and its appRoleAssignments
        #    We read the SP object-id from /me (which won't work for app-only),
        #    so instead we look up our own appId via the token's 'appid' claim
        #    by listing appRoleAssignments on the SP matching our client_id.
        granted_values: set[str] = set()
        try:
            # Get the token to extract appid
            token_obj = await self._credential.get_token(_SCOPE)
            import base64
            import json as _json
            # Decode JWT payload (no verification needed, just reading claims)
            payload_b64 = token_obj.token.split(".")[1]
            # Fix padding
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            claims = _json.loads(base64.urlsafe_b64decode(payload_b64))
            app_id = claims.get("appid") or claims.get("azp", "")

            if not app_id:
                result["warnings"].append("Kunne ikke bestemme appId fra token.")
                return result

            # Look up the service principal
            sp_data = await self.get(
                "/servicePrincipals",
                params={"$filter": f"appId eq '{app_id}'", "$select": "id"},
            )
            sp_list = sp_data.get("value", [])
            if not sp_list:
                result["warnings"].append("Fant ikke service principal for appen.")
                return result
            sp_id = sp_list[0]["id"]

            # Fetch granted appRoleAssignments
            assignments = await self.get_all(
                f"/servicePrincipals/{sp_id}/appRoleAssignments",
                params={"$select": "appRoleId,resourceId,resourceDisplayName"},
            )

            # We need to map appRoleId -> permission value name.
            # Collect all unique resourceIds (should be Microsoft Graph SP).
            resource_ids = {a.get("resourceId") for a in assignments if a.get("resourceId")}
            role_id_to_value: dict[str, str] = {}
            for rid in resource_ids:
                try:
                    res_sp = await self.get(
                        f"/servicePrincipals/{rid}",
                        params={"$select": "appRoles"},
                    )
                    for role in res_sp.get("appRoles", []):
                        role_id_to_value[role["id"]] = role["value"]
                except Exception:
                    pass

            for a in assignments:
                role_value = role_id_to_value.get(a.get("appRoleId", ""), "")
                if role_value:
                    granted_values.add(role_value)

        except Exception as exc:
            result["warnings"].append(f"Kunne ikke hente tillatelser: {exc}")
            return result

        # 3. Compare
        granted: list[str] = []
        missing: list[str] = []
        warnings: list[str] = list(result["warnings"])  # keep any earlier warnings

        for perm in self.REQUIRED_PERMISSIONS:
            if perm in granted_values:
                granted.append(perm)
            elif perm in self._WARN_ONLY_PERMISSIONS:
                warnings.append(f"{perm} — mangler, kan gi ufullstendige resultater")
                missing.append(perm)
            else:
                missing.append(perm)

        critical_missing = [p for p in missing if p not in self._WARN_ONLY_PERMISSIONS]
        result["ok"] = len(critical_missing) == 0
        result["granted"] = sorted(granted)
        result["missing"] = sorted(missing)
        result["warnings"] = warnings
        return result

    async def validate_gdap_access(self) -> dict[str, Any]:
        """Validate GDAP delegated access by probing key Graph endpoints.

        GDAP uses Azure AD role assignments (Global Reader, Security Reader)
        rather than app-role permissions, so we probe endpoints directly
        instead of inspecting appRoleAssignments.
        """
        result: dict[str, Any] = {
            "ok": False,
            "connectivity": False,
            "accessible": [],
            "warnings": [],
        }

        # 1. Connectivity — /organization
        try:
            org = await self.get("/organization", params={"$top": "1"})
            if "error" in org:
                result["warnings"].append(
                    f"Tilkoblingstest feilet: {org.get('detail', '')[:200]}"
                )
                return result
            result["connectivity"] = True
            orgs = org.get("value", [])
            if orgs:
                result["tenant_name"] = orgs[0].get("displayName", "")
        except Exception as exc:
            result["warnings"].append(f"Tilkoblingstest feilet: {exc}")
            return result

        # 2. Probe key endpoints to confirm GDAP role grants
        probes = [
            ("/users", {"$top": "1", "$select": "id"}, "Users (Directory.Read.All)"),
            ("/security/secureScores", {"$top": "1"}, "Secure Score (SecurityEvents.Read.All)"),
            ("/policies/conditionalAccessPolicies", {"$top": "1"}, "Conditional Access (Policy.Read.All)"),
            ("/deviceManagement/managedDevices", {"$top": "1", "$select": "id"}, "Intune (DeviceManagement)"),
            ("/identityGovernance/accessReviews/definitions", {"$top": "1"}, "Access Reviews"),
        ]
        for path, params, label in probes:
            try:
                data = await self.get(path, params=params)
                if "error" not in data:
                    result["accessible"].append(label)
                else:
                    result["warnings"].append(f"Ingen tilgang: {label}")
            except Exception:
                result["warnings"].append(f"Ingen tilgang: {label}")

        result["ok"] = result["connectivity"] and len(result["accessible"]) >= 2
        return result
