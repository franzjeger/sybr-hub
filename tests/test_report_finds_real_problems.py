"""Contract test: a badly-run tenant must still be caught.

The rest of this suite pushes in one direction. The empty-audit test, the
partial-audit test and every data-quality fix behind them make the report
*quieter* — axes disappear, controls drop to "info", recommendations stop
firing, metrics become NULL. All of it is verified against a deliberately
healthy fixture, which proves the report raises no false positives and proves
nothing at all about whether it still raises true ones.

That asymmetry is the risk those fixes created. A ``has_data`` gate that is
one condition too broad does not fail any test here — it just silently stops
reporting something. On a security auditor that is the worse failure: a false
finding wastes an hour, a suppressed one leaves a tenant exposed while the
report says everything is fine.

So: the same tenant, badly run. Every scored area has a real problem, and each
one has to survive all the way to a finding.
"""

from __future__ import annotations

from collections import Counter

import pytest

from app.reports.generator import build_report_context
from tests.audit_fixture import BROKEN_AUDIT, FULL_AUDIT

# Every finding_id the report knows how to raise, given inputs that warrant it.
EXPECTED_FINDINGS = [
    "finding-mfa",
    "finding-securescore",
    "finding-email",
    "finding-fwd",
    "finding-ga",
    "finding-intune",
    "finding-sp",
    "finding-risky",
    "finding-fg-admin-2fa",
    "finding-fg-allow-all",
    "finding-fg-no-logging",
    "finding-fg-no-trusthost",
    "finding-uf-open-wifi",
    "finding-uf-default-creds",
    "finding-uf-eol",
    "finding-uf-outdated-fw",
]


@pytest.fixture
def broken(tmp_path) -> dict:
    d = tmp_path / "Acme_AS" / "2026-01-01_0900"
    d.mkdir(parents=True)
    for name, content in BROKEN_AUDIT.items():
        (d / name).write_text(content, encoding="utf-8")
    return build_report_context("Acme AS", "acme.no", d, [], lang="no", frameworks="all")


def _finding_ids(ctx: dict) -> set[str]:
    return {r.get("finding_id", "") for r in ctx.get("recommendations", [])}


# ── Findings ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("finding_id", EXPECTED_FINDINGS)
def test_each_finding_still_fires(broken, finding_id):
    assert finding_id in _finding_ids(broken), (
        f"{finding_id} did not fire on a tenant that warrants it — a data-quality "
        "guard is one condition too broad"
    )


def test_the_worst_problems_are_ranked_critical(broken):
    """Priority is what a technician triages by, so it is part of the finding."""
    critical = {
        r["finding_id"] for r in broken["recommendations"]
        if r.get("priority") == "critical" and r.get("finding_id")
    }
    assert {"finding-mfa", "finding-fwd", "finding-uf-open-wifi"} <= critical


def test_findings_name_the_affected_things(broken):
    """A count without the list is not actionable."""
    by_id = {r.get("finding_id"): r for r in broken["recommendations"]}
    assert by_id["finding-uf-open-wifi"]["sub_items"] == ["Acme-Open"]
    assert len(by_id["finding-fg-admin-2fa"]["sub_items"]) == 2
    assert "?" not in by_id["finding-fg-no-trusthost"]["sub_items"], "admin name lost"


# ── Scores ────────────────────────────────────────────────────────────────────


def test_the_grade_reflects_the_state(broken):
    assert broken["risk"]["score"] is not None, "gradeable — MFA data is present"
    assert broken["risk"]["grade"] == "F"


def test_the_radar_shows_the_weak_axes(broken):
    radar = broken["risk_radar"]
    assert radar, "the radar must still draw for a tenant we did measure"
    assert radar["Identitet"] < 40, "20% MFA and no CA policy"
    assert radar["Enheter"] < 50, "12 of 40 devices compliant"


def test_compliance_records_the_failures(broken):
    statuses = Counter(c["status"] for c in broken["compliance"])
    assert statuses["fail"] >= 8
    failed = {c["cis_id"] for c in broken["compliance"] if c["status"] == "fail"}
    # One per area the data-quality work touched, so an over-broad guard shows up.
    assert {"1.1.3", "1.1.4", "5.2.1", "5.2.2", "5.2.3", "7.2.1"} <= failed


@pytest.mark.parametrize(
    ("cis_id", "status"),
    [
        ("4.4", "warn"),    # external forwarding, via the 28b WARN file
        ("9.2", "warn"),    # active Defender alerts
        ("7.2.1", "fail"),  # anyone-with-the-link sharing
        ("5.2.3", "fail"),  # DKIM checked and absent
        ("6.1.1", "partial"),
    ],
)
def test_controls_reworked_in_this_branch_still_detect(broken, cis_id, status):
    """Each of these had its "no data" path fixed. This is the other half."""
    ctrl = next(c for c in broken["compliance"] if c["cis_id"] == cis_id)
    assert ctrl["status"] == status


# ── The two fixtures must actually differ ─────────────────────────────────────


def test_the_healthy_tenant_is_not_quietly_the_same_as_the_broken_one(broken, tmp_path):
    """Guards against the fixtures drifting into agreement, which would make
    both this file and the partial-audit file pass while asserting nothing."""
    d = tmp_path / "Healthy" / "2026-01-01_0900"
    d.mkdir(parents=True)
    for name, content in FULL_AUDIT.items():
        (d / name).write_text(content, encoding="utf-8")
    healthy = build_report_context("Acme AS", "acme.no", d, [], lang="no", frameworks="all")

    assert healthy["risk"]["grade"] == "A"
    assert len(_finding_ids(broken)) > len(_finding_ids(healthy)) + 10


# ── Robustness of the finding path itself ─────────────────────────────────────


@pytest.mark.parametrize("missing", ["name", "profile"])
def test_a_fortigate_admin_missing_a_field_does_not_kill_the_report(tmp_path, missing):
    """The audit JSON is read from disk, so it can predate a field or be a
    partial write. The filters around these findings use .get(); the sub-item
    labels indexed directly, so a KeyError escaped build_report_context and
    cost the entire report for the sake of a label.
    """
    import json

    admin = {"name": "admin", "profile": "super_admin",
             "two_factor": False, "trusthost": False}
    admin.pop(missing)
    files = dict(BROKEN_AUDIT)
    files["60_fortigate_audit.txt"] = json.dumps({
        "hostname": "acme-fgt-01",
        "admins": [admin],
        "policy_warnings": ["Policy 12 is an allow-all rule"],
    })

    d = tmp_path / "Acme_AS" / "2026-01-01_0900"
    d.mkdir(parents=True)
    for name, content in files.items():
        (d / name).write_text(content, encoding="utf-8")

    ctx = build_report_context("Acme AS", "acme.no", d, [], lang="no", frameworks="all")
    assert "finding-fg-admin-2fa" in _finding_ids(ctx), "the finding must survive too"
