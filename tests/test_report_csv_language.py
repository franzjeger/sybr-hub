"""The CSV export is in the language it is asked for, and says what it did not measure.

/report/csv wrote "Kategori; Metrikk; Verdi; Status", "Kritisk" and "av 100"
whatever language the report screen was set to, and its recommendations came
out of a Norwegian report context. It now takes the screen's language in the
body, as /report/generate does.

It also wrote a section the audit could not read as a measured zero: a tenant
whose user list was refused exported "MFA; Dekning %; 0". That cell is now
empty, with "not measured" beside it.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from app.core import job_state as state
from app.reports.generator import build_report_context
from app.web.routes.reports import _csv_rows
from tests.audit_fixture import BROKEN_AUDIT, FULL_AUDIT
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    _reset_middleware_state,
    _scope_env,
    client,
    login,
)
from tests.test_english_reports import _norwegian


def _run(tmp_path: Path, files: dict[str, str]) -> Path:
    run = tmp_path / "Acme_AS" / "2026-01-01_0900"
    run.mkdir(parents=True)
    for name, content in files.items():
        (run / name).write_text(content, encoding="utf-8")
    return run


def _rows(tmp_path: Path, files: dict[str, str], lang: str) -> list[list]:
    run = _run(tmp_path, files)
    ctx = build_report_context("Acme AS", "acme.example", run, [], lang=lang, persist_metrics=False)
    return _csv_rows(ctx, "Acme AS", lang)


def _fixed_words(rows: list[list]) -> list[str]:
    """Every cell the export writes itself: not the tenant's name, values or warnings."""
    cells = [rows[0], *([r[0], r[1], r[3]] for r in rows[1:] if r[0] not in ("Varsel", "Warning"))]
    return [str(c) for row in cells for c in row if isinstance(c, str)]


def test_an_english_export_is_english(tmp_path):
    rows = _rows(tmp_path, BROKEN_AUDIT, "en")
    assert rows[0] == ["Category", "Metric", "Value", "Status"]
    words = _fixed_words(rows)
    assert not [w for w in words if _norwegian(w)], [w for w in words if _norwegian(w)]
    assert "Critical" in {r[3] for r in rows}  # users without MFA
    recs = [r for r in rows if r[0] == "Recommendation"]
    assert recs and all(r[2] in ("Critical", "High", "Medium", "Low") for r in recs)
    assert not [r for r in recs if _norwegian(r[1])]


def test_a_norwegian_export_is_norwegian(tmp_path):
    rows = _rows(tmp_path, BROKEN_AUDIT, "no")
    assert rows[0] == ["Kategori", "Metrikk", "Verdi", "Status"]
    recs = [r for r in rows if r[0] == "Anbefaling"]
    assert recs and all(r[2] in ("Kritisk", "Høy", "Middels", "Lav") for r in recs)
    score = next(r for r in rows if r[1] == "Sikkerhetsscore")
    assert score[0] == "Sikkerhet" and score[3] == "av 100"


@pytest.mark.parametrize(("lang", "not_measured"), [("no", "ikke målt"), ("en", "not measured")])
def test_what_was_not_measured_is_not_written_as_zero(tmp_path, lang, not_measured):
    files = {name: "Error: 403 Forbidden\n" for name in FULL_AUDIT}
    rows = _rows(tmp_path, files, lang)
    by_metric = {(r[0], r[1]): r for r in rows}
    coverage = [r for key, r in by_metric.items() if key[0] == "MFA"]
    assert coverage and all(r[2:] == ["", not_measured] for r in coverage)
    score = next(r for r in rows if r[1] in ("Sikkerhetsscore", "Security score"))
    assert score[2:] == ["", not_measured]  # no grade, so no "None of 100"


def test_a_measured_tenant_has_its_values(tmp_path):
    rows = _rows(tmp_path, FULL_AUDIT, "en")
    coverage = next(r for r in rows if r[:2] == ["MFA", "Coverage %"])
    assert isinstance(coverage[2], int | float) and coverage[3] == ""


# ── Through the route ────────────────────────────────────────────────────────


def _select(monkeypatch, run: Path) -> None:
    async def selected(user, customer_id, *, require_results=False):
        return state.AuditRunContext(
            owner_user_id=user.id,
            customer_id=customer_id,
            out_dir=run,
            results=[{"name": "Identity", "status": "done"}],
        )

    monkeypatch.setattr("app.web.routes.reports._selected_audit_run", selected)


def _download(client, headers, body) -> list[list[str]]:
    response = client.post("/api/report/csv", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))


async def test_the_route_answers_in_the_language_the_body_asks_for(client, tmp_path, monkeypatch):
    _select(monkeypatch, _run(tmp_path, BROKEN_AUDIT))
    headers = await login("csv-tech", customers=(ACME,))

    english = _download(client, headers, {"customer_id": ACME, "lang": "en"})
    assert english[0] == ["Category", "Metric", "Value", "Status"]
    assert any(r[0] == "Recommendation" for r in english)

    norwegian = _download(client, headers, {"customer_id": ACME})
    assert norwegian[0] == ["Kategori", "Metrikk", "Verdi", "Status"]

    refused = client.post(
        "/api/report/csv", headers=headers, json={"customer_id": ACME, "lang": "de"}
    )
    assert refused.status_code == 422
