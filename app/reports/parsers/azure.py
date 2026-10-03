"""Parsers for the Azure section files: inventory, VMs and backup coverage."""

from __future__ import annotations

import json
import re

from app.reports.parsers.common import _find_azure_files, _find_azure_json

# A protected item in one of these states is not backing the VM up: it was
# stopped, paused or suspended, or never valid. Its recovery points may still
# exist, but nothing new is being taken.
_BACKUP_INACTIVE_STATES = {"protectionstopped", "protectionpaused", "backupssuspended", "invalid"}


# The VM listing trims names to this width. A legacy run without the JSON
# sidecar can only match a trimmed name by prefix.
_VM_NAME_WIDTH = 35


def _vm_inventory(file_contents: dict[str, str]) -> list[dict]:
    """Every VM, as {"name", "id"}. The JSON sidecar when the run wrote one."""
    vms: list[dict] = []
    sidecars = [
        f for f in _find_azure_json(file_contents, "30_azure_vms") if "cpu_metrics" not in f[0]
    ]
    for _fname, content, _sub in sidecars:
        try:
            data = json.loads(content)
        except ValueError:
            continue
        for vm in data.get("vms") or []:
            if vm.get("name"):
                vms.append({"name": vm["name"], "id": (vm.get("id") or "").lower()})
    if sidecars:
        return vms
    for fname, content, _sub in _find_azure_files(file_contents, "30_azure_vms"):
        if "cpu_metrics" in fname:
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
                vms.append({"name": cols[0], "id": ""})
    return vms


def _backup_inventory(file_contents: dict[str, str]) -> dict:
    """What the vaults protect: {"read", "complete", "vaults", "items"}.

    read: some vault data was read successfully (an empty read counts).
    complete: every vault's item list was read in full. When it was not, a VM
    missing from the list may still be protected, so it cannot be named.
    """
    out: dict = {"read": False, "complete": True, "vaults": set(), "items": []}
    sidecars = _find_azure_json(file_contents, "52_azure_backup")
    for _fname, content, _sub in sidecars:
        try:
            data = json.loads(content)
        except ValueError:
            continue
        out["read"] = True
        for vault in data.get("vaults") or []:
            out["vaults"].add(vault.get("name") or "")
            if vault.get("items_error"):
                out["complete"] = False
            for item in vault.get("items") or []:
                state = (item.get("protection_state") or "").lower()
                out["items"].append(
                    {
                        "name": (item.get("friendly_name") or item.get("name") or "").lower(),
                        "id": (item.get("source_resource_id") or "").lower(),
                        "active": state not in _BACKUP_INACTIVE_STATES,
                    }
                )
    if sidecars:
        return out

    # A run from before the sidecar. This is the format _collect_backup writes:
    # a "Vault    : name" block per vault, then "      - <name>  Status:..."
    # per protected item. The item lines start with "-", and an earlier parser
    # skipped every line that did, so it read no items at all and listed every
    # VM as unprotected.
    for _fname, content, _sub in _find_azure_files(file_contents, "52_azure_backup"):
        if not content.strip() or content.strip().startswith("Error:"):
            continue
        out["read"] = True
        for line in content.splitlines():
            stripped = line.strip()
            vault = re.match(r"Vault\s*:\s*(.+)$", stripped)
            if vault:
                out["vaults"].add(vault.group(1).strip())
            elif stripped.startswith("Protected Items:") and "Error" in stripped:
                out["complete"] = False
            elif re.match(r"\.\.\. and \d+ more items", stripped):
                # Listings were cut at 15 items per vault.
                out["complete"] = False
            elif stripped.startswith("- "):
                name = re.split(r"\s{2,}", stripped[2:].strip())[0]
                state = re.search(r"State:(\S+)", stripped)
                active = not state or state.group(1).lower() not in _BACKUP_INACTIVE_STATES
                out["items"].append({"name": name.lower(), "id": "", "active": active})
    return out


