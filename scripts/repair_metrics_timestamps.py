#!/usr/bin/env python3
"""Restore each run's metrics timestamp from its directory name.

build_report_context ends by saving the metrics it computed, stamped with the
current time. Any tool that rebuilt a context in order to *read* an old run
therefore rewrote that run's timestamp to the moment it was read — which a
maintenance script walking every run did to all of them at once.

The run directory is the authority: make_output_dir names it
``%Y-%m-%d_%H%M`` in UTC, so the correct value can be reconstructed exactly,
to the minute. Seconds are lost and never meant anything for a run.

Only the timestamp field is touched. Dry run by default.

    python scripts/repair_metrics_timestamps.py
    python scripts/repair_metrics_timestamps.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RUN_NAME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})$")


def timestamp_from_run_name(name: str) -> str | None:
    """The run's own name, as the timestamp it should carry."""
    m = RUN_NAME.match(name)
    if not m:
        return None
    y, mo, d, h, mi = (int(x) for x in m.groups())
    try:
        return datetime(y, mo, d, h, mi, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def repair_run(run_dir: Path, apply: bool) -> tuple[str, str] | None:
    """Return (stored, correct) when they disagree, else None."""
    from app.core.encryption import encrypted_read_json, encrypted_write_json

    path = run_dir / "_audit_metrics.json"
    correct = timestamp_from_run_name(run_dir.name)
    if not correct or not path.exists():
        return None
    metrics = encrypted_read_json(path)
    stored = str(metrics.get("timestamp", ""))
    if stored == correct:
        return None
    if apply:
        metrics["timestamp"] = correct
        encrypted_write_json(path, metrics)
    return stored, correct


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from app.core.config import get_audit_dir

    root = get_audit_dir()
    if not root.is_dir():
        print(f"No audit directory at {root}")
        return 1

    changed = 0
    for customer_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        print(f"\n=== {customer_dir.name} ===")
        for run_dir in sorted(p for p in customer_dir.iterdir() if p.is_dir()):
            result = repair_run(run_dir, args.apply)
            if result:
                changed += 1
                print(f"  {run_dir.name}: {result[0]!r} -> {result[1]!r}")

    print(f"\n{'Repaired' if args.apply else 'Would repair'} {changed} run(s).")
    if not args.apply:
        print("Dry run — pass --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
