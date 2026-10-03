"""Request models on the audit router: scope, presets and the pasted sign-in.

``/audit/scope`` wrote whatever object arrived straight into the customer's
encrypted scope file, and the page then read it back as the section list.
"""

from __future__ import annotations

import pytest

from tests.request_body_fixtures import (  # autouse fixtures apply to this module
    _init_db,
    _reset_middleware_state,
    assert_refused,
    tech_client,
    tenant_writer_client,
)


def _activate(client) -> str:
    from app.core.customer import CustomerManager

    cid = CustomerManager.save_customer({"CustomerName": "Customer A", "TenantId": "a"})
    assert client.post("/api/customers/switch", json={"customer_id": cid}).status_code == 200
    return cid


async def test_the_scope_the_spa_sends_is_stored_and_read_back(tech_client):
    _activate(tech_client)

    r = tech_client.post("/api/audit/scope", json={"enabled_sections": ["mfa", "ca"]})

    assert r.status_code == 200, r.text
    assert tech_client.get("/api/audit/scope").json()["scope"] == {
        "enabled_sections": ["mfa", "ca"]
    }


async def test_an_empty_scope_body_still_stores_no_choice(tech_client):
    """The page reads a stored list, even an empty one, as a choice."""
    _activate(tech_client)

    tech_client.post("/api/audit/scope", json={})

    assert tech_client.get("/api/audit/scope").json()["scope"] == {}


@pytest.mark.parametrize(
    "body", [{"enabled_sections": "mfa"}, {"enabled_sections": [1]}, {"sections": []}, ["mfa"]]
)
async def test_a_malformed_scope_is_refused_and_not_stored(tech_client, body):
    _activate(tech_client)
    tech_client.post("/api/audit/scope", json={"enabled_sections": ["mfa"]})

    assert_refused(tech_client.post("/api/audit/scope", json=body), 422)
    assert tech_client.get("/api/audit/scope").json()["scope"] == {"enabled_sections": ["mfa"]}


async def test_a_preset_is_still_saved(tech_client):
    r = tech_client.post("/api/audit/presets", json={"name": " Quick ", "sections": ["mfa"]})

    assert r.status_code == 200, r.text
    presets = {p["name"]: p for p in tech_client.get("/api/audit/presets").json()["presets"]}
    assert presets["Quick"]["sections"] == ["mfa"]


async def test_a_preset_without_a_name_keeps_its_message(tech_client):
    body = assert_refused(tech_client.post("/api/audit/presets", json={"sections": ["mfa"]}), 400)
    assert body["error"] != "err_missing_title"


@pytest.mark.parametrize(
    "body", [{"name": 7}, {"name": "Q", "sections": "mfa"}, {"name": "Q", "builtin": True}]
)
async def test_a_malformed_preset_is_refused(tech_client, body):
    assert_refused(tech_client.post("/api/audit/presets", json=body), 422)


# ── The pasted PKCE redirect ─────────────────────────────────────────────────

# The setup page posts this with no Content-Type, so the browser sends it as
# text/plain. Binding a body model would have refused it.
_PLAIN = {"Content-Type": "text/plain;charset=UTF-8"}


async def test_the_pasted_redirect_is_still_read_without_a_json_content_type(
    tenant_writer_client, monkeypatch
):
    seen = []

    async def _exchange(code, state, redirect_uri):
        seen.append((code, state))
        raise RuntimeError("stop here")

    monkeypatch.setattr("app.modules.m365_audit.pkce.exchange_code_for_token", _exchange)

    tenant_writer_client.post(
        "/api/setup/pkce/callback-manual",
        content=b'{"code": "the-code", "state": "the-state"}',
        headers=_PLAIN,
    )

    assert seen == [("the-code", "the-state")]


async def test_a_pasted_redirect_without_code_keeps_its_answer(tenant_writer_client):
    r = tenant_writer_client.post(
        "/api/setup/pkce/callback-manual",
        content=b'{"state": "s"}',
        headers={**_PLAIN, "Accept-Language": "en"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "Missing code or state"
    assert r.json()["error_key"] == "err_setup_code_state_required"


@pytest.mark.parametrize(
    "raw", [b'{"code": 1, "state": "s"}', b'{"code": "c", "state": "s", "x": 1}', b"not json"]
)
async def test_a_malformed_pasted_redirect_is_a_422(tenant_writer_client, raw):
    assert_refused(
        tenant_writer_client.post("/api/setup/pkce/callback-manual", content=raw, headers=_PLAIN),
        422,
    )


# ── Audit history ────────────────────────────────────────────────────────────


async def test_history_deletes_keep_their_messages(tech_client):
    for path, body in (
        ("/api/history/delete", {"paths": []}),
        ("/api/history/delete-customer", {"customer_dir": ""}),
    ):
        assert_refused(tech_client.post(path, json=body), 400)


async def test_deleting_runs_outside_the_audit_dir_is_still_reported_per_path(tech_client):
    """What deleteSelectedRuns() sends; the handler still judges each path itself."""
    r = tech_client.post("/api/history/delete", json={"paths": ["/etc"]})

    assert r.status_code == 200, r.text
    assert not r.json()["deleted"]
    assert r.json()["errors"]


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/history/load", {"path": 5}),
        ("/api/history/load", {"run": "/x"}),
        ("/api/history/delete", {"paths": "/x"}),
        ("/api/history/delete", {"paths": [1]}),
        ("/api/history/delete-customer", {"customer_dir": ["Customer_A"]}),
        ("/api/history/delete-customer", {"customer": "Customer_A"}),
    ],
)
async def test_a_malformed_history_request_deletes_nothing(tech_client, path, body):
    assert_refused(tech_client.post(path, json=body), 422)
