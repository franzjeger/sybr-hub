from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.models.baseline import M365SecurityBaseline
from app.models.user import Role, User
from app.services.baseline_engine import BaselineEngine
from app.web.middleware.auth import require_role, require_tenant_write

router = APIRouter()
logger = logging.getLogger(__name__)


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
    engine = BaselineEngine(customer_id)
    diff = await engine.plan(req.baseline, req.selected)
    return {"status": "planned", "customer_id": customer_id, "diff": diff}


@router.post("/baseline-deploy/{customer_id}/apply")
async def apply_baseline_deployment(
    customer_id: str, req: BaselinePlanRequest, user: User = Depends(require_tenant_write())
) -> dict[str, Any]:
    """Apply the granular baseline configuration to the tenant."""
    engine = BaselineEngine(customer_id)
    result = await engine.apply(req.baseline, req.selected)
    return {"status": "applied", "customer_id": customer_id, "result": result}
