"""The tiered Conditional Access baseline library, and picking from it.

Instead of one monolithic package, the deploy library offers focused, named
baselines — IAM Core (identity floor), IAM Device & session hardening, and IAM
Risk-based (P2) — grounded in Microsoft/CIS guidance. Each policy is documented
twice: `effect` (what it does and who it hits) and `why` (why it matters), so a
technician knows exactly what they are deploying. The operator ticks which to
deploy ("velge av"); plan and apply filter to the same subset. The annotations
are for the operator and must never reach Graph, which rejects unknown fields.
"""

from __future__ import annotations

import pytest

from app.core.policy_templates import (
    list_templates,
    load_template,
    metadata,
    placeholders_in,
    render,
)
from app.web.routes.policy_deploy import _select_policies

# The tiered library — disjoint by theme, together the full recommended set.
TIERS = ["sybr-iam-core", "sybr-iam-hardening", "sybr-iam-riskbased"]


def test_the_library_offers_more_than_one_choice():
    ids = {t["id"] for t in list_templates("en")}
    for tid in TIERS:
        assert tid in ids, f"{tid} is not in the deploy library"
    # A real menu, not one package: the minimal baseline plus the tiers.
    assert len(ids) >= 4


def test_the_tiers_are_disjoint_and_cover_the_set():
    seen: set[str] = set()
    total = 0
    for tid in TIERS:
        names = {p["displayName"] for p in load_template(tid)["policies"]}
        assert not (names & seen), f"{tid} repeats a policy from another tier"
        seen |= names
        total += len(names)
    assert total == len(seen) >= 10


@pytest.mark.parametrize("tid", TIERS)
def test_annotations_never_reach_graph(tid):
    rendered = render(tid, {"break_glass_group": "GROUP-1"})
    for policy in rendered:
        for annotation in ("why", "effect", "tier", "requires_license"):
            assert annotation not in policy, f"{annotation} leaked into a Graph body"
    assert "{{break_glass_group}}" not in str(rendered)
    assert placeholders_in(load_template(tid)) == {"break_glass_group"}


@pytest.mark.parametrize("tid", TIERS)
def test_every_policy_is_documented_both_ways(tid):
    meta = metadata(tid, "en")
    assert meta, f"{tid} has no policies"
    for name, m in meta.items():
        assert m["effect"], f"{name} has no effect line (what it does)"
        assert m["why"], f"{name} has no why line (why it matters)"
        assert m["tier"] in {"essential", "recommended", "extended"}


def test_the_risk_based_tier_is_flagged_p2():
    meta = metadata("sybr-iam-riskbased", "en")
    assert meta and all(m["requires_license"] == "entra_p2" for m in meta.values())


@pytest.mark.parametrize("tid", TIERS)
def test_every_policy_deploys_report_only_and_excludes_break_glass(tid):
    for policy in load_template(tid)["policies"]:
        assert policy["state"] == "enabledForReportingButNotEnforced"
        users = policy["conditions"]["users"]
        assert "{{break_glass_group}}" in (users.get("excludeGroups") or []), (
            f"{policy['displayName']} does not exclude break-glass"
        )


# ── Picking a subset ─────────────────────────────────────────────────────────

_DESIRED = [{"displayName": "A"}, {"displayName": "B"}, {"displayName": "C"}]


def test_selection_keeps_only_ticked_policies():
    got = _select_policies(_DESIRED, {"select": ["A", "C"]})
    assert [p["displayName"] for p in got] == ["A", "C"]


def test_empty_selection_means_the_whole_baseline():
    assert _select_policies(_DESIRED, {}) == _DESIRED
    assert _select_policies(_DESIRED, {"select": []}) == _DESIRED
