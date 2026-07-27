"""Contract test: removing input must never create a finding.

``test_report_empty_audit.py`` covers the degenerate case — an audit that
collected nothing. Real audits are rarely that clean. What actually happens is
that twenty-five sections succeed and one hits a throttle, a permission gap, or
a licensing wall. An empty-audit check cannot catch a bug in that case, because
a ``has_data`` guard that only fires when *everything* is missing still passes
it. Two of the three defects this file first caught were exactly that shape.

The method: start from a healthy tenant (``tests/audit_fixture.py``), delete
one collector output, and re-render. The tenant is unchanged; only our
knowledge of it shrank. So the report may say *less* — a control moving to
"info", a metric to None, a radar axis disappearing — but it must never say
something *worse*. A finding that appears when evidence is removed was
manufactured by the absence.

What it caught on first run:

  * **CIS 4.4** read the wrong two files in both directions.
    ``28_exchange_mailbox_forwarding.txt`` is written unconditionally and is
    titled "MAILBOX FORWARDING", so ``"forwarding" in text`` was true for
    every tenant whose Exchange section ran — a guaranteed "external
    forwarding detected". Meanwhile the collector writes the real finding to
    ``28b_..._WARN.txt`` and ``29_..._WARN.txt``, neither of which the control
    ever opened. False positive for everyone, blind to the true positive.
  * **CIS 6.1.1** graded *fail* — "devices are enrolled but no Intune
    compliance policies are configured" — when the policy file was simply
    absent. Only reachable with devices present, so the empty-audit check
    could not see it.
  * **CIS 5.2.3** graded *fail* — "No DKIM record found" — for any domain
    whose DKIM lookup did not run. Per domain, so a multi-domain tenant
    collected a column of them.

A failure here names the file that was removed and the claim that appeared.
Fix the claim.
"""

from __future__ import annotations

import pytest

from app.reports.generator import build_report_context, save_audit_metrics
from tests.audit_fixture import FULL_AUDIT


def _render(tmp_path, files: dict[str, str]) -> dict:
    d = tmp_path / "Acme_AS" / "2026-01-01_0900"
    d.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (d / name).write_text(content, encoding="utf-8")
    return build_report_context("Acme AS", "acme.no", d, [], lang="no", frameworks="all")


def _titles(ctx: dict) -> set[str]:
    return {r.get("title", "") for r in ctx.get("recommendations", [])}


def _statuses(ctx: dict) -> dict[tuple[str, str], str]:
    return {(c["cis_id"], c["title"]): c["status"] for c in ctx.get("compliance", [])}


def _metrics(tmp_path, ctx: dict, monkeypatch) -> dict:
    written: dict = {}
    monkeypatch.setattr(
        "app.core.encryption.encrypted_write_json",
        lambda path, data: written.update(data),
    )
    monkeypatch.setattr("app.reports.generator._save_metrics_to_db", lambda *a, **k: None)
    save_audit_metrics(tmp_path, ctx)
    return written


# The conftest keyring mock is function-scoped and seeds a *fresh random key*
# per test, so a module-scoped fixture cannot build this — it would run before
# the mock and, worse, write an _audit_metrics.json no later test could
# decrypt. Build it once inside a function-scoped fixture and cache the plain
# dict, which needs no keyring to be read back.
_BASELINE: dict = {}


@pytest.fixture
def baseline(tmp_path_factory) -> dict:
    """The healthy tenant, fully audited."""
    if not _BASELINE:
        _BASELINE.update(_render(tmp_path_factory.mktemp("baseline"), FULL_AUDIT))
    return _BASELINE


# ── The fixture itself has to be healthy, or the test proves nothing ──────────


@pytest.mark.parametrize(
    "section",
    ["users", "mfa", "secure_score", "ca", "admin_roles", "intune", "sharepoint",
     "oauth", "groups", "azure", "purview", "signin_risk", "network"],
)
def test_every_fixture_section_parses(baseline, section):
    """A fixture file the parser silently rejects would make this whole test
    vacuous — the section would read as absent in the baseline too."""
    assert baseline[section].get("has_data") is True, (
        f"{section} did not parse; the fixture format has drifted from the parser"
    )


def test_the_baseline_tenant_grades_well(baseline):
    assert baseline["risk"]["grade"] == "A"
    assert baseline["backup_coverage"]["coverage_known"] is True
    graded = [s for s in _statuses(baseline).values() if s != "info"]
    assert len(graded) > 20, "too few controls assessed for the comparison to mean much"


def test_the_baseline_raises_no_false_findings(baseline):
    """One real finding — a single non-compliant device — and nothing else."""
    assert _titles(baseline) == {"Intune: 1 enhet(er) er ikke i samsvar"}


# ── The invariant ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("removed", sorted(FULL_AUDIT))
def test_removing_a_file_never_creates_a_finding(baseline, tmp_path, removed, monkeypatch):
    """The three ways the report can say something worse on less evidence.

    Checked together against a single re-render — building the context is the
    expensive part, and one clear failure listing every violation beats three
    parametrised sets that each rebuild it.
    """
    partial = {k: v for k, v in FULL_AUDIT.items() if k != removed}
    ctx = _render(tmp_path, partial)
    violations: list[str] = []

    # 1. A recommendation that was not there before.
    for title in sorted(_titles(ctx) - _titles(baseline)):
        violations.append(f"invented recommendation: {title}")

    # 2. A compliance control that got louder. Going quiet ("info") is the
    #    correct response to losing evidence; anything else is a new claim.
    before, after = _statuses(baseline), _statuses(ctx)
    for key, status in after.items():
        prev = before.get(key)
        if prev is not None and status != prev and status != "info":
            violations.append(f"control {key[0]} ({key[1]}): {prev} → {status}")

    # 3. A persisted metric that became a measured 0 rather than None. This
    #    one outlives the report: it is written to the audit_metrics table and
    #    drawn as a real datapoint by the next audit's trend chart.
    base_metrics = _metrics(tmp_path, baseline, monkeypatch)
    now_metrics = _metrics(tmp_path, ctx, monkeypatch)
    for key, base_val in base_metrics.items():
        if isinstance(base_val, bool) or not isinstance(base_val, (int, float)):
            continue
        if base_val == 0:
            continue  # a measured zero staying zero is fine
        if now_metrics.get(key) == 0:
            violations.append(f"metric {key}: {base_val} → 0 (should be None)")

    assert not violations, (
        f"removing {removed} made the report say {len(violations)} new thing(s):\n  "
        + "\n  ".join(violations)
    )
