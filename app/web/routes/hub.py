"""Per-customer Hub view — the user-facing core of Sybr HUB.

Aggregates everything we know about a customer in one place:

    - M365 audit results (read from local audit dir)
    - Autotask classification + active contract (read)
    - IT Glue documentation pointers (read)
    - RMM WebRemote deep-links per device (read)

Plus two action endpoints (manual operator clicks only):

    POST /api/hub/{customer_id}/findings/{finding_id}/create-ticket
        → Autotask CreateTicket
    POST /api/hub/{customer_id}/findings/{finding_id}/push-to-myitprocess
        → myITprocess CreateRecommendation

Both actions are guarded so a scheduled audit cannot trigger them —
they must originate from an authenticated operator request.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.user import User
from app.web.middleware.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/hub/{customer_id}")
async def get_customer_hub(
    customer_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Aggregate view of one customer.

    Stub: returns the shape only. Wire each section to its source in
    follow-up PRs (one per integration). The contract here is the
    single source of truth for the front-end Hub view.
    """
    return {
        "customer_id": customer_id,
        # ── Latest M365 audit ──
        "audit": {
            "last_run": None,         # ISO-8601 timestamp
            "grade": None,            # 'A' | 'B' | 'C' | 'D' | 'F' | '?'
            "score": None,            # 0..100 or None
            "compliance_total": 0,
            "compliance_pass": 0,
            "compliance_fail": 0,
            "data_quality_issues": [],
            "findings": [],           # list of {id, priority, title, detail}
        },
        # ── Autotask ──
        "autotask": {
            "account_id": None,
            "classification": None,   # icon shown next to customer name
            "active_contract": None,  # {name, type, end_date}
        },
        # ── IT Glue ──
        "itglue": {
            "organization_id": None,
            "documents_url": None,
            "fortigate_backup_count": 0,
        },
        # ── RMM ──
        "rmm": {
            "provider": None,         # 'datto' | 'ninja' | 'atera' | None
            "devices": [],            # list of {name, online, webremote_url}
        },
    }


@router.post(
    "/hub/{customer_id}/findings/{finding_id}/create-ticket",
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket_from_finding(
    customer_id: str,
    finding_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Convert an audit finding into an Autotask ticket.

    Operator-only — the dependency on get_current_user is the guard
    that prevents scheduled-audit code paths from invoking this.

    Stub: 501 Not Implemented until the Autotask write-side PR.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Autotask CreateTicket not yet wired. See ROADMAP.md.",
    )


@router.post(
    "/hub/{customer_id}/findings/{finding_id}/push-to-myitprocess",
    status_code=status.HTTP_201_CREATED,
)
async def push_finding_to_myitprocess(
    customer_id: str,
    finding_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Convert an audit finding into a myITprocess Recommendation.

    For findings that need planning rather than immediate action —
    the distinction is operator's judgement, not encoded here.

    Stub: 501 Not Implemented until the myITprocess PR.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="myITprocess CreateRecommendation not yet wired. See ROADMAP.md.",
    )
