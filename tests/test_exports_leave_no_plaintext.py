"""An export is a download, not a plaintext copy in the audit tree.

Everything under the audit directory is encrypted at rest (AES-256-GCM).
/report/csv also wrote its export into the run folder as plaintext, and
/export/excel wrote every customer's grade, score and MFA coverage into the
audit directory as plaintext, with the server path in an X-File-Path header.
Nothing ever read either copy back.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import job_state as state
from app.core.encryption import encrypted_write_json
from tests.audit_fixture import FULL_AUDIT
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    _reset_middleware_state,
    _scope_env,
    client,
    login,
)


@pytest.fixture
def audit_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "audits"
    run = root / "Acme_AS" / "2026-01-01_0900"
    run.mkdir(parents=True)
    for name, content in FULL_AUDIT.items():
        (run / name).write_text(content, encoding="utf-8")
    encrypted_write_json(run / "_audit_metrics.json", {"risk_grade": "B", "risk_score": 71})
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: root)

    async def selected(user, customer_id, *, require_results=False):
        return state.AuditRunContext(
            owner_user_id=user.id,
            customer_id=customer_id,
            out_dir=run,
            results=[{"name": "Identity", "status": "done"}],
        )

    monkeypatch.setattr("app.web.routes.reports._selected_audit_run", selected)
    return root


def _files(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()}


async def test_the_csv_export_leaves_nothing_in_the_run_folder(client, audit_root):
    headers = await login("csv-tech", customers=(ACME,))
    before = _files(audit_root)

    response = client.post("/api/report/csv", headers=headers, json={"customer_id": ACME})

    assert response.status_code == 200, response.text
    assert response.content.startswith(b"\xef\xbb\xbf")  # the download is still there
    assert _files(audit_root) - before == set(), "a plaintext copy was left in the run folder"


async def test_the_dashboard_export_leaves_nothing_in_the_audit_tree(client, audit_root):
    headers = await login("excel-tech", customers=(ACME,))
    before = _files(audit_root)

    response = client.post("/api/export/excel", headers=headers)

    assert response.status_code == 200, response.text
    assert "Acme AS" in response.content.decode("utf-8-sig")
    assert _files(audit_root) - before == set(), "a plaintext copy was left in the audit tree"
    assert "X-File-Path" not in response.headers, "the server path went back to the browser"
