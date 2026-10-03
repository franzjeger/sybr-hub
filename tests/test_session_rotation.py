"""What the refresh endpoint answers, and what a session's tokens survive.

The session table stored a hash of the refresh token from day one, and nothing
ever compared against it: a refresh token stayed good for its full 30 days no
matter how often it was used, and a copy kept working alongside the original.
Changing a password left every one of those tokens alive.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import app.core.auth as auth_mod
from app.core import mfa
from app.core.auth import (
    RefreshResult,
    change_password,
    create_refresh_token,
    create_session,
    create_user,
    get_user_by_id,
    rotate_refresh_token,
    validate_session,
)
from app.core.database import get_db
from app.core.rbac import set_can_write
from app.models.user import Role
from tests.test_web_auth_routes import GOOD_PASSWORD, _init_db, _reset_middleware_state, client

NEW_PASSWORD = "Fresh-pass-2468!"


def _login(client, username: str = "tech") -> dict:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": GOOD_PASSWORD}
    )
    assert response.status_code == 200, response.text
    client.cookies.clear()
    return response.json()


def _refresh(client, refresh_token: str):
    response = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    client.cookies.clear()
    return response


def _me(client, access_token: str) -> int:
    return client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    ).status_code


def _set_cookie_names(response) -> list[str]:
    return [c.split("=", 1)[0] for c in response.headers.get_list("set-cookie")]


async def _technician(username: str = "rotor"):
    return await create_user(username, GOOD_PASSWORD, username, role=Role.technician)


async def _new_session(user) -> tuple[str, str]:
    sid = str(uuid.uuid4())
    refresh = await create_refresh_token(user, sid)
    await create_session(user.id, refresh, session_id=sid)
    return sid, refresh


# ---------------------------------------------------------------------------
# A missing or unusable refresh token is an authentication failure
# ---------------------------------------------------------------------------


def test_refresh_without_any_token_is_401(client):
    """Every page load before login sends this; a 400 read as 'server down'."""
    response = client.post("/api/auth/refresh")
    assert response.status_code == 401, response.text


def test_refresh_with_a_non_object_body_is_401(client):
    response = client.post("/api/auth/refresh", json=["not", "an", "object"])
    assert response.status_code == 401, response.text


def test_refresh_with_a_garbage_token_is_401(client):
    response = client.post("/api/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert response.status_code == 401, response.text


async def test_refresh_token_without_a_session_is_401(client):
    """Such a token can be neither rotated nor revoked, so it is not honoured."""
    user = await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    unbound = await create_refresh_token(user)
    assert _refresh(client, unbound).status_code == 401


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------


async def test_refresh_issues_a_new_refresh_token_and_cookie(client):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    first = _login(client)["refresh_token"]

    response = client.post("/api/auth/refresh", json={"refresh_token": first})
    assert response.status_code == 200, response.text
    second = response.json()["refresh_token"]
    assert second and second != first
    assert {"access_token", "refresh_token"} <= set(_set_cookie_names(response))
    assert client.cookies.get("refresh_token") == second
    client.cookies.clear()

    third = _refresh(client, second)
    assert third.status_code == 200, third.text
    assert _me(client, third.json()["access_token"]) == 200


async def test_a_cookie_refresh_keeps_the_new_refresh_token_out_of_the_body(client):
    """The browser's refresh token is HttpOnly; page script must never receive it."""
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    first = _login(client)["refresh_token"]

    response = client.post("/api/auth/refresh", headers={"Cookie": f"refresh_token={first}"})
    client.cookies.clear()

    assert response.status_code == 200, response.text
    assert "refresh_token" not in response.json()
    rotated = response.cookies.get("refresh_token")
    assert rotated and rotated != first
    assert _refresh(client, rotated).status_code == 200


async def test_a_retired_refresh_token_revokes_the_session(client, monkeypatch):
    """A rotated-out token coming back means two parties hold this session."""
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    original = _login(client)["refresh_token"]
    rotated = _refresh(client, original).json()
    monkeypatch.setattr(auth_mod, "REFRESH_REUSE_GRACE_SECONDS", 0)

    assert _refresh(client, original).status_code == 401
    # Both holders lose it: the legitimate one signs in again, the copy is dead.
    assert _refresh(client, rotated["refresh_token"]).status_code == 401
    assert _me(client, rotated["access_token"]) == 401


async def test_a_late_duplicate_refresh_gets_an_access_token_only(client):
    """Two requests that left the browser with the same cookie both succeed.

    The late one must not hand out a refresh token of its own, and must not
    overwrite the cookie the winning response is setting.
    """
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    original = _login(client)["refresh_token"]
    winner = _refresh(client, original).json()

    late = client.post("/api/auth/refresh", json={"refresh_token": original})
    assert late.status_code == 200, late.text
    assert "refresh_token" not in late.json()
    assert _set_cookie_names(late) == ["access_token"]
    client.cookies.clear()
    assert _me(client, late.json()["access_token"]) == 200

    # The session survived, so the token the winner received still works.
    assert _refresh(client, winner["refresh_token"]).status_code == 200


