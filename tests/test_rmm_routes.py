"""The RMM deep-link routes, end to end against a fake Datto (TODO D19).

The real driver runs; only its transport is a fake Datto RMM answering by path.
What is pinned: credentials are an administrator's and never come back,
a site is looked up before a customer is bound to it, one customer's site is
not another's, and a Web Remote link reaches the page only for a device the
Hub knows that Datto knows by exactly the same name or MAC address.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.customer import CustomerManager, customer_dir_name
from app.core.database import run_migrations
from app.core.rbac import grant_access, set_can_write
from app.integrations.datto_rmm import DattoRMMClient
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

PASSWORD = "Str0ng-Passphrase-For-RMM-Tests!"
API = "https://concord-api.centrastage.net"
KEY = "synthetic-datto-key"
SECRET = "synthetic-datto-secret"
TOKEN = "synthetic-datto-token"
RUN = "2026-10-01_120000"


def _device(uid: str, hostname: str, site: str = "site-a", online: bool = True) -> dict:
    return {
        "uid": uid,
        "hostname": hostname,
        "siteUid": site,
        "operatingSystem": "Microsoft Windows 11 Pro",
        "online": online,
        "deleted": False,
        "webRemoteUrl": f"https://concord.centrastage.net/csm/remote/{uid}",
    }


class FakeDatto:
    """Datto RMM by path. ``answers`` maps an API path to JSON or a Response."""

    def __init__(self) -> None:
        self.answers: dict[str, object] = {
            "/api/v2/account/sites": {
                "pageDetails": {},
                "sites": [
                    {"uid": "site-a", "name": "Kunde A site"},
                    {"uid": "site-b", "name": "Kunde B site"},
                ],
            },
            "/api/v2/site/site-a": {"uid": "site-a", "name": "Kunde A site"},
            "/api/v2/site/site-b": {"uid": "site-b", "name": "Kunde B site"},
        }
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/auth/oauth/token":
            return httpx.Response(200, json={"access_token": TOKEN})
        answer = self.answers.get(request.url.path)
        if answer is None:
            return httpx.Response(404, json={"message": "not found"})
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(200, json=answer)


@pytest.fixture(autouse=True)
def _reset_middleware_state():
    import app.web.middleware.rate_limit as rate_limit

    _reset_users_exist_cache()
    rate_limit._hits.clear()
    rate_limit._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rate_limit._hits.clear()
    rate_limit._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _isolated_state(tmp_path, monkeypatch):
    import app.core.config as config_module
    import app.core.customer as customer_module
    import app.core.database as database_module

    database_module.DB_PATH = tmp_path / "test.db"
    (tmp_path / "customers").mkdir()
    (tmp_path / "audits").mkdir()
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config_module, "_DEFAULT_AUDIT_DIR", tmp_path / "audits")
    await run_migrations()
    yield


@pytest.fixture()
def datto(monkeypatch) -> FakeDatto:
    """The real driver, wired to a fake Datto instead of the network."""
    fake = FakeDatto()

    class _Wired(DattoRMMClient):
        def __init__(self, *args: str) -> None:
            super().__init__(*args)
            headers = self._client.headers
            self._client = httpx.AsyncClient(
                transport=httpx.MockTransport(fake.handle), headers=headers
            )

    monkeypatch.setattr("app.web.routes.rmm.DattoRMMClient", _Wired)
    return fake


@pytest.fixture()
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _configure() -> None:
    from app.core.config import update_app_settings

    def mutate(settings: dict) -> None:
        settings.update(datto_rmm_api_url=API, datto_rmm_api_key=KEY, datto_rmm_api_secret=SECRET)

    update_app_settings(mutate)


def _customer(name: str, **extra: str) -> str:
    return CustomerManager.save_customer({"CustomerName": name, **extra})


def _audit(name: str, intune: list[dict], entra: list[dict] | None = None) -> None:
    from app.core.config import get_audit_dir
    from app.core.encryption import encrypted_write_json

    run = get_audit_dir() / customer_dir_name(name) / RUN
    run.mkdir(parents=True)
    encrypted_write_json(run / "_audit_metrics.json", {"recommendations": []})
    encrypted_write_json(run / "10_intune_devices.json", {"devices": intune})
    if entra is not None:
        encrypted_write_json(run / "15_entra_devices.json", {"devices": entra})


async def _headers(name: str, role: Role = Role.technician, grants: list[str] | None = None):
    user = await create_user(name, PASSWORD, name, role=role, all_customers=grants is None)
    await set_can_write(user.id, True)
    for cid in grants or []:
        await grant_access(user.id, cid)
    user = await get_user_by_id(user.id)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


# ── Settings and the connection test ──────────────────────────────────────────


async def test_the_credentials_are_stored_masked_and_the_url_must_be_datto(client):
    admin = await _headers("rmm-admin", Role.admin)

    saved = client.post(
        "/api/settings",
        headers=admin,
        json={
            "datto_rmm_api_url": "https://Concord-API.centrastage.net/",
            "datto_rmm_api_key": KEY,
            "datto_rmm_api_secret": SECRET,
        },
    )
    assert saved.status_code == 200, saved.text
    got = client.get("/api/settings", headers=admin).json()
    assert got["datto_rmm_api_url"] == API
    assert got["datto_rmm_api_key"] == got["datto_rmm_api_secret"] == "••••••"
    assert got["datto_rmm_api_key_set"] and got["datto_rmm_api_secret_set"]
    assert KEY not in str(got) and SECRET not in str(got)

    # The mask sent back is "unchanged", never the new secret.
    client.post("/api/settings", headers=admin, json={"datto_rmm_api_secret": "••••••"})
    from app.core.config import load_app_settings

    assert load_app_settings()["datto_rmm_api_secret"] == SECRET

    # The URL is where the key and secret go: anything but Datto's API host is refused.
    refused = client.post(
        "/api/settings", headers=admin, json={"datto_rmm_api_url": "https://evil.example"}
    )
    assert refused.status_code == 400
    assert refused.json()["error_key"] == "err_rmm_api_url_invalid"
    assert load_app_settings()["datto_rmm_api_url"] == API


async def test_the_connection_test_is_an_administrators_and_records_evidence(client, datto):
    _configure()
    tech = await _headers("rmm-tech")
    admin = await _headers("rmm-admin", Role.admin)

    assert client.post("/api/rmm/test", headers=tech, json={}).status_code == 403
    assert client.post("/api/rmm/test", headers=admin, json={"token": "x"}).status_code == 422

    result = client.post("/api/rmm/test", headers=admin, json={}).json()

    assert result["ok"] is True and result["sample_fields"] == ["name", "uid"]
    assert "Kunde A site" not in str(result), "field names, never a customer's record"
    health = client.get("/api/settings", headers=admin).json()["integration_health"]
    assert health["datto_rmm"]["state"] == "verified"


async def test_unsaved_credentials_are_tested_without_verifying_the_saved_ones(client, datto):
    _configure()
    admin = await _headers("rmm-admin", Role.admin)

    result = client.post(
        "/api/rmm/test",
        headers=admin,
        json={"api_url": API, "api_key": "a-draft-key", "api_secret": "••••••"},
    ).json()

    assert result["ok"] is True
    token = next(r for r in datto.requests if r.url.path == "/auth/oauth/token")
    assert b"a-draft-key" in token.content and SECRET.encode() in token.content
    health = client.get("/api/settings", headers=admin).json()["integration_health"]
    assert health["datto_rmm"]["state"] == "configured", "a draft is not the stored account"


# ── The site picker and the binding ───────────────────────────────────────────


async def test_the_site_list_is_ids_and_names_and_a_failure_is_not_empty(client, datto):
    _configure()
    tech = await _headers("rmm-tech")
    viewer = await _headers("rmm-viewer", Role.viewer)

    assert client.get("/api/rmm/sites", headers=viewer).status_code == 403
    sites = client.get("/api/rmm/sites", headers=tech).json()["sites"]
    assert sites == [
        {"id": "site-a", "name": "Kunde A site"},
        {"id": "site-b", "name": "Kunde B site"},
    ]

    datto.answers["/api/v2/account/sites"] = httpx.Response(403)
    failed = client.get("/api/rmm/sites", headers=tech)
    assert failed.status_code == 502 and "sites" not in failed.json()


async def test_a_site_is_looked_up_before_a_customer_is_bound_to_it(client, datto):
    _configure()
    acme = _customer("Acme")
    beta = _customer("Beta")
    tech = await _headers("rmm-tech")

    bound = client.post(
        f"/api/hub/{acme}/link", headers=tech, json={"datto_rmm_site_uid": "site-a"}
    )
    assert bound.status_code == 200, bound.text
    block = client.get(f"/api/hub/{acme}", headers=tech).json()["rmm"]
    assert block == {"status": "ok", "site_uid": "site-a", "site_name": "Kunde A site"}

    # A uid Datto has never heard of is refused, not stored.
    unknown = client.post(
        f"/api/hub/{beta}/link", headers=tech, json={"datto_rmm_site_uid": "site-x"}
    )
    assert unknown.status_code == 404
    assert "DattoRmmSiteUid" not in CustomerManager.get_customer(beta)

    # One site is one customer's: its devices are offered to whoever holds it.
    taken = client.post(
        f"/api/hub/{beta}/link", headers=tech, json={"datto_rmm_site_uid": "site-a"}
    )
    assert taken.status_code == 409

    cleared = client.post(f"/api/hub/{acme}/link", headers=tech, json={"datto_rmm_site_uid": None})
    assert cleared.status_code == 200
    record = CustomerManager.get_customer(acme)
    assert "DattoRmmSiteUid" not in record and "DattoRmmSiteName" not in record


# ── The devices and their Web Remote links ────────────────────────────────────


async def test_each_state_before_a_device_list_says_which_it_is(client, datto):
    acme = _customer("Acme")
    tech = await _headers("rmm-tech")
    path = f"/api/rmm/devices/{acme}"

    assert client.get(path, headers=tech).json() == {"status": "not_configured"}
    _configure()
    assert client.get(path, headers=tech).json() == {"status": "not_linked"}
    client.post(f"/api/hub/{acme}/link", headers=tech, json={"datto_rmm_site_uid": "site-a"})
    assert client.get(path, headers=tech).json()["status"] == "no_run"
    assert not any("/devices" in r.url.path for r in datto.requests), "no device read before a run"


async def test_a_web_remote_link_is_offered_only_for_an_exact_match(client, datto):
    """The whole point: a button opens a session, so a near miss gets none."""
    _configure()
    acme = _customer("Acme", DattoRmmSiteUid="site-a", DattoRmmSiteName="Kunde A site")
    _audit(
        "Acme",
        intune=[
            {"name": "PC-01", "os": "Windows"},
            {"name": "PC-02", "os": "Windows"},
            {"name": "PC-03", "os": "Windows"},
            {"name": "Kari's MacBook", "os": "macOS", "wifi_mac": "0a:1b:2c:3d:4e:5f"},
            {"name": "Ola's MacBook", "os": "macOS", "wifi_mac": "0a:1b:2c:3d:4e:60"},
            {"name": "Kari iPhone", "os": "iOS"},
        ],
    )
    datto.answers["/api/v2/site/site-a/devices"] = {
        "pageDetails": {},
        "devices": [
            _device("d1", "pc-01"),
            _device("d2", "PC-02"),
            _device("d3", "PC-02"),
            _device("d4", "SRV-NOT-IN-THE-HUB"),
        ],
    }
    datto.answers["/api/v2/device/macAddress/0A1B2C3D4E5F"] = [_device("d5", "Karis-MBP")]
    # Found by MAC, but in another customer's site: not this customer's machine.
    datto.answers["/api/v2/device/macAddress/0A1B2C3D4E60"] = [_device("d6", "Olas-MBP", "site-b")]
    tech = await _headers("rmm-tech")

    body = client.get(f"/api/rmm/devices/{acme}", headers=tech).json()

    assert body["status"] == "ok" and body["audit_date"] == RUN
    rows = {r["name"]: r for r in body["devices"]}
    assert set(rows) == {"Kari's MacBook", "Ola's MacBook", "PC-01", "PC-02", "PC-03"}
    assert rows["PC-01"]["web_remote_url"].endswith("/remote/d1")
    assert rows["PC-01"]["matched_by"] == "hostname" and rows["PC-01"]["online"] is True
    assert rows["Kari's MacBook"]["web_remote_url"].endswith("/remote/d5")
    assert rows["Kari's MacBook"]["matched_by"] == "mac"
    assert (rows["PC-02"]["match"], rows["PC-02"]["candidates"]) == ("ambiguous", 2)
    for name in ("PC-02", "PC-03", "Ola's MacBook"):
        assert rows[name]["web_remote_url"] == "" and rows[name]["online"] is None
    assert body["matched"] == 2
    # Datto's other devices are not the Hub's to list, and nothing secret comes back.
    text = str(body)
    assert "SRV-NOT-IN-THE-HUB" not in text and "d6" not in text
    assert KEY not in text and SECRET not in text and TOKEN not in text


async def test_an_unreadable_datto_is_unavailable_in_the_readers_language(client, datto):
    _configure()
    acme = _customer("Acme", DattoRmmSiteUid="site-a")
    _audit("Acme", intune=[{"name": "PC-01", "os": "Windows"}])
    datto.answers["/api/v2/site/site-a/devices"] = httpx.Response(403)
    tech = await _headers("rmm-tech")

    norsk = client.get(f"/api/rmm/devices/{acme}", headers=tech).json()
    english = client.get(f"/api/rmm/devices/{acme}?lang=en", headers=tech).json()

    assert norsk["status"] == "unavailable" and "devices" not in norsk
    assert norsk["reason_key"] == "err_rmm_devices_failed"
    assert norsk["reason"].startswith("Kunne ikke lese enhetene i Datto RMM")
    assert english["reason"].startswith("Could not read the devices in Datto RMM")


async def test_another_customers_devices_are_refused_and_a_viewer_reads_none(client, datto):
    _configure()
    acme = _customer("Acme", DattoRmmSiteUid="site-a")
    beta = _customer("Beta", DattoRmmSiteUid="site-b")
    scoped = await _headers("acme-tech", grants=[acme])
    viewer = await _headers("rmm-viewer", Role.viewer)

    assert client.get(f"/api/rmm/devices/{beta}", headers=scoped).status_code == 403
    assert client.get(f"/api/rmm/devices/{acme}", headers=scoped).status_code == 200
    assert client.get(f"/api/rmm/devices/{acme}", headers=viewer).status_code == 403
