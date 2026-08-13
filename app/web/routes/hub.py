"""Per-customer Hub view — the user-facing core of Sybr HUB.

Aggregates what is known about one customer:

    - M365 audit results, from the stored metrics
    - Autotask company + active contracts (read)
    - IT Glue documentation pointers (read)
    - RMM WebRemote deep-links per device (read)

Plus two action endpoints (manual operator clicks only):

    POST /api/hub/{customer_id}/findings/{finding_id}/create-ticket
        → Autotask CreateTicket
    POST /api/hub/{customer_id}/findings/{finding_id}/push-to-myitprocess
        → myITprocess CreateRecommendation

Both actions are guarded so a scheduled audit cannot trigger them — they must
originate from an authenticated operator request.

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

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.models.settings import CreateTicketRequest
from app.models.user import Role, User
from app.web.middleware.auth import require_customer_access

logger = logging.getLogger(__name__)
router = APIRouter()


# Bindings live on the customer record; get_customer returns the raw JSON so
# extra keys survive. Named here so a typo cannot silently mean "not linked".
_AUTOTASK_ID = "AutotaskAccountId"
_ITGLUE_ID = "ITGlueOrgId"


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

    async with get_db() as conn:
        async with conn.execute(
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

    if not changed:
        raise ValidationError(
            "Send autotask_account_id and/or itglue_org_id to change a binding."
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
    """Raise one Autotask ticket for one audit finding.

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
    from app.core.activity_log import log_activity
    from app.core.config import load_app_settings
    from app.core.customer import CustomerManager
    from app.core.exceptions import IntegrationError, NotFoundError, ValidationError
    from app.integrations.autotask import AutotaskError
    from app.services.finding_tickets import (
        SYSTEM_AUTOTASK,
        find_recommendation,
        get_ticket,
        record_ticket,
    )
    from app.web.i18n import get_ui_lang
    from app.web.routes.autotask import _client_from_settings

    customer = CustomerManager.get_customer(customer_id)
    if customer is None:
        raise NotFoundError(f"No such customer: {customer_id}")

    account_id = customer.get(_AUTOTASK_ID)
    if not account_id:
        raise ValidationError(
            "Denne kunden er ikke koblet til en Autotask-konto. "
            "Koble den først under Hub → kobling."
        )

    # Already raised? Answer before touching Autotask, so a double click costs
    # nothing and cannot fail halfway.
    existing = await get_ticket(customer_id, body.rec_id, SYSTEM_AUTOTASK)
    if existing is not None:
        return {"ok": True, "created": False, "ticket": existing.as_dict()}

    finding = find_recommendation(customer_id, body.rec_id, get_ui_lang(request))
    if finding is None:
        raise NotFoundError(
            f"Fant ikke anbefalingen {body.rec_id!r} i siste audit for denne kunden."
        )

    settings = load_app_settings()
    client = _client_from_settings(request)
    try:
        ticket_id = await client.create_ticket(
            account_id=int(account_id),
            title=body.title or finding.title,
            description=_ticket_description(finding, body.notes),
            priority=body.priority or int(settings.get("autotask_default_priority", 2)),
            status=int(settings.get("autotask_default_status", 1)),
            queue_id=body.queue_id if body.queue_id is not None
            else settings.get("autotask_default_queue_id"),
            contract_id=customer.get("AutotaskContractId"),
        )
        ticket_url = client.ticket_url(ticket_id)
    except AutotaskError as exc:
        raise IntegrationError(f"Autotask avviste saken: {exc}") from exc
    finally:
        await client.close()

    record, is_ours = await record_ticket(
        customer_id=customer_id,
        rec_id=body.rec_id,
        system=SYSTEM_AUTOTASK,
        external_id=str(ticket_id),
        external_url=ticket_url,
        title=body.title or finding.title,
        created_by=user.username,
    )

    log_activity(
        "autotask_ticket_created",
        detail=f"{body.rec_id} -> Autotask #{ticket_id}",
        customer=customer.get("CustomerName", ""),
        user=user.username,
    )

    if not is_ours:
        # Another request won the race. Our ticket exists in Autotask and is
        # not the one on record, so say so with the id — silently returning
        # theirs would leave a real ticket nobody knows about.
        logger.warning(
            "Duplicate Autotask ticket %s for %s (kept %s)",
            ticket_id, body.rec_id, record.external_id,
        )
        return {
            "ok": True,
            "created": False,
            "ticket": record.as_dict(),
            "duplicate_ticket_id": str(ticket_id),
        }

    return {"ok": True, "created": True, "ticket": record.as_dict()}


def _ticket_description(finding, notes: str) -> str:
    """The ticket body: what the audit found, plus anything the operator added.

    The provenance line is not decoration. A ticket outlives the report it came
    from, and a technician picking it up three weeks later needs to know which
    run said this and which finding it was — otherwise the first thing they do
    is re-run the audit to find out.
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
    "/hub/{customer_id}/findings/{finding_id}/push-to-myitprocess",
    status_code=status.HTTP_201_CREATED,
)
async def push_finding_to_myitprocess(
    customer_id: str,
    finding_id: str,
    user: User = Depends(require_customer_access()),
) -> dict[str, Any]:
    """Convert an audit finding into a myITprocess Recommendation.

    For findings that need planning rather than immediate action —
    the distinction is operator's judgement, not encoded here.

    Stub: 501 Not Implemented until the myITprocess PR.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="myITprocess CreateRecommendation not yet wired. See ROADMAP.md.",
    )
