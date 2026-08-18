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
from app.models.user import Role, User
from app.web.i18n import get_ui_lang, ui_t
from app.web.middleware.auth import get_current_user, require_role

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


# ── Remediation tracking ─────────────────────────────────────────────────────

def _recommendation_titles(customer_id: str, lang: str) -> dict[str, str]:
    """{rec_id: title} from the customer's latest run, in the reader's language.

    Remediation rows store an id, not a sentence — that is what lets the state
    survive a language change. Something still has to turn the id back into
    words, and the recommendation it came from is the only thing that can.
    """
    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_read_json
    from app.web.routes.dashboard_overview import relocalise_recommendations

    customer = CustomerManager.get_customer(customer_id) or {}
    name = customer.get("CustomerName", customer_id)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    root = get_audit_dir() / safe
    if not root.is_dir():
        return {}
    for run in sorted((d for d in root.iterdir() if d.is_dir()), reverse=True):
        path = run / "_audit_metrics.json"
        if not path.exists():
            continue
        try:
            metrics = relocalise_recommendations(encrypted_read_json(path), lang)
        except Exception as e:
            logger.warning("Could not read recommendations for %s: %s", customer_id, e)
            return {}
        return {
            r["rec_id"]: r.get("title", "")
            for r in metrics.get("recommendations", [])
            if isinstance(r, dict) and r.get("rec_id")
        }
    return {}


@router.get("/remediation")
async def get_remediation(request: Request):
    from app.core.customer import CustomerManager
    from app.services.remediation import load_remediation
    active_id = CustomerManager.get_active_id()
    if not active_id:
        raise ValidationError(ui_t("err_no_active_customer"))
    data = await load_remediation(active_id)
    titles = _recommendation_titles(active_id, get_ui_lang(request))
    # A row whose finding no longer appears keeps its id as the label. That is
    # unlovely, and it is honest: something was actioned that this run does not
    # raise, and hiding it would lose the note attached to it.
    items = {
        rec_id: {**entry, "title": titles.get(rec_id) or rec_id}
        for rec_id, entry in data.items()
    }
    total = len(items)
    done = sum(1 for v in items.values() if v.get("status") == "done")
    pct = round((done / total) * 100, 1) if total > 0 else 0.0
    return {"customer_id": active_id, "items": items, "total": total, "done": done, "pct": pct}


@router.post("/remediation")
async def update_remediation(request: Request, _user: User = Depends(require_role(Role.technician))):
    from app.core.customer import CustomerManager
    from app.services.remediation import set_remediation
    active_id = CustomerManager.get_active_id()
    if not active_id:
        raise ValidationError(ui_t("err_no_active_customer", request))
    body = await request.json()
    # rec_id is the stable, language-independent identity. "title" is still
    # accepted for a client that has not reloaded since this changed, and for
    # rows written before recommendations had ids at all.
    rec_id = (body.get("rec_id") or body.get("title") or "").strip()
    new_status = body.get("status", "open")
    notes = body.get("notes", "")
    if not rec_id:
        raise ValidationError(ui_t("err_missing_title", request))
    if new_status not in ("open", "in_progress", "done", "ignored"):
        raise ValidationError(ui_t("err_invalid_status", request))

    updated_by = getattr(getattr(request.state, "user", None), "username", "")
    item = await set_remediation(active_id, rec_id, new_status, notes, assigned_to=updated_by)

    from app.core.activity_log import log_activity
    customer = CustomerManager.get_customer(active_id)
    customer_name = customer.get("CustomerName", "") if customer else ""
    log_activity(
        "remediation_updated",
        detail=f"{rec_id} -> {new_status}",
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
