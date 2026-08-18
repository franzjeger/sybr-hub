"""The non-interactive service principal owns unattended work.

Everything the hub does on its own — scheduled audits, backups, alert sweeps,
the VPN tunnels the collectors hold — is attributed to one account, ``sybr-system``.
This file pins the properties that make that safe rather than dangerous:

* it exists by the time the schedulers start,
* its actions are attributed to it and are distinguishable from a human's,
* a manual "run now" is still logged under the person who clicked it,
* it can never log in, and
* attributing work to it cannot narrow the set of customers that work touches
  (it can see every customer), so the audit trail change is not a scope change.

The privilege-concentration tradeoff is deliberate and bounded: one identity
owns every tunnel and runs every job, but it holds only the capabilities those
jobs need (can_write, not tenant_write), and it cannot be turned into a login.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import system_user
from app.core.auth import authenticate, change_password, get_user_by_username
from app.core.database import run_migrations
from app.core.rbac import get_accessible_customer_ids
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app


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
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


# ── It exists before the schedulers run ───────────────────────────────────────

async def test_startup_creates_a_usable_service_account():
    """Entering the TestClient context runs the app's startup lifespan, which
    calls ensure() before the schedulers start."""
    with TestClient(create_app()):
        pass
    account = await system_user.get()
    assert account is not None, "startup did not create the system account"
    # Exactly the capabilities the background jobs need, and no more.
    assert account.is_system is True
    assert account.all_customers is True
    assert account.can_write is True
    assert account.tenant_write is False, (
        "nothing running unattended should be able to change a customer's tenant"
    )
    assert account.role == Role.technician


async def test_ensuring_it_twice_is_idempotent():
    first = await system_user.ensure()
    second = await system_user.ensure()
    assert first.id == second.id


# ── Its actions are attributed to it, and tell apart from a human's ───────────

async def test_scheduled_work_is_logged_under_the_service_account():
    from app.core.activity_log import get_activity_log
    from app.core.scheduler import AuditScheduler

    await system_user.ensure()
    AuditScheduler._log_activity("audit_completed", "nightly-attribution-probe", "Acme")

    entry = next(
        (e for e in get_activity_log(limit=20)
         if e["detail"] == "nightly-attribution-probe"),
        None,
    )
    assert entry is not None, "the scheduler wrote nothing to the activity log"
    assert entry["user"] == system_user.USERNAME
    assert entry["action"] == "audit_completed"


async def test_the_actor_is_distinguishable_from_a_human_admin():
    from app.core.auth import create_user

    system = await system_user.ensure()
    human = await create_user("alice", "Str0ng-Passphrase!1", "Alice", role=Role.admin)

    # Same activity-log field, but the actor resolves to an is_system row for the
    # service account and a human row for the person — the log can always say
    # which did a thing.
    assert (await get_user_by_username(system.username)).is_system is True
    assert (await get_user_by_username(human.username)).is_system is False


async def test_a_manual_run_is_logged_under_the_person_not_the_system(monkeypatch):
    from app.core.activity_log import get_activity_log
    from app.services import scheduler as task_scheduler

    await system_user.ensure()

    async def _noop():
        return "ok"

    # Replace a real task with a no-op so the test does no work; restored by
    # monkeypatch so the global runner table is not mutated for other tests.
    monkeypatch.setitem(task_scheduler._TASK_RUNNERS, "db_cleanup", _noop)
    await task_scheduler.run_now("db_cleanup", actor="alice")

    entry = next(
        (e for e in get_activity_log(limit=20)
         if e["action"] == "task_db_cleanup_manual"),
        None,
    )
    assert entry is not None, "the manual run wrote nothing"
    assert entry["user"] == "alice", (
        "a human 'run now' must not be hidden behind the system account"
    )


# ── It can never become a login ───────────────────────────────────────────────

async def test_the_service_account_cannot_sign_in_even_with_a_known_password():
    await system_user.ensure()
    # Force a password we know onto it — the only way in would be if authenticate
    # forgot the is_system refusal.
    account = await get_user_by_username(system_user.USERNAME)
    await change_password(account.id, "Kn0wn-Passphrase-Attempt!")
    assert await authenticate(system_user.USERNAME, "Kn0wn-Passphrase-Attempt!") is None


# ── Attribution does not narrow the customer set (no-regression argument) ──────

async def test_the_system_account_does_not_close_first_run_setup():
    """It is created at startup, so it must not make a fresh install look set up.

    First-run counts humans: with only the system account present, setup is
    still required and create_initial_admin still works — otherwise the account
    that runs before any human would lock everyone out of their own hub.
    """
    from app.core.auth import create_initial_admin, get_user_count

    await system_user.ensure()
    assert await get_user_count() == 0, "the system account was counted as a human"

    admin = await create_initial_admin("boss", "Str0ng-Passphrase!1", "Boss")
    assert admin.role == Role.admin
    assert await get_user_count() == 1


async def test_the_principal_can_see_every_customer():
    """Background jobs iterate the full customer list; attributing them to this
    principal cannot regress that, because its scope is unrestricted.

    get_accessible_customer_ids returns None for "no restriction". If any job is
    ever routed through the principal's scope, None keeps it covering every
    customer — the same set it covers today.
    """
    account = await system_user.ensure()
    assert await get_accessible_customer_ids(account) is None
