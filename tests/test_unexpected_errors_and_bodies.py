"""An unexpected error must answer with something, and a body must have a shape.

Two failures with one cause: the route layer reads ``await request.json()`` in
about a hundred places and indexes straight into the result, and ``create_app``
only registered a handler for ``ToolkitError``. So a JSON list where a dict was
expected raised ``AttributeError`` inside the handler and fell through to
Starlette's default — a bare 500 with no id, nothing logged that ties it to the
request, and a body that depends on how the server happened to be started.

The scheduler was the worst of them: ``settings["scheduler"] = body`` persisted
whatever arrived, so a malformed request left its wreckage in the settings file
for the next tick to read.

``raise_server_exceptions=False`` below is not a workaround. Starlette's
``ServerErrorMiddleware`` re-raises after the handler returns, so the default
``True`` shows the test the original exception rather than the response the
client would receive. These tests are about the response, so they ask for it.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.models.user import Role, User
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app


@pytest.fixture(autouse=True)
def _reset_middleware_state():
    import app.web.middleware.rate_limit as rl

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


@pytest.fixture()
async def admin() -> User:
    user = await create_user(
        username="boss",
        password="Test1234!xyz",
        display_name="Boss",
        role=Role.admin,
    )
    # can_write is a grant nobody inherits, admins included — see
    # middleware/write_guard.py. Without it every POST below is a 403.
    from app.core.auth import get_user_by_id
    from app.core.rbac import set_can_write

    await set_can_write(user.id, True)
    return await get_user_by_id(user.id)


@pytest.fixture()
async def admin_token(admin) -> str:
    return await create_access_token(admin)


@pytest.fixture()
async def admin_client(admin_token):
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers.update({"Authorization": f"Bearer {admin_token}"})
        yield c


def _app_with_route(router: APIRouter):
    app = create_app()
    app.include_router(router, prefix="/api")
    return app


# ── The catch-all handler ────────────────────────────────────────────────────

async def test_an_unexpected_error_gets_a_shaped_response(admin_token):
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise AttributeError("'list' object has no attribute 'get'")

    with TestClient(_app_with_route(router), raise_server_exceptions=False) as c:
        r = c.get("/api/boom", headers={"Authorization": f"Bearer {admin_token}"})

    assert r.status_code == 500
    body = r.json()
    assert body["ok"] is False
    assert body["error_type"] == "internal_error"
    assert body["error_id"]


async def test_the_response_does_not_carry_the_exception_text(admin_token):
    """The id goes in the log; the client gets nothing to leak.

    An exception message routinely quotes the call that failed, and the calls
    that fail here carry API tokens and passwords.
    """
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise RuntimeError("connect failed for token=9xQhZ3mNbVcXwErTyUiOpAsDfGhJkL2z")

    with TestClient(_app_with_route(router), raise_server_exceptions=False) as c:
        r = c.get("/api/boom", headers={"Authorization": f"Bearer {admin_token}"})

    assert "9xQhZ3mNbVcXwErTyUiOpAsDfGhJkL2z" not in r.text
    assert "RuntimeError" not in r.text
    assert "Traceback" not in r.text


async def test_the_error_id_is_in_the_log_line(caplog, admin_token):
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise RuntimeError("nope")

    auth = {"Authorization": f"Bearer {admin_token}"}
    with caplog.at_level("ERROR"), \
            TestClient(_app_with_route(router), raise_server_exceptions=False) as c:
        error_id = c.get("/api/boom", headers=auth).json()["error_id"]

    assert error_id in caplog.text, "an id nobody can look up is not an id"


async def test_the_logged_exception_text_is_redacted(caplog, admin_token):
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise RuntimeError("secret=9xQhZ3mNbVcXwErTyUiOpAsDfGhJkL2z")

    auth = {"Authorization": f"Bearer {admin_token}"}
    with caplog.at_level("ERROR"), \
            TestClient(_app_with_route(router), raise_server_exceptions=False) as c:
        c.get("/api/boom", headers=auth)

    # The formatted message is redacted. The traceback below it is not — that
    # is the diagnostic, and Python does not put locals in it.
    message = next(
        r.getMessage() for r in caplog.records if "500 unhandled" in r.getMessage()
    )
    assert "9xQhZ3mNbVcXwErTyUiOpAsDfGhJkL2z" not in message


async def test_a_toolkit_error_still_gets_its_own_status(admin_token):
    """The new handler must not swallow the one that was already right."""
    router = APIRouter()

    @router.get("/bad")
    async def bad():
        from app.core.exceptions import ValidationError

        raise ValidationError("Ugyldig verdi")

    with TestClient(_app_with_route(router), raise_server_exceptions=False) as c:
        r = c.get("/api/bad", headers={"Authorization": f"Bearer {admin_token}"})

    assert r.status_code == 400
    assert r.json()["error"] == "Ugyldig verdi"


# ── The bodies that persist what they are given ──────────────────────────────

async def test_a_list_body_is_a_400_not_a_500(admin_client):
    """The concrete crash: `body.get("enabled")` on a JSON list."""
    r = admin_client.post("/api/scheduler", json=[1, 2, 3])
    assert r.status_code == 422


async def test_an_unknown_scheduler_key_is_refused(admin_client):
    """It used to be stored forever and silently do nothing."""
    r = admin_client.post(
        "/api/scheduler",
        json={"enabled": True, "intervall_timer": 24},
    )
    assert r.status_code == 422


async def test_a_rejected_scheduler_body_changes_nothing(admin_client):
    """The persist happened before any check, so a bad body left wreckage."""
    before = admin_client.get("/api/scheduler").json()

    admin_client.post("/api/scheduler", json={"enabled": "yes please", "junk": {}})

    assert admin_client.get("/api/scheduler").json() == before


async def test_a_valid_scheduler_body_is_still_accepted(admin_client):
    r = admin_client.post(
        "/api/scheduler",
        json={
            "enabled": False,
            "interval_hours": 24,
            "audit_all_customers": True,
            "webhook_url": "https://example.no/hook",
            "alert_on": {"audit_completed": True, "risk_score_drop": 10},
        },
    )
    assert r.status_code == 200, r.text
    stored = admin_client.get("/api/scheduler").json()
    assert stored["interval_hours"] == 24
    assert stored["alert_on"]["risk_score_drop"] == 10


async def test_false_still_means_alert_disabled(admin_client):
    """`False` and `0` are different answers and the scheduler reads both."""
    r = admin_client.post(
        "/api/scheduler",
        json={"enabled": False, "alert_on": {"risk_score_drop": False}},
    )
    assert r.status_code == 200, r.text
    stored = admin_client.get("/api/scheduler").json()
    assert stored["alert_on"]["risk_score_drop"] is False


async def test_an_out_of_range_interval_is_refused(admin_client):
    r = admin_client.post("/api/scheduler", json={"enabled": True, "interval_hours": 0})
    assert r.status_code == 422


async def test_an_unparseable_task_time_is_refused(admin_client):
    """It used to be stored and fail later, disconnected from this request.

    A real task id, because the handler skips ids it does not know — aiming at
    a made-up one would have this test passing against no validation at all.
    """
    r = admin_client.post(
        "/api/scheduler/tasks/config",
        json={"uniweb_sync": {"time": "25:99"}},
    )
    assert r.status_code in (400, 422)


async def test_a_valid_task_time_is_still_accepted(admin_client):
    r = admin_client.post(
        "/api/scheduler/tasks/config",
        json={"uniweb_sync": {"enabled": True, "time": "04:30"}},
    )
    assert r.status_code == 200, r.text

    # Read the persisted config rather than the status list: what matters is
    # that the value survived validation and was written, not how the status
    # endpoint happens to render it.
    from app.services.scheduler import get_task_scheduler_config

    assert get_task_scheduler_config()["uniweb_sync"]["time"] == "04:30"


async def test_a_list_body_to_the_task_scheduler_is_not_a_500(admin_client):
    r = admin_client.post("/api/scheduler/tasks/config", json=["nope"])
    assert r.status_code in (400, 422)


async def test_a_bad_language_is_refused(admin_client):
    r = admin_client.post("/api/settings/language", json={"language": "de"})
    assert r.status_code == 422


async def test_a_good_language_is_accepted(admin_client):
    r = admin_client.post("/api/settings/language", json={"language": "en"})
    assert r.status_code == 200
    assert r.json()["language"] == "en"
