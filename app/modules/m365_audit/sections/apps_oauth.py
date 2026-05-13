"""Section 17 — App Registrations and OAuth Consent Grants."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient

_EXPIRY_WARN_DAYS = 30


def _parse_utc(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cred_status(creds: list[dict], now: datetime) -> list[str]:
    flags: list[str] = []
    for c in creds:
        end = _parse_utc(c.get("endDateTime"))
        if end is None:
            flags.append("NO-EXPIRY")
            continue
        delta = (end - now).days
        if delta < 0:
            flags.append(f"EXPIRED({end.date()})")
        elif delta <= _EXPIRY_WARN_DAYS:
            flags.append(f"EXPIRING-SOON({end.date()},d={delta})")
    return flags


class AppsOAuthSection(BaseSection):
    name = "App Registrations & OAuth"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph
        self.apps: list[dict] = []

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_app_registrations()
            self._check_credential_expiry()
            await self._collect_oauth_grants()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── App Registrations ─────────────────────────────────────────────────────

    async def _collect_app_registrations(self) -> None:
        try:
            apps = await self.graph.get_all(
                "applications",
                params={
                    "$select": (
                        "id,displayName,appId,createdDateTime,signInAudience,"
                        "requiredResourceAccess,keyCredentials,passwordCredentials"
                    ),
                    "$top": "999",
                },
            )
        except Exception as ex:
            self._save("17_app_registrations.txt", f"Error: {ex}\n")
            self._warn(f"App registrations fetch failed: {ex}")
            return

        self.apps = apps
        now = datetime.now(timezone.utc)
        has_expired = False

        lines = [
            "=" * 120,
            f"  APP REGISTRATIONS  ({len(apps)} total)",
            "=" * 120,
            f"  {'App Name':<40} {'App ID':<38} {'Audience':<25} {'Created':<22} Credential Flags",
            "  " + "-" * 116,
        ]

        for app in apps:
            name      = (app.get("displayName") or "")[:40]
            app_id    = (app.get("appId") or "")[:38]
            audience  = (app.get("signInAudience") or "")[:25]
            created   = (app.get("createdDateTime") or "N/A")[:19]

            key_flags  = _cred_status(app.get("keyCredentials", []), now)
            pwd_flags  = _cred_status(app.get("passwordCredentials", []), now)
            all_flags  = key_flags + pwd_flags
            flags_str  = ", ".join(all_flags) if all_flags else "OK"

            if any("EXPIRED" in f for f in all_flags):
                has_expired = True
                self._warn(f"App '{name}' ({app_id}) has expired credentials")

            lines.append(
                f"  {name:<40} {app_id:<38} {audience:<25} {created:<22} {flags_str}"
            )

        lines += ["=" * 120, ""]
        self._save("17_app_registrations.txt", "\n".join(lines))

    # ── App Credential Expiry ────────────────────────────────────────────────

    def _check_credential_expiry(self) -> None:
        """Analyse passwordCredentials and keyCredentials for expiry."""
        if not self.apps:
            return

        now = datetime.now(timezone.utc)
        _CRITICAL_DAYS = 30
        _WARNING_DAYS = 90

        rows: list[dict] = []
        for app in self.apps:
            app_name = (app.get("displayName") or "(unnamed)")[:40]

            for cred in app.get("passwordCredentials") or []:
                end = _parse_utc(cred.get("endDateTime"))
                cred_name = (cred.get("displayName") or "")[:30]
                if end is None:
                    days_left = None
                    status = "No Expiry"
                else:
                    days_left = (end - now).days
                    if days_left < 0:
                        status = "EXPIRED"
                    elif days_left < _CRITICAL_DAYS:
                        status = "CRITICAL"
                    elif days_left < _WARNING_DAYS:
                        status = "Warning"
                    else:
                        status = "OK"
                rows.append({
                    "app": app_name,
                    "type": "Secret",
                    "cred_name": cred_name,
                    "expiry": end,
                    "days_left": days_left,
                    "status": status,
                })

            for cred in app.get("keyCredentials") or []:
                end = _parse_utc(cred.get("endDateTime"))
                cred_name = (cred.get("displayName") or "")[:30]
                if end is None:
                    days_left = None
                    status = "No Expiry"
                else:
                    days_left = (end - now).days
                    if days_left < 0:
                        status = "EXPIRED"
                    elif days_left < _CRITICAL_DAYS:
                        status = "CRITICAL"
                    elif days_left < _WARNING_DAYS:
                        status = "Warning"
                    else:
                        status = "OK"
                rows.append({
                    "app": app_name,
                    "type": "Certificate",
                    "cred_name": cred_name,
                    "expiry": end,
                    "days_left": days_left,
                    "status": status,
                })

        expired = [r for r in rows if r["status"] == "EXPIRED"]
        critical = [r for r in rows if r["status"] == "CRITICAL"]
        warning = [r for r in rows if r["status"] == "Warning"]

        lines = [
            "=" * 140,
            "  APP REGISTRATION CREDENTIAL EXPIRY REPORT",
            "=" * 140,
            "",
            f"  Total credentials : {len(rows)}",
            f"  Expired           : {len(expired)}",
            f"  Critical (<30d)   : {len(critical)}",
            f"  Warning  (<90d)   : {len(warning)}",
            f"  OK / No Expiry    : {len(rows) - len(expired) - len(critical) - len(warning)}",
            "",
        ]

        if rows:
            header = (
                f"  {'App Name':<40} {'Type':<12} {'Credential Name':<30} "
                f"{'Expiry Date':<22} {'Days Left':>9}  Status"
            )
            lines.append(header)
            lines.append("  " + "-" * 136)

            for r in rows:
                expiry_str = r["expiry"].strftime("%Y-%m-%d %H:%M") if r["expiry"] else "N/A"
                days_str = str(r["days_left"]) if r["days_left"] is not None else "N/A"
                lines.append(
                    f"  {r['app']:<40} {r['type']:<12} {r['cred_name']:<30} "
                    f"{expiry_str:<22} {days_str:>9}  {r['status']}"
                )
        else:
            lines.append("  No credentials found on any app registration.")

        lines += ["", "=" * 140, ""]
        self._save("17c_app_credential_expiry.txt", "\n".join(lines))

        # Warnings
        if expired:
            self._warn(
                f"{len(expired)} app credential(s) have EXPIRED"
            )
        if critical:
            self._warn(
                f"{len(critical)} app credential(s) expiring within {_CRITICAL_DAYS} days"
            )

        # Save WARN file if any expired or critical
        if expired or critical:
            warn_lines = [
                "=" * 140,
                "  WARNING: EXPIRED OR SOON-EXPIRING APP CREDENTIALS",
                "=" * 140,
                "",
                f"  {len(expired)} expired, {len(critical)} expiring within {_CRITICAL_DAYS} days.",
                "",
                f"  {'App Name':<40} {'Type':<12} {'Credential Name':<30} "
                f"{'Expiry Date':<22} {'Days Left':>9}  Status",
                "  " + "-" * 136,
            ]
            for r in expired + critical:
                expiry_str = r["expiry"].strftime("%Y-%m-%d %H:%M") if r["expiry"] else "N/A"
                days_str = str(r["days_left"]) if r["days_left"] is not None else "N/A"
                warn_lines.append(
                    f"  {r['app']:<40} {r['type']:<12} {r['cred_name']:<30} "
                    f"{expiry_str:<22} {days_str:>9}  {r['status']}"
                )
            warn_lines += ["", "=" * 140, ""]
            self._save("17c_app_credential_expiry_WARN.txt", "\n".join(warn_lines))

    # ── OAuth Consent Grants ──────────────────────────────────────────────────

    async def _resolve_sp_names(self, sp_ids: set[str]) -> dict[str, str]:
        """Batch-resolve service principal IDs to display names with caching."""
        resolved: dict[str, str] = {}
        sem = asyncio.Semaphore(10)

        async def fetch_sp(sp_id: str) -> tuple[str, str]:
            async with sem:
                try:
                    data = await self.graph.get(
                        f"servicePrincipals/{sp_id}",
                        params={"$select": "displayName,appDisplayName"},
                    )
                    name = (
                        data.get("displayName")
                        or data.get("appDisplayName")
                        or sp_id
                    )
                    return sp_id, name
                except Exception:
                    return sp_id, sp_id

        results = await asyncio.gather(
            *[fetch_sp(sid) for sid in sp_ids],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                continue
            sp_id, name = r
            resolved[sp_id] = name
        return resolved

    async def _collect_oauth_grants(self) -> None:
        try:
            grants = await self.graph.get_all(
                "oauth2PermissionGrants",
                params={
                    "$filter": "consentType eq 'AllPrincipals'",
                    "$top":    "200",
                },
            )
        except Exception as ex:
            self._save("17b_oauth_consent_grants.txt", f"Error: {ex}\n")
            self._warn(f"OAuth consent grants fetch failed: {ex}")
            return

        # Resolve service principal IDs to display names
        all_sp_ids: set[str] = set()
        for g in grants:
            if g.get("clientId"):
                all_sp_ids.add(g["clientId"])
            if g.get("resourceId"):
                all_sp_ids.add(g["resourceId"])

        sp_names = await self._resolve_sp_names(all_sp_ids) if all_sp_ids else {}

        lines = [
            "=" * 120,
            f"  OAUTH TENANT-WIDE CONSENT GRANTS  ({len(grants)} total)",
            "=" * 120,
            f"  {'Client App':<40} {'Resource':<40} Scopes",
            "  " + "-" * 116,
        ]
        for g in grants:
            client_id   = g.get("clientId") or ""
            resource_id = g.get("resourceId") or ""
            client_name = sp_names.get(client_id, client_id)[:40]
            resource_name = sp_names.get(resource_id, resource_id)[:40]
            scopes      = (g.get("scope") or "").replace(" ", ", ")
            lines.append(f"  {client_name:<40} {resource_name:<40} {scopes}")
        lines += ["=" * 120, ""]
        self._save("17b_oauth_consent_grants.txt", "\n".join(lines))
