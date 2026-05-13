"""Section 08 — Conditional Access Policies and Named Locations."""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


def _summarise_conditions(cond: dict) -> str:
    users = cond.get("users", {})
    apps  = cond.get("applications", {})

    inc_users = users.get("includeUsers", [])
    inc_apps  = apps.get("includeApplications", [])

    u_str = "All" if "All" in inc_users else f"{len(inc_users)} user(s)"
    a_str = "All" if "All" in inc_apps else f"{len(inc_apps)} app(s)"
    return u_str, a_str


class ConditionalAccessSection(BaseSection):
    name = "Conditional Access"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph
        self.policies: list[dict] = []  # raw policies for downstream use

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_policies()
            await self._collect_named_locations()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Policies ──────────────────────────────────────────────────────────────

    async def _collect_policies(self) -> None:
        try:
            policies = await self.graph.get_all(
                "identity/conditionalAccess/policies",
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save("08_conditional_access.txt", f"Error fetching CA policies: {ex}\n")
            self._warn(f"Conditional Access policies fetch failed: {ex}")
            return

        self.policies = policies  # store for downstream use (MFA analysis)

        # Resolve group IDs to names for readability
        group_ids: set[str] = set()
        for policy in policies:
            cond = policy.get("conditions", {}).get("users", {})
            group_ids.update(cond.get("includeGroups", []))
            group_ids.update(cond.get("excludeGroups", []))

        group_names: dict[str, str] = {}
        for gid in group_ids:
            try:
                g = await self.graph.get(f"groups/{gid}", params={"$select": "displayName"})
                group_names[gid] = g.get("displayName", gid)
            except Exception:
                group_names[gid] = gid

        lines = [
            "=" * 120,
            "  CONDITIONAL ACCESS POLICIES",
            "=" * 120,
            f"  {'State':<12} {'Policy Name':<45} {'Users':<25} {'Groups':<25} {'Apps'}",
            "  " + "-" * 116,
        ]

        emergency_exclusions: list[str] = []

        for policy in policies:
            state    = policy.get("state", "unknown")
            name     = (policy.get("displayName") or "")[:45]
            cond     = policy.get("conditions", {})
            u_str, a_str = _summarise_conditions(cond)

            # Resolve included groups
            inc_groups = cond.get("users", {}).get("includeGroups", [])
            if inc_groups:
                g_names = [group_names.get(g, g)[:20] for g in inc_groups[:3]]
                g_str = ", ".join(g_names)
                if len(inc_groups) > 3:
                    g_str += f" +{len(inc_groups)-3}"
            else:
                g_str = "-"

            flag = ""
            if state == "disabled":
                flag = "  *** DISABLED ***"
                self._warn(f"CA policy '{name}' is in disabled state")

            lines.append(f"  [{state:<10}] {name:<45} {u_str:<25} {g_str:<25} {a_str}{flag}")

            # Grant controls summary
            grants = policy.get("grantControls") or {}
            controls = grants.get("builtInControls", [])
            if controls:
                lines.append(f"  {'':>12} Grant controls: {', '.join(controls)}")

            # Check for emergency access exclusions
            exc_users = cond.get("users", {}).get("excludeUsers", [])
            exc_groups = cond.get("users", {}).get("excludeGroups", [])
            if exc_users:
                emergency_exclusions.append(
                    f"  Policy '{name}' excludes user IDs: {', '.join(exc_users[:5])}"
                    + (f" ... +{len(exc_users)-5} more" if len(exc_users) > 5 else "")
                )
            if exc_groups:
                exc_g_names = [group_names.get(g, g) for g in exc_groups[:5]]
                emergency_exclusions.append(
                    f"  Policy '{name}' excludes groups: {', '.join(exc_g_names)}"
                )

        lines += ["", "  Emergency / Break-Glass User Exclusions:"]
        if emergency_exclusions:
            lines += emergency_exclusions
        else:
            lines.append("  (none detected)")
        lines += ["=" * 120, ""]
        self._save("08_conditional_access.txt", "\n".join(lines))

    # ── Named Locations ───────────────────────────────────────────────────────

    async def _collect_named_locations(self) -> None:
        try:
            locs = await self.graph.get_all(
                "identity/conditionalAccess/namedLocations",
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save(
                "08b_conditional_access_named_locations.txt",
                f"Error fetching named locations: {ex}\n",
            )
            self._warn(f"Conditional Access named locations fetch failed: {ex}")
            return

        lines = [
            "=" * 100,
            "  CONDITIONAL ACCESS NAMED LOCATIONS",
            "=" * 100,
            f"  {'Name':<40} {'Type':<20} {'Trusted':>8}  Details",
            "  " + "-" * 96,
        ]

        for loc in locs:
            odata   = loc.get("@odata.type", "")
            name    = (loc.get("displayName") or "")[:40]
            trusted = "Yes" if loc.get("isTrusted") else "No"

            if "ipNamedLocation" in odata:
                loc_type = "IP Range"
                ranges   = loc.get("ipRanges", [])
                details  = ", ".join(r.get("cidrAddress", "") for r in ranges[:5])
                if len(ranges) > 5:
                    details += f" ... +{len(ranges)-5} more"
            elif "countryNamedLocation" in odata:
                loc_type = "Country"
                details  = ", ".join(loc.get("countriesAndRegions", []))
            else:
                loc_type = odata.split(".")[-1]
                details  = ""

            lines.append(
                f"  {name:<40} {loc_type:<20} {trusted:>8}  {details}"
            )

        lines += ["=" * 100, ""]
        self._save("08b_conditional_access_named_locations.txt", "\n".join(lines))
