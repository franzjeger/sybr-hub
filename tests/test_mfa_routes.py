import time
import uuid

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core import mfa
from app.core.auth import create_access_token, create_refresh_token, create_session, get_user_by_id
from app.core.database import get_db
from app.core.rbac import set_can_write
from tests.test_web_auth_routes import GOOD_PASSWORD, _init_db, _reset_middleware_state, client


async def test_enrollment_login_and_sensitive_action_step_up(client, monkeypatch):
    setup = client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": GOOD_PASSWORD, "display_name": "Admin"},
    ).json()
    client.headers["Authorization"] = "Bearer " + setup["access_token"]
    await set_can_write(setup["user"]["id"], True)
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
    assert len(recovery) == 10
    assert client.get("/api/encryption/key-backup").status_code == 200
    async with get_db() as db:
        await db.execute("UPDATE mfa_stepup SET verified_at=0")
        await db.commit()
    denied = client.get("/api/encryption/key-backup")
    assert denied.status_code == 403
    assert denied.json()["detail"] == "step_up_required"
    assert (
        client.post(
            "/api/auth/step-up", json={"password": GOOD_PASSWORD, "otp": recovery[0]}
        ).status_code
        == 200
    )
    assert client.get("/api/encryption/key-backup").status_code == 200
    client.post("/api/auth/logout")
    client.headers.pop("Authorization", None)
    assert (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": GOOD_PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": GOOD_PASSWORD, "otp": recovery[1]},
        ).status_code
        == 200
    )


def test_required_mfa_keeps_enrollment_reachable_but_blocks_customer_features(client, monkeypatch):
    @client.app.get("/api/legacy-protected-route")
    async def legacy_route():
        return {"value": "authenticated route without a user dependency"}

    setup = client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": GOOD_PASSWORD, "display_name": "Admin"},
    ).json()
    client.headers["Authorization"] = "Bearer " + setup["access_token"]
    monkeypatch.setenv("SYBR_REQUIRE_MFA", "1")
    assert client.get("/api/auth/me").json()["mfa_required"]
    assert client.get("/api/customers").status_code == 403
    assert client.get("/api/legacy-protected-route").status_code == 403
    enrollment = client.post("/api/auth/mfa/enroll", json={"password": GOOD_PASSWORD})
    assert enrollment.status_code == 200


async def test_session_created_after_enrollment_still_requires_its_own_mfa_proof(client):
    setup = client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": GOOD_PASSWORD, "display_name": "Admin"},
    ).json()
    user = await get_user_by_id(setup["user"]["id"])
    enrollment = await mfa.begin_enrollment(user.id, user.username)
    valid, _ = await mfa.verify(
        user.id, mfa.totp(enrollment["secret"], int(time.time() // 30)), enroll=True
    )
    assert valid
    # Model a password-only login that checked MFA before enrollment and then
    # issued its session after enrollment had already revoked the old sessions.
    sid = str(uuid.uuid4())
    access = await create_access_token(user, sid)
    refresh = await create_refresh_token(user, sid)
    await create_session(user.id, refresh, session_id=sid)
    client.headers["Authorization"] = "Bearer " + access
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": refresh}).status_code == 401
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/api/ws/dashboard?token=" + access, headers={"origin": "http://testserver"}
        ),
    ):
        pytest.fail("Unverified MFA session accepted")
    await mfa.mark_recent(sid)
    assert client.get("/api/auth/me").status_code == 200
