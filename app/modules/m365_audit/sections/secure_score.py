"""Section 09 — Secure Score, Auth Methods Policy, Auth Strength."""

from __future__ import annotations

import logging
from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient

logger = logging.getLogger(__name__)


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

        # Improvement actions: what is left to do, ordered by what it is worth.
        #
        # This sorted by scoreInPercentage *descending* and called the result
        # "Top 20 Improvement Actions (by impact)". scoreInPercentage is how
        # much of a control's own maximum the tenant has already earned, so
        # 100% means fully implemented and nothing to improve. The list was the
        # twenty things the customer had already done — every row 100.0% — put
        # under a heading telling them to go and do those things.
        #
        # "By impact" needs the points at stake, which controlScores does not
        # carry; secureScoreControlProfiles does. A control at 50% of thirty
        # points is worth more than one at 0% of one point, and ordering by
        # percentage alone cannot see that.
        ctrl_scores = latest.get("controlScores", [])
        max_by_control = await self._control_max_scores()

        ranked: list[tuple[float, float, str, str]] = []
        for ctrl in ctrl_scores:
            name = (ctrl.get("controlName") or "").strip()
            if not name:
                continue
            ctrl_pct = float(ctrl.get("scoreInPercentage") or 0.0)
            if ctrl_pct >= 100:
                continue  # done; there is no improvement to make
            ctrl_max = max_by_control.get(name)
            remaining = (
                ctrl_max * (1 - ctrl_pct / 100) if ctrl_max is not None else None
            )
            # Without the profiles, fall back to "furthest from done". Sorting
            # by -pct keeps that ordering while the ranked tuple stays uniform.
            sort_key = remaining if remaining is not None else (100 - ctrl_pct) / 100
            ranked.append((sort_key, ctrl_pct, name[:50], ctrl.get("controlCategory") or ""))

        ranked.sort(key=lambda r: r[0], reverse=True)
        by_impact = bool(max_by_control)

        lines = [
            "=" * 80,
            "  SECURE SCORE",
            "=" * 80,
            f"  Score         : {current:.1f} / {max_sc:.1f}  ({pct:.1f}%)",
            f"  As of         : {created}",
            "",
            "  Top 20 Improvement Actions "
            + ("(by points still available):" if by_impact else "(by how far from done):"),
            f"  {'Control':<50} {'Score%':>7}  {'Left':>6}  {'Category'}",
            "  " + "-" * 76,
        ]

        if not ranked:
            lines.append("  (none — every scored control is fully implemented)")

        for sort_key, ctrl_pct, ctrl_name, ctrl_cat in ranked[:20]:
            left = f"{sort_key:.1f}" if by_impact else "-"
            lines.append(f"  {ctrl_name:<50} {ctrl_pct:>6.1f}%  {left:>6}  {ctrl_cat}")

        lines += ["=" * 80, ""]
        self._save("09_secure_score.txt", "\n".join(lines))

    async def _control_max_scores(self) -> dict[str, float]:
        """Points each control is worth, keyed by control name.

        controlScores says how much of a control the tenant has earned, never
        how much it was worth. Without this, "by impact" cannot mean anything
        more than "by percentage". An empty dict is the honest answer when the
        profiles cannot be read, and the caller says so in the heading rather
        than presenting a different ordering under the same words.
        """
        try:
            profiles = await self.graph.get_all("security/secureScoreControlProfiles")
        except Exception as ex:
            logger.warning("Secure Score control profiles unavailable: %s", ex)
            return {}
        out: dict[str, float] = {}
        for prof in profiles or []:
            name = (prof.get("id") or prof.get("controlName") or "").strip()
            try:
                out[name] = float(prof.get("maxScore") or 0.0)
            except (TypeError, ValueError):
                continue
        return {k: v for k, v in out.items() if k and v > 0}

    # ── Auth Methods Policy ───────────────────────────────────────────────────

    async def _collect_auth_methods_policy(self) -> None:
        try:
            data = await self.graph.get("policies/authenticationMethodsPolicy")
        except Exception as ex:
            self._save(
                "09b_auth_methods_policy.txt",
                # "Error:" is the codebase-wide unavailable-evidence sentinel the
                # report's info-guards key on — keep the prefix exact.
                f"Error: authentication methods policy fetch failed: {ex}\n",
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
