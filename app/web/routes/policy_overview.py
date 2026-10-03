"""The policy overview: the policies in production, and what to do next.

Read-only by construction. It composes three already-produced sources — the
customer-card inventory, the latest run's drift, and the Sybr templates — and
sends them to the interface. It calls no Graph, mutates nothing, and refuses
to invent state it has not read: an empty tenant is ``inventory_present``
False and ``unmeasured`` drift, not a clean diff.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.policy_overview import build_overview
from app.models.user import User
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
    from app.web.i18n import get_ui_lang

    overview = build_overview(customer_id, get_ui_lang(request))
    return overview
