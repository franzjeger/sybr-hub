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

The diff endpoint is the same data read a second way. Two runs, and what
changed between them: policies added, removed, and the fields that moved.
That is drift, and it costs nothing extra now that the snapshots exist.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from app.core.exceptions import NotFoundError
from app.models.user import User
from app.web.middleware.auth import require_customer_access

router = APIRouter()
logger = logging.getLogger(__name__)

SNAPSHOT_DIR = "policy_snapshots"


def _customer_runs(customer_id: str) -> list[Path]:
    """Audit run directories for one customer, newest first."""
    from app.core.config import get_audit_dir

    root = get_audit_dir() / customer_id
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir()), reverse=True)


def _read_snapshot(path: Path) -> dict[str, Any]:
    from app.core.encryption import encrypted_read_bytes

    raw = encrypted_read_bytes(path).decode("utf-8", errors="replace")
    return json.loads(raw)


def _snapshots_in(run: Path) -> list[str]:
    directory = run / SNAPSHOT_DIR
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


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
        names = _snapshots_in(run)
        runs.append({
            "run": run.name,
            "snapshots": names,
            "captured": bool(names),
        })
    return {"customer_id": customer_id, "runs": runs}


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
    return _read_snapshot(path)


def _index(items: list[dict]) -> dict[str, dict]:
    """Key objects by their Graph id, dropping any that have none.

    An object without an id cannot be tracked across runs, so counting it as
    added-then-removed on every comparison would be noise dressed as drift.
    """
    return {str(i["id"]): i for i in items if isinstance(i, dict) and i.get("id")}


# Fields Graph rewrites on its own. Reporting them as drift trains a reader
# to skim the diff, which is how a real change goes unread.
_NOISY = {"modifiedDateTime", "lastModifiedDateTime", "createdDateTime", "@odata.context"}


def _changed_fields(before: dict, after: dict) -> list[str]:
    keys = (set(before) | set(after)) - _NOISY
    return sorted(k for k in keys if before.get(k) != after.get(k))


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

    before = _index(_read_snapshot(paths["older"]).get("items", []))
    after = _index(_read_snapshot(paths["newer"]).get("items", []))

    changed = [
        {"id": pid, "fields": fields}
        for pid in sorted(before.keys() & after.keys())
        if (fields := _changed_fields(before[pid], after[pid]))
    ]

    return {
        "customer_id": customer_id,
        "snapshot": name,
        "older": older,
        "newer": newer,
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": changed,
        "unchanged": len(before.keys() & after.keys()) - len(changed),
    }
