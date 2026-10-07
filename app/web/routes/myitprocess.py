"""myITprocess route handlers — accounts and connection test.

The write side lives in ``routes/hub.py``, beside the Autotask ticket endpoint,
because both turn one audit finding into one record somewhere else and the
choice between them is the operator's.

What is here is the read side, and ``/myitprocess/test`` carries more weight
than the equivalent for any other integration in this repo: nothing in the
client has met a real server, so the field names it filters on are unconfirmed.
The test reports the keys myITprocess actually returned, which is how they get
corrected.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from app.core.exceptions import IntegrationError, ValidationError
from app.models.integrations import MyITProcessTestRequest
from app.models.user import Role
from app.web.connection_checks import connection_check
from app.web.connection_checks import connection_settings as load_app_settings
from app.web.i18n import refusal
from app.web.middleware.auth import get_current_user, require_role

router = APIRouter(dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)


def _client_from_settings():
    """Build a client from stored settings, or say what is missing."""
    from app.integrations.myitprocess import MyITProcessClient

    settings = load_app_settings()
    api_key = settings.get("myitprocess_api_key", "")
    if not api_key:
        raise refusal(ValidationError, "err_myitprocess_not_configured")
    return MyITProcessClient(
        api_key=api_key,
        base_url=settings.get("myitprocess_base_url", ""),
    )


@router.post("/myitprocess/test")
@connection_check(
    "myitprocess", {"api_key": "myitprocess_api_key", "base_url": "myitprocess_base_url"}
)
async def myitprocess_test(
    body: MyITProcessTestRequest | None = None, _user=Depends(require_role(Role.admin))
):
    """One bounded call, reporting the field names that came back."""
    from app.integrations.myitprocess import MyITProcessClient

    # An unsaved key can be tested directly, so an operator can check a key
    # before storing it. Same shape as /autotask/test. The body is optional.
    if body and body.api_key:
        saved = load_app_settings()
        masked = body.api_key == "••••••"
        client = MyITProcessClient(
            api_key=saved.get("myitprocess_api_key", "") if masked else body.api_key,
            base_url=saved.get("myitprocess_base_url", "")
            if masked and "base_url" not in body.model_fields_set
            else body.base_url,
        )
    else:
        client = _client_from_settings()

    try:
        return await client.test_connection()
    finally:
        await client.close()


@router.get("/myitprocess/accounts")
async def myitprocess_accounts(
    limit: int = Query(default=200, ge=1, le=1000),
    user=Depends(require_role(Role.technician)),
):
    """Accounts, for binding a customer to its myITprocess counterpart.

    Technician floor: this is a list of another system's customers, which is
    not something a read-only account on this install has any reason to pull.
    """
    from app.integrations.myitprocess import MyITProcessError

    client = _client_from_settings()
    try:
        accounts = await client.list_accounts(limit=limit)
    except MyITProcessError as exc:
        # A failed read is not an empty list. Saying so here is what stops the
        # binding screen showing "no accounts" about a tenant that has them.
        raise refusal(IntegrationError, "err_myitprocess_accounts_failed", error=exc) from exc
    finally:
        await client.close()

    # Only what the binding screen needs. The full record is another system's
    # customer data and has no business being on this screen.
    return {
        "accounts": [
            {
                "id": a.get("id") or a.get("accountId") or a.get("Id"),
                "name": a.get("name") or a.get("accountName") or a.get("Name") or "",
            }
            for a in accounts
        ],
        "total": len(accounts),
    }
