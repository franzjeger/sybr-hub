"""The comprehensive Best Practice Conditional Access suite, and picking from it.

The suite is a broad set of CA policies grounded in Microsoft/CIS guidance,
each documented, tiered, and licence-tagged. The operator ticks which to deploy
("velge av"); plan and apply filter to that same subset so the approved plan is
the one that runs. The annotations (why/tier/requires_license) are for the
operator and must never reach Graph, which rejects unknown fields.
"""

from __future__ import annotations

from app.core.policy_templates import (
    list_templates,
    load_template,
    metadata,
    placeholders_in,
    render,
)
from app.web.routes.policy_deploy import _select_policies

TID = "sybr-best-practice-ca"


def test_the_suite_is_listed_and_comprehensive():
    ids = {t["id"] for t in list_templates("en")}
    assert TID in ids
    assert len(load_template(TID)["policies"]) >= 10


def test_annotations_never_reach_graph():
    rendered = render(TID, {"break_glass_group": "GROUP-1"})
    for policy in rendered:
        for annotation in ("why", "tier", "requires_license"):
            assert annotation not in policy, f"{annotation} leaked into a Graph body"
    # …but the break-glass exclusion did get filled everywhere it appears.
    assert "{{break_glass_group}}" not in str(rendered)
    assert placeholders_in(load_template(TID)) == {"break_glass_group"}


def test_metadata_carries_tier_and_licence():
    meta = metadata(TID, "en")
    tiers = {m["tier"] for m in meta.values()}
    assert tiers == {"essential", "recommended", "extended"}
    p2 = [n for n, m in meta.items() if m["requires_license"] == "entra_p2"]
    assert len(p2) == 2, "the two risk-based policies require Entra ID P2"
    # every policy has a rationale in the requested language
    assert all(m["why"] for m in meta.values())


def test_every_policy_deploys_report_only_first():
    for policy in load_template(TID)["policies"]:
        assert policy["state"] == "enabledForReportingButNotEnforced"


def test_every_policy_excludes_the_break_glass_group():
    for policy in load_template(TID)["policies"]:
        users = policy["conditions"]["users"]
        assert "{{break_glass_group}}" in (users.get("excludeGroups") or []), (
            f"{policy['displayName']} does not exclude break-glass — a policy "
            f"that can lock everyone out"
        )


# ── Picking a subset ─────────────────────────────────────────────────────────

_DESIRED = [
    {"displayName": "A"}, {"displayName": "B"}, {"displayName": "C"},
]


def test_selection_keeps_only_ticked_policies():
    got = _select_policies(_DESIRED, {"select": ["A", "C"]})
    assert [p["displayName"] for p in got] == ["A", "C"]


def test_empty_selection_means_the_whole_suite():
    assert _select_policies(_DESIRED, {}) == _DESIRED
    assert _select_policies(_DESIRED, {"select": []}) == _DESIRED
