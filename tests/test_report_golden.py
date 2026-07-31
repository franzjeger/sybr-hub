"""A change detector over every number the report puts in front of a reader.

This is not a correctness oracle. The fixture is synthetic, so it cannot say
whether 96% is the *right* answer for a healthy tenant. What it can say is
that today's answer differs from yesterday's, which is the thing nothing else
here catches: a parser change that quietly moves a figure.

Almost every defect found in this codebase moved a number without moving a
test — a connector count from one to three, eleven consent grants out of a
tally, report-only policies into the enforced count, a compliance percentage
whose denominator changed shape. Each was found by a person reading output,
not by the suite.

So when a value below changes, that is not a failure to route around. Work out
which change caused it and whether the new number is more truthful than the
old, then update the constant in the same commit and say why in the message.
"""

from __future__ import annotations

import pathlib

import pytest

from app.reports.generator import build_report_context
from tests.audit_fixture import FULL_AUDIT

# Derived from the synthetic healthy tenant in tests/audit_fixture.py.
GOLDEN = {
    "ca_enabled": 4,
    "compliance_assessed": 27,
    "compliance_info": 4,
    "compliance_pass": 26,
    "compliance_pct": 96.0,
    "compliance_total": 31,
    "exchange_connectors": 0,
    "exchange_transport_rules": 0,
    "ga_count": 3,
    "mfa_pct": 100.0,
    "recommendations": 1,
    "risk_grade": "A",
    "risk_score": 94,
    "users_total": 40,
}


@pytest.fixture(scope="module")
def report(tmp_path_factory) -> dict:
    d = tmp_path_factory.mktemp("golden") / "Acme_AS" / "2026-01-01_0900"
    d.mkdir(parents=True)
    for name, content in FULL_AUDIT.items():
        (d / name).write_text(content, encoding="utf-8")
    return build_report_context("Acme AS", "acme.no", d, [], lang="no", frameworks="all")


def _actual(ctx: dict) -> dict:
    return {
        "ca_enabled": ctx["ca"]["enabled"],
        "compliance_assessed": ctx["compliance_assessed"],
        "compliance_info": ctx["compliance_info"],
        "compliance_pass": ctx["compliance_pass"],
        "compliance_pct": ctx["compliance_pct"],
        "compliance_total": ctx["compliance_total"],
        "exchange_connectors": ctx["exchange"]["connectors"],
        "exchange_transport_rules": ctx["exchange"]["transport_rules"],
        "ga_count": ctx["admin_roles"]["global_admin_count"],
        "mfa_pct": ctx["mfa"]["pct"],
        "recommendations": len(ctx["recommendations"]),
        "risk_score": ctx["risk"]["score"],
        "risk_grade": ctx["risk"]["grade"],
        "users_total": ctx["users"]["total"],
    }


def test_no_headline_number_has_moved(report):
    assert _actual(report) == GOLDEN


def test_the_compliance_arithmetic_holds(report):
    """Independent of the snapshot: the parts must sum to the whole."""
    assert report["compliance_assessed"] + report["compliance_info"] == report["compliance_total"]
    expected = round(report["compliance_pass"] / max(report["compliance_assessed"], 1) * 100, 0)
    assert report["compliance_pct"] == expected


def test_every_control_is_in_exactly_one_bucket(report):
    """No control counted twice, none dropped between the buckets."""
    statuses = [c["status"] for c in report["compliance"]]
    assert len(statuses) == report["compliance_total"]
    assert statuses.count("info") == report["compliance_info"]
    assert statuses.count("pass") == report["compliance_pass"]


def test_a_healthy_tenant_produces_no_unverifiable_headline_metrics(report):
    """The fixture is deliberately complete, so nothing should read as absent."""
    for section in ("mfa", "ca", "admin_roles", "secure_score"):
        assert report[section].get("has_data") is True, f"{section} read as missing"
