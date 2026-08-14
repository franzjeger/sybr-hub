"""System self-management: report the running version, and update in place.

The update endpoint pulls the deployed branch to ``origin`` and re-execs onto
the new code (see ``app/core/self_update.py`` for the mechanism and its
constraints). It exists because the box the service runs on sits behind a
tailnet the operator's browser can reach but a build host cannot, so "ssh in and
git pull" is not always an option.

It is admin-only, and ``can_write``-gated by ``WriteGuardMiddleware`` (a POST
that is not on its exemption list). It is unreachable from scheduled code: the
scheduler drives service functions, not authenticated HTTP routes, and nothing
imports the updater outside this handler.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends

from app.core.exceptions import IntegrationError
from app.core.self_update import (
    BOOTED_COMMIT,
    SelfUpdateError,
    get_update_state,
    perform_self_update,
    schedule_reexec,
)
from app.core.version import get_build_info
from app.models.user import Role
from app.web.middleware.auth import get_current_user, require_role

log = logging.getLogger(__name__)

# Admin at the router level, on GET too: only the admin update card reads
# /system/version, and get_update_state() shells out to git on every call — no
# reason to expose that to a viewer as a repeatable resource lever. It also
# means the admin requirement cannot be lost by a refactor that touches only the
# POST handler's signature.
router = APIRouter(dependencies=[Depends(require_role(Role.admin))])


@router.get("/system/version")
async def system_version() -> dict:
    """Running version, commit and branch, and whether it can self-update.

    ``running_commit`` is the SHA this *process* booted with (captured at import,
    not read live from disk). The update card's post-restart poll matches against
    it, so "restart succeeded" means the new process is serving — not merely that
    the working tree on disk was advanced a second before the re-exec.
    """
    return {"ok": True, "running_commit": BOOTED_COMMIT,
            **get_build_info(), **(await get_update_state())}


@router.post("/system/update")
async def system_update(
    background: BackgroundTasks,
    user=Depends(get_current_user),
) -> dict:
    """Fast-forward the deployment to origin and restart onto the new code.

    Returns the from/to commit immediately; the restart happens in a background
    task *after* this response is flushed, so the operator sees the outcome and
    the browser can poll ``/system/version`` for the new commit. When there is
    nothing to pull, it says so and does not restart.
    """
    try:
        result = await perform_self_update()
    except SelfUpdateError as exc:
        # Operator-facing message (dirty tree, detached HEAD, network, …).
        raise IntegrationError(str(exc)) from exc

    if result.get("updated"):
        log.warning(
            "Self-update by %s: %s -> %s (deps_changed=%s) — restarting",
            getattr(user, "username", "?"), result["from"], result["to"],
            result.get("deps_changed"),
        )
        background.add_task(schedule_reexec)

    return {"ok": True, "restarting": bool(result.get("updated")), **result}
