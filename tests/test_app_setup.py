"""Manual onboarding must grant Exchange access and wait for real token roles."""

import asyncio
import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.modules.m365_audit import app_setup as setup
from app.modules.m365_audit.pkce import PkceSetupError

TENANT = "11111111-1111-4111-8111-111111111111"
APP_ID = "22222222-2222-4222-8222-222222222222"
OBJECT_ID = "33333333-3333-4333-8333-333333333333"
PRINCIPAL = "44444444-4444-4444-8444-444444444444"


def _token(roles, wids=()):
    payload = (
        base64.urlsafe_b64encode(json.dumps({"roles": roles, "wids": wids}).encode())
        .decode()
        .rstrip("=")
    )
    return f"e30.{payload}.synthetic"


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "DATA_DIR", tmp_path)
    monkeypatch.setattr(setup, "_setup_lock", asyncio.Lock())
    monkeypatch.setattr(setup, "_certificate_assertion", lambda *args: "synthetic-assertion")
    monkeypatch.setattr("app.core.credentials.load_global_config", lambda: None)
    monkeypatch.setattr("app.core.customer.CustomerManager.list_customers", lambda: [])
    monkeypatch.setattr("app.core.credentials.global_cert_path", lambda: tmp_path / "staging.pfx")
    monkeypatch.setattr(
        "app.modules.m365_audit.setup._generate_cert",
        lambda: (
            "public-key",
            "2030-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
            b"synthetic-pfx",
            "cert-password",
        ),
    )
    calls = []
    behavior = {
        "denied": "",
        "existing": False,
        "ready": True,
        "directory_roles": set(),
        "hidden_directory_roles": set(),
        "app_creations": 0,
        "token_rounds": 0,
        "grant_ids": set(),
        "keys": [],
    }

    def handler(request):
        path = request.url.path.removeprefix("/v1.0")
        body = (
            json.loads(request.content)
            if request.content and request.headers.get("content-type") == "application/json"
            else {}
        )
        calls.append((request.method, path, body))
        if behavior["denied"] and path.endswith(behavior["denied"]) and request.method == "POST":
            return httpx.Response(
                403, json={"error": {"message": "synthetic-secret-never-display"}}
            )
        if path.endswith("/oauth2/v2.0/token"):
            data = parse_qs(request.content.decode())
            scope = data["scope"][0]
            if scope == setup.RESOURCES[0][3]:
                assert data["client_secret"] == ["client-secret"]
            else:
                assert "client_secret" not in data
                assert data["client_assertion"] == ["synthetic-assertion"]
            if scope == setup.RESOURCES[0][3]:
                behavior["token_rounds"] += 1
            resource = next(r for r in setup.RESOURCES if r[3] == scope)
            roles = resource[2] if behavior["ready"] else []
            wids = sorted(behavior["directory_roles"] - behavior["hidden_directory_roles"])
            return httpx.Response(200, json={"access_token": _token(roles, wids)})
        if path == "/organization":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": TENANT,
                            "displayName": "Customer A",
                            "verifiedDomains": [
                                {"name": "customer.example", "isDefault": True},
                                {"name": "customer.onmicrosoft.com", "isInitial": True},
                            ],
                        }
                    ]
                },
            )
        if path == "/servicePrincipals" and request.method == "GET":
            app_id = request.url.params["$filter"].split("'")[1]
            if app_id == APP_ID:
                rows = [{"id": PRINCIPAL}] if behavior["existing"] else []
            else:
                resource = next(r for r in setup.RESOURCES if r[0] == app_id)
                rows = [
                    {
                        "id": app_id,
                        "appRoles": [
                            {
                                "id": f"role-{role}",
                                "value": role,
                                "isEnabled": True,
                                "allowedMemberTypes": ["Application"],
                            }
                            for role in resource[2]
                        ],
                    }
                ]
            return httpx.Response(200, json={"value": rows})
        if path == "/servicePrincipals" and request.method == "POST":
            behavior["existing"] = True
            return httpx.Response(201, json={"id": PRINCIPAL})
        if path == "/applications" and request.method == "POST":
            behavior["app_creations"] += 1
            return httpx.Response(201, json={"id": OBJECT_ID, "appId": APP_ID})
        if path.startswith("/applications") and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": OBJECT_ID,
                    "appId": APP_ID,
                    "keyCredentials": behavior["keys"]
                    if request.url.params.get("$select") == "keyCredentials"
                    else [],
                    "requiredResourceAccess": [
                        {
                            "resourceAppId": "other-resource",
                            "resourceAccess": [{"id": "other-permission", "type": "Scope"}],
                        }
                    ],
                },
            )
        if path.startswith("/applications") and request.method == "PATCH":
            return httpx.Response(204)
        if path.endswith("/addPassword"):
            return httpx.Response(
                200, json={"secretText": "client-secret", "endDateTime": "2030-01-01T00:00:00Z"}
            )
        if path.endswith("/appRoleAssignments"):
            if request.method == "POST":
                behavior["grant_ids"].add((body["resourceId"], body["appRoleId"]))
                return httpx.Response(201, json={})
            return httpx.Response(
                200,
                json={
                    "value": [{"resourceId": r, "appRoleId": a} for r, a in behavior["grant_ids"]]
                },
            )
        if path.endswith("/roleDefinitions"):
            return httpx.Response(
                200, json={"value": [{"id": request.url.params["$filter"].split("'")[1]}]}
            )
        if path.endswith("/roleAssignments"):
            if request.method == "POST":
                behavior["directory_roles"].add(body["roleDefinitionId"])
                return httpx.Response(201, json={})
            return httpx.Response(
                200,
                json={
                    "value": [
                        {"roleDefinitionId": role, "directoryScopeId": "/"}
                        for role in behavior["directory_roles"]
                    ]
                },
            )
        pytest.fail(f"Unexpected request: {request.method} {path}")

    real = httpx.AsyncClient
    monkeypatch.setattr(
        setup.httpx,
        "AsyncClient",
        lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs),
    )
    return behavior, calls, tmp_path


