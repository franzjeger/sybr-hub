"""Pushing Conditional Access policies into a customer's tenant.

The half of this tool that writes. Everything else here reads a tenant and
reports on it; this changes one, and a Conditional Access policy is the single
most effective way to lock every administrator out of a Microsoft tenant
permanently. Recovery is a support case with Microsoft measured in days.

So the shape is plan, then apply, and the plan is not advisory.

**A plan is computed against the live tenant and carries its fingerprint.**
Apply re-reads the policies and refuses if anything moved since — the operator
approved a specific change to a specific state, and a tenant that has changed
underneath them is one where they approved something else. This is optimistic
concurrency, and it is the difference between "deploy the standard" and
"overwrite whatever somebody did this morning".

**Nothing is enforced on creation.** A new policy arrives as
``enabledForReportingButNotEnforced`` unless the caller asks otherwise in the
same breath. Report-only is how you find out that the policy you just wrote
would have blocked the finance department, before it does.

**The lockout rails refuse rather than warn.** A policy that targets every user
with no exclusion and grants a control that can fail is the accident that ends
tenants, and a warning is something an operator clicks past at four in the
afternoon. ``_lockout_risk`` returns a reason and the change is dropped from
the plan; there is no flag to override it, because the flag would be set by the
same click.

**Every write is preceded by a snapshot of what it replaces**, taken then and
not borrowed from the last audit. A restore point from six hours ago is a
restore point for a tenant that no longer exists.

Nothing here runs without the tenant_write capability and
``Policy.ReadWrite.ConditionalAccess`` consent. The first is ours to grant, the
second is the customer's, and ``missing_consent`` tells the two apart so the
operator is not sent to argue with the wrong person.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

CA_PATH = "identity/conditionalAccess/policies"

# The Graph permission this needs. Deliberately not in REQUIRED_GRAPH_PERMISSIONS:
# an MSP that never deploys should not see a consent gap reported on every audit
# for a power it does not want.
WRITE_PERMISSION = "Policy.ReadWrite.ConditionalAccess"

CREATE, UPDATE, DELETE = "create", "update", "delete"

# States a policy can be in. Report-only is the one new policies get.
ENABLED = "enabled"
REPORT_ONLY = "enabledForReportingButNotEnforced"
DISABLED = "disabled"

# Fields Graph owns. Sending them back is at best ignored and at worst rejected,
# and diffing on them reports drift that is not drift.
_SERVER_OWNED = {
    "id", "createdDateTime", "modifiedDateTime", "@odata.context",
    "templateId", "partialEnablementStrategy",
}


class DeployError(Exception):
    """A deployment cannot proceed, with a reason meant for an operator."""


@dataclass
class Change:
    """One policy's worth of intent."""

    action: str
    name: str
    body: dict
    policy_id: str | None = None
    fields: list[str] = field(default_factory=list)
    refused: str | None = None
    # Set when this update is the standard taking over a policy the customer
    # already had. Carried so the plan can say "adopting «Block legacy
    # authentication»" rather than showing a rename with no explanation.
    adopts: str | None = None

    def as_dict(self) -> dict:
        return {
            "action": self.action, "name": self.name, "policy_id": self.policy_id,
            "fields": self.fields, "refused": self.refused, "adopts": self.adopts,
        }


@dataclass
class Plan:
    """What would happen, and to which version of the tenant."""

    customer_id: str
    changes: list[Change]
    fingerprint: str
    missing_consent: bool = False

    @property
    def applicable(self) -> list[Change]:
        return [c for c in self.changes if not c.refused]

    @property
    def refused(self) -> list[Change]:
        return [c for c in self.changes if c.refused]

    def as_dict(self) -> dict:
        return {
            "customer_id": self.customer_id,
            "fingerprint": self.fingerprint,
            "missing_consent": self.missing_consent,
            "changes": [c.as_dict() for c in self.changes],
            "applicable": len(self.applicable),
            "refused": len(self.refused),
        }


