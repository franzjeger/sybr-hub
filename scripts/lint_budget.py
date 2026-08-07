#!/usr/bin/env python3
"""Make the lint debt one-way instead of permanent.

`ruff check` reports about a thousand findings in this repository, nearly all
of them inherited. CI runs it with `continue-on-error` for a stated reason: the
alternative was a lockstep reformat that would bury every real change under
whitespace for a month. That reasoning is sound and its consequence is that
nothing stops the number going up.

So it is a budget rather than a gate. Two numbers are recorded — the total, and
the set of files that are already clean — and both may only improve:

* the total may fall and never rise;
* a file at zero stays at zero, so **anything written from today is clean**
  even while the inherited debt is paid down slowly.

The second is the one that matters. A single total lets a new file arrive with
twenty findings as long as somebody happened to fix twenty elsewhere, which is
how a ratchet stops ratcheting.

    python scripts/lint_budget.py            # check
    python scripts/lint_budget.py --update   # record an improvement
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from collections import Counter

BUDGET_FILE = pathlib.Path(__file__).parent.parent / "lint_budget.json"


def current() -> tuple[int, dict[str, int]]:
    """Ruff's findings now, as a total and a per-file count."""
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format=json", "."],
        capture_output=True,
        text=True,
        cwd=BUDGET_FILE.parent,
    )
    if proc.returncode not in (0, 1):
        raise SystemExit(f"ruff could not run:\n{proc.stderr.strip()}")
    findings = json.loads(proc.stdout or "[]")
    per_file = Counter(
        str(pathlib.Path(f["filename"]).relative_to(BUDGET_FILE.parent))
        for f in findings
    )
    return len(findings), dict(per_file)


def _tracked_files() -> set[str]:
    """Python files git knows about, so a stray venv cannot look like progress."""
    proc = subprocess.run(
        ["git", "ls-files", "*.py"], capture_output=True, text=True, cwd=BUDGET_FILE.parent
    )
    return {line for line in proc.stdout.splitlines() if line}


def load_budget() -> dict:
    """Separate from check() so a test can supply one without a temp file."""
    return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))


def check() -> int:
    total, per_file = current()
    budget = load_budget()
    tracked = _tracked_files()
    clean_before = set(budget["clean_files"]) & tracked

    dirtied = sorted(f for f in clean_before if per_file.get(f, 0) > 0)
    failed = False

    if dirtied:
        failed = True
        print("Files that were clean and no longer are:")
        for name in dirtied:
            print(f"  {name}: {per_file[name]} finding(s)")
        print("\nNew code is expected to be clean. Run `ruff check --fix` on these.")

    if total > budget["total"]:
        failed = True
        print(f"\nTotal findings rose from {budget['total']} to {total}.")

    if failed:
        return 1

    clean_now = {f for f in tracked if per_file.get(f, 0) == 0}
    newly_clean = sorted(clean_now - set(budget["clean_files"]))

    if total < budget["total"] or newly_clean:
        parts = []
        if total < budget["total"]:
            parts.append(f"{budget['total']} -> {total} finding(s)")
        if newly_clean:
            parts.append(f"{len(newly_clean)} newly clean file(s)")
        print(
            f"Lint debt improved: {', '.join(parts)}. "
            f"Run `python scripts/lint_budget.py --update` to record it."
        )
    else:
        print(f"Lint debt unchanged at {total}.")
    return 0


def update() -> int:
    """Record an improvement — and refuse to record anything else.

    Without this, the command that maintains the ratchet is the one that
    undoes it: run --update after dirtying a file and the new, worse state
    becomes the baseline. It happened within an hour of the budget existing.
    """
    if check() != 0:
        print("\nRefusing to record a worse state. Fix the above, then update.")
        return 1

    total, per_file = current()
    tracked = _tracked_files()
    clean = sorted(f for f in tracked if per_file.get(f, 0) == 0)
    BUDGET_FILE.write_text(
        json.dumps({"total": total, "clean_files": clean}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Recorded: {total} findings, {len(clean)} clean file(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()
    return update() if args.update else check()


if __name__ == "__main__":
    raise SystemExit(main())
