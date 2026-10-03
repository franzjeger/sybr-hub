"""SSH hosts and keys: what goes into a host record, and who may point it where.

A stored host carries a device password (or names a key) that the hub sends
on the caller's behalf. Three things decide whether that is safe: the fields
are clean enough to be written into an SSH config or RDP profile, a key is
only attached by someone entitled to use it, and moving a host to a new
address does not take the stored password along.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.database import run_migrations
from app.core.rbac import grant_access, set_can_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

GOOD_PASSWORD = "Test1234!xyz"


@pytest.fixture(autouse=True)
def _reset_state():
    import app.web.middleware.rate_limit as rl

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _init_db(tmp_path, monkeypatch):
    import app.core.database as db_mod
    from app.services import ssh_manager

    db_mod.DB_PATH = tmp_path / "test.db"
    # SSH_KEYS_DIR is resolved at import time, before the suite redirects
    # DATA_DIR, so keys and host passwords would land in the real data dir.
    monkeypatch.setattr(ssh_manager, "SSH_KEYS_DIR", tmp_path / "ssh_keys")
    await run_migrations()
    yield


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


async def _token(
    name: str,
    role: Role = Role.technician,
    *,
    customers: list[str] | None = None,
    all_customers: bool = False,
) -> dict[str, str]:
    user = await create_user(
        name, GOOD_PASSWORD, name.title(), role=role, all_customers=all_customers
    )
    for cid in customers or []:
        await grant_access(user.id, cid)
    await set_can_write(user.id, True)
    user = await get_user_by_id(user.id)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


def _host_body(**over) -> dict:
    body = {
        "label": "SRV-FILE01",
        "hostname": "10.20.1.10",
        "port": 22,
        "username": "root",
        "auth_method": "password",
        "password": "device-secret",
        "customer_id": "acme",
    }
    body.update(over)
    return body


# ── Field validation ─────────────────────────────────────────────────────────


class TestHostFieldsAreValidated:
    @pytest.mark.parametrize(
        "over",
        [
            {"hostname": "10.0.0.1\nProxyCommand nc evil 22"},
            {"hostname": "a host"},
            {"hostname": "$(id)"},
            {"username": "root\nProxyCommand sh"},
            {"username": "bob;reboot"},
            {"username": "a/b"},
            {"label": "web\nHost *"},
            {"group_name": "grp\x00"},
            {"label": "\N{RIGHT-TO-LEFT OVERRIDE}evil"},
            {"notes": "bell\x07"},
            {"tags": ["ok", "bad\ntag"]},
        ],
    )
    async def test_create_refuses_control_characters_and_bad_hosts(self, client, over):
        from app.services.ssh_manager import list_hosts

        resp = client.post(
            "/api/ssh/hosts",
            headers=await _token("tech", customers=["acme"]),
            json=_host_body(**over),
        )
        assert resp.status_code == 400, resp.text
        assert await list_hosts() == [], "a rejected host was stored anyway"

    async def test_create_accepts_ordinary_unicode_text(self, client):
        from app.services.ssh_manager import list_hosts

        resp = client.post(
            "/api/ssh/hosts",
            headers=await _token("tech", customers=["acme"]),
            json=_host_body(
                label="Kontor Ålesund",
                group_name="Filservere øst (Bodø)",
                username="FIRMA\\ola.nordmann",
                notes="Første linje\nAndre linje",
            ),
        )
        assert resp.status_code == 200, resp.text
        [host] = await list_hosts()
        assert host.label == "Kontor Ålesund"
        assert host.username == "FIRMA\\ola.nordmann"
        assert host.notes == "Første linje\nAndre linje"

    @pytest.mark.parametrize(
        "over",
        [
            {"hostname": "10.0.0.1 -oProxyCommand=x"},
            {"username": "ro\r\not"},
            {"label": ""},
            {"port": 70000},
        ],
    )
    async def test_update_validates_the_same_fields(self, client, over):
        from app.services.ssh_manager import get_host

        hdr = await _token("tech", customers=["acme"])
        created = client.post("/api/ssh/hosts", headers=hdr, json=_host_body())
        host_id = created.json()["host"]["id"]

        resp = client.put(f"/api/ssh/hosts/{host_id}", headers=hdr, json=over)
        assert resp.status_code in (400, 422), resp.text
        host = await get_host(host_id)
        assert host.hostname == "10.20.1.10"
        assert host.username == "root"
        assert host.label == "SRV-FILE01"
        assert host.port == 22


# ── Keys are scoped to a customer ────────────────────────────────────────────


async def _key(customer_id: str | None, name: str = "k"):
    from app.services.ssh_manager import generate_key

    return await generate_key(name=name, customer_id=customer_id)


class TestAKeyIsOnlyAttachedBySomeoneWhoMayUseIt:
    """A customer-scoped technician must not be able to point a host of their
    own at another customer's device and authenticate with a key that is
    authorised there."""

    @pytest.mark.parametrize("key_owner", [None, "other"])
    async def test_scoped_technician_cannot_attach_a_key_outside_their_customers(
        self, client, key_owner
    ):
        from app.services.ssh_manager import list_hosts

        key = await _key(key_owner)
        resp = client.post(
            "/api/ssh/hosts",
            headers=await _token("tech", customers=["acme"]),
            json=_host_body(auth_method="key", password=None, auth_key_id=key.id),
        )
        assert resp.status_code == 403, resp.text
        assert await list_hosts() == []

    async def test_scoped_technician_can_attach_their_customers_key(self, client):
        from app.services.ssh_manager import list_hosts

        key = await _key("acme")
        resp = client.post(
            "/api/ssh/hosts",
            headers=await _token("tech", customers=["acme"]),
            json=_host_body(auth_method="key", password=None, auth_key_id=key.id),
        )
        assert resp.status_code == 200, resp.text
        [host] = await list_hosts()
        assert host.auth_key_id == key.id

    async def test_an_all_customers_technician_can_attach_an_msp_wide_key(self, client):
        key = await _key(None)
        resp = client.post(
            "/api/ssh/hosts",
            headers=await _token("tech", all_customers=True),
            json=_host_body(auth_method="key", password=None, auth_key_id=key.id),
        )
        assert resp.status_code == 200, resp.text

    async def test_a_key_that_does_not_exist_is_refused(self, client):
        resp = client.post(
            "/api/ssh/hosts",
            headers=await _token("admin", Role.admin),
            json=_host_body(auth_method="key", password=None, auth_key_id="no-such-key"),
        )
        assert resp.status_code == 400, resp.text

    async def test_update_cannot_switch_to_a_key_outside_scope(self, client):
        from app.services.ssh_manager import get_host

        own = await _key("acme", "own")
        msp = await _key(None, "msp")
        hdr = await _token("tech", customers=["acme"])
        created = client.post(
            "/api/ssh/hosts",
            headers=hdr,
            json=_host_body(auth_method="key", password=None, auth_key_id=own.id),
        )
        host_id = created.json()["host"]["id"]

        resp = client.put(f"/api/ssh/hosts/{host_id}", headers=hdr, json={"auth_key_id": msp.id})
        assert resp.status_code == 403, resp.text
        assert (await get_host(host_id)).auth_key_id == own.id


class TestKeyListingAndManagement:
    async def test_viewers_cannot_list_keys(self, client):
        await _key("acme")
        resp = client.get(
            "/api/ssh/keys", headers=await _token("viewer", Role.viewer, customers=["acme"])
        )
        assert resp.status_code == 403, resp.text

    async def test_scoped_technician_lists_only_keys_they_can_use(self, client):
        own = await _key("acme", "own")
        await _key("other", "theirs")
        await _key(None, "msp")
        resp = client.get("/api/ssh/keys", headers=await _token("tech", customers=["acme"]))
        assert resp.status_code == 200, resp.text
        assert [k["id"] for k in resp.json()["keys"]] == [own.id]

    async def test_admin_lists_every_key(self, client):
        for owner in ("acme", "other", None):
            await _key(owner)
        resp = client.get("/api/ssh/keys", headers=await _token("admin", Role.admin))
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["keys"]) == 3

    @pytest.mark.parametrize("path", ["/api/ssh/keys/{id}", "/api/ssh/keys/{id}/public"])
    async def test_a_key_outside_scope_cannot_be_read(self, client, path):
        key = await _key(None)
        resp = client.get(path.format(id=key.id), headers=await _token("tech", customers=["acme"]))
        assert resp.status_code == 403, resp.text

    async def test_a_key_outside_scope_cannot_be_pushed(self, client):
        key = await _key(None)
        hdr = await _token("tech", customers=["acme"])
        created = client.post("/api/ssh/hosts", headers=hdr, json=_host_body())
        host_id = created.json()["host"]["id"]
        resp = client.post(
            f"/api/ssh/keys/{key.id}/push", headers=hdr, json={"host_ids": [host_id]}
        )
        assert resp.status_code == 403, resp.text

    async def test_technicians_cannot_delete_keys(self, client):
        from app.services.ssh_manager import get_key

        key = await _key("acme")
        resp = client.delete(
            f"/api/ssh/keys/{key.id}", headers=await _token("tech", customers=["acme"])
        )
        assert resp.status_code == 403, resp.text
        assert await get_key(key.id) is not None

    async def test_admin_can_delete_a_key(self, client):
        from app.services.ssh_manager import get_key

        key = await _key("acme")
        resp = client.delete(f"/api/ssh/keys/{key.id}", headers=await _token("admin", Role.admin))
        assert resp.status_code == 200, resp.text
        assert await get_key(key.id) is None

    async def test_a_scoped_technician_must_bind_a_new_key_to_their_customer(self, client):
        from app.services.ssh_manager import list_keys

        hdr = await _token("tech", customers=["acme"])
        assert client.post("/api/ssh/keys", headers=hdr, json={"name": "k"}).status_code == 403
        assert (
            client.post(
                "/api/ssh/keys", headers=hdr, json={"name": "k", "customer_id": "other"}
            ).status_code
            == 403
        )
        resp = client.post("/api/ssh/keys", headers=hdr, json={"name": "k", "customer_id": "acme"})
        assert resp.status_code == 200, resp.text
        [key] = await list_keys()
        assert key.customer_id == "acme"


# ── Repointing a host does not take its password along ───────────────────────


@pytest.fixture()
def captured_connect(monkeypatch):
    """Record what the hub would send when it opens an SSH session."""
    from app.services.ssh_connection import SshSession

    calls: list[dict] = []

    async def _fake_connect(**kwargs):
        calls.append(kwargs)
        raise OSError("not connecting from a test")

    monkeypatch.setattr(SshSession, "connect", staticmethod(_fake_connect))
    return calls


def _create(client, hdr, **over) -> str:
    resp = client.post("/api/ssh/hosts", headers=hdr, json=_host_body(**over))
    assert resp.status_code == 200, resp.text
    return resp.json()["host"]["id"]


class TestRepointingClearsTheStoredPassword:
    @pytest.mark.parametrize(
        "change",
        [{"hostname": "203.0.113.66"}, {"port": 2222}, {"username": "admin"}],
    )
    async def test_a_new_target_without_a_password_is_not_sent_the_old_one(
        self, client, captured_connect, change
    ):
        from app.services.ssh_manager import _load_host_password

        hdr = await _token("tech", customers=["acme"])
        host_id = _create(client, hdr)

        resp = client.put(f"/api/ssh/hosts/{host_id}", headers=hdr, json=change)
        assert resp.status_code == 200, resp.text
        assert resp.json()["password_cleared"] is True
        assert _load_host_password(host_id) is None

        client.post(f"/api/ssh/hosts/{host_id}/test", headers=hdr)
        [call] = captured_connect
        assert call["password"] is None, "the stored password went to the new target"

    async def test_repointing_with_a_new_password_stores_that_one(self, client):
        from app.services.ssh_manager import _load_host_password

        hdr = await _token("tech", customers=["acme"])
        host_id = _create(client, hdr)

        resp = client.put(
            f"/api/ssh/hosts/{host_id}",
            headers=hdr,
            json={"hostname": "10.20.1.99", "password": "new-device-secret"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["password_cleared"] is False
        assert _load_host_password(host_id) == "new-device-secret"

    async def test_the_edit_form_resending_unchanged_values_keeps_the_password(self, client):
        """The UI sends every field on save. Only a real change counts."""
        from app.services.ssh_manager import _load_host_password

        hdr = await _token("tech", customers=["acme"])
        host_id = _create(client, hdr)

        resp = client.put(
            f"/api/ssh/hosts/{host_id}",
            headers=hdr,
            json={
                "label": "SRV-FILE01 (primær)",
                "hostname": "10.20.1.10",
                "username": "root",
                "port": 22,
                "device_type": "linux",
                "group_name": "Filservere",
                "notes": "flyttet rack",
                "customer_id": "acme",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["password_cleared"] is False
        assert _load_host_password(host_id) == "device-secret"

    async def test_the_rule_applies_to_admins_as_well(self, client):
        from app.services.ssh_manager import _load_host_password

        hdr = await _token("admin", Role.admin)
        host_id = _create(client, hdr)
        resp = client.put(
            f"/api/ssh/hosts/{host_id}", headers=hdr, json={"hostname": "198.51.100.7"}
        )
        assert resp.status_code == 200, resp.text
        assert _load_host_password(host_id) is None

    async def test_a_key_host_cannot_be_repointed_by_someone_who_may_not_use_the_key(self, client):
        """An admin attached an MSP-wide key to one of acme's hosts. A technician
        scoped to acme may use the host, but aiming it elsewhere would aim the
        MSP key at a device of their choosing."""
        from app.services.ssh_manager import get_host

        msp = await _key(None)
        host_id = _create(
            client,
            await _token("admin", Role.admin),
            auth_method="key",
            password=None,
            auth_key_id=msp.id,
        )
        tech = await _token("tech", customers=["acme"])

        resp = client.put(f"/api/ssh/hosts/{host_id}", headers=tech, json={"hostname": "10.9.9.9"})
        assert resp.status_code == 403, resp.text
        assert (await get_host(host_id)).hostname == "10.20.1.10"

        resp = client.put(f"/api/ssh/hosts/{host_id}", headers=tech, json={"label": "renamed"})
        assert resp.status_code == 200, resp.text


class TestMovingAHostToAnotherCustomer:
    async def test_needs_access_to_the_target_customer(self, client):
        from app.services.ssh_manager import get_host

        hdr = await _token("tech", customers=["acme"])
        host_id = _create(client, hdr)
        resp = client.put(f"/api/ssh/hosts/{host_id}", headers=hdr, json={"customer_id": "other"})
        assert resp.status_code == 403, resp.text
        assert (await get_host(host_id)).customer_id == "acme"

    async def test_an_empty_customer_makes_it_estate_wide_which_needs_unrestricted(self, client):
        from app.services.ssh_manager import get_host

        hdr = await _token("tech", customers=["acme"])
        host_id = _create(client, hdr)
        resp = client.put(f"/api/ssh/hosts/{host_id}", headers=hdr, json={"customer_id": ""})
        assert resp.status_code == 403, resp.text
        assert (await get_host(host_id)).customer_id == "acme"

    async def test_allowed_when_the_caller_has_both_customers(self, client):
        from app.services.ssh_manager import get_host

        hdr = await _token("tech", customers=["acme", "beta"])
        host_id = _create(client, hdr)
        resp = client.put(f"/api/ssh/hosts/{host_id}", headers=hdr, json={"customer_id": "beta"})
        assert resp.status_code == 200, resp.text
        assert (await get_host(host_id)).customer_id == "beta"
