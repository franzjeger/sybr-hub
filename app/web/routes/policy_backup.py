"""Policy snapshots: what a tenant's configuration looked like on a given run.

Distinct from routes/backup.py, which backs up Sybr HUB itself. These are the
customer's Conditional Access policies, named locations and Intune profiles,
stored exactly as Graph returned them.

The audit has always collected these — as evidence, in columns trimmed to a
width a person reads. A trimmed policy cannot be put back, so the snapshots
keep the raw objects beside the evidence and the two serve different readers.

**Read only, on purpose.** Restoring writes into a customer's tenant, which
needs the tenant_write capability and Graph permissions this app does not
hold: every one it asks for ends in .Read.All. Backing up is the half that
can be done safely today, and it is the half that has to exist first anyway —
a restore is worth nothing without something to restore from.

The diff endpoints are the same data read a second way. Two runs, and what
changed between them: policies added, removed, and the fields that moved.
That is drift, and it costs nothing extra now that the snapshots exist.

The comparison itself lives in ``app.core.policy_drift``, because the report
generator surfaces the same drift as a finding. One implementation, two
readers — so drift in a report and drift over HTTP can never disagree about
what drift means.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from app.core.exceptions import NotFoundError
from app.core.policy_drift import (
    SNAPSHOT_DIR,
    compute_drift,
    diff_items,
    read_snapshot,
    snapshots_in,
)
from app.models.user import User
from app.web.middleware.auth import require_customer_access

router = APIRouter()
logger = logging.getLogger(__name__)


def _customer_runs(customer_id: str) -> list[Path]:
    """Audit run directories for one customer, newest first."""
    from app.core.config import get_audit_dir

    root = get_audit_dir() / customer_id
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir()), reverse=True)


@router.get("/policy-backup/{customer_id}/runs")
async def list_runs(
    customer_id: str,
    user: User = Depends(require_customer_access()),
) -> dict[str, Any]:
    """Runs that produced snapshots, newest first.

    A run with no snapshots is listed with an empty set rather than omitted:
    "this run captured nothing" and "this run did not happen" are different,
    and only one of them means the section failed.
    """
    runs = []
    for run in _customer_runs(customer_id):
        names = snapshots_in(run)
        runs.append({
            "run": run.name,
            "snapshots": names,
            "captured": bool(names),
        })
    return {"customer_id": customer_id, "runs": runs}


@router.get("/policy-backup/{customer_id}/drift")
async def latest_drift(
    customer_id: str,
    user: User = Depends(require_customer_access()),
) -> dict[str, Any]:
    """What moved in this customer's policies since the previous audit.

    The pair of runs is chosen rather than given: the newest run, against the
    newest earlier run that actually captured snapshots. Skipping the empty
    ones is what makes drift survive one failed audit — comparing against the
    last run that has something to compare beats reporting nothing because
    last night's collector hit a 403.

    A customer with one run, or none, gets ``measured: false`` and a reason.
    Not an empty diff: an empty diff reads as "nothing changed", and that is a
    claim about the tenant rather than a statement about the evidence.
    """
    runs = _customer_runs(customer_id)
    if not runs:
        return {
            "customer_id": customer_id,
            "run": None,
            "measured": False,
            "reason": "This customer has no audit runs yet.",
            "compared_with": None,
            "snapshots": [],
            "added_total": None,
            "removed_total": None,
            "changed_total": None,
        }
    latest = runs[0]
    return {"customer_id": customer_id, "run": latest.name, **compute_drift(latest)}


@router.get("/policy-backup/{customer_id}/{run}/{name}")
async def get_snapshot(
    customer_id: str,
    run: str,
    name: str,
    user: User = Depends(require_customer_access()),
) -> dict[str, Any]:
    """One snapshot, envelope and all."""
    from app.core.config import get_audit_dir

    root = get_audit_dir() / customer_id
    path = (root / run / SNAPSHOT_DIR / f"{name}.json").resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise NotFoundError("No such snapshot")
    if not path.is_file():
        raise NotFoundError(f"No snapshot {name!r} in run {run!r}")
    return read_snapshot(path)


@router.get("/policy-backup/{customer_id}/diff/{older}/{newer}/{name}")
async def diff_snapshots(
    customer_id: str,
    older: str,
    newer: str,
    name: str,
    user: User = Depends(require_customer_access()),
) -> dict[str, Any]:
    """What changed in one snapshot between two runs.

    Drift, in other words. Reported as ids and field names — not values —
    because a policy body can carry group memberships and exclusions, and a
    drift summary is read in places a full policy dump should not appear.
    """
    from app.core.config import get_audit_dir

    root = get_audit_dir() / customer_id
    paths = {}
    for label, run in (("older", older), ("newer", newer)):
        path = (root / run / SNAPSHOT_DIR / f"{name}.json").resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            raise NotFoundError("No such snapshot")
        if not path.is_file():
            raise NotFoundError(f"No snapshot {name!r} in run {run!r}")
        paths[label] = path

    before = read_snapshot(paths["older"]).get("items", [])
    after = read_snapshot(paths["newer"]).get("items", [])

    return {
        "customer_id": customer_id,
        "snapshot": name,
        "older": older,
        "newer": newer,
        **diff_items(before, after),
    }
