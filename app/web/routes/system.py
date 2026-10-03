"""System diagnostics for administrators: component health and the running build.

In-place self-update is gone: it modified dependencies in the live interpreter
and a git reset could not undo that. Releases follow docs/DEPLOYMENT.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.version import get_build_info
from app.models.user import Role
from app.web.middleware.auth import require_role

# Admin at the router level, on GET too: the build lookup shells out to git, no
# reason to expose that to a viewer as a repeatable resource lever.
router = APIRouter(dependencies=[Depends(require_role(Role.admin))])


@router.get("/system/health")
async def system_health() -> dict:
    from app.services.health import component_health

    return await component_health()


@router.get("/system/version")
async def system_version() -> dict:
    """Running version, commit and branch."""
    return {"ok": True, **get_build_info()}
