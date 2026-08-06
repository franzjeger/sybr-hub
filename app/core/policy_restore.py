"""Finding a state to put a tenant back to.

Two kinds of source, and they answer different questions.

**Restore points** are written immediately before a deployment, so they hold
what that deployment replaced. This is the one somebody reaches for at four in
the afternoon when a rollout did something unexpected: it is the exact state
that existed a moment earlier, and there is nothing between it and now.

**Audit snapshots** are a by-product of the nightly run. They are older and
coarser, and they answer a different question — "what did this tenant look like
last Tuesday" rather than "undo what I just did".

Both hold the raw Graph objects, so both can be handed to the same planner the
deployment path uses. That reuse is the point rather than a convenience:
restoring is a write into somebody's production tenant, and a restore path with
its own gentler rules would be the way around the rules. Everything a
deployment must survive — the lockout guard, the fingerprint, the report-only
default, a restore point of its own — a restore survives too.

The lockout guard applies unchanged, and that is a deliberate trade. A stored
policy that targets every user with no exclusion was presumably working when it
was captured, so refusing to restore it can be inconvenient. But "it worked
before" is not a guarantee that it works now — the break-glass account may have
been deleted in between — and a restore path that waives the guard is a
deployment path that waives the guard, one POST away.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RESTORE_POINT_DIR = "policy_restore_points"
SNAPSHOT_NAME = "conditional_access_policies"

DEPLOYMENT, AUDIT = "deployment", "audit"

_RUN_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}$")


class RestoreError(Exception):
    """No such source, or one that cannot be read."""


@dataclass
class Source:
    """Somewhere a tenant's policies were recorded."""

    kind: str
    ref: str
    captured_at: str
    count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "ref": self.ref,
            "captured_at": self.captured_at, "count": self.count,
        }


def _read(path: Path) -> dict:
    from app.core.encryption import encrypted_read_bytes

    return json.loads(encrypted_read_bytes(path).decode("utf-8", errors="replace"))


def list_sources(customer_id: str) -> list[Source]:
    """Everything this customer could be put back to, newest first.

    Deployment restore points sort above audit snapshots of the same age: when
    both could answer, the one taken at the moment of a change is the one
    somebody means.
    """
    from app.core.config import get_audit_dir

    root = get_audit_dir() / customer_id
    if not root.is_dir():
        return []

    sources: list[Source] = []

    points = root / RESTORE_POINT_DIR
    if points.is_dir():
        for path in sorted(points.glob("*.json"), reverse=True):
            try:
                doc = _read(path)
            except Exception as exc:
                logger.warning("Unreadable restore point %s: %s", path.name, exc)
                continue
            sources.append(Source(
                kind=DEPLOYMENT, ref=path.stem,
                captured_at=str(doc.get("captured_at", path.stem)),
                count=int(doc.get("count", len(doc.get("items", [])))),
            ))

    for run in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        if not _RUN_NAME.match(run.name):
            continue
        path = run / "policy_snapshots" / f"{SNAPSHOT_NAME}.json"
        if not path.is_file():
            continue
        try:
            doc = _read(path)
        except Exception as exc:
            logger.warning("Unreadable snapshot in %s: %s", run.name, exc)
            continue
        sources.append(Source(
            kind=AUDIT, ref=run.name,
            captured_at=run.name,
            count=int(doc.get("count", len(doc.get("items", [])))),
        ))

    return sources


def load_source(customer_id: str, kind: str, ref: str) -> list[dict]:
    """The policies recorded by one source, as Graph returned them."""
    from app.core.config import get_audit_dir

    root = (get_audit_dir() / customer_id).resolve()
    if kind == DEPLOYMENT:
        path = root / RESTORE_POINT_DIR / f"{ref}.json"
    elif kind == AUDIT:
        if not _RUN_NAME.match(ref):
            raise RestoreError(f"{ref!r} is not an audit run")
        path = root / ref / "policy_snapshots" / f"{SNAPSHOT_NAME}.json"
    else:
        raise RestoreError(f"Unknown restore source {kind!r}")

    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        # A ref carrying .. would otherwise read another customer's policies
        # and hand them to a planner pointed at this one.
        raise RestoreError("No such restore source") from None
    if not resolved.is_file():
        raise RestoreError(f"No {kind} restore source {ref!r}")

    items = _read(resolved).get("items", [])
    if not isinstance(items, list):
        raise RestoreError(f"Restore source {ref!r} holds no policy list")
    return items
