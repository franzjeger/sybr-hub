"""Dashboard remediation tracking endpoints.

Split from dashboard.py for maintainability.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.web.i18n import ui_t
from app.web.middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


# ── Remediation tracking ─────────────────────────────────────────────────────

@router.get("/remediation")
async def get_remediation():
    from app.core.customer import CustomerManager
    from app.services.remediation import load_remediation
    active_id = CustomerManager.get_active_id()
    if not active_id:
        raise ValidationError(ui_t("err_no_active_customer"))
    data = await load_remediation(active_id)
    total = len(data)
    done = sum(1 for v in data.values() if v.get("status") == "done")
    pct = round((done / total) * 100, 1) if total > 0 else 0.0
    return {"customer_id": active_id, "items": data, "total": total, "done": done, "pct": pct}


@router.post("/remediation")
async def update_remediation(request: Request):
    from app.core.customer import CustomerManager
    from app.services.remediation import set_remediation
    active_id = CustomerManager.get_active_id()
    if not active_id:
        raise ValidationError(ui_t("err_no_active_customer", request))
    body = await request.json()
    title = body.get("title", "").strip()
    new_status = body.get("status", "open")
    notes = body.get("notes", "")
    if not title:
        raise ValidationError(ui_t("err_missing_title", request))
    if new_status not in ("open", "in_progress", "done", "ignored"):
        raise ValidationError(ui_t("err_invalid_status", request))

    updated_by = getattr(getattr(request.state, "user", None), "username", "")
    # The recommendation title is the stable per-customer key for an item.
    item = await set_remediation(active_id, title, new_status, notes, assigned_to=updated_by)

    from app.core.activity_log import log_activity
    customer = CustomerManager.get_customer(active_id)
    customer_name = customer.get("CustomerName", "") if customer else ""
    log_activity(
        "remediation_updated",
        detail=f"{title} -> {new_status}",
        customer=customer_name,
        user=updated_by,
    )

    return {"ok": True, "item": item}


@router.get("/remediation/summary")
async def get_remediation_summary():
    from app.core.customer import CustomerManager
    from app.services.remediation import get_remediation_counts
    active_id = CustomerManager.get_active_id()
    if not active_id:
        raise ValidationError(ui_t("err_no_active_customer"))
    summary = await get_remediation_counts(active_id)
    return {"customer_id": active_id, **summary}
