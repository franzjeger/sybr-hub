"""Per-customer Hub view — the user-facing core of Sybr HUB.

Aggregates what is known about one customer:

    - M365 audit results, from the stored metrics
    - Autotask company + active contracts (read)
    - IT Glue documentation pointers (read)
    - RMM WebRemote deep-links per device (read)

Plus two action endpoints (manual operator clicks only):

    POST /api/hub/{customer_id}/tickets
        → Autotask ticket — something to fix this week
    POST /api/hub/{customer_id}/recommendations
        → myITprocess Recommendation — something to plan next quarter

Which bucket a finding belongs in is the operator's judgement and is not
encoded anywhere. Both are guarded so a scheduled audit cannot trigger them:
technician floor, the ``can_write`` grant from ``WriteGuardMiddleware``, and a
test asserting no unattended module imports either client. Both share
``_push_finding`` rather than being two copies of the same seven steps.

``rec_id`` travels in the body of both, never the path — it is built from a
message key plus params carrying tenant data, and a path segment cannot hold a
domain or an app registration's name safely.

**Every source carries its own status.** This route returned a fixed shape of
nulls and called itself the front-end's single source of truth, which meant a
customer with no Autotask, a customer whose Autotask call failed, and a
customer whose Autotask record is simply empty all looked identical on the
page. The front end guessed from the nulls, and guessed wrong — that is where
"Cannot read properties of null" came from.

So each block says which of these it is:

    ok               read, and here it is
    not_configured   no credentials for this integration anywhere
    not_linked       configured, but this customer is not bound to a record
    unavailable      configured and bound, and the read failed — reason says why
    not_implemented  the integration does not exist yet

A figure that was not measured stays null. It is never a zero, and the caller
must not treat it as one.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, status

from app.models.settings import CreateRecommendationRequest, CreateTicketRequest
from app.models.user import Role, User
from app.web.middleware.auth import require_customer_access

logger = logging.getLogger(__name__)
router = APIRouter()


# Bindings live on the customer record; get_customer returns the raw JSON so
# extra keys survive. Named here so a typo cannot silently mean "not linked".
_AUTOTASK_ID = "AutotaskAccountId"
_ITGLUE_ID = "ITGlueOrgId"
_MYITPROCESS_ID = "MyITProcessAccountId"


def _blank(status_name: str, reason: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"status": status_name}
    if reason:
        out["reason"] = reason
    return out


async def _audit_block(customer_id: str, customer_name: str) -> dict[str, Any]:
    """Latest stored metrics. Absent columns stay None — never 0.

    users_no_mfa of 0 and users_no_mfa of "not measured" are different facts
    and the tile that renders them has no other way to tell.
    """
    from app.core.database import get_db

    async with get_db() as conn, conn.execute(
        """SELECT audit_date, risk_grade, risk_score, mfa_coverage_pct,
                      secure_score_pct, total_users, users_no_mfa,
                      ca_policies_enabled, intune_compliance_pct
               FROM audit_metrics
               WHERE customer_id = ? OR customer_name = ?
               ORDER BY audit_date DESC LIMIT 1""",
        (customer_id, customer_name or customer_id),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        return _blank("never_run")
    return {
        "status": "ok",
        "last_run": row[0],
        "grade": row[1],
        "score": row[2],
        "mfa_coverage_pct": row[3],
        "secure_score_pct": row[4],
        "total_users": row[5],
        "users_no_mfa": row[6],
        "ca_policies_enabled": row[7],
        "intune_compliance_pct": row[8],
    }


async def _autotask_block(customer: dict) -> dict[str, Any]:
    from app.core.config import load_app_settings

    settings = load_app_settings()
    if not all(settings.get(k) for k in (
        "autotask_integration_code", "autotask_username", "autotask_secret",
    )):
        return _blank("not_configured")

    account_id = customer.get(_AUTOTASK_ID)
    if not account_id:
        return _blank("not_linked")

    from app.integrations.autotask import AutotaskClient, AutotaskError

    client = AutotaskClient(
        api_integration_code=settings["autotask_integration_code"],
        username=settings["autotask_username"],
        secret=settings["autotask_secret"],
        zone_url=settings.get("autotask_zone_url", ""),
    )
    try:
        account = await client.get_account(int(account_id))
        if account is None:
            return _blank(
                "unavailable",
                f"Autotask has no company with id {account_id} — the link is stale.",
            )
        contracts = await client.list_contracts_for_account(int(account_id))
    except (AutotaskError, ValueError) as exc:
        # A failed read is not an absent classification. Saying so here is what
        # stops the page printing "no contract" about a customer who has one.
        return _blank("unavailable", str(exc)[:300])
    finally:
        await client.close()

    active = contracts[0] if contracts else None
    return {
        "status": "ok",
        "account_id": account.get("id"),
        "account_name": account.get("companyName"),
        "classification": account.get("classification"),
        "active_contract": None if active is None else {
            "id": active.get("id"),
            "name": active.get("contractName"),
            "type": active.get("contractType"),
            "end_date": active.get("endDate"),
        },
        "contract_count": len(contracts),
    }


async def _itglue_block(customer: dict) -> dict[str, Any]:
    from app.core.config import load_app_settings

    settings = load_app_settings()
    api_key = settings.get("itglue_api_key", "")
    if not api_key:
        return _blank("not_configured")

    org_id = customer.get(_ITGLUE_ID)
    if not org_id:
        return _blank("not_linked")

    return {
        "status": "ok",
        "organization_id": org_id,
        # Built rather than fetched: the link is deterministic and asking IT
        # Glue for it on every page load spends a rate-limit slot to learn
        # something already known.
        "documents_url": f"https://{settings.get('itglue_region', 'eu')}.itglue.com"
                         f"/{org_id}/docs",
    }


def _myitprocess_block(customer: dict) -> dict[str, Any]:
    """Configured, bound, or neither — no network call.

    Unlike the Autotask block this does not fetch the account. A read here
    would cost a round-trip on every page load to confirm something the
    binding already asserts, and the client has never spoken to a live
    instance, so a failed read would report "unavailable" about a tenant that
    is fine far more often than it would find a real problem.
    """
    from app.core.config import load_app_settings

    settings = load_app_settings()
    if not settings.get("myitprocess_api_key"):
        return _blank("not_configured")

    account_id = customer.get(_MYITPROCESS_ID)
    if not account_id:
        return _blank("not_linked")

    return {"status": "ok", "account_id": account_id}


def _rmm_block() -> dict[str, Any]:
    # app/integrations/rmm.py is a URL-builder interface with no backend behind
    # it. Reporting "not configured" would invite someone to go looking for the
    # setting.
    return _blank("not_implemented", "No RMM backend is wired yet.")


@router.get("/hub/{customer_id}")
async def get_customer_hub(
    customer_id: str,
    user: User = Depends(require_customer_access()),
) -> dict[str, Any]:
    """Aggregate view of one customer.

    Each block reports its own status; see the module docstring. Nothing here
    invents a zero for something it could not read.
    """
    from app.core.customer import CustomerManager
    from app.core.exceptions import NotFoundError

    customer = CustomerManager.get_customer(customer_id)
    if customer is None:
        raise NotFoundError(f"No such customer: {customer_id}")

    customer_name = customer.get("CustomerName", "")
    return {
        "customer_id": customer_id,
        "customer_name": customer_name,
        "audit": await _audit_block(customer_id, customer_name),
        "autotask": await _autotask_block(customer),
        "itglue": await _itglue_block(customer),
        "myitprocess": _myitprocess_block(customer),
        "rmm": _rmm_block(),
    }


@router.post("/hub/{customer_id}/link")
async def link_customer_records(
    customer_id: str,
    request: Request,
    user: User = Depends(require_customer_access(Role.technician)),
) -> dict[str, Any]:
    """Bind this customer to its Autotask company and IT Glue organisation.

    Without this the integrations can be configured tenant-wide and still have
    nothing to fetch, which is the difference between not_configured and
    not_linked. Sending null for a field clears that binding.
    """
    from app.core.customer import CustomerManager
    from app.core.exceptions import NotFoundError, ValidationError

    customer = CustomerManager.get_customer(customer_id)
    if customer is None:
        raise NotFoundError(f"No such customer: {customer_id}")

    body = await request.json()
    changed: list[str] = []

    if "autotask_account_id" in body:
        value = body["autotask_account_id"]
        if value in (None, ""):
            customer.pop(_AUTOTASK_ID, None)
        else:
            try:
                customer[_AUTOTASK_ID] = int(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError("autotask_account_id must be a number") from exc
        changed.append("autotask")

    if "itglue_org_id" in body:
        value = body["itglue_org_id"]
        if value in (None, ""):
            customer.pop(_ITGLUE_ID, None)
        else:
            customer[_ITGLUE_ID] = str(value)
        changed.append("itglue")

    if "myitprocess_account_id" in body:
        # Kept as a string rather than coerced to int like Autotask's: the
        # myITprocess account identifier has not been seen from a live
        # instance, and narrowing a type on an assumption is how a valid id
        # gets rejected at the binding step with no way to tell why.
        value = body["myitprocess_account_id"]
        if value in (None, ""):
            customer.pop(_MYITPROCESS_ID, None)
        else:
            customer[_MYITPROCESS_ID] = str(value)
        changed.append("myitprocess")

    if not changed:
        raise ValidationError(
            "Send autotask_account_id, itglue_org_id and/or "
            "myitprocess_account_id to change a binding."
        )

    CustomerManager.save_customer({k: v for k, v in customer.items() if not k.startswith("_")})
    return {"ok": True, "changed": changed}


@router.get("/hub/{customer_id}/tickets")
async def list_customer_tickets(
    customer_id: str,
    user: User = Depends(require_customer_access()),
) -> dict[str, Any]:
    """{rec_id: ticket} for this customer, so a findings list can mark them all.

    One query rather than one per finding: the remediation view renders every
    recommendation at once, and asking per row is how a list view becomes
    twenty round-trips.
    """
    from app.services.finding_tickets import list_tickets

    return {"customer_id": customer_id, "tickets": await list_tickets(customer_id)}


async def _push_finding(
    *,
    customer_id: str,
    rec_id: str,
    request: Request,
    username: str,
    system: str,
    binding_key: str,
    not_linked: str,
    activity_action: str,
    system_label: str,
    title_override: str,
    push,
) -> dict[str, Any]:
    """The half of a push that is the same whichever system it goes to.

    Both integrations do the identical seven steps around one different call:
    find the customer, check the binding, answer early if this finding was
    already pushed, resolve the finding from the latest run, push, record under
    a uniqueness constraint, log it. Written twice, those seven drift — the
    duplicate-race handling in particular is subtle enough that a second copy
    would be a second chance to get it wrong.

    ``push(finding, account_id, title)`` does the part that differs and returns
    ``(external_id, external_url)``. It is responsible for turning its own
    integration's error type into an ``IntegrationError``, because only it
    knows what that type is.
    """
    from app.core.activity_log import log_activity
    from app.core.customer import CustomerManager
    from app.core.exceptions import NotFoundError, ValidationError
    from app.services.finding_tickets import (
        find_recommendation,
        get_ticket,
        record_ticket,
    )
    from app.web.i18n import get_ui_lang

    customer = CustomerManager.get_customer(customer_id)
    if customer is None:
        raise NotFoundError(f"No such customer: {customer_id}")

    account_id = customer.get(binding_key)
    if not account_id:
        raise ValidationError(not_linked)

    # Already pushed? Answer before touching the network, so a double click
    # costs nothing and cannot fail halfway.
    existing = await get_ticket(customer_id, rec_id, system)
    if existing is not None:
        return {"ok": True, "created": False, "ticket": existing.as_dict()}

    finding = find_recommendation(customer_id, rec_id, get_ui_lang(request))
    if finding is None:
        raise NotFoundError(
            f"Fant ikke anbefalingen {rec_id!r} i siste audit for denne kunden."
        )

    title = title_override or finding.title
    external_id, external_url = await push(finding, account_id, title)

    record, is_ours = await record_ticket(
        customer_id=customer_id,
        rec_id=rec_id,
        system=system,
        external_id=str(external_id),
        external_url=external_url,
        title=title,
        created_by=username,
    )

    log_activity(
        activity_action,
        detail=f"{rec_id} -> {system_label} #{external_id}",
        customer=customer.get("CustomerName", ""),
        user=username,
    )

    if not is_ours:
        # Another request won the race. What we created is real and is not the
        # one on record, so say so with the id — silently returning theirs
        # would leave something nobody knows about in a customer's system.
        logger.warning(
            "Duplicate %s record %s for %s (kept %s)",
            system_label, external_id, rec_id, record.external_id,
        )
        return {
            "ok": True,
            "created": False,
            "ticket": record.as_dict(),
            "duplicate_ticket_id": str(external_id),
        }

    return {"ok": True, "created": True, "ticket": record.as_dict()}


def _push_description(finding, notes: str) -> str:
    """The body text: what the audit found, plus anything the operator added.

    The provenance line is not decoration. A ticket or a recommendation
    outlives the report it came from, and whoever picks it up three weeks later
    needs to know which run said this and which finding it was — otherwise the
    first thing they do is re-run the audit to find out.
    """
    parts = [finding.detail.strip()]
    if notes.strip():
        parts += ["", "── Fra operatør ──", notes.strip()]
    parts += [
        "",
        "── Kilde ──",
        f"Sybr HUB-anbefaling: {finding.rec_id}",
        f"Fra audit: {finding.audit_date}",
    ]
    return "\n".join(parts)


@router.post(
    "/hub/{customer_id}/tickets",
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket_from_finding(
    customer_id: str,
    body: CreateTicketRequest,
    request: Request,
    user: User = Depends(require_customer_access(Role.technician)),
) -> dict[str, Any]:
    """Raise one Autotask ticket for one audit finding — something to fix now.

    **Operator-initiated, and three separate things keep it that way.** The
    role floor is technician — it was ``viewer`` while this was a stub, which
    would have let a read-only account write into a customer's PSA the moment
    it stopped being one. ``WriteGuardMiddleware`` requires the ``can_write``
    grant on top, because this path is not in its exemption table. And nothing
    scheduled imports the client;
    ``tests/test_autotask_write_side.py`` asserts that rather than trusting it.

    ``rec_id`` arrives in the body, not the path. It is built from message key
    plus identifying params, and those params carry tenant data — an app
    registration's name, a domain — so a path segment cannot safely hold one.

    Idempotent by the identity of the finding. A second click returns the
    first ticket with ``created: false`` rather than raising another; the
    uniqueness is a database constraint, not a check in Python, because two
    technicians clicking at once fit neatly between a SELECT and an INSERT.
    """
    from app.core.config import load_app_settings
    from app.core.customer import CustomerManager
    from app.core.exceptions import IntegrationError
    from app.integrations.autotask import AutotaskError
    from app.services.finding_tickets import SYSTEM_AUTOTASK
    from app.web.routes.autotask import _client_from_settings

    settings = load_app_settings()
    customer = CustomerManager.get_customer(customer_id) or {}

    async def _push(finding, account_id, title):
        client = _client_from_settings(request)
        try:
            ticket_id = await client.create_ticket(
                account_id=int(account_id),
                title=title,
                description=_push_description(finding, body.notes),
                priority=body.priority
                or int(settings.get("autotask_default_priority", 2)),
                status=int(settings.get("autotask_default_status", 1)),
                queue_id=body.queue_id if body.queue_id is not None
                else settings.get("autotask_default_queue_id"),
                contract_id=customer.get("AutotaskContractId"),
            )
            return ticket_id, client.ticket_url(ticket_id)
        except AutotaskError as exc:
            raise IntegrationError(f"Autotask avviste saken: {exc}") from exc
        finally:
            await client.close()

    return await _push_finding(
        customer_id=customer_id,
        rec_id=body.rec_id,
        request=request,
        username=user.username,
        system=SYSTEM_AUTOTASK,
        binding_key=_AUTOTASK_ID,
        not_linked="Denne kunden er ikke koblet til en Autotask-konto. "
                   "Koble den først under Hub → kobling.",
        activity_action="autotask_ticket_created",
        system_label="Autotask",
        title_override=body.title,
        push=_push,
    )


@router.get("/hub/{customer_id}/recommendations")
async def list_customer_recommendations(
    customer_id: str,
    user: User = Depends(require_customer_access()),
) -> dict[str, Any]:
    """{rec_id: pushed recommendation} for this customer."""
    from app.services.finding_tickets import SYSTEM_MYITPROCESS, list_tickets

    return {
        "customer_id": customer_id,
        "recommendations": await list_tickets(customer_id, system=SYSTEM_MYITPROCESS),
    }


@router.post(
    "/hub/{customer_id}/recommendations",
    status_code=status.HTTP_201_CREATED,
)
async def push_finding_to_myitprocess(
    customer_id: str,
    body: CreateRecommendationRequest,
    request: Request,
    user: User = Depends(require_customer_access(Role.technician)),
) -> dict[str, Any]:
    """Push one audit finding to myITprocess — something to plan next quarter.

    The sibling of the ticket endpoint above, and the distinction between them
    is the operator's judgement rather than anything encoded here: a finding
    that needs scheduling through a quarterly review goes here, one that needs
    fixing this week goes to Autotask.

    Same guards, same idempotency. A finding may legitimately have both a
    ticket and a recommendation — the uniqueness is per system — but two
    recommendations for one finding would arrive in the customer's review as
    two agenda items nobody can tell apart.
    """
    from app.core.config import load_app_settings
    from app.core.exceptions import IntegrationError, ValidationError
    from app.integrations.myitprocess import MyITProcessClient, MyITProcessError
    from app.services.finding_tickets import SYSTEM_MYITPROCESS

    settings = load_app_settings()
    api_key = settings.get("myitprocess_api_key", "")
    if not api_key:
        raise ValidationError(
            "myITprocess er ikke konfigurert. Legg inn API-nøkkelen under "
            "Integrasjoner først."
        )

    async def _push(finding, account_id, title):
        client = MyITProcessClient(
            api_key=api_key,
            base_url=settings.get("myitprocess_base_url", ""),
        )
        try:
            recommendation_id = await client.create_recommendation(
                account_id=str(account_id),
                title=title,
                detail=_push_description(finding, body.notes),
                category=body.category or None,
                # The finding's own priority when the operator did not choose,
                # so a critical finding does not arrive in the review looking
                # like routine housekeeping.
                priority=body.priority or finding.priority or None,
                source_finding_id=finding.rec_id,
            )
            return recommendation_id, client.recommendation_url(recommendation_id)
        except MyITProcessError as exc:
            raise IntegrationError(
                f"myITprocess avviste anbefalingen: {exc}"
            ) from exc
        finally:
            await client.close()

    return await _push_finding(
        customer_id=customer_id,
        rec_id=body.rec_id,
        request=request,
        username=user.username,
        system=SYSTEM_MYITPROCESS,
        binding_key=_MYITPROCESS_ID,
        not_linked="Denne kunden er ikke koblet til en myITprocess-konto. "
                   "Koble den først under Hub → kobling.",
        activity_action="myitprocess_recommendation_created",
        system_label="myITprocess",
        title_override=body.title,
        push=_push,
    )
