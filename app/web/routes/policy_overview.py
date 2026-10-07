"""Captured policy overview, recommendation library and Hub-only customer plans.

The inventory endpoint reads existing audit evidence. Plan and review writes
store encrypted intent and human evidence; they never call Microsoft Graph.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.core import policy_library
from app.core.customer import CustomerManager
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.policy_overview import _latest_run, build_overview
from app.models.user import Role, User
from app.web.middleware.auth import require_customer_access

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/policy-overview/{customer_id}")
async def policy_overview(
    customer_id: str,
    request: Request,
    user: User = Depends(require_customer_access()),
) -> dict[str, Any]:
    """Policies in production, what moved, and the standard gaps.

    Readable by a viewer with access to the customer — the same audience as
    the customer-card panel the inventory already feeds, so the two cannot
    disagree about what is configured.
    """
    from app.core.rbac import check_audit_path_access
    from app.web.i18n import get_ui_lang, refusal

    latest = _latest_run(customer_id)
    if latest is not None and not await check_audit_path_access(user, str(latest)):
        raise refusal(ForbiddenError, "err_audit_run_access_denied")
    overview = build_overview(customer_id, get_ui_lang(request))
    overview["catalog"] = policy_library.catalog()
    overview["plan"] = policy_library.load_plan(customer_id)
    return overview


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: str = Field(max_length=64)
    policy_ids: list[str] | None = Field(default=None, max_length=100)
    expected_revision: int = Field(ge=0)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["not_assessed", "aligned", "needs_change", "exception"]
    note: str = Field(default="", max_length=2000)
    review_due: date | None = None
    expected_revision: int = Field(ge=0)


def _writable(customer_id: str, user: User) -> None:
    if not user.can_write:
        from app.web.i18n import refusal

        raise refusal(ForbiddenError, "err_readonly_account")
    if CustomerManager.get_customer(customer_id) is None:
        from app.web.i18n import refusal

        raise refusal(NotFoundError, "err_customer_not_found_id", customer=customer_id)


@router.post("/policy-overview/{customer_id}/plan")
def save_plan(
    customer_id: str,
    body: PlanRequest,
    user: User = Depends(require_customer_access(Role.technician)),
) -> dict[str, Any]:
    _writable(customer_id, user)
    return policy_library.save_plan(
        customer_id, body.package_id, body.policy_ids, body.expected_revision, user.id
    )


@router.post("/policy-overview/{customer_id}/reviews/{policy_id}")
def save_review(
    customer_id: str,
    policy_id: str,
    body: ReviewRequest,
    user: User = Depends(require_customer_access(Role.technician)),
) -> dict[str, Any]:
    _writable(customer_id, user)
    return policy_library.save_review(
        customer_id,
        policy_id,
        body.status,
        body.note,
        body.review_due,
        body.expected_revision,
        user.id,
    )
