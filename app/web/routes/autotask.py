"""Autotask PSA route handlers — read side.

The client was written against Autotask's published reference rather than a
live instance, so `/autotask/test` matters more here than it does for the
other integrations: it is how the field names get confirmed. It reports the
keys Autotask actually returned, which is the thing to compare against what
the read methods filter on.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request

from app.core.config import load_app_settings
from app.core.customer import CustomerManager
from app.core.exceptions import IntegrationError, NotFoundError, ValidationError
from app.core.rbac import filter_customers, get_accessible_customer_ids
from app.models.integrations import AutotaskTestRequest
from app.models.user import Role, User
from app.web.i18n import ui_t
from app.web.middleware.auth import get_current_user, require_role

router = APIRouter(dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)

# The customer-record key routes/hub.py binds a customer to its company with.
_BINDING_KEY = "AutotaskAccountId"


def _bound_to_a_customer_in(account_id: int, allowed: set[str]) -> bool:
    """Whether one of the caller's customers is bound to this company."""
    return any(
        str(c.get(_BINDING_KEY, "")) == str(account_id)
        for c in filter_customers(CustomerManager.list_customers(), allowed)
    )


def _client_from_settings(request: Request):
    """Build a client from stored settings, or say which part is missing."""
    from app.integrations.autotask import AutotaskClient

    settings = load_app_settings()
    code = settings.get("autotask_integration_code", "")
    user = settings.get("autotask_username", "")
    secret = settings.get("autotask_secret", "")

    missing = [
        name
        for name, value in (
            ("integration code", code),
            ("username", user),
            ("secret", secret),
        )
        if not value
    ]
    if missing:
        raise ValidationError(
            ui_t("err_autotask_not_configured", request) + " (" + ", ".join(missing) + ")"
        )
    return AutotaskClient(
        api_integration_code=code,
        username=user,
        secret=secret,
        zone_url=settings.get("autotask_zone_url", ""),
    )


@router.post("/autotask/test")
async def autotask_test(
    request: Request,
    body: AutotaskTestRequest | None = None,
    _user: User = Depends(require_role(Role.admin)),
):
    """Zone discovery plus one bounded query, reporting what came back.

    Returns the field names of the first company rather than the company, so
    the response can be read in the UI without putting a customer's record on
    screen for a connection test.
    """
    from app.integrations.autotask import AutotaskClient

    if body and body.integration_code and body.username and body.secret:
        client = AutotaskClient(
            api_integration_code=body.integration_code,
            username=body.username,
            secret=body.secret,
        )
    else:
        client = _client_from_settings(request)

    try:
        return await client.test_connection()
    finally:
        await client.close()


@router.get("/autotask/accounts")
async def autotask_accounts(
    request: Request,
    search: str = Query("", description="Narrow by company name"),
    limit: int = Query(50, ge=1, le=500),
    user: User = Depends(require_role(Role.technician)),
):
    """Active companies, for binding a Sybr HUB customer to its PSA record.

    This is every company the MSP has, so the floor is technician, and a
    caller scoped to some customers gets id and name only: enough to pick the
    company to bind, nothing about companies that are not theirs.
    """
    from app.integrations.autotask import AutotaskError

    restricted = await get_accessible_customer_ids(user) is not None
    client = _client_from_settings(request)
    try:
        accounts = await client.list_accounts(name_filter=search, limit=limit)
    except AutotaskError as exc:
        raise IntegrationError(str(exc)) from exc
    finally:
        await client.close()

    # Only the fields the picker needs. The full record carries addresses and
    # contact details that a customer-binding screen has no business showing.
    rows = []
    for a in accounts:
        row = {"id": a.get("id"), "name": a.get("companyName")}
        if not restricted:
            row["classification"] = a.get("classification")
            row["company_type"] = a.get("companyType")
        rows.append(row)
    return {"accounts": rows}


@router.get("/autotask/accounts/{account_id}")
async def autotask_account(
    request: Request, account_id: int, user: User = Depends(get_current_user)
):
    """One company and its active contracts.

    A company that does not exist is a 404, not an empty object: the caller
    asked about a specific record and "no such record" is the answer, not
    "here is a company with no fields".

    Contracts are one customer's commercial terms, so a scoped caller reads
    only a company bound to a customer they hold. Any other id is the same
    404, decided before Autotask is asked, so it says nothing about which
    companies exist.
    """
    from app.integrations.autotask import AutotaskError

    allowed = await get_accessible_customer_ids(user)
    if allowed is not None and not _bound_to_a_customer_in(account_id, allowed):
        raise NotFoundError(ui_t("err_autotask_account_not_found", request))

    client = _client_from_settings(request)
    try:
        account = await client.get_account(account_id)
        if account is None:
            raise NotFoundError(ui_t("err_autotask_account_not_found", request))
        contracts = await client.list_contracts_for_account(account_id)
    except AutotaskError as exc:
        raise IntegrationError(str(exc)) from exc
    finally:
        await client.close()

    return {
        "account": {
            "id": account.get("id"),
            "name": account.get("companyName"),
            "classification": account.get("classification"),
            "company_type": account.get("companyType"),
            "is_active": account.get("isActive"),
        },
        "contracts": [
            {
                "id": c.get("id"),
                "name": c.get("contractName"),
                "type": c.get("contractType"),
                "start_date": c.get("startDate"),
                "end_date": c.get("endDate"),
                "status": c.get("status"),
            }
            for c in contracts
        ],
    }
