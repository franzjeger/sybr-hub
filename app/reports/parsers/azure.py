"""Parsers for the Azure section files: inventory, VMs and backup coverage."""

from __future__ import annotations

import json
import re

from app.reports.parsers.common import _find_azure_files, _find_azure_json, _sidecar

# A protected item in one of these states is not backing the VM up: it was
# stopped, paused or suspended, or never valid. Its recovery points may still
# exist, but nothing new is being taken.
_BACKUP_INACTIVE_STATES = {"protectionstopped", "protectionpaused", "backupssuspended", "invalid"}


# The VM listing trims names to this width. A legacy run without the JSON
# sidecar can only match a trimmed name by prefix.
_VM_NAME_WIDTH = 35


def _by_subscription(file_contents: dict[str, str], prefix: str) -> dict[str, tuple[str, str]]:
    """{subscription suffix: (kind, content)} for one collector's files.

    A multi-subscription run writes one file per subscription, named with a
    suffix ("" for a single-subscription run). Each subscription is read from
    its JSON sidecar when it has one and from its text file otherwise: a
    subscription whose read failed writes only the text error, and must not be
    hidden by another subscription's sidecar.
    """
    picked: dict[str, tuple[str, str]] = {}
    for fname, content, sub in _find_azure_files(file_contents, prefix):
        if "cpu_metrics" not in fname:
            picked[sub] = ("text", content)
    for fname, content, sub in _find_azure_json(file_contents, prefix):
        if "cpu_metrics" not in fname:
            picked[sub] = ("json", content)
    return picked


def _vm_inventory(file_contents: dict[str, str]) -> list[dict]:
    """Every VM, as {"name", "id", "sub"}."""
    vms: list[dict] = []
    for sub, (kind, content) in _by_subscription(file_contents, "30_azure_vms").items():
        if kind == "json":
            try:
                data = json.loads(content)
            except ValueError:
                continue
            for vm in data.get("vms") or []:
                if vm.get("name"):
                    vms.append({"name": vm["name"], "id": (vm.get("id") or "").lower(), "sub": sub})
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("=")
                or stripped.startswith("-")
                or "VM Name" in stripped
                or "AZURE VIRTUAL" in stripped
                or stripped.startswith("Error")
            ):
                continue
            cols = re.split(r"\s{2,}", stripped)
            if len(cols) >= 4:
                vms.append({"name": cols[0], "id": "", "sub": sub})
    return vms


def _backup_inventory(file_contents: dict[str, str]) -> dict:
    """What the vaults protect, per subscription.

    {sub: {"read", "complete", "vaults", "items"}}. read: the vault data was
    read (an empty read counts). complete: every vault's item list was read in
    full; when it was not, a VM missing from the list may still be protected.
    """
    out: dict[str, dict] = {}
    for sub, (kind, content) in _by_subscription(file_contents, "52_azure_backup").items():
        found: dict = {"read": False, "complete": True, "vaults": set(), "items": []}
        out[sub] = found
        if kind == "json":
            try:
                data = json.loads(content)
            except ValueError:
                continue
            found["read"] = True
            for vault in data.get("vaults") or []:
                found["vaults"].add(vault.get("name") or "")
                if vault.get("items_error"):
                    found["complete"] = False
                for item in vault.get("items") or []:
                    state = (item.get("protection_state") or "").lower()
                    found["items"].append(
                        {
                            "name": (item.get("friendly_name") or item.get("name") or "").lower(),
                            "id": (item.get("source_resource_id") or "").lower(),
                            "active": state not in _BACKUP_INACTIVE_STATES,
                        }
                    )
            continue

        # A run from before the sidecar. This is the format _collect_backup
        # writes: a "Vault    : name" block per vault, then "      - <name>
        # Status:..." per protected item. The item lines start with "-", and an
        # earlier parser skipped every line that did, so it read no items at
        # all and listed every VM as unprotected.
        if not content.strip() or content.strip().startswith("Error:"):
            continue
        found["read"] = True
        for line in content.splitlines():
            stripped = line.strip()
            vault = re.match(r"Vault\s*:\s*(.+)$", stripped)
            if vault:
                found["vaults"].add(vault.group(1).strip())
            elif stripped.startswith("Protected Items:") and "Error" in stripped:
                found["complete"] = False
            elif re.match(r"\.\.\. and \d+ more items", stripped):
                # Listings were cut at 15 items per vault.
                found["complete"] = False
            elif stripped.startswith("- "):
                name = re.split(r"\s{2,}", stripped[2:].strip())[0]
                state = re.search(r"State:(\S+)", stripped)
                active = not state or state.group(1).lower() not in _BACKUP_INACTIVE_STATES
                found["items"].append({"name": name.lower(), "id": "", "active": active})
    return out


