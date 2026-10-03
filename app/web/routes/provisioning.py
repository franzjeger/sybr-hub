"""Provisioning wizard routes — 5-step guided network site setup."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ToolkitError,
    ValidationError,
)
from app.models.network import ProvisioningStart
from app.models.user import User
from app.web.i18n import refusal
from app.web.middleware.auth import require_feature, require_module

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_module("provisioning"))])

# Provisioning is an admin feature in the matrix (app/core/features.py), and the
# routes carried only a technician floor (SR-001 #7). require_feature reads that
# table, so the screen and the route cannot disagree.
_role_dep = Depends(require_feature("provisioning"))


async def _authorize(session_id: str, user: User, *, tenant_write: bool = False) -> dict:
    """Return the raw session if the caller owns it and may act on its customer.

    Missing and not-owned both raise 404 — the same answer, so a caller cannot
    probe which session ids exist or belong to someone else (SR-001 #2/#3).
    Deploy additionally requires the tenant-write capability, because it writes
    to a customer's device (SR-001 #7).
    """
    from app.core.rbac import check_customer_access
    from app.services.provisioning import get_session_raw

    session = get_session_raw(session_id)
    if session is None or str(session.get("user_id")) != str(user.id):
        raise refusal(NotFoundError, "err_provisioning_session_not_found")
    cid = session.get("customer_id") or ""
    if cid and not await check_customer_access(user, cid):
        raise refusal(NotFoundError, "err_provisioning_session_not_found")
    if tenant_write and not (
        getattr(user, "can_write", False) and getattr(user, "tenant_write", False)
    ):
        logger.warning(
            "403 provisioning-deploy tenant-write: user=%s session=%s",
            user.username,
            session_id,
        )
        raise refusal(ForbiddenError, "err_provisioning_write_denied")
    return session


# ── Session Management ───────────────────────────────────────────────────────


@router.post("/provisioning/start")
async def start_wizard(
    body: ProvisioningStart | None = None,
    user: User = _role_dep,
):
    """Start a new provisioning wizard session, bound to the customer it names.

    The customer whose stored FortiGate/UniFi credentials the deploy may use
    is the one in the body, checked here. It was the caller's active
    customer, which another tab could change; no customer binds none.
    """
    from app.core.customer import CustomerManager
    from app.core.rbac import check_customer_access
    from app.services.provisioning import start_session

    customer_id = (body.customer_id if body else None) or ""
    if customer_id:
        if not await check_customer_access(user, customer_id):
            raise refusal(ForbiddenError, "err_customer_no_access")
        if CustomerManager.get_customer(customer_id) is None:
            raise refusal(NotFoundError, "err_customer_not_found")
    return start_session(user_id=str(user.id), customer_id=customer_id)


@router.get("/provisioning/sessions")
async def list_wizard_sessions(
    user: User = _role_dep,
):
    """List the current user's active wizard sessions."""
    from app.services.provisioning import list_sessions

    sessions = list_sessions(user_id=str(user.id))
    return {"sessions": sessions}


@router.get("/provisioning/{session_id}")
async def get_wizard_session(
    session_id: str,
    user: User = _role_dep,
):
    """Get a wizard session's current state."""
    from app.services.provisioning import get_session

    await _authorize(session_id, user)
    return get_session(session_id)


# ── Step Submission ──────────────────────────────────────────────────────────


@router.post("/provisioning/suggest-subnets")
async def suggest_subnets(
    request: Request,
    user: User = _role_dep,
):
    """Auto-generate subnets from customer name."""
    from app.services.provisioning import generate_subnets

    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise refusal(ValidationError, "err_provisioning_customer_name_required")
    return generate_subnets(name)


@router.put("/provisioning/{session_id}/step/{step}")
async def submit_wizard_step(
    session_id: str,
    step: int,
    request: Request,
    user: User = _role_dep,
):
    """Submit data for a specific wizard step (1-5)."""
    from app.services.provisioning import submit_step

    await _authorize(session_id, user)
    body = await request.json()
    try:
        result = submit_step(session_id, step, body)
        return result
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


# ── Review & Generate ────────────────────────────────────────────────────────


@router.get("/provisioning/{session_id}/summary")
async def get_wizard_summary(
    session_id: str,
    user: User = _role_dep,
):
    """Get the review summary for all wizard steps."""
    from app.services.provisioning import get_summary

    await _authorize(session_id, user)
    try:
        summary = get_summary(session_id)
        return summary
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc


@router.post("/provisioning/{session_id}/generate")
async def generate_wizard_configs(
    session_id: str,
    request: Request,
    user: User = _role_dep,
):
    """Generate device configs from the wizard data.

    Body: ``{"use_ai": true}`` to use Claude for generation,
    otherwise falls back to template-based output.
    """
    from app.services.provisioning import generate_configs

    await _authorize(session_id, user)
    body = await request.json()
    use_ai = body.get("use_ai", False)
    try:
        result = await generate_configs(session_id, use_ai=use_ai)
        return result
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


# ── Deployment ───────────────────────────────────────────────────────────────


@router.post("/provisioning/{session_id}/deploy")
async def deploy_wizard_config(
    session_id: str,
    request: Request,
    user: User = _role_dep,
):
    """Deploy generated config to a device.

    Body: ``{"method": "ssh"|"rest", "target_host": "10.0.0.1"}``

    Returns the service's structured result (DeployReport.as_dict): top-level
    ``ok`` true only when every device took every required step, and per
    device each step with its status and reason.

    All outcomes (start/success/failure) are recorded in the activity log
    so they're visible via Settings → Aktivitetslogg without tailing files.
    """
    import traceback

    from app.core.activity_log import log_activity
    from app.core.customer import CustomerManager
    from app.services.provisioning import deploy_config

    session = await _authorize(session_id, user, tenant_write=True)

    body = await request.json()
    method = body.get("method", "ssh")
    target_host = body.get("target_host", "")

    # The customer the session is bound to — not whichever is active now.
    _cid = session.get("customer_id", "")
    cust = (CustomerManager.get_customer(_cid) or {}) if _cid else {}
    cust_name = cust.get("CustomerName", "")

    log_activity(
        "provisioning_deploy_started",
        detail=f"method={method} host={target_host or '(from config)'}",
        customer=cust_name,
        user=user.username,
    )
    logger.info(
        "Deploy request: session=%s method=%s target_host=%s user=%s",
        session_id,
        method,
        target_host or "(none)",
        user.username,
    )

    try:
        report = await deploy_config(session_id, method=method, target_host=target_host)
    except ValueError as exc:
        log_activity(
            "provisioning_deploy_failed",
            detail=f"method={method} validation: {exc}",
            customer=cust_name,
            user=user.username,
        )
        logger.warning("Deploy validation error: %s", exc)
        raise ValidationError(str(exc)) from exc
    except ToolkitError as exc:
        # A refusal the service raised on purpose (nothing generated yet, an
        # unknown method) is a failed deploy with its own status code, not a
        # crash: it used to fall into the branch below and come back as 502.
        log_activity(
            "provisioning_deploy_failed",
            detail=f"method={method}: {exc.message}",
            customer=cust_name,
            user=user.username,
        )
        logger.warning("Deploy refused: %s", exc.message)
        raise
    except Exception as exc:
        tb_tail = traceback.format_exc().splitlines()[-4:]
        log_activity(
            "provisioning_deploy_crashed",
            detail=f"method={method} {type(exc).__name__}: {exc} | {' / '.join(tb_tail)}",
            customer=cust_name,
            user=user.username,
        )
        logger.exception("Deploy crashed unexpectedly")
        raise refusal(
            IntegrationError, "err_provisioning_deploy_crashed", kind=type(exc).__name__, error=exc
        ) from exc

    # The report says what happened; the route only files it. "partial" means
    # the device took some changes before the run stopped, so it is not in the
    # state it was before; "failed" means nothing was written to it.
    if report.ok:
        action = "provisioning_deploy_completed"
    elif report.changed_device:
        action = "provisioning_deploy_partial"
    else:
        action = "provisioning_deploy_failed"
    summary = report.summary()
    log_activity(
        action,
        detail=f"method={method} {summary}",
        customer=cust_name,
        user=user.username,
    )
    if report.ok:
        logger.info("Deploy ok: %s", summary)
    else:
        logger.warning("Deploy not ok (%s): %s", action, summary)
    return report.as_dict()


# ── Cleanup ──────────────────────────────────────────────────────────────────


@router.delete("/provisioning/{session_id}")
async def delete_wizard_session(
    session_id: str,
    user: User = _role_dep,
):
    """Delete a wizard session."""
    from app.services.provisioning import delete_session

    await _authorize(session_id, user)
    delete_session(session_id)
    return {"ok": True}
