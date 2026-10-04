"""What the score could not measure stands beside the score.

``_compute_risk`` collects every input it could not read into
``data_quality_issues``, and its own comments say that list "must be visible
beside the score". Nothing rendered it. A tenant whose Secure Score could not
be read scored 20 points better than its measured peers, with nothing on the
page to say a fifth of the score was not in it.

Both templates now list the gaps under the score, in the report's language,
and show nothing when there are none. When there is no score at all, the
blocking gaps say why instead, and the tech report, which showed a bare "?",
now says it too.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.reports.generator import _jinja_env, build_report_context
from app.reports.i18n import T
from tests.audit_fixture import FULL_AUDIT

TEMPLATES = ("report_customer.html.j2", "report_tech.html.j2")


def _render(tmp_path: Path, files: dict[str, str], lang: str) -> tuple[dict, dict[str, str]]:
    run = tmp_path / "Acme_AS" / "2026-01-01_0900"
    run.mkdir(parents=True)
    for name, content in files.items():
        (run / name).write_text(content, encoding="utf-8")
    ctx = build_report_context("Acme AS", "acme.example", run, [], lang=lang, persist_metrics=False)
    ctx["t"], ctx["lang"], ctx["theme"] = T(lang), lang, "light"
    env = _jinja_env()
    return ctx, {name: env.get_template(name).render(**ctx) for name in TEMPLATES}


def _gaps_block(page: str) -> str | None:
    m = re.search(r'id="score-gaps">(.*?)</div>', page, re.S)
    return m.group(1) if m else None


def _without_secure_score() -> dict[str, str]:
    return {k: v for k, v in FULL_AUDIT.items() if not k.startswith("09_secure_score")}


@pytest.mark.parametrize("lang", ["no", "en"])
def test_the_gaps_are_listed_under_the_score(tmp_path, lang):
    ctx, pages = _render(tmp_path, _without_secure_score(), lang)
    assert ctx["risk"]["score"] is not None
    issue = T(lang).risk_dq_secure_score
    assert ctx["risk"]["data_quality_issues"] == [issue]
    for template, page in pages.items():
        block = _gaps_block(page)
        assert block is not None, f"{template} has no gap list"
        assert T(lang).risk_not_in_score_label in block
        assert f"<li>{issue}</li>" in block


def test_the_list_is_in_the_reports_language(tmp_path):
    _, pages = _render(tmp_path, _without_secure_score(), "en")
    for page in pages.values():
        block = _gaps_block(page)
        assert "Microsoft Secure Score unavailable" in block
        assert "utilgjengelig" not in block


@pytest.mark.parametrize("lang", ["no", "en"])
def test_nothing_is_shown_when_the_score_measured_everything(tmp_path, lang):
    ctx, pages = _render(tmp_path, FULL_AUDIT, lang)
    assert ctx["risk"]["data_quality_issues"] == []
    for template, page in pages.items():
        assert _gaps_block(page) is None, template
        assert T(lang).risk_not_in_score_label not in page, template


def test_without_a_score_the_blocking_gaps_say_why_in_both_reports(tmp_path):
    files = {name: "Error: 403 Forbidden\n" for name in FULL_AUDIT}
    ctx, pages = _render(tmp_path, files, "no")
    assert ctx["risk"]["score"] is None
    for template, page in pages.items():
        # The gaps of a score that does not exist are not listed as left out of it.
        assert _gaps_block(page) is None, template
        assert T("no").posture_blocking_gaps_label in page, template
        assert ctx["risk"]["blocking_data_gaps"][0] in page, template
