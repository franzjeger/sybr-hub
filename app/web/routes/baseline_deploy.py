from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.exceptions import ValidationError
from app.models.baseline import M365SecurityBaseline
from app.models.user import Role, User
from app.web.i18n import refusal
from app.web.middleware.auth import require_role, require_tenant_write

router = APIRouter()
logger = logging.getLogger(__name__)

# Switched off, not removed. BaselineEngine's plan is a mock (every selected
# item reported as "create", a constant fingerprint) while its apply makes real
# Graph writes, one of them tenant-wide (blocking user consent), with none of
# the rails Conditional Access deployment has: no fingerprint check, no restore
# point, no lockout check, no activity log. It only failed safely because it
# crashed before the first write. Until it is rebuilt on policy_deploy's plan /
# apply model, both endpoints refuse before touching a tenant.
_DISABLED = True


@router.get("/baseline-deploy/schema")
async def get_baseline_schema(
    user: User = Depends(require_role(Role.technician)),
) -> dict[str, Any]:
    """Return the JSON schema for the granular M365 baseline.
    The frontend can use this to dynamically build the toggle UI."""
    return M365SecurityBaseline.model_json_schema()


class BaselinePlanRequest(BaseModel):
    baseline: M365SecurityBaseline
    selected: list[str]


@router.post("/baseline-deploy/{customer_id}/plan")
async def plan_baseline_deployment(
    customer_id: str, req: BaselinePlanRequest, user: User = Depends(require_tenant_write())
) -> dict[str, Any]:
    """Calculate the diff between the desired baseline and the tenant's current state."""
    if _DISABLED:
        raise refusal(ValidationError, "err_baseline_deploy_disabled")
    from app.services.baseline_engine import BaselineEngine

    engine = BaselineEngine(customer_id)
    diff = await engine.plan(req.baseline, req.selected)
    return {"status": "planned", "customer_id": customer_id, "diff": diff}


@router.post("/baseline-deploy/{customer_id}/apply")
async def apply_baseline_deployment(
    customer_id: str, req: BaselinePlanRequest, user: User = Depends(require_tenant_write())
) -> dict[str, Any]:
    """Apply the granular baseline configuration to the tenant."""
    if _DISABLED:
        logger.warning(
            "baseline apply refused (disabled): user=%s customer=%s", user.username, customer_id
        )
        raise refusal(ValidationError, "err_baseline_deploy_disabled")
    from app.services.baseline_engine import BaselineEngine

    engine = BaselineEngine(customer_id)
    result = await engine.apply(req.baseline, req.selected)
    return {"status": "applied", "customer_id": customer_id, "result": result}
