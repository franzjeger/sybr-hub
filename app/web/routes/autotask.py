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
from app.core.exceptions import IntegrationError, ValidationError
from app.web.i18n import ui_t
from app.web.middleware.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)


def _client_from_settings(request: Request):
    """Build a client from stored settings, or say which part is missing."""
    from app.integrations.autotask import AutotaskClient

    settings = load_app_settings()
    code = settings.get("autotask_integration_code", "")
    user = settings.get("autotask_username", "")
    secret = settings.get("autotask_secret", "")

    missing = [
        name for name, value in (
            ("integration code", code), ("username", user), ("secret", secret),
        ) if not value
    ]
    if missing:
        raise ValidationError(
            ui_t("err_autotask_not_configured", request)
            + " (" + ", ".join(missing) + ")"
        )
    return AutotaskClient(
        api_integration_code=code,
        username=user,
        secret=secret,
        zone_url=settings.get("autotask_zone_url", ""),
    )


@router.post("/autotask/test")
async def autotask_test(request: Request):
    """Zone discovery plus one bounded query, reporting what came back.

    Returns the field names of the first company rather than the company, so
    the response can be read in the UI without putting a customer's record on
    screen for a connection test.
    """
    body = await request.json() if await request.body() else {}
    from app.integrations.autotask import AutotaskClient

    if body.get("integration_code") and body.get("username") and body.get("secret"):
        client = AutotaskClient(
            api_integration_code=body["integration_code"],
            username=body["username"],
            secret=body["secret"],
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
):
    """Active companies, for binding a Sybr HUB customer to its PSA record."""
    from app.integrations.autotask import AutotaskError

    client = _client_from_settings(request)
    try:
        accounts = await client.list_accounts(name_filter=search, limit=limit)
    except AutotaskError as exc:
        raise IntegrationError(str(exc)) from exc
    finally:
        await client.close()

    # Only the fields the picker needs. The full record carries addresses and
    # contact details that a customer-binding screen has no business showing.
    return {
        "accounts": [
            {
                "id": a.get("id"),
                "name": a.get("companyName"),
                "classification": a.get("classification"),
                "company_type": a.get("companyType"),
            }
            for a in accounts
        ]
    }


@router.get("/autotask/accounts/{account_id}")
async def autotask_account(request: Request, account_id: int):
    """One company and its active contracts.

    A company that does not exist is a 404, not an empty object: the caller
    asked about a specific record and "no such record" is the answer, not
    "here is a company with no fields".
    """
    from app.core.exceptions import NotFoundError
    from app.integrations.autotask import AutotaskError

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
