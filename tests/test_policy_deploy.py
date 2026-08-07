"""The half of this tool that writes into somebody's production tenant.

A Conditional Access policy is the most effective way to lock every
administrator out of a Microsoft tenant permanently, and the recovery is a
support case with Microsoft measured in days. So most of what follows is about
refusing, and about noticing that the tenant is not what the operator looked at
when they approved the change.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.policy_deploy import (
    CREATE,
    DELETE,
    ENABLED,
    REPORT_ONLY,
    UPDATE,
    DeployError,
    apply_plan,
    as_report_only,
    build_plan,
    fingerprint,
    lockout_risk,
    strip_server_fields,
)


def _policy(name, *, state=REPORT_ONLY, include=("All",), exclude_groups=(), controls=("mfa",), **kw):
    body = {
        "displayName": name,
        "state": state,
        "conditions": {
            "users": {"includeUsers": list(include), "excludeGroups": list(exclude_groups)},
            "applications": {"includeApplications": ["All"]},
            "clientAppTypes": ["all"],
        },
        "grantControls": {"operator": "OR", "builtInControls": list(controls)},
    }
    body.update(kw)
    return body


class _Client:
    """Records what would have been sent, and can be told to fail."""

    def __init__(self, fail_on: str | None = None):
        self.calls: list[tuple[str, str, dict]] = []
        self.fail_on = fail_on

    async def post(self, path, body, **kw):
        self._maybe_fail(body.get("displayName"))
        self.calls.append(("POST", path, body))
        return {}

    async def patch(self, path, body, **kw):
        self._maybe_fail(body.get("displayName"))
        self.calls.append(("PATCH", path, body))

    async def delete(self, path, **kw):
        self.calls.append(("DELETE", path, {}))

    def _maybe_fail(self, name):
        if self.fail_on and name == self.fail_on:
            raise RuntimeError("Graph said no")


# ── The lockout rails ────────────────────────────────────────────────────────

def test_a_policy_that_locks_everyone_out_is_refused():
    """All users, nobody excluded, and a control that can fail.

    This is the accident that ends tenants. Refused rather than warned: a
    warning at four in the afternoon is a dialog somebody dismisses.
    """
    risk = lockout_risk(_policy("bad", state=ENABLED, include=["All"], exclude_groups=[]))

    assert risk is not None
    assert "break-glass" in risk


def test_a_break_glass_exclusion_is_what_makes_it_safe():
    safe = _policy("ok", state=ENABLED, include=["All"], exclude_groups=["bg-group-id"])

    assert lockout_risk(safe) is None


@pytest.mark.parametrize("control", ["block", "mfa", "compliantDevice", "domainJoinedDevice"])
def test_every_control_that_can_fail_counts_as_a_lockout(control):
    """A user who has not enrolled is locked out by a device requirement as
    thoroughly as by an explicit block."""
    body = _policy("x", state=ENABLED, include=["All"], exclude_groups=[], controls=[control])

    assert lockout_risk(body) is not None


def test_report_only_cannot_lock_anyone_out():
    """It is the state new policies arrive in, and the reason that is safe."""
    body = _policy("x", state=REPORT_ONLY, include=["All"], exclude_groups=[])

    assert lockout_risk(body) is None


def test_a_refused_policy_stays_in_the_plan_but_out_of_the_applicable_set():
    """Hiding it would leave an operator wondering what happened to it."""
    plan = build_plan("acme", [], [_policy("bad", state=ENABLED, exclude_groups=[])])

    assert len(plan.changes) == 1
    assert plan.applicable == []
    assert plan.refused[0].refused


async def test_a_refused_policy_is_never_sent():
    plan = build_plan("acme", [], [_policy("bad", state=ENABLED, exclude_groups=[])])
    client = _Client()

    await apply_plan(client, plan, [])

    assert client.calls == []


# ── The tenant moving underneath a plan ──────────────────────────────────────

async def test_applying_against_a_changed_tenant_is_refused():
    """The operator approved a change to a state that no longer exists.

    Somebody edited a policy this morning; applying anyway would overwrite
    their work with a plan made before it.
    """
    live = [{"id": "1", "displayName": "One", "state": ENABLED, "modifiedDateTime": "t1"}]
    reviewed = build_plan("acme", live, [_policy("Two")])
    moved = [{"id": "1", "displayName": "One", "state": DISABLED_STATE, "modifiedDateTime": "t2"}]
    # What apply rebuilds against the tenant as it now stands.
    rebuilt = build_plan("acme", moved, [_policy("Two")])

    with pytest.raises(DeployError, match="no longer describes"):
        await apply_plan(_Client(), rebuilt, moved, approved=reviewed.fingerprint)


async def test_the_intent_moving_is_refused_as_well_as_the_tenant():
    """The gap a tenant-only hash left open.

    Operator A reviews a plan that says CREATE. Operator B confirms an adoption
    mapping. A clicks apply, and the tool PATCHes a policy A never saw — the
    tenant check green, because the tenant had not moved.
    """
    live = [{"id": "1", "displayName": "Theirs", "state": ENABLED, "modifiedDateTime": "t"}]
    reviewed = build_plan("acme", live, [_policy("Ours")])
    with_adoption = build_plan("acme", live, [_policy("Ours")], adopt={"Ours": "1"})

    assert reviewed.fingerprint != with_adoption.fingerprint

    with pytest.raises(DeployError, match="no longer describes"):
        await apply_plan(_Client(), with_adoption, live, approved=reviewed.fingerprint)


DISABLED_STATE = "disabled"


async def test_an_unchanged_tenant_applies():
    live = [{"id": "1", "displayName": "One", "state": ENABLED, "modifiedDateTime": "t1"}]
    plan = build_plan("acme", live, [_policy("Two")])
    client = _Client()

    result = await apply_plan(client, plan, live, approved=plan.fingerprint)

    assert len(result["applied"]) == 1
    assert client.calls[0][0] == "POST"


def test_the_fingerprint_notices_an_edit():
    before = [{"id": "1", "displayName": "One", "state": ENABLED, "modifiedDateTime": "t1"}]
    after = [{"id": "1", "displayName": "One", "state": ENABLED, "modifiedDateTime": "t2"}]

    assert fingerprint(before) != fingerprint(after)


def test_the_fingerprint_ignores_the_order_graph_returns_them_in():
    a = [{"id": "1", "displayName": "A"}, {"id": "2", "displayName": "B"}]

    assert fingerprint(a) == fingerprint(list(reversed(a)))


# ── Building the plan ────────────────────────────────────────────────────────

def test_a_policy_that_matches_is_not_touched():
    """Otherwise every deployment reports changes it is not making."""
    want = _policy("Same")
    live = [{**want, "id": "1", "modifiedDateTime": "t"}]

    assert build_plan("acme", live, [want]).changes == []


def test_a_changed_policy_names_the_fields_that_moved():
    want = _policy("One", state=ENABLED, exclude_groups=["bg"])
    live = [{**_policy("One", state=DISABLED_STATE, exclude_groups=["bg"]), "id": "1"}]

    change = build_plan("acme", live, [want]).changes[0]

    assert change.action == UPDATE
    assert change.policy_id == "1"
    assert change.fields == ["state"]


def test_policies_are_matched_by_name_not_id():
    """A template has no id until it exists somewhere, and the same standard
    across twenty customers is twenty ids for one policy."""
    live = [{**_policy("One"), "id": "whatever-this-tenant-calls-it"}]

    plan = build_plan("acme", live, [_policy("One", state=ENABLED, exclude_groups=["bg"])])

    assert plan.changes[0].action == UPDATE


def test_nothing_is_deleted_unless_asked():
    """A policy the customer added on purpose is the common case."""
    live = [{**_policy("Theirs"), "id": "1"}]

    assert build_plan("acme", live, []).changes == []


def test_deletion_names_one_policy_at_a_time():
    """It used to be a boolean, so one tick planned the removal of every policy
    the standard does not contain — a mass un-protection event behind a
    checkbox."""
    live = [{**_policy("Theirs"), "id": "1"}, {**_policy("Also theirs"), "id": "2"}]

    plan = build_plan("acme", live, [], delete=["1"])

    assert [(c.action, c.name, c.policy_id) for c in plan.changes] == [(DELETE, "Theirs", "1")]


def test_what_the_standard_does_not_contain_is_reported_not_removed():
    """Shown so an operator can see it and choose; choosing means naming it."""
    live = [{**_policy("Theirs"), "id": "1"}]

    plan = build_plan("acme", live, [])

    assert plan.changes == []
    assert plan.unmanaged == [{"policy_id": "1", "name": "Theirs", "state": REPORT_ONLY}]


def test_deleting_something_that_is_not_unmanaged_is_refused():
    """A stale id from an older plan must not delete whatever holds it now."""
    live = [{**_policy("Ours"), "id": "1"}]

    with pytest.raises(DeployError, match="not an unmanaged policy"):
        build_plan("acme", live, [_policy("Ours")], delete=["1"])


def test_a_policy_without_a_name_is_refused_outright():
    with pytest.raises(DeployError, match="displayName"):
        build_plan("acme", [], [{"state": REPORT_ONLY}])


# ── What we send ─────────────────────────────────────────────────────────────

def test_server_owned_fields_are_not_sent_back():
    """Graph rejects some of them and ignores the rest, and diffing on them
    reports drift that is not drift."""
    stripped = strip_server_fields(
        {**_policy("One"), "id": "1", "createdDateTime": "t", "modifiedDateTime": "t"}
    )

    assert set(stripped) == {"displayName", "state", "conditions", "grantControls"}


def test_a_new_policy_is_downgraded_to_report_only():
    assert as_report_only(_policy("x", state=ENABLED))["state"] == REPORT_ONLY


def test_report_only_leaves_a_disabled_policy_alone():
    assert as_report_only(_policy("x", state=DISABLED_STATE))["state"] == DISABLED_STATE


# ── Failure part-way through ─────────────────────────────────────────────────

async def test_one_policy_failing_does_not_abandon_the_rest():
    """And the operator is told which of them landed."""
    plan = build_plan("acme", [], [_policy("First"), _policy("Second"), _policy("Third")])
    client = _Client(fail_on="Second")

    result = await apply_plan(client, plan, [])

    assert [c["name"] for c in result["applied"]] == ["First", "Third"]
    assert [c["name"] for c in result["failed"]] == ["Second"]
    assert "Graph said no" in result["failed"][0]["error"]


# ── Consent ──────────────────────────────────────────────────────────────────

async def test_without_consent_nothing_is_sent():
    """And the message says whose problem it is: ours to grant tenant_write,
    the customer's to consent to the Graph permission."""
    plan = build_plan("acme", [], [_policy("One")], missing_consent=True)
    client = _Client()

    with pytest.raises(DeployError, match="consent"):
        await apply_plan(client, plan, [])

    assert client.calls == []


