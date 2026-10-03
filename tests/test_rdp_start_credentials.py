"""/rdp/start sends a host's stored password only for the stored account.

The caller may type a different username to sign in as someone else on that
host. The stored password belongs to the stored account, so it must not be
sent along with whatever username the caller typed.
"""

from __future__ import annotations

import pytest

from app.web.routes import proxy
from tests.test_rdp_launch import (  # autouse fixtures apply to this module
    _init_db,
    _reset_state,
    _setup,
    client,
)


@pytest.fixture()
def guacamole(monkeypatch):
    sent: list[tuple[str, str]] = []

    async def login():
        return "guac-token"

    async def create(token, host, port, username, password):
        sent.append((username, password))
        return {"identifier": "c1"}

    async def no_pending():
        return None

    monkeypatch.setattr(proxy, "_guac_login", login)
    monkeypatch.setattr(proxy, "_guac_create_connection", create)
    monkeypatch.setattr(proxy, "_retry_pending_guacamole_cleanup", no_pending)
    proxy._guac_sessions.clear()
    yield sent
    proxy._guac_sessions.clear()


async def test_the_stored_account_gets_the_stored_password(client, guacamole):
    hdr, host_id = await _setup(client)
    assert client.post("/api/rdp/start", headers=hdr, json={"host_id": host_id}).status_code == 200
    assert guacamole == [("Administrator", "rdp-secret")]


async def test_another_username_does_not_get_the_stored_password(client, guacamole):
    hdr, host_id = await _setup(client)
    resp = client.post("/api/rdp/start", headers=hdr, json={"host_id": host_id, "username": "bob"})
    assert resp.status_code == 200, resp.text
    assert guacamole == [("bob", "")]


# ── The request bodies of the remote-session routes ──────────────────────────


async def test_what_the_rdp_form_sends_still_starts_a_session(client, guacamole):
    """rdpStart() sends every field, empty ones as empty strings."""
    hdr, host_id = await _setup(client)

    resp = client.post(
        "/api/rdp/start",
        headers=hdr,
        json={"host_id": host_id, "port": 3389, "username": "", "password": ""},
    )

    assert resp.status_code == 200, resp.text
    assert guacamole == [("Administrator", "rdp-secret")]


@pytest.mark.parametrize(
    "over", [{"port": "rdp"}, {"host_id": 5}, {"password": ["x"]}, {"hostname": "evil.example"}]
)
async def test_a_malformed_rdp_start_reaches_no_guacamole(client, guacamole, over):
    hdr, host_id = await _setup(client)

    resp = client.post("/api/rdp/start", headers=hdr, json={"host_id": host_id, **over})

    assert resp.status_code == 422, resp.text
    assert guacamole == []


async def test_an_out_of_range_rdp_port_keeps_its_message(client, guacamole):
    hdr, host_id = await _setup(client)

    resp = client.post("/api/rdp/start", headers=hdr, json={"host_id": host_id, "port": 70000})

    assert resp.status_code == 400
    assert resp.json()["error"] == "Ugyldig RDP-port"


async def test_clipboard_and_browser_bodies_are_typed(client, guacamole):
    hdr, _host_id = await _setup(client)

    # Valid bodies get the handlers' own answers: no session is running.
    assert client.post("/api/rdp/clipboard", headers=hdr, json={"text": "x"}).json() == {
        "ok": False,
        "error": "Ingen aktiv RDP-sesjon",
        "error_key": "err_rdp_no_session",
    }
    nav = client.post("/api/browser/navigate", headers=hdr, json={"url": "https://example.no"})
    assert nav.status_code == 400, nav.text

    for path, body in (
        ("/api/rdp/clipboard", {"text": 5}),
        ("/api/rdp/clipboard", {"clipboard": "x"}),
        ("/api/browser/navigate", {"url": ["https://example.no"]}),
        ("/api/browser/start", {"url": 5}),
        ("/api/browser/start", {"target": "https://example.no"}),
    ):
        resp = client.post(path, headers=hdr, json=body)
        assert resp.status_code == 422, (path, resp.text)
