"""The migration runner owns the schema; the ORM may only describe it.

Alembic, the SQLModel classes and the runner in app/core/database.py once all
defined the same tables. Only the runner ever executed, so the other two could
drift without anything failing. Alembic is gone; this keeps the ORM honest:
every table and column it names must exist exactly as the runner creates it.
"""

from __future__ import annotations

import importlib
import pkgutil
import sqlite3

import app.models
from app.core import database


async def test_orm_tables_and_columns_match_the_migrated_schema(tmp_path, monkeypatch):
    from sqlmodel import SQLModel

    for module in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module(f"app.models.{module.name}")

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "schema.db")
    await database.run_migrations()
    await database.close_all_pools()

    con = sqlite3.connect(tmp_path / "schema.db")
    try:
        migrated = {
            row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        described = set(SQLModel.metadata.tables)
        assert described <= migrated, (
            f"ORM names tables the runner never creates: {described - migrated}"
        )

        drift = {}
        for table in sorted(described):
            columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
            orm_columns = {c.name for c in SQLModel.metadata.tables[table].columns}
            if columns != orm_columns:
                drift[table] = {
                    "only_in_schema": sorted(columns - orm_columns),
                    "only_in_orm": sorted(orm_columns - columns),
                }
        assert not drift, drift
    finally:
        con.close()