def _match_item(vm: dict, items: list[dict]) -> dict | None:
    """The item protecting this VM, among its own subscription's items.

    By resource id when both sides carry one. By name only against items that
    carry no id (a run from before the sidecar): a name is not unique, and a
    protected VM of the same name must not cover one that has no backup.
    """
    if vm["id"]:
        for item in items:
            if item["id"] == vm["id"]:
                return item
    name = vm["name"].lower()
    nameless = [item for item in items if not item["id"]]
    for item in nameless:
        if item["name"] == name:
            return item
    if len(vm["name"]) == _VM_NAME_WIDTH:
        return next((item for item in nameless if item["name"].startswith(name)), None)
    return None


def _parse_backup_coverage(file_contents: dict[str, str]) -> dict:
    """Cross-reference Azure VMs with the items the backup vaults protect.

    Coverage is a cross-reference between two independently collected files.
    If the backup half was not read, every VM would fall into
    vms_not_backed_up: a high-priority "these servers have no backup" finding,
    naming each one, from a file nobody read. So coverage is only known when
    every subscription that has VMs had its vault data read, completely or
    with all its VMs found in it. An empty *successful* read is a real finding.

    A VM is matched only against its own subscription's items. An item whose
    protection was stopped, paused or suspended does not count: nothing new is
    being backed up.
    """
    vms = _vm_inventory(file_contents)
    backup = _backup_inventory(file_contents)
    none: dict = {"read": False, "complete": True, "vaults": set(), "items": []}
    matched = [_match_item(vm, backup.get(vm["sub"], none)["items"]) for vm in vms]

    def known(sub: str) -> bool:
        found = backup.get(sub, none)
        if not found["read"]:
            return False
        if found["complete"]:
            return True
        return all(
            item is not None for vm, item in zip(vms, matched, strict=True) if vm["sub"] == sub
        )

    vms_total = len(vms)
    coverage_known = vms_total > 0 and all(known(sub) for sub in {vm["sub"] for vm in vms})

    vms_backed_up = 0
    vms_not_backed_up: list[str] = []
    vms_backup_stopped: list[str] = []
    if coverage_known:
        for vm, item in zip(vms, matched, strict=True):
            if item is not None and item["active"]:
                vms_backed_up += 1
            else:
                vms_not_backed_up.append(vm["name"])
                if item is not None:
                    vms_backup_stopped.append(vm["name"])

    backup_pct = (vms_backed_up / vms_total * 100) if coverage_known else 0.0
    vaults = {(sub, name) for sub, found in backup.items() for name in found["vaults"]}

    return {
        "vms_total": vms_total,
        "vms_backed_up": vms_backed_up,
        "vms_not_backed_up": vms_not_backed_up,  # empty unless coverage_known
        "vms_backup_stopped": vms_backup_stopped,  # a subset of the above
        "backup_pct": round(backup_pct, 1),
        "vaults": len(vaults),
        "coverage_known": coverage_known,
        "has_data": vms_total > 0 or len(vaults) > 0,
    }


