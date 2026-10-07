"""Bounded CA setting checks over captured data; no claim of effective coverage.

Schema: https://learn.microsoft.com/graph/api/conditionalaccesspolicy-get
Assignments, exclusions, emergency access and sign-in outcomes require review.
"""

from __future__ import annotations

from typing import Any


def captured_checks(policies: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for recommendation, control in (("ca-mfa", "mfa"), ("ca-legacy", "block")):
        if policies is None:
            out[recommendation] = {"state": "unmeasured", "matches": []}
            continue
        matches = []
        for policy in policies:
            conditions = policy.get("conditions") or {}
            grants = policy.get("grantControls") or {}
            controls = grants.get("builtInControls") or []
            if control not in controls or (
                grants.get("operator") != "AND"
                and (
                    controls != [control]
                    or grants.get("authenticationStrength")
                    or grants.get("customAuthenticationFactors")
                    or grants.get("termsOfUse")
                )
            ):
                continue
            if (conditions.get("users") or {}).get("includeUsers") != ["All"]:
                continue
            if (conditions.get("applications") or {}).get("includeApplications") != ["All"]:
                continue
            clients = set(conditions.get("clientAppTypes") or [])
            if recommendation == "ca-mfa" and clients != {"all"}:
                continue
            if recommendation == "ca-legacy" and not {"exchangeActiveSync", "other"} <= clients:
                continue
            # A conditional match never establishes the broad baseline.
            restricted = any(
                conditions.get(key)
                for key in (
                    "locations",
                    "platforms",
                    "devices",
                    "userRiskLevels",
                    "signInRiskLevels",
                    "servicePrincipalRiskLevels",
                    "authenticationFlows",
                    "clientApplications",
                )
            )
            if restricted:
                continue
            matches.append(
                {
                    "id": str(policy.get("id") or ""),
                    "name": str(policy.get("displayName") or ""),
                    "state": str(policy.get("state") or "unknown"),
                }
            )
        out[recommendation] = {
            "state": "settings_found" if matches else "no_match",
            "matches": matches,
        }
    return out
