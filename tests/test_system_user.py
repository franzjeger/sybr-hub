"""The account the toolkit acts as when nobody is watching.

Scheduled work still does things to customer systems, and those things want an
identity. VPN tunnels held open to pull statistics used to be opened under
whichever technician happened to click: the activity log was then wrong about
who did it, and one person's session owned infrastructure everybody depended
on.
"""

from __future__ import annotations

import pytest

from app.core import system_user
from app.core.auth import authenticate, create_user, get_user_by_username
from app.core.database import run_migrations
from app.models.user import Role

GOOD_PASSWORD = "Str0ng-Passphrase-For-Tests!"


@pytest.fixture(autouse=True)
async def _db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


async def test_an_install_starts_without_one():
    """A migration that inserted a privileged account into every existing
    install is the kind of thing that should be a decision somebody made."""
    assert await system_user.get() is None


async def test_creating_it_is_idempotent():
    first = await system_user.ensure()
    second = await system_user.ensure()

    assert first.id == second.id


async def test_it_cannot_sign_in(monkeypatch):
    """An account with no human behind it and no password would otherwise be a
    standing invitation. The identity is for attribution and locking, not a
    second way through the front door.
    """
    await system_user.ensure()
    # Even with the right password — which nothing knows, but prove the refusal
    # is not merely "the password is unguessable".
    import app.core.auth as auth_mod

    monkeypatch.setattr(auth_mod, "verify_password", lambda *a: True)

    assert await authenticate(system_user.USERNAME, "anything") is None


async def test_an_ordinary_account_still_signs_in(monkeypatch):
    """The complement — the refusal must be about is_system, not about the
    monkeypatched password check."""
    await create_user("human", GOOD_PASSWORD, "Human", role=Role.technician)

    assert await authenticate("human", GOOD_PASSWORD) is not None


async def test_it_holds_customer_access_and_write_but_not_tenant_write():
    """It opens tunnels and records what it finds. Nothing running unattended
    should be able to change a customer's Microsoft tenant."""
    user = await system_user.ensure()

    assert user.can_write is True
    assert user.tenant_write is False
    assert user.role == Role.technician, "it administers nothing"


async def test_a_human_account_is_not_mistaken_for_it():
    await create_user(system_user.USERNAME + "-lookalike", GOOD_PASSWORD, "X", role=Role.admin)

    assert await system_user.get() is None


async def test_get_ignores_an_account_with_the_name_but_not_the_flag():
    """Otherwise creating a user called sybr-system would hand it the tunnels."""
    await create_user(system_user.USERNAME, GOOD_PASSWORD, "Impostor", role=Role.admin)

    assert await system_user.get() is None
    assert await get_user_by_username(system_user.USERNAME) is not None


# ── The tunnels it holds ─────────────────────────────────────────────────────

@pytest.fixture()
def tunnels(monkeypatch):
    import app.services.vpn_manager as vm

    monkeypatch.setattr(vm, "_connections", {})
    return vm


def test_a_tunnel_records_who_opened_it(tunnels):
    tunnels._connections["p1"] = {"state": tunnels.VpnState.connected, "owned_by": "frank"}

    assert tunnels.owner_of("p1") == "frank"
    assert tunnels.system_held() == []


def test_a_tunnel_the_system_holds_is_reported(tunnels):
    tunnels._connections["p1"] = {
        "state": tunnels.VpnState.connected, "owned_by": system_user.USERNAME
    }

    assert tunnels.system_held() == ["p1"]


def test_a_tunnel_still_coming_up_counts(tunnels):
    """Tearing one down mid-handshake breaks the collection just as thoroughly."""
    tunnels._connections["p1"] = {
        "state": tunnels.VpnState.connecting, "owned_by": system_user.USERNAME
    }

    assert tunnels.system_held() == ["p1"]


def test_a_tunnel_that_has_gone_down_does_not_hold_the_lock(tunnels):
    """Otherwise a failed collection locks VPN out until somebody restarts."""
    tunnels._connections["p1"] = {
        "state": tunnels.VpnState.error, "owned_by": system_user.USERNAME
    }

    assert tunnels.system_held() == []


async def test_the_lock_names_what_is_holding_it(tunnels, monkeypatch):
    """A wall with no reason is one somebody works around rather than waits for."""
    from app.core.exceptions import ForbiddenError
    from app.web.routes import vpn as vpn_routes

    tunnels._connections["p1"] = {
        "state": tunnels.VpnState.connected, "owned_by": system_user.USERNAME
    }

    class _Profile:
        name = "Fonnafly hovedkontor"

    monkeypatch.setattr(
        "app.services.vpn_manager.get_profile", lambda pid: _profile_coro(_Profile())
    )

    with pytest.raises(ForbiddenError) as exc:
        await vpn_routes._refuse_if_system_holds_tunnels()

    assert "Fonnafly hovedkontor" in str(exc.value)


async def _profile_coro(value):
    return value


async def test_nothing_is_refused_when_the_system_holds_nothing(tunnels):
    from app.web.routes import vpn as vpn_routes

    assert await vpn_routes._refuse_if_system_holds_tunnels() is None


def test_every_route_that_can_tear_down_a_tunnel_is_behind_the_lock():
    """Scoped to what actually disturbs a running tunnel.

    A first version demanded the lock on every mutating VPN route, which caught
    profile creation and the Azure sign-in flows — neither touches a tunnel, and
    blocking them would be a wall with nothing behind it. The routes that matter
    are the ones that stop, replace or remove a connection, and force-disconnect
    especially: unguarded it is simply the way around the guard on disconnect.
    """
    import re

    source = pathlib.Path("app/web/routes/vpn.py").read_text(encoding="utf-8")
    must_be_guarded = {
        "/vpn/connect/{profile_id}",
        "/vpn/disconnect",
        "/vpn/force-disconnect",
        "/vpn/profiles/{profile_id}",   # deleting one the collectors are using
    }

    guarded = set()
    for block in re.split(r"@router\.", source)[1:]:
        head = block.split("\n")[0]
        if head.startswith("get("):
            continue
        name = re.search(r'"([^"]+)"', head)
        if name and "_refuse_if_system_holds_tunnels" in block.split("@router.")[0]:
            guarded.add(name.group(1))

    assert must_be_guarded <= guarded, (
        f"can tear down a system tunnel without the lock: "
        f"{sorted(must_be_guarded - guarded)}"
    )


def test_the_lock_is_not_on_routes_that_touch_no_tunnel():
    """A wall with nothing behind it teaches people to route around walls."""
    import re

    source = pathlib.Path("app/web/routes/vpn.py").read_text(encoding="utf-8")
    for block in re.split(r"@router\.", source)[1:]:
        head = block.split("\n")[0]
        name = re.search(r'"([^"]+)"', head)
        if not name or not name.group(1).startswith("/vpn/azure"):
            continue
        assert "_refuse_if_system_holds_tunnels" not in block.split("@router.")[0], (
            f"{name.group(1)} is an authentication flow and disturbs no tunnel"
        )


import pathlib  # noqa: E402
