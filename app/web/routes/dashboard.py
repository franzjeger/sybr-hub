"""Dashboard routes — split into sub-modules for maintainability."""
from __future__ import annotations

from fastapi import APIRouter

from app.web.routes.dashboard_health import router as health_router
from app.web.routes.dashboard_infra import router as infra_router
from app.web.routes.dashboard_overview import router as overview_router
from app.web.routes.dashboard_remediation import router as remediation_router
from app.web.routes.dashboard_status import router as status_router

router = APIRouter()
router.include_router(status_router)
router.include_router(overview_router)
router.include_router(remediation_router)
router.include_router(health_router)
router.include_router(infra_router)
