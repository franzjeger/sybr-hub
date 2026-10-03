"""PDF rendering never runs on the event loop.

WeasyPrint spends seconds on a long document. Called straight from an async
route it stalls every other request for that long, health checks and audit
streams included. The audit reports already render in an executor; these are
the two routes that did not.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.database import run_migrations
from app.core.rbac import set_can_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


@pytest.fixture
async def admin(tmp_path):
    import app.core.database as database_module

    _reset_users_exist_cache()
    database_module.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    user = await create_user("pdf-admin", "Str0ng-Passphrase-For-Pdf!", "Admin", role=Role.admin)
    await set_can_write(user.id, True)
    token = await create_access_token(await get_user_by_id(user.id))
    yield {"Authorization": f"Bearer {token}"}
    _reset_users_exist_cache()


async def test_the_renewal_report_renders_off_the_loop(admin, monkeypatch):
    seen: list[bool] = []

    class FakeHTML:
        def __init__(self, string: str):
            pass

        def write_pdf(self) -> bytes:
            seen.append(_on_event_loop())
            return b"%PDF-1.7"

    monkeypatch.setattr("weasyprint.HTML", FakeHTML)
    with TestClient(create_app()) as client:
        r = client.get("/api/also/renewals/report", headers=admin)
    assert r.status_code == 200 and r.content == b"%PDF-1.7"
    assert seen == [False]


async def test_the_pentest_report_renders_off_the_loop(admin, monkeypatch):
    calls: list[tuple[bool, str]] = []

    def fake_pdf(target, findings, summary, out_path, **_):
        calls.append((_on_event_loop(), out_path.name))
        return {"ok": True}

    monkeypatch.setattr("app.modules.pentest.report.generate_pdf_report", fake_pdf)
    body = {
        "target": "../etc/acme.example",
        "findings": [{"title": "x", "severity": "low"}],
        "format": "pdf",
    }
    with TestClient(create_app()) as client:
        r = client.post("/api/pentest/report", headers=admin, json=body)
    assert r.status_code == 200, r.text
    [(on_loop, name)] = calls
    assert on_loop is False
    # The target names the file, so nothing in it may act as a path.
    assert "/" not in name and ".." not in name and name.startswith("pentest____etc_acme_example_")
