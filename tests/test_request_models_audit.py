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
    """Register Customer A; the scope routes name it in their query."""
    from app.core.customer import CustomerManager

    return CustomerManager.save_customer({"CustomerName": "Customer A", "TenantId": "a"})


SCOPE = "/api/audit/scope?customer_id=Customer_A"


async def test_the_scope_the_spa_sends_is_stored_and_read_back(tech_client):
    _activate(tech_client)

    r = tech_client.post(SCOPE, json={"enabled_sections": ["mfa", "ca"]})

    assert r.status_code == 200, r.text
    assert tech_client.get(SCOPE).json()["scope"] == {"enabled_sections": ["mfa", "ca"]}


async def test_an_empty_scope_body_still_stores_no_choice(tech_client):
    """The page reads a stored list, even an empty one, as a choice."""
    _activate(tech_client)

    tech_client.post(SCOPE, json={})

    assert tech_client.get(SCOPE).json()["scope"] == {}


@pytest.mark.parametrize(
    "body", [{"enabled_sections": "mfa"}, {"enabled_sections": [1]}, {"sections": []}, ["mfa"]]
)
async def test_a_malformed_scope_is_refused_and_not_stored(tech_client, body):
    _activate(tech_client)
    tech_client.post(SCOPE, json={"enabled_sections": ["mfa"]})

    assert_refused(tech_client.post(SCOPE, json=body), 422)
    assert tech_client.get(SCOPE).json()["scope"] == {"enabled_sections": ["mfa"]}


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

    async def _exchange(code, state, redirect_uri, *, owner_user_id):
        seen.append((code, state))
        raise RuntimeError("stop here")

    monkeypatch.setattr("app.modules.m365_audit.pkce.exchange_code_for_token", _exchange)

    tenant_writer_client.post(
        "/api/setup/pkce/callback-manual",
        content=b'{"code": "the-code", "state": "the-state"}',
        headers=_PLAIN,
    )

    assert seen == [("the-code", "the-state")]


async def test_pkce_connection_error_retains_localised_retry_advice(
    tenant_writer_client, monkeypatch
):
    from app.modules.m365_audit.pkce import PkceSetupError

    async def exchange(*args, **kwargs):
        raise PkceSetupError("err_setup_pkce_connect", 503, restart_required=False)

    monkeypatch.setattr("app.modules.m365_audit.pkce.exchange_code_for_token", exchange)
    r = tenant_writer_client.post(
        "/api/setup/pkce/callback-manual",
        json={"code": "c", "state": "s"},
        headers={"Accept-Language": "en"},
    )
    assert r.status_code == 503
    assert r.json()["restart_required"] is False
    assert "DNS" in r.json()["error"]
    assert "retry Complete Setup" in r.json()["error"]


async def test_pkce_state_is_bound_to_the_signed_in_setup_user(tenant_writer_client):
    from urllib.parse import parse_qs, urlparse

    from app.modules.m365_audit.pkce import _pkce_store

    url = tenant_writer_client.get("/api/setup/pkce/start").json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    try:
        assert _pkce_store[state].owner_user_id
        _pkce_store[state].expires_at = 0
        r = tenant_writer_client.post(
            "/api/setup/pkce/callback-manual",
            json={"code": "c", "state": state},
            headers={"Accept-Language": "en"},
        )
        assert r.status_code == 400
        assert r.json()["restart_required"] is True
        assert "New sign-in" in r.json()["error"]
    finally:
        _pkce_store.pop(state, None)


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


async def test_renewal_callback_passes_the_selected_customer_configuration(
    tenant_writer_client, monkeypatch
):
    from app.core.customer import CustomerManager

    tenant = "11111111-1111-4111-8111-111111111111"
    customer_id = CustomerManager.save_customer(
        {
            "CustomerName": "Customer A",
            "TenantId": tenant,
            "ClientId": "22222222-2222-4222-8222-222222222222",
        }
    )
    seen = []

    async def exchange(*args, **kwargs):
        return "synthetic-token"

    async def provision(token, *, allowed_customer_ids, renew_config):
        seen.append(renew_config)
        return {"TenantId": tenant, "CustomerName": "Customer A"}

    monkeypatch.setattr("app.modules.m365_audit.pkce.exchange_code_for_token", exchange)
    monkeypatch.setattr("app.modules.m365_audit.pkce.create_sybr_app", provision)
    monkeypatch.setattr("app.core.credentials.save_config", lambda _: None)
    response = tenant_writer_client.post(
        "/api/setup/pkce/callback-manual",
        json={
            "code": "synthetic-code",
            "state": "synthetic-state",
            "renew_customer_id": customer_id,
        },
    )
    assert response.status_code == 200
    assert seen[0]["CustomerId"] == customer_id
    assert seen[0]["TenantId"] == tenant


async def test_missing_renewal_customer_is_refused_before_app_provisioning(
    tenant_writer_client, monkeypatch
):
    async def exchange(*args, **kwargs):
        return "synthetic-token"

    async def provision(*args, **kwargs):
        pytest.fail("Missing renewal target must not provision an app")

    monkeypatch.setattr("app.modules.m365_audit.pkce.exchange_code_for_token", exchange)
    monkeypatch.setattr("app.modules.m365_audit.pkce.create_sybr_app", provision)
    response = tenant_writer_client.post(
        "/api/setup/pkce/callback-manual",
        json={"code": "synthetic-code", "state": "synthetic-state", "renew_customer_id": "missing"},
    )
    assert response.status_code == 404