# ── The restore point ────────────────────────────────────────────────────────

async def test_what_is_about_to_be_replaced_is_snapshotted_first():
    """A restore point from the last audit describes a tenant that has since
    changed. This one is taken at the moment of the write."""
    live = [{**_policy("One"), "id": "1", "modifiedDateTime": "t"}]
    plan = build_plan("acme", live, [_policy("One", state=ENABLED, exclude_groups=["bg"])])
    taken: list = []

    await apply_plan(_Client(), plan, live, approved=plan.fingerprint, snapshot=taken.extend)

    assert taken and taken[0]["displayName"] == "One"


async def test_the_snapshot_is_taken_before_anything_is_sent():
    order: list[str] = []

    class _Recording(_Client):
        async def patch(self, path, body, **kw):
            order.append("write")
            await super().patch(path, body, **kw)

    live = [{**_policy("One"), "id": "1", "modifiedDateTime": "t"}]
    plan = build_plan("acme", live, [_policy("One", state=ENABLED, exclude_groups=["bg"])])

    await apply_plan(_Recording(), plan, live, snapshot=lambda _: order.append("snapshot"))

    assert order == ["snapshot", "write"]


# ── What an adversarial read of this module found ────────────────────────────

def test_adopting_does_not_wipe_conditions_the_template_never_mentions():
    """The worst one, and it was real.

    Graph replaces an included complex property wholesale. PATCHing a template's
    conditions — users, applications, clientAppTypes — would clear whatever the
    live policy had beside them: the customer's excludeUsers, their trusted
    locations, their risk levels. On an adopted MFA policy that is the directory
    sync account losing its exclusion, silently, during an operation the plan
    described as "conditions changed".
    """
    live = {
        "id": "1", "displayName": "Their MFA", "state": REPORT_ONLY,
        "modifiedDateTime": "t",
        "conditions": {
            "users": {"includeUsers": ["All"], "excludeUsers": ["sync-account"],
                      "excludeGroups": ["bg"]},
            "locations": {"excludeLocations": ["trusted-office"]},
            "signInRiskLevels": ["high"],
        },
        "grantControls": {"operator": "OR", "builtInControls": ["mfa"],
                          "authenticationStrength": {"id": "strength-1"}},
    }
    template = _policy("Sybr — MFA", exclude_groups=["bg"])

    change = build_plan("acme", [live], [template], adopt={"Sybr — MFA": "1"}).changes[0]

    users = change.body["conditions"]["users"]
    assert users["excludeUsers"] == ["sync-account"], "the sync account lost its exclusion"
    assert change.body["conditions"]["locations"]["excludeLocations"] == ["trusted-office"]
    assert change.body["conditions"]["signInRiskLevels"] == ["high"]
    assert change.body["grantControls"]["authenticationStrength"] == {"id": "strength-1"}


