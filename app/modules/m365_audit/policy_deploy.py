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

# How enforced each state is. A deployment may raise a policy's state and, by
# default, never lower it: templates ship report-only so a human can review the
# impact and then enable in the portal, and a routine re-deploy that PATCHed
# the state back would silently switch that protection off tenant-wide. The
# second-most-routine operation this tool has must not un-enforce a baseline.
_ENFORCEMENT = {"disabled": 0, "enabledForReportingButNotEnforced": 1, "enabled": 2}

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
    # Before and after per changed field, so "conditions changed" is not the
    # whole of what somebody approves. Only populated for updates.
    diff: dict = field(default_factory=dict)
    # Set when this update is the standard taking over a policy the customer
    # already had. Carried so the plan can say "adopting «Block legacy
    # authentication»" rather than showing a rename with no explanation.
    adopts: str | None = None

    def as_dict(self) -> dict:
        return {
            "action": self.action, "name": self.name, "policy_id": self.policy_id,
            "fields": self.fields, "refused": self.refused, "adopts": self.adopts,
            "diff": self.diff,
        }


@dataclass
class Plan:
    """What would happen, and to which version of the tenant."""

    customer_id: str
    changes: list[Change]
    fingerprint: str
    missing_consent: bool = False
    # Policies in the tenant the standard does not contain. Reported, never
    # acted on: deleting one means naming its id in `delete`.
    unmanaged: list[dict] = field(default_factory=list)

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
            "unmanaged": self.unmanaged,
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


