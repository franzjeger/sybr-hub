"""Request models on the integration routers (GDAP, IT Glue, ALSO, Uniweb, …).

Each case is one of three: what the SPA sends still reaches the handler (often
shown by the handler's own 400 for a missing value, which only a body that
parsed can produce), a value of the wrong type is a 422 rather than a 500, and
an unknown key is refused.
"""

from __future__ import annotations

import pytest

from tests.request_body_fixtures import (  # autouse fixtures apply to this module
    _init_db,
    _reset_middleware_state,
    admin_client,
    assert_refused,
    tech_client,
)

# ── GDAP ─────────────────────────────────────────────────────────────────────


async def test_gdap_setup_keeps_its_required_field_message(admin_client):
    """gdapSaveConfig() sends the three fields; empty ones reach the handler."""
    body = assert_refused(
        admin_client.post(
            "/api/gdap/setup", json={"partner_tenant_id": "", "client_id": "", "client_secret": ""}
        ),
        400,
    )
    assert "partner_tenant_id" in body["error"]


@pytest.mark.parametrize(
    "body", [{"partner_tenant_id": 5, "client_id": "c"}, {"client_id": ["c"]}, {"tenant": "t"}]
)
async def test_a_malformed_gdap_setup_stores_nothing(admin_client, body):
    from app.core.credentials import get_secret

    assert_refused(admin_client.post("/api/gdap/setup", json=body), 422)
    assert get_secret("gdap", "partner_client_id") is None


async def test_gdap_import_keeps_its_message_and_refuses_a_wrong_type(admin_client):
    body = assert_refused(admin_client.post("/api/gdap/import", json={"tenant_ids": []}), 400)
    assert "tenant_ids" in body["error"]
    for bad in ({"tenant_ids": "t1"}, {"tenant_ids": ["t1"], "links": {"t1": 5}}, {"ids": []}):
        assert_refused(admin_client.post("/api/gdap/import", json=bad), 422)


async def test_gdap_setup_still_saves_when_partner_center_refuses(admin_client, monkeypatch):
    """The path past validation: credentials stored, the refusal recorded.

    It read ``app_display_name`` off the raw body, which a model has no
    ``.get`` for; this is the test that walks that far.
    """
    from app.core.credentials import get_secret, load_gdap_config

    class _Refusing:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            raise RuntimeError("AADSTS7000215: invalid client secret")

        async def __aexit__(self, *_):
            return None

    monkeypatch.setattr("app.integrations.partner_center.PartnerCenterClient", _Refusing)

    r = admin_client.post(
        "/api/gdap/setup",
        json={"partner_tenant_id": "t-1", "client_id": "c-1", "client_secret": "s-1"},
    )

    assert r.status_code == 200, r.text
    assert r.json()["validated"] is False
    assert get_secret("gdap", "partner_client_id") == "c-1"
    assert load_gdap_config()["app_display_name"] == "MSP Toolkit GDAP"


# ── IT Glue ──────────────────────────────────────────────────────────────────


async def test_itglue_test_without_a_key_still_falls_back_to_settings(admin_client):
    r = admin_client.post("/api/itglue/test", json={"api_key": "", "region": "eu"})

    assert r.status_code == 200, r.text
    assert r.json()["ok"] is False


async def test_a_connection_test_needs_an_admin(tech_client):
    """It runs with the stored credentials, which only an admin may configure."""
    for path in ("/api/itglue/test", "/api/autotask/test", "/api/myitprocess/test"):
        assert tech_client.post(path, json={}).status_code == 403, path


async def test_a_malformed_itglue_test_is_refused(admin_client):
    for body in ({"api_key": 5}, {"region": ["eu"]}, {"key": "k"}):
        assert_refused(admin_client.post("/api/itglue/test", json=body), 422)


async def test_importing_itglue_organisations_still_creates_customers(tech_client):
    """runITGlueImport() sends ``{organizations: [{name, id}]}``."""
    from app.core.customer import CustomerManager

    r = tech_client.post(
        "/api/customers/import-itglue",
        json={"organizations": [{"name": "Customer B", "id": 77}]},
    )

    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1
    [stored] = [c for c in CustomerManager.list_customers() if c["CustomerName"] == "Customer B"]
    assert stored["ITGlueOrgId"] == "77"


async def test_a_malformed_itglue_import_creates_nothing(tech_client):
    from app.core.customer import CustomerManager

    body = assert_refused(
        tech_client.post("/api/customers/import-itglue", json={"organizations": []}), 400
    )
    assert body["error"] != "err_no_orgs_selected"
    for bad in (
        {"organizations": [{"name": 5, "id": 1}]},
        {"organizations": [{"name": "C", "id": 1, "tenant": "x"}]},
        {"organizations": "Customer C"},
    ):
        assert_refused(tech_client.post("/api/customers/import-itglue", json=bad), 422)
    assert CustomerManager.list_customers() == []


async def test_itglue_uploads_keep_their_message_and_refuse_a_wrong_type(tech_client, admin_client):
    body = assert_refused(tech_client.post("/api/itglue/upload/audit", json={}), 400)
    assert body["error"] == "org_id er påkrevd"
    for client, path, bad in (
        (tech_client, "/api/itglue/upload/audit", {"org_id": ["501"]}),
        (tech_client, "/api/itglue/upload/reports", {"org_id": "501", "files": "a.pdf"}),
        (tech_client, "/api/itglue/upload/reports", {"org": "501"}),
        (admin_client, "/api/itglue/upload/credentials", {"org_id": {"id": 1}}),
    ):
        assert_refused(client.post(path, json=bad), 422)