async def test_grace_covers_only_the_immediately_previous_token(client):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    first = _login(client)["refresh_token"]
    second = _refresh(client, first).json()["refresh_token"]
    third = _refresh(client, second).json()["refresh_token"]

    assert _refresh(client, first).status_code == 401
    assert _refresh(client, third).status_code == 401  # session revoked


async def test_concurrent_refreshes_of_one_token_do_not_revoke_the_session():
    user = await _technician()
    sid, refresh = await _new_session(user)
    replacements = [await create_refresh_token(user, sid) for _ in range(2)]

    results = await asyncio.gather(
        *(rotate_refresh_token(sid, user.id, refresh, r) for r in replacements)
    )

    assert sorted(results) == sorted([RefreshResult.ROTATED, RefreshResult.GRACE])
    assert await validate_session(sid)


async def test_a_refresh_token_for_someone_elses_session_is_invalid():
    sid, _ = await _new_session(await _technician("owner"))
    intruder = await _technician("intruder")
    forged = await create_refresh_token(intruder, sid)

    result = await rotate_refresh_token(sid, intruder.id, forged, forged)

    assert result is RefreshResult.INVALID
    assert await validate_session(sid)  # the owner's session is untouched


async def test_reuse_detection_does_not_trigger_on_a_refused_mfa_check(client):
    """Refusing before rotation keeps a pending MFA proof from burning the token."""
    user = await _technician()
    sid, refresh = await _new_session(user)
    enrollment = await mfa.begin_enrollment(user.id, user.username)
    valid, _ = await mfa.verify(
        user.id, mfa.totp(enrollment["secret"], int(time.time() // 30)), enroll=True
    )
    assert valid

    assert _refresh(client, refresh).status_code == 401
    await mfa.mark_recent(sid)
    assert _refresh(client, refresh).status_code == 200


async def test_access_tokens_survive_rotation_of_their_own_session(client):
    """Rotation replaces the refresh token, not the session the tokens name."""
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    login = _login(client)
    assert _refresh(client, login["refresh_token"]).status_code == 200
    assert _me(client, login["access_token"]) == 200


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------


async def test_changing_your_password_signs_out_every_other_session(client):
    await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    here = _login(client)
    elsewhere = _login(client)

    response = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {here['access_token']}"},
        json={"current_password": GOOD_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.json()["sessions_revoked"] == 1
    client.cookies.clear()

    assert _me(client, elsewhere["access_token"]) == 401
    assert _refresh(client, elsewhere["refresh_token"]).status_code == 401
    # The session that made the change carries on.
    assert _me(client, here["access_token"]) == 200
    assert _refresh(client, here["refresh_token"]).status_code == 200


async def test_a_password_reset_without_a_session_to_keep_revokes_all():
    """The administrator path: nothing the old password opened survives."""
    user = await _technician()
    first, _ = await _new_session(user)
    second, _ = await _new_session(user)

    assert await change_password(user.id, NEW_PASSWORD) == 2

    assert not await validate_session(first)
    assert not await validate_session(second)


# ---------------------------------------------------------------------------
# Granting tenant_write sits behind the existing step-up check
# ---------------------------------------------------------------------------


async def test_granting_tenant_write_requires_a_fresh_step_up(client, monkeypatch):
    setup = client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": GOOD_PASSWORD, "display_name": "Admin"},
    ).json()
    admin_id = setup["user"]["id"]
    await set_can_write(admin_id, True)
    client.headers["Authorization"] = "Bearer " + setup["access_token"]
    timestamp = time.time()
    monkeypatch.setattr(mfa.time, "time", lambda: timestamp)
    secret = client.post("/api/auth/mfa/enroll", json={"password": GOOD_PASSWORD}).json()["secret"]
    confirmed = client.post(
        "/api/auth/mfa/confirm",
        json={"password": GOOD_PASSWORD, "otp": mfa.totp(secret, int(timestamp // 30))},
    )
    assert confirmed.status_code == 200, confirmed.text
    recovery = confirmed.json()["recovery_codes"]
    client.headers["Authorization"] = "Bearer " + client.cookies.get("access_token")
    target = await create_user("target", GOOD_PASSWORD, "Target", role=Role.technician)

    async with get_db() as db:
        await db.execute("UPDATE mfa_stepup SET verified_at=0")
        await db.commit()
    denied = client.put(f"/api/auth/users/{target.id}", json={"tenant_write": True})
    assert denied.status_code == 403
    assert denied.json()["detail"] == "step_up_required"
    assert not (await get_user_by_id(target.id)).tenant_write

    stepped = client.post("/api/auth/step-up", json={"password": GOOD_PASSWORD, "otp": recovery[0]})
    assert stepped.status_code == 200, stepped.text
    granted = client.put(f"/api/auth/users/{target.id}", json={"tenant_write": True})
    assert granted.status_code == 200, granted.text
    assert (await get_user_by_id(target.id)).tenant_write
