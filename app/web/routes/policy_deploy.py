"""Deploying Conditional Access policies into a customer's tenant, and undoing it.

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

Restore is the same two requests pointed at a stored state instead of a
template, and deliberately shares every rail rather than getting gentler ones.
A restore path that waived the lockout guard would be a deployment path that
waived it, one POST away — so restoring a policy that would lock the tenant out
is refused exactly as deploying one is, and the operator fixes the exclusion
first.

All of them require ``tenant_write``, which requires ``can_write``, which is off
by default for every account. And both need the customer's own consent to
``Policy.ReadWrite.ConditionalAccess``, which is a different party's decision —
reported separately so nobody goes to argue with the wrong one.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import ValidationError
from app.core.policy_adoption import (
    AdoptionError,
    describe,
    load_mapping,
    save_mapping,
    suggest,
    validate,
)
from app.core.policy_restore import RestoreError, list_sources, load_source
from app.core.policy_templates import TemplateError, annotations, list_templates, render
from app.models.user import User
from app.modules.m365_audit.consent import (
    ConsentError,
    complete_device_flow,
    grant_application_permission,
    start_device_flow,
)
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

    async with auth as entered, GraphClient(entered.credential) as client:
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
    try:
        adopt = load_mapping(customer_id)
    except AdoptionError as exc:
        raise ValidationError(str(exc)) from exc
    plan = build_plan(
        customer_id, live, desired,
        allow_delete=bool(body.get("allow_delete")),
        missing_consent=missing_consent,
        adopt=adopt,
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
    try:
        adopt = load_mapping(customer_id)
    except AdoptionError as exc:
        raise ValidationError(str(exc)) from exc
    plan = build_plan(
        customer_id, live, desired,
        allow_delete=bool(body.get("allow_delete")),
        missing_consent=missing_consent,
        adopt=adopt,
    )
    # The fingerprint the operator approved, not the one just computed. If the
    # tenant moved between reviewing and confirming, these differ and
    # apply_plan refuses — which is the whole point of carrying it.
    plan.fingerprint = supplied_fingerprint

    customer = CustomerManager.get_customer(customer_id)
    auth = get_auth_for_customer(customer, CustomerManager.get_cert_path(customer_id))

    saved: list[dict] = []
    try:
        async with auth as entered, GraphClient(entered.credential) as client:
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


# ── Asking for the permission this cannot grant itself ───────────────────────

# One pending sign-in per customer, in memory. It is a device-code flow with a
# lifetime of minutes; persisting it would mean storing a half-finished
# authentication, which is worth less than re-running a step that takes seconds.
_PENDING: dict[str, dict] = {}


@router.post("/policy-deploy/{customer_id}/consent/start")
async def start_consent(
    customer_id: str,
    user: User = Depends(require_tenant_write()),
) -> dict[str, Any]:
    """Begin an interactive sign-in for a Global Admin.

    Sybr HUB holds no permission that can widen its own access — deliberately,
    since that is what keeps a compromised toolkit from becoming a way into
    every customer's tenant. So the only honest route to a write permission is
    somebody with the authority signing in and granting it, and this is that,
    in the product rather than as portal instructions.
    """
    from app.core.customer import CustomerManager

    customer = CustomerManager.get_customer(customer_id)
    if not customer:
        raise ValidationError(f"No customer {customer_id!r}")
    tenant_id = str(customer.get("TenantId", ""))
    if not tenant_id:
        raise ValidationError(f"{customer_id!r} has no tenant id")

    try:
        flow = start_device_flow(tenant_id)
    except ConsentError as exc:
        raise ValidationError(str(exc)) from exc

    _PENDING[customer_id] = flow
    logger.warning(
        "consent sign-in started: user=%s customer=%s", user.username, customer_id
    )
    return {
        "user_code": flow.get("user_code"),
        "verification_uri": flow.get("verification_uri"),
        "expires_in": flow.get("expires_in"),
        "message": flow.get("message"),
    }


@router.post("/policy-deploy/{customer_id}/consent/complete")
async def complete_consent(
    customer_id: str,
    user: User = Depends(require_tenant_write()),
) -> dict[str, Any]:
    """Wait for the sign-in, then declare and assign the permission.

    Two things, and the portal doing them together makes them easy to conflate:
    declaring puts the permission on the registration, assigning is the consent
    that makes it real. A registration that declares what nobody assigned still
    reports missing consent.
    """
    import asyncio

    from app.core.customer import CustomerManager

    flow = _PENDING.get(customer_id)
    if not flow:
        raise ValidationError("No sign-in is pending for this customer. Start one first.")

    customer = CustomerManager.get_customer(customer_id) or {}
    tenant_id = str(customer.get("TenantId", ""))
    client_id = str(customer.get("ClientId", ""))
    if not client_id:
        raise ValidationError(f"{customer_id!r} has no client id")

    try:
        # msal blocks while polling, so it goes to a thread rather than holding
        # the event loop for the length of somebody typing a code.
        token = await asyncio.to_thread(complete_device_flow, tenant_id, flow)
        result = await grant_application_permission(token, client_id, WRITE_PERMISSION)
    except ConsentError as exc:
        raise ValidationError(str(exc)) from exc
    finally:
        _PENDING.pop(customer_id, None)

    logger.warning(
        "consent granted: user=%s customer=%s permission=%s declared=%s assigned=%s",
        user.username, customer_id, WRITE_PERMISSION,
        result["declared"], result["assigned"],
    )
    from app.core.activity_log import log_activity

    log_activity(
        "graph_permission_granted",
        detail=f"{WRITE_PERMISSION} for {client_id}",
        customer=customer.get("CustomerName", customer_id),
        user=user.username,
    )
    return result


# ── Adopting what the customer already has ───────────────────────────────────

@router.post("/policy-deploy/{customer_id}/adoption/suggest")
async def suggest_adoption(
    customer_id: str,
    request: Request,
    user: User = Depends(require_tenant_write()),
) -> dict[str, Any]:
    """Candidates for each policy in the standard, best first.

    A shortlist for a person. Nothing here reaches a plan until somebody
    confirms it through the endpoint below — matching by heuristic and then
    overwriting is the silent destruction every other guard here prevents.
    """
    body = await request.json()
    template_id = str(body.get("template", "")).strip()
    if not template_id:
        raise ValidationError("No template named")
    try:
        desired = render(template_id, body.get("values") or {})
    except TemplateError as exc:
        raise ValidationError(str(exc)) from exc

    live, _ = await _live_policies(customer_id)
    return {
        "customer_id": customer_id,
        "suggestions": suggest(desired, live),
        "confirmed": describe(load_mapping(customer_id), live),
    }


@router.get("/policy-deploy/{customer_id}/adoption")
async def get_adoption(
    customer_id: str,
    user: User = Depends(require_tenant_write()),
) -> dict[str, Any]:
    """What this customer has already agreed the standard takes over."""
    live, _ = await _live_policies(customer_id)
    return {"customer_id": customer_id, "confirmed": describe(load_mapping(customer_id), live)}


@router.put("/policy-deploy/{customer_id}/adoption")
async def set_adoption(
    customer_id: str,
    request: Request,
    user: User = Depends(require_tenant_write()),
) -> dict[str, Any]:
    """Confirm which existing policies the standard takes over.

    Validated against both sides before it is stored: a mapping naming a policy
    the standard does not contain, or one the tenant no longer has, would fail
    later at the worst moment — during a deployment somebody is watching.
    """
    body = await request.json()
    template_id = str(body.get("template", "")).strip()
    mapping = {str(k): str(v) for k, v in (body.get("mapping") or {}).items() if v}
    if not template_id:
        raise ValidationError("No template named")

    try:
        desired = render(template_id, body.get("values") or {})
    except TemplateError as exc:
        raise ValidationError(str(exc)) from exc

    live, _ = await _live_policies(customer_id)
    try:
        validate(mapping, desired, live)
    except AdoptionError as exc:
        raise ValidationError(str(exc)) from exc

    save_mapping(customer_id, mapping)
    logger.warning(
        "adoption confirmed: user=%s customer=%s adopted=%d",
        user.username, customer_id, len(mapping),
    )
    from app.core.activity_log import log_activity

    log_activity(
        "policy_adoption_set",
        detail=f"{template_id}: {len(mapping)} policy/policies adopted",
        customer=customer_id,
        user=user.username,
    )
    return {"ok": True, "confirmed": describe(mapping, live)}


# ── Putting a tenant back ────────────────────────────────────────────────────

@router.get("/policy-restore/{customer_id}/sources")
async def restore_sources(
    customer_id: str,
    user: User = Depends(require_tenant_write()),
) -> dict[str, Any]:
    """States this customer could be put back to, newest first.

    Behind the capability rather than readable by anyone: the list is a map of
    when this tenant changed, which is not something a read-only account needs.
    """
    return {
        "customer_id": customer_id,
        "sources": [s.as_dict() for s in list_sources(customer_id)],
    }


async def _restore_plan(customer_id: str, body: dict) -> tuple[Plan, list[dict]]:
    """Shared by plan and apply, so the two cannot drift into disagreeing."""
    kind = str(body.get("kind", "")).strip()
    ref = str(body.get("ref", "")).strip()
    if not kind or not ref:
        raise ValidationError("Both a restore source kind and its reference are required")

    try:
        desired = load_source(customer_id, kind, ref)
    except RestoreError as exc:
        raise ValidationError(str(exc)) from exc

    live, missing_consent = await _live_policies(customer_id)
    plan = build_plan(
        customer_id, live, desired,
        allow_delete=bool(body.get("allow_delete")),
        missing_consent=missing_consent,
    )
    return plan, live


@router.post("/policy-restore/{customer_id}/plan")
async def plan_restore(
    customer_id: str,
    request: Request,
    user: User = Depends(require_tenant_write()),
) -> dict[str, Any]:
    """What putting the tenant back to this state would do. Changes nothing.

    Policies created since the source was captured are left alone unless
    allow_delete is set. A restore that silently removed everything added since
    would be a rollback of other people's work as well as of the deployment.
    """
    body = await request.json()
    plan, _ = await _restore_plan(customer_id, body)
    logger.warning(
        "restore plan: user=%s customer=%s source=%s/%s changes=%d refused=%d",
        user.username, customer_id, body.get("kind"), body.get("ref"),
        len(plan.applicable), len(plan.refused),
    )
    payload = plan.as_dict()
    payload["source"] = {"kind": body.get("kind"), "ref": body.get("ref")}
    return payload


@router.post("/policy-restore/{customer_id}/apply")
async def apply_restore(
    customer_id: str,
    request: Request,
    user: User = Depends(require_tenant_write()),
) -> dict[str, Any]:
    """Carry out a restore that was reviewed, against the tenant it was read from."""
    from app.core.customer import CustomerManager
    from app.modules.m365_audit.auth import get_auth_for_customer
    from app.modules.m365_audit.graph_client import GraphClient

    body = await request.json()
    supplied = str(body.get("fingerprint", "")).strip()
    if not supplied:
        raise ValidationError("The fingerprint of the reviewed plan is required")

    plan, live = await _restore_plan(customer_id, body)
    plan.fingerprint = supplied

    customer = CustomerManager.get_customer(customer_id)
    auth = get_auth_for_customer(customer, CustomerManager.get_cert_path(customer_id))

    saved: list[dict] = []
    try:
        async with auth as entered, GraphClient(entered.credential) as client:
            # A restore point of its own, so undoing the undo is possible. The
            # state being restored *from* is worth keeping too.
            result = await apply_plan(client, plan, live, snapshot=saved.extend)
    except DeployError as exc:
        logger.warning(
            "restore refused: user=%s customer=%s: %s", user.username, customer_id, exc
        )
        raise ValidationError(str(exc)) from exc

    if saved:
        _store_restore_point(customer_id, saved)

    logger.warning(
        "restore applied: user=%s customer=%s source=%s/%s applied=%d failed=%d",
        user.username, customer_id, body.get("kind"), body.get("ref"),
        len(result["applied"]), len(result["failed"]),
    )
    from app.core.activity_log import log_activity

    log_activity(
        "policy_restored",
        detail=f"{body.get('kind')}/{body.get('ref')}: "
               f"{len(result['applied'])} applied, {len(result['failed'])} failed",
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
    from datetime import UTC, datetime

    from app.core.config import get_audit_dir
    from app.core.encryption import encrypted_write_text

    stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
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
