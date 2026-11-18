"""Section 34: backup of the Microsoft 365 data (mailboxes, OneDrive, SharePoint, Teams).

The question customers ask most is whether their mail and files are backed up,
and until this section the audit only looked at Azure VMs. Two sources answer
it, read independently because either one can be the tenant's answer:

* **Microsoft 365 Backup**, the native service, through the Backup Storage API
  in Graph: whether the service is enabled, which protection policies exist
  for Exchange, OneDrive and SharePoint, and how many mailboxes, accounts and
  sites they protect.
* **A third-party backup product**, recognised from the service principals in
  the tenant: a backup vendor's app holding consent to mail or files.

Neither proves that restorable backups exist. An active policy with protected
units is the strongest reading the tenant gives; a vendor's app with access is
evidence that the product is installed and allowed to read the data, not that
its jobs run. The report words it that way.

A refusal is not a zero. A 403 (the permission was never consented), a 404 or
any other failed read is recorded as unreadable, with the reason, and never as
"no backup". Only a source that was read and showed nothing counts as nothing.

Endpoints and permissions, verified against Microsoft Learn (October 2026):

* ``GET v1.0/solutions/backupRestore``: the tenant's ``serviceStatus``
  (``disabled``, ``enabled``, ``protectionChangeLocked``, ``restoreLocked``).
  Needs BackupRestore-Control.Read.All.
* ``GET v1.0/solutions/backupRestore/protectionPolicies``: every policy, each
  typed by ``@odata.type`` as an Exchange, SharePoint or OneDrive policy, with
  its aggregated status. Needs BackupRestore-Configuration.Read.All, as do the
  two reads below.
* ``GET beta/solutions/backupRestore/protectionPolicies/{id}`` with
  ``$select=...protectionPolicyArtifactCount``: the protected, in-progress
  and failed counts in one call (returned only on ``$select``), and
  ``protectionMode`` (``fullServiceBackup`` backs up the whole workload).
* When that beta read gives no count, the policy's protection units are
  listed on v1.0 and counted by status. Under application permissions a unit
  carries no display name or address, so the section records counts only.

The third-party read lists the service principals (Application.Read.All,
already granted) and, for the few that match a backup product, their
application permissions and delegated grants. A service principal is matched
on what it says about itself, strongest first:

* ``app_id``: an application id the vendor publishes for its backup app. None
  of the vendors below publishes one (October 2026), so this tier is empty
  rather than filled with ids nobody can cite.
* ``publisher``: the app's Microsoft-verified publisher is a backup vendor.
  Microsoft verifies the publisher against the vendor's partner account, and
  the customer's admin cannot rename it, so a renamed app is still found.
* ``name``: the service principal's or its app's display name names a product.
  The tenant's own admin can rename the first, which is the gap the two tiers
  above and below exist for.
* ``generic``: "backup" in the name, kept only with access to the data.
* ``access``: no name at all, but the application permissions a backup product
  needs: every mailbox and every site or drive, app-only. Found from the
  resource side (who holds app roles on Microsoft Graph and Exchange Online), so
  it costs two listings rather than one read per app. This is a candidate to
  check, never a backup product: mail archivers, migration tools and e-mail
  security products hold the same access, and the report says so.

None of the tiers says whether a backup ran. The last successful backup is in
the vendor's own API, behind the vendor's own credentials, and the audit reads
neither; the report states that plainly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import EXO_APP_ID, GRAPH_APP_ID
from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient, GraphPermissionError

logger = logging.getLogger(__name__)

# The workloads in report order. Teams is listed because customers ask about
# it, but Microsoft 365 Backup has no Teams policy: Teams files live in
# SharePoint sites, and chats and channel messages are not covered.
WORKLOADS = ("exchange", "onedrive", "sharepoint", "teams")

# The permission each read needs, named where a refusal is explained. The
# names are the ones the Graph permissions reference lists.
SERVICE_PERMISSION = "BackupRestore-Control.Read.All"
POLICY_PERMISSION = "BackupRestore-Configuration.Read.All"

_POLICY_TYPES = {
    "#microsoft.graph.exchangeProtectionPolicy": "exchange",
    "#microsoft.graph.sharePointProtectionPolicy": "sharepoint",
    "#microsoft.graph.oneDriveForBusinessProtectionPolicy": "onedrive",
}

# Where a policy's protection units are listed on v1.0, per workload.
_UNIT_COLLECTIONS = {
    "exchange": ("exchangeProtectionPolicies", "mailboxProtectionUnits"),
    "sharepoint": ("sharePointProtectionPolicies", "siteProtectionUnits"),
    "onedrive": ("oneDriveForBusinessProtectionPolicies", "driveProtectionUnits"),
}

# protectionUnitStatus values that mean the unit is not being backed up.
_UNIT_NOT_PROTECTED = {
    "unprotected",
    "unprotectrequested",
    "removerequested",
    "offboardrequested",
    "offboarded",
}


# ── Third-party products ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class BackupProduct:
    """A backup product as it shows up among a tenant's service principals.

    ``patterns`` are regular expressions matched, case-insensitively, against
    the app's Microsoft-verified publisher and against the service principal's
    display name and its app's display name. A vendor that also sells other
    products has a pattern that needs "backup", so its verified publisher
    alone ("AvePoint, Inc.") matches none of them, which is what keeps a
    migration tool from the same publisher out.
    ``app_ids`` are multi-tenant application ids, listed only where the vendor
    publishes one; none of the products below does, so every entry matches on
    its publisher or its name. ``name`` is None only for the generic catch-all,
    whose matches the report names by the app's own display name.
    """

    name: str | None
    patterns: tuple[str, ...]
    app_ids: tuple[str, ...] = ()


# Several vendors also sell e-mail security or migration tools whose apps hold
# the same mail and file permissions. For those the pattern requires "backup"
# in the name, so a mail filter is not reported as a backup product.
BACKUP_PRODUCTS: tuple[BackupProduct, ...] = (
    # The admin registers Veeam's app in the customer's own tenant (default name
    # "Veeam Backup for Microsoft 365"), so there is no fixed app id to match.
    BackupProduct("Veeam Backup for Microsoft 365", (r"\bveeam\b",)),
    # AvePoint's migration (Fly) and governance apps carry broad scopes too;
    # only the backup product's name says "backup".
    BackupProduct("AvePoint Cloud Backup", (r"avepoint.*backup",)),
    # Keepit's connector app is named after the vendor; no published app id.
    BackupProduct("Keepit", (r"\bkeepit\b",)),
    # Acronis Cyber Protect's Microsoft 365 backup; no published app id.
    BackupProduct("Acronis Cyber Protect", (r"\bacronis\b",)),
    # Datto's own help names the enterprise app "Backupify", the product's
    # former name, under Enterprise apps > Backupify > Permissions.
    BackupProduct("Datto SaaS Protection", (r"\bbackupify\b", r"\bdatto\s+saas\b")),
    # Dropsuite was renamed NinjaOne SaaS Backup after the 2024 acquisition.
    BackupProduct("Dropsuite / NinjaOne SaaS Backup", (r"\bdropsuite\b", r"ninjaone.*backup")),
    # Barracuda's Email Protection apps read mail as well; require "backup".
    BackupProduct("Barracuda Cloud-to-Cloud Backup", (r"barracuda.*backup",)),
    # Spanning Backup (Kaseya); no published app id.
    BackupProduct("Spanning Backup", (r"\bspanning\b",)),
    # SkyKick also sells migration tooling; require "backup".
    BackupProduct("SkyKick Cloud Backup", (r"skykick.*backup",)),
    # Commvault's SaaS backup, sold as Metallic and now as Commvault Cloud.
    BackupProduct("Commvault Metallic", (r"\bcommvault\b", r"\bmetallic\b")),
    # Druva inSync / Druva Microsoft 365 backup; no published app id.
    BackupProduct("Druva", (r"\bdruva\b",)),
    # CloudAlly; no published app id.
    BackupProduct("CloudAlly", (r"\bcloudally\b",)),
    # Synology Active Backup for Microsoft 365 registers an app per NAS.
    BackupProduct("Synology Active Backup", (r"\bsynology\b", r"active\s*backup\s+for")),
    # Redstor; no published app id.
    BackupProduct("Redstor", (r"\bredstor\b",)),
    # Hornetsecurity 365 Total Backup, formerly Altaro Office 365 Backup.
    # Hornetsecurity's e-mail security apps read mail too; require "backup".
    BackupProduct(
        "Hornetsecurity 365 Total Backup",
        (r"hornetsecurity.*backup", r"365\s+total\s+backup", r"\baltaro\b"),
    ),
    # N-able Cove Data Protection (Microsoft 365 backup).
    BackupProduct("N-able Cove Data Protection", (r"cove\s+data\s+protection", r"n-able.*backup")),
    # Rubrik's Microsoft 365 protection; no published app id.
    BackupProduct("Rubrik", (r"\brubrik\b",)),
    # Cohesity DataProtect for Microsoft 365; no published app id.
    BackupProduct("Cohesity", (r"\bcohesity\b",)),
    # Afi.ai backup; no published app id.
    BackupProduct("Afi Backup", (r"\bafi\.ai\b", r"\bafi\s+backup\b")),
    # Arcserve SaaS Backup; no published app id.
    BackupProduct("Arcserve", (r"\barcserve\b",)),
    # Unitrends Backup for Microsoft 365 (Kaseya).
    BackupProduct("Unitrends", (r"\bunitrends\b",)),
    # Carbonite (OpenText) Backup for Microsoft 365.
    BackupProduct("Carbonite", (r"\bcarbonite\b",)),
    # CrashPlan for Microsoft 365.
    BackupProduct("CrashPlan", (r"\bcrashplan\b",)),
    # Kaseya 365 Backup, Kaseya's bundle around Spanning and Datto.
    BackupProduct("Kaseya 365 Backup", (r"kaseya.*backup",)),
    # Anything else calling itself a backup. Kept only when it holds access to
    # mail, files or chats, and never for Microsoft's own service principals
    # (Microsoft 365 Backup's first-party apps are the native service above).
    BackupProduct(None, (r"\bback\s?-?up\b",)),
)

# The tenants Microsoft's first-party apps are registered in. A service
# principal owned by one of these is Microsoft's, never a third-party product.
# Both are named in "Verify first-party Microsoft applications in sign-in
# reports": f8cdef31-… is the Microsoft Services tenant, 72f988bf-… the tenant
# of Microsoft's own tenant-owned applications.
# https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/governance/verify-first-party-apps-sign-in
_MICROSOFT_OWNER_TENANTS = {
    "f8cdef31-a31e-4b4a-93e4-5f571e91255a",
    "72f988bf-86f1-41af-91ab-2d7cd011db47",
}

# The permissions that reach each workload's data, application or delegated,
# on Microsoft Graph, Exchange Online or SharePoint Online. Files.* and
# Sites.* reach OneDrive as well as SharePoint: a OneDrive is a SharePoint
# site. Sites.Selected is left out: it reaches only the sites an admin picked.
_WORKLOAD_PERMISSIONS: dict[str, frozenset[str]] = {
    "exchange": frozenset(
        {
            "Mail.Read",
            "Mail.ReadWrite",
            "MailboxItem.Read.All",
            "MailboxItem.ImportExport.All",
            "MailboxFolder.Read.All",
            "MailboxFolder.ReadWrite.All",
            "full_access_as_app",
            "full_access_as_user",
            "EWS.AccessAsUser.All",
        }
    ),
    "onedrive": frozenset(
        {
            "Files.Read.All",
            "Files.ReadWrite.All",
            "Sites.Read.All",
            "Sites.ReadWrite.All",
            "Sites.Manage.All",
            "Sites.FullControl.All",
            "AllSites.Read",
            "AllSites.Write",
            "AllSites.FullControl",
        }
    ),
    "teams": frozenset({"ChannelMessage.Read.All", "Chat.Read.All", "Chat.ReadWrite.All"}),
}
_WORKLOAD_PERMISSIONS["sharepoint"] = _WORKLOAD_PERMISSIONS["onedrive"]

# How many matched apps get their permissions read. A tenant with more apps
# called "backup" than this is unusual; the rest are recorded as not read.
_MAX_APPS_READ = 25

# The resources whose app-only grants the access scan lists, addressed by
# application id as "GET /servicePrincipals(appId='{appId}')/appRoleAssignedTo"
# allows (Application.Read.All). Microsoft Graph carries Mail.*, Files.* and
# Sites.*; Exchange Online carries full_access_as_app, the EWS role mailbox
# backup products use. Both ids are the resourceAppId values in Microsoft's
# Exchange Online app-only manifest example.
# https://learn.microsoft.com/en-us/graph/api/serviceprincipal-list-approleassignedto
# https://learn.microsoft.com/en-us/powershell/exchange/app-only-auth-powershell-v2
# SharePoint's own REST resource is not listed: a product that reads sites only
# through it, and mail only through EWS, is found by name or not at all.
_ACCESS_SCAN_RESOURCES = (GRAPH_APP_ID, EXO_APP_ID)


def _verified_publisher(sp: dict) -> str:
    """The Microsoft-verified publisher's name, or "" when there is none.

    ``verifiedPublisher`` is always present and all null for an unverified app,
    so the publisher counts only when it carries the publisher's Partner Center
    id. The name is the one on that Partner Center account.
    https://learn.microsoft.com/en-us/graph/api/resources/verifiedpublisher
    """
    verified = sp.get("verifiedPublisher") or {}
    if not isinstance(verified, dict) or not verified.get("verifiedPublisherId"):
        return ""
    return str(verified.get("displayName") or "")


def match_product(sp: dict) -> tuple[BackupProduct, str] | None:
    """The backup product a service principal belongs to, and how it matched.

    ("app_id" | "publisher" | "name" | "generic"), or None for an app that is
    not one. The access tier is not decided here: it needs the app's grants.
    """
    app_id = (sp.get("appId") or "").lower()
    owner = (sp.get("appOwnerOrganizationId") or "").lower()
    publisher = _verified_publisher(sp)
    names = " ".join(n for n in (sp.get("displayName"), sp.get("appDisplayName")) if n)
    for product in BACKUP_PRODUCTS:
        if app_id and app_id in (a.lower() for a in product.app_ids):
            return product, "app_id"
        # The catch-all says nothing about a vendor, so a publisher with
        # "backup" in its name is no more a product than its other apps are.
        if (
            product.name is not None
            and publisher
            and owner not in _MICROSOFT_OWNER_TENANTS
            and any(re.search(p, publisher, re.IGNORECASE) for p in product.patterns)
        ):
            return product, "publisher"
        if not any(re.search(p, names, re.IGNORECASE) for p in product.patterns):
            continue
        if product.name is not None:
            return product, "name"
        if owner in _MICROSOFT_OWNER_TENANTS:
            return None
        return product, "generic"
    return None


def workloads_reached(permissions: list[str]) -> list[str]:
    """The workloads these permission values reach, in report order."""
    granted = set(permissions)
    return [w for w in WORKLOADS if granted & _WORKLOAD_PERMISSIONS[w]]


def has_backup_scope(permissions: list[str]) -> bool:
    """Whether these app-only permissions are what a backup product needs.

    Every mailbox and every site or drive. An app with only one of the two is
    a mail filter, an archiver or a file tool, and is not a candidate.
    """
    reached = workloads_reached(permissions)
    return "exchange" in reached and ("onedrive" in reached or "sharepoint" in reached)


# ── Reading a refusal ─────────────────────────────────────────────────────────


def _failure(err: Exception) -> tuple[str, str]:
    """(kind, detail) for a read that failed: never a reading of "nothing".

    kind is "permission" (401/403), "licence" (a 403 whose body names a
    missing licence), "not_found" (404) or "error" (anything else).
    """
    if isinstance(err, GraphPermissionError):
        if err.is_service_registration_gap:
            return "not_registered", str(err)[:400]
        return ("licence" if err.is_licence_gap else "permission"), str(err)[:400]
    if isinstance(err, httpx.HTTPStatusError) and err.response is not None:
        status = err.response.status_code
        try:
            body = err.response.json().get("error") or {}
        except ValueError:
            body = {}
        said = f" {body.get('code', '')}: {body.get('message', '')}" if body else ""
        kind = "not_found" if status == 404 else "error"
        return kind, f"HTTP {status}{said}"[:400]
    return "error", f"{type(err).__name__}: {err}"[:400]


# ── The section ───────────────────────────────────────────────────────────────


class M365BackupSection(BaseSection):
    name = "Microsoft 365 Backup"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            native = await self._native()
            third_party = await self._third_party()
            self._write(native, third_party)
            self._warn_findings(native, third_party)
            if (
                not native["service"]["read"]
                and not native["policies"]["read"]
                and not (third_party["read"])
            ):
                # Nothing at all could be read: the section has no reading.
                self._report(
                    SectionStatus.FAILED,
                    "Neither Microsoft 365 Backup nor the service principals could be read",
                )
            else:
                self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Microsoft 365 Backup ──────────────────────────────────────────────────

    async def _native(self) -> dict:
        service: dict = {
            "read": False,
            "status": "",
            "disable_reason": "",
            "consumer": "",
            "error_kind": "",
            "error": "",
        }
        try:
            root = await self.graph.get("solutions/backupRestore")
            status = root.get("serviceStatus") or {}
            service.update(
                read=True,
                status=str(status.get("status") or ""),
                disable_reason=str(status.get("disableReason") or ""),
                consumer=str(status.get("backupServiceConsumer") or ""),
            )
        except Exception as ex:
            service["error_kind"], service["error"] = _failure(ex)

        # Read whatever the service status said: the policies need their own
        # permission, and a disabled or locked service still lists the
        # policies it had, which is worth showing beside the status.
        policies: dict = {"read": False, "error_kind": "", "error": "", "items": []}
        try:
            raw = await self.graph.get_all("solutions/backupRestore/protectionPolicies")
            policies["read"] = True
        except Exception as ex:
            raw = []
            policies["error_kind"], policies["error"] = _failure(ex)
        for item in raw:
            policies["items"].append(await self._policy(item))
        return {"service": service, "policies": policies}

    async def _policy(self, item: dict) -> dict:
        odata_type = str(item.get("@odata.type") or "")
        workload = _POLICY_TYPES.get(odata_type, "")
        policy = {
            "id": str(item.get("id") or ""),
            "name": str(item.get("displayName") or ""),
            "type": odata_type,
            "workload": workload,
            "status": str(item.get("status") or ""),
            "mode": "",
            "retention": [
                {"interval": r.get("interval"), "period": r.get("period")}
                for r in item.get("retentionSettings") or []
                if isinstance(r, dict)
            ],
            "units": {
                "read": False,
                "source": "",
                "total": None,
                "protected": None,
                "in_progress": None,
                "failed": None,
                "error_kind": "",
                "error": "",
            },
        }
        if not policy["id"]:
            return policy
        units = policy["units"]

        # One beta call gives the counts and the mode. It is beta, so when it
        # fails or leaves the count out, the v1.0 unit listing stands in.
        try:
            detail = await self.graph.get(
                f"solutions/backupRestore/protectionPolicies/{policy['id']}",
                beta=True,
                params={"$select": "id,status,protectionMode,protectionPolicyArtifactCount"},
            )
        except Exception:
            logger.debug("No artifact count for policy %s", policy["id"], exc_info=True)
            detail = {}
        policy["mode"] = str(detail.get("protectionMode") or "")
        counts = detail.get("protectionPolicyArtifactCount")
        if isinstance(counts, dict) and isinstance(counts.get("total"), int):
            units.update(
                read=True,
                source="artifact_count",
                total=int(counts.get("total") or 0),
                protected=int(counts.get("completed") or 0),
                in_progress=int(counts.get("inProgress") or 0),
                failed=int(counts.get("failed") or 0),
            )
            return policy

        if workload not in _UNIT_COLLECTIONS:
            return policy
        collection, relation = _UNIT_COLLECTIONS[workload]
        try:
            listed = await self.graph.get_all(
                f"solutions/backupRestore/{collection}/{policy['id']}/{relation}"
            )
        except Exception as ex:
            units["error_kind"], units["error"] = _failure(ex)
            return policy
        protected = in_progress = failed = 0
        for unit in listed:
            state = str(unit.get("status") or "").lower()
            if unit.get("error"):
                failed += 1
            elif state == "protected":
                protected += 1
            elif state == "protectrequested":
                in_progress += 1
            elif state not in _UNIT_NOT_PROTECTED:
                logger.debug("Unknown protection unit status %r", state)
        units.update(
            read=True,
            source="protection_units",
            total=len(listed),
            protected=protected,
            in_progress=in_progress,
            failed=failed,
        )
        return policy

    # ── Third-party products ──────────────────────────────────────────────────

    async def _third_party(self) -> dict:
        found: dict = {
            "read": False,
            "error_kind": "",
            "error": "",
            "scanned": 0,
            "access_scan": {"read": False, "error_kind": "", "error": ""},
            "apps": [],
        }
        try:
            principals = await self.graph.get_all(
                "servicePrincipals",
                params={
                    "$select": (
                        "id,appId,displayName,appDisplayName,appOwnerOrganizationId,"
                        "accountEnabled,servicePrincipalType,verifiedPublisher,publisherName"
                    ),
                    "$top": "999",
                },
            )
        except Exception as ex:
            found["error_kind"], found["error"] = _failure(ex)
            found["access_scan"]["error_kind"] = found["error_kind"]
            return found
        found["read"] = True
        found["scanned"] = len(principals)

        role_names: dict[str, dict[str, str]] = {}
        resource_names: dict[str, str] = {}
        broad = await self._access_scan(found["access_scan"], role_names, resource_names)
        reads = 0
        for sp in principals:
            if (sp.get("servicePrincipalType") or "") == "ManagedIdentity":
                continue
            sp_id = str(sp.get("id") or "")
            owner = (sp.get("appOwnerOrganizationId") or "").lower()
            matched = match_product(sp)
            if matched is not None:
                product_name, how = matched[0].name, matched[1]
            elif (
                sp_id in broad
                and owner not in _MICROSOFT_OWNER_TENANTS
                and has_backup_scope([p["value"] for p in broad[sp_id]])
            ):
                product_name, how = None, "access"
            else:
                continue
            app = {
                "product": product_name,
                "display_name": str(sp.get("displayName") or sp.get("appDisplayName") or ""),
                "app_id": str(sp.get("appId") or ""),
                "sp_id": sp_id,
                "enabled": sp.get("accountEnabled") is not False,
                "match": how,
                "publisher": _verified_publisher(sp),
                "publisher_name": str(sp.get("publisherName") or ""),
                "permissions_read": False,
                "permissions_error": "",
                "application_permissions": [],
                "delegated_scopes": [],
                "workloads": [],
            }
            if how == "access":
                # Already read from the resource side, which is what made it a
                # candidate; the per-app read below adds the rest when it can.
                self._set_permissions(app, broad[sp_id], [])
            if reads < _MAX_APPS_READ:
                reads += 1
                await self._permissions(app, role_names, resource_names)
            elif not app["permissions_read"]:
                # Not read, and why, as a number the report words: more
                # matching apps than the audit reads. It was an English phrase.
                app["permissions_skipped"] = _MAX_APPS_READ
            # A catch-all match is a backup product only if it reaches the data.
            if how == "generic" and app["permissions_read"] and not app["workloads"]:
                continue
            found["apps"].append(app)
        return found

    async def _access_scan(
        self,
        scan: dict,
        role_names: dict[str, dict[str, str]],
        resource_names: dict[str, str],
    ) -> dict[str, list[dict]]:
        """{service principal id: app-only permissions} on Graph and Exchange Online.

        Records in ``scan`` whether it could be read. A failed scan leaves the
        name tiers standing, as they stood before this scan existed, and the
        report notes that an unnamed app may have been missed.
        """
        granted: dict[str, list[dict]] = {}
        try:
            for app_id in _ACCESS_SCAN_RESOURCES:
                assignments = await self.graph.get_all(
                    f"servicePrincipals(appId='{app_id}')/appRoleAssignedTo"
                )
                for assignment in assignments:
                    if (assignment.get("principalType") or "") != "ServicePrincipal":
                        continue
                    resource_id = str(assignment.get("resourceId") or "")
                    roles = await self._resource_roles(resource_id, role_names, resource_names)
                    if not roles:
                        # Every grant would stay a GUID and none could qualify:
                        # that is a scan that did not happen, not one that
                        # found nothing.
                        scan["error_kind"] = "error"
                        scan["error"] = f"the app roles of resource {resource_id} could not be read"
                        return {}
                    role_id = str(assignment.get("appRoleId") or "")
                    granted.setdefault(str(assignment.get("principalId") or ""), []).append(
                        {
                            "value": roles.get(role_id, "") or role_id,
                            "resource": str(
                                assignment.get("resourceDisplayName")
                                or resource_names.get(resource_id)
                                or ""
                            ),
                        }
                    )
        except Exception as ex:
            scan["error_kind"], scan["error"] = _failure(ex)
            return {}
        scan["read"] = True
        return granted

    @staticmethod
    def _set_permissions(app: dict, application: list[dict], delegated: list[dict]) -> None:
        app["application_permissions"] = application
        app["delegated_scopes"] = delegated
        app["permissions_read"] = True
        app["permissions_error"] = ""
        values = [p["value"] for p in application + delegated]
        app["workloads"] = workloads_reached(values)

    async def _permissions(
        self, app: dict, role_names: dict[str, dict[str, str]], resource_names: dict[str, str]
    ) -> None:
        """Fill in what the app may read: its app roles and delegated grants.

        A failed read leaves whatever the app already carried, so an access
        candidate keeps the grants the resource side showed.
        """
        sp_id = app["sp_id"]
        try:
            assignments = await self.graph.get_all(f"servicePrincipals/{sp_id}/appRoleAssignments")
            grants = await self.graph.get_all(f"servicePrincipals/{sp_id}/oauth2PermissionGrants")
        except Exception as ex:
            if not app["permissions_read"]:
                app["permissions_error"] = _failure(ex)[1]
            return

        application: list[dict] = []
        delegated: list[dict] = []
        for assignment in assignments:
            resource_id = str(assignment.get("resourceId") or "")
            roles = await self._resource_roles(resource_id, role_names, resource_names)
            value = roles.get(str(assignment.get("appRoleId") or ""), "")
            resource = str(
                assignment.get("resourceDisplayName") or resource_names.get(resource_id) or ""
            )
            application.append(
                {"value": value or str(assignment.get("appRoleId") or ""), "resource": resource}
            )
        for grant in grants:
            resource_id = str(grant.get("resourceId") or "")
            if resource_id not in resource_names:
                await self._resource_roles(resource_id, role_names, resource_names)
            for scope in str(grant.get("scope") or "").split():
                delegated.append({"value": scope, "resource": resource_names.get(resource_id, "")})
        self._set_permissions(app, application, delegated)

    async def _resource_roles(
        self,
        resource_id: str,
        role_names: dict[str, dict[str, str]],
        resource_names: dict[str, str],
    ) -> dict[str, str]:
        """{app role id: permission value} for one resource service principal, cached."""
        if not resource_id:
            return {}
        if resource_id not in role_names:
            try:
                resource = await self.graph.get(
                    f"servicePrincipals/{resource_id}",
                    params={"$select": "id,appId,displayName,appRoles"},
                )
            except Exception:
                # The role stays a GUID; the app is still listed with it.
                logger.debug("Could not resolve app roles of %s", resource_id, exc_info=True)
                resource = {}
            role_names[resource_id] = {
                str(r.get("id") or ""): str(r.get("value") or "")
                for r in resource.get("appRoles") or []
            }
            resource_names[resource_id] = str(resource.get("displayName") or "")
        return role_names[resource_id]

    # ── Output ────────────────────────────────────────────────────────────────

    def _write(self, native: dict, third_party: dict) -> None:
        width = 100
        service, policies = native["service"], native["policies"]
        lines = [
            "=" * width,
            "  MICROSOFT 365 BACKUP  (mailboxes, OneDrive, SharePoint, Teams)",
            "=" * width,
            "",
            "  NATIVE: MICROSOFT 365 BACKUP",
            "  " + "-" * (width - 4),
        ]
        if service["read"]:
            lines += [
                f"  Service status    : {service['status'] or 'unknown'}",
                f"  Disable reason    : {service['disable_reason'] or 'none'}",
                f"  Controlled by     : {service['consumer'] or 'unknown'}",
            ]
        else:
            lines += [
                f"  Service status    : unreadable ({service['error_kind']})",
                f"  Service detail    : {service['error']}",
                f"  Needs             : {SERVICE_PERMISSION}",
            ]
        if policies["read"]:
            lines.append(f"  Policies          : {len(policies['items'])}")
            for p in policies["items"]:
                units = p["units"]
                if units["read"]:
                    counts = (
                        f"protected={units['protected']} in_progress={units['in_progress']} "
                        f"failed={units['failed']} total={units['total']}"
                    )
                else:
                    counts = f"units unreadable ({units['error_kind'] or 'unknown'})"
                lines.append(
                    f"    {p['workload'] or 'unknown'} | {p['status'] or 'unknown'} | "
                    f"{p['mode'] or 'standard'} | {counts} | {p['name']}"
                )
        else:
            lines += [
                f"  Policies          : unreadable ({policies['error_kind']})",
                f"  Policies detail   : {policies['error']}",
                f"  Needs             : {POLICY_PERMISSION}",
            ]

        lines += ["", "  THIRD-PARTY BACKUP APPS", "  " + "-" * (width - 4)]
        if third_party["read"]:
            lines.append(
                f"  Apps found        : {len(third_party['apps'])} "
                f"(of {third_party['scanned']} service principals)"
            )
            scan = third_party["access_scan"]
            if scan["read"]:
                lines.append("  Access scan       : read")
            else:
                lines += [
                    f"  Access scan       : unreadable ({scan['error_kind']})",
                    f"  Access detail     : {scan['error']}",
                ]
            for app in third_party["apps"]:
                workloads = ",".join(app["workloads"]) if app["permissions_read"] else "unknown"
                lines.append(
                    f"    {app['product'] or app['display_name']} | {app['display_name']} | "
                    f"{'enabled' if app['enabled'] else 'disabled'} | match={app['match']} | "
                    f"workloads={workloads or 'none'} | app_id={app['app_id']}"
                )
                if app["publisher"] or app["publisher_name"]:
                    lines.append(
                        f"      publisher   : verified={app['publisher'] or '(none)'} | "
                        f"tenant={app['publisher_name'] or '(none)'}"
                    )
                if not app["permissions_read"]:
                    if app.get("permissions_skipped"):
                        lines.append(f"      permissions : skipped {app['permissions_skipped']}")
                    else:
                        lines.append(f"      permissions : unreadable ({app['permissions_error']})")
                    continue
                roles = ", ".join(
                    f"{p['resource']}/{p['value']}" for p in app["application_permissions"]
                )
                scopes = ", ".join(f"{p['resource']}/{p['value']}" for p in app["delegated_scopes"])
                lines += [
                    f"      application : {roles or '(none)'}",
                    f"      delegated   : {scopes or '(none)'}",
                ]
        else:
            lines += [
                f"  Apps found        : unreadable ({third_party['error_kind']})",
                f"  Apps detail       : {third_party['error']}",
            ]
        lines += ["", "=" * width, ""]
        self._save("34_m365_backup.txt", "\n".join(lines))
        self._save_sidecar("34_m365_backup.txt", {"native": native, "third_party": third_party})

    def _warn_findings(self, native: dict, third_party: dict) -> None:
        service, policies = native["service"], native["policies"]
        if not service["read"]:
            detail = (
                f"it needs {SERVICE_PERMISSION}"
                if service["error_kind"] == "permission"
                else service["error"]
            )
            self._warn(
                f"Microsoft 365 Backup status could not be read ({service['error_kind']}); "
                f"{detail}",
                level="info",
            )
        elif service["status"] in ("protectionChangeLocked", "restoreLocked"):
            self._warn(
                f"Microsoft 365 Backup is {service['status']}: no protection changes are "
                f"possible (reason: {service['disable_reason'] or 'unknown'})"
            )
        if not policies["read"]:
            detail = (
                f"they need {POLICY_PERMISSION}"
                if policies["error_kind"] == "permission"
                else policies["error"]
            )
            self._warn(
                f"Microsoft 365 Backup policies could not be read ({policies['error_kind']}); "
                f"{detail}",
                level="info",
            )
        if not third_party["read"]:
            self._warn(
                f"Service principals could not be read for backup apps "
                f"({third_party['error_kind']})",
                level="info",
            )
            return
        scan = third_party.get("access_scan") or {}
        if scan and not scan.get("read"):
            self._warn(
                "The scan for unnamed apps with backup-like access could not be read "
                f"({scan.get('error_kind')}); a renamed backup app may be missed",
                level="info",
            )
        for app in third_party.get("apps") or []:
            if app["match"] == "access" and app["enabled"]:
                self._warn(
                    f"{app['display_name']} holds app-only read access to every mailbox and "
                    "site, as a backup product does, but is not a known one; check what it is",
                    level="info",
                )
