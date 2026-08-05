"""IT Glue API integration for uploading audit data, credentials, and reports.

Supports US, EU, and AU regions. Authentication via API key.
All customer data is uploaded as Flexible Assets with attached PDF reports.

Usage:
    client = ITGlueClient(api_key="...", region="eu")
    orgs = await client.list_organizations()
    await client.upload_audit_report(org_id=123, report_path=Path("report.pdf"), ...)
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional

import httpx

from app.integrations.http_retry import send_with_retry

_BASE_URLS = {
    "us": "https://api.itglue.com",
    "eu": "https://api.eu.itglue.com",
    "au": "https://api.au.itglue.com",
}

# Flexible Asset Type name used by MSP Toolkit
ASSET_TYPE_NAME = "MSP Toolkit"
CRED_ASSET_TYPE_NAME = "MSP Toolkit — Tenant Credentials"


class ITGlueClient:
    """Async IT Glue API client."""

    def __init__(self, api_key: str, region: str = "eu"):
        self.api_key = api_key
        self.base_url = _BASE_URLS.get(region.lower(), _BASE_URLS["eu"])
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/vnd.api+json",
            },
            timeout=60.0,
        )
        self._folder_cache: dict[tuple, int] = {}  # (org_id, folder_name) -> folder_id

    async def close(self):
        await self._client.aclose()

    # ── Generic helpers ──────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict | None = None) -> dict:
        r = await send_with_retry(
            lambda: self._client.get(path, params=params),
            method="GET", target=f"IT Glue GET {path}",
        )
        r.raise_for_status()
        return r.json()

    async def _post(self, path: str, payload: dict) -> dict:
        # Throttling is retried; a 5xx is not. A repeated upload that the
        # server had already applied leaves two documents behind.
        r = await send_with_retry(
            lambda: self._client.post(path, json=payload),
            method="POST", target=f"IT Glue POST {path}",
        )
        if r.status_code >= 400:
            detail = r.text[:500] if r.text else ""
            raise httpx.HTTPStatusError(
                f"IT Glue API {r.status_code}: {detail}",
                request=r.request,
                response=r,
            )
        return r.json()

    async def _patch(self, path: str, payload: dict) -> dict:
        r = await send_with_retry(
            lambda: self._client.patch(path, json=payload),
            method="PATCH", target=f"IT Glue PATCH {path}",
        )
        r.raise_for_status()
        return r.json()

    # ── Organizations ────────────────────────────────────────────────────────

    async def list_organizations(self, name: str = "") -> list[dict]:
        """List organizations, optionally filtered by name.

        Walks all pages so MSPs with >250 orgs see the full list.
        """
        all_orgs: list[dict] = []
        page = 1
        while True:
            params: dict = {"page[size]": 250, "page[number]": page}
            if name:
                params["filter[name]"] = name
            data = await self._get("/organizations", params)
            batch = data.get("data", [])
            all_orgs.extend(batch)
            if len(batch) < 250:
                break
            page += 1
            if page > 200:  # safety cap: 50 000 orgs
                break
        return all_orgs

    async def find_organization(self, name: str) -> Optional[dict]:
        """Find a single organization by exact name match."""
        orgs = await self.list_organizations(name)
        for org in orgs:
            if org.get("attributes", {}).get("name", "").lower() == name.lower():
                return org
        return orgs[0] if orgs else None

    # ── Flexible Asset Types ─────────────────────────────────────────────────

    async def list_flexible_asset_types(self) -> list[dict]:
        data = await self._get("/flexible_asset_types")
        return data.get("data", [])

    async def find_or_create_audit_type(self) -> int:
        """Find or create the 'Security Audit' flexible asset type. Returns ID."""
        types = await self.list_flexible_asset_types()
        for t in types:
            if t.get("attributes", {}).get("name") == ASSET_TYPE_NAME:
                return int(t["id"])

        # Create the type with fields — may fail if API key lacks admin permissions
        try:
            payload = {
                "data": {
                    "type": "flexible_asset_types",
                    "attributes": {
                        "name": ASSET_TYPE_NAME,
                        "icon": "shield",
                        "description": "Security audit results from MSP Toolkit",
                        "enabled": True,
                    },
                }
            }
            result = await self._post("/flexible_asset_types", payload)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Kunne ikke opprette Flexible Asset Type «{ASSET_TYPE_NAME}» i IT Glue "
                f"(HTTP {e.response.status_code}). Opprett typen manuelt i IT Glue under "
                f"Account → Flexible Asset Types, eller bruk en API-nøkkel med admin-tilgang."
            ) from e
        type_id = int(result["data"]["id"])

        # Create fields — matches Marius' IT Glue Flexible Asset config
        fields = [
            {"name": "Audit Date", "kind": "Date", "required": False, "show_in_list": True, "use_for_title": True, "decimals": None},
            {"name": "Risk Grade", "kind": "Text", "required": False, "show_in_list": True, "use_for_title": False, "decimals": None},
            {"name": "Risk Score", "kind": "Number", "required": False, "show_in_list": True, "use_for_title": False, "decimals": 0},
            {"name": "MFA Coverage %", "kind": "Percent", "required": False, "show_in_list": True, "use_for_title": False, "decimals": 0},
            {"name": "Secure Score %", "kind": "Percent", "required": False, "show_in_list": True, "use_for_title": False, "decimals": 0},
            {"name": "Users Total", "kind": "Number", "required": False, "show_in_list": True, "use_for_title": False, "decimals": 0},
            {"name": "Users Without MFA", "kind": "Number", "required": False, "show_in_list": True, "use_for_title": False, "decimals": 0},
            {"name": "CA Policies", "kind": "Number", "required": False, "show_in_list": True, "use_for_title": False, "decimals": 0},
            {"name": "Global Admins", "kind": "Number", "required": False, "show_in_list": True, "use_for_title": False, "decimals": 0},
            {"name": "Intune Compliance", "kind": "Percent", "required": False, "show_in_list": True, "use_for_title": False, "decimals": 0},
            {"name": "Executive Summary", "kind": "Textbox", "required": False, "show_in_list": True, "use_for_title": False, "decimals": None},
            {"name": "Recommendations", "kind": "Textbox", "required": False, "show_in_list": True, "use_for_title": False, "decimals": None},
        ]
        for i, field in enumerate(fields):
            attrs = {
                "flexible-asset-type-id": type_id,
                "order": i + 1,
                "name": field["name"],
                "kind": field["kind"],
                "required": field.get("required", False),
                "show-in-list": field.get("show_in_list", True),
                "use-for-title": field.get("use_for_title", False),
            }
            if field.get("decimals") is not None:
                attrs["decimals"] = field["decimals"]
            field_payload = {"data": {"type": "flexible_asset_fields", "attributes": attrs}}
            await self._post(f"/flexible_asset_types/{type_id}/relationships/flexible_asset_fields", field_payload)

        return type_id

    async def find_or_create_credential_type(self) -> int:
        """Find or create the 'Tenant Credentials' flexible asset type. Returns ID."""
        types = await self.list_flexible_asset_types()
        for t in types:
            name = t.get("attributes", {}).get("name", "")
            if name == CRED_ASSET_TYPE_NAME:
                return int(t["id"])

        # Try to create — may fail if API key lacks admin permissions
        try:
            payload = {
                "data": {
                    "type": "flexible_asset_types",
                    "attributes": {
                        "name": CRED_ASSET_TYPE_NAME,
                        "icon": "lock",
                        "description": "M365/Azure tenant credentials managed by MSP Toolkit",
                        "enabled": True,
                    },
                }
            }
            result = await self._post("/flexible_asset_types", payload)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Kunne ikke opprette Flexible Asset Type «{CRED_ASSET_TYPE_NAME}» i IT Glue "
                f"(HTTP {e.response.status_code}). Opprett typen manuelt i IT Glue under "
                f"Account → Flexible Asset Types, eller bruk en API-nøkkel med admin-tilgang."
            ) from e
        type_id = int(result["data"]["id"])

        fields = [
            {"name": "Tenant Name", "kind": "Text", "required": True, "show_in_list": True},
            {"name": "Tenant ID", "kind": "Text", "required": True, "show_in_list": True},
            {"name": "Client ID", "kind": "Text", "required": True, "show_in_list": False},
            {"name": "Primary Domain", "kind": "Text", "required": False, "show_in_list": True},
            {"name": "Client Secret", "kind": "Password", "required": False, "show_in_list": False},
            {"name": "Certificate Expiry", "kind": "Date", "required": False, "show_in_list": True},
            {"name": "Secret Expiry", "kind": "Date", "required": False, "show_in_list": True},
            {"name": "Setup Date", "kind": "Date", "required": False, "show_in_list": False},
            {"name": "Notes", "kind": "Textbox", "required": False, "show_in_list": False},
        ]
        for i, field in enumerate(fields):
            field_payload = {
                "data": {
                    "type": "flexible_asset_fields",
                    "attributes": {
                        "flexible-asset-type-id": type_id,
                        "order": i + 1,
                        "name": field["name"],
                        "kind": field["kind"],
                        "required": field.get("required", False),
                        "show-in-list": field.get("show_in_list", False),
                        "use-for-title": field["name"] == "Tenant Name",
                    },
                }
            }
            await self._post(f"/flexible_asset_types/{type_id}/relationships/flexible_asset_fields", field_payload)

        return type_id

    @staticmethod
    def _trait_key(field_name: str) -> str:
        """Convert an IT Glue field name to a trait key (lowercase, spaces→hyphens)."""
        key = field_name.lower().replace(" ", "-").replace("%", "")
        # Clean up trailing/double hyphens from removed characters
        while "--" in key:
            key = key.replace("--", "-")
        return key.strip("-")

    # ── Inspect existing structure ─────────────────────────────────────────

    async def inspect_asset_type(self, type_name: str = ASSET_TYPE_NAME) -> dict | None:
        """Fetch an existing Flexible Asset Type and its fields from IT Glue.

        Returns a dict with type info and field mappings, or None if not found.
        This lets the app adapt to whatever field structure exists in IT Glue
        rather than assuming our hardcoded layout.
        """
        types = await self.list_flexible_asset_types()
        match = None
        for t in types:
            if t.get("attributes", {}).get("name") == type_name:
                match = t
                break
        if not match:
            return None

        type_id = int(match["id"])
        # Fetch fields for this type
        fields_data = await self._get(
            f"/flexible_asset_types/{type_id}/relationships/flexible_asset_fields"
        )
        fields = []
        for f in fields_data.get("data", []):
            attrs = f.get("attributes", {})
            fields.append({
                "id": int(f["id"]),
                "name": attrs.get("name", ""),
                "name_key": attrs.get("name-key", ""),
                "kind": attrs.get("kind", ""),
                "decimals": attrs.get("decimals", None),
                "required": attrs.get("required", False),
                "show_in_list": attrs.get("show-in-list", False),
                "use_for_title": attrs.get("use-for-title", False),
                "order": attrs.get("order", 0),
            })
        fields.sort(key=lambda x: x["order"])

        return {
            "id": type_id,
            "name": type_name,
            "icon": match.get("attributes", {}).get("icon", ""),
            "fields": fields,
            "field_names": [f["name"] for f in fields],
            "name_keys": {f["name_key"] for f in fields if f["name_key"]},
            "field_by_key": {f["name_key"]: f for f in fields if f["name_key"]},
        }

    async def inspect_all_types(self) -> list[dict]:
        """List all Flexible Asset Types with their fields. Useful for discovering
        what structure already exists in IT Glue before uploading."""
        types = await self.list_flexible_asset_types()
        result = []
        for t in types:
            type_id = int(t["id"])
            attrs = t.get("attributes", {})
            try:
                fields_data = await self._get(
                    f"/flexible_asset_types/{type_id}/relationships/flexible_asset_fields"
                )
                fields = [
                    {
                        "name": f.get("attributes", {}).get("name", ""),
                        "kind": f.get("attributes", {}).get("kind", ""),
                        "required": f.get("attributes", {}).get("required", False),
                    }
                    for f in fields_data.get("data", [])
                ]
            except Exception:
                fields = []
            result.append({
                "id": type_id,
                "name": attrs.get("name", ""),
                "icon": attrs.get("icon", ""),
                "fields": fields,
            })
        return result

    # ── Upload audit data ────────────────────────────────────────────────────

    async def upload_audit(
        self,
        org_id: int,
        audit_date: str,
        metrics: dict,
        executive_summary: str = "",
        recommendations: str = "",
        report_pdf_path: Optional[Path] = None,
    ) -> dict:
        """Upload audit results as a flexible asset, optionally with PDF attachment.

        Inspects the existing Flexible Asset Type fields in IT Glue and only
        sends traits for fields that actually exist, avoiding API errors from
        field mismatches.
        """
        type_id = await self.find_or_create_audit_type()

        # Inspect actual field structure from IT Glue (uses name-key from API)
        type_info = await self.inspect_asset_type(ASSET_TYPE_NAME)
        field_by_key = type_info["field_by_key"] if type_info else {}
        valid_keys = type_info["name_keys"] if type_info else set()

        all_traits = {
            "audit-date": audit_date,
            "risk-grade": str(metrics.get("risk_grade", "")),
            "risk-score": metrics.get("risk_score", 0),
            "mfa-coverage": metrics.get("mfa_coverage_pct", 0),
            "secure-score": metrics.get("secure_score_pct", 0),
            "users-total": metrics.get("total_users", 0),
            "users-without-mfa": metrics.get("users_no_mfa", 0),
            "ca-policies": metrics.get("ca_policies_enabled", 0),
            "global-admins": metrics.get("admin_roles_ga_count", 0),
            "intune-compliance": metrics.get("intune_compliance_pct", 0),
            "executive-summary": executive_summary,
            "recommendations": recommendations,
        }

        # Only send traits for fields that exist, and respect decimals setting
        if valid_keys:
            traits = {}
            for k, v in all_traits.items():
                if k not in valid_keys:
                    continue
                field_info = field_by_key.get(k, {})
                # Round numbers if field has decimals: 0
                if field_info.get("kind") in ("Number", "Percent") and field_info.get("decimals") == 0:
                    v = int(round(v)) if isinstance(v, (int, float)) else v
                traits[k] = v
        else:
            traits = all_traits

        payload = {
            "data": {
                "type": "flexible_assets",
                "attributes": {
                    "organization-id": org_id,
                    "flexible-asset-type-id": type_id,
                    "traits": traits,
                },
            }
        }
        result = await self._post("/flexible_assets", payload)
        asset_id = result["data"]["id"]

        # Attach PDF report if provided
        if report_pdf_path and report_pdf_path.exists():
            await self._attach_file(
                resource_type="flexible_assets",
                resource_id=asset_id,
                file_path=report_pdf_path,
            )

        return result["data"]

    # ── Upload credentials ───────────────────────────────────────────────────

    async def upload_credentials(
        self,
        org_id: int,
        config: dict,
        client_secret: str = "",
        cert_path: Optional[Path] = None,
    ) -> dict:
        """Upload tenant credentials as a flexible asset."""
        type_id = await self.find_or_create_credential_type()

        traits = {
            "tenant-name": config.get("CustomerName", ""),
            "tenant-id": config.get("TenantId", ""),
            "client-id": config.get("ClientId", ""),
            "primary-domain": config.get("PrimaryDomain", ""),
            "client-secret": client_secret,
            "certificate-expiry": config.get("CertExpiry", "")[:10] if config.get("CertExpiry") else "",
            "secret-expiry": config.get("SecretExpiry", "")[:10] if config.get("SecretExpiry") else "",
            "setup-date": config.get("SetupDate", "")[:10] if config.get("SetupDate") else "",
            "notes": f"Managed by MSP Toolkit. App Object ID: {config.get('AppObjectId', '')}",
        }

        payload = {
            "data": {
                "type": "flexible_assets",
                "attributes": {
                    "organization-id": org_id,
                    "flexible-asset-type-id": type_id,
                    "traits": traits,
                },
            }
        }
        result = await self._post("/flexible_assets", payload)
        asset_id = result["data"]["id"]

        # Attach certificate if provided
        if cert_path and cert_path.exists():
            from app.core.encryption import encrypted_read_bytes
            await self._attach_file(
                resource_type="flexible_assets",
                resource_id=asset_id,
                file_path=cert_path,
                file_name=f"{config.get('CustomerName', 'cert')}.pfx",
            )

        return result["data"]

    # ── File attachment ──────────────────────────────────────────────────────

    async def _attach_file(
        self,
        resource_type: str,
        resource_id: str | int,
        file_path: Path,
        file_name: str = "",
    ) -> dict:
        """Attach a file to an IT Glue resource via base64 encoding."""
        from app.core.encryption import encrypted_read_bytes

        raw_bytes = encrypted_read_bytes(file_path)
        b64_content = base64.b64encode(raw_bytes).decode("ascii")

        payload = {
            "data": {
                "type": "attachments",
                "attributes": {
                    "attachment": {
                        "content": b64_content,
                        "file_name": file_name or file_path.name,
                    }
                },
            }
        }
        return await self._post(
            f"/{resource_type}/{resource_id}/relationships/attachments",
            payload,
        )

    # ── Document folders & documents ─────────────────────────────────────────

    async def find_or_create_document_folder(self, org_id: int, folder_name: str = "MSP Toolkit") -> int:
        """Find or create a document folder under an organization. Returns folder ID.

        Searches ALL pages of document folders to avoid creating duplicates.
        """
        cache_key = (org_id, folder_name.lower())
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        # Search existing folders — try org relationship first, then global with filter
        all_folders = []
        for search_endpoint in [
            (f"/organizations/{org_id}/relationships/document_folders", {}),
            ("/document_folders", {"filter[organization-id]": org_id}),
        ]:
            endpoint, extra_params = search_endpoint
            page = 1
            while True:
                try:
                    params = {"page[size]": 250, "page[number]": page, **extra_params}
                    data = await self._get(endpoint, params=params)
                    batch = data.get("data", [])
                    all_folders.extend(batch)
                    if len(batch) < 250:
                        break
                    page += 1
                except Exception:
                    break
            if all_folders:
                break

        for f in all_folders:
            if f.get("attributes", {}).get("name", "").lower() == folder_name.lower():
                fid = int(f["id"])
                self._folder_cache[cache_key] = fid
                return fid

        # Folder truly doesn't exist — create it (try both endpoints)
        payload = {
            "data": {
                "type": "document_folders",
                "attributes": {
                    "name": folder_name,
                    "organization-id": org_id,
                },
            }
        }
        result = None
        last_error = None
        for endpoint in [
            f"/organizations/{org_id}/relationships/document_folders",
            "/document_folders",
        ]:
            try:
                result = await self._post(endpoint, payload)
                break
            except httpx.HTTPStatusError as e:
                last_error = e
                continue
        if not result:
            code = last_error.response.status_code if last_error else "unknown"
            raise RuntimeError(
                f"Could not create folder '{folder_name}' in IT Glue (HTTP {code})"
            )

        fid = int(result["data"]["id"])
        self._folder_cache[cache_key] = fid
        return fid

    @staticmethod
    def _prepare_html_for_itglue(html: str) -> str:
        """Strip CSS, scripts, head, base64 images, and inline styles from HTML.

        IT Glue renders its own styling, so we only need the semantic content.
        This also avoids the ~50K section size limit caused by heavy payloads.
        """
        import re
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL)
        html = re.sub(r'src="data:image/[^"]*"', 'src=""', html)
        html = re.sub(r'<!DOCTYPE[^>]*>', '', html)
        html = re.sub(r'</?html[^>]*>', '', html)
        html = re.sub(r'</?body[^>]*>', '', html)
        html = re.sub(r'\s*style="[^"]*"', '', html)
        # Collapse whitespace
        html = re.sub(r'\n\s*\n', '\n', html)
        return html.strip()

    async def upload_report_as_document(
        self,
        org_id: int,
        file_path: Path,
        doc_name: str,
    ) -> dict:
        """Upload a report to IT Glue as a Document with content.

        HTML reports: stripped of CSS/images, split into <=40K sections.
        PDF/other:    attached as file attachment on the document.
        Uses POST /documents/:id/relationships/sections for content.
        """
        from app.core.encryption import encrypted_read_bytes

        raw_bytes = encrypted_read_bytes(file_path)

        # Create the document — status 1 = Published (avoids blank draft state)
        result = await self._post("/documents", {
            "data": {
                "type": "documents",
                "attributes": {
                    "organization-id": org_id,
                    "name": doc_name,
                    "document-status-id": 1,
                },
            }
        })
        doc_id = result["data"]["id"]

        suffix = file_path.suffix.lower()
        if suffix == ".html":
            html_content = self._prepare_html_for_itglue(
                raw_bytes.decode("utf-8", errors="replace")
            )
            # Split into chunks if needed (IT Glue ~50K limit per section)
            max_chunk = 40000
            chunks = []
            while html_content:
                chunks.append(html_content[:max_chunk])
                html_content = html_content[max_chunk:]

            for i, chunk in enumerate(chunks):
                await self._post(
                    f"/documents/{doc_id}/relationships/sections",
                    {
                        "data": {
                            "type": "document-sections",
                            "attributes": {
                                "resource-type": "Document::Text",
                                "content": chunk,
                                "position": i + 1,
                            },
                        }
                    },
                )

            # Force publish after sections are uploaded — ensures document renders
            # and doesn't sit in draft/blank state
            try:
                await self._patch(f"/documents/{doc_id}", {
                    "data": {
                        "id": doc_id,
                        "type": "documents",
                        "attributes": {"document-status-id": 1},
                    }
                })
            except Exception:
                pass  # Non-fatal — document was created with status 1 already
        else:
            # Attach binary file (PDF etc.)
            b64_content = base64.b64encode(raw_bytes).decode("ascii")
            await self._post(
                f"/documents/{doc_id}/relationships/attachments",
                {
                    "data": {
                        "type": "attachments",
                        "attributes": {
                            "attachment": {
                                "content": b64_content,
                                "file_name": file_path.name,
                            }
                        },
                    }
                },
            )

        return result.get("data", {})

    async def upload_audit_reports(
        self,
        org_id: int,
        report_files: list[Path],
        audit_date: str,
    ) -> list[dict]:
        """Upload selected reports to IT Glue Documents under the organization."""
        uploaded = []
        date_label = audit_date[:10] if audit_date else "unknown"

        for f in report_files:
            doc_name = f"{date_label} — {f.stem}{f.suffix}"
            result = await self.upload_report_as_document(
                org_id=org_id,
                file_path=f,
                doc_name=doc_name,
            )
            uploaded.append({"name": doc_name, "id": result.get("id", "")})

        return uploaded

    # ── Test connection ──────────────────────────────────────────────────────

    # ── Flexible Asset upsert (find or create/update by name) ─────────────

    async def find_flexible_assets(
        self,
        type_id: int,
        org_id: int,
        name_contains: str = "",
    ) -> list[dict]:
        """Find flexible assets filtered by type and organization."""
        params: dict = {
            "filter[flexible-asset-type-id]": type_id,
            "filter[organization-id]": org_id,
            "page[size]": 250,
        }
        if name_contains:
            params["filter[name]"] = name_contains
        data = await self._get("/flexible_assets", params)
        return data.get("data", [])

    async def upsert_flexible_asset(
        self,
        type_id: int,
        org_id: int,
        asset_name: str,
        traits: dict,
    ) -> dict:
        """Create or update a flexible asset, matched by asset name within org+type.

        Returns the asset data dict with 'id', 'upserted' ('created'|'updated').
        """
        existing = await self.find_flexible_assets(type_id, org_id, asset_name)
        match = None
        for a in existing:
            a_traits = a.get("attributes", {}).get("traits", {})
            for v in a_traits.values():
                if isinstance(v, str) and v.strip().lower() == asset_name.strip().lower():
                    match = a
                    break
            if match:
                break

        if match:
            asset_id = match["id"]
            payload = {
                "data": {
                    "id": asset_id,
                    "type": "flexible_assets",
                    "attributes": {"traits": traits},
                }
            }
            result = await self._patch(f"/flexible_assets/{asset_id}", payload)
            result["data"]["upserted"] = "updated"
            return result["data"]
        else:
            payload = {
                "data": {
                    "type": "flexible_assets",
                    "attributes": {
                        "organization-id": org_id,
                        "flexible-asset-type-id": type_id,
                        "traits": traits,
                    },
                }
            }
            result = await self._post("/flexible_assets", payload)
            result["data"]["upserted"] = "created"
            return result["data"]

    # ── Documentation Sync asset types ──────────────────────────────────────

    async def find_or_create_doc_type(
        self, type_name: str, icon: str, description: str, fields: list[dict],
    ) -> int:
        """Find or create a documentation Flexible Asset Type. Returns type ID."""
        types = await self.list_flexible_asset_types()
        for t in types:
            if t.get("attributes", {}).get("name") == type_name:
                return int(t["id"])

        try:
            payload = {
                "data": {
                    "type": "flexible_asset_types",
                    "attributes": {
                        "name": type_name,
                        "icon": icon,
                        "description": description,
                        "enabled": True,
                    },
                }
            }
            result = await self._post("/flexible_asset_types", payload)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Could not create Flexible Asset Type '{type_name}' in IT Glue "
                f"(HTTP {e.response.status_code}). Create it manually under "
                f"Account > Flexible Asset Types, or use an admin API key."
            ) from e
        type_id = int(result["data"]["id"])

        for i, fld in enumerate(fields):
            attrs: dict = {
                "flexible-asset-type-id": type_id,
                "order": i + 1,
                "name": fld["name"],
                "kind": fld["kind"],
                "required": fld.get("required", False),
                "show-in-list": fld.get("show_in_list", True),
                "use-for-title": fld.get("use_for_title", False),
            }
            if fld.get("decimals") is not None:
                attrs["decimals"] = fld["decimals"]
            field_payload = {
                "data": {"type": "flexible_asset_fields", "attributes": attrs}
            }
            await self._post(
                f"/flexible_asset_types/{type_id}/relationships/flexible_asset_fields",
                field_payload,
            )

        return type_id

    async def ensure_network_inventory_type(self) -> int:
        """Ensure the Network Inventory Flexible Asset Type exists."""
        return await self.find_or_create_doc_type(
            type_name="MSP Toolkit \u2014 Network Inventory",
            icon="sitemap",
            description="Network device inventory from MSP Toolkit (UniFi, FortiGate)",
            fields=[
                {"name": "Customer", "kind": "Text", "required": True, "show_in_list": True, "use_for_title": True},
                {"name": "Last Updated", "kind": "Date", "required": False, "show_in_list": True},
                {"name": "Total Devices", "kind": "Number", "required": False, "show_in_list": True, "decimals": 0},
                {"name": "APs", "kind": "Number", "required": False, "show_in_list": True, "decimals": 0},
                {"name": "Switches", "kind": "Number", "required": False, "show_in_list": True, "decimals": 0},
                {"name": "Gateways", "kind": "Number", "required": False, "show_in_list": True, "decimals": 0},
                {"name": "Firewalls", "kind": "Number", "required": False, "show_in_list": True, "decimals": 0},
                {"name": "Outdated Firmware", "kind": "Number", "required": False, "show_in_list": True, "decimals": 0},
                {"name": "Device List", "kind": "Textbox", "required": False, "show_in_list": False},
                {"name": "Alerts", "kind": "Textbox", "required": False, "show_in_list": False},
            ],
        )

    async def ensure_domain_overview_type(self) -> int:
        """Ensure the Domain Overview Flexible Asset Type exists."""
        return await self.find_or_create_doc_type(
            type_name="MSP Toolkit \u2014 Domain Overview",
            icon="globe",
            description="Domain and DNS overview from MSP Toolkit (Uniweb)",
            fields=[
                {"name": "Customer", "kind": "Text", "required": True, "show_in_list": True, "use_for_title": True},
                {"name": "Last Updated", "kind": "Date", "required": False, "show_in_list": True},
                {"name": "Total Domains", "kind": "Number", "required": False, "show_in_list": True, "decimals": 0},
                {"name": "Domain List", "kind": "Textbox", "required": False, "show_in_list": False},
                {"name": "SSL Status", "kind": "Textbox", "required": False, "show_in_list": False},
                {"name": "Expiring Soon", "kind": "Number", "required": False, "show_in_list": True, "decimals": 0},
            ],
        )

    async def ensure_license_summary_type(self) -> int:
        """Ensure the License Summary Flexible Asset Type exists."""
        return await self.find_or_create_doc_type(
            type_name="MSP Toolkit \u2014 License Summary",
            icon="key",
            description="ALSO license/subscription summary from MSP Toolkit",
            fields=[
                {"name": "Customer", "kind": "Text", "required": True, "show_in_list": True, "use_for_title": True},
                {"name": "Last Updated", "kind": "Date", "required": False, "show_in_list": True},
                {"name": "Total Subscriptions", "kind": "Number", "required": False, "show_in_list": True, "decimals": 0},
                {"name": "Monthly Cost", "kind": "Number", "required": False, "show_in_list": True, "decimals": 2},
                {"name": "Currency", "kind": "Text", "required": False, "show_in_list": True},
                {"name": "Subscription List", "kind": "Textbox", "required": False, "show_in_list": False},
                {"name": "Expiring Soon", "kind": "Number", "required": False, "show_in_list": True, "decimals": 0},
            ],
        )

    # ── Test connection ─────────────────────────────────────────────────────

    async def test_connection(self) -> dict:
        """Test the API key by fetching organizations. Returns status."""
        try:
            orgs = await self.list_organizations()
            return {"ok": True, "organizations": len(orgs)}
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
