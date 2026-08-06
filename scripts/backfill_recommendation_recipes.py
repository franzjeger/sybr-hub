#!/usr/bin/env python3
"""Add the translation recipe to recommendations stored before it existed.

A recommendation used to be stored as its finished sentence, so a run collected
in Norwegian showed Norwegian to an English reader forever. Runs from now on
carry the key and params they were built from and can be re-rendered on the
way out; runs from before carry nothing, and fall back to their stored words.

This gives those runs the recipe too, without re-auditing the tenant: the
recommendations are a pure function of the audit files already on disk, so
rebuilding the report context from a run directory produces the same
recommendations with the recipe attached.

**The stored wording is kept.** Only ``rec_id`` and the four recipe fields are
added, matched to the stored entries by title. An audit run is a record of what
we found and said on a day, and rewriting its sentences to whatever today's
code would phrase them is not a backfill — it is an edit of the record. If a
stored recommendation cannot be matched, it is left exactly as it is and
reported here.

Dry run by default. Pass --apply to write.

    python scripts/backfill_recommendation_recipes.py            # report only
    python scripts/backfill_recommendation_recipes.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RECIPE_FIELDS = ("rec_id", "title_key", "title_params", "detail_key", "detail_params")


def _rebuild(run_dir: Path, customer_name: str, lang: str) -> list[dict]:
    """The recommendations this run's files produce under today's code."""
    from app.reports.generator import build_report_context

    # persist_metrics=False is what makes a dry run dry. Without it this
    # rebuild *is* a write: build_report_context ends by saving the metrics it
    # just computed, so walking every run to inspect it rewrote all of them.
    context = build_report_context(
        customer_name, "", run_dir, [], lang=lang, persist_metrics=False
    )
    return context.get("recommendations", []) or []


def backfill_run(run_dir: Path, customer_name: str, lang: str, apply: bool) -> dict:
    from app.core.encryption import encrypted_read_json, encrypted_write_json

    path = run_dir / "_audit_metrics.json"
    metrics = encrypted_read_json(path)
    stored = metrics.get("recommendations") or []
    if not stored:
        return {"run": run_dir.name, "stored": 0, "matched": 0, "already": 0, "unmatched": []}

    already = sum(1 for r in stored if r.get("title_key"))
    if already == len(stored):
        return {"run": run_dir.name, "stored": len(stored), "matched": 0,
                "already": already, "unmatched": []}

    rebuilt = _rebuild(run_dir, customer_name, lang)
    # Matched on the rendered title: it is what both sides have in common, and
    # a title that no longer renders the same way is exactly the case where
    # guessing would be wrong.
    by_title: dict[str, dict] = {}
    for rec in rebuilt:
        by_title.setdefault(str(rec.get("title", "")), rec)

    matched, unmatched = 0, []
    for rec in stored:
        if rec.get("title_key"):
            continue
        source = by_title.get(str(rec.get("title", "")))
        if not source:
            unmatched.append(str(rec.get("title", ""))[:70])
            continue
        for field in RECIPE_FIELDS:
            rec[field] = source.get(field, "" if field.endswith("key") or field == "rec_id" else {})
        matched += 1

    if apply and matched:
        encrypted_write_json(path, metrics)

    return {"run": run_dir.name, "stored": len(stored), "matched": matched,
            "already": already, "unmatched": unmatched}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write; otherwise report only")
    parser.add_argument("--lang", default="no", help="language the runs were collected in")
    args = parser.parse_args()

    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager

    # The audit tree is named after the customer, with anything unusual folded
    # to an underscore. Recovering the real name matters: the report context
    # takes it, and a recommendation can quote it.
    names = {}
    for cust in CustomerManager.list_customers():
        real = cust.get("CustomerName", "")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in real)
        names[safe] = real

    root = get_audit_dir()
    if not root.is_dir():
        print(f"No audit directory at {root}")
        return 1

    total_matched = total_unmatched = 0
    for customer_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        customer_name = names.get(customer_dir.name, customer_dir.name)
        print(f"\n=== {customer_dir.name} ({customer_name}) ===")
        for run_dir in sorted(p for p in customer_dir.iterdir() if p.is_dir()):
            if not (run_dir / "_audit_metrics.json").exists():
                continue
            try:
                result = backfill_run(run_dir, customer_name, args.lang, args.apply)
            except Exception as exc:
                print(f"  {run_dir.name}: FAILED — {exc}")
                continue
            total_matched += result["matched"]
            total_unmatched += len(result["unmatched"])
            note = []
            if result["already"]:
                note.append(f"{result['already']} already had one")
            if result["unmatched"]:
                note.append(f"{len(result['unmatched'])} unmatched")
            print(
                f"  {result['run']}: {result['matched']}/{result['stored']} given a recipe"
                + (f"  ({', '.join(note)})" if note else "")
            )
            for title in result["unmatched"]:
                print(f"      left alone: {title}")

    print(
        f"\n{'Wrote' if args.apply else 'Would write'} recipes for {total_matched} "
        f"recommendation(s); {total_unmatched} left untouched."
    )
    if not args.apply:
        print("Dry run — pass --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
