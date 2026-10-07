"""Versioned recommendations and encrypted, customer-scoped review plans.

A plan records intent and human evidence. It never changes a Microsoft tenant
or infers effective compliance from a matching policy name.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import threading
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.core.customer import CustomerManager
from app.core.encryption import encrypted_read_json, encrypted_write_json
from app.core.exceptions import ToolkitError
from app.core.messages import conflict, invalid, text

_LIBRARY = Path(__file__).resolve().parents[1] / "policy_catalog" / "library.json"
_LOCK = threading.Lock()
_STATUSES = {"not_assessed", "aligned", "needs_change", "exception"}


def catalog() -> dict[str, Any]:
    """Return independent data, including per-policy content fingerprints."""
    data: dict[str, Any] = json.loads(_LIBRARY.read_text(encoding="utf-8"))
    for policy in data["policies"]:
        policy["fingerprint"] = hashlib.sha256(
            json.dumps(policy, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    return data


def _empty() -> dict[str, Any]:
    return {"revision": 0, "package_id": None, "policy_ids": [], "reviews": {}}


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty()
    try:
        plan = encrypted_read_json(path)
        if not (
            isinstance(plan, dict)
            and type(plan.get("revision")) is int
            and plan["revision"] >= 0
            and isinstance(plan.get("policy_ids"), list)
            and all(isinstance(x, str) for x in plan["policy_ids"])
            and isinstance(plan.get("reviews"), dict)
            and all(isinstance(x, dict) for x in plan["reviews"].values())
        ):
            raise ValueError("invalid plan schema")
        return plan
    except Exception as exc:
        # An unreadable plan must never be replaced with a fresh empty plan.
        raise ToolkitError(
            text("err_policy_plan_unreadable"), message_key="err_policy_plan_unreadable"
        ) from exc


def load_plan(customer_id: str) -> dict[str, Any]:
    plan = _read(CustomerManager.get_customer_dir(customer_id) / "policy_plan.json")
    policies = {p["id"]: p for p in catalog()["policies"]}
    for pid, review in plan["reviews"].items():
        due = review.get("review_due", "")
        review["stale"] = (
            pid not in policies
            or review.get("fingerprint") != policies[pid]["fingerprint"]
            or bool(due and due <= date.today().isoformat())
        )
    return plan


@contextlib.contextmanager
def _writing(customer_id: str) -> Iterator[Path]:
    folder = CustomerManager.get_customer_dir(customer_id)
    folder.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        fd = os.open(folder / ".policy_plan.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield folder / "policy_plan.json"
        finally:
            os.close(fd)


def _save(path: Path, plan: dict[str, Any], expected_revision: int, user_id: str) -> None:
    if plan["revision"] != expected_revision:
        raise conflict("err_policy_plan_changed")
    plan["revision"] += 1
    plan["updated_by"] = user_id
    plan["updated_at"] = datetime.now(UTC).isoformat()
    encrypted_write_json(path, plan)


def save_plan(
    customer_id: str,
    package_id: str,
    policy_ids: list[str] | None,
    expected_revision: int,
    user_id: str,
) -> dict[str, Any]:
    data = catalog()
    package = next((p for p in data["packages"] if p["id"] == package_id), None)
    policies = {p["id"]: p for p in data["policies"]}
    if not package or (policy_ids is not None and any(pid not in policies for pid in policy_ids)):
        raise invalid("err_policy_plan_selection")
    selected = set(package["policy_ids"] if policy_ids is None else policy_ids)

    # Dependencies are intent too. Include them even in a tailored package.
    def include(pid: str) -> None:
        for dep in policies[pid]["dependencies"]:
            if dep not in selected:
                selected.add(dep)
                include(dep)

    for pid in list(selected):
        include(pid)
    with _writing(customer_id) as path:
        plan = _read(path)
        plan["package_id"] = package_id
        plan["policy_ids"] = sorted(selected)
        _save(path, plan, expected_revision, user_id)
    return load_plan(customer_id)


def save_review(
    customer_id: str,
    policy_id: str,
    status: str,
    note: str,
    review_due: date | None,
    expected_revision: int,
    user_id: str,
) -> dict[str, Any]:
    policy = next((p for p in catalog()["policies"] if p["id"] == policy_id), None)
    if not policy or status not in _STATUSES:
        raise invalid("err_policy_plan_selection")
    note = note.strip()
    if status != "not_assessed" and not note:
        raise invalid("err_policy_review_evidence")
    if len(note) > 2000 or (review_due and review_due <= date.today()):
        raise invalid("err_policy_review_date")
    if status == "exception" and review_due is None:
        raise invalid("err_policy_review_date")
    with _writing(customer_id) as path:
        plan = _read(path)
        if status == "not_assessed":
            plan["reviews"].pop(policy_id, None)
        else:
            plan["reviews"][policy_id] = {
                "status": status,
                "note": note,
                "review_due": review_due.isoformat() if review_due else None,
                "reviewed_by": user_id,
                "reviewed_at": datetime.now(UTC).isoformat(),
                "fingerprint": policy["fingerprint"],
            }
        _save(path, plan, expected_revision, user_id)
    return load_plan(customer_id)
