"""GDAP / Partner Center integration routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AuthError, IntegrationError, ValidationError
from app.models.user import Role, User
from app.web.middleware.auth import get_current_user, require_role

logger = logging.getLogger(__name__)
router = APIRouter()

_admin = Depends(require_role(Role.admin))


# ── Status ───────────────────────────────────────────────────────────────────

@router.get("/gdap/status")
async def gdap_status(user: User = _admin):
    """Return GDAP configuration status and partner tenant info."""
    from app.core.credentials import gdap_configured, load_gdap_config

    cfg = load_gdap_config() or {}
    return {
        "configured": gdap_configured(),
        "partner_tenant_id": cfg.get("partner_tenant_id", ""),
        "client_id": cfg.get("client_id", ""),
        "app_display_name": cfg.get("app_display_name", ""),
        "setup_date": cfg.get("setup_date", ""),
        "last_customer_sync": cfg.get("last_customer_sync", ""),
        "customer_count": cfg.get("customer_count", 0),
    }


# ── Setup ────────────────────────────────────────────────────────────────────

@router.post("/gdap/setup")
async def gdap_setup(request: Request, user: User = _admin):
    """Save (or update) GDAP partner credentials and validate connectivity."""
    from app.core.credentials import (
        get_secret,
        save_gdap_config,
        store_secret,
    )

    body = await request.json()
    partner_tenant_id = (body.get("partner_tenant_id") or "").strip()
    client_id = (body.get("client_id") or "").strip()
    client_secret = (body.get("client_secret") or "").strip()

    if not partner_tenant_id or not client_id:
        raise ValidationError("partner_tenant_id and client_id are required")

    # Only require secret on first setup; allow update without changing it
    existing_secret = get_secret("gdap", "partner_client_secret")
    if not client_secret and not existing_secret:
        raise ValidationError("client_secret is required for initial setup")

    # Persist to keyring
    store_secret("gdap", "partner_tenant_id", partner_tenant_id)
    store_secret("gdap", "partner_client_id", client_id)
    if client_secret:
        store_secret("gdap", "partner_client_secret", client_secret)

    # Validate by acquiring a token for Partner Center API
    try:
        from app.integrations.partner_center import PartnerCenterClient
        async with PartnerCenterClient(
            partner_tenant_id, client_id,
            client_secret or existing_secret,
        ) as pc:
            customers = await pc.list_customers()
            customer_count = len(customers)
    except Exception as exc:
        logger.warning("GDAP setup: Partner Center validation failed: %s", exc)
        # Credentials saved but validation failed. The outcome is written to
        # the config, not only returned: the response is read once, while the
        # integration card is repainted from the stored config on every load.
        # Without this the card went green and stayed green — "Konfigurert" —
        # for credentials Partner Center had just rejected.
        save_gdap_config({
            "partner_tenant_id": partner_tenant_id,
            "client_id": client_id,
            "app_display_name": body.get("app_display_name", "MSP Toolkit GDAP"),
            "setup_date": datetime.now(timezone.utc).isoformat(),
            "last_customer_sync": "",
            "customer_count": 0,
            "validated": False,
            "validated_at": "",
            "validation_error": str(exc),
        })
        return {
            "ok": True,
            "validated": False,
            "warning": f"Credentials saved but Partner Center validation failed: {exc}",
        }

    # One clock read: setup, sync and validation all happened at this moment,
    # and three separate now() calls can straddle a second boundary and file
    # them as three.
    now_iso = datetime.now(timezone.utc).isoformat()
    save_gdap_config({
        "partner_tenant_id": partner_tenant_id,
        "client_id": client_id,
        "app_display_name": body.get("app_display_name", "MSP Toolkit GDAP"),
        "setup_date": now_iso,
        "last_customer_sync": now_iso,
        "customer_count": customer_count,
        "validated": True,
        "validated_at": now_iso,
        "validation_error": "",
    })

    logger.info("GDAP setup complete: %d customers found", customer_count)
    return {"ok": True, "validated": True, "customer_count": customer_count}


# ── Validate Graph access for one customer ───────────────────────────────────

@router.post("/gdap/validate/{tenant_id}")
async def validate_gdap_customer(tenant_id: str, user: User = _admin):
    """Test GDAP Graph API access for a specific customer tenant."""
    from app.modules.m365_audit.auth import AuthManager

    try:
        auth = AuthManager.from_gdap(tenant_id)
        async with auth:
            from app.modules.m365_audit.graph_client import GraphClient
            async with GraphClient(auth.credential) as graph:
                result = await graph.validate_gdap_access()
                return result
    except AuthError as exc:
        raise
    except Exception as exc:
        logger.error("GDAP validate failed for %s: %s", tenant_id, exc)
        raise IntegrationError(f"GDAP validation failed: {exc}")


# ── Customer discovery ───────────────────────────────────────────────────────

@router.get("/gdap/customers")
async def list_gdap_customers(user: User = _admin):
    """Discover all customers from Partner Center API."""
    from app.core.credentials import gdap_configured, get_secret

    if not gdap_configured():
        raise ValidationError("GDAP is not configured. Set up partner credentials first.")

    partner_tenant = get_secret("gdap", "partner_tenant_id")
    partner_client = get_secret("gdap", "partner_client_id")
    partner_secret = get_secret("gdap", "partner_client_secret")

    try:
        from app.integrations.partner_center import PartnerCenterClient
        async with PartnerCenterClient(partner_tenant, partner_client, partner_secret) as pc:
            customers = await pc.list_customers()
            relationships = await pc.list_gdap_relationships()
    except Exception as exc:
        logger.error("GDAP customer discovery failed: %s", exc)
        raise IntegrationError(f"Partner Center API error: {exc}")

    # Build relationship lookup by customer tenant ID
    rel_by_tenant: dict[str, dict] = {}
    for rel in relationships:
        cid = rel.get("customer", {}).get("tenantId", "")
        if cid:
            rel_by_tenant[cid] = {
                "status": rel.get("status", ""),
                "roles": [r.get("displayName", "") for r in rel.get("accessDetails", {}).get("unifiedRoles", [])],
            }

    # Match with local customer registry.
    #
    # Keying on TenantId alone found nothing: a customer imported from IT Glue
    # has a name and an org id and nothing else, so every tenant looked new and
    # importing would have created a duplicate of each one. The name is the
    # only thing the two systems share, so it is what they are joined on —
    # proposed, never assumed.
    from app.core.customer import CustomerManager
    from app.core.name_match import match_by_name

    locals_ = CustomerManager.list_customers()
    by_tenant = {
        (c.get("TenantId") or "").strip(): c
        for c in locals_
        if (c.get("TenantId") or "").strip()
    }
    unclaimed = [
        (c.get("CustomerName", ""), c)
        for c in locals_
        if not (c.get("TenantId") or "").strip() and c.get("CustomerName", "").strip()
    ]

    result = []
    for cust in customers:
        profile = cust.get("companyProfile", {})
        tid = profile.get("tenantId", cust.get("id", ""))
        name = profile.get("companyName", cust.get("companyName", ""))
        rel_info = rel_by_tenant.get(tid, {})

        local = by_tenant.get(tid)
        if local:
            match_confidence, match_score = "linked", 1.0
        else:
            local, match_score, match_confidence = match_by_name(name, unclaimed)

        result.append({
            "tenant_id": tid,
            "company_name": name,
            "domain": profile.get("domain", ""),
            "gdap_status": rel_info.get("status", "unknown"),
            "gdap_roles": rel_info.get("roles", []),
            "already_imported": match_confidence == "linked",
            # A proposal below "high" is shown but not offered for a bulk
            # import: enriching the wrong customer writes a tenant id onto a
            # company that does not own it.
            "match_confidence": match_confidence,
            "match_score": round(match_score, 3),
            "local_customer_id": local.get("_id", "") if local else "",
            "local_customer_name": local.get("CustomerName", "") if local else "",
            "local_auth_mode": local.get("AuthMode", "legacy") if local else "",
        })

    return {"customers": result, "total": len(result)}


# ── Import customers ─────────────────────────────────────────────────────────

@router.post("/gdap/import")
async def import_gdap_customers(request: Request, user: User = _admin):
    """Import selected GDAP customers into local customer registry."""
    from datetime import datetime, timezone

    from app.core.credentials import load_gdap_config, save_gdap_config
    from app.core.customer import CustomerManager

    body = await request.json()
    tenant_ids: list[str] = body.get("tenant_ids", [])
    # Optional {tenant_id: customer_id}: the operator accepting the discovery
    # endpoint's proposals. Absent, a tenant with no local match is created new.
    links: dict[str, str] = body.get("links") or {}
    if not tenant_ids:
        raise ValidationError("No tenant_ids provided")

    # Fetch full customer info from Partner Center
    from app.core.credentials import get_secret
    partner_tenant = get_secret("gdap", "partner_tenant_id")
    partner_client = get_secret("gdap", "partner_client_id")
    partner_secret = get_secret("gdap", "partner_client_secret")

    try:
        from app.integrations.partner_center import PartnerCenterClient
        async with PartnerCenterClient(partner_tenant, partner_client, partner_secret) as pc:
            all_customers = await pc.list_customers()
    except Exception as exc:
        raise IntegrationError(f"Partner Center API error: {exc}")

    # Index by tenant ID
    by_tenant = {}
    for c in all_customers:
        profile = c.get("companyProfile", {})
        tid = profile.get("tenantId", c.get("id", ""))
        by_tenant[tid] = {
            "company_name": profile.get("companyName", c.get("companyName", "")),
            "domain": profile.get("domain", ""),
        }

    imported = []
    skipped = []
    for tid in tenant_ids:
        info = by_tenant.get(tid)
        if not info:
            skipped.append({"tenant_id": tid, "reason": "Not found in Partner Center"})
            continue

        # A tenant id already on a customer settles it. Otherwise the caller
        # may name the customer this tenant belongs to — the discovery endpoint
        # proposes one, a person accepts it. Nothing is matched by name here:
        # writing a tenant id onto the wrong company hands one customer's
        # Conditional Access to another, and no confidence score is worth that.
        existing = None
        for c in CustomerManager.list_customers():
            if (c.get("TenantId") or "").strip() == tid:
                existing = c
                break

        if existing is None and links.get(tid):
            candidate = CustomerManager.get_customer(links[tid])
            if candidate is None:
                skipped.append({"tenant_id": tid, "reason": "Ukjent kunde i kobling"})
                continue
            claimed = (candidate.get("TenantId") or "").strip()
            if claimed and claimed != tid:
                skipped.append({
                    "tenant_id": tid,
                    "reason": f"Kunden har allerede tenant {claimed[:8]}…",
                })
                continue
            existing = candidate

        if existing:
            # Enrich rather than duplicate: the customer already carries its IT
            # Glue org id and any UniFi link, and a second record would split
            # that history in two.
            existing["TenantId"] = tid
            if info.get("domain"):
                if not (existing.get("PrimaryDomain") or "").strip():
                    existing["PrimaryDomain"] = info["domain"]
                if not (existing.get("InitialDomain") or "").strip():
                    existing["InitialDomain"] = info["domain"]
            existing["AuthMode"] = "gdap"
            CustomerManager.save_customer(
                {k: v for k, v in existing.items() if not k.startswith("_")}
            )
            imported.append({
                "tenant_id": tid,
                "company_name": info["company_name"],
                "customer_id": existing.get("_id", ""),
                "action": "enriched",
            })
        else:
            # Create new customer entry
            config = {
                "CustomerName": info["company_name"],
                "PrimaryDomain": info["domain"],
                "InitialDomain": info["domain"],
                "TenantId": tid,
                "ClientId": "",
                "AppObjectId": "",
                "SubscriptionId": "",
                "AuthMode": "gdap",
                "SetupDate": datetime.now(timezone.utc).isoformat(),
                "SecretExpiry": "",
                "CertExpiry": "",
            }
            cust_id = CustomerManager.save_customer(config)
            imported.append({
                "tenant_id": tid,
                "company_name": info["company_name"],
                "customer_id": cust_id,
                "action": "created",
            })

    # Update GDAP config with sync timestamp
    gdap_cfg = load_gdap_config() or {}
    gdap_cfg["last_customer_sync"] = datetime.now(timezone.utc).isoformat()
    save_gdap_config(gdap_cfg)

    logger.info("GDAP import: %d imported, %d skipped", len(imported), len(skipped))
    return {"imported": imported, "skipped": skipped}


# ── Refresh customer list ────────────────────────────────────────────────────

@router.post("/gdap/refresh")
async def refresh_gdap_customers(user: User = _admin):
    """Re-sync customer list from Partner Center and update local registry."""
    from app.core.credentials import get_secret, load_gdap_config, save_gdap_config
    from app.core.customer import CustomerManager

    if not (get_secret("gdap", "partner_client_secret")):
        raise ValidationError("GDAP is not configured")

    partner_tenant = get_secret("gdap", "partner_tenant_id")
    partner_client = get_secret("gdap", "partner_client_id")
    partner_secret = get_secret("gdap", "partner_client_secret")

    try:
        from app.integrations.partner_center import PartnerCenterClient
        async with PartnerCenterClient(partner_tenant, partner_client, partner_secret) as pc:
            customers = await pc.list_customers()
    except Exception as exc:
        raise IntegrationError(f"Partner Center API error: {exc}")

    # Update local GDAP customers with latest info from Partner Center
    local_gdap = {c.get("TenantId", ""): c for c in CustomerManager.list_customers()
                  if c.get("AuthMode") == "gdap"}

    updated = 0
    for cust in customers:
        profile = cust.get("companyProfile", {})
        tid = profile.get("tenantId", cust.get("id", ""))
        if tid in local_gdap:
            local = local_gdap[tid]
            new_name = profile.get("companyName", "")
            new_domain = profile.get("domain", "")
            if new_name and new_name != local.get("CustomerName"):
                local["CustomerName"] = new_name
                CustomerManager.save_customer(local)
                updated += 1
            if new_domain and new_domain != local.get("PrimaryDomain"):
                local["PrimaryDomain"] = new_domain
                CustomerManager.save_customer(local)
                updated += 1

    gdap_cfg = load_gdap_config() or {}
    gdap_cfg["last_customer_sync"] = datetime.now(timezone.utc).isoformat()
    gdap_cfg["customer_count"] = len(customers)
    save_gdap_config(gdap_cfg)

    return {
        "total_partner_customers": len(customers),
        "local_gdap_customers": len(local_gdap),
        "updated": updated,
    }
