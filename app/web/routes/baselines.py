"""Baselines: measure a customer against a named, versioned standard.

CIS says what good looks like in general; a baseline says what Sybr requires
of a customer it runs. The result names which baseline version judged it, so
raising the bar next year does not silently rewrite last year's verdict.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.baseline import (
    BaselineError,
    default_baseline_id,
    evaluate,
    list_baselines,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.models.user import User
from app.web.i18n import get_ui_lang
from app.web.middleware.auth import get_current_user, require_customer_access

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/baselines")
async def get_baselines(
    request: Request, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """Every baseline on disk, with the house standard marked.

    A caller that wants "whatever we currently require" should not have to
    hardcode which document that is — it asks for the id "default" and gets
    the same answer the report generator used.
    """
    default = default_baseline_id()
    return {
        "default": default,
        "baselines": [
            {**b, "is_default": b["id"] == default}
            for b in list_baselines(get_ui_lang(request))
        ],
    }


@router.get("/baselines/{baseline_id}/evaluate/{customer_id}/{run}")
async def evaluate_baseline(
    request: Request,
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

    if baseline_id == "default":
        baseline_id = default_baseline_id()

    root = get_audit_dir() / customer_id
    if run == "latest":
        # Runs are timestamp-named, so newest is last lexically. "latest" is
        # safe as a sentinel precisely because no real run can be called that.
        runs = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
        if not runs:
            # 200, not 404. A customer we have not audited yet is a state, not
            # a bad request — and the customer card calls this on every open,
            # so a 404 here means an error toast in a technician's face for a
            # customer who is simply new.
            return {
                "customer_id": customer_id,
                "run": None,
                "evaluated": False,
                "reason_code": "no_runs",
            }
        run_dir = runs[-1]
        run = run_dir.name
    else:
        run_dir = (root / run).resolve()
        try:
            run_dir.relative_to(root.resolve())
        except ValueError:
            raise NotFoundError("No such run")
        if not run_dir.is_dir():
            raise NotFoundError(f"No audit run {run!r} for {customer_id!r}")

    lang = get_ui_lang(request)
    # Reading, not producing. Without this the card rewrote the run's stored
    # metrics — with the current time as its timestamp — on every open.
    context = build_report_context(
        customer_id, "", run_dir, [], lang=lang, persist_metrics=False
    )
    try:
        result = evaluate(baseline_id, context, lang)
    except BaselineError as exc:
        raise ValidationError(str(exc)) from exc

    result["customer_id"] = customer_id
    result["run"] = run
    result["evaluated"] = True
    return result
