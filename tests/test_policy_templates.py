"""The policies we deploy, as data — and the placeholder that must be filled.

Every policy in the shipped template excludes a break-glass group whose id
differs per tenant. An unfilled placeholder is an exclusion that excludes
nobody, inside a policy that applies to everybody.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.core.policy_templates import (
    TemplateError,
    annotations,
    list_templates,
    load_template,
    placeholders_in,
    render,
)
from app.modules.m365_audit.policy_deploy import REPORT_ONLY, lockout_risk

FILLED = {"break_glass_group": "11111111-2222-3333-4444-555555555555"}


def test_the_shipped_template_loads():
    doc = load_template("sybr-baseline-ca")

    assert doc["version"]
    assert len(doc["policies"]) >= 3


def test_rendering_refuses_while_a_placeholder_is_unfilled():
    """The failure this prevents: excludeGroups: ["{{break_glass_group}}"]."""
    with pytest.raises(TemplateError, match="break_glass_group"):
        render("sybr-baseline-ca", {})


def test_rendering_refuses_a_blank_value_too():
    with pytest.raises(TemplateError):
        render("sybr-baseline-ca", {"break_glass_group": "   "})


def test_a_rendered_policy_carries_the_real_group_id():
    policies = render("sybr-baseline-ca", FILLED)

    for policy in policies:
        excluded = policy["conditions"]["users"].get("excludeGroups", [])
        assert FILLED["break_glass_group"] in excluded
    assert "{{" not in json.dumps(policies)


def test_every_shipped_policy_survives_the_lockout_rail():
    """A standard that our own guard would refuse is a standard nobody can
    deploy. Checked at the state they would be enabled in, not the state they
    arrive in — report-only passes the rail trivially and would prove nothing.
    """
    for policy in render("sybr-baseline-ca", FILLED):
        enabled = {**policy, "state": "enabled"}
        assert lockout_risk(enabled) is None, policy["displayName"]


def test_every_shipped_policy_arrives_report_only():
    for policy in render("sybr-baseline-ca", FILLED):
        assert policy["state"] == REPORT_ONLY, policy["displayName"]


def test_the_rationale_is_stripped_before_anything_is_sent():
    """Graph rejects fields it does not know."""
    for policy in render("sybr-baseline-ca", FILLED):
        assert "why" not in policy


def test_the_rationale_survives_for_the_person_approving():
    """A plan that says "3 policies will be created" is not one you can
    consent to."""
    for lang in ("no", "en"):
        why = annotations("sybr-baseline-ca", lang)
        assert len(why) >= 3
        assert all(text.strip() for text in why.values())


def test_both_languages_are_present_everywhere_a_person_reads():
    doc = load_template("sybr-baseline-ca")

    for field in ("name", "description"):
        assert set(doc[field]) >= {"no", "en"}
    for policy in doc["policies"]:
        assert set(policy["why"]) >= {"no", "en"}, policy["displayName"]


def test_a_duplicate_policy_name_is_refused(tmp_path, monkeypatch):
    """Names are how a plan matches a template to a tenant."""
    import app.core.policy_templates as mod

    doc = {"id": "d", "version": "1", "name": {"no": "D", "en": "D"}, "policies": [
        {"displayName": "Same"}, {"displayName": "Same"},
    ]}
    (tmp_path / "d.json").write_text(json.dumps(doc))
    monkeypatch.setattr(mod, "TEMPLATE_DIR", tmp_path)

    with pytest.raises(TemplateError, match="Duplicate"):
        load_template("d")


def test_the_listing_names_what_a_tenant_must_supply():
    entry = next(t for t in list_templates() if t["id"] == "sybr-baseline-ca")

    assert entry["requires"] == ["break_glass_group"]
    assert entry["policies"] >= 3


def test_the_declared_requirements_match_the_placeholders_actually_used():
    """A requirement nobody reads for, or a placeholder nobody declares, and
    the operator is asked the wrong question."""
    doc = load_template("sybr-baseline-ca")

    assert placeholders_in(doc) == set(doc.get("requires", {}))
