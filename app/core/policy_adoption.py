"""Letting the standard take over a policy the customer already has.

The plan matches a template to a tenant by display name, which is right for a
tenant we set up and wrong for every tenant we inherit. Fonnafly has five
sensible Conditional Access policies with five names nobody at Sybr chose, so
deploying the standard alongside them produces ten policies where five were
meant — and overlapping Conditional Access is genuinely hard to reason about,
which is a worse outcome than not deploying at all.

Adoption is the answer, and the whole design is about *not guessing*.

**A suggestion decides nothing.** `suggest` scores a live policy against a
template policy on what it does — the controls it grants, who it covers, which
client apps it catches — and returns candidates with the reasons for the score.
It is a shortlist for a person, never an input to a plan. Matching by heuristic
and then overwriting is exactly the silent destruction every other guard in
this module exists to prevent, and a policy overwritten because a fuzzy matcher
thought it looked familiar is a production incident with a plausible-sounding
cause.

**Adoption is an explicit mapping**, confirmed once per customer and stored.
Template policy name to live policy id. After that, plans match through it
without asking again.

**Adopting renames.** The adopted policy takes the standard's name, so every
later comparison is the ordinary one. That is a real change to a real policy,
so it appears in the plan's changed fields like any other — the operator sees
"displayName" in the diff and knows what they agreed to.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

MAPPING_FILE = "policy_adoption.json"


class AdoptionError(Exception):
    """A mapping that cannot be honoured, with a reason for an operator."""


# ── Suggesting, which is not deciding ────────────────────────────────────────

def _controls(policy: dict) -> set[str]:
    grants = policy.get("grantControls") or {}
    return {str(c).lower() for c in (grants.get("builtInControls") or [])}


def _users(policy: dict) -> dict[str, set[str]]:
    users = ((policy.get("conditions") or {}).get("users")) or {}
    return {
        key: {str(v).lower() for v in (users.get(key) or [])}
        for key in ("includeUsers", "includeRoles", "excludeGroups")
    }


def _client_apps(policy: dict) -> set[str]:
    return {
        str(c).lower()
        for c in (((policy.get("conditions") or {}).get("clientAppTypes")) or [])
    }


def score(template: dict, live: dict) -> tuple[int, list[str]]:
    """How alike two policies are in effect, and why.

    Deliberately about behaviour rather than wording. "All users require MFA"
    and "Sybr — Require MFA for all users" share no words a matcher could use,
    and are the same policy; two policies both called "MFA" can be nothing
    alike.
    """
    points, reasons = 0, []

    t_controls, l_controls = _controls(template), _controls(live)
    if t_controls and t_controls == l_controls:
        points += 3
        reasons.append(f"grants the same controls ({', '.join(sorted(t_controls))})")
    elif t_controls & l_controls:
        points += 1
        reasons.append("grants overlapping controls")

    t_users, l_users = _users(template), _users(live)
    if t_users["includeUsers"] and t_users["includeUsers"] == l_users["includeUsers"]:
        points += 2
        reasons.append("covers the same users")
    if t_users["includeRoles"] and t_users["includeRoles"] == l_users["includeRoles"]:
        points += 2
        reasons.append("covers the same directory roles")
    elif t_users["includeRoles"] and t_users["includeRoles"] & l_users["includeRoles"]:
        points += 1
        reasons.append("covers overlapping directory roles")

    t_apps, l_apps = _client_apps(template), _client_apps(live)
    if t_apps and t_apps == l_apps:
        points += 1
        reasons.append("catches the same client apps")

    return points, reasons


# A score below this is not worth putting in front of somebody as a candidate.
# Three is "grants exactly the same controls" and nothing else, which is the
# weakest thing still worth a look.
SUGGESTION_FLOOR = 3


def suggest(desired: list[dict], live: list[dict]) -> dict[str, list[dict]]:
    """Candidates per template policy, best first. A shortlist, not a decision."""
    out: dict[str, list[dict]] = {}
    for template in desired:
        name = str(template.get("displayName", ""))
        candidates = []
        for policy in live:
            points, reasons = score(template, policy)
            if points >= SUGGESTION_FLOOR:
                candidates.append({
                    "policy_id": str(policy.get("id", "")),
                    "display_name": str(policy.get("displayName", "")),
                    "state": str(policy.get("state", "")),
                    "score": points,
                    "reasons": reasons,
                })
        candidates.sort(key=lambda c: (-c["score"], c["display_name"]))
        out[name] = candidates
    return out


# ── The mapping, which is ────────────────────────────────────────────────────

def validate(mapping: dict[str, str], desired: list[dict], live: list[dict]) -> None:
    """Refuse a mapping that cannot mean what it says."""
    names = {str(p.get("displayName", "")) for p in desired}
    ids = {str(p.get("id", "")) for p in live}

    for template_name, policy_id in mapping.items():
        if template_name not in names:
            raise AdoptionError(
                f"{template_name!r} is not a policy in this standard, so nothing "
                f"can adopt on its behalf."
            )
        if policy_id not in ids:
            # Silently creating instead would produce the duplicate the whole
            # feature exists to avoid, at the moment somebody believed they had
            # avoided it.
            raise AdoptionError(
                f"{template_name!r} is mapped to policy {policy_id!r}, which no "
                f"longer exists in this tenant. Re-check the mapping."
            )

    taken: dict[str, str] = {}
    for template_name, policy_id in sorted(mapping.items()):
        if policy_id in taken:
            raise AdoptionError(
                f"{template_name!r} and {taken[policy_id]!r} both adopt policy "
                f"{policy_id!r}. One policy cannot become two."
            )
        taken[policy_id] = template_name


def load_mapping(customer_id: str) -> dict[str, str]:
    """The adoptions confirmed for this customer, or nothing."""
    from app.core.config import get_audit_dir
    from app.core.encryption import encrypted_read_json

    path = get_audit_dir() / customer_id / MAPPING_FILE
    if not path.is_file():
        return {}
    try:
        data = encrypted_read_json(path)
    except Exception as exc:
        # A mapping that cannot be read must not quietly become "adopt
        # nothing", which would deploy duplicates beside the policies it was
        # meant to take over.
        raise AdoptionError(
            f"The adoption mapping for {customer_id!r} could not be read: {exc}"
        ) from exc
    return {str(k): str(v) for k, v in (data or {}).items()}


def save_mapping(customer_id: str, mapping: dict[str, str]) -> None:
    from app.core.config import get_audit_dir
    from app.core.encryption import encrypted_write_json

    directory = get_audit_dir() / customer_id
    directory.mkdir(parents=True, exist_ok=True)
    encrypted_write_json(directory / MAPPING_FILE, dict(mapping))
    logger.warning(
        "adoption mapping saved for %s: %d policy/policies adopted",
        customer_id, len(mapping),
    )


def describe(mapping: dict[str, str], live: list[dict]) -> list[dict[str, Any]]:
    """The mapping as something a person reads, with the current names."""
    by_id = {str(p.get("id", "")): p for p in live}
    return [
        {
            "template": name,
            "policy_id": policy_id,
            "current_name": str(by_id.get(policy_id, {}).get("displayName", "")),
            "present": policy_id in by_id,
        }
        for name, policy_id in sorted(mapping.items())
    ]
