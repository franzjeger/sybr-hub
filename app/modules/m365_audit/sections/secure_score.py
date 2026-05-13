"""Section 09 — Secure Score, Auth Methods Policy, Auth Strength."""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class SecureScoreSection(BaseSection):
    name = "Secure Score"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_score()
            await self._collect_auth_methods_policy()
            await self._collect_auth_strength_policies()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Secure Score ──────────────────────────────────────────────────────────

    async def _collect_score(self) -> None:
        try:
            data   = await self.graph.get(
                "security/secureScores", params={"$top": "5"}
            )
            scores = data.get("value", [])
        except Exception as ex:
            self._save("09_secure_score.txt", f"Error fetching secure score: {ex}\n")
            return

        if not scores:
            self._save("09_secure_score.txt", "No secure score data available.\n")
            return

        # Pick latest
        latest = max(scores, key=lambda s: s.get("createdDateTime", ""))
        current = latest.get("currentScore", 0)
        max_sc  = latest.get("maxScore", 0)
        pct     = (current / max_sc * 100) if max_sc else 0.0
        created = latest.get("createdDateTime", "N/A")

        # Sort improvement actions by impact (score impact descending)
        ctrl_scores = latest.get("controlScores", [])
        sorted_ctrl = sorted(
            ctrl_scores,
            key=lambda c: c.get("scoreInPercentage", 0),
            reverse=True,
        )

        lines = [
            "=" * 80,
            "  SECURE SCORE",
            "=" * 80,
            f"  Score         : {current:.1f} / {max_sc:.1f}  ({pct:.1f}%)",
            f"  As of         : {created}",
            "",
            "  Top 20 Improvement Actions (by impact):",
            f"  {'Control':<50} {'Score%':>7}  {'Category'}",
            "  " + "-" * 76,
        ]

        for ctrl in sorted_ctrl[:20]:
            ctrl_name  = (ctrl.get("controlName") or "")[:50]
            ctrl_pct   = ctrl.get("scoreInPercentage", 0)
            ctrl_cat   = ctrl.get("controlCategory") or ""
            lines.append(f"  {ctrl_name:<50} {ctrl_pct:>6.1f}%  {ctrl_cat}")

        lines += ["=" * 80, ""]
        self._save("09_secure_score.txt", "\n".join(lines))

    # ── Auth Methods Policy ───────────────────────────────────────────────────

    async def _collect_auth_methods_policy(self) -> None:
        try:
            data = await self.graph.get("policies/authenticationMethodsPolicy")
        except Exception as ex:
            self._save(
                "09b_auth_methods_policy.txt",
                f"Error fetching authentication methods policy: {ex}\n",
            )
            return

        configs = data.get("authenticationMethodConfigurations", [])
        lines = [
            "=" * 70,
            "  AUTHENTICATION METHODS POLICY",
            "=" * 70,
            f"  {'Method':<40} {'State'}",
            "  " + "-" * 66,
        ]
        for cfg in configs:
            method = cfg.get("@odata.type", cfg.get("id", "Unknown"))
            method = method.split(".")[-1].replace("AuthenticationMethodConfiguration", "")
            state  = cfg.get("state", "unknown")
            lines.append(f"  {method:<40} {state}")
        lines += ["=" * 70, ""]
        self._save("09b_auth_methods_policy.txt", "\n".join(lines))

    # ── Auth Strength Policies ────────────────────────────────────────────────

    async def _collect_auth_strength_policies(self) -> None:
        try:
            policies = await self.graph.get_all(
                "identity/conditionalAccess/authenticationStrength/policies",
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save(
                "09c_auth_strength_policies.txt",
                f"Error fetching authentication strength policies: {ex}\n",
            )
            self._warn(f"Authentication strength policies fetch failed: {ex}")
            return

        lines = [
            "=" * 90,
            "  AUTHENTICATION STRENGTH POLICIES",
            "=" * 90,
            f"  {'Policy Name':<40} {'Policy Type':<20} {'Allowed Combinations'}",
            "  " + "-" * 86,
        ]
        for p in policies:
            name   = (p.get("displayName") or "")[:40]
            ptype  = p.get("policyType", "custom")[:20]
            combos = ", ".join(p.get("allowedCombinations", []))[:60]
            lines.append(f"  {name:<40} {ptype:<20} {combos}")
        lines += ["=" * 90, ""]
        self._save("09c_auth_strength_policies.txt", "\n".join(lines))