def plan_fingerprint(
    live: list[dict], desired: list[dict], adopt: dict, delete: list[str]
) -> str:
    """What the operator approved: this tenant *and* this change to it.

    Hashing the tenant alone was not enough. The plan is recomputed at apply
    time from inputs the tenant hash does not cover — the adoption mapping is
    loaded fresh from disk, and the template could be edited between the two
    requests. So: operator A reviews a plan that says CREATE, operator B
    confirms an adoption mapping, A clicks apply, and the tool PATCHes a policy
    A never saw, with the tenant check green because the tenant had not moved.

    Now the fingerprint moves when the intent moves, and apply refuses.
    """
    material = json.dumps(
        {
            "tenant": fingerprint(live),
            "desired": [strip_server_fields(p) for p in desired],
            "adopt": dict(sorted(adopt.items())),
            "delete": sorted(delete),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(material.encode()).hexdigest()[:32]


# ── The rails ────────────────────────────────────────────────────────────────

def _grants_a_blocking_control(body: dict) -> bool:
    controls = (body.get("grantControls") or {})
    built_in = {str(c).lower() for c in (controls.get("builtInControls") or [])}
    if "block" in built_in:
        return True
    # authenticationStrength is the modern form and lives beside builtInControls
    # rather than inside it — phishing-resistant MFA fails for an unenrolled
    # user exactly as plain MFA does, and reading only builtInControls made the
    # strictest policy Microsoft offers invisible to this check.
    if controls.get("authenticationStrength"):
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
    include_users = {str(u).lower() for u in (users.get("includeUsers") or [])}
    include_roles = [r for r in (users.get("includeRoles") or []) if r]
    include_groups = [g for g in (users.get("includeGroups") or []) if g]
    excluded = (
        (users.get("excludeUsers") or [])
        + (users.get("excludeGroups") or [])
        + (users.get("excludeRoles") or [])
    )

    if body.get("state") != ENABLED:
        # Report-only and disabled policies cannot lock anyone out of anything.
        return None

    if not _grants_a_blocking_control(body):
        return None
    if excluded:
        return None

    # Three ways to say "everyone who matters", and the first draft read only
    # the first. A policy over every administrator role with no exclusion is
    # the every-admin-locked-out accident this exists for, and it was invisible
    # because "all" is not in an empty includeUsers set.
    if "all" in include_users:
        return (
            "Targets all users, excludes nobody, and grants a control that "
            "can fail. Exclude a break-glass account before enabling this."
        )
    if include_roles:
        return (
            f"Targets {len(include_roles)} directory role(s) with no exclusion, "
            f"and grants a control that can fail. Every holder of those roles is "
            f"one enrolment problem from being locked out. Exclude a break-glass "
            f"account before enabling this."
        )
    if include_groups:
        return (
            f"Targets {len(include_groups)} group(s) with no exclusion, and "
            f"grants a control that can fail. Exclude a break-glass account "
            f"before enabling this — a group can hold every administrator."
        )
    return None


def merge_into(current: dict, desired: dict) -> dict:
    """The body to PATCH: what the standard says, over what the tenant has.

    Graph replaces an included complex property wholesale, so PATCHing a
    template's ``conditions`` — users, applications, clientAppTypes and nothing
    else — clears whatever the live policy had beside them: the customer's
    excludeUsers, their trusted-location conditions, their risk levels, their
    device filters. On an adopted MFA policy that is the sync account losing its
    exclusion, silently, during an operation described to the operator as
    "conditions changed".

    So the standard is merged into the live body rather than sent in its place.
    A key the template names wins; a key it does not name survives untouched.

    The cost, stated because it is real: a standard cannot *remove* something
    this way. Taking a stray exclusion off an adopted policy is a deliberate
    edit somebody makes, not a side effect of deploying. That is the safer
    direction to be wrong in.
    """
    out = dict(current)
    for key, value in desired.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            out[key] = merge_into(current[key], value)
        else:
            out[key] = value
    return strip_server_fields(out)


def field_diff(current: dict, desired: dict, fields: list[str]) -> dict[str, dict]:
    """Before and after for each changed field, for the person approving.

    A plan that says "conditions changed" is not something anybody can consent
    to — it is the field name of a complex object with a customer's exclusions
    inside it. Adoption is the case that needs this: the operator is deciding
    whether the standard may take over a policy somebody else configured, and
    they cannot decide that from a list of key names.

    Values travel here, unlike in a drift summary, because this reader holds
    tenant_write and is about to change the very object being shown.
    """
    return {
        f: {"before": current.get(f), "after": desired.get(f)}
        for f in fields
    }


# ── Building a plan ──────────────────────────────────────────────────────────

def _changed_fields(current: dict, desired: dict) -> list[str]:
    keys = (set(strip_server_fields(current)) | set(desired)) - _SERVER_OWNED
    return sorted(k for k in keys if current.get(k) != desired.get(k))


def would_weaken(current: dict, desired: dict) -> bool:
    """True when applying this would make a live policy less enforced."""
    return _ENFORCEMENT.get(str(desired.get("state")), 1) < _ENFORCEMENT.get(
        str(current.get("state")), 1
    )


def build_plan(
    customer_id: str,
    live: list[dict],
    desired: list[dict],
    *,
    delete: list[str] | None = None,
    missing_consent: bool = False,
    adopt: dict[str, str] | None = None,
    allow_weakening: bool = False,
) -> Plan:
    """Compare what the tenant has with what we want it to have.

    Matched on displayName, which is right for a tenant we set up and wrong for
    every tenant we inherit: a template has no id until it exists somewhere,
    and the same standard across twenty customers is twenty ids for one policy.

    Except when the desired policy carries an id that the tenant still has —
    which is a restore, since a snapshot records what Graph returned. Matching
    a restore by name cannot undo an adoption: adopting renamed the policy, the
    snapshot holds the old name, and name-matching would create a duplicate
    under it, or with deletion approved would remove the adopted policy and
    leave the stored mapping pointing at a dead id, hard-failing every plan
    after that until somebody hand-edited an encrypted file.

    ``adopt`` is how an inherited tenant is handled — a confirmed mapping from
    template name to the id of a policy the customer already has. The standard
    then *updates* that policy instead of creating a second one beside it, and
    the rename shows up in the changed fields like any other change, because it
    is one.

    ``delete`` names the policy ids to remove, one at a time. It used to be a
    boolean, which meant a single tick planned the deletion of *every* policy in
    the tenant the standard does not contain — a mass un-protection event behind
    one checkbox. Everything not in the standard is now reported as unmanaged so
    an operator can see it and choose, and choosing means naming it.
    """
    adopt = adopt or {}
    delete = list(delete or [])
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

        # A restore carries the id the policy had when it was captured. If the
        # tenant still has it, that is the policy this is about — whatever it
        # has since been renamed to.
        own_id = str(want.get("id", ""))
        adopted_id = adopt.get(name)
        if own_id and own_id in by_id and not adopted_id:
            current = by_id[own_id]
        elif adopted_id:
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

        # Merged, never substituted — see merge_into. The refusal is judged on
        # what would actually be sent, not on the template in isolation.
        merged = merge_into(current, body)
        refusal = lockout_risk(merged) or refusal
        fields = _changed_fields(current, merged)
        if not fields:
            continue
        if not allow_weakening and would_weaken(current, merged):
            # Templates ship report-only so a human can enable after review. A
            # re-deploy that put the state back would switch that protection
            # off, which is the quiet inverse of a lockout.
            merged["state"] = current.get("state")
            fields = _changed_fields(current, merged)
            if not fields:
                continue
        changes.append(Change(
            action=UPDATE, name=name, body=merged,
            policy_id=str(current.get("id")), fields=fields, refused=refusal,
            adopts=str(current.get("displayName", "")) if adopted_id else None,
            diff=field_diff(current, merged, fields),
        ))

    wanted_names = {str(p.get("displayName", "")) for p in desired}
    wanted_ids = {str(p.get("id", "")) for p in desired if p.get("id")}
    unmanaged: list[dict] = []
    for name, current in sorted(by_name.items()):
        # An adopted policy is the standard's now, whatever it is still called
        # at this moment; so is one a restore matched by id under a new name.
        policy_id = str(current.get("id", ""))
        if policy_id in adopted_ids or policy_id in wanted_ids or name in wanted_names:
            continue
        unmanaged.append({
            "policy_id": str(current.get("id", "")),
            "name": name,
            "state": str(current.get("state", "")),
        })

    if delete:
        known = {u["policy_id"] for u in unmanaged}
        for policy_id in delete:
            if policy_id not in known:
                raise DeployError(
                    f"Policy {policy_id!r} was named for deletion but is not an "
                    f"unmanaged policy in this tenant. Re-check the plan."
                )
        wanted = set(delete)
        for current in live:
            policy_id = str(current.get("id", ""))
            if policy_id in wanted:
                changes.append(Change(
                    action=DELETE, name=str(current.get("displayName", "")),
                    body={}, policy_id=policy_id,
                ))

    return Plan(
        customer_id=customer_id,
        changes=changes,
        fingerprint=plan_fingerprint(live, desired, adopt, delete),
        missing_consent=missing_consent,
        unmanaged=unmanaged,
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


async def verify_exclusion_group(client, group_id: str) -> str | None:
    """Why this break-glass group cannot be relied on, or None.

    Every rail here rests on one assumption: the excluded group contains
    somebody who can still sign in. Nothing checked it. Graph accepts an
    unresolvable GUID in excludeGroups without complaint, so a typo, another
    customer's id — the exact nightmare the template docstring names — a deleted
    group or a valid but *empty* one all produce a non-empty exclusion list, and
    ``lockout_risk`` is then permanently satisfied by an exclusion that excludes
    nobody. Across twenty customers with copy-pasted GUIDs this happens.

    Checked at plan time, where a Graph client is already open.
    """
    try:
        group = await client.get(f"groups/{group_id}")
    except Exception:
        return (
            f"The break-glass group {group_id} does not exist in this tenant. "
            f"An exclusion naming it excludes nobody."
        )
    if not group or not group.get("id"):
        return f"The break-glass group {group_id} could not be read."
    try:
        members = await client.get(f"groups/{group_id}/members", params={"$top": "1"})
    except Exception:
        return f"The members of break-glass group {group_id} could not be read."
    if not (members or {}).get("value"):
        return (
            f"The break-glass group «{group.get('displayName', group_id)}» is empty. "
            f"Excluding it excludes nobody, which is the same as excluding nothing."
        )
    return None


# ── Applying it ──────────────────────────────────────────────────────────────

async def apply_plan(
    client,
    plan: Plan,
    live_now: list[dict],
    *,
    approved: str = "",
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

    # `plan` was rebuilt from live inputs a moment ago, so its fingerprint is
    # what would happen now. `approved` is what the operator read. Comparing
    # the two catches the tenant moving *and* the intent moving — the plan is
    # recomputed from an adoption mapping and a template file that another
    # request could have changed in between.
    if approved and approved != plan.fingerprint:
        raise DeployError(
            "This plan no longer describes what would happen. Either the "
            "tenant's policies changed, or the standard or its adoption "
            "mapping did. Re-plan and review the differences before applying."
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