async def test_setup_grants_graph_exchange_purview_and_directory_role(api):
    behavior, calls, _ = api
    config = await setup.provision_app("delegated-token")
    manifest = next(
        body["requiredResourceAccess"]
        for method, path, body in calls
        if method == "POST" and path == "/applications"
    )
    assert {r["resourceAppId"] for r in manifest} == {r[0] for r in setup.RESOURCES}
    assert (setup.EXO_APP_ID, "role-Exchange.ManageAsApp") in behavior["grant_ids"]
    assert (setup.EOP_APP_ID, "role-Exchange.ManageAsApp") in behavior["grant_ids"]
    assert any(
        body.get("directoryScopeId") == "/" and body.get("principalId") == PRINCIPAL
        for _, _, body in calls
    )
    assert behavior["directory_roles"] == {
        setup.EXCHANGE_ADMIN_TEMPLATE,
        setup.GLOBAL_READER_TEMPLATE,
    }
    assert config["InitialDomain"] == "customer.onmicrosoft.com"
    assert config["AppObjectId"] == OBJECT_ID
    assert behavior["token_rounds"] == 1


@pytest.mark.parametrize("denied", ["/appRoleAssignments", "/roleAssignments"])
async def test_denied_consent_cannot_report_success_and_retry_reuses_app(api, denied):
    behavior, calls, path = api
    behavior["denied"] = denied
    with pytest.raises(PkceSetupError) as error:
        await setup.provision_app("delegated-token")
    assert error.value.message_key == "err_setup_grant"
    assert "synthetic-secret" not in str(error.value)
    assert not (path / "staging.pfx").exists()
    assert not any(p.endswith("/addPassword") for _, p, _ in calls)
    behavior["denied"] = ""
    assert await setup.provision_app("new-sign-in")
    assert behavior["app_creations"] == 1


async def test_unpropagated_roles_remain_pending_without_reminting_credentials(api, monkeypatch):
    behavior, calls, path = api
    behavior["ready"] = False
    monkeypatch.setattr(setup, "READINESS_SECONDS", 0)
    with pytest.raises(PkceSetupError) as error:
        await setup.provision_app("delegated-token")
    assert error.value.message_key == "err_setup_permissions_pending"
    assert not (path / "staging.pfx").exists()
    checkpoint = setup._pending_path(TENANT)
    assert b"client-secret" not in checkpoint.read_bytes()
    behavior["ready"] = True
    assert await setup.provision_app("new-sign-in")
    assert behavior["app_creations"] == 1
    assert sum(p.endswith("/addPassword") for _, p, _ in calls) == 1
    assert checkpoint.exists()
    setup.finish_setup(TENANT)
    assert not checkpoint.exists()


async def test_readiness_requests_fresh_tokens_after_propagation(api, monkeypatch):
    behavior, _, _ = api
    behavior["ready"] = False
    sleeps = []

    async def propagate(seconds):
        sleeps.append(seconds)
        behavior["ready"] = True

    monkeypatch.setattr(setup.asyncio, "sleep", propagate)
    await setup.provision_app("delegated-token")
    assert len(sleeps) == 1
    assert behavior["token_rounds"] == 2


async def test_repair_reuses_saved_app_and_retains_existing_permissions_and_certificates(
    api, monkeypatch
):
    behavior, calls, _ = api
    behavior.update(existing=True, keys=[{"keyId": "old-cert", "key": "old-public-key"}])
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        lambda: [
            {
                "TenantId": TENANT,
                "ClientId": APP_ID,
                "CustomerId": "Customer_A",
                "CustomerName": "Local name",
                "SubscriptionId": "existing-subscription",
            }
        ],
    )
    config = await setup.provision_app("delegated-token")
    assert behavior["app_creations"] == 0
    patch = [b for m, p, b in calls if m == "PATCH" and p.startswith("/applications")]
    assert any(r["resourceAppId"] == "other-resource" for r in patch[0]["requiredResourceAccess"])
    assert patch[1]["keyCredentials"][0]["keyId"] == "old-cert"
    assert config["SubscriptionId"] == "existing-subscription"
    assert config["CustomerName"] == "Local name"


