"""Section 26 — Microsoft Compliance Manager: Compliance score & improvement actions."""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class ComplianceScoreSection(BaseSection):
    name = "Compliance Score"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_compliance_score()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Compliance Score ─────────────────────────────────────────────────────

    async def _collect_compliance_score(self) -> None:
        # The score figures always come from security/secureScores. The
        # Compliance Manager eDiscovery probe below only confirms that the
        # compliance API is reachable; it does not return score data, so it
        # must not be named as the source of the numbers.
        scores = None
        source = ""

        # Attempt 1: Compliance Manager (requires ComplianceManager.Read.All)
        try:
            await self.graph.get(
                "compliance/ediscovery/cases",
                params={"$top": "1"},
            )
            # Accessible — note it, but it is not where the scores come from.
        except Exception:
            pass  # Expected if permissions not granted

        # Attempt 2: secureScores with compliance focus
        try:
            data   = await self.graph.get(
                "security/secureScores",
                params={"$top": "5"},
            )
            scores = data.get("value", [])
            source = "secureScores"
        except Exception as ex:
            self._save(
                "26_compliance_score.txt",
                f"Error fetching compliance data: {ex}\n"
                "Note: Requires SecurityEvents.Read.All or ComplianceManager.Read.All.\n",
            )
            return

        if not scores:
            self._save("26_compliance_score.txt", "No compliance score data available.\n")
            return

        # Use the latest score entry
        latest    = max(scores, key=lambda s: s.get("createdDateTime", ""))
        current   = latest.get("currentScore", 0)
        max_score = latest.get("maxScore", 0)
        pct       = (current / max_score * 100) if max_score else 0.0
        created   = latest.get("createdDateTime", "N/A")

        # Extract compliance-related control scores
        ctrl_scores = latest.get("controlScores", [])
        compliance_controls = [
            c for c in ctrl_scores
            if "compliance" in (c.get("controlCategory") or "").lower()
            or "data" in (c.get("controlCategory") or "").lower()
            or "information" in (c.get("controlCategory") or "").lower()
        ]

        # Sort all controls by score percentage (ascending = worst first)
        sorted_ctrl = sorted(
            ctrl_scores,
            key=lambda c: c.get("scoreInPercentage", 0),
        )

        lines = [
            "=" * 90,
            "  MICROSOFT COMPLIANCE SCORE",
            "=" * 90,
            f"  Overall Score : {current:.1f} / {max_score:.1f}  ({pct:.1f}%)",
            f"  As of         : {created}",
            f"  Data source   : {source}",
            "",
        ]

        # Compliance-specific controls
        if compliance_controls:
            lines += [
                f"  ── Compliance-Related Controls ({len(compliance_controls)} found) ──",
                f"  {'Control':<50} {'Score%':>7}  {'Category'}",
                "  " + "-" * 86,
            ]
            for ctrl in sorted(compliance_controls, key=lambda c: c.get("scoreInPercentage", 0)):
                ctrl_name = (ctrl.get("controlName") or "")[:50]
                ctrl_pct  = ctrl.get("scoreInPercentage", 0)
                ctrl_cat  = ctrl.get("controlCategory") or ""
                lines.append(f"  {ctrl_name:<50} {ctrl_pct:>6.1f}%  {ctrl_cat}")
            lines.append("")

        # Top 20 improvement actions (lowest scores first)
        lines += [
            f"  ── Top 20 Improvement Actions (lowest scores first) ──",
            f"  {'Control':<50} {'Score%':>7}  {'Category'}",
            "  " + "-" * 86,
        ]
        for ctrl in sorted_ctrl[:20]:
            ctrl_name = (ctrl.get("controlName") or "")[:50]
            ctrl_pct  = ctrl.get("scoreInPercentage", 0)
            ctrl_cat  = ctrl.get("controlCategory") or ""
            lines.append(f"  {ctrl_name:<50} {ctrl_pct:>6.1f}%  {ctrl_cat}")

        lines += ["=" * 90, ""]
        self._save("26_compliance_score.txt", "\n".join(lines))

        # Warnings
        if pct < 50:
            self._warn(
                f"Compliance score is critically low: {pct:.1f}% ({current:.1f}/{max_score:.1f})"
            )
        elif pct < 70:
            self._warn(
                f"Compliance score is below recommended threshold: {pct:.1f}%"
            )

        # Warn about controls with 0% score
        zero_controls = [c for c in ctrl_scores if c.get("scoreInPercentage", 0) == 0]
        if zero_controls:
            self._warn(
                f"{len(zero_controls)} compliance control(s) have 0% score — critical improvement actions pending"
            )
