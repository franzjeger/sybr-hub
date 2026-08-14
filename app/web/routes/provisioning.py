"""Provisioning wizard routes — 5-step guided network site setup."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.user import User
from app.web.middleware.auth import require_feature

logger = logging.getLogger(__name__)
router = APIRouter()

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
        raise NotFoundError("Sesjon ikke funnet")
    cid = session.get("customer_id") or ""
    if cid and not await check_customer_access(user, cid):
        raise NotFoundError("Sesjon ikke funnet")
    if tenant_write and not (
        getattr(user, "can_write", False) and getattr(user, "tenant_write", False)
    ):
        logger.warning(
            "403 provisioning-deploy tenant-write: user=%s session=%s",
            user.username, session_id,
        )
        raise ForbiddenError(
            "Deploy skriver til kundens enhet og krever skrivetilgang. "
            "Kontoen din har lesetilgang."
        )
    return session


# ── Session Management ───────────────────────────────────────────────────────


@router.post("/provisioning/start")
async def start_wizard(
    user: User = _role_dep,
):
    """Start a new provisioning wizard session."""
    from app.core.customer import CustomerManager
    from app.services.provisioning import start_session

    active = CustomerManager.get_active() or {}
    return start_session(user_id=str(user.id), customer_id=active.get("_id", ""))


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
        raise ValidationError("Kundenavn er påkrevd")
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
        raise ValidationError(str(exc))


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
        raise NotFoundError(str(exc))


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
        raise ValidationError(str(exc))


# ── Deployment ───────────────────────────────────────────────────────────────


@router.post("/provisioning/{session_id}/deploy")
async def deploy_wizard_config(
    session_id: str,
    request: Request,
    user: User = _role_dep,
):
    """Deploy generated config to a device.

    Body: ``{"method": "ssh"|"rest", "target_host": "10.0.0.1"}``

    All outcomes (start/success/failure) are recorded in the activity log
    so they're visible via Settings → Aktivitetslogg without tailing files.
    """
    import logging
    import traceback

    from app.core.activity_log import log_activity
    from app.core.customer import CustomerManager
    from app.services.provisioning import deploy_config
    log = logging.getLogger(__name__)

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
        customer=cust_name, user=user.username,
    )
    log.info("Deploy request: session=%s method=%s target_host=%s user=%s",
             session_id, method, target_host or "(none)", user.username)

    try:
        result = await deploy_config(session_id, method=method, target_host=target_host)

        # Extract meaningful outcome — surface FortiGate-level errors even if outer ok=True
        fg = (result.get("results") or {}).get("fortigate") or {}
        top_ok = result.get("ok", False)
        top_err = result.get("error", "")
        fg_ok = fg.get("ok", False)
        fg_err = fg.get("error", "")
        fg_total = fg.get("total", 0)
        fg_failed = fg.get("failed", 0)
        fg_details = fg.get("details") or []

        if not top_ok and top_err:
            log_activity(
                "provisioning_deploy_failed",
                detail=f"method={method}: {top_err}",
                customer=cust_name, user=user.username,
            )
            log.warning("Deploy failed at top level: %s", top_err)
        elif fg_total == 0 and not fg_ok and fg_err:
            # REST branch returned a direct error (no steps attempted)
            log_activity(
                "provisioning_deploy_failed",
                detail=f"method={method} FortiGate: {fg_err}",
                customer=cust_name, user=user.username,
            )
            log.warning("Deploy failed (FortiGate branch): %s", fg_err)
        elif fg_failed > 0:
            # Partial failure — log each failed step
            failed_steps = [d for d in fg_details if not d.get("ok")][:10]
            failed_summary = "; ".join(
                f"{d.get('step','?')}: {d.get('error','?')}" for d in failed_steps
            ) or f"{fg_failed} steg feilet"
            log_activity(
                "provisioning_deploy_partial",
                detail=f"method={method} {fg.get('success',0)}/{fg_total} OK, {fg_failed} feilet — {failed_summary}",
                customer=cust_name, user=user.username,
            )
            log.warning("Deploy partial: %d/%d OK, %d failed", fg.get("success", 0), fg_total, fg_failed)
        else:
            log_activity(
                "provisioning_deploy_completed",
                detail=f"method={method} {fg.get('success', fg_total)}/{fg_total or '?'} steg OK",
                customer=cust_name, user=user.username,
            )
            log.info("Deploy ok: %d/%d steg", fg.get("success", fg_total), fg_total)

        return result

    except ValueError as exc:
        log_activity(
            "provisioning_deploy_failed",
            detail=f"method={method} validation: {exc}",
            customer=cust_name, user=user.username,
        )
        log.warning("Deploy validation error: %s", exc)
        raise ValidationError(str(exc))
    except Exception as exc:
        tb_tail = traceback.format_exc().splitlines()[-4:]
        log_activity(
            "provisioning_deploy_crashed",
            detail=f"method={method} {type(exc).__name__}: {exc} | {' / '.join(tb_tail)}",
            customer=cust_name, user=user.username,
        )
        log.exception("Deploy crashed unexpectedly")
        raise IntegrationError(f"Deploy crashed: {type(exc).__name__}: {exc}")


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
