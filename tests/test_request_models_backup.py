"""Request models on the backup routes.

``/backup/restore`` replaces every data file the hub has, and both routes read
the raw body: a number as ``zip_path`` or ``backup_password`` reached
``.strip()`` and answered 500.
"""

from __future__ import annotations

import pytest

from tests.request_body_fixtures import (  # autouse fixtures apply to this module
    _init_db,
    _reset_middleware_state,
    admin_client,
    assert_refused,
)


@pytest.fixture()
def created(monkeypatch):
    calls: list[tuple] = []

    def _create(dest, password):
        calls.append((dest, password))
        return {"ok": True, "path": "/tmp/backup.zip"}

    monkeypatch.setattr("app.web.routes.backup.create_backup_sync", _create)
    return calls


async def test_a_backup_with_no_body_still_uses_the_defaults(admin_client, created):
    r = admin_client.post("/api/backup/create")

    assert r.status_code == 200, r.text
    assert created == [(None, None)]


async def test_what_the_settings_page_sends_still_creates_a_backup(admin_client, created):
    """createBackup() sends ``{}`` or ``{dest_path}``; the smoke test adds a password."""
    admin_client.post("/api/backup/create", json={})
    admin_client.post(
        "/api/backup/create", json={"dest_path": " /srv/backups ", "backup_password": "pw"}
    )

    assert created == [(None, None), ("/srv/backups", "pw")]


@pytest.mark.parametrize("body", [{"dest_path": 5}, {"backup_password": ["pw"]}, {"dest": "/x"}])
async def test_a_malformed_backup_request_creates_nothing(admin_client, created, body):
    assert_refused(admin_client.post("/api/backup/create", json=body), 422)
    assert created == []


async def test_a_restore_without_a_path_keeps_its_message(admin_client):
    body = assert_refused(admin_client.post("/api/backup/restore", json={}), 400)
    assert body["error"] != "err_no_file_path"


@pytest.mark.parametrize(
    "body", [{"zip_path": 5}, {"zip_path": "/x.zip", "backup_password": 1}, {"path": "/x.zip"}]
)
async def test_a_malformed_restore_is_refused_before_any_file_is_touched(admin_client, body):
    assert_refused(admin_client.post("/api/backup/restore", json=body), 422)
