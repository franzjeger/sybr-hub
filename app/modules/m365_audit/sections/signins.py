"""Section 05 — Sign-in Activity (last 30 days)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient, GraphPermissionError

_FAILURE_THRESHOLD = 50

# auditLogs/signIns is gated on the tenant's Entra ID tier, not on a Graph
# permission: AuditLog.Read.All can be granted and consented and the endpoint
# will still answer 403 on a tenant without P1. Saying so is the difference
# between an actionable finding — this customer should be on P1 — and sending a
# technician to look for a consent that is already in place.
_TIER_REQUIREMENT = "Microsoft Entra ID P1 (or P2)"


class SignInsSection(BaseSection):
    name = "Sign-in Activity"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    def _save_unavailable(self, err: GraphPermissionError) -> None:
        """Record *why* there is no sign-in data, in both output files.

        Without this the section simply wrote nothing, the report found no
        file, and the whole sign-in analysis disappeared from the document —
        not even as "not measured". A reader could not tell it had been tried.
        """
        if err.is_licence_gap:
            cause = [
                f"  auditLogs/signIns requires {_TIER_REQUIREMENT}, and Graph refused",
                f"  the request with {err.status} reporting a licence gap — this tenant",
                "  does not have that tier.",
            ]
        else:
            cause = [
                f"  Graph refused the request with {err.status}. The app registration is",
                "  missing AuditLog.Read.All or its admin consent.",
                "",
                f"  Note: this endpoint also requires {_TIER_REQUIREMENT}, so granting the",
                "  permission alone will not make it readable on a tenant without it.",
            ]
        detail = ["", "  Error details for troubleshooting:", f"    {err}", ""]

        for name, title, width in (
            ("05_signin_activity.txt", "SIGN-IN ACTIVITY", 90),
            ("05b_signin_failures.txt", "SIGN-IN FAILURES", 70),
        ):
            self._save(name, "\n".join([
                "=" * width, f"  {title}  (not available)", "=" * width, "",
                *cause, *detail, "=" * width, "",
            ]))

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            since = (
                datetime.now(timezone.utc) - timedelta(days=30)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

            signins = await self.graph.get_all(
                "auditLogs/signIns",
                params={
                    "$filter": f"createdDateTime ge {since}",
                    "$top":    "999",
                },
            )

            # Aggregate by UPN. Note: `status.errorCode == 0` is the only
            # signal that a sign-in succeeded — a missing errorCode (the
            # field is absent or the whole status object is null) means
            # "we don't know", which we count separately rather than
            # defaulting to success. Counting unknowns as success is what
            # produced under-reported failure totals in v10.10.
            success_counts: dict[str, int] = defaultdict(int)
            failure_counts: dict[str, int] = defaultdict(int)
            unknown_counts: dict[str, int] = defaultdict(int)

            for s in signins:
                upn = s.get("userPrincipalName") or "(unknown)"
                status = s.get("status") or {}
                if "errorCode" not in status:
                    unknown_counts[upn] += 1
                elif status["errorCode"] == 0:
                    success_counts[upn] += 1
                else:
                    failure_counts[upn] += 1

            total_unknown = sum(unknown_counts.values())
            if total_unknown:
                self._warn(
                    f"{total_unknown} sign-in event(s) had no status.errorCode "
                    "— success/failure cannot be determined for those events"
                )

            # ── Sign-in activity file ─────────────────────────────────────────
            all_upns = set(success_counts) | set(failure_counts) | set(unknown_counts)
            sorted_upns = sorted(
                all_upns,
                key=lambda u: (
                    success_counts[u] + failure_counts[u] + unknown_counts[u]
                ),
                reverse=True,
            )

            header = (
                f"  {'UPN':<50} {'Success':>8} {'Failures':>9} "
                f"{'Unknown':>8} {'Total':>6}"
            )
            lines = [
                "=" * 90,
                f"  SIGN-IN ACTIVITY  (last 30 days — {len(signins)} events)",
                "=" * 90,
                header,
                "  " + "-" * 86,
            ]
            if total_unknown:
                lines.append(
                    f"  NOTE: {total_unknown} event(s) had no status.errorCode; "
                    "see 'Unknown' column below."
                )
            for upn in sorted_upns:
                s_cnt = success_counts[upn]
                f_cnt = failure_counts[upn]
                u_cnt = unknown_counts[upn]
                lines.append(
                    f"  {upn:<50} {s_cnt:>8} {f_cnt:>9} {u_cnt:>8} "
                    f"{s_cnt + f_cnt + u_cnt:>6}"
                )
            lines += ["=" * 90, ""]
            self._save("05_signin_activity.txt", "\n".join(lines))

            # ── Failure file ──────────────────────────────────────────────────
            failed_upns = sorted(
                failure_counts.keys(), key=lambda u: failure_counts[u], reverse=True
            )
            fail_lines = [
                "=" * 70,
                "  SIGN-IN FAILURES  (last 30 days, error code != 0)",
                "=" * 70,
                f"  {'UPN':<50} {'Failures':>9}",
                "  " + "-" * 66,
            ]
            for upn in failed_upns:
                cnt = failure_counts[upn]
                flag = "  *** THRESHOLD EXCEEDED ***" if cnt > _FAILURE_THRESHOLD else ""
                fail_lines.append(f"  {upn:<50} {cnt:>9}{flag}")
                if cnt > _FAILURE_THRESHOLD:
                    self._warn(
                        f"User '{upn}' had {cnt} sign-in failures in the last 30 days"
                    )
            fail_lines += ["=" * 70, ""]
            self._save("05b_signin_failures.txt", "\n".join(fail_lines))

            self._report(SectionStatus.DONE)
        except GraphPermissionError as e:
            # Still FAILED: the tenant's sign-in posture was not measured, and
            # nothing downstream may read the explanation below as a zero.
            self._save_unavailable(e)
            self._warn(str(e))
            self._report(SectionStatus.FAILED, str(e))
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result
