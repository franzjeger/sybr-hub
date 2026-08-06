"""Deploying Conditional Access policies into a customer's tenant.

The first routes in this application that change something outside it, and the
only ones behind ``require_tenant_write``. That dependency has existed since
the capability was added and guarded nothing until now, which was worth saying
out loud: a gate in a field is not a gate.

The workflow is deliberately two requests.

``/plan`` reads the tenant, renders the template against it, and returns what
would change — including the policies it refuses to deploy and why, and the
rationale for each so the person approving is reading sentences rather than a
count. It changes nothing.

``/apply`` takes the fingerprint that plan returned. If the tenant's policies
have moved since, it refuses: the operator approved a change to a state that no
longer exists, and applying anyway would overwrite whatever moved it.

Both require ``tenant_write``, which requires ``can_write``, which is off by
default for every account. And both need the customer's own consent to
``Policy.ReadWrite.ConditionalAccess``, which is a different party's decision —
reported separately so nobody goes to argue with the wrong one.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import ValidationError
from app.core.policy_templates import TemplateError, annotations, list_templates, render
from app.models.user import User
from app.modules.m365_audit.policy_deploy import (
    CA_PATH,
    WRITE_PERMISSION,
    DeployError,
    Plan,
    apply_plan,
    build_plan,
)
from app.web.i18n import get_ui_lang
from app.web.middleware.auth import get_current_user, require_tenant_write

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/policy-deploy/templates")
async def get_templates(
    request: Request, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """What we can deploy. Readable without the capability — knowing the
    standard exists is not the same as being able to push it."""
    return {"templates": list_templates(get_ui_lang(request))}


async def _live_policies(customer_id: str) -> tuple[list[dict], bool]:
    """The tenant's Conditional Access policies, and whether we may write them.

    Consent is read from the granted app roles rather than inferred from a
    failed write. Finding out by being refused means finding out afterwards.
    """
    from app.core.customer import CustomerManager
    from app.modules.m365_audit.auth import get_auth_for_customer
    from app.modules.m365_audit.graph_client import GraphClient

    customer = CustomerManager.get_customer(customer_id)
    if not customer:
        raise ValidationError(f"No customer {customer_id!r}")
    auth = get_auth_for_customer(customer, CustomerManager.get_cert_path(customer_id))

    async with GraphClient(auth.credential) as client:
        policies = await client.get_all(CA_PATH)
        try:
            check = await client.validate_permissions()
            granted = set(check.get("granted") or [])
        except Exception as exc:
            logger.warning("Could not read granted permissions for %s: %s", customer_id, exc)
            granted = set()
    return list(policies), WRITE_PERMISSION not in granted


def _plan_payload(plan: Plan, template_id: str, lang: str) -> dict[str, Any]:
    why = annotations(template_id, lang)
    payload = plan.as_dict()
    payload["template"] = template_id
    for change in payload["changes"]:
        change["why"] = why.get(change["name"], "")
    return payload


@router.post("/policy-deploy/{customer_id}/plan")
async def plan_deployment(
    customer_id: str,
    request: Request,
    user: User = Depends(require_tenant_write()),
) -> dict[str, Any]:
    """What deploying this template would do. Changes nothing."""
    body = await request.json()
    template_id = str(body.get("template", "")).strip()
    values = body.get("values") or {}
    if not template_id:
        raise ValidationError("No template named")

    try:
        desired = render(template_id, values)
    except TemplateError as exc:
        raise ValidationError(str(exc)) from exc

    live, missing_consent = await _live_policies(customer_id)
    plan = build_plan(
        customer_id, live, desired,
        allow_delete=bool(body.get("allow_delete")),
        missing_consent=missing_consent,
    )
    logger.warning(
        "policy plan: user=%s customer=%s template=%s changes=%d refused=%d",
        user.username, customer_id, template_id,
        len(plan.applicable), len(plan.refused),
    )
    return _plan_payload(plan, template_id, get_ui_lang(request))


@router.post("/policy-deploy/{customer_id}/apply")
async def apply_deployment(
    customer_id: str,
    request: Request,
    user: User = Depends(require_tenant_write()),
) -> dict[str, Any]:
    """Carry out a plan that was reviewed, against the tenant it was made for."""
    body = await request.json()
    template_id = str(body.get("template", "")).strip()
    supplied_fingerprint = str(body.get("fingerprint", "")).strip()
    values = body.get("values") or {}
    if not template_id or not supplied_fingerprint:
        raise ValidationError("Both a template and the fingerprint of its plan are required")

    from app.core.customer import CustomerManager
    from app.modules.m365_audit.auth import get_auth_for_customer
    from app.modules.m365_audit.graph_client import GraphClient

    try:
        desired = render(template_id, values)
    except TemplateError as exc:
        raise ValidationError(str(exc)) from exc

    live, missing_consent = await _live_policies(customer_id)
    plan = build_plan(
        customer_id, live, desired,
        allow_delete=bool(body.get("allow_delete")),
        missing_consent=missing_consent,
    )
    # The fingerprint the operator approved, not the one just computed. If the
    # tenant moved between reviewing and confirming, these differ and
    # apply_plan refuses — which is the whole point of carrying it.
    plan.fingerprint = supplied_fingerprint

    customer = CustomerManager.get_customer(customer_id)
    auth = get_auth_for_customer(customer, CustomerManager.get_cert_path(customer_id))

    saved: list[dict] = []
    try:
        async with GraphClient(auth.credential) as client:
            result = await apply_plan(client, plan, live, snapshot=saved.extend)
    except DeployError as exc:
        logger.warning(
            "policy apply refused: user=%s customer=%s: %s", user.username, customer_id, exc
        )
        raise ValidationError(str(exc)) from exc

    if saved:
        _store_restore_point(customer_id, saved)

    logger.warning(
        "policy apply: user=%s customer=%s applied=%d failed=%d",
        user.username, customer_id, len(result["applied"]), len(result["failed"]),
    )
    from app.core.activity_log import log_activity

    log_activity(
        "policy_deployed",
        detail=f"{template_id}: {len(result['applied'])} applied, {len(result['failed'])} failed",
        customer=customer.get("CustomerName", customer_id) if customer else customer_id,
        user=user.username,
    )
    return result


def _store_restore_point(customer_id: str, policies: list[dict]) -> None:
    """Keep what a deployment replaced, beside the audit snapshots.

    Named by the moment of the write rather than by a run, because it belongs
    to the deployment and not to an audit that happened to precede it.
    """
    import json
    from datetime import datetime, timezone

    from app.core.config import get_audit_dir
    from app.core.encryption import encrypted_write_text

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    directory = get_audit_dir() / customer_id / "policy_restore_points"
    directory.mkdir(parents=True, exist_ok=True)
    encrypted_write_text(
        directory / f"{stamp}.json",
        json.dumps({
            "snapshot": "conditional_access_policies",
            "source": CA_PATH,
            "captured_at": stamp,
            "reason": "taken immediately before a policy deployment",
            "count": len(policies),
            "items": policies,
        }),
    )
    logger.warning("restore point written for %s: %d policies", customer_id, len(policies))
