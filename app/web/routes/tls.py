"""TLS/Certificate monitoring routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.rbac import customer_in_scope, get_accessible_customer_ids
from app.models.network import (
    DnsBulkCheckRequest,
    DnsCheckRequest,
    TlsCheckRequest,
    TlsScanRequest,
)
from app.models.user import Role, User
from app.services import tls_inventory
from app.services.dns_checker import check_domain as dns_check_domain
from app.services.tls_monitor import (
    check_endpoint_tls,
    discover_tls_endpoints,
    scan_customer_endpoints,
)
from app.web.i18n import refusal
from app.web.middleware.auth import get_current_user, require_customer_access, require_feature

log = logging.getLogger(__name__)
# The whole module is the 'network' feature (app/core/features.py); per-route
# floors below only ever raise it.
router = APIRouter(tags=["tls"], dependencies=[Depends(require_feature("network"))])


@router.get("/tls/auto-discover")
async def tls_auto_discover(user: User = Depends(get_current_user)):
    """Auto-discover TLS endpoints from the caller's customers' SSH hosts,
    FortiGates and UniFi controllers."""
    endpoints = await discover_tls_endpoints(await get_accessible_customer_ids(user))
    return {"endpoints": endpoints, "count": len(endpoints)}


# Both checks are lookups in the write guard's sense (a read-only account may
# run them), and both now leave their reading behind. For an account without
# can_write that reading only refreshes an endpoint the hub already knows: a
# lookup brings state up to date, it does not add to the list the daily job
# re-checks. See LOOKUPS in app/web/middleware/write_guard.py.


@router.post("/tls/check")
async def tls_check_single(body: TlsCheckRequest, user: User = Depends(get_current_user)):
    """Check TLS for a single endpoint, and keep what it found."""
    host = body.host.strip()
    port = body.port
    if not host:
        raise refusal(ValidationError, "err_host_required")
    result = await check_endpoint_tls(host, port)
    # No source here: a new endpoint is filed as "manual", and an endpoint
    # discovery found keeps saying where it came from.
    await tls_inventory.record_quietly(
        [result],
        allowed=await get_accessible_customer_ids(user),
        may_add=bool(getattr(user, "can_write", False)),
    )
    return result


@router.post("/tls/scan")
async def tls_scan_endpoints(body: TlsScanRequest, user: User = Depends(get_current_user)):
    """Scan multiple endpoints for TLS health, and keep what each one found.

    An endpoint may name its customer (auto-discover sends it back), which
    must be one the caller holds: a scan is not a way to file an endpoint
    under somebody else's customer.
    """
    if not body.endpoints:
        raise refusal(ValidationError, "err_tls_no_endpoints")
    allowed = await get_accessible_customer_ids(user)
    for ep in body.endpoints:
        if ep.customer_id and not customer_in_scope(ep.customer_id, allowed):
            raise refusal(ForbiddenError, "err_customer_no_access")
    results = await scan_customer_endpoints(
        [ep.model_dump(exclude_none=True) for ep in body.endpoints]
    )
    await tls_inventory.record_quietly(
        results["results"],
        allowed=allowed,
        may_add=bool(getattr(user, "can_write", False)),
    )
    return results


# ── What the checks found, kept ─────────────────────────────────────────────


@router.get("/tls/certificates")
async def tls_certificates(user: User = Depends(get_current_user)):
    """Every endpoint the hub has checked that the caller may see, with its
    certificate's expiry status, most urgent first."""
    endpoints = await tls_inventory.list_endpoints(await get_accessible_customer_ids(user))
    return {"endpoints": endpoints, "count": len(endpoints)}


@router.get("/tls/certificates/{customer_id}")
async def tls_certificates_for_customer(
    customer_id: str, user: User = Depends(require_customer_access(Role.technician))
):
    """The endpoints filed under one customer."""
    endpoints = await tls_inventory.list_endpoints(
        await get_accessible_customer_ids(user), customer_id
    )
    return {"customer_id": customer_id, "endpoints": endpoints, "count": len(endpoints)}


@router.delete("/tls/certificates")
async def tls_forget_endpoint(
    host: str = Query(..., min_length=1, max_length=255),
    port: int = Query(443, ge=1, le=65535),
    user: User = Depends(get_current_user),
):
    """Take an endpoint off the list, and off the daily re-check.

    For a typo or a one-off check of somebody else's site. An endpoint that
    configuration names (a customer's FortiGate, say) comes back with the next
    daily check, because the configuration still points at it.
    """
    if not await tls_inventory.forget(host, port, await get_accessible_customer_ids(user)):
        raise refusal(NotFoundError, "err_tls_endpoint_not_found")
    return {"ok": True}


# ── DNS email-security check (SPF / DKIM / DMARC) ──────────────────────────


@router.post("/dns/check")
async def dns_check_single(body: DnsCheckRequest, user: User = Depends(get_current_user)):
    """Check SPF, DKIM, DMARC and MX for a single domain (live DNS lookup)."""
    domain = (body.domain or "").strip().lower()
    if not domain:
        raise refusal(ValidationError, "err_domain_required")

    import asyncio

    result = await asyncio.get_event_loop().run_in_executor(None, dns_check_domain, domain)
    return result


@router.post("/dns/check-bulk")
async def dns_check_bulk(body: DnsBulkCheckRequest, user: User = Depends(get_current_user)):
    """Check email security for multiple domains in parallel."""
    domains = body.domains
    if not domains:
        raise refusal(ValidationError, "err_tls_no_domains")

    import asyncio

    loop = asyncio.get_event_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(None, dns_check_domain, d.strip().lower()) for d in domains[:50]]
    )
    return {"results": results, "count": len(results)}
