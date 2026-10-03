#!/usr/bin/env python3
"""Offline purge of a retired customer's primary local records.

Dry-run by default. Stop the hub first. Backups, exported copies and shared
activity logs have independent retention; this command does not erase them.
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("customer_id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--service-stopped", action="store_true")
    args = parser.parse_args()
    from app.core.config import DATA_DIR, get_audit_dir, get_cert_dir
    from app.core.customer import CustomerManager, _validate_customer_id
    from app.core.database import DB_PATH
    from app.core.encryption import encrypted_read_json

    cid = args.customer_id
    _validate_customer_id(cid)
    if CustomerManager.get_customer(cid):
        parser.error("Retire the customer registration first")
    retired = DATA_DIR / "retired_customers" / cid
    if not (retired / "config.json").exists():
        parser.error("No retired registration with that ID")
    config = encrypted_read_json(retired / "config.json")
    name = config.get("CustomerName", cid)
    if not isinstance(name, str) or not name.strip():
        parser.error("Invalid legacy customer name; reconcile its audit paths manually")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    for customer in CustomerManager.list_customers():
        other = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in customer.get("CustomerName", "")
        )
        if other == safe_name:
            parser.error(
                "Another active customer shares this legacy audit directory; reconcile manually"
            )
    paths = list(
        dict.fromkeys(
            [
                retired,
                get_audit_dir() / safe_name,
                get_audit_dir() / cid,
                get_cert_dir() / f"{cid}.pfx",
            ]
        )
    )
    paths = [p for p in paths if p.exists()]
    with sqlite3.connect(DB_PATH) as db:
        db.execute("PRAGMA foreign_keys=ON")
        references = []
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            identifier = '"' + table.replace('"', '""') + '"'
            columns = {r[1] for r in db.execute(f"PRAGMA table_info({identifier})")}
            for column in ("customer_id", "local_customer_id"):
                if column in columns:
                    count = db.execute(
                        f"SELECT COUNT(*) FROM {identifier} WHERE {column}=?", (cid,)
                    ).fetchone()[0]
                    references.append((identifier, column, count))
        print(
            json.dumps(
                {
                    "customer_id": cid,
                    "paths": [str(p) for p in paths],
                    "rows": references,
                    "retained": [
                        "backups",
                        "shared activity log",
                        "exported copies",
                        "shared SSH keys",
                        "provider data",
                    ],
                },
                indent=2,
            )
        )
        if not args.apply:
            return
        if args.confirm != cid or not args.service_stopped:
            parser.error("Applying requires --confirm CUSTOMER_ID and --service-stopped")
        moved = []
        db.execute("BEGIN IMMEDIATE")
        db.execute("PRAGMA defer_foreign_keys=ON")
        try:
            for path in paths:
                target = path.with_name(".sybr-purge-" + uuid.uuid4().hex)
                os.rename(path, target)
                moved.append((path, target))
            for table, column, _count in references:
                db.execute(f"DELETE FROM {table} WHERE {column}=?", (cid,))
            db.commit()
        except BaseException:
            db.rollback()
            for source, staged in reversed(moved):
                os.rename(staged, source)
            raise
        for _source, staged in moved:
            if staged.is_dir():
                shutil.rmtree(staged)
            else:
                staged.unlink()
        print(
            "Primary customer records purged. Complete the separate retention checks in docs/RETENTION.md."
        )


if __name__ == "__main__":
    main()
