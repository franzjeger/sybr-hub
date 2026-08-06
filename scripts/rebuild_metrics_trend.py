#!/usr/bin/env python3
"""Rebuild the audit_metrics trend table from the runs it summarises.

``audit_metrics`` is a derived table: one row per audit run, written at the end
of a run so a trend can be charted without re-parsing every artefact. The runs
themselves are the record; this is a cache of them.

It had drifted from them in three ways.

**Duplicates.** A row is inserted both when an audit finishes and when a report
is generated from it, so most runs appear two or three times. Sixty rows for
twenty-one runs.

**Stale readings.** A row holds the figures as the parsers read them on the day.
When a parser is fixed, the row keeps the old answer — including impossible
ones: two rows here recorded MFA coverage of 101.6% and 100.5%, from a bug
since fixed. A trend that mixes readings from before and after a fix does not
describe the tenant; it describes which day each point was parsed on.

**Timestamps.** The row's audit_date is the moment the metrics were saved,
minutes after the run it belongs to, so a row cannot be matched to its run by
time alone.

So the table is rebuilt from ``_audit_metrics.json`` — one row per run, dated
from the run directory, holding whatever the current parsers read from evidence
that has not changed. That is "what we would say now" rather than "what we said
then", which is the only thing a trend can honestly be.

A row matching no surviving run is left alone and reported: the run may have
been cleaned up, and its figures are the last trace of it.

Dry run by default.

    python scripts/rebuild_metrics_trend.py
    python scripts/rebuild_metrics_trend.py --apply
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

COLUMNS = (
    "risk_grade", "risk_score", "mfa_coverage_pct", "secure_score_pct",
    "total_users", "users_no_mfa", "ca_policies_enabled",
    "intune_compliance_pct", "admin_roles_ga_count",
)


def rows_from_runs(audit_root: Path, customer_ids: dict[str, str]) -> list[dict]:
    """One row per run that still has stored metrics, newest last."""
    from app.core.encryption import encrypted_read_json

    out = []
    for customer_dir in sorted(p for p in audit_root.iterdir() if p.is_dir()):
        customer_name = customer_dir.name.replace("_", " ")
        customer_id = customer_ids.get(customer_dir.name, "")
        for run_dir in sorted(p for p in customer_dir.iterdir() if p.is_dir()):
            path = run_dir / "_audit_metrics.json"
            if not path.exists():
                continue
            try:
                metrics = encrypted_read_json(path)
            except Exception as exc:  # a run we cannot read is not a run we can chart
                print(f"  ! {run_dir.name}: unreadable ({exc})")
                continue
            row = {c: metrics.get(c) for c in COLUMNS}
            row.update(
                customer_id=customer_id,
                customer_name=customer_name,
                audit_date=metrics.get("timestamp", ""),
                metrics_json=json.dumps(metrics),
                run=run_dir.name,
            )
            out.append(row)
    return out


def rebuild(db_path: Path, rows: list[dict], apply: bool) -> dict:
    """Replace each customer's rows with one per run; report what is dropped."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = [dict(r) for r in conn.execute(
            "SELECT customer_id, customer_name, audit_date FROM audit_metrics"
        )]
        wanted = {(r["customer_name"], r["audit_date"]) for r in rows}
        customers = {r["customer_name"] for r in rows}
        # Matched on the customer *name*, because that is what links a row to a
        # run: _save_metrics_to_db derives it from the run directory, while
        # customer_id comes from whatever the active config held at the time.
        # Here that is the tenant id, and three different names share it —
        # including two from run directories long since deleted.
        orphans = [e for e in existing if e["customer_name"] not in customers]
        replaced = [
            e for e in existing
            if e["customer_name"] in customers
            and (e["customer_name"], e["audit_date"]) not in wanted
        ]

        if apply:
            for customer_name in customers:
                conn.execute(
                    "DELETE FROM audit_metrics WHERE customer_name = ?", (customer_name,)
                )
            conn.executemany(
                "INSERT INTO audit_metrics (customer_id, customer_name, audit_date, "
                + ", ".join(COLUMNS)
                + ", metrics_json, created_at) VALUES ("
                + ", ".join("?" * (3 + len(COLUMNS) + 2))
                + ")",
                [
                    tuple(
                        [r["customer_id"], r["customer_name"], r["audit_date"]]
                        + [r[c] for c in COLUMNS]
                        + [r["metrics_json"], r["audit_date"]]
                    )
                    for r in rows
                ],
            )
            conn.commit()
        return {"before": len(existing), "after": len(rows),
                "dropped": len(replaced), "left_alone": len(orphans)}
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager
    from app.core.database import DB_PATH

    ids = {}
    for cust in CustomerManager.list_customers():
        real = cust.get("CustomerName", "")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in real)
        ids[safe] = cust.get("TenantId", "") or cust.get("_id", "")

    root = get_audit_dir()
    if not root.is_dir():
        print(f"No audit directory at {root}")
        return 1

    rows = rows_from_runs(root, ids)
    for row in rows:
        print(f"  {row['run']:20} {row['audit_date']:22} "
              f"mfa={row['mfa_coverage_pct']}  no_mfa={row['users_no_mfa']}")

    result = rebuild(DB_PATH, rows, args.apply)
    print(
        f"\n{'Rebuilt' if args.apply else 'Would rebuild'}: {result['before']} row(s) -> "
        f"{result['after']}, dropping {result['dropped']} duplicate or stale row(s). "
        f"{result['left_alone']} row(s) for customers with no runs left untouched."
    )
    if not args.apply:
        print("Dry run — pass --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