async def test_customer_scope_is_checked_before_any_tenant_writes(api, monkeypatch):
    _, calls, _ = api
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        lambda: [{"TenantId": TENANT, "ClientId": APP_ID, "_id": "forbidden"}],
    )
    with pytest.raises(PkceSetupError) as error:
        await setup.provision_app("delegated-token", allowed_customer_ids={"allowed"})
    assert error.value.status_code == 403
    assert all(method == "GET" for method, _, _ in calls)


def test_certificate_assertion_proves_private_key_and_binds_audience():
    import jwt
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import pkcs12

    from app.modules.m365_audit.setup import _generate_cert

    _, _, _, pfx, password = _generate_cert()
    config = {"ClientId": APP_ID, "CertPassword": password}
    token_url = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
    assertion = setup._certificate_assertion(config, pfx, token_url)
    _, certificate, _ = pkcs12.load_key_and_certificates(pfx, password.encode())
    claims = jwt.decode(
        assertion, certificate.public_key(), algorithms=["PS256"], audience=token_url
    )
    assert claims["iss"] == claims["sub"] == APP_ID
    assert claims["exp"] - claims["iat"] == 300
    header = jwt.get_unverified_header(assertion)
    assert header["x5t#S256"] == base64.urlsafe_b64encode(
        certificate.fingerprint(hashes.SHA256())
    ).decode().rstrip("=")
    assert setup._certificate_assertion(config, pfx, token_url) != assertion


async def test_permission_repair_retains_a_valid_saved_credential_pair(api, monkeypatch):
    from app.core.encryption import encrypted_write_bytes

    behavior, calls, path = api
    behavior["existing"] = True
    certificate = path / "existing.pfx"
    encrypted_write_bytes(certificate, b"existing-pfx")
    saved = {
        "TenantId": TENANT,
        "ClientId": APP_ID,
        "CustomerId": "Customer_A",
        "CustomerName": "Customer A",
        "CertExpiry": "2030-01-01T00:00:00Z",
        "SecretExpiry": "2030-01-01T00:00:00Z",
    }
    monkeypatch.setattr("app.core.customer.CustomerManager.list_customers", lambda: [saved])
    monkeypatch.setattr("app.core.customer.CustomerManager.get_cert_path", lambda _: certificate)
    monkeypatch.setattr(
        "app.core.credentials.get_secret",
        lambda _, name: "client-secret" if name == "client_secret" else "existing-password",
    )
    config = await setup.provision_app("delegated-token")
    assert config["CertPassword"] == "existing-password"
    assert not any(p.endswith("/addPassword") or "keyCredentials" in b for _, p, b in calls)
    from app.core.encryption import encrypted_read_bytes

    assert encrypted_read_bytes(path / "staging.pfx") == b"existing-pfx"


async def test_explicit_renewal_issues_new_credentials_and_resumes_same_pair(api, monkeypatch):
    behavior, calls, _ = api
    behavior["existing"] = True
    saved = {
        "TenantId": TENANT,
        "ClientId": APP_ID,
        "CustomerId": "Customer_A",
        "CustomerName": "Customer A",
    }
    monkeypatch.setattr("app.core.customer.CustomerManager.list_customers", lambda: [saved])
    monkeypatch.setattr(
        setup,
        "_existing_credentials",
        lambda _: pytest.fail("Explicit renewal must issue a new pair"),
    )
    assert await setup.provision_app("delegated-token", renew_config=saved)
    assert await setup.provision_app("new-sign-in", renew_config=saved)
    assert behavior["app_creations"] == 0
    assert sum(p.endswith("/addPassword") for _, p, _ in calls) == 1


async def test_renewal_rejects_sign_in_to_another_tenant_before_mutation(api):
    _, calls, _ = api
    with pytest.raises(PkceSetupError) as error:
        await setup.provision_app(
            "delegated-token", renew_config={"TenantId": APP_ID, "ClientId": APP_ID}
        )
    assert error.value.message_key == "err_setup_renew_tenant"
    assert all(method == "GET" for method, _, _ in calls)


@pytest.mark.parametrize("service", ["Exchange Online", "Purview"])
async def test_each_workload_requires_its_supported_directory_role(api, monkeypatch, service):
    behavior, _, _ = api
    template, role_name = setup.DIRECTORY_ROLES[service]
    behavior["hidden_directory_roles"].add(template)
    monkeypatch.setattr(setup, "READINESS_SECONDS", 0)
    with pytest.raises(PkceSetupError) as error:
        await setup.provision_app("delegated-token")
    assert error.value.message_key == "err_setup_permissions_pending"
    assert error.value.params["missing"] == f"{service}: {role_name}"
