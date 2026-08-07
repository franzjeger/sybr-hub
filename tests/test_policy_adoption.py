"""Letting the standard take over a policy the customer already has.

The plan matches by display name, which is right for a tenant we set up and
wrong for every tenant we inherit. Fonnafly has five sensible policies with
five names nobody at Sybr chose, so deploying the standard beside them produces
ten policies where five were meant — and overlapping Conditional Access is
harder to reason about than no deployment at all.

The whole design is about not guessing. A suggestion is a shortlist for a
person; a policy overwritten because a fuzzy matcher thought it looked familiar
is a production incident with a plausible-sounding cause.
"""

from __future__ import annotations

import pytest

from app.core.policy_adoption import (
    AdoptionError,
    describe,
    load_mapping,
    save_mapping,
    score,
    suggest,
    validate,
)
from app.modules.m365_audit.policy_deploy import CREATE, DELETE, UPDATE, DeployError, build_plan

REPORT_ONLY = "enabledForReportingButNotEnforced"


def _p(name, *, pid=None, controls=("mfa",), users=("All",), roles=(), apps=("all",), state=REPORT_ONLY):
    body = {
        "displayName": name,
        "state": state,
        "conditions": {
            "users": {"includeUsers": list(users), "includeRoles": list(roles),
                      "excludeGroups": ["bg"]},
            "clientAppTypes": list(apps),
        },
        "grantControls": {"operator": "OR", "builtInControls": list(controls)},
    }
    if pid:
        body["id"] = pid
    return body


# ── Suggesting ───────────────────────────────────────────────────────────────

def test_the_same_policy_under_a_different_name_scores_highly():
    """"All users require MFA" and "Sybr — Require MFA for all users" share no
    words a matcher could use, and are the same policy."""
    ours = _p("Sybr — Require MFA for all users")
    theirs = _p("All users require MFA", pid="1")

    points, reasons = score(ours, theirs)

    assert points >= 5
    assert any("same controls" in r for r in reasons)


def test_two_policies_that_do_different_things_are_not_suggested():
    ours = _p("Sybr — Block legacy authentication", controls=["block"], apps=["other"])
    theirs = _p("Require compliant device", pid="1", controls=["compliantDevice"])

    candidates = suggest([ours], [theirs])

    assert candidates["Sybr — Block legacy authentication"] == []


def test_candidates_come_back_best_first_with_their_reasons():
    ours = _p("Sybr — Require MFA for administrators", users=[], roles=["r1"])
    close = _p("Admin MFA", pid="1", users=[], roles=["r1"])
    looser = _p("Something with MFA", pid="2", users=["All"])

    candidates = suggest([ours], [close, looser])["Sybr — Require MFA for administrators"]

    assert candidates[0]["policy_id"] == "1"
    assert candidates[0]["score"] > candidates[-1]["score"]
    assert candidates[0]["reasons"]


def test_a_suggestion_on_its_own_changes_nothing():
    """The load-bearing property. Suggestions are a shortlist for a person."""
    ours = _p("Sybr — Require MFA for all users")
    theirs = _p("All users require MFA", pid="1")

    assert suggest([ours], [theirs])["Sybr — Require MFA for all users"]

    plan = build_plan("acme", [theirs], [ours])
    assert [c.action for c in plan.changes] == [CREATE], "a suggestion reached the plan"


# ── The mapping ──────────────────────────────────────────────────────────────

def test_adoption_updates_the_existing_policy_instead_of_creating_a_second():
    ours = _p("Sybr — Require MFA for all users")
    theirs = _p("All users require MFA", pid="1", state="enabled")

    plan = build_plan("acme", [theirs], [ours], adopt={"Sybr — Require MFA for all users": "1"})

    assert len(plan.changes) == 1
    change = plan.changes[0]
    assert change.action == UPDATE
    assert change.policy_id == "1"