def test_what_the_template_does_say_still_wins():
    """Merging must not mean the standard is advisory."""
    live = {
        "id": "1", "displayName": "Theirs", "state": "disabled", "modifiedDateTime": "t",
        "conditions": {"users": {"includeUsers": ["someone"], "excludeGroups": []}},
        "grantControls": {"operator": "OR", "builtInControls": []},
    }
    template = _policy("Sybr — MFA", include=["All"], exclude_groups=["bg"])

    change = build_plan("acme", [live], [template], adopt={"Sybr — MFA": "1"}).changes[0]

    assert change.body["conditions"]["users"]["includeUsers"] == ["All"]
    assert change.body["grantControls"]["builtInControls"] == ["mfa"]


def test_the_plan_shows_before_and_after_not_just_a_field_name():
    """"conditions changed" is the field name of an object holding somebody's
    exclusions. Nobody can consent to that."""
    live = {**_policy("Theirs", state="disabled"), "id": "1", "modifiedDateTime": "t"}
    template = _policy("Sybr — MFA", state=REPORT_ONLY)

    change = build_plan("acme", [live], [template], adopt={"Sybr — MFA": "1"}).changes[0]

    assert change.diff["state"]["before"] == "disabled"
    assert change.diff["state"]["after"] == REPORT_ONLY
    assert change.diff["displayName"]["before"] == "Theirs"


