"""ALSO Cloud Marketplace integration routes."""

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
from app.core.rbac import get_accessible_customer_ids
from app.core.utils import fire_and_forget
from app.models.user import Role, User
from app.web.i18n import ui_t
from app.web.middleware.auth import get_current_user, require_role

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Customer scoping (SR-002) ────────────────────────────────────────────────
#
# Every ALSO record belongs to a Sybr customer: a company is linked by its
# AlsoAccountId, and a renewal / subscription-detail row carries customer_id.
# An authenticated-but-restricted user must see only their assigned customers'
# data. get_accessible_customer_ids returns None for an unrestricted user
# (admin or the all-customers grant) and otherwise the assigned set — possibly
# empty, which means "no customers", not "all".


async def _customer_scope(user: User) -> tuple[set[str] | None, dict[str, str]]:
    """Return (allowed customer ids or None, {AlsoAccountId: customer_id})."""
    from app.core.customer import CustomerManager

    allowed = await get_accessible_customer_ids(user)
    acct_map: dict[str, str] = {}
    for c in CustomerManager.list_customers():
        aid = str(c.get("AlsoAccountId", "") or "")
        if aid:
            acct_map[aid] = c.get("_id", "")
    return allowed, acct_map


def _deny_unless_scoped(customer_id: str | None, allowed: set[str] | None) -> None:
    """Refuse with 404 unless the user may see this customer.

    404 rather than 403: answering "forbidden" for one id and "not found" for
    another lets a restricted caller map which accounts exist. An unrestricted
    user (allowed is None) always passes.
    """
    if allowed is None:
        return
    if not customer_id or customer_id not in allowed:
        raise NotFoundError("Ikke funnet")


async def _customer_for_subscription(sub_id: str) -> str | None:
    from app.core.database import get_db

    async with (
        get_db() as db,
        db.execute(
            "SELECT customer_id FROM also_renewals WHERE subscription_id = ? LIMIT 1",
            (str(sub_id),),
        ) as cur,
    ):
        row = await cur.fetchone()
        return row["customer_id"] if row else None


async def _customer_for_renewal(renewal_id: int) -> str | None:
    from app.core.database import get_db

    async with (
        get_db() as db,
        db.execute(
            "SELECT customer_id FROM also_renewals WHERE id = ?", (renewal_id,)
        ) as cur,
    ):
        row = await cur.fetchone()
        return row["customer_id"] if row else None


def _detect_term(row: dict, now=None) -> str | None:
    """Determine subscription term from service name patterns, with date fallback."""
    from datetime import datetime, timezone
    name = (row.get("service_display") or row.get("service_name") or "").lower()

    # NCE: Monthly if explicit, otherwise Annual (default NCE commitment)
    if "(nce)" in name:
        return "Monthly" if "monthly" in name else "Annual"
    if "monthly" in name:
        return "Monthly"
    if "azure plan" in name and "reserved" not in name:
        return "Pay-as-you-go"
    if "reserved" in name:
        return "Reserved"
    if "tenant" in name:
        return "Tenant"
    if "adobe" in name:
        return "Annual"

    # Fallback: remaining time until contract_end
    try:
        ce = row.get("contract_end", "")
        if ce:
            if now is None:
                now = datetime.now(timezone.utc)
            end = datetime.fromisoformat(ce.replace("Z", "+00:00"))
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            rem = (end.year - now.year) * 12 + (end.month - now.month)
            if rem <= 1:
                return "Monthly"
            if rem <= 14:
                return "Annual"
            if rem <= 38:
                return "3-Year"
            return "Long-term"
    except (ValueError, TypeError):
        pass
    return None


def _get_also_config() -> dict:
    """Load ALSO credentials from app settings."""
    from app.core.config import load_app_settings
    settings = load_app_settings()
    return {
        "username": settings.get("also_username", ""),
        "password": settings.get("also_password", ""),
        "country": settings.get("also_country", "no"),
    }


# Reuse a single client/session to avoid repeated GetSessionToken calls
# (ALSO rate-limits or blocks frequent auth attempts → 403)
_shared_client = None
_shared_client_cfg = None


async def _get_client():
    """Get a shared ALSO client, reusing the session token when possible."""
    global _shared_client, _shared_client_cfg
    from app.integrations.also_cloud import AlsoCloudClient, AlsoCloudError

    cfg = _get_also_config()
    if not cfg["username"] or not cfg["password"]:
        return None

    # If config changed or no client exists, create a new one
    if _shared_client is None or _shared_client_cfg != cfg:
        if _shared_client is not None:
            try:
                await _shared_client.close()
            except Exception as e:
                logger.debug("Closing old ALSO client failed: %s", e)
        _shared_client = AlsoCloudClient(cfg["username"], cfg["password"], cfg["country"])
        await _shared_client.authenticate()
        _shared_client_cfg = cfg
        return _shared_client

    # Verify session is still alive; re-auth if not
    try:
        await _shared_client.ping()
    except Exception as e:
        logger.debug("ALSO session ping failed, re-authenticating: %s", e)
        try:
            await _shared_client.authenticate()
        except Exception as e:
            logger.warning("ALSO re-authentication failed, performing full reset: %s", e)
            # Full reset
            try:
                await _shared_client.close()
            except Exception as e:
                logger.debug("Closing ALSO client during reset failed: %s", e)
            _shared_client = AlsoCloudClient(cfg["username"], cfg["password"], cfg["country"])
            await _shared_client.authenticate()
            _shared_client_cfg = cfg

    return _shared_client


