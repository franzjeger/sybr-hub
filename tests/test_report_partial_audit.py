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

import re
from pathlib import Path

import pytest

from app.reports.generator import (
    _EVIDENCE_MAP,
    build_report_context,
    save_audit_metrics,
)
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


# ── The other half of the invariant ───────────────────────────────────────────
#
# The check above catches a report that gets *louder* on less evidence. It
# cannot catch one that stays exactly as reassuring — a control still reading
# "pass" when the file behind it is gone, because "we found nothing bad" and
# "we could not look" produce the same silence. That is the shape behind most
# of what this branch pulled out of the report: a measured zero standing in for
# an unmeasured one.
#
# _EVIDENCE_MAP already declares which files each verdict is formed from, and a
# sibling test requires every control to appear in it. That declaration is what
# makes this mechanical: remove exactly what a control says it reads, and the
# control must stop claiming anything.


@pytest.mark.parametrize("cis_id", sorted(_EVIDENCE_MAP))
def test_a_control_stops_claiming_when_its_own_evidence_is_gone(baseline, tmp_path, cis_id):
    declared = set(_EVIDENCE_MAP[cis_id])
    partial = {k: v for k, v in FULL_AUDIT.items() if k not in declared}
    after = {cid: st for (cid, _t), st in _statuses(_render(tmp_path, partial)).items()}
    got = after.get(cis_id)
    if got is None:
        return  # emitting no row at all is a valid way to claim nothing
    assert got == "info", (
        f"CIS {cis_id} still reports {got!r} with none of its declared evidence "
        f"present ({', '.join(sorted(declared))}). A verdict that survives the "
        f"removal of everything it reads was not formed from that evidence."
    )


# ── The shape collectors actually produce ─────────────────────────────────────
#
# Everything above removes files. Collectors do not remove on failure — they
# write prose into the file: "Error: {ex}", or a "(not available)" block naming
# the licence or permission that is missing. That is a different input, and the
# report used to read it differently. Three verdicts were formed from prose:
# Defender counted an error stub as one active alert and deducted four points;
# risky users had the guard but announced nothing; and the guard itself matched
# "requires" anywhere in the file, so one finding whose text used the word made
# the whole file read as unmeasured and its penalty vanish.
#
# The deletion sweep could not see any of them. Removal yields an empty string,
# which every reader already treats as absent.

_STUB = "Error: HTTP 403 Forbidden\n"


@pytest.mark.parametrize("stubbed", sorted(FULL_AUDIT))
def test_a_failed_fetch_never_creates_a_finding(baseline, tmp_path, stubbed):
    """A file that explains why it is empty must score as absent, not as read."""
    ctx = _render(tmp_path, {**FULL_AUDIT, stubbed: _STUB})
    violations: list[str] = []

    for title in sorted(_titles(ctx) - _titles(baseline)):
        violations.append(f"invented recommendation: {title}")

    before, after = _statuses(baseline), _statuses(ctx)
    for key, status in after.items():
        prev = before.get(key)
        if prev is not None and status != prev and status != "info":
            violations.append(f"control {key[0]} ({key[1]}): {prev} → {status}")

    base_score, now_score = baseline["risk"]["score"], ctx["risk"]["score"]
    if base_score is not None and now_score is not None and now_score < base_score:
        violations.append(
            f"score {base_score} → {now_score}: the failure itself cost points"
        )

    assert not violations, (
        f"stubbing {stubbed} made the report say {len(violations)} new thing(s):\n  "
        + "\n  ".join(violations)
    )


def test_a_wholly_failed_audit_refuses_to_grade():
    """The end of the same line: every file a stub. Nothing may be claimed."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        ctx = _render(Path(tmp), {name: _STUB for name in FULL_AUDIT})

    assert ctx["risk"]["score"] is None
    assert ctx["risk"]["blocking_data_gaps"]
    assert _titles(ctx) == set()
    still_claiming = {k: v for k, v in _statuses(ctx).items() if v != "info"}
    assert not still_claiming, (
        "controls formed a verdict from prose explaining why there was no data: "
        + ", ".join(f"{cid} → {st}" for (cid, _t), st in sorted(still_claiming.items()))
    )


# ── How far the fixture actually reaches ──────────────────────────────────────
#
# Every invariant in this file is only as wide as FULL_AUDIT. A collector output
# the fixture does not contain cannot be removed, cannot be stubbed, and the
# controls reading it are never exercised in either direction. That is not a
# hypothetical: 19b_defender_active_alerts.txt is in the fixture, and the one
# reader that had no guard was found by hand rather than by these sweeps —
# because the guardless reader also logs nothing, so nothing pointed at it.
#
# The gap is closed: every collector output the report reads is in FULL_AUDIT.
# This keeps it that way. Adding a reader for a file the fixture does not have
# now fails, with the name to add.

_FIXTURE_GAPS: set[str] = set()


_OUTPUT = re.compile(r"""["']([0-9]{2}[a-z]?_[a-z0-9_]+\.(?:txt|json))["']""")
_SAVED = re.compile(r"""_save\(\s*(?:self\._fname\(\s*)?["']([0-9][^"']*\.(?:txt|json))["']""")


def test_the_fixture_gap_does_not_grow():
    root = Path(__file__).resolve().parents[1]
    written: set[str] = set()
    for path in (root / "app/modules").rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        written |= set(_SAVED.findall(path.read_text(encoding="utf-8")))
    read = set(_OUTPUT.findall((root / "app/reports/generator.py").read_text(encoding="utf-8")))

    new = sorted((written & read) - set(FULL_AUDIT) - _FIXTURE_GAPS)
    assert not new, (
        "these collector outputs are read by the report but absent from "
        "tests/audit_fixture.py, so no sweep in this file can reach them:\n  "
        + "\n  ".join(new)
        + "\n\nAdd them to FULL_AUDIT with realistic healthy-tenant content, or "
        "record them in _FIXTURE_GAPS with a reason."
    )


def test_the_recorded_gaps_are_still_gaps():
    """A ratchet nobody tightens is a comment. When one is closed, drop it."""
    closed = sorted(_FIXTURE_GAPS & set(FULL_AUDIT))
    assert not closed, (
        "these are in the fixture now — remove them from _FIXTURE_GAPS: "
        + ", ".join(closed)
    )


def test_the_fixture_covers_every_file_the_report_reads():
    """Stated as its own claim, not just as the absence of new entries.

    _FIXTURE_GAPS being empty is the whole point; a future exemption should
    have to delete this test, which is harder to do by accident than adding a
    name to a set.
    """
    assert not _FIXTURE_GAPS, (
        "the fixture no longer covers everything the report reads: "
        + ", ".join(sorted(_FIXTURE_GAPS))
    )
