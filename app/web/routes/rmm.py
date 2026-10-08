"""RMM deep-link routes: the connection test, the site picker and a customer's devices.

The flow, end to end:

* An administrator stores Datto RMM's API URL, key and secret key on the
  Integrations page and tests them here (``POST /rmm/test``).
* A technician binds a customer to its Datto site through the link picker
  (``GET /rmm/sites``, then ``POST /hub/{customer_id}/link``, which looks the
  site up in Datto before storing it).
* The customer's Tilgang tab lists the devices the Hub knows from its newest
  audit and, for each one Datto knows by the exact same name or MAC address,
  offers Datto's own Web Remote link (``GET /rmm/devices/{customer_id}``).

The page opens that link in a new tab with ``rel="noopener noreferrer"``.
Datto asks the technician to sign in; the Hub sends no credential, and the
driver drops any link that would carry one (``DattoRMMClient._safe_link``).

Every answer is about the customer's own site. A device found by MAC address in
another site is ignored, and the route never lists the RMM's devices that the
Hub's own list did not name.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import IntegrationError, NotFoundError, ValidationError
from app.integrations.datto_rmm import DattoRMMClient
from app.integrations.rmm import (
    DeviceMatch,
    RMMError,
    claim_once,
    match_by_hostname,
    match_by_mac,
)
from app.models.integrations import DattoRMMTestRequest
from app.models.user import Role, User
from app.web.connection_checks import connection_check
from app.web.connection_checks import connection_settings as load_app_settings
from app.web.i18n import keyed, refusal
from app.web.middleware.auth import get_current_user, require_customer_access, require_role

router = APIRouter(dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)

# The customer-record keys routes/hub.py binds a customer to its site with.
SITE_KEY = "DattoRmmSiteUid"
SITE_NAME_KEY = "DattoRmmSiteName"

_MASK = "••••••"


def configured(settings: dict[str, Any]) -> bool:
    return all(
        settings.get(k) for k in ("datto_rmm_api_url", "datto_rmm_api_key", "datto_rmm_api_secret")
    )


def client_from_settings(settings: dict[str, Any] | None = None) -> DattoRMMClient:
    """A client from the stored settings, or the refusal that says what to do."""
    settings = load_app_settings() if settings is None else settings
    if not configured(settings):
        raise refusal(ValidationError, "err_rmm_not_configured")
    try:
        return DattoRMMClient(
            settings["datto_rmm_api_url"],
            settings["datto_rmm_api_key"],
            settings["datto_rmm_api_secret"],
        )
    except ValueError as exc:
        raise refusal(ValidationError, "err_rmm_api_url_invalid") from exc


@router.post("/rmm/test")
@connection_check(
    "datto_rmm",
    {
        "api_url": "datto_rmm_api_url",
        "api_key": "datto_rmm_api_key",
        "api_secret": "datto_rmm_api_secret",
    },
)
async def rmm_test(
    body: DattoRMMTestRequest | None = None,
    _user: User = Depends(require_role(Role.admin)),
) -> dict[str, Any]:
    """A token and one page of sites, reporting the field names that came back.

    Nothing here has met a live Datto tenant, so the field names are the point:
    compare them with what the driver reads.
    """
    if body and body.api_url and body.api_key and body.api_secret:
        saved = load_app_settings()
        key = saved.get("datto_rmm_api_key", "") if body.api_key == _MASK else body.api_key
        secret = (
            saved.get("datto_rmm_api_secret", "") if body.api_secret == _MASK else body.api_secret
        )
        try:
            client = DattoRMMClient(body.api_url, key, secret)
        except ValueError as exc:
            raise refusal(ValidationError, "err_rmm_api_url_invalid") from exc
    else:
        client = client_from_settings()
    try:
        return await client.test_connection()
    finally:
        await client.close()


@router.get("/rmm/sites")
async def rmm_sites(_user: User = Depends(require_role(Role.technician))) -> dict[str, Any]:
    """Every site in the Datto account, for binding a customer to its own.

    Uid and name only: enough to pick the site, nothing about the devices of
    sites that belong to other customers. Technician floor, like the Autotask
    company list it sits beside in the picker.
    """
    client = client_from_settings()
    try:
        sites = await client.list_sites()
    except RMMError as exc:
        # A failed read is not an empty list: the picker says it could not ask.
        raise refusal(IntegrationError, "err_rmm_sites_failed", error=exc) from exc
    finally:
        await client.close()
    return {"sites": [{"id": s.uid, "name": s.name} for s in sites]}


@router.get("/rmm/devices/{customer_id}")
async def rmm_devices(
    customer_id: str,
    request: Request,
    _user: User = Depends(require_customer_access(Role.technician)),
) -> dict[str, Any]:
    """The customer's devices from its newest audit, each with its Datto match.

    ``status`` says which of these the answer is:

        not_configured  no Datto RMM credentials stored
        not_linked      configured, and the customer has no Datto site
        no_run          no finished audit, so the Hub knows no devices
        no_devices      the newest run carries no device list to match
        unavailable     Datto could not be read; ``reason`` says why
        ok              ``devices`` holds a row per hub device

    A row carries ``web_remote_url`` only when exactly one Datto device in the
    customer's site has the same name or MAC address. Anything else is a row
    without a link, and its ``match`` says why.
    """
    from app.core.customer import CustomerManager
    from app.services.rmm_devices import hub_devices, latest_finished_run

    customer = CustomerManager.get_customer(customer_id)
    if customer is None:
        raise refusal(NotFoundError, "err_customer_not_found_id", customer=customer_id)
    settings = load_app_settings()
    if not configured(settings):
        return {"status": "not_configured"}
    site_uid = str(customer.get(SITE_KEY) or "")
    if not site_uid:
        return {"status": "not_linked"}
    site = {"uid": site_uid, "name": str(customer.get(SITE_NAME_KEY) or "")}

    run = latest_finished_run(customer)
    if run is None:
        return {"status": "no_run", "site": site}
    devices = hub_devices(run)
    if devices is None:
        return {"status": "no_devices", "site": site, "audit_date": run.name}

    # No device the RMM could hold, no request to the RMM.
    matches: list[DeviceMatch] = []
    if devices:
        client = client_from_settings(settings)
        try:
            matches = match_by_hostname(devices, await client.list_site_devices(site_uid))
            await match_by_mac(matches, client, site_uid)
            claim_once(matches)
        except RMMError as exc:
            logger.info("Datto RMM devices for %s could not be read: %s", customer_id, exc)
            return {
                "status": "unavailable",
                "site": site,
                "audit_date": run.name,
                **keyed("reason", "err_rmm_devices_failed", request, error=exc),
            }
        finally:
            await client.close()

    rows = []
    for m in matches:
        found = m.status == "matched" and m.rmm is not None
        rows.append(
            {
                "name": m.device.name,
                "os": m.device.os,
                "sources": list(m.device.sources),
                "match": m.status,
                "matched_by": m.by if found else "",
                "candidates": m.candidates,
                "online": m.rmm.online if found and m.rmm else None,
                "web_remote_url": m.rmm.web_remote_url if found and m.rmm else "",
            }
        )
    return {
        "status": "ok",
        "provider": DattoRMMClient.label,
        "site": site,
        "audit_date": run.name,
        "devices": rows,
        "matched": sum(1 for r in rows if r["web_remote_url"]),
    }


async def verified_site(site_uid: str) -> tuple[str, str]:
    """(uid, name) of a Datto site that exists, for the link route to store.

    A binding is trusted as proof that the site is this customer's, so the uid
    is looked up rather than stored as sent.
    """
    client = client_from_settings()
    try:
        site = await client.get_site(site_uid)
    except RMMError as exc:
        raise refusal(IntegrationError, "err_rmm_site_failed", error=exc) from exc
    finally:
        await client.close()
    if site is None:
        raise refusal(NotFoundError, "err_rmm_site_not_found")
    return site.uid, site.name
