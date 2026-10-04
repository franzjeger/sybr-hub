"""The dashboard export is in the language it is asked for.

/export/excel wrote "Customer; Domain; Risk Grade; ..." whatever the reader's
language, and "Ukjent" for a customer without a name. It now takes a
language in the body as /report/csv does, and the overview's Excel button
sends the reader's.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from app.core.encryption import encrypted_write_json
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    _reset_middleware_state,
    _scope_env,
    client,
    login,
)


@pytest.fixture
def metrics(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "audits"
    run = root / "Acme_AS" / "2026-01-01_090000_000000_abcdef012345"
    run.mkdir(parents=True)
    encrypted_write_json(
        run / "_audit_metrics.json",
        {"risk_grade": "B", "risk_score": 71, "mfa_coverage_pct": 92.04},
    )
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: root)
    return root


def _export(client, headers, **kwargs) -> list[list[str]]:
    response = client.post("/api/export/excel", headers=headers, **kwargs)
    assert response.status_code == 200, response.text
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))


async def test_an_english_export_has_english_headers(client, metrics):
    headers = await login("excel-en", customers=(ACME,))

    rows = _export(client, headers, json={"lang": "en"})

    assert rows[0][:4] == ["Customer", "Domain", "Grade", "Security score"]
    assert "MFA coverage %" in rows[0]
    assert rows[1][:3] == ["Acme AS", "acme.example", "B"]


async def test_a_norwegian_export_has_norwegian_headers(client, metrics):
    headers = await login("excel-no", customers=(ACME,))

    rows = _export(client, headers, json={"lang": "no"})

    assert rows[0][:4] == ["Kunde", "Domene", "Karakter", "Sikkerhetsscore"]
    assert "MFA-dekning %" in rows[0]
    assert not [h for h in rows[0] if h in ("Customer", "Risk Grade", "Total Users")]


async def test_no_body_is_norwegian_as_before(client, metrics):
    """A script that posts nothing keeps working."""
    headers = await login("excel-plain", customers=(ACME,))

    assert _export(client, headers)[0][0] == "Kunde"


async def test_an_unknown_language_is_refused(client, metrics):
    headers = await login("excel-de", customers=(ACME,))

    response = client.post("/api/export/excel", headers=headers, json={"lang": "de"})

    assert response.status_code == 422


def test_the_excel_button_sends_the_readers_language():
    source = Path("app/web/static/app-customers.js").read_text(encoding="utf-8")
    call = source[source.index("fetch('/api/export/excel'") :].split("\n", 1)[0]
    assert "lang:" in call and "_lang" in call