# ── Reading the tenant ───────────────────────────────────────────────────────

def strip_server_fields(policy: dict) -> dict:
    """The parts of a policy we are allowed to send back."""
    return {k: v for k, v in policy.items() if k not in _SERVER_OWNED}


def fingerprint(policies: list[dict]) -> str:
    """A stable hash of the tenant's policies as they stand.

    Includes modifiedDateTime deliberately — the point is to notice that
    something moved, and that field is precisely the one that moves.
    """
    material = json.dumps(
        sorted(
            ({k: p.get(k) for k in ("id", "displayName", "state", "modifiedDateTime")}
             for p in policies),
            key=lambda p: str(p.get("id")),
        ),
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()[:32]


# ── The rails ────────────────────────────────────────────────────────────────

def _grants_a_blocking_control(body: dict) -> bool:
    controls = (body.get("grantControls") or {})
    built_in = {str(c).lower() for c in (controls.get("builtInControls") or [])}
    if "block" in built_in:
        return True
    # Anything that can fail for a user who has not enrolled locks them out
    # just as thoroughly as an explicit block.
    return bool(built_in & {"mfa", "compliantdevice", "domainjoineddevice", "approvedapplication"})


def lockout_risk(body: dict) -> str | None:
    """Why this policy must not be deployed, or None.

    The accident this exists for: a policy that applies to All users, excludes
    nobody, and requires something an account can fail to satisfy. Every
    administrator is then one enrolment problem away from a tenant nobody can
    sign in to, and the recovery is a support case with Microsoft.

    Refused rather than warned. A warning at the end of a working day is a
    dialog somebody dismisses.
    """
    conditions = body.get("conditions") or {}
    users = conditions.get("users") or {}
    include = {str(u).lower() for u in (users.get("includeUsers") or [])}
    excluded = (
        (users.get("excludeUsers") or [])
        + (users.get("excludeGroups") or [])
        + (users.get("excludeRoles") or [])
    )

    if body.get("state") != ENABLED:
        # Report-only and disabled policies cannot lock anyone out of anything.
        return None

    if "all" in include and not excluded and _grants_a_blocking_control(body):
        return (
            "Targets all users, excludes nobody, and grants a control that "
            "can fail. Exclude a break-glass account before enabling this."
        )
    return None


# ── Building a plan ──────────────────────────────────────────────────────────

def _changed_fields(current: dict, desired: dict) -> list[str]:
    keys = (set(strip_server_fields(current)) | set(desired)) - _SERVER_OWNED
    return sorted(k for k in keys if current.get(k) != desired.get(k))


def build_plan(
    customer_id: str,
    live: list[dict],
    desired: list[dict],
    *,
    allow_delete: bool = False,
    missing_consent: bool = False,
    adopt: dict[str, str] | None = None,
) -> Plan:
    """Compare what the tenant has with what we want it to have.

    Matched on displayName, which is right for a tenant we set up and wrong for
    every tenant we inherit: a template has no id until it exists somewhere,
    and the same standard across twenty customers is twenty ids for one policy.

    ``adopt`` is how an inherited tenant is handled — a confirmed mapping from
    template name to the id of a policy the customer already has. The standard
    then *updates* that policy instead of creating a second one beside it, and
    the rename shows up in the changed fields like any other change, because it
    is one.

    Deletion is off unless asked for. A policy present in the tenant and absent
    from the standard is far more often something the customer added on purpose
    than something we should remove.
    """
    adopt = adopt or {}
    by_name = {str(p.get("displayName", "")): p for p in live}
    by_id = {str(p.get("id", "")): p for p in live}
    adopted_ids = set(adopt.values())
    changes: list[Change] = []

    for want in desired:
        name = str(want.get("displayName", ""))
        if not name:
            raise DeployError("A policy without a displayName cannot be matched or reported")
        body = strip_server_fields(want)
        refusal = lockout_risk(body)

        adopted_id = adopt.get(name)
        if adopted_id:
            current = by_id.get(adopted_id)
            if current is None:
                # Falling back to a create here would produce exactly the
                # duplicate adoption exists to avoid, at the moment somebody
                # believed they had avoided it.
                raise DeployError(
                    f"{name!r} is set to adopt policy {adopted_id!r}, which is not "
                    f"in this tenant. Re-check the adoption mapping."
                )
        else:
            current = by_name.get(name)
            # A policy already spoken for by an adoption is not also a
            # name-match for something else.
            if current is not None and str(current.get("id", "")) in adopted_ids:
                current = None

        if current is None:
            changes.append(Change(
                action=CREATE, name=name, body=body, refused=refusal,
            ))
            continue

        fields = _changed_fields(current, body)
        if not fields:
            continue
        changes.append(Change(
            action=UPDATE, name=name, body=body,
            policy_id=str(current.get("id")), fields=fields, refused=refusal,
            adopts=str(current.get("displayName", "")) if adopted_id else None,
        ))

    if allow_delete:
        wanted_names = {str(p.get("displayName", "")) for p in desired}
        for name, current in sorted(by_name.items()):
            # An adopted policy is the standard's now, whatever it is still
            # called at this moment.
            if str(current.get("id", "")) in adopted_ids:
                continue
            if name not in wanted_names:
                changes.append(Change(
                    action=DELETE, name=name, body={},
                    policy_id=str(current.get("id")),
                ))

    return Plan(
        customer_id=customer_id,
        changes=changes,
        fingerprint=fingerprint(live),
        missing_consent=missing_consent,
    )


def as_report_only(policy: dict) -> dict:
    """A policy in the state a new one should arrive in.

    Report-only is how somebody finds out that the policy they just wrote would
    have blocked the finance department, while it still has not.
    """
    out = dict(policy)
    if out.get("state") == ENABLED:
        out["state"] = REPORT_ONLY
    return out


# ── Applying it ──────────────────────────────────────────────────────────────

async def apply_plan(
    client,
    plan: Plan,
    live_now: list[dict],
    *,
    snapshot=None,
) -> dict[str, Any]:
    """Carry out a plan, or refuse because the tenant moved.

    ``snapshot`` is called with the policies about to be replaced, before
    anything is sent. A restore point taken at the moment of the change is the
    only one that describes what the change replaced.
    """
    if plan.missing_consent:
        raise DeployError(
            f"This tenant has not consented to {WRITE_PERMISSION}. "
            f"Nothing was sent."
        )

    current = fingerprint(live_now)
    if current != plan.fingerprint:
        raise DeployError(
            "The tenant's policies changed after this plan was made, so the "
            "plan describes a state that no longer exists. Re-plan and review "
            "the differences before applying."
        )

    if snapshot is not None:
        snapshot([p for p in live_now])

    applied, failed = [], []
    for change in plan.applicable:
        try:
            if change.action == CREATE:
                await client.post(CA_PATH, change.body)
            elif change.action == UPDATE:
                await client.patch(f"{CA_PATH}/{change.policy_id}", change.body)
            elif change.action == DELETE:
                await client.delete(f"{CA_PATH}/{change.policy_id}")
            else:
                raise DeployError(f"Unknown action {change.action!r}")
            logger.warning(
                "policy %s applied: customer=%s policy=%r",
                change.action, plan.customer_id, change.name,
            )
            applied.append(change.as_dict())
        except Exception as exc:
            # One policy failing must not abandon the rest half-done, and the
            # operator needs to know which of them landed.
            logger.error(
                "policy %s FAILED: customer=%s policy=%r: %s",
                change.action, plan.customer_id, change.name, exc,
            )
            failed.append({**change.as_dict(), "error": str(exc)})

    return {
        "applied": applied,
        "failed": failed,
        "refused": [c.as_dict() for c in plan.refused],
    }