def test_a_redeploy_never_switches_an_enabled_policy_back_to_report_only():
    """Templates ship report-only so a human enables after review. A routine
    re-deploy that PATCHed the state back would un-enforce the baseline
    tenant-wide — the quiet inverse of a lockout, on the second-most-routine
    operation this tool has.
    """
    live = {**_policy("Sybr — MFA", state=ENABLED), "id": "1", "modifiedDateTime": "t"}
    template = _policy("Sybr — MFA", state=REPORT_ONLY)

    plan = build_plan("acme", [live], [template])

    assert plan.changes == [], "the enabled policy was pushed back to report-only"


def test_weakening_is_possible_when_asked_for_explicitly():
    live = {**_policy("Sybr — MFA", state=ENABLED), "id": "1", "modifiedDateTime": "t"}
    template = _policy("Sybr — MFA", state=REPORT_ONLY)

    plan = build_plan("acme", [live], [template], allow_weakening=True)

    assert plan.changes[0].body["state"] == REPORT_ONLY


@pytest.mark.parametrize("condition,expected", [
    ({"includeUsers": ["All"]}, True),
    ({"includeRoles": ["62e90394-69f5-4237-9190-012177145e10"]}, True),
    ({"includeGroups": ["all-staff"]}, True),
    ({"includeUsers": ["one-person"]}, False),
])
def test_every_way_of_saying_everyone_is_caught(condition, expected):
    """The rail read includeUsers only, so a policy over every administrator
    role sailed through — the exact accident it exists for, invisible because
    "all" is not in an empty set."""
    body = {
        "displayName": "x", "state": ENABLED,
        "conditions": {"users": {**condition, "excludeGroups": []}},
        "grantControls": {"operator": "OR", "builtInControls": ["mfa"]},
    }

    assert (lockout_risk(body) is not None) is expected


def test_authentication_strength_counts_as_a_control_that_can_fail():
    """The modern form lives beside builtInControls rather than inside it, so
    reading only builtInControls made the strictest policy Microsoft offers
    invisible to this check."""
    body = {
        "displayName": "x", "state": ENABLED,
        "conditions": {"users": {"includeUsers": ["All"], "excludeGroups": []}},
        "grantControls": {"operator": "OR", "builtInControls": None,
                          "authenticationStrength": {"id": "phishing-resistant"}},
    }

    assert lockout_risk(body) is not None


async def test_a_break_glass_group_that_does_not_exist_is_caught():
    """The one assumption every rail here rests on, and nothing checked it.

    Graph accepts an unresolvable GUID in excludeGroups without complaint, so a
    typo, another customer's id, or a deleted group all produce a non-empty
    exclusion list — and lockout_risk is then permanently satisfied by an
    exclusion that excludes nobody.
    """
    from app.modules.m365_audit.policy_deploy import verify_exclusion_group

    class _Missing:
        async def get(self, path, **kw):
            raise RuntimeError("404")

    assert "does not exist" in (await verify_exclusion_group(_Missing(), "nope"))


async def test_an_empty_break_glass_group_is_caught():
    """Excluding a group with no members is the same as excluding nothing."""
    from app.modules.m365_audit.policy_deploy import verify_exclusion_group

    class _Empty:
        async def get(self, path, **kw):
            if path.endswith("/members"):
                return {"value": []}
            return {"id": "g1", "displayName": "Break glass"}

    assert "is empty" in (await verify_exclusion_group(_Empty(), "g1"))


async def test_a_populated_break_glass_group_passes():
    from app.modules.m365_audit.policy_deploy import verify_exclusion_group

    class _Good:
        async def get(self, path, **kw):
            if path.endswith("/members"):
                return {"value": [{"id": "u1"}]}
            return {"id": "g1", "displayName": "Break glass"}

    assert await verify_exclusion_group(_Good(), "g1") is None
