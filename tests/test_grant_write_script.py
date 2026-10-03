"""The key that ships with the lock.

Every account starts read-only and granting is itself a write, so immediately
after the migration there is no way to hand out the first grant through the
interface. This script is the only way in. It is worth a test for that reason
alone.
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib

import pytest

from app.core.auth import create_user, get_user_by_id
from app.core.database import run_migrations
from app.models.user import Role

_spec = importlib.util.spec_from_file_location(
    "grant_write", pathlib.Path("scripts/grant_write.py")
)
grant_write = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(grant_write)

GOOD_PASSWORD = "Str0ng-Passphrase-For-Tests!"


@pytest.fixture(autouse=True)
async def _db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


def _args(**kw):
    base = {"user": None, "list": False, "write": False, "tenant_write": False, "revoke": False}
    return argparse.Namespace(**{**base, **kw})


async def test_a_new_account_starts_without_write():
    """The migration's whole point, seen from outside."""
    user = await create_user("frank", GOOD_PASSWORD, "Frank", role=Role.admin)

    assert (await get_user_by_id(user.id)).can_write is False


async def test_granting_write():
    user = await create_user("frank", GOOD_PASSWORD, "Frank", role=Role.admin)

    assert await grant_write._run(_args(user="frank", write=True)) == 0
    assert (await get_user_by_id(user.id)).can_write is True


async def test_tenant_write_is_refused_without_write():
    """It stands on can_write, so granting it alone would be a contradiction
    the middleware resolves safely and a reader does not."""
    await create_user("frank", GOOD_PASSWORD, "Frank", role=Role.admin)

    assert await grant_write._run(_args(user="frank", tenant_write=True)) == 1


async def test_granting_both_together():
    user = await create_user("frank", GOOD_PASSWORD, "Frank", role=Role.admin)

    assert await grant_write._run(_args(user="frank", write=True, tenant_write=True)) == 0
    refreshed = await get_user_by_id(user.id)
    assert (refreshed.can_write, refreshed.tenant_write) == (True, True)


async def test_revoking_takes_both():
    """Leaving tenant_write set on an account that may not write at all is a
    state no reader should have to reason about."""
    user = await create_user("frank", GOOD_PASSWORD, "Frank", role=Role.admin)
    await grant_write._run(_args(user="frank", write=True, tenant_write=True))

    assert await grant_write._run(_args(user="frank", revoke=True)) == 0
    refreshed = await get_user_by_id(user.id)
    assert (refreshed.can_write, refreshed.tenant_write) == (False, False)


async def test_an_unknown_account_is_named_not_guessed():
    await create_user("frank", GOOD_PASSWORD, "Frank", role=Role.admin)

    assert await grant_write._run(_args(user="franck", write=True)) == 1
