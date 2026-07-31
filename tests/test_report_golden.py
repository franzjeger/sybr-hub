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
import re

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


# ---------------------------------------------------------------------------
# Recommendations carry the same provenance the CIS controls do. These are the
# customer-facing "do this" items, and until now nothing said which collected
# file each one was formed from.
# ---------------------------------------------------------------------------

def test_every_recommendation_names_its_source(report):
    """Except the ones whose evidence genuinely is not an M365 audit file.

    The Fortigate and UniFi findings come from other modules, and three Azure
    ones read per-subscription files chosen at run time. Naming a file for
    those would be a guess, and a citation that does not land is worse than
    none.
    """
    exempt = ("finding-fg-", "finding-uf-")
    missing = [
        r.get("finding_id") or r["title"]
        for r in report["recommendations"]
        if not r.get("evidence")
        and not str(r.get("finding_id", "")).startswith(exempt)
    ]
    assert not missing, f"recommendations with no source: {missing}"


def test_a_recommendation_only_cites_files_the_run_collected(report):
    for r in report["recommendations"]:
        for f in r.get("evidence", []):
            assert f in report["file_contents"], (
                f"{r.get('finding_id')} cites {f}, which this run has not got"
            )


def test_the_mfa_recommendation_cites_the_mfa_files():
    """A named case, so the mapping is pinned and not merely non-empty."""
    from app.reports.generator import _build_recommendations

    recs = _build_recommendations(
        mfa={"has_data": True, "no_mfa": 3, "pct": 50.0, "total": 6,
             "users": [], "mfa_registered": 3, "ca_covered": 0},
        spf_dmarc=[], secure_score={}, ext_fwd="", risky_users="", licenses=[],
        file_contents={"04_mfa_methods.txt": "x\n", "04b_mfa_ca_analysis.txt": "y\n"},
    )
    mfa_rec = [r for r in recs if r.get("finding_id") == "finding-mfa"][0]
    assert mfa_rec["evidence"] == ["04_mfa_methods.txt", "04b_mfa_ca_analysis.txt"]


def test_a_recommendation_drops_a_file_the_run_did_not_produce():
    from app.reports.generator import _build_recommendations

    recs = _build_recommendations(
        mfa={"has_data": True, "no_mfa": 3, "pct": 50.0, "total": 6,
             "users": [], "mfa_registered": 3, "ca_covered": 0},
        spf_dmarc=[], secure_score={}, ext_fwd="", risky_users="", licenses=[],
        file_contents={"04_mfa_methods.txt": "x\n"},   # no 04b
    )
    mfa_rec = [r for r in recs if r.get("finding_id") == "finding-mfa"][0]
    assert mfa_rec["evidence"] == ["04_mfa_methods.txt"]


def test_every_recommendation_in_the_source_declares_a_source_file():
    """Static, because the dynamic check only sees what a tenant triggers.

    The synthetic tenant is healthy and raises one recommendation, so the test
    above walks one of twenty-eight — it let a mutation stripping the evidence
    off the Global Administrator finding pass. This one reads the builder
    itself, so a new recommendation cannot ship without provenance whether or
    not any fixture happens to fire it.
    """
    import inspect

    from app.reports import generator as gen

    src = inspect.getsource(gen._build_recommendations)
    exempt = ('"finding-fg-', '"finding-uf-')
    # Azure recommendations read per-subscription files picked at run time;
    # naming one would be a guess. They are listed rather than pattern-matched
    # so adding a third does not silently inherit the exemption.
    exempt_titles = ('t("rec_advisor_title"', 't("rec_orphaned_title"', 't("rec_backup_title"')

    missing = []
    for m in re.finditer(r"recs\.append\(\{", src):
        depth, i = 0, m.end() - 1
        while i < len(src):                      # find this dict's closing brace
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        block = src[m.start():i]
        if '"evidence"' in block:
            continue
        if any(e in block for e in exempt) or any(e in block for e in exempt_titles):
            continue
        title = re.search(r'"title":\s*(.+)', block)
        missing.append(title.group(1)[:60] if title else block[:60])

    assert not missing, f"recommendations with no declared source: {missing}"
