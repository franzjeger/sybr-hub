"""TLS/Certificate monitoring routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.user import User
from app.services.dns_checker import check_domain as dns_check_domain
from app.services.tls_monitor import (
    check_endpoint_tls,
    discover_tls_endpoints,
    scan_customer_endpoints,
)
from app.web.middleware.auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(tags=["tls"])


@router.get("/tls/auto-discover")
async def tls_auto_discover(user: User = Depends(get_current_user)):
    """Auto-discover TLS endpoints from configured SSH hosts, FortiGate, and UniFi."""
    endpoints = await discover_tls_endpoints()
    return {"endpoints": endpoints, "count": len(endpoints)}


@router.post("/tls/check")
async def tls_check_single(request: Request, user: User = Depends(get_current_user)):
    """Check TLS for a single endpoint."""
    body = await request.json()
    host = body.get("host", "").strip()
    port = int(body.get("port", 443))
    if not host:
        raise ValidationError("Host er påkrevd")
    result = await check_endpoint_tls(host, port)
    return result


@router.post("/tls/scan")
async def tls_scan_endpoints(request: Request, user: User = Depends(get_current_user)):
    """Scan multiple endpoints for TLS health."""
    body = await request.json()
    endpoints = body.get("endpoints", [])
    if not endpoints:
        raise ValidationError("Ingen endepunkter oppgitt")
    results = await scan_customer_endpoints(endpoints)
    return results


# ── DNS email-security check (SPF / DKIM / DMARC) ──────────────────────────

@router.post("/dns/check")
async def dns_check_single(request: Request, user: User = Depends(get_current_user)):
    """Check SPF, DKIM, DMARC and MX for a single domain (live DNS lookup)."""
    body = await request.json()
    domain = (body.get("domain") or "").strip().lower()
    if not domain:
        raise ValidationError("Domene er påkrevd")

    import asyncio
    result = await asyncio.get_event_loop().run_in_executor(None, dns_check_domain, domain)
    return result


@router.post("/dns/check-bulk")
async def dns_check_bulk(request: Request, user: User = Depends(get_current_user)):
    """Check email security for multiple domains in parallel."""
    body = await request.json()
    domains = body.get("domains", [])
    if not domains:
        raise ValidationError("Ingen domener oppgitt")

    import asyncio
    loop = asyncio.get_event_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(None, dns_check_domain, d.strip().lower()) for d in domains[:50]]
    )
    return {"results": results, "count": len(results)}