@router.post("/also/test")
async def test_connection(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Test ALSO Cloud Marketplace connection."""
    from app.integrations.also_cloud import AlsoCloudClient, AlsoCloudError
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    country = body.get("country", "no").strip()

    if not username or not password:
        raise ValidationError("Brukernavn og passord er påkrevd")

    try:
        client = AlsoCloudClient(username, password, country)
        await client.authenticate()
        pong = await client.ping()
        await client.close()
        return {"ok": True, "ping": pong}
    except AlsoCloudError as e:
        raise ValidationError(str(e))
    except Exception as e:
        raise IntegrationError(f"Tilkobling feilet: {e}")


@router.get("/also/companies")
async def list_companies(user: User = Depends(get_current_user)):
    """List all end-customer companies from ALSO."""
    allowed, acct_map = await _customer_scope(user)
    try:
        client = await _get_client()
        if not client:
            raise ValidationError("ALSO er ikke konfigurert")
        companies = await client.get_companies()
        if allowed is not None:
            companies = [
                c for c in companies
                if acct_map.get(str(c.get("AccountId", "") or "")) in allowed
            ]
        return {"companies": companies, "count": len(companies)}
    except Exception as e:
        logger.warning("ALSO get_companies failed: %s", e)
        raise IntegrationError(str(e))


@router.get("/also/company/{account_id}")
async def get_company_detail(account_id: str, user: User = Depends(get_current_user)):
    """Get full company detail including subscription/service data."""
    allowed, acct_map = await _customer_scope(user)
    _deny_unless_scoped(acct_map.get(str(account_id)), allowed)
    try:
        client = await _get_client()
        if not client:
            raise ValidationError("ALSO er ikke konfigurert")
        company = await client.get_company(account_id)
        return {"company": company}
    except Exception as e:
        logger.warning("ALSO get_company failed: %s", e)
        raise IntegrationError(str(e))


@router.get("/also/api-stats")
async def also_api_stats(user: User = Depends(get_current_user)):
    """Get ALSO API usage stats for the current session."""
    from app.integrations.also_cloud import AlsoCloudClient
    return AlsoCloudClient.get_api_stats()


@router.get("/also/subscription/{account_id}")
async def get_subscription_detail(account_id: str, user: User = Depends(get_current_user)):
    """Get a single subscription with addons (fields, pricing). Auto-caches pricing."""
    allowed, acct_map = await _customer_scope(user)
    if allowed is not None:
        cid = acct_map.get(str(account_id)) or await _customer_for_subscription(account_id)
        _deny_unless_scoped(cid, allowed)
    try:
        client = await _get_client()
        if not client:
            raise ValidationError("ALSO er ikke konfigurert")
        sub = await client.get_subscription_with_addons(account_id)

        # Auto-cache pricing in DB (fire-and-forget)
        fire_and_forget(_cache_subscription_pricing(account_id, sub))

        return {"subscription": sub}
    except Exception as e:
        logger.warning("GetSubscriptionWithAddons(%s) failed: %s", account_id, e)
        # Fallback to basic GetSubscription
        try:
            sub = await client.get_subscription(account_id)
            return {"subscription": sub}
        except Exception as e2:
            raise IntegrationError(str(e2))


async def _cache_subscription_pricing(sub_id: str, sub: dict) -> None:
    """Cache pricing data from GetSubscriptionWithAddons into the DB."""
    import json
    from datetime import datetime, timezone

    from app.core.database import get_db

    fields = sub.get("Fields", sub.get("fields", []))
    items = sub.get("PriceableItems", sub.get("priceableItems", []))

    # Extract quantity: look for fields with numeric values that represent seat counts
    quantity = 0
    for f in (fields if isinstance(fields, list) else []):
        val = f.get("Value", f.get("value"))
        name = (f.get("Name", f.get("name", "")) or "").lower()
        if isinstance(val, (int, float)) and val > 0:
            # Prefer fields that look like seat counts
            if any(kw in name for kw in ("quantity", "seat", "license", "user", "count")):
                quantity = int(val)
                break
            elif quantity == 0:
                quantity = int(val)  # fallback to first numeric field

    # Extract pricing: sum purchase prices from PriceableItems
    unit_price = 0.0
    currency = ""
    for p in (items if isinstance(items, list) else []):
        pp = p.get("PurchasePrice", p.get("purchasePrice", 0))
        if pp and isinstance(pp, (int, float)):
            unit_price += float(pp)
        if not currency:
            currency = p.get("Currency", p.get("currency", ""))

    monthly_cost = unit_price * max(quantity, 1)

    # Find customer_id from also_renewals
    customer_id = ""
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id FROM also_renewals WHERE subscription_id = ? LIMIT 1",
                (sub_id,)
            ) as cur:
                row = await cur.fetchone()
                if row:
                    customer_id = row["customer_id"]
    except Exception as e:
        logger.debug("Could not find customer_id for subscription %s: %s", sub_id, e)

    now = datetime.now(timezone.utc).isoformat()
    try:
        async with get_db() as db:
            await db.execute("""
                INSERT INTO also_subscription_details
                    (subscription_id, customer_id, quantity, unit_price, monthly_cost, currency,
                     fields_json, priceable_items_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(subscription_id) DO UPDATE SET
                    quantity = excluded.quantity,
                    unit_price = excluded.unit_price,
                    monthly_cost = excluded.monthly_cost,
                    currency = excluded.currency,
                    fields_json = excluded.fields_json,
                    priceable_items_json = excluded.priceable_items_json,
                    cached_at = excluded.cached_at
            """, (
                sub_id, customer_id, quantity, unit_price, monthly_cost, currency,
                json.dumps(fields if isinstance(fields, list) else []),
                json.dumps(items if isinstance(items, list) else []),
                now,
            ))
            await db.commit()
        logger.info("Cached pricing for sub %s: qty=%d, price=%.2f, monthly=%.2f %s",
                     sub_id, quantity, unit_price, monthly_cost, currency)
    except Exception as e:
        logger.warning("Failed to cache pricing for %s: %s", sub_id, e)


@router.get("/also/subscriptions/{account_id}")
async def get_subscriptions(account_id: str, user: User = Depends(get_current_user)):
    """Get all subscriptions for a company.

    Tries GetSubscriptions first; if the API returns 500 (common when
    account_id is a company-level ID rather than a subscription ID),
    falls back to fetching the company detail which often embeds
    subscription/service data.
    """
    from app.integrations.also_cloud import AlsoCloudError
    allowed, acct_map = await _customer_scope(user)
    _deny_unless_scoped(acct_map.get(str(account_id)), allowed)
    try:
        client = await _get_client()
        if not client:
            raise ValidationError("ALSO er ikke konfigurert")

        subs = []
        # GetSubscriptions with parentAccountId (1 API call)
        try:
            subs = await client.get_subscriptions(account_id)
            logger.info("GetSubscriptions(parentAccountId=%s) returned %d items", account_id, len(subs) if isinstance(subs, list) else 0)
            # No raw provider payload in the logs — SR-002 criterion 5.
        except Exception as e:
            logger.info("GetSubscriptions(%s) failed: %s", account_id, e)

        # Auto-cache renewals in DB (fire-and-forget, don't block response)
        if subs:
            fire_and_forget(_cache_renewals(account_id, subs))

        # Enrich subscriptions with cached quantity/pricing from also_subscription_details
        if subs:
            try:
                from app.core.database import get_db
                # Try multiple ID fields — ALSO API uses different keys depending on endpoint
                sub_ids = []
                for s in subs:
                    sid = str(s.get("AccountId", "") or s.get("accountId", "") or s.get("Id", "") or s.get("id", "") or "")
                    if sid:
                        sub_ids.append(sid)
                logger.info("Enriching %d subscriptions with cached pricing", len(sub_ids))
                if sub_ids:
                    placeholders = ",".join("?" * len(sub_ids))
                    async with get_db() as db:
                        async with db.execute(
                            f"SELECT subscription_id, quantity, unit_price, monthly_cost, currency "
                            f"FROM also_subscription_details WHERE subscription_id IN ({placeholders})",
                            sub_ids,
                        ) as cur:
                            cached = {row["subscription_id"]: dict(row) for row in await cur.fetchall()}
                    logger.info("Found %d cached details for %d sub_ids", len(cached), len(sub_ids))
                    enriched = 0
                    for s in subs:
                        sid = str(s.get("AccountId", "") or s.get("accountId", "") or s.get("Id", "") or s.get("id", "") or "")
                        detail = cached.get(sid)
                        if detail:
                            s["Quantity"] = detail["quantity"] or 0
                            s["UnitPrice"] = detail["unit_price"] or 0
                            s["MonthlyCost"] = detail["monthly_cost"] or 0
                            s["Currency"] = detail["currency"] or ""
                            enriched += 1
                    logger.info("Enriched %d/%d subscriptions with cached qty/pricing", enriched, len(subs))
            except Exception as e:
                logger.warning("Could not enrich subscriptions with cached pricing: %s", e)

        return {"subscriptions": subs, "count": len(subs)}
    except Exception as e:
        logger.warning("ALSO get_subscriptions failed: %s", e)
        raise IntegrationError(str(e))


async def _cache_renewals(account_id: str, subs: list[dict]) -> None:
    """Cache subscription renewal data in the DB for the renewals action list."""
    from datetime import datetime, timezone

    from app.core.customer import CustomerManager
    from app.core.database import get_db

    # Find customer name from account_id
    customer_name = ""
    customer_id = ""
    for c in CustomerManager.list_customers():
        if str(c.get("AlsoAccountId", "")) == str(account_id):
            customer_name = c.get("CustomerName", "")
            customer_id = c.get("_id", "")
            break

    if not customer_id:
        return

    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        for s in subs:
            sub_id = str(s.get("AccountId", ""))
            if not sub_id:
                continue
            await db.execute("""
                INSERT INTO also_renewals
                    (customer_id, customer_name, subscription_id, service_name, service_display,
                     vendor, contract_id, contract_end, billing_start, account_state, scanned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(customer_id, subscription_id) DO UPDATE SET
                    service_display = excluded.service_display,
                    vendor = excluded.vendor,
                    contract_end = excluded.contract_end,
                    account_state = excluded.account_state,
                    scanned_at = excluded.scanned_at
            """, (
                customer_id, customer_name, sub_id,
                s.get("ServiceName", ""),
                s.get("ServiceDisplayName", ""),
                s.get("VendorDisplayName", ""),
                s.get("ContractId", ""),
                s.get("ContractEndDate", ""),
                s.get("BillingStartDate", ""),
                s.get("AccountState", "Active"),
                now,
            ))
        await db.commit()
    logger.info("Cached %d renewals for %s", len(subs), customer_name)


# ── Renewal action list ──────────────────────────────────────────────────────

@router.get("/also/renewals")
async def get_renewals(days: int = 90, user: User = Depends(get_current_user)):
    """Get cached renewal data — subscriptions expiring within N days."""
    from datetime import datetime, timedelta, timezone

    from app.core.database import get_db

    allowed, _ = await _customer_scope(user)
    now = datetime.now(timezone.utc)
    cutoff = (now + timedelta(days=days)).isoformat()

    async with get_db() as db:
        # LEFT JOIN pricing data from subscription_details cache
        async with db.execute("""
            SELECT r.*, d.quantity, d.unit_price, d.monthly_cost, d.currency
            FROM also_renewals r
            LEFT JOIN also_subscription_details d ON r.subscription_id = d.subscription_id
            WHERE r.contract_end != '' AND r.contract_end IS NOT NULL
            ORDER BY r.contract_end ASC
        """) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    # Scope to the customers this user may see, before any count or MRR is
    # computed from the rows (SR-002).
    if allowed is not None:
        rows = [r for r in rows if r.get("customer_id") in allowed]

    # Calculate days_left + term for each
    for r in rows:
        # Days left
        try:
            raw = r["contract_end"]
            if not raw:
                r["days_left"] = None
                r["term"] = None
                continue
            end = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            r["days_left"] = (end - now).days
        except (ValueError, TypeError):
            r["days_left"] = None

        # Term from service name (most reliable for Microsoft NCE)
        r["term"] = _detect_term(r, now)

    # Split into categories
    expired = [r for r in rows if r["days_left"] is not None and r["days_left"] < 0]
    urgent = [r for r in rows if r["days_left"] is not None and 0 <= r["days_left"] <= 30]
    soon = [r for r in rows if r["days_left"] is not None and 30 < r["days_left"] <= 60]
    upcoming = [r for r in rows if r["days_left"] is not None and 60 < r["days_left"] <= days]

    shown = expired + urgent + soon + upcoming
    # Include rows with no contract_end or null days_left as "unknown"
    unknown = [r for r in rows if r["days_left"] is None]
    beyond = [r for r in rows if r["days_left"] is not None and r["days_left"] > days]

    # MRR calculations
    total_mrr = sum(r.get("monthly_cost") or 0 for r in rows)
    priced_count = sum(1 for r in rows if r.get("monthly_cost"))
    currency = ""
    for r in rows:
        if r.get("currency"):
            currency = r["currency"]
            break

    # Auto-cache pricing for uncached subscriptions in the background
    uncached_ids = [
        r["subscription_id"] for r in rows
        if r.get("subscription_id") and not r.get("monthly_cost")
    ]
    if uncached_ids:
        fire_and_forget(_auto_cache_uncached_pricing(uncached_ids))

    return {
        "renewals": shown,
        "total": len(rows),
        "expired": len(expired),
        "urgent_30d": len(urgent),
        "soon_60d": len(soon),
        "upcoming": len(upcoming),
        "beyond": len(beyond),
        "unknown_date": len(unknown),
        "all_cached": len(rows),
        "total_mrr": round(total_mrr, 2),
        "priced_count": priced_count,
        "currency": currency,
    }


async def _auto_cache_uncached_pricing(uncached_ids: list[str]) -> None:
    """Background task: fetch and cache pricing for a small batch of uncached subscriptions."""
    import asyncio

    limit = min(len(uncached_ids), 10)
    batch = uncached_ids[:limit]
    logger.info("Auto-cache pricing: starting for %d uncached subscriptions", len(batch))
    scanned = 0
    errors = 0
    try:
        client = await _get_client()
        if not client:
            logger.info("Auto-cache pricing: ALSO client not available, skipping")
            return
        for sub_id in batch:
            try:
                detail = await client.get_subscription_with_addons(sub_id)
                await _cache_subscription_pricing(sub_id, detail)
                scanned += 1
            except Exception as e:
                errors += 1
                logger.warning("Auto-cache pricing failed for %s: %s", sub_id, e)
                if "403" in str(e) or "429" in str(e):
                    logger.warning("Auto-cache pricing: rate limit hit, stopping early")
                    break
            await asyncio.sleep(2)
    except Exception as e:
        logger.warning("Auto-cache pricing task error: %s", e)
    finally:
        logger.info("Auto-cache pricing: finished — %d cached, %d errors", scanned, errors)


# Per-user, not global (SR-002 criterion 6). The scan routes are admin-only,
# but a shared dict still showed one admin the customer names another admin's
# scan was walking, and let two concurrent scans overwrite each other. Keyed by
# user id; the running-set is a single-flight guard so one user cannot start two.
_IDLE_PROGRESS = {"scanned": 0, "errors": 0, "total": 0, "current": "", "done": True}
_scan_progress: dict[str, dict] = {}
_price_progress: dict[str, dict] = {}
_scans_running: set[str] = set()
_price_scans_running: set[str] = set()


@router.get("/also/renewal-scan/progress")
async def renewal_scan_progress(user: User = Depends(get_current_user)):
    """Poll this user's renewal-scan progress."""
    return _scan_progress.get(str(user.id), dict(_IDLE_PROGRESS))


@router.get("/also/price-scan/progress")
async def price_scan_progress(user: User = Depends(get_current_user)):
    """Poll this user's price-scan progress."""
    return _price_progress.get(str(user.id), dict(_IDLE_PROGRESS))


@router.post("/also/price-scan")
async def price_scan(request: Request, user: User = Depends(require_role(Role.admin))):
    """Fetch pricing for subscriptions that don't have cached prices yet.

    Batch of 15, 2s delay. Skips already-cached subscriptions.
    """
    import asyncio

    from app.core.database import get_db

    uid = str(user.id)

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    batch_size = min(int(body.get("batch_size", 15)), 25)
    delay = max(float(body.get("delay", 2)), 1.5)

    # Find subscriptions without pricing
    async with get_db() as db:
        async with db.execute("""
            SELECT r.subscription_id, r.service_display, r.customer_name
            FROM also_renewals r
            LEFT JOIN also_subscription_details d ON r.subscription_id = d.subscription_id
            WHERE d.subscription_id IS NULL
            LIMIT ?
        """, (batch_size,)) as cur:
            to_scan = [dict(r) for r in await cur.fetchall()]

    if not to_scan:
        return {"ok": True, "scanned": 0, "remaining": 0, "message": "All subscriptions already have pricing cached"}

    # Count total remaining
    async with get_db() as db:
        async with db.execute("""
            SELECT COUNT(*) as cnt FROM also_renewals r
            LEFT JOIN also_subscription_details d ON r.subscription_id = d.subscription_id
            WHERE d.subscription_id IS NULL
        """) as cur:
            total_remaining = (await cur.fetchone())["cnt"]

    client = await _get_client()
    if not client:
        raise ValidationError("ALSO er ikke konfigurert")

    if uid in _price_scans_running:
        raise ConflictError("En prisskanning kjører allerede")
    _price_scans_running.add(uid)
    _price_progress[uid] = {"scanned": 0, "errors": 0, "total": len(to_scan), "current": "", "done": False}

    scanned = 0
    errors = 0
    try:
        for i, sub in enumerate(to_scan):
            sub_id = sub["subscription_id"]
            _price_progress[uid] = {"scanned": i, "errors": errors, "total": len(to_scan), "current": sub.get("service_display", sub_id), "done": False}
            try:
                detail = await client.get_subscription_with_addons(sub_id)
                await _cache_subscription_pricing(sub_id, detail)
                scanned += 1
            except Exception as e:
                logger.warning("Price scan failed for %s: %s", sub_id, e)
                errors += 1
                if "403" in str(e) or "429" in str(e):
                    logger.warning("Rate limit hit — stopping price scan early")
                    break
            await asyncio.sleep(delay)

        _price_progress[uid] = {"scanned": scanned, "errors": errors, "total": len(to_scan), "current": "", "done": True}
    finally:
        _price_scans_running.discard(uid)

    remaining = total_remaining - len(to_scan)
    return {
        "ok": True,
        "scanned": scanned,
        "errors": errors,
        "remaining": max(0, remaining),
        "total": total_remaining,
    }


@router.post("/also/renewals/{renewal_id}/handle")
async def handle_renewal(renewal_id: int, request: Request, user: User = Depends(get_current_user)):
    """Mark a renewal as handled / add notes."""
    from app.core.database import get_db

    allowed, _ = await _customer_scope(user)
    cid = await _customer_for_renewal(renewal_id)
    if cid is None:
        raise NotFoundError("Fornyelse ikke funnet")
    _deny_unless_scoped(cid, allowed)
    body = await request.json()
    handled = body.get("handled", 1)
    notes = body.get("notes", "")

    async with get_db() as db:
        await db.execute(
            "UPDATE also_renewals SET handled = ?, notes = ? WHERE id = ?",
            (int(handled), notes, renewal_id)
        )
        await db.commit()
    return {"ok": True}


@router.post("/also/renewal-scan")
async def renewal_scan(request: Request, user: User = Depends(require_role(Role.admin))):
    """Scan ALSO-linked customers for renewal data.

    Scans in small batches (default 10) with 3s pauses between calls.
    Skips customers already scanned within the last 24h.
    Call multiple times to gradually fill the cache.
    """
    import asyncio
    from datetime import datetime, timedelta, timezone

    from app.core.customer import CustomerManager
    from app.core.database import get_db

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    batch_size = min(int(body.get("batch_size", 25)), 50)  # Max 50 per batch
    delay = max(float(body.get("delay", 1.5)), 1)  # Min 1s between calls

    customers = CustomerManager.list_customers()
    linked = [c for c in customers if c.get("AlsoAccountId")]

    if not linked:
        return {"ok": True, "scanned": 0, "message": "No ALSO-linked customers"}

    # Find which customers were already scanned recently (last 24h)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recently_scanned = set()
    async with get_db() as db:
        async with db.execute(
            "SELECT DISTINCT customer_id FROM also_renewals WHERE scanned_at > ?", (cutoff,)
        ) as cur:
            recently_scanned = {row["customer_id"] for row in await cur.fetchall()}

    # Filter to unscanned customers, take batch_size
    to_scan = [c for c in linked if c.get("_id", "") not in recently_scanned]
    batch = to_scan[:batch_size]

    if not batch:
        return {
            "ok": True, "scanned": 0, "errors": 0,
            "total_linked": len(linked),
            "already_cached": len(recently_scanned),
            "remaining": 0,
            "message": "All linked customers scanned within last 24h",
        }

    client = await _get_client()
    if not client:
        raise ValidationError("ALSO er ikke konfigurert")

    # Per-user progress + single-flight (SR-002).
    uid = str(user.id)
    if uid in _scans_running:
        raise ConflictError("En skanning kjører allerede")
    _scans_running.add(uid)
    _scan_progress[uid] = {"scanned": 0, "errors": 0, "total": len(batch), "current": "", "done": False}

    scanned = 0
    errors = 0
    try:
        for i, c in enumerate(batch):
            account_id = str(c["AlsoAccountId"])
            cname = c.get("CustomerName", "?")
            _scan_progress[uid] = {"scanned": i, "errors": errors, "total": len(batch), "current": cname, "done": False}
            try:
                subs = await client.get_subscriptions(account_id)
                if subs:
                    await _cache_renewals(account_id, subs)
                scanned += 1
            except Exception as e:
                logger.warning("Renewal scan failed for %s: %s", cname, e)
                errors += 1
                if "403" in str(e) or "429" in str(e) or "rate" in str(e).lower():
                    logger.warning("Rate limit hit — stopping scan early")
                    break

            # Rate limit pause
            await asyncio.sleep(delay)

        _scan_progress[uid] = {"scanned": scanned, "errors": errors, "total": len(batch), "current": "", "done": True}
    finally:
        _scans_running.discard(uid)

    remaining = len(to_scan) - len(batch)
    return {
        "ok": True,
        "scanned": scanned,
        "errors": errors,
        "total_linked": len(linked),
        "already_cached": len(recently_scanned),
        "remaining": remaining,
    }


@router.get("/also/renewals/report")
async def renewal_report_pdf(days: int = 90, user: User = Depends(get_current_user)):
    """Generate a PDF renewal report for all cached subscriptions."""
    from collections import OrderedDict
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    import jinja2
    import weasyprint
    from starlette.responses import Response

    from app.core.database import get_db

    allowed, _ = await _customer_scope(user)
    now = datetime.now(timezone.utc)

    async with get_db() as db:
        async with db.execute("""
            SELECT * FROM also_renewals
            WHERE contract_end != '' AND contract_end IS NOT NULL
            ORDER BY customer_name ASC, contract_end ASC
        """) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    if allowed is not None:
        rows = [r for r in rows if r.get("customer_id") in allowed]

    # Calculate days_left, term, status for each row
    for r in rows:
        # Days left
        try:
            raw = r["contract_end"]
            if not raw:
                r["days_left"] = None
                continue
            end = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            r["days_left"] = (end - now).days
        except (ValueError, TypeError):
            r["days_left"] = None

        # Term from service name (most reliable for Microsoft NCE)
        r["term"] = _detect_term(r, now)

    # Filter to within requested window + expired
    filtered = [r for r in rows if r["days_left"] is not None and r["days_left"] <= days]

    # Counters
    expired_count = sum(1 for r in filtered if r["days_left"] < 0)
    urgent_count = sum(1 for r in filtered if 0 <= r["days_left"] <= 30)
    soon_count = sum(1 for r in filtered if 30 < r["days_left"] <= 60)

    # Build template data grouped by customer
    grouped: OrderedDict[str, list] = OrderedDict()
    for r in filtered:
        cname = r.get("customer_name") or "Unknown"
        dl = r["days_left"]
        if dl < 0:
            status, color = "Expired", "#c0392b"
        elif dl <= 30:
            status, color = "Critical", "#c0392b"
        elif dl <= 60:
            status, color = "Warning", "#e67e22"
        else:
            status, color = "OK", "#27ae60"

        # Format renewal date
        try:
            raw = r["contract_end"]
            rd = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            renewal_date = rd.strftime("%Y-%m-%d")
        except (ValueError, TypeError) as e:
            logger.debug("Could not parse contract_end date: %s", e)
            renewal_date = r.get("contract_end", "-")

        grouped.setdefault(cname, []).append({
            "product": r.get("service_display") or r.get("service_name") or "-",
            "vendor": r.get("vendor") or "-",
            "term": r.get("term"),
            "renewal_date": renewal_date,
            "days_left": dl,
            "status": status,
            "status_color": color,
        })

    # Render template
    template_dir = Path(__file__).resolve().parent.parent.parent / "reports" / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    template = env.get_template("renewal_report.html")
    html = template.render(
        generated_date=now.strftime("%Y-%m-%d %H:%M UTC"),
        total=len(filtered),
        expired_count=expired_count,
        urgent_count=urgent_count,
        soon_count=soon_count,
        grouped=grouped,
    )

    # Generate PDF
    pdf_bytes = weasyprint.HTML(string=html).write_pdf()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=renewal_report.pdf"},
    )


@router.get("/also/invoices")
async def get_invoices(user: User = Depends(require_role(Role.admin))):
    """Get current month invoices.

    Provider-wide preview invoices carry no field that maps a line to a Sybr
    customer, so they cannot be safely customer-scoped and are admin-only
    rather than filtered (SR-002 criterion 4).
    """
    try:
        client = await _get_client()
        if not client:
            raise ValidationError("ALSO er ikke konfigurert")
        invoices = await client.get_preview_invoices()
        return {"invoices": invoices, "count": len(invoices)}
    except Exception as e:
        logger.warning("ALSO get_invoices failed: %s", e)
        raise IntegrationError(str(e))


@router.get("/also/sync-preview")
async def sync_preview(user: User = Depends(require_role(Role.admin))):
    """Preview ALSO ↔ Toolkit customer matching before importing."""
    from app.core.customer import CustomerManager

    try:
        client = await _get_client()
        if not client:
            raise ValidationError("ALSO er ikke konfigurert")

        companies = await client.get_companies()

        existing = CustomerManager.list_customers()

        # Build lookup by normalized name and domain
        existing_names = {}
        existing_domains = {}
        for c in existing:
            name = c.get("CustomerName", "")
            domain = c.get("PrimaryDomain", "")
            # Handle domain being a list or string
            if isinstance(domain, list):
                domain = domain[0] if domain else ""
            if not isinstance(name, str):
                name = str(name) if name else ""
            if not isinstance(domain, str):
                domain = str(domain) if domain else ""
            if name:
                existing_names[name.lower().strip()] = c
            if domain:
                existing_domains[domain.lower().strip()] = c

        results = []
        for comp in companies:
            name = comp.get("CompanyName") or comp.get("Name") or comp.get("AccountName", "")
            if not name:
                continue

            email = comp.get("Email", "") or ""
            domain = comp.get("Domain", "") or ""
            if isinstance(name, list): name = name[0] if name else ""
            if isinstance(email, list): email = email[0] if email else ""
            if isinstance(domain, list): domain = domain[0] if domain else ""
            name = str(name)
            email = str(email)
            domain = str(domain)
            if not domain and "@" in email:
                domain = email.split("@")[-1]

            also_id = comp.get("AccountId", "")

            # Try matching
            match = None
            match_type = None

            # Exact name match
            if name.lower().strip() in existing_names:
                match = existing_names[name.lower().strip()]
                match_type = "exact_name"
            # Domain match
            elif domain and domain.lower().strip() in existing_domains:
                match = existing_domains[domain.lower().strip()]
                match_type = "domain"
            # Fuzzy name match (contains)
            else:
                name_lower = name.lower().strip()
                for ename, ecust in existing_names.items():
                    if name_lower in ename or ename in name_lower:
                        match = ecust
                        match_type = "fuzzy_name"
                        break

            results.append({
                "also_name": name,
                "also_id": also_id,
                "also_domain": domain,
                "also_email": email,
                "match": {
                    "toolkit_name": match.get("CustomerName", "") if match else None,
                    "toolkit_id": match.get("_id", "") if match else None,
                    "match_type": match_type,
                } if match else None,
                "status": "matched" if match else "new",
            })

        matched = sum(1 for r in results if r["status"] == "matched")
        new = sum(1 for r in results if r["status"] == "new")

        return {
            "also_total": len(results),
            "matched": matched,
            "new": new,
            "toolkit_total": len(existing),
            "customers": results,
        }

    except Exception as e:
        logger.error("ALSO sync preview failed: %s", e)
        raise IntegrationError(str(e))


@router.post("/also/link-matched")
async def link_matched(request: Request, user: User = Depends(require_role(Role.admin))):
    """Write AlsoAccountId to existing matched customers so licenses become visible."""
    from pathlib import Path

    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_read_json, encrypted_write_json

    body = await request.json()
    matches = body.get("matches", [])  # [{toolkit_id, also_id}]
    if not matches:
        raise ValidationError("Ingen treff oppgitt")

    linked = 0
    for m in matches:
        toolkit_id = str(m.get("toolkit_id", "") or "").strip()
        also_id = str(m.get("also_id", "") or "").strip()
        if not toolkit_id or not also_id:
            continue
        try:
            from app.core.customer import _CUSTOMERS_DIR
            cfg_path = _CUSTOMERS_DIR / toolkit_id / "config.json"
            if not cfg_path.exists():
                continue
            config = encrypted_read_json(cfg_path)
            if config.get("AlsoAccountId") == also_id:
                linked += 1  # Already linked
                continue
            config["AlsoAccountId"] = also_id
            encrypted_write_json(cfg_path, config)
            linked += 1
        except Exception as e:
            logger.warning("Failed to link ALSO account %s to %s: %s", also_id, toolkit_id, e)

    from app.core.activity_log import log_activity
    log_activity("also_link", detail=f"Linked {linked} customers to ALSO accounts", user=user.username)

    return {"ok": True, "linked": linked}


@router.post("/also/sync-customers")
async def sync_customers(request: Request, user: User = Depends(require_role(Role.admin))):
    """Import selected new companies from ALSO to MSP Toolkit."""
    from app.core.customer import CustomerManager

    body = await request.json()
    to_import = body.get("customers", [])  # List of {name, domain, also_id}

    if not to_import:
        raise ValidationError(ui_t("err_no_customers_selected", request))

    imported = 0
    failed = 0

    for comp in to_import:
        name = comp.get("name", "").strip()
        if not name:
            continue
        try:
            CustomerManager.save_customer({
                "CustomerName": name,
                "PrimaryDomain": comp.get("domain", ""),
                "AlsoAccountId": comp.get("also_id", ""),
                "Source": "also_cloud",
            })
            imported += 1
        except Exception as e:
            logger.warning("Failed to import ALSO customer %s: %s", name, e)
            failed += 1

    from app.core.activity_log import log_activity
    log_activity("also_sync", detail=f"Imported {imported}, failed {failed}", user=user.username)

    return {"ok": True, "imported": imported, "failed": failed}


# ── License optimization ────────────────────────────────────────────────────


def _normalize_product_name(service_display: str) -> str:
    """Collapse ALSO service display names to a canonical M365 product name.

    E.g. "Microsoft 365 Business Premium (NCE) Annual" -> "Microsoft 365 Business Premium"
    """
    name = service_display or ""
    # Strip common suffixes
    for suffix in ("(NCE)", "(nce)", "Annual", "Monthly", "annual", "monthly"):
        name = name.replace(suffix, "")
    name = name.strip().rstrip("-").strip()
    return name


@router.get("/also/license-optimization")
async def license_optimization(user: User = Depends(get_current_user)):
    """Compare ALSO-paid M365 licenses with actual assigned users from audit data.

    Joins also_renewals + also_subscription_details (paid qty / unit price)
    with audit_metrics (total_users) and per-customer license files (assigned
    counts per SKU) to identify over-licensed, under-licensed, and unused seats.
    """
    from collections import defaultdict

    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager
    from app.core.database import get_db

    allowed, _ = await _customer_scope(user)
    audit_dir = get_audit_dir()

    # 1. Fetch all Microsoft subscriptions with pricing from ALSO cache
    async with get_db() as db:
        async with db.execute("""
            SELECT r.customer_id, r.customer_name, r.subscription_id,
                   r.service_display, r.vendor, r.account_state,
                   d.quantity, d.unit_price, d.monthly_cost, d.currency
            FROM also_renewals r
            LEFT JOIN also_subscription_details d ON r.subscription_id = d.subscription_id
            WHERE LOWER(r.vendor) LIKE '%microsoft%'
              AND LOWER(r.account_state) = 'active'
              AND (d.quantity IS NULL OR d.quantity > 0)
            ORDER BY r.customer_name ASC
        """) as cur:
            also_rows = [dict(r) for r in await cur.fetchall()]

    if allowed is not None:
        also_rows = [r for r in also_rows if r.get("customer_id") in allowed]

    if not also_rows:
        return {
            "customers": [],
            "summary": {
                "total_waste": 0,
                "over_licensed_count": 0,
                "under_licensed_count": 0,
                "optimal_count": 0,
                "currency": "NOK",
            },
        }

    # 2. Fetch latest audit metrics per customer from DB
    async with get_db() as db:
        async with db.execute("""
            SELECT customer_id, customer_name, total_users, metrics_json, audit_date
            FROM audit_metrics
            ORDER BY audit_date DESC
        """) as cur:
            audit_rows = [dict(r) for r in await cur.fetchall()]

    # Deduplicate — keep latest per customer_id
    audit_by_customer: dict[str, dict] = {}
    for ar in audit_rows:
        cid = ar["customer_id"]
        if cid and cid not in audit_by_customer:
            audit_by_customer[cid] = ar

    # 3. Try to read license files from latest audit runs for detailed SKU data
    license_data_by_customer: dict[str, list[dict]] = {}
    customers_list = CustomerManager.list_customers()
    customer_name_map = {c.get("_id", ""): c.get("CustomerName", "") for c in customers_list}

    for cid, cname in customer_name_map.items():
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in cname)
        customer_dir = audit_dir / safe_name
        if not customer_dir.exists():
            continue
        runs = sorted([d for d in customer_dir.iterdir() if d.is_dir()], reverse=True)
        for run_dir in runs:
            lic_path = run_dir / "02_licenses.txt"
            if lic_path.exists():
                try:
                    from app.core.encryption import encrypted_read_text
                    try:
                        text = encrypted_read_text(lic_path)
                    except Exception as e:
                        logger.debug("Encrypted read failed for %s, falling back to plain read: %s", lic_path, e)
                        text = lic_path.read_text(encoding="utf-8", errors="replace")
                    from app.reports.generator import _parse_licenses
                    parsed = _parse_licenses(text)
                    if parsed:
                        license_data_by_customer[cid] = parsed
                except Exception as e:
                    logger.warning("Failed to parse license file for customer %s: %s", cid, e)
                break  # only need latest run

    # 4. Group ALSO subscriptions by customer, then by normalized product
    customers_data: dict[str, dict] = {}
    for row in also_rows:
        cid = row["customer_id"]
        if cid not in customers_data:
            customers_data[cid] = {
                "customer_id": cid,
                "customer_name": row["customer_name"],
                "products": defaultdict(lambda: {
                    "paid_qty": 0, "unit_price": 0.0, "monthly_cost": 0.0,
                    "currency": "", "sub_ids": [],
                }),
            }
        product = _normalize_product_name(row["service_display"])
        p = customers_data[cid]["products"][product]
        qty = row["quantity"] or 0
        up = row["unit_price"] or 0.0
        mc = row["monthly_cost"] or 0.0
        p["paid_qty"] += qty
        p["monthly_cost"] += mc
        if up > 0:
            p["unit_price"] = up  # use the latest non-zero
        if row["currency"]:
            p["currency"] = row["currency"]
        p["sub_ids"].append(row["subscription_id"])

    # 5. Build response — cross-reference with audit data
    result_customers = []
    summary_total_waste = 0.0
    summary_over = 0
    summary_under = 0
    summary_optimal = 0
    currency = "NOK"

    for cid, cdata in sorted(customers_data.items(), key=lambda x: x[1]["customer_name"]):
        audit = audit_by_customer.get(cid, {})
        total_users = audit.get("total_users", 0) or 0
        license_files = license_data_by_customer.get(cid, [])

        # Build a lookup from license file SKU name -> assigned (used) count
        sku_assigned: dict[str, int] = {}
        sku_total: dict[str, int] = {}
        for lf in license_files:
            sku_assigned[lf["part"]] = lf["used"]
            sku_total[lf["part"]] = lf["total"]

        customer_licenses = []
        customer_waste = 0.0
        customer_paid_total = 0
        customer_assigned_total = 0

        for product, pdata in sorted(cdata["products"].items()):
            paid_qty = pdata["paid_qty"]
            unit_price = pdata["unit_price"]
            mc = pdata["monthly_cost"]
            if pdata["currency"]:
                currency = pdata["currency"]

            # Try to match ALSO product to audit license SKU
            assigned_qty = 0
            active_users = 0
            matched_sku = False

            # Try exact/fuzzy match against license file SKUs
            product_lower = product.lower()
            for sku_name, used_count in sku_assigned.items():
                sku_lower = sku_name.lower()
                # Fuzzy match: check if significant words overlap
                if (sku_lower in product_lower or product_lower in sku_lower
                        or _sku_match(product_lower, sku_lower)):
                    assigned_qty = used_count
                    active_users = used_count  # best approximation
                    matched_sku = True
                    break

            # Fallback: if no SKU match but we have audit data, use total_users
            if not matched_sku and total_users > 0 and paid_qty > 0:
                # For primary M365 suites, total_users is a reasonable proxy
                if any(kw in product_lower for kw in ("business", "e3", "e5", "enterprise", "365")):
                    assigned_qty = total_users
                    active_users = total_users

            # Calculate effective unit price if we only have monthly_cost
            if unit_price <= 0 and paid_qty > 0 and mc > 0:
                unit_price = mc / paid_qty

            # Determine status
            if paid_qty <= 0:
                continue  # skip zero-quantity

            if assigned_qty <= 0 and not matched_sku and total_users <= 0:
                status = "no_audit_data"
                excess = 0
                monthly_waste = 0.0
            elif assigned_qty <= 0:
                status = "unused"
                excess = paid_qty
                monthly_waste = mc if mc > 0 else paid_qty * unit_price
            elif paid_qty > assigned_qty:
                status = "over_licensed"
                excess = paid_qty - assigned_qty
                monthly_waste = excess * unit_price
            elif assigned_qty > paid_qty:
                status = "under_licensed"
                excess = assigned_qty - paid_qty
                monthly_waste = 0.0  # not a waste, but a risk
            else:
                status = "optimal"
                excess = 0
                monthly_waste = 0.0

            monthly_waste = round(monthly_waste, 2)

            if status == "over_licensed":
                summary_over += 1
                customer_waste += monthly_waste
            elif status == "under_licensed":
                summary_under += 1
            elif status == "optimal":
                summary_optimal += 1

            customer_paid_total += paid_qty
            customer_assigned_total += assigned_qty

            customer_licenses.append({
                "product": product,
                "paid_qty": paid_qty,
                "assigned_qty": assigned_qty,
                "active_users": active_users,
                "status": status,
                "excess": excess,
                "monthly_waste": monthly_waste,
                "unit_price": round(unit_price, 2),
            })

        # Sort by waste descending
        customer_licenses.sort(key=lambda x: x["monthly_waste"], reverse=True)

        summary_total_waste += customer_waste

        result_customers.append({
            "customer_id": cid,
            "customer_name": cdata["customer_name"],
            "licenses": customer_licenses,
            "total_monthly_waste": round(customer_waste, 2),
            "total_paid": customer_paid_total,
            "total_assigned": customer_assigned_total,
            "has_audit_data": cid in audit_by_customer,
        })

    # Sort customers by waste descending
    result_customers.sort(key=lambda x: x["total_monthly_waste"], reverse=True)

    return {
        "customers": result_customers,
        "summary": {
            "total_waste": round(summary_total_waste, 2),
            "over_licensed_count": summary_over,
            "under_licensed_count": summary_under,
            "optimal_count": summary_optimal,
            "currency": currency,
        },
    }


def _sku_match(also_product: str, audit_sku: str) -> bool:
    """Fuzzy-match an ALSO product name with an audit license SKU name.

    Matches on key M365 product keywords to bridge naming differences
    between ALSO (e.g. "Microsoft 365 Business Premium") and Graph API
    SKU names (e.g. "Microsoft 365 Business Premium" or "SPB").
    """
    # Extract key tokens
    keywords = {
        "business basic", "business standard", "business premium",
        "e1", "e3", "e5", "f1", "f3",
        "exchange online", "power bi", "visio", "project",
        "defender", "intune", "copilot", "teams",
        "enterprise mobility", "ems",
    }
    for kw in keywords:
        if kw in also_product and kw in audit_sku:
            return True
    return False
