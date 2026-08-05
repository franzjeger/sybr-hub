"""Section 16 — Microsoft 365 usage: which licences are actually being used.

The licence section already says a tenant has 106 Exchange seats and that all
106 are assigned. It cannot say whether anyone signed into them. That gap is
the difference between an inventory and a finding: "you are paying for 106"
is not actionable, "23 of those have had no activity in 90 days" is.

One caveat is worth stating in the output rather than discovering later. The
Microsoft 365 admin centre has a setting that replaces user names in every
usage report with an opaque identifier. When it is on, the per-user rows are
real but unattributable, and a reader who does not know that reads the hashes
as corrupt data. It is detected here from the rows themselves — a
principal name with no @ in it — so no extra permission is needed to say so.
"""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient, GraphPermissionError

# A quarter is long enough that a dormant seat is dormant rather than on leave.
_PERIOD = "D90"
_INACTIVE_DAYS = 90


class UsageReportsSection(BaseSection):
    name = "Usage Reports"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph
        self._failures: list[str] = []

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_active_users()
            if self._failures:
                self._report(SectionStatus.FAILED, "; ".join(self._failures)[:500])
            else:
                self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    def _save_unavailable(self, filename: str, title: str, err: Exception) -> None:
        lines = ["=" * 90, f"  {title}  (not available)", "=" * 90, ""]
        if isinstance(err, GraphPermissionError):
            if err.is_licence_gap:
                lines.append(
                    f"  Graph refused this collection with {err.status}, reporting a "
                    "licence gap."
                )
            else:
                lines.append(
                    f"  Graph refused this collection with {err.status}. The app "
                    "registration is missing Reports.Read.All or its admin consent."
                )
            if err.code or err.message:
                lines += ["", f"  Graph said: {err.code} — {err.message}"[:300]]
        else:
            lines.append("  The collection failed before it could be read.")
        lines += ["", "  Error details for troubleshooting:", f"    {err}", "", "=" * 90, ""]
        self._save(filename, "\n".join(lines))
        self._failures.append(str(err)[:200])

    async def _collect_active_users(self) -> None:
        try:
            rows = await self.graph.get_report("getOffice365ActiveUserDetail", _PERIOD)
        except Exception as ex:
            self._save_unavailable(
                "16_usage_active_users.txt", "MICROSOFT 365 ACTIVE USERS", ex
            )
            self._warn(f"Usage report fetch failed: {ex}")
            return

        # Names concealed at the tenant level come back without an @.
        names = [str(r.get("userPrincipalName") or "") for r in rows]
        concealed = bool(names) and not any("@" in n for n in names)

        activity_fields = (
            "exchangeLastActivityDate", "oneDriveLastActivityDate",
            "sharePointLastActivityDate", "teamsLastActivityDate",
        )

        def last_seen(row: dict) -> str:
            dates = [str(row.get(f) or "") for f in activity_fields]
            dates = [d for d in dates if d]
            return max(dates) if dates else ""

        total = len(rows)
        deleted = sum(1 for r in rows if r.get("isDeleted") is True)
        live = [r for r in rows if r.get("isDeleted") is not True]
        never = [r for r in live if not last_seen(r)]
        licensed_never = [r for r in never if (r.get("assignedProducts") or [])]

        lines = [
            "=" * 110,
            f"  MICROSOFT 365 ACTIVE USERS  (last {_INACTIVE_DAYS} days, {total} rows)",
            "=" * 110,
        ]
        if concealed:
            lines += [
                "",
                "  NOTE: this tenant conceals user names in usage reports, so the",
                "  principal names below are opaque identifiers. The counts are",
                "  accurate; the names cannot be matched to people until the setting",
                "  'Reports: display concealed user information' is turned off in the",
                "  Microsoft 365 admin centre.",
                "",
            ]
        lines += [
            f"  {'User':<45} {'Products':<28} Last activity",
            "  " + "-" * 106,
        ]
        for r in sorted(live, key=lambda x: last_seen(x)):
            products = ", ".join(r.get("assignedProducts") or [])[:28]
            lines.append(
                f"  {str(r.get('userPrincipalName') or '')[:45]:<45} "
                f"{products:<28} {last_seen(r) or 'never'}"
            )
        lines += ["=" * 110, ""]
        self._save("16_usage_active_users.txt", "\n".join(lines))

        count_lines = [
            "MICROSOFT 365 USAGE SUMMARY",
            f"Period days: {_INACTIVE_DAYS}",
            f"Total: {total}",
            f"Deleted: {deleted}",
            f"Active users: {len(live) - len(never)}",
            f"No activity: {len(never)}",
            f"Licensed without activity: {len(licensed_never)}",
            f"Names concealed: {'yes' if concealed else 'no'}",
        ]
        self._save("16_usage_summary.txt", "\n".join(count_lines))

        if licensed_never:
            self._warn(
                f"{len(licensed_never)} licensed users have no activity in the last "
                f"{_INACTIVE_DAYS} days"
            )
