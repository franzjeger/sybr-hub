"""Section — Purview (lightweight).

Sensitivity labels are collected in identity_security.py (19c).
DLP and retention policies are collected in exchange.py (19d, 19e) from EXO data.

This section checks whether those files were already produced by the above sections
and skips if so; otherwise it attempts to re-collect sensitivity labels via Graph.
"""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class PurviewSection(BaseSection):
    name = "Purview"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            already_done = all(
                (self.out_dir / f).exists()
                for f in (
                    "19c_purview_sensitivity_labels.txt",
                    "19d_purview_dlp_policies.txt",
                    "19e_purview_retention_policies.txt",
                )
            )

            if already_done:
                self._report(
                    SectionStatus.SKIPPED,
                    "Purview data already saved by IdentitySecuritySection and ExchangeSection",
                )
                return self.result

            # Fallback: collect sensitivity labels if not already saved
            if not (self.out_dir / "19c_purview_sensitivity_labels.txt").exists():
                await self._collect_sensitivity_labels()

            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    async def _collect_sensitivity_labels(self) -> None:
        try:
            labels = await self.graph.get_all(
                "security/informationProtection/sensitivityLabels",
                beta=True,
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save("19c_purview_sensitivity_labels.txt", f"Error: {ex}\n")
            self._warn(f"Purview sensitivity labels (fallback) fetch failed: {ex}")
            return

        lines = [
            "=" * 90,
            f"  PURVIEW SENSITIVITY LABELS  ({len(labels)} total)",
            "=" * 90,
            f"  {'Label Name':<45} {'Priority':>9} {'Enabled':>8} {'Parent ID'}",
            "  " + "-" * 86,
        ]
        for lbl in labels:
            name     = (lbl.get("name") or "")[:45]
            priority = lbl.get("priority", 0)
            enabled  = "Yes" if lbl.get("isActive") else "No"
            parent   = lbl.get("parent", {}).get("id") or "(top-level)"
            lines.append(f"  {name:<45} {priority:>9} {enabled:>8}  {parent}")
        lines += ["=" * 90, ""]
        self._save("19c_purview_sensitivity_labels.txt", "\n".join(lines))