def _parse_backup_coverage(file_contents: dict[str, str]) -> dict:
    """Cross-reference Azure VMs with the items the backup vaults protect.

    Coverage is a cross-reference between two independently collected files.
    If the backup half was not read, every VM would fall into
    vms_not_backed_up: a high-priority "these servers have no backup" finding,
    naming each one, from a file nobody read. So coverage is only known when
    the vault data was read, and when the item lists were complete or every VM
    was found in them anyway. An empty *successful* read is a real finding.

    A VM matches an item by resource id when the run recorded ids, otherwise by
    name. An item whose protection was stopped, paused or suspended does not
    count: nothing new is being backed up.
    """
    vms = _vm_inventory(file_contents)
    backup = _backup_inventory(file_contents)
    by_id = {i["id"]: i for i in backup["items"] if i["id"]}
    by_name = {}
    for item in backup["items"]:
        by_name.setdefault(item["name"], item)

    def match(vm: dict) -> dict | None:
        if vm["id"] and vm["id"] in by_id:
            return by_id[vm["id"]]
        name = vm["name"].lower()
        if name in by_name:
            return by_name[name]
        if len(vm["name"]) == _VM_NAME_WIDTH:
            return next((i for n, i in by_name.items() if n.startswith(name)), None)
        return None

    vms_total = len(vms)
    matched = {vm["name"]: match(vm) for vm in vms}
    all_found = bool(vms) and all(item is not None for item in matched.values())
    coverage_known = backup["read"] and vms_total > 0 and (backup["complete"] or all_found)

    vms_backed_up = 0
    vms_not_backed_up: list[str] = []
    vms_backup_stopped: list[str] = []
    if coverage_known:
        for vm in vms:
            item = matched[vm["name"]]
            if item is not None and item["active"]:
                vms_backed_up += 1
            else:
                vms_not_backed_up.append(vm["name"])
                if item is not None:
                    vms_backup_stopped.append(vm["name"])

    backup_pct = (vms_backed_up / vms_total * 100) if coverage_known else 0.0

    return {
        "vms_total": vms_total,
        "vms_backed_up": vms_backed_up,
        "vms_not_backed_up": vms_not_backed_up,  # empty unless coverage_known
        "vms_backup_stopped": vms_backup_stopped,  # a subset of the above
        "backup_pct": round(backup_pct, 1),
        "vaults": len(backup["vaults"]),
        "coverage_known": coverage_known,
        "has_data": vms_total > 0 or len(backup["vaults"]) > 0,
    }


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
    for _fname, content, sub_name in _find_azure_files(
        file_contents, "60_azure_resource_inventory_summary"
    ):
        sub_resources = 0
        sub_types: dict[str, int] = {}
        sub_rgs: list[dict] = []
        in_types = False
        in_rgs = False

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
    for _fname, content, sub_name in _find_azure_files(file_contents, "35_azure_storage"):
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
        m = re.search(r"\((\d+) total\)", content)
        if m and int(m.group(1)) > 0:
            result["nsgs"].append({"subscription": sub_name, "count": int(m.group(1))})

    # ── Advisor recommendations (with details) ──────────────────────────────
    for _fname, content, sub_name in _find_azure_files(file_contents, "51_azure_advisor"):
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
    for _fname, content, sub_name in _find_azure_files(
        file_contents, "61_azure_orphaned_resources"
    ):
        m = re.search(r"\((\d+) found\)", content)
        if m:
            result["orphaned"] += int(m.group(1))
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

    # Convert resource_types dict to sorted list
    result["resource_types_list"] = sorted(
        [{"type": k, "count": v} for k, v in result["resource_types"].items()],
        key=lambda x: -x["count"],
    )

    result["has_data"] = (
        result["total_resources"] > 0 or len(result["vms"]) > 0 or len(result["subscriptions"]) > 0
    )
    return result
