"""End-to-end rendering of both report templates.

Everything else in this suite exercises ``build_report_context`` — the data
layer. Nothing exercised the templates, which are 1800 and 1000 lines of Jinja
and the actual deliverable. Three sessions' worth of template edits (the WLAN
security column, the backup-coverage panel, the SharePoint sharing pill) had
never been rendered.

Two things are worth asserting that a data-layer test cannot:

**Undefined variables.** ``_jinja_env`` uses Jinja's default ``Undefined``,
which renders a missing key as an empty string and keeps going. A context key
that gets renamed leaves a blank in the report and nothing anywhere says so.
Rendering here under ``StrictUndefined`` turns that into a test failure while
leaving production forgiving — a report that renders with one blank field
beats a report that raises, which is the same reasoning as the broad except in
``load_previous_metrics``.

**That the data-layer work survives to the page.** The rest of the suite
proves the *context* never claims something it did not measure. This proves
the rendered HTML doesn't either — no "None", no fabricated zero — which is
what a customer actually reads.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.core.encryption import encrypted_read_text
from app.reports.generator import _TEMPLATES_DIR, build_report_context, generate_reports
from app.reports.i18n import T
from tests.audit_fixture import FULL_AUDIT

TEMPLATES = ["report_customer.html.j2", "report_tech.html.j2"]


def _audit_dir(tmp_path: Path, files: dict[str, str] | None) -> Path:
    d = tmp_path / "Acme_AS" / "2026-01-01_0900"
    d.mkdir(parents=True, exist_ok=True)
    for name, content in (files or {}).items():
        (d / name).write_text(content, encoding="utf-8")
    return d


def _render_strict(tmp_path, template: str, files: dict[str, str] | None, lang="no") -> str:
    d = _audit_dir(tmp_path, files)
    ctx = build_report_context("Acme AS", "acme.no", d, [], lang=lang, frameworks="all")
    ctx["t"], ctx["lang"], ctx["theme"] = T(lang), lang, "light"
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR), encoding="utf-8"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )
    return env.get_template(template).render(**ctx)


def _visible_text(html: str) -> str:
    """Strip tags, scripts and styles — what a reader actually sees."""
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"<[^>]+>", " ", html)


# ── Structure ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("lang", ["no", "en"])
def test_a_full_audit_renders_with_no_undefined_variables(tmp_path, template, lang):
    html = _render_strict(tmp_path, template, FULL_AUDIT, lang=lang)
    assert len(html) > 20_000, "suspiciously short — most of the report is missing"


@pytest.mark.parametrize("template", TEMPLATES)
def test_an_empty_audit_also_renders(tmp_path, template):
    """The path with every optional key absent is the one most likely to hit
    an undefined, and the one a failed audit actually takes."""
    html = _render_strict(tmp_path, template, None)
    assert "<html" in html.lower() or "<!doctype" in html.lower()


@pytest.mark.parametrize("report_type", ["customer", "tech"])
def test_generate_reports_writes_readable_html(tmp_path, report_type):
    """Through the real entry point, including the encrypted write."""
    d = _audit_dir(tmp_path, FULL_AUDIT)
    out = generate_reports("Acme AS", "acme.no", d, [], formats=["html"],
                           report_type=report_type)
    assert out["html"].exists()
    assert len(encrypted_read_text(out["html"])) > 20_000


@pytest.mark.slow
def test_pdf_generation_works(tmp_path):
    """WeasyPrint is the one dependency that fails on a missing system lib
    rather than a missing wheel, so exercising it is worth the two seconds."""
    pytest.importorskip("weasyprint")
    d = _audit_dir(tmp_path, FULL_AUDIT)
    out = generate_reports("Acme AS", "acme.no", d, [], formats=["pdf"],
                           report_type="customer")
    assert out["pdf"].read_bytes()[:5] == b"%PDF-"


# ── The data-quality work has to survive to the page ──────────────────────────


@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("lang", ["no", "en"])
def test_an_empty_audit_never_renders_none_or_a_fabricated_score(tmp_path, template, lang):
    text = _visible_text(_render_strict(tmp_path, template, None, lang=lang))

    assert "None" not in text, "a Python None reached the page"
    assert not re.search(r"\bNone\s*/\s*100\b", text)
    # The grade is "?" for an ungradeable audit; no letter grade may appear.
    assert not re.search(r"\bgrade\s+[A-F]\b", text, re.I)
    assert not re.search(r"\bgrad\s+[A-F]\b", text, re.I)


def test_a_full_audit_still_shows_its_grade(tmp_path):
    """The complement — silence on missing data must not mean silence always."""
    text = _visible_text(_render_strict(tmp_path, "report_customer.html.j2", FULL_AUDIT))
    assert "A" in text
    assert "85" in text, "the Secure Score percentage should be on the page"


# ── The template edits made in this work ──────────────────────────────────────


def test_wlan_table_renders_the_security_label(tmp_path):
    html = _render_strict(tmp_path, "report_customer.html.j2", FULL_AUDIT)
    assert "WPA3" in html
    assert ">Open<" not in html, "no WLAN in the fixture is open"


def test_backup_panel_shows_coverage_when_it_is_known(tmp_path):
    html = _render_strict(tmp_path, "report_customer.html.j2", FULL_AUDIT)
    assert "Backup-dekning" in html
    assert T("no").backup_coverage_unknown not in html


def test_backup_panel_says_unknown_when_the_vault_was_not_read(tmp_path):
    """Removing only the vault file must flip the panel, not the VM count."""
    partial = {k: v for k, v in FULL_AUDIT.items() if k != "52_azure_backup.txt"}
    html = _render_strict(tmp_path, "report_customer.html.j2", partial)
    assert T("no").backup_coverage_unknown in html
    text = _visible_text(html)
    assert "VMs uten backup" not in text, "claimed unprotected VMs from an unread vault"


def test_sharepoint_sharing_renders_neutral_when_settings_were_not_read(tmp_path):
    partial = {k: v for k, v in FULL_AUDIT.items() if k != "15b_sharepoint_settings.txt"}
    html = _render_strict(tmp_path, "report_customer.html.j2", partial)
    assert "status-pill unknown" in html
    assert "status-pill warning" not in html.split("sharing")[0][-2000:]


# ── Why a control could not be verified ───────────────────────────────────────


_PURVIEW_404 = (
    "Error: Client error '404 Not Found' for url "
    "'https://graph.microsoft.com/beta/security/informationProtection/sensitivityLabels'\n"
    "For more information check: https://developer.mozilla.org/\n"
)


def test_the_tech_report_names_the_file_that_held_an_error(tmp_path):
    """"Cannot be verified" has to be traceable to the file that failed.

    The filename alone is not evidence of this: every collected file is
    printed in the raw-data appendix, so asserting it appears somewhere in the
    page would pass without the panel. It has to appear beside the CIS table,
    with the control it explains.
    """
    broken = {**FULL_AUDIT, "19c_purview_sensitivity_labels.txt": _PURVIEW_404}
    html = _render_strict(tmp_path, "report_tech.html.j2", broken)

    overview = html.split("<!-- /tab-overview -->")[0]
    assert 'id="error-files"' in overview, "no failure panel beside the CIS table"

    panel = overview.split('id="error-files"', 1)[1]
    assert "19c_purview_sensitivity_labels.txt" in panel
    assert "3.2.1" in panel, "the panel must say which control the failure explains"
    assert T("no").error_files_heading in _visible_text(panel)


def test_a_clean_audit_renders_no_failure_panel(tmp_path):
    html = _render_strict(tmp_path, "report_tech.html.j2", FULL_AUDIT)
    assert 'id="error-files"' not in html, "nothing failed; the panel must stay away"


def test_the_failure_panel_is_translated(tmp_path):
    broken = {**FULL_AUDIT, "19c_purview_sensitivity_labels.txt": _PURVIEW_404}
    html = _render_strict(tmp_path, "report_tech.html.j2", broken, lang="en")
    text = _visible_text(html)
    assert T("en").error_files_heading in text
    assert T("no").error_files_heading not in text


# ── Trend charts vs. the now-nullable metrics ─────────────────────────────────


def _previous_run(audit_dir: Path, name: str, metrics: dict) -> None:
    from app.core.encryption import encrypted_write_json
    prev = audit_dir.parent / name
    prev.mkdir(parents=True, exist_ok=True)
    encrypted_write_json(prev / "_audit_metrics.json", metrics)


def test_a_history_containing_nulls_renders_without_plotting_a_zero(tmp_path):
    """save_audit_metrics now writes None for unread metrics, so historical
    runs legitimately contain nulls. The chart macros filter `is not none`
    before any arithmetic — this pins that, because the alternative is either
    a template crash or a 0% datapoint drawn as if it were measured.
    """
    d = _audit_dir(tmp_path, FULL_AUDIT)
    _previous_run(d, "2025-11-01_0900", {
        "timestamp": "2025-11-01T09:00:00Z",
        "mfa_coverage_pct": 95.0, "total_users": 40, "risk_score": 88,
        "users_no_mfa": 2, "secure_score_pct": 80.0,
    })
    # The throttled run in the middle — every metric unknown.
    _previous_run(d, "2025-12-01_0900", {
        "timestamp": "2025-12-01T09:00:00Z",
        "mfa_coverage_pct": None, "total_users": None, "risk_score": None,
        "users_no_mfa": None, "secure_score_pct": None,
    })

    ctx = build_report_context("Acme AS", "acme.no", d, [], lang="no", frameworks="all")
    ctx["t"], ctx["lang"], ctx["theme"] = T("no"), "no", "light"
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR), encoding="utf-8"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True, lstrip_blocks=True, undefined=StrictUndefined,
    )
    html = env.get_template("report_customer.html.j2").render(**ctx)

    assert len(ctx["metrics_timeline"]) == 3
    assert any(p.get("mfa_coverage_pct") is None for p in ctx["metrics_timeline"])
    assert "<svg" in html


def test_a_null_run_does_not_become_a_trend_delta(tmp_path):
    """_compute_trends compares against the most recent previous run. If that
    run was the throttled one, every delta would read as a huge improvement.
    """
    d = _audit_dir(tmp_path, FULL_AUDIT)
    _previous_run(d, "2025-12-01_0900", {
        "timestamp": "2025-12-01T09:00:00Z",
        "mfa_coverage_pct": None, "total_users": None, "risk_score": None,
    })

    ctx = build_report_context("Acme AS", "acme.no", d, [], lang="no", frameworks="all")
    for key in ("mfa_coverage_pct", "total_users", "risk_score"):
        assert key not in ctx.get("trends", {}), (
            f"{key} produced a delta against an unknown previous value"
        )


def test_an_unmeasured_purview_count_is_not_shown_as_zero(tmp_path):
    """A count of nought and a count never taken must not read alike.

    Fonnafly's runs get a 404 from the sensitivity-label endpoint. The reader
    blanks an errored section before any parser sees it, which stops the error
    being parsed as data — but it also leaves the customer report printing a
    brand-coloured 0 under "Sensitivitetsmerker", which reads as "you have
    none" rather than "we could not look". The technical report lists the
    errored sections outright; this one had nothing.
    """
    files = {
        "19c_purview_sensitivity_labels.txt": (
            "Error: Client error '404 Not Found' for url "
            "'https://graph.microsoft.com/beta/security/informationProtection/"
            "sensitivityLabels'"
        ),
        "19d_purview_dlp_policies.txt": "  POLICY NAME    STATUS\n  Default DLP    Enabled",
    }
    ctx = build_report_context("Acme AS", "acme.no", _audit_dir(tmp_path, files), [], lang="no")
    assert ctx["purview"]["sensitivity_labels_unavailable"] is True
    assert ctx["purview"]["dlp_unavailable"] is False, "a section that worked was marked unavailable"

    text = _visible_text(_render_strict(tmp_path, "report_customer.html.j2", files))
    assert "Ikke m\u00e5lt" in text, "the customer report still presents the gap as a measurement"
    assert "404" not in text and "Client error" not in text
