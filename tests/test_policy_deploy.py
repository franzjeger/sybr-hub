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
    plan = build_plan("acme", live, [_policy("Two")])
    moved = [{"id": "1", "displayName": "One", "state": DISABLED_STATE, "modifiedDateTime": "t2"}]

    with pytest.raises(DeployError, match="no longer exists"):
        await apply_plan(_Client(), plan, moved)


DISABLED_STATE = "disabled"


async def test_an_unchanged_tenant_applies():
    live = [{"id": "1", "displayName": "One", "state": ENABLED, "modifiedDateTime": "t1"}]
    plan = build_plan("acme", live, [_policy("Two")])
    client = _Client()

    result = await apply_plan(client, plan, live)

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


def test_deletion_when_asked_for_names_the_policy():
    live = [{**_policy("Theirs"), "id": "1"}]

    change = build_plan("acme", live, [], allow_delete=True).changes[0]

    assert (change.action, change.name, change.policy_id) == (DELETE, "Theirs", "1")


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

    await apply_plan(_Client(), plan, live, snapshot=taken.extend)

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
