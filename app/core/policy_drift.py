"""Drift: what changed in a tenant's policies between two audit runs.

The snapshots are already there — every run stores the Conditional Access
policies, named locations and Intune profiles exactly as Graph returned them.
Comparing two runs costs nothing extra, and it answers the question a monthly
report otherwise cannot: *did anything move since last time?*

That question matters more than the absolute posture for a customer already in
good shape. A tenant can sit at the same Secure Score for six months while
somebody disables the policy that requires MFA for administrators. The score
barely notices. The diff says it in one line.

**Nothing to compare against is not "nothing changed".** This is the same rule
the audit collectors, the report parsers and the baseline evaluator all live
under, and it has one more place to hold here: the first run of a customer,
a run whose predecessor predates snapshots, and a run whose snapshots failed
to write all look identical to "no drift" if you are careless — and that
reading is the dangerous one, because "no policies were removed" is exactly
the reassurance a reader would act on.

So the totals are ``None`` rather than ``0`` when nothing could be compared.
A baseline check reading ``drift.removed_total`` reports not_measured on a
``None`` even if whoever wrote the check forgot its ``measured_when`` guard.
The guard is still there; this is the belt under it.

Nothing here is prose a person reads: an unmeasured comparison carries a
``reason_code`` and the values behind it, and the report and the browser turn
that into a sentence in the reader's own language.

This module holds the comparison itself. ``routes/policy_backup.py`` exposes
it over HTTP and ``reports/generator.py`` puts it in the report — one
implementation, two readers, so drift in a report and drift in the API can
never disagree about what drift means.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = "policy_snapshots"

# Every reason a comparison can decline to be one. See baseline.REASON_CODES.
# "no_runs" is raised by the routes, for a customer with no audits at all.
REASON_CODES = (
    "no_runs",
    "no_snapshots_in_run",
    "no_earlier_snapshots",
    "nothing_comparable",
    "comparison_failed",
    "predecessor_lacked_snapshot",
    "snapshot_unreadable",
)

# Fields Graph rewrites on its own. Reporting them as drift trains a reader to
# skim the diff, which is how a real change goes unread.
NOISY_FIELDS = {
    "modifiedDateTime",
    "lastModifiedDateTime",
    "createdDateTime",
    "@odata.context",
}

# Snapshot names in the order a reader cares about them, most security-relevant
# first. Anything not listed still appears, after these.
#
# These must be the names the collectors actually write. The first version of
# this list invented three of the four, which put conditional_access_policies —
# the one a reader should see first — last, because an unrecognised name sorts
# to the end. It looked right in a test that used the same invented names.
# test_policy_drift.py now checks the list against the collectors' own literals.
_ORDER = [
    "conditional_access_policies",
    "named_locations",
    "intune_configuration_profiles",
    "intune_compliance_policies",
]


def index_by_id(items: list[dict]) -> dict[str, dict]:
    """Key objects by their Graph id, dropping any that have none.

    An object without an id cannot be tracked across runs, so counting it as
    added-then-removed on every comparison would be noise dressed as drift.
    """
    return {str(i["id"]): i for i in items if isinstance(i, dict) and i.get("id")}


def changed_fields(before: dict, after: dict) -> list[str]:
    keys = (set(before) | set(after)) - NOISY_FIELDS
    return sorted(k for k in keys if before.get(k) != after.get(k))


def _name_of(obj: dict) -> str:
    """The policy's own title, if it has one.

    Only the display name travels with a diff — never field *values*. A policy
    body carries group memberships and exclusion lists, and a drift summary is
    read in places a full policy dump should not appear. The name is what makes
    the line legible; the values are what makes it a leak.
    """
    for key in ("displayName", "name", "title"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def diff_items(before_items: list[dict], after_items: list[dict]) -> dict[str, Any]:
    """Compare two snapshots of the same collection."""
    before = index_by_id(before_items)
    after = index_by_id(after_items)

    changed = [
        {"id": pid, "name": _name_of(after[pid]), "fields": fields}
        for pid in sorted(before.keys() & after.keys())
        if (fields := changed_fields(before[pid], after[pid]))
    ]

    return {
        "added": [
            {"id": pid, "name": _name_of(after[pid])}
            for pid in sorted(after.keys() - before.keys())
        ],
        "removed": [
            {"id": pid, "name": _name_of(before[pid])}
            for pid in sorted(before.keys() - after.keys())
        ],
        "changed": changed,
        "unchanged": len(before.keys() & after.keys()) - len(changed),
    }


def snapshots_in(run: Path) -> list[str]:
    """Snapshot names captured by one run, security-relevant ones first."""
    directory = run / SNAPSHOT_DIR
    if not directory.is_dir():
        return []
    names = sorted(p.stem for p in directory.glob("*.json"))
    return sorted(names, key=lambda n: (_ORDER.index(n) if n in _ORDER else len(_ORDER), n))


def read_snapshot(path: Path) -> dict[str, Any]:
    from app.core.encryption import encrypted_read_bytes

    raw = encrypted_read_bytes(path).decode("utf-8", errors="replace")
    return json.loads(raw)


def previous_run_with_snapshots(out_dir: Path) -> Path | None:
    """The newest earlier run of the same customer that captured snapshots.

    Runs are named by timestamp, so a lexical comparison is chronological.
    Skipping runs that captured nothing is what makes drift survive one failed
    audit: comparing against the last run that *has* something to compare is
    more useful than reporting "not measured" because last night's collector
    hit a 403.
    """
    customer_dir = out_dir.parent
    if not customer_dir.is_dir():
        return None
    earlier = [
        p for p in sorted(customer_dir.iterdir())
        if p.is_dir() and p.name < out_dir.name and snapshots_in(p)
    ]
    return earlier[-1] if earlier else None


def unmeasured(reason_code: str, **params: Any) -> dict[str, Any]:
    """The shape of "we could not compare", with totals None rather than 0.

    Public because the report generator needs to produce it too when the
    comparison itself raises. Two places writing the shape by hand is two
    places to forget that the totals are not zero.
    """
    return {
        "measured": False,
        "reason_code": reason_code,
        "reason_params": params,
        "compared_with": None,
        "snapshots": [],
        "added_total": None,
        "removed_total": None,
        "changed_total": None,
    }


def compute_drift(out_dir: Path) -> dict[str, Any]:
    """Compare one run's policy snapshots against the previous run's."""
    current = snapshots_in(out_dir)
    if not current:
        return unmeasured("no_snapshots_in_run")

    previous = previous_run_with_snapshots(out_dir)
    if previous is None:
        return unmeasured("no_earlier_snapshots")

    per_snapshot: list[dict[str, Any]] = []
    for name in current:
        older = previous / SNAPSHOT_DIR / f"{name}.json"
        newer = out_dir / SNAPSHOT_DIR / f"{name}.json"
        if not older.is_file():
            per_snapshot.append({
                "name": name,
                "comparable": False,
                "reason_code": "predecessor_lacked_snapshot",
                "reason_params": {"run": previous.name, "name": name},
            })
            continue
        try:
            before = read_snapshot(older).get("items", [])
            after = read_snapshot(newer).get("items", [])
        except Exception as exc:
            # Deliberately broad, and for the same reason load_previous_metrics
            # is: a snapshot that cannot be decrypted after a key rotation must
            # cost the drift comparison, not the report it sits in.
            logger.warning("Could not compare snapshot %s: %s", name, exc)
            per_snapshot.append({
                "name": name,
                "comparable": False,
                "reason_code": "snapshot_unreadable",
                "reason_params": {"name": name},
            })
            continue
        per_snapshot.append({"name": name, "comparable": True, **diff_items(before, after)})

    comparable = [s for s in per_snapshot if s.get("comparable")]
    if not comparable:
        result = unmeasured("nothing_comparable", run=previous.name)
        result["snapshots"] = per_snapshot
        return result

    return {
        "measured": True,
        "reason_code": "",
        "reason_params": {},
        "compared_with": previous.name,
        "snapshots": per_snapshot,
        "added_total": sum(len(s["added"]) for s in comparable),
        "removed_total": sum(len(s["removed"]) for s in comparable),
        "changed_total": sum(len(s["changed"]) for s in comparable),
    }
