"""Baselines: measure a customer against a named, versioned standard.

CIS says what good looks like in general; a baseline says what Sybr requires
of a customer it runs. The result names which baseline version judged it, so
raising the bar next year does not silently rewrite last year's verdict.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from app.core.baseline import BaselineError, evaluate, list_baselines
from app.core.exceptions import NotFoundError, ValidationError
from app.models.user import User
from app.web.middleware.auth import get_current_user, require_customer_access

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/baselines")
async def get_baselines(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"baselines": list_baselines()}


@router.get("/baselines/{baseline_id}/evaluate/{customer_id}/{run}")
async def evaluate_baseline(
    baseline_id: str,
    customer_id: str,
    run: str,
    user: User = Depends(require_customer_access()),
) -> dict[str, Any]:
    """Judge one audit run against one baseline.

    Conformance is quoted over the checks that could be assessed, and the
    unassessed are counted beside it rather than folded in. A percentage that
    treats an unreadable section as a failure describes the audit, not the
    tenant — and hands a customer a remediation task for something nobody
    looked at.
    """
    from app.core.config import get_audit_dir
    from app.reports.generator import build_report_context

    root = get_audit_dir() / customer_id
    run_dir = (root / run).resolve()
    try:
        run_dir.relative_to(root.resolve())
    except ValueError:
        raise NotFoundError("No such run")
    if not run_dir.is_dir():
        raise NotFoundError(f"No audit run {run!r} for {customer_id!r}")

    context = build_report_context(customer_id, "", run_dir, [], lang="no")
    try:
        result = evaluate(baseline_id, context)
    except BaselineError as exc:
        raise ValidationError(str(exc)) from exc

    result["customer_id"] = customer_id
    result["run"] = run
    return result
