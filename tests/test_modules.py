"""Optional modules: off is off, and an existing install keeps what it uses.

A switched-off module answers 404 on its routes, hides its views, keeps its
scheduled jobs from running, and drops out of /auth/me. The first start
decides the defaults from evidence of use, so an upgrade removes nothing an
install relies on while a new install starts small.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import modules
from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.config import load_app_settings, update_app_settings
from app.core.database import get_db, run_migrations
from app.core.features import FEATURES, allows, views_for
from app.core.rbac import set_can_write
from app.models.user import Role
from app.services import scheduler
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

pytestmark = pytest.mark.modules_real
PASSWORD = "Str0ng-Passphrase-For-Modules!"


@pytest.fixture(autouse=True)
async def _db(tmp_path):
    import app.core.database as database_module
    import app.web.middleware.rate_limit as rate_limit

    _reset_users_exist_cache()
    rate_limit._hits.clear()
    database_module.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    update_app_settings(lambda s: s.pop(modules.SETTINGS_KEY, None))
    yield
    _reset_users_exist_cache()


async def _headers(role: Role = Role.admin) -> dict:
    user = await create_user(f"u-{role.value}", PASSWORD, "User", role=role, all_customers=True)
    await set_can_write(user.id, True)
    return {"Authorization": f"Bearer {await create_access_token(await get_user_by_id(user.id))}"}


async def test_a_new_install_starts_with_every_module_off():
    await modules.initialize()
    assert modules.enabled() == set()
    assert set(load_app_settings()[modules.SETTINGS_KEY]) == {m.key for m in modules.MODULES}


async def test_an_existing_install_keeps_what_it_uses():
    await create_user("existing", PASSWORD, "Existing", role=Role.admin)
    async with get_db() as db:
        await db.execute(
            "INSERT INTO ssh_keys (id, name, key_type, public_key, fingerprint, created_at, updated_at) "
            "VALUES ('k1', 'k', 'ed25519', 'pub', 'fp', '2026-01-01', '2026-01-01')"
        )
        await db.commit()
    update_app_settings(lambda s: s.update({"uniweb_email": "ops@example.invalid"}))
    await modules.initialize()
    assert modules.enabled() == {"remote", "provisioning", "billing"}


async def test_the_defaults_are_decided_once():
    await modules.initialize()
    modules.set_enabled({"ai": True})
    await modules.initialize()
    assert modules.enabled() == {"ai"}


async def test_a_switched_off_module_answers_404_and_comes_back_when_on():
    modules.set_enabled({m.key: False for m in modules.MODULES})
    h = await _headers()
    with TestClient(create_app()) as client:
        for path in (
            "/api/ssh/hosts",
            "/api/tailscale/status",
            "/api/claude/status",
            "/api/also/companies",
        ):
            assert client.get(path, headers=h).status_code == 404, path
        modules.set_enabled({"remote": True})
        assert client.get("/api/ssh/hosts", headers=h).status_code == 200


async def test_off_modules_leave_auth_me_and_the_views():
    modules.set_enabled({m.key: False for m in modules.MODULES} | {"tailscale": True})
    h = await _headers()
    with TestClient(create_app()) as client:
        me = client.get("/api/auth/me", headers=h).json()
    assert me["modules"] == ["tailscale"]
    assert "remote" not in me["features"] and "ai" not in me["features"]
    assert {"hosts", "terminal", "ai", "provision"}.isdisjoint(me["views"])
    assert "tailscale" in me["views"]


async def test_a_feature_in_an_off_module_is_out_of_reach_for_everyone():
    modules.set_enabled({m.key: False for m in modules.MODULES})
    admin = type("U", (), {"role": Role.admin, "tenant_write": True, "can_write": True})()
    gated = [f for f in FEATURES if f.module]
    assert gated and not any(allows(admin, f) for f in gated)
    assert "ai" not in views_for(admin)


async def test_jobs_of_an_off_module_do_not_run():
    modules.set_enabled({m.key: False for m in modules.MODULES})
    assert not modules.task_allowed("uniweb_sync")
    assert modules.task_allowed("db_cleanup")
    result = await scheduler.run_now("uniweb_sync", actor="tester")
    assert result["ok"] is False


async def test_only_an_admin_switches_modules_and_unknown_names_are_refused():
    modules.set_enabled({m.key: False for m in modules.MODULES})
    admin = await _headers()
    tech = await _headers(Role.technician)
    with TestClient(create_app()) as client:
        assert (
            client.put("/api/settings/modules", headers=tech, json={"ai": True}).status_code == 403
        )
        r = client.put("/api/settings/modules", headers=admin, json={"ai": True})
        assert r.status_code == 200 and r.json()["enabled"] == ["ai"]
        listed = client.get("/api/settings/modules", headers=admin).json()["modules"]
        assert {m["key"]: m["enabled"] for m in listed}["ai"] is True
        assert (
            client.put("/api/settings/modules", headers=admin, json={"nope": True}).status_code
            == 400
        )


async def test_an_off_modules_jobs_neither_list_nor_hold_up_readiness():
    modules.set_enabled({m.key: False for m in modules.MODULES})
    listed = {t["id"] for t in scheduler.get_status()}
    assert "uniweb_sync" not in listed and "also_price_refresh" not in listed
    assert "db_cleanup" in listed