def test_the_rename_is_visible_in_the_plan():
    """It is a real change to a real policy, so the operator sees it and knows
    what they agreed to."""
    ours = _p("Sybr — Require MFA for all users")
    theirs = _p("All users require MFA", pid="1")

    change = build_plan(
        "acme", [theirs], [ours], adopt={"Sybr — Require MFA for all users": "1"}
    ).changes[0]

    assert "displayName" in change.fields
    assert change.adopts == "All users require MFA"


def test_adopting_a_policy_that_has_since_been_deleted_is_refused():
    """Falling back to a create would produce the duplicate adoption exists to
    avoid, at the moment somebody believed they had avoided it."""
    ours = _p("Sybr — Require MFA for all users")

    with pytest.raises(DeployError, match="not in this tenant"):
        build_plan("acme", [], [ours], adopt={"Sybr — Require MFA for all users": "gone"})


def test_an_adopted_policy_is_not_also_deleted_as_unknown():
    """It is the standard's now, whatever it is still called at this moment."""
    ours = _p("Sybr — Require MFA for all users")
    theirs = _p("All users require MFA", pid="1")

    plan = build_plan("acme", [theirs], [ours], adopt={"Sybr — Require MFA for all users": "1"})

    assert DELETE not in [c.action for c in plan.changes]
    assert plan.unmanaged == [], "an adopted policy is not unmanaged"


def test_an_adopted_policy_is_not_also_a_name_match_for_another():
    """Otherwise one live policy backs two changes and the second overwrites
    the first."""
    a = _p("Shared name")
    b = _p("Other")
    theirs = _p("Shared name", pid="1")

    plan = build_plan("acme", [theirs], [a, b], adopt={"Other": "1"})

    by_action = {c.name: c.action for c in plan.changes}
    assert by_action["Other"] == UPDATE
    assert by_action["Shared name"] == CREATE


# ── Refusing a mapping that cannot mean what it says ─────────────────────────

def test_two_template_policies_cannot_adopt_one_live_policy():
    ours = [_p("First"), _p("Second")]
    theirs = [_p("Theirs", pid="1")]

    with pytest.raises(AdoptionError, match="cannot become two"):
        validate({"First": "1", "Second": "1"}, ours, theirs)


def test_a_mapping_naming_a_policy_outside_the_standard_is_refused():
    with pytest.raises(AdoptionError, match="not a policy in this standard"):
        validate({"Invented": "1"}, [_p("First")], [_p("Theirs", pid="1")])


def test_a_mapping_to_a_missing_policy_is_refused():
    with pytest.raises(AdoptionError, match="no longer exists"):
        validate({"First": "gone"}, [_p("First")], [_p("Theirs", pid="1")])


def test_a_sound_mapping_passes():
    validate({"First": "1"}, [_p("First")], [_p("Theirs", pid="1")])


# ── Remembering it ───────────────────────────────────────────────────────────

@pytest.fixture()
def audits(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path)
    return tmp_path


def test_a_confirmed_mapping_survives_so_nobody_is_asked_twice(audits):
    save_mapping("Acme", {"Sybr — Require MFA for all users": "1"})

    assert load_mapping("Acme") == {"Sybr — Require MFA for all users": "1"}


def test_a_customer_with_no_mapping_adopts_nothing(audits):
    assert load_mapping("Acme") == {}


def test_an_unreadable_mapping_raises_rather_than_adopting_nothing(audits):
    """Quietly becoming "adopt nothing" would deploy duplicates beside the
    policies it was meant to take over."""
    (audits / "Acme").mkdir(parents=True)
    (audits / "Acme" / "policy_adoption.json").write_bytes(b"not an envelope")

    with pytest.raises(AdoptionError):
        load_mapping("Acme")


def test_the_mapping_reads_back_with_the_current_names(audits):
    live = [_p("All users require MFA", pid="1")]

    described = describe({"Sybr — Require MFA for all users": "1"}, live)

    assert described[0]["current_name"] == "All users require MFA"
    assert described[0]["present"] is True


def test_a_mapping_pointing_at_something_gone_says_so(audits):
    described = describe({"Sybr — Require MFA for all users": "1"}, [])

    assert described[0]["present"] is False