def _vm_rows(sidecar: dict | None) -> list[dict] | None:
    """The VM table from a 30_azure_vms sidecar, or None to read the text.

    A sidecar from v1.2.0 carries only each VM's name and id, for the backup
    cross-reference; the rest of the table is in its text.
    """
    if sidecar is None:
        return None
    vms = sidecar.get("vms") or []
    if not all("location" in vm for vm in vms):
        return None
    return [
        {
            "name": vm.get("name") or "",
            "rg": vm.get("resource_group") or "N/A",
            "location": vm.get("location") or "",
            "os": vm.get("os_type") or "N/A",
            "size": vm.get("size") or "N/A",
            "status": vm.get("power_state") or "N/A",
        }
        for vm in vms
    ]


def _orphan_detail(orphan: dict) -> str:
    """One orphan from the 61 sidecar, worded as the text's line after the colon."""
    parts = [orphan.get("name") or ""]
    if "size_gb" in orphan:
        parts += [f"{orphan.get('size_gb') or 0} GB", orphan.get("sku") or "N/A"]
    if "ip_address" in orphan:
        parts.append(f"IP: {orphan.get('ip_address') or 'unassigned'}")
    parts.append(f"RG: {orphan.get('resource_group') or 'N/A'}")
    return "  ".join(parts)


