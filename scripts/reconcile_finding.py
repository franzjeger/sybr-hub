#!/usr/bin/env python3
"""Reconcile an uncertain remote write after checking the provider manually.

Default: print pending/unknown operation IDs. Applying requires a stopped hub.
No request is ever made to an external ticket system by this command.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation")
    outcome = parser.add_mutually_exclusive_group()
    outcome.add_argument("--external-id")
    outcome.add_argument("--confirmed-no-remote-object", action="store_true")
    parser.add_argument("--service-stopped", action="store_true")
    args = parser.parse_args()
    from app.core.database import DB_PATH

    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        if not args.operation:
            for row in db.execute(
                "SELECT operation_id, system, status, created_at FROM finding_operations WHERE status!='succeeded'"
            ):
                print(dict(row))
            return
        if not args.service_stopped or not (args.external_id or args.confirmed_no_remote_object):
            parser.error(
                "Stop the hub, verify the provider outcome, and supply --service-stopped and an outcome"
            )
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM finding_operations WHERE operation_id=? AND status!='succeeded'",
            (args.operation,),
        ).fetchone()
        if row is None:
            parser.error("No unresolved operation with that ID")
        ticket = db.execute(
            "SELECT external_id FROM finding_tickets WHERE customer_id=? AND rec_id=? AND system=?",
            (row["customer_id"], row["rec_id"], row["system"]),
        ).fetchone()
        if ticket and ticket[0] != args.external_id:
            parser.error("An existing ticket conflicts with this outcome; nothing changed")
        if args.external_id:
            db.execute(
                """INSERT INTO finding_tickets(customer_id,rec_id,system,external_id,title,created_at,created_by)
                          VALUES (?,?,?,?,?,?,?) ON CONFLICT(customer_id,rec_id,system) DO NOTHING""",
                (
                    row["customer_id"],
                    row["rec_id"],
                    row["system"],
                    args.external_id,
                    "Reconciled external operation",
                    row["created_at"],
                    "offline-reconciliation",
                ),
            )
            db.execute(
                "UPDATE finding_operations SET status='succeeded' WHERE operation_id=?",
                (args.operation,),
            )
        else:
            db.execute("DELETE FROM finding_operations WHERE operation_id=?", (args.operation,))
        db.commit()
        print("Reconciled", args.operation)


if __name__ == "__main__":
    main()
