"""Migration 30 removes what the server-side "active customer" left on disk.

The server used to keep one selected customer per user in
customers/.active/<SHA-256 of the user id>.txt, and customers/active.txt
outside a web request. The selection is gone (every tab of a user shared it),
but its files stayed, each naming the customer somebody last opened. These
tests hold the clean-up to exactly those paths: it must never take a
customer's own files, a file it does not recognise, or a customer whose id
happens to be ".active", and running it twice must change nothing more.
"""

from __future__ import annotations

import hashlib
import logging

import pytest

import app.core.customer as customer_module
from app.core import database


def _selection_name(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest() + ".txt"


@pytest.fixture
def customers(tmp_path, monkeypatch):
    root = tmp_path / "customers"
    root.mkdir()
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", root)
    return root


@pytest.fixture
async def at_version_29(tmp_path, monkeypatch, customers):
    """A database migrated to 29, so the next run applies 30 as an upgrade does."""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "upgrade.db")
    await database.run_migrations()
    async with database.get_db() as conn:
        await conn.execute("UPDATE schema_version SET version = 29 WHERE id = 1")
        await conn.commit()


def _tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


async def test_the_upgrade_removes_the_selection_files_and_nothing_else(
    at_version_29, customers, caplog
):
    (customers / "active.txt").write_bytes(b"encrypted id")
    selections = customers / ".active"
    selections.mkdir()
    for user in ("first-user", "second-user"):
        (selections / _selection_name(user)).write_bytes(b"encrypted id")
    acme = customers / "Acme"
    acme.mkdir()
    (acme / "config.json").write_text("{}")
    # Named like the old file, but inside a customer: the customer's, not ours.
    (acme / "active.txt").write_text("notes")

    with caplog.at_level(logging.INFO, logger="app.core.database"):
        await database.run_migrations()

    assert _tree(customers) == ["Acme", "Acme/active.txt", "Acme/config.json"]
    removed = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Removed")]
    assert len(removed) == 4, removed  # active.txt, two selections, the empty folder
    async with database.get_db() as conn, conn.execute("SELECT version FROM schema_version") as cur:
        assert (await cur.fetchone())[0] == database.SCHEMA_VERSION


async def test_it_leaves_what_it_does_not_recognise_and_says_so(at_version_29, customers, caplog):
    selections = customers / ".active"
    selections.mkdir()
    (selections / _selection_name("someone")).write_bytes(b"encrypted id")
    (selections / "notes.txt").write_text("somebody put this here")
    (selections / "subfolder").mkdir()
    (customers / "active.txt").mkdir()  # a folder by that name is not the old file

    with caplog.at_level(logging.INFO, logger="app.core.database"):
        await database.run_migrations()

    assert _tree(customers) == [".active", ".active/notes.txt", ".active/subfolder", "active.txt"]
    left = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Left")]
    assert len(left) == 3, left


async def test_a_selection_named_symlink_is_left_and_its_target_kept(customers, tmp_path):
    target = tmp_path / "elsewhere.txt"
    target.write_text("not ours")
    selections = customers / ".active"
    selections.mkdir()
    (selections / _selection_name("someone")).symlink_to(target)
    (customers / "active.txt").symlink_to(target)

    await database._remove_active_customer_selections(None)

    assert target.read_text() == "not ours"
    assert (customers / "active.txt").is_symlink()
    assert (selections / _selection_name("someone")).is_symlink()


async def test_a_customer_whose_id_is_dot_active_is_not_touched(customers):
    folder = customers / ".active"
    folder.mkdir()
    (folder / "config.json").write_text("{}")
    (folder / _selection_name("someone")).write_bytes(b"customer data")

    await database._remove_active_customer_selections(None)

    assert _tree(customers) == sorted(
        [".active", ".active/config.json", f".active/{_selection_name('someone')}"]
    )


async def test_running_it_again_changes_nothing(customers, caplog):
    (customers / "active.txt").write_bytes(b"encrypted id")
    (customers / ".active").mkdir()
    (customers / ".active" / _selection_name("someone")).write_bytes(b"encrypted id")
    (customers / "Acme").mkdir()
    (customers / "Acme" / "config.json").write_text("{}")

    await database._remove_active_customer_selections(None)
    after_first = _tree(customers)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.core.database"):
        await database._remove_active_customer_selections(None)

    assert _tree(customers) == after_first == ["Acme", "Acme/config.json"]
    assert caplog.records == []


async def test_a_fresh_install_has_nothing_to_remove(customers, caplog):
    with caplog.at_level(logging.INFO, logger="app.core.database"):
        await database._remove_active_customer_selections(None)
    assert _tree(customers) == []
    assert caplog.records == []
