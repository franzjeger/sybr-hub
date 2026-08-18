"""Section 33 — Viva Engage (Yammer) usage: is the social layer used or just on?

Viva Engage is the rebranded Yammer, and Microsoft kept the *old* name on the
Graph reporting endpoints — the data comes from ``getYammerActivityUserDetail``.
For an audit the interesting question is not the message count, it is whether
the tenant has an enterprise social network switched on that nobody governs: a
provisioned, licensed surface with no activity is an open door with no one
watching it, and it belongs on the findings list next to any other unused-but-
enabled service.

Two states are deliberately kept apart. An *empty* report — Graph answered, and
there is simply nothing — means Viva Engage is not in use (never provisioned,
unlicensed, or dormant for the period), which is a clean 'not in use' signal,
not a failure. A *refused* report means the app registration could not read it,
which is reported as unavailable so a reader never mistakes 'we could not look'
for 'there is nothing there'. Needs only Reports.Read.All, which the audit app
already holds — no extra consent for this section.

The Microsoft 365 admin centre setting that conceals user names in usage reports
applies here too, exactly as it does to section 16; it is detected from the rows
(a principal name with no @) and stated in the output rather than left to look
like corrupt data.
"""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient, GraphPermissionError

# A quarter: long enough that "no activity" means dormant, not on leave.
_PERIOD = "D90"
_INACTIVE_DAYS = 90


def _num(row: dict, key: str) -> int:
    """A count column, parsed. get_report leaves these as strings."""
    try:
        return int(str(row.get(key) or "0").replace(",", "").strip() or "0")
    except ValueError:
        return 0


def _is_deleted(row: dict) -> bool:
    """The Yammer report marks removed users with userState, older shapes with
    isDeleted — honour either so a deleted account is never counted as active."""
    if row.get("isDeleted") is True:
        return True
    return str(row.get("userState") or "").strip().lower() == "deleted"


def _has_activity(row: dict) -> bool:
    if str(row.get("lastActivityDate") or "").strip():
        return True
    return any(_num(row, k) > 0 for k in ("postedCount", "readCount", "likedCount"))


class VivaEngageSection(BaseSection):
    name = "Viva Engage"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph
        self._failures: list[str] = []

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_activity()
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

    async def _collect_activity(self) -> None:
        try:
            rows = await self.graph.get_report("getYammerActivityUserDetail", _PERIOD)
        except Exception as ex:
            self._save_unavailable(
                "33_viva_engage_activity.txt", "VIVA ENGAGE (YAMMER) ACTIVITY", ex
            )
            self._warn(f"Viva Engage usage report fetch failed: {ex}")
            return

        live = [r for r in rows if not _is_deleted(r)]
        deleted = len(rows) - len(live)
        active = [r for r in live if _has_activity(r)]
        posters = [r for r in live if _num(r, "postedCount") > 0]
        inactive = [r for r in live if not _has_activity(r)]

        # Names concealed at the tenant level come back without an @ (section 16).
        names = [str(r.get("userPrincipalName") or "") for r in live]
        concealed = bool(names) and not any("@" in n for n in names)
        in_use = bool(active)

        lines = [
            "=" * 110,
            f"  VIVA ENGAGE (YAMMER) ACTIVITY  (last {_INACTIVE_DAYS} days, {len(rows)} rows)",
            "=" * 110,
            "",
        ]
        if not rows:
            lines += [
                "  No Viva Engage activity was reported for this period. The service",
                "  is not in use in this tenant — never provisioned, not licensed, or",
                "  dormant for the whole window. This is a clean 'not in use' result,",
                "  not a collection failure.",
                "",
                "=" * 110,
                "",
            ]
            self._save("33_viva_engage_activity.txt", "\n".join(lines))
        else:
            if concealed:
                lines += [
                    "  NOTE: this tenant conceals user names in usage reports, so the",
                    "  principal names below are opaque identifiers. The counts are",
                    "  accurate; the names cannot be matched to people until the setting",
                    "  'Reports: display concealed user information' is turned off in the",
                    "  Microsoft 365 admin centre.",
                    "",
                ]
            lines += [
                f"  {'User':<45} {'Last activity':<14} {'Posted':>7} {'Read':>7} {'Liked':>7}",
                "  " + "-" * 106,
            ]
            for r in sorted(live, key=lambda x: str(x.get("lastActivityDate") or "")):
                upn = str(r.get("userPrincipalName") or "")[:45]
                last = str(r.get("lastActivityDate") or "never")
                lines.append(
                    f"  {upn:<45} {last:<14} "
                    f"{_num(r, 'postedCount'):>7} {_num(r, 'readCount'):>7} "
                    f"{_num(r, 'likedCount'):>7}"
                )
            lines += ["=" * 110, ""]
            self._save("33_viva_engage_activity.txt", "\n".join(lines))

        count_lines = [
            "VIVA ENGAGE (YAMMER) USAGE SUMMARY",
            f"Period days: {_INACTIVE_DAYS}",
            f"Total users in report: {len(rows)}",
            f"Deleted: {deleted}",
            f"Active (any activity): {len(active)}",
            f"Posters (created content): {len(posters)}",
            f"Present but inactive: {len(inactive)}",
            f"Names concealed: {'yes' if concealed else 'no'}",
            f"In use: {'yes' if in_use else 'no'}",
        ]
        self._save("33_viva_engage_summary.txt", "\n".join(count_lines))

        # A provisioned-but-silent social network is the finding worth raising:
        # it is enabled and nobody uses it, so it is an ungoverned surface to
        # adopt deliberately or switch off. An empty report is not that — it is
        # simply not turned on, and warns nothing.
        if rows and not active:
            self._warn(
                f"Viva Engage is provisioned ({len(live)} users in scope) but shows "
                f"no activity in the last {_INACTIVE_DAYS} days — enabled but unused."
            )
