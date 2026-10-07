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


async def test_the_last_audit_is_the_runs_day_and_time(client, metrics):
    """The run 2026-01-01_090000 read "01:09 2026.01.01": the day as the hour."""
    headers = await login("excel-date", customers=(ACME,))

    rows = _export(client, headers, json={"lang": "en"})

    column = rows[0].index("Last audit (UTC)")
    assert rows[1][column] == "2026-01-01 09:00"


def test_the_excel_button_sends_the_readers_language():
    source = Path("app/web/static/app-customers.js").read_text(encoding="utf-8")
    call = source[source.index("fetch('/api/export/excel'") :].split("\n", 1)[0]
    assert "lang:" in call and "_lang" in call


@pytest.mark.parametrize("lang", ["no", "en"])
async def test_unknown_values_are_empty_and_named_while_measured_zero_stays_zero(
    client, metrics, lang
):
    run = next((metrics / "Acme_AS").iterdir())
    encrypted_write_json(
        run / "_audit_metrics.json",
        {
            "risk_grade": "?",
            "risk_score": None,
            "mfa_coverage_pct": None,
            "secure_score_pct": 0,
            "total_users": 0,
            "users_no_mfa": None,
            "ca_policies_enabled": 0,
            "intune_compliance_pct": None,
            # An absent GA count must be treated the same as an explicit null.
        },
    )
    headers = await login("excel-unmeasured", customers=(ACME,))

    rows = _export(client, headers, json={"lang": lang})

    assert rows[1][2:11] == ["", "", "", "0", "0", "", "0", "", ""]
    label = "Unmeasured values" if lang == "en" else "Ikke målte verdier"
    assert rows[0][-1] == label
    assert rows[1][-1].split(", ") == [rows[0][i] for i in (2, 3, 4, 7, 9, 10)]


async def test_a_customer_without_a_run_has_no_invented_metrics(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path)
    headers = await login("excel-no-run", customers=(ACME,))

    rows = _export(client, headers, json={"lang": "en"})

    assert rows[1][2:11] == [""] * 9
    assert rows[1][-1].split(", ") == rows[0][2:11]