def _parse_azure_overview(file_contents: dict[str, str]) -> dict:
    """Parse Azure data files into a structured overview.

    Supports both single-subscription (e.g. 30_azure_vms.txt) and
    multi-subscription (e.g. 30_azure_vms_Corp-Backend-01.txt) file naming.
    Aggregates data across all subscriptions.
    """
    result: dict = {
        "subscriptions": [],
        "per_sub": [],  # per-subscription breakdown
        "total_resources": 0,
        "resource_types": {},  # type -> count (aggregated)
        "resource_groups": [],
        "vms": [],
        "storage_accounts": [],
        "nsgs": [],
        "advisor_recs": 0,
        "advisor_details": [],  # list of {"category", "impact", "description", "resource", "subscription"}
        "orphaned": 0,
        "orphaned_details": [],  # list of {"type", "name", "detail", "subscription"}
        "has_data": False,
    }

    # ── Subscriptions ──────────────────────────────────────────────────────
    sub_text = file_contents.get("45_azure_subscriptions.txt", "")
    for line in sub_text.splitlines():
        line = line.strip()
        if (
            not line
            or line.startswith("=")
            or line.startswith("NOTE")
            or line.startswith("Falling")
            or line.startswith("To audit")
            or line.startswith("AZURE SUB")
        ):
            continue
        if "[" in line and "]" in line:
            parts = line.rsplit("[", 1)
            state = parts[1].rstrip("]").strip()
            name_id = parts[0].strip()
            m = re.search(
                r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", name_id
            )
            if m:
                sub_id = m.group(1)
                name = name_id[: m.start()].strip()
                result["subscriptions"].append({"name": name, "id": sub_id, "state": state})

    # ── Resource inventory (aggregate across all subs) ─────────────────────
    for fname, content, sub_name in _find_azure_files(
        file_contents, "60_azure_resource_inventory_summary"
    ):
        sub_resources = 0
        sub_types: dict[str, int] = {}
        sub_rgs: list[dict] = []
        in_types = False
        in_rgs = False

        inventory = _sidecar(file_contents, fname)
        if inventory is not None:
            sub_resources = int(inventory.get("total") or 0)
            for row in inventory.get("by_type") or []:
                name, count = row.get("type") or "", int(row.get("count") or 0)
                sub_types[name] = sub_types.get(name, 0) + count
                result["resource_types"][name] = result["resource_types"].get(name, 0) + count
            for row in inventory.get("by_resource_group") or []:
                name, count = row.get("name") or "", int(row.get("count") or 0)
                sub_rgs.append({"name": name, "count": count})
                result["resource_groups"].append(
                    {"name": f"{name} ({sub_name})" if sub_name else name, "count": count}
                )
            content = ""  # every figure came from the sidecar: no text to read

        for line in content.splitlines():
            if "By Type:" in line:
                in_types = True
                in_rgs = False
                continue
            elif "By Resource Group:" in line:
                in_rgs = True
                in_types = False
                continue
            elif line.strip().startswith("=") or line.strip().startswith("-") or not line.strip():
                continue
            elif "AZURE RESOURCE" in line:
                m = re.search(r"\((\d+) resources?\)", line)
                if m:
                    sub_resources = int(m.group(1))
                continue

            parts = line.rsplit(None, 1)
            if len(parts) == 2:
                try:
                    count = int(parts[1])
                    name = parts[0].strip()
                    if in_types and name and name not in ("Type", "Count"):
                        sub_types[name] = sub_types.get(name, 0) + count
                        result["resource_types"][name] = (
                            result["resource_types"].get(name, 0) + count
                        )
                    elif in_rgs and name and name not in ("Resource Group", "Count"):
                        sub_rgs.append({"name": name, "count": count})
                        result["resource_groups"].append(
                            {"name": f"{name} ({sub_name})" if sub_name else name, "count": count}
                        )
                except ValueError:
                    pass

        result["total_resources"] += sub_resources
        if sub_resources > 0 or sub_types:
            result["per_sub"].append(
                {
                    "name": sub_name or "Default",
                    "resources": sub_resources,
                    "types": sorted(sub_types.items(), key=lambda x: -x[1]),
                    "rgs": sub_rgs,
                }
            )

    # ── VMs (aggregate across all subs) ────────────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "30_azure_vms"):
        if "cpu_metrics" in fname:
            continue
        rows = _vm_rows(_sidecar(file_contents, fname))
        if rows is not None:
            result["vms"] += [{**row, "subscription": sub_name} for row in rows]
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("=")
                or stripped.startswith("-")
                or "VM Name" in stripped
                or "AZURE VIRTUAL" in stripped
            ):
                continue
            cols = re.split(r"\s{2,}", stripped)
            if len(cols) >= 4:
                result["vms"].append(
                    {
                        "name": cols[0],
                        "rg": cols[1] if len(cols) > 1 else "",
                        "location": cols[2] if len(cols) > 2 else "",
                        "os": cols[3] if len(cols) > 3 else "",
                        "size": cols[4] if len(cols) > 4 else "",
                        "status": cols[5] if len(cols) > 5 else "",
                        "subscription": sub_name,
                    }
                )

    # ── Storage accounts ───────────────────────────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "35_azure_storage"):
        storage = _sidecar(file_contents, fname)
        if storage is not None:
            result["storage_accounts"] += [
                {
                    "name": account.get("name") or "",
                    "sku": account.get("sku") or "N/A",
                    "kind": account.get("kind") or "N/A",
                    "subscription": sub_name,
                }
                for account in storage.get("accounts") or []
            ]
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("=")
                or stripped.startswith("-")
                or "Account Name" in stripped
                or "AZURE STORAGE" in stripped
            ):
                continue
            cols = re.split(r"\s{2,}", stripped)
            if len(cols) >= 3:
                result["storage_accounts"].append(
                    {
                        "name": cols[0],
                        "sku": cols[1] if len(cols) > 1 else "",
                        "kind": cols[2] if len(cols) > 2 else "",
                        "subscription": sub_name,
                    }
                )

    # ── NSGs ───────────────────────────────────────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "32_azure_nsgs"):
        if "risky" in fname or "WARN" in fname:
            continue
        nsgs = _sidecar(file_contents, fname)
        if nsgs is not None:
            if int(nsgs.get("count") or 0) > 0:
                result["nsgs"].append({"subscription": sub_name, "count": int(nsgs["count"])})
            continue
        m = re.search(r"\((\d+) total\)", content)
        if m and int(m.group(1)) > 0:
            result["nsgs"].append({"subscription": sub_name, "count": int(m.group(1))})

    # ── Advisor recommendations (with details) ──────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "51_azure_advisor"):
        advisor = _sidecar(file_contents, fname)
        if advisor is not None:
            result["advisor_recs"] += int(advisor.get("count") or 0)
            result["advisor_details"] += [
                {
                    "category": rec.get("category") or "General",
                    "impact": rec.get("impact") or "Medium",
                    "description": rec.get("description") or "N/A",
                    "resource": rec.get("resource") or "N/A",
                    "subscription": sub_name,
                }
                for rec in advisor.get("recommendations") or []
            ]
            continue
        m = re.search(r"\((\d+) total\)", content)
        if m:
            result["advisor_recs"] += int(m.group(1))

        # Parse individual recommendations
        current_category = ""
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Category header: "[Cost]  (16 recommendations)"
            cat_m = re.match(r"\[(\w+)\]", line)
            if cat_m:
                current_category = cat_m.group(1)
                i += 1
                continue
            # Recommendation: "    [High    ]  Description text"
            rec_m = re.match(r"\[(\w+)\s*\]\s+(.+)", line)
            if rec_m:
                impact = rec_m.group(1)
                desc = rec_m.group(2).strip()
                resource = ""
                # Next line might be "Resource: ..."
                if i + 1 < len(lines) and "Resource:" in lines[i + 1]:
                    resource = lines[i + 1].strip().replace("Resource:", "").strip()
                    i += 1
                result["advisor_details"].append(
                    {
                        "category": current_category,
                        "impact": impact,
                        "description": desc,
                        "resource": resource,
                        "subscription": sub_name,
                    }
                )
            i += 1

    # Deduplicate advisor details (same description counted once, with count)
    seen: dict[str, dict] = {}
    for ad in result["advisor_details"]:
        key = f"{ad['category']}|{ad['description']}"
        if key in seen:
            seen[key]["count"] += 1
        else:
            seen[key] = {**ad, "count": 1}
    result["advisor_summary"] = sorted(
        seen.values(),
        key=lambda x: ({"High": 0, "Medium": 1, "Low": 2}.get(x["impact"], 3), x["category"]),
    )

    # ── Orphaned resources (with details) ──────────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "61_azure_orphaned_resources"):
        orphans = _sidecar(file_contents, fname)
        if orphans is not None:
            result["orphaned"] += int(orphans.get("count") or 0)
            result["orphaned_details"] += [
                {
                    "type": orphan.get("type") or "",
                    "status": orphan.get("status") or "",
                    "detail": _orphan_detail(orphan),
                    "subscription": sub_name,
                }
                for orphan in orphans.get("orphans") or []
            ]
            continue
        m = re.search(r"\((\d+) found\)", content)
        listed = len(result["orphaned_details"])
        for line in content.splitlines():
            line = line.strip()
            if (
                not line
                or line.startswith("=")
                or line.startswith("No orphaned")
                or "ORPHANED" in line
            ):
                continue
            # Format: "DISK (unattached) : diskname  500 GB  Standard_LRS  RG: rg-name"
            type_m = re.match(r"(\w[\w\s]*?)\s*\((\w+)\)\s*:\s*(.+)", line)
            if type_m:
                result["orphaned_details"].append(
                    {
                        "type": type_m.group(1).strip(),
                        "status": type_m.group(2).strip(),
                        "detail": type_m.group(3).strip(),
                        "subscription": sub_name,
                    }
                )
        if m:
            # No more than the lines that name an orphan. Until the collector
            # was fixed, "(N found)" also counted a listing that failed, whose
            # "DISK (list error)" line names none.
            found = len(result["orphaned_details"]) - listed
            result["orphaned"] += min(int(m.group(1)), found)

    # Convert resource_types dict to sorted list
    result["resource_types_list"] = sorted(
        [{"type": k, "count": v} for k, v in result["resource_types"].items()],
        key=lambda x: -x["count"],
    )

    result["has_data"] = (
        result["total_resources"] > 0 or len(result["vms"]) > 0 or len(result["subscriptions"]) > 0
    )
    return result
