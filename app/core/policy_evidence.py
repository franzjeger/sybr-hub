"""Inspect captured Conditional Access and Intune configuration.

Schema: https://learn.microsoft.com/graph/api/conditionalaccesspolicy-get
Assignments, exclusions, emergency access and sign-in outcomes require review.
"""

from __future__ import annotations

from typing import Any


def captured_checks(policies: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for recommendation, control in (
        ("ca-mfa", "mfa"),
        ("ca-legacy", "block"),
        ("ca-signin-risk", "mfa"),
    ):
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
            if control == "mfa" and clients != {"all"}:
                continue
            if recommendation == "ca-legacy" and not {"exchangeActiveSync", "other"} <= clients:
                continue
            risk_levels = set(conditions.get("signInRiskLevels") or [])
            if recommendation == "ca-signin-risk":
                if not {"medium", "high"} <= risk_levels:
                    continue
            elif risk_levels:
                continue
            # A conditional match never establishes the broad baseline.
            restricted = any(
                conditions.get(key)
                for key in (
                    "locations",
                    "platforms",
                    "devices",
                    "userRiskLevels",
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
                    "exclusions": sum(
                        len(values) if isinstance(values, list) else int(bool(values))
                        for scope in ("users", "applications")
                        for key, values in (conditions.get(scope) or {}).items()
                        if key.startswith("exclude")
                    ),
                }
            )
        out[recommendation] = {
            "state": "settings_found" if matches else "no_match",
            "matches": matches,
        }
    return out


def firewall_check(profiles: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Inspect the three Windows endpoint protection profile values in one policy."""
    matches = []
    complete = False
    partial = False
    for policy in profiles or []:
        if policy.get("@odata.type") != "#microsoft.graph.windows10EndpointProtectionConfiguration":
            continue
        values = []
        for kind in ("Domain", "Private", "Public"):
            profile = policy.get("firewallProfile" + kind)
            values.append(profile.get("firewallEnabled") if isinstance(profile, dict) else None)
        if any(v not in ("allowed", "blocked", "notConfigured") for v in values):
            partial = True
            continue
        complete = True
        if all(value == "allowed" for value in values):
            matches.append(
                {
                    "name": str(policy.get("displayName") or policy.get("id") or ""),
                    "state": "firewall_profiles_enabled",
                }
            )
    state = "unmeasured"
    if matches:
        state = "settings_found"
    elif complete and not partial:
        state = "no_match"
    return {"state": state, "matches": matches}
