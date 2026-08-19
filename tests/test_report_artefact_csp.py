"""The generated report is a standalone document, not part of the app UI.

Served under the application CSP, `style-src-elem 'self'` blocked its <style>
elements — and the tech report carries all of its layout in two of them. Every
rule was dropped: headings in the browser default, the KPI strip as a column
of loose numbers, and a search box and tab buttons that did nothing, because
`script-src-elem 'self'` had blocked the <script> as well. The same file
opened from disk looks correct, so it rendered two different ways depending on
who opened it.

The other direction matters more. The report is built from tenant data —
display names, mailbox addresses, policy names — and the viewer puts it in a
same-origin iframe inside the application. Under the app policy that document
can reach the app's DOM.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = (ROOT / "app/web/routes/frontend.py").read_text(encoding="utf-8")
REPORTS = (ROOT / "app/web/routes/reports.py").read_text(encoding="utf-8")
SECURITY = (ROOT / "app/web/middleware/security_headers.py").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "app/reports/templates/report_tech.html.j2").read_text(encoding="utf-8")


def _artefact_csp() -> dict[str, str]:
    # Canonical home is the security-headers module; the report routes import it
    # so a self-contained styled document (audit report, customer summary, batch
    # summary) renders and stays sandboxed regardless of which route emits it.
    m = re.search(r"ARTEFACT_CSP = \(\n(.*?)\n\)", SECURITY, re.S)
    assert m, "the artefact policy is gone"
    raw = "".join(re.findall(r'"([^"]*)"', m.group(1)))
    out: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if part:
            name, _, value = part.partition(" ")
            out[name] = value.strip()
    return out


# ── The report needs its own style and script to render at all ───────────────

def test_the_template_really_does_depend_on_style_elements():
    # The premise. If the report ever inlines its CSS some other way this test
    # should fail rather than quietly guard nothing.
    assert TEMPLATE.count("<style>") >= 1
    assert "<script>" in TEMPLATE


def test_style_elements_are_allowed():
    csp = _artefact_csp()
    assert "unsafe-inline" in csp.get("style-src", ""), (
        "the report's layout lives in <style> elements; blocking them renders "
        "it as unstyled markup"
    )


def test_script_elements_are_allowed():
    assert "unsafe-inline" in _artefact_csp().get("script-src", "")


def test_the_inline_handlers_in_the_report_still_work():
    # The tab buttons carry onclick attributes and the script reads them back.
    assert "onclick" in TEMPLATE
    assert "unsafe-inline" in _artefact_csp().get("script-src-attr", "")


# ── And must not be trusted with anything else ───────────────────────────────

def test_it_is_sandboxed_into_an_opaque_origin():
    sandbox = _artefact_csp().get("sandbox", "")
    assert "allow-scripts" in sandbox
    assert "allow-same-origin" not in sandbox, (
        "the report is built from tenant data and rendered in a same-origin "
        "iframe inside the app; allow-same-origin hands it the app's DOM"
    )


def test_it_has_no_network_at_all():
    csp = _artefact_csp()
    assert csp.get("default-src") == "'none'"
    for directive in ("img-src", "font-src"):
        assert "http" not in csp.get(directive, ""), (
            f"{directive} reaches the network; a confidential report should "
            f"not announce to a third party that it was opened"
        )


def test_the_font_import_stays_blocked():
    # The stylesheet @imports Google Fonts. Left reachable, opening a
    # confidential audit tells Google who and when — including for the copy
    # sent to the customer.
    assert "fonts.googleapis.com" in TEMPLATE, "premise changed"
    assert "googleapis" not in " ".join(_artefact_csp().values())


def test_forms_and_base_uri_are_closed():
    csp = _artefact_csp()
    assert csp.get("form-action") == "'none'"
    assert csp.get("base-uri") == "'none'"


# ── Only the HTML artefacts get it ───────────────────────────────────────────

def test_the_policy_is_applied_to_html_responses():
    assert 'if content_type == "text/html":' in FRONTEND
    assert 'headers["Content-Security-Policy"] = ARTEFACT_CSP' in FRONTEND


def test_the_self_built_summary_reports_also_get_it():
    """The customer summary and batch summary build their own styled HTML and
    are served straight from /api, not from serve_audit_data. They carried no
    CSP of their own, so the application policy blocked their <style> block and
    they rendered as unstyled markup — the exact bug this file exists for, one
    layer over. They must import and apply the same artefact policy."""
    assert "from app.web.middleware.security_headers import ARTEFACT_CSP" in REPORTS
    # Both text/html report responses set the artefact policy in their headers.
    assert REPORTS.count('"Content-Security-Policy": ARTEFACT_CSP') >= 2


def test_other_artefacts_keep_the_default():
    # PDFs and raw collector output are served by the same route. Leaving the
    # header unset lets the middleware apply the app policy exactly as before,
    # so this change cannot alter how a PDF renders.
    body = FRONTEND[FRONTEND.index("async def serve_audit_data"):]
    body = body[:body.index("\n@router.get")]
    assert "headers: dict[str, str] = {}" in body


def test_the_route_still_checks_who_is_asking():
    # The policy change must not distract from the guard that stops one
    # customer's reports being served to another.
    assert "require_audit_path_access()" in FRONTEND


@pytest.mark.parametrize("directive", ["default-src", "sandbox", "frame-ancestors"])
def test_the_policy_is_wellformed(directive):
    assert directive in _artefact_csp()