# ── ALSO Cloud Marketplace ───────────────────────────────────────────────────


async def test_also_test_keeps_its_message_and_refuses_a_wrong_type(tech_client):
    body = assert_refused(
        tech_client.post("/api/also/test", json={"username": "", "password": "", "country": "no"}),
        400,
    )
    assert "påkrevd" in body["error"]
    for bad in ({"username": 5}, {"password": ["x"]}, {"user": "x"}):
        assert_refused(tech_client.post("/api/also/test", json=bad), 422)


async def test_the_scan_buttons_still_scan_and_a_bad_batch_is_refused(admin_client):
    """Both scan buttons send ``{batch_size: 25, delay: 1.5}``."""
    r = admin_client.post("/api/also/renewal-scan", json={"batch_size": 25, "delay": 1.5})
    assert r.status_code == 200, r.text
    assert r.json()["scanned"] == 0
    # The body stays optional.
    assert admin_client.post("/api/also/renewal-scan").status_code == 200

    for path in ("/api/also/renewal-scan", "/api/also/price-scan"):
        for bad in ({"batch_size": "lots"}, {"delay": [1]}, {"batchsize": 5}):
            assert_refused(admin_client.post(path, json=bad), 422)


async def test_marking_a_renewal_refuses_a_wrong_type_before_looking_it_up(tech_client):
    assert_refused(tech_client.post("/api/also/renewals/99999/handle", json={"handled": 1}), 404)
    for bad in ({"handled": "yes"}, {"notes": 5}, {"note": "x"}):
        assert_refused(tech_client.post("/api/also/renewals/99999/handle", json=bad), 422)


async def test_also_linking_and_import_keep_their_messages(admin_client):
    assert_refused(admin_client.post("/api/also/link-matched", json={"matches": []}), 400)
    assert_refused(admin_client.post("/api/also/sync-customers", json={"customers": []}), 400)
    for path, bad in (
        ("/api/also/link-matched", {"matches": [{"toolkit_id": 1, "also_id": 2}]}),
        ("/api/also/link-matched", {"matches": [{"toolkit": "a", "also_id": 2}]}),
        ("/api/also/sync-customers", {"customers": [{"name": None}]}),
        ("/api/also/sync-customers", {"customers": "Customer D"}),
    ):
        assert_refused(admin_client.post(path, json=bad), 422)


async def test_also_import_still_creates_customers(admin_client):
    """alsoDoImport() sends name, domain and also_id from data attributes."""
    from app.core.customer import CustomerManager

    r = admin_client.post(
        "/api/also/sync-customers",
        json={"customers": [{"name": "Customer D", "domain": "d.example", "also_id": "991"}]},
    )

    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1
    [stored] = CustomerManager.list_customers()
    assert stored["AlsoAccountId"] == "991"


# ── Uniweb ───────────────────────────────────────────────────────────────────


async def test_uniweb_settings_still_save_and_keep_the_masked_password(admin_client):
    from app.core.config import load_app_settings

    r = admin_client.post(
        "/api/uniweb/settings", json={"email": "ops@example.no", "password": "secret"}
    )
    assert r.status_code == 200, r.text
    admin_client.post(
        "/api/uniweb/settings", json={"email": "ops@example.no", "password": "••••••"}
    )

    assert load_app_settings()["uniweb_password"] == "secret"


async def test_uniweb_routes_keep_their_messages(tech_client, admin_client):
    for client, path, body in (
        (tech_client, "/api/uniweb/match", {"uniweb_account_id": "", "customer_id": "c"}),
        (tech_client, "/api/uniweb/import-customers", {"account_ids": []}),
        (admin_client, "/api/uniweb/settings", {"email": "", "password": ""}),
    ):
        assert_refused(client.post(path, json=body), 400)


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/uniweb/match", {"uniweb_account_id": 5}),
        ("/api/uniweb/match", {"account_id": "a1"}),
        ("/api/uniweb/import-customers", {"account_ids": "a1"}),
        ("/api/uniweb/settings", {"email": ["ops@example.no"], "password": "x"}),
        ("/api/uniweb/settings", {"username": "ops", "password": "x"}),
    ],
)
async def test_a_malformed_uniweb_request_is_a_422(admin_client, path, body):
    assert_refused(admin_client.post(path, json=body), 422)


# ── PSA connection tests ─────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/api/autotask/test", "/api/myitprocess/test"])
async def test_a_psa_test_with_no_body_or_an_empty_one_uses_the_stored_settings(admin_client, path):
    """The cards save first and then post ``{}``; nothing is stored here."""
    for kwargs in ({}, {"json": {}}):
        r = admin_client.post(path, **kwargs)
        assert r.status_code == 400, r.text
        assert "konfigurert" in r.json()["error"]


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/autotask/test", {"integration_code": 5, "username": "u", "secret": "s"}),
        ("/api/autotask/test", {"code": "c"}),
        ("/api/myitprocess/test", {"api_key": ["k"]}),
        ("/api/myitprocess/test", {"key": "k"}),
    ],
)
async def test_a_malformed_psa_test_is_a_422(admin_client, path, body):
    assert_refused(admin_client.post(path, json=body), 422)
