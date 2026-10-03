"""Section 02 — License Inventory."""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class LicensesSection(BaseSection):
    name = "Licenses"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            skus = await self.graph.get_all("subscribedSkus")

            lines = [
                "=" * 70,
                "  LICENSE INVENTORY",
                "=" * 70,
                f"  {'SKU / Part Number':<40} {'Used':>6} {'Total':>6}  {'Pct':>5}  Status",
                "  " + "-" * 66,
            ]
            rows: list[dict] = []

            for sku in skus:
                part = sku.get("skuPartNumber", "Unknown")
                used = sku.get("consumedUnits", 0)
                total = sku.get("prepaidUnits", {}).get("enabled", 0)
                pct = (used / total * 100) if total else 0.0
                status = ""
                if total > 0 and pct >= 90:
                    status = "  *** OVER 90% ***"
                    self._warn(
                        f"License '{part}' is over 90% utilised ({used}/{total} = {pct:.0f}%)"
                    )
                lines.append(f"  {part:<40} {used:>6} {total:>6}  {pct:>4.0f}%{status}")
                rows.append(
                    {
                        "part": part,
                        "sku_id": sku.get("skuId"),
                        "used": used,
                        "total": total,
                        # Unrounded: the table prints whole percents, and a SKU
                        # at 69.6% reads as 70% there.
                        "pct": pct,
                        "warn": total > 0 and used / total >= 0.9,
                    }
                )

            lines += ["=" * 70, ""]
            self._save("02_licenses.txt", "\n".join(lines))
            self._save_sidecar("02_licenses.txt", {"skus": rows})
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result
