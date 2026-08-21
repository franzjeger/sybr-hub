"""Uniweb hosting provider integration routes.

Provides REST endpoints for triggering Uniweb scrape syncs, viewing
cached account data, and matching Uniweb accounts to MSP Toolkit customers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, Request

from app.core.config import load_app_settings, update_app_settings
from app.core.database import get_db
from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.core.utils import fire_and_forget
from app.models.user import Role, User
from app.web.middleware.auth import get_current_user, require_customer_access, require_role

_auth = Depends(get_current_user)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Sync state (in-memory) ──────────────────────────────────────────────────
_sync_status = {
    "running": False,
    "last_sync": None,
    "last_error": None,
    "accounts_synced": 0,
    "total_accounts": 0,
    "current_account": "",
    "domains_found": 0,
    "errors_count": 0,
    "sync_start_time": None,
}


def _get_uniweb_config() -> dict:
    """Load Uniweb credentials from app settings."""
    settings = load_app_settings()
    return {
        "email": settings.get("uniweb_email", ""),
        "password": settings.get("uniweb_password", ""),
    }


# ── Partner API (structured, replaces the scraper for reads) ─────────────────
# The Partner API reuses the control-panel login: harvest the session cookies
# once and hold them, re-logging in only when the API says they expired (401).
# A login spins up headless Chrome, so doing it per request would be wasteful.
_partner_cookies: dict[str, str] | None = None
_partner_lock = asyncio.Lock()


async def _harvest_partner_cookies() -> dict[str, str]:
    """Log in to the control panel (headless Chrome, in a thread) and return the
    session/grant cookies the Partner API authenticates with."""
    cfg = _get_uniweb_config()
    if not cfg["email"] or not cfg["password"]:
        raise ValidationError("Uniweb-legitimasjon er ikke konfigurert")

    def _login_and_harvest() -> dict[str, str]:
        from app.services.uniweb_client import UniwebClient
        client = UniwebClient()
        try:
            if not client.login(cfg["email"], cfg["password"]):
                raise IntegrationError("Innlogging til Uniweb feilet")
            return client.harvest_cookies()
        finally:
            client.close()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _login_and_harvest)


async def _partner_call(fn):
    """Run a Partner API call with the cached session, re-logging in once if the
    session has expired. ``fn`` takes a UniwebPartnerClient and returns a value.
    """
    from app.services.uniweb_partner import UniwebAuthError, UniwebPartnerClient

    global _partner_cookies
    async with _partner_lock:
        if not _partner_cookies:
            _partner_cookies = await _harvest_partner_cookies()
    cookies = _partner_cookies
    try:
        async with UniwebPartnerClient(cookies) as client:
            return await fn(client)
    except UniwebAuthError:
        # The cached session expired — re-login once and retry.
        async with _partner_lock:
            _partner_cookies = await _harvest_partner_cookies()
        async with UniwebPartnerClient(_partner_cookies) as client:
            return await fn(client)


def _subscription_summary(customer_id: str, subs: list[dict]) -> dict:
    """Project subscriptions to their non-secret fields and total the margin.

    Pure, so the projection (never a ``tsig`` or private key) and the revenue /
    cost / margin arithmetic are unit-tested without a login or a database.
    """
    from app.services.uniweb_partner import public_subscription

    revenue = sum(float(s.get("rc") or 0) for s in subs)
    cost = sum(float(s.get("inRc") or 0) for s in subs)
    return {
        "matched": True,
        "customer_id": customer_id,
        "count": len(subs),
        "monthly_revenue": round(revenue, 2),
        "monthly_cost": round(cost, 2),
        "monthly_margin": round(revenue - cost, 2),
        "subscriptions": [public_subscription(s) for s in subs],
    }


def _product_category(product: dict) -> str:
    """The alert ``type`` the Hub renders — domain / ssl / subscription.

    Derived from the subscription's product ``code`` so a ``.no`` domain reads
    as a domain and a certificate as SSL; everything else (web, mail, …) is a
    generic subscription, matching the three labels the frontend knows.
    """
    code = str((product or {}).get("code") or "").lower()
    if code == "dns":
        return "domain"
    if "ssl" in code or "cert" in code:
        return "ssl"
    return "subscription"


def _expiry_items(
    subs: list[dict], accounts: dict[str, dict], now: datetime, max_days: int
) -> list[dict]:
    """Expiring subscriptions from the live Partner list, soonest first.

    ``period.to`` is the authoritative renewal date — no scraped date strings.
    ``accounts`` maps a Uniweb customer id to its resolved
    ``{customer_id, customer_name, account_name}`` so each item carries the
    Sybr customer it belongs to; unmatched services fall back to their own
    name rather than vanishing. Pure, so the date arithmetic and the
    customer-name resolution are unit-tested without a login.
    """
    items: list[dict] = []
    for sub in subs:
        period = sub.get("period") or {}
        to = str(period.get("to") or "").strip()
        if len(to) < 10:
            continue
        try:
            exp = datetime.fromisoformat(to[:10]).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        days = (exp - now).days
        if days > max_days:
            continue
        acct = accounts.get(str(sub.get("customer"))) or {}
        item_name = str(sub.get("username") or (sub.get("product") or {}).get("text") or "")
        items.append({
            "type": _product_category(sub.get("product") or {}),
            "customer_name": acct.get("customer_name") or item_name or "Uniweb",
            "customer_id": acct.get("customer_id") or "",
            "uniweb_account": acct.get("account_name") or "",
            "item_name": item_name,
            "expiry_date": to[:10],
            "days_remaining": days,
            "category": "critical" if days < 7 else "warning" if days < 14 else "upcoming",
        })
    items.sort(key=lambda x: x["days_remaining"])
    return items


@router.get("/uniweb/partner/subscriptions/{customer_id}")
async def uniweb_partner_subscriptions(
    customer_id: str, user: User = Depends(require_customer_access(Role.technician))
):
    """Structured subscriptions for the Uniweb account bound to this customer.

    ``customer_id`` is a Sybr customer, scoped by ``require_customer_access``;
    the bound Uniweb account is resolved from ``uniweb_accounts`` and its id used
    against the Partner API. The JSON replacement for the scraped service list:
    each subscription is projected to its non-secret fields (never a ``tsig`` or
    a private key), with a monthly revenue / cost / margin summary from ``rc``
    and ``inRc``.
    """
    async with get_db() as db, db.execute(
        "SELECT id FROM uniweb_accounts WHERE customer_id = ?", (customer_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return {"matched": False}

    subs = await _partner_call(lambda c: c.subscriptions_for_customer(row["id"]))
    return _subscription_summary(customer_id, subs)


# ── Sync endpoint ───────────────────────────────────────────────────────────

@router.post("/uniweb/sync")
async def uniweb_sync(user: User = Depends(require_role(Role.technician))):
    """Trigger a full Uniweb sync as a background task."""
    if _sync_status["running"]:
        return {"ok": False, "error": "Synkronisering kjorer allerede"}

    cfg = _get_uniweb_config()
    if not cfg["email"] or not cfg["password"]:
        raise ValidationError("Uniweb-legitimasjon er ikke konfigurert")

    fire_and_forget(_run_sync(cfg["email"], cfg["password"]))
    return {"ok": True, "message": "Synkronisering startet"}


async def _run_sync(email: str, password: str) -> None:
    """Background sync task — runs the Uniweb scraper in a thread."""
    global _sync_status
    _sync_status["running"] = True
    _sync_status["last_error"] = None
    _sync_status["accounts_synced"] = 0
    _sync_status["current_account"] = ""
    _sync_status["domains_found"] = 0
    _sync_status["errors_count"] = 0
    _sync_status["sync_start_time"] = datetime.now(timezone.utc).isoformat()

    try:
        from app.services.uniweb_client import UniwebClient, UniwebScrapeError

        def _do_sync():
            client = UniwebClient()
            try:
                if not client.login(email, password):
                    raise RuntimeError("Innlogging til Uniweb feilet")

                # List accounts first for progress tracking
                try:
                    accounts = client.list_accounts()
                except UniwebScrapeError as exc:
                    # Not zero accounts. The page did not parse, and a sync
                    # that reports "0 customers" here would look like a
                    # successful run against an empty portal.
                    raise RuntimeError(f"Uniweb: {exc}") from exc
                _sync_status["total_accounts"] = len(accounts)
                _sync_status["partner_rows"] = getattr(client, "last_partner_rows", None)
                _sync_status["current_account"] = "Henter kontoliste..."

                results = []
                for i, acct in enumerate(accounts):
                    _sync_status["accounts_synced"] = i
                    _sync_status["current_account"] = acct.get("name", "?")

                    # An account that could not be read gets no data key.
                    # Writing empty lists made "we could not open this page"
                    # indistinguishable from "this customer has no domains",
                    # and the second is a claim about the customer.
                    try:
                        if client.select_account(acct):
                            acct["data"] = client.scrape_account_data()
                            _sync_status["domains_found"] += len(
                                acct["data"].get("domains", [])
                            )
                        else:
                            acct["unavailable"] = "Could not enter the account page."
                            _sync_status["errors_count"] += 1
                    except UniwebScrapeError as exc:
                        acct["unavailable"] = str(exc)[:300]
                        _sync_status["errors_count"] += 1

                    results.append(acct)

                _sync_status["accounts_synced"] = len(results)
                _sync_status["current_account"] = ""
                return results
            finally:
                client.close()

        # Run blocking scraper in thread pool
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _do_sync)

        _sync_status["total_accounts"] = len(results)

        # Store results in database
        now = datetime.now(timezone.utc).isoformat()
        async with get_db() as db:
            for account in results:
                # Preserve existing customer_id mapping
                async with db.execute(
                    "SELECT customer_id FROM uniweb_accounts WHERE id = ?",
                    (account["id"],),
                ) as cur:
                    row = await cur.fetchone()
                    existing_customer_id = row["customer_id"] if row else None

                # Include parent info in data_json for sub-customers
                data_to_store = dict(account["data"])
                if account.get("parent_id"):
                    data_to_store["parent_id"] = account["parent_id"]
                    data_to_store["parent_name"] = account.get("parent_name", "")

                await db.execute(
                    """INSERT INTO uniweb_accounts (id, name, customer_id, last_sync, data_json)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                           name = excluded.name,
                           last_sync = excluded.last_sync,
                           data_json = excluded.data_json""",
                    (
                        account["id"],
                        account["name"],
                        existing_customer_id,
                        now,
                        json.dumps(data_to_store, ensure_ascii=False),
                    ),
                )
                _sync_status["accounts_synced"] += 1

            await db.commit()

        # Auto-match by name similarity
        await _auto_match_accounts()

        _sync_status["last_sync"] = now
        logger.info("Uniweb sync complete: %d accounts", len(results))

    except Exception as e:
        _sync_status["last_error"] = str(e)
        logger.error("Uniweb sync failed: %s", e)
    finally:
        _sync_status["running"] = False


async def _auto_match_accounts() -> int:
    """Auto-match unmatched Uniweb accounts to MSP customers by name similarity."""
    from app.core.customer import CustomerManager

    customers = CustomerManager.list_customers()
    if not customers:
        return 0

    matched_count = 0
    async with get_db() as db:
        async with db.execute(
            "SELECT id, name FROM uniweb_accounts WHERE customer_id IS NULL"
        ) as cur:
            unmatched = await cur.fetchall()

        for row in unmatched:
            uniweb_name = row["name"].lower().strip()
            best_match = None
            best_score = 0.0

            for cust in customers:
                cust_name = cust.get("CustomerName", "").lower().strip()
                if not cust_name:
                    continue

                # Exact match
                if uniweb_name == cust_name:
                    best_match = cust
                    best_score = 1.0
                    break

                # Contains match
                if uniweb_name in cust_name or cust_name in uniweb_name:
                    score = 0.85
                    if score > best_score:
                        best_match = cust
                        best_score = score
                    continue

                # Fuzzy match (Levenshtein-based via SequenceMatcher)
                score = SequenceMatcher(None, uniweb_name, cust_name).ratio()
                if score > best_score:
                    best_match = cust
                    best_score = score

            # Only auto-match if confidence is high enough (>= 0.75)
            if best_match and best_score >= 0.75:
                cust_id = best_match.get("_id", "")
                if cust_id:
                    await db.execute(
                        "UPDATE uniweb_accounts SET customer_id = ? WHERE id = ?",
                        (cust_id, row["id"]),
                    )
                    matched_count += 1
                    logger.info(
                        "Auto-matched Uniweb '%s' -> customer '%s' (score=%.2f)",
                        row["name"],
                        best_match.get("CustomerName"),
                        best_score,
                    )

        if matched_count:
            await db.commit()

    return matched_count


# ── Status endpoint ─────────────────────────────────────────────────────────

@router.get("/uniweb/status")
async def uniweb_status(user: User = _auth):
    """Return current sync status."""
    return {
        "running": _sync_status["running"],
        "last_sync": _sync_status["last_sync"],
        "last_error": _sync_status["last_error"],
        "accounts_synced": _sync_status["accounts_synced"],
        "total_accounts": _sync_status["total_accounts"],
        "current_account": _sync_status.get("current_account", ""),
        "domains_found": _sync_status.get("domains_found", 0),
        "errors_count": _sync_status.get("errors_count", 0),
        "sync_start_time": _sync_status.get("sync_start_time"),
        "configured": bool(_get_uniweb_config()["email"]),
    }


# ── Account listing ─────────────────────────────────────────────────────────

@router.get("/uniweb/accounts")
async def uniweb_accounts(user: User = _auth):
    """List all cached Uniweb accounts with data summaries."""
    async with get_db() as db:
        async with db.execute(
            "SELECT id, name, customer_id, last_sync, data_json FROM uniweb_accounts ORDER BY name"
        ) as cur:
            rows = await cur.fetchall()

    accounts = []
    for row in rows:
        data = {}
        if row["data_json"]:
            try:
                data = json.loads(row["data_json"])
            except json.JSONDecodeError:
                pass

        # Compute summaries
        domains = data.get("domains", [])
        subs = data.get("subscriptions", [])
        ssl = data.get("ssl", [])
        email = data.get("email", [])
        hosting = data.get("hosting", [])

        # Calculate monthly cost total
        monthly_total = 0.0
        for sub in subs:
            price_str = sub.get("Price per month", sub.get("price_monthly", ""))
            try:
                cleaned = price_str.replace(",", ".").replace(" ", "").replace("NOK", "").replace("kr", "")
                cleaned = "".join(c for c in cleaned if c.isdigit() or c == ".")
                if cleaned:
                    monthly_total += float(cleaned)
            except (ValueError, TypeError):
                pass

        # Find earliest renewal date
        earliest_renewal = None
        for sub in subs:
            rd = sub.get("Renewed until", sub.get("renewal_date", "")).strip()
            if rd and len(rd) >= 10:
                if earliest_renewal is None or rd < earliest_renewal:
                    earliest_renewal = rd

        # Get matched customer name
        customer_name = None
        if row["customer_id"]:
            from app.core.customer import CustomerManager
            cust = CustomerManager.get_customer(row["customer_id"])
            if cust:
                customer_name = cust.get("CustomerName")

        accounts.append({
            "id": row["id"],
            "name": row["name"],
            "customer_id": row["customer_id"],
            "customer_name": customer_name,
            "last_sync": row["last_sync"],
            "domain_count": len(domains),
            "subscription_count": len(subs),
            "ssl_count": len(ssl),
            "email_count": len(email),
            "hosting_count": len(hosting),
            "monthly_total": round(monthly_total, 2),
            "earliest_renewal": earliest_renewal,
        })

    return {"accounts": accounts, "total": len(accounts)}


# ── Single account detail ───────────────────────────────────────────────────

@router.get("/uniweb/account/{account_id}")
async def uniweb_account_detail(account_id: str, user: User = _auth):
    """Return full cached data for a single Uniweb account."""
    async with get_db() as db:
        async with db.execute(
            "SELECT id, name, customer_id, last_sync, data_json FROM uniweb_accounts WHERE id = ?",
            (account_id,),
        ) as cur:
            row = await cur.fetchone()

    if not row:
        raise NotFoundError("Konto ikke funnet")

    data = {}
    if row["data_json"]:
        try:
            data = json.loads(row["data_json"])
        except json.JSONDecodeError:
            pass

    customer_name = None
    if row["customer_id"]:
        from app.core.customer import CustomerManager
        cust = CustomerManager.get_customer(row["customer_id"])
        if cust:
            customer_name = cust.get("CustomerName")

    return {
        "id": row["id"],
        "name": row["name"],
        "customer_id": row["customer_id"],
        "customer_name": customer_name,
        "last_sync": row["last_sync"],
        "domains": data.get("domains", []),
        "subscriptions": data.get("subscriptions", []),
        "ssl": data.get("ssl", []),
        "email": data.get("email", []),
        "hosting": data.get("hosting", []),
    }


# ── Account matching ────────────────────────────────────────────────────────

@router.post("/uniweb/match")
async def uniweb_match(request: Request, user: User = Depends(require_role(Role.technician))):
    """Match a Uniweb account to an MSP Toolkit customer."""
    body = await request.json()
    uniweb_account_id = body.get("uniweb_account_id", "").strip()
    customer_id = body.get("customer_id", "").strip()

    if not uniweb_account_id:
        raise ValidationError("uniweb_account_id er pakrevd")

    async with get_db() as db:
        # Verify the Uniweb account exists
        async with db.execute(
            "SELECT id FROM uniweb_accounts WHERE id = ?",
            (uniweb_account_id,),
        ) as cur:
            if not await cur.fetchone():
                raise NotFoundError("Uniweb-konto ikke funnet")

        # customer_id can be empty to unmatch
        await db.execute(
            "UPDATE uniweb_accounts SET customer_id = ? WHERE id = ?",
            (customer_id or None, uniweb_account_id),
        )
        await db.commit()

    return {"ok": True}


@router.get("/uniweb/matches")
async def uniweb_matches(user: User = _auth):
    """List all Uniweb accounts with their match status."""
    from app.core.customer import CustomerManager

    customers = CustomerManager.list_customers()
    customer_map = {}
    for c in customers:
        cid = c.get("_id", "")
        if cid:
            customer_map[cid] = c.get("CustomerName", "")

    async with get_db() as db:
        async with db.execute(
            "SELECT id, name, customer_id, data_json FROM uniweb_accounts ORDER BY name"
        ) as cur:
            rows = await cur.fetchall()

    matched = []
    unmatched = []
    for row in rows:
        # Extract parent info from data_json
        parent_name = ""
        if row["data_json"]:
            try:
                data = json.loads(row["data_json"])
                parent_name = data.get("parent_name", "")
            except json.JSONDecodeError:
                pass

        entry = {
            "uniweb_id": row["id"],
            "uniweb_name": row["name"],
            "customer_id": row["customer_id"],
            "customer_name": customer_map.get(row["customer_id"], "") if row["customer_id"] else None,
            "parent_name": parent_name,
        }
        if row["customer_id"]:
            matched.append(entry)
        else:
            unmatched.append(entry)

    # Provide available customers for matching dropdown
    available_customers = [
        {"id": c.get("_id", ""), "name": c.get("CustomerName", "")}
        for c in customers
        if c.get("_id") and c.get("CustomerName")
    ]

    return {
        "matched": matched,
        "unmatched": unmatched,
        "available_customers": available_customers,
    }


# ── Settings ────────────────────────────────────────────────────────────────

# ── Customer-specific data ─────────────────────────────────────────────────

@router.get("/uniweb/customer/{customer_id}")
async def uniweb_customer_data(
    customer_id: str, user: User = Depends(require_customer_access(Role.viewer))
):
    """Return Uniweb data for a customer (if matched)."""
    async with get_db() as db:
        async with db.execute(
            "SELECT id, name, data_json, last_sync FROM uniweb_accounts WHERE customer_id = ?",
            (customer_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return {"matched": False}
    data = {}
    if row["data_json"]:
        try:
            data = json.loads(row["data_json"])
        except json.JSONDecodeError:
            pass

    # Calculate monthly cost total
    subs = data.get("subscriptions", [])
    monthly_total = 0.0
    for sub in subs:
        price_str = sub.get("Price per month", sub.get("price_monthly", ""))
        try:
            cleaned = str(price_str).replace(",", ".").replace(" ", "").replace("NOK", "").replace("kr", "")
            cleaned = "".join(c for c in cleaned if c.isdigit() or c == ".")
            if cleaned:
                monthly_total += float(cleaned)
        except (ValueError, TypeError):
            pass

    return {
        "matched": True,
        "account_id": row["id"],
        "account_name": row["name"],
        "last_sync": row["last_sync"],
        "domains": data.get("domains", []),
        "subscriptions": subs,
        "ssl": data.get("ssl", []),
        "email": data.get("email", []),
        "hosting": data.get("hosting", []),
        "monthly_total": round(monthly_total, 2),
    }


# ── Expiry alerts ──────────────────────────────────────────────────────────

async def _uniweb_account_index() -> dict[str, dict]:
    """Map each Uniweb customer id to its resolved Sybr customer + account name.

    ``uniweb_accounts`` holds the Uniweb account id (which the Partner API calls
    a subscription's ``customer``) alongside the Sybr customer it is matched to.
    This builds the lookup ``_expiry_items`` needs so a live subscription can be
    named after its Sybr customer.
    """
    async with get_db() as db, db.execute(
        "SELECT id, name, customer_id FROM uniweb_accounts"
    ) as cur:
        rows = await cur.fetchall()

    names: dict[str, str] = {}
    cids = {r["customer_id"] for r in rows if r["customer_id"]}
    if cids:
        from app.core.customer import CustomerManager
        for cid in cids:
            cust = CustomerManager.get_customer(cid)
            if cust:
                names[cid] = cust.get("CustomerName", "")

    index: dict[str, dict] = {}
    for row in rows:
        cid = row["customer_id"] or ""
        index[str(row["id"])] = {
            "customer_id": cid,
            "customer_name": names.get(cid) or row["name"],
            "account_name": row["name"],
        }
    return index


def _empty_alerts() -> dict:
    return {"items": [], "total": 0, "critical": 0, "warning": 0, "upcoming": 0, "longterm": 0}


@router.get("/uniweb/alerts")
async def uniweb_alerts(user: User = _auth, days: int = 365):
    """Uniweb services expiring within N days (default 365), from the live API.

    Derived from the Partner API's ``/subscriptions`` — ``period.to`` is the
    authoritative renewal date — instead of scraped date strings, so the list
    no longer depends on a recent sync. Uniweb being unconfigured is not an
    error (there simply are no renewals); a live call that fails does raise,
    because "we could not ask" must never render as "nothing expires".
    """
    if not _get_uniweb_config()["email"]:
        return _empty_alerts()

    now = datetime.now(timezone.utc)
    max_days = max(7, min(days, 3650))  # clamp 7-3650

    subs = await _partner_call(lambda c: c.list_subscriptions())
    accounts = await _uniweb_account_index()
    items = _expiry_items(subs, accounts, now, max_days)

    return {
        "items": items,
        "total": len(items),
        "critical": sum(1 for i in items if i["days_remaining"] < 7),
        "warning": sum(1 for i in items if 7 <= i["days_remaining"] < 30),
        "upcoming": sum(1 for i in items if 30 <= i["days_remaining"] < 90),
        "longterm": sum(1 for i in items if i["days_remaining"] >= 90),
    }


@router.get("/uniweb/dns/{domain}")
async def uniweb_dns(domain: str, user: User = _auth):
    """Live DNS records for a domain, from the Partner API.

    Replaces the scraped cache: ``GET /domain/{domain}/dns/record`` returns the
    current zone, projected to ``{hostname, type, value, ttl}`` (never the
    zone's DNSSEC signing keys). The endpoint serves clustered zones only —
    a domain whose DNS Uniweb does not host has no records to show, which reads
    as an empty list, exactly as the scraper's DNS tab did. An expired session
    still surfaces as an error rather than a false "no records".
    """
    from app.services.uniweb_partner import (
        UniwebAuthError,
        UniwebPartnerError,
        dns_record_view,
    )

    if not _get_uniweb_config()["email"]:
        return {"domain": domain, "records": []}

    try:
        records = await _partner_call(lambda c: c.dns_records(domain))
    except UniwebAuthError:
        raise
    except UniwebPartnerError as exc:
        # Clustered-only endpoint: a non-auth failure means Uniweb hosts no DNS
        # for this domain — an empty zone here, not a system error.
        logger.debug("Uniweb DNS unavailable for %s: %s", domain, exc)
        return {"domain": domain, "records": []}

    return {"domain": domain, "records": [dns_record_view(r) for r in records]}


@router.post("/uniweb/import-customers")
async def uniweb_import_customers(request: Request, user: User = Depends(require_role(Role.technician))):
    """Create new MSP Toolkit customers from unmatched Uniweb accounts."""
    from app.core.customer import CustomerManager

    body = await request.json()
    account_ids = body.get("account_ids", [])
    if not account_ids:
        raise ValidationError("Ingen kontoer valgt")

    # Load existing customers to skip duplicates
    existing = CustomerManager.list_customers()
    existing_names = {c.get("CustomerName", "").lower() for c in existing}

    imported = 0
    errors = []

    async with get_db() as db:
        for acct_id in account_ids:
            # Look up the Uniweb account
            async with db.execute(
                "SELECT id, name, customer_id FROM uniweb_accounts WHERE id = ?",
                (acct_id,),
            ) as cur:
                row = await cur.fetchone()

            if not row:
                errors.append({"name": acct_id, "reason": "Konto ikke funnet"})
                continue

            if row["customer_id"]:
                errors.append({"name": row["name"], "reason": "Allerede koblet til en kunde"})
                continue

            name = row["name"].strip()
            if not name:
                errors.append({"name": acct_id, "reason": "Kontonavnet mangler"})
                continue

            if name.lower() in existing_names:
                # Customer already exists — just link it
                for c in existing:
                    if c.get("CustomerName", "").lower() == name.lower():
                        cust_id = c.get("_id", "")
                        if cust_id:
                            await db.execute(
                                "UPDATE uniweb_accounts SET customer_id = ? WHERE id = ?",
                                (cust_id, acct_id),
                            )
                            imported += 1
                        break
                continue

            # Create a minimal customer entry
            config = {
                "CustomerName": name,
                "TenantId": "",
                "ClientId": "",
                "PrimaryDomain": "",
                "InitialDomain": "",
                "AppObjectId": "",
                "SubscriptionId": "",
                "SetupDate": "",
                "SecretExpiry": "",
                "CertExpiry": "",
                "UniwebAccountId": str(acct_id),
            }
            cust_id = CustomerManager.save_customer(config)
            existing_names.add(name.lower())

            # Link the Uniweb account to the new customer
            await db.execute(
                "UPDATE uniweb_accounts SET customer_id = ? WHERE id = ?",
                (cust_id, acct_id),
            )
            imported += 1

        await db.commit()

    try:
        from app.core.activity_log import log_activity
        _user = getattr(getattr(request.state, "user", None), "username", "")
        log_activity(
            "uniweb_import",
            detail=f"Importerte {imported} kunde(r) fra Uniweb",
            user=_user,
        )
    except Exception as e:
        logger.debug("Failed to log Uniweb import activity: %s", e)

    return {"ok": True, "imported": imported, "errors": errors}


@router.post("/uniweb/settings")
async def uniweb_save_settings(request: Request, user: User = Depends(require_role(Role.admin))):
    """Save Uniweb credentials (email + password) to encrypted app settings."""
    body = await request.json()
    email = body.get("email", "").strip()
    password = body.get("password", "").strip()

    if not email or not password:
        raise ValidationError("E-post og passord er pakrevd")

    def _set(s: dict) -> None:
        s["uniweb_email"] = email
        if password != "••••••":
            s["uniweb_password"] = password

    update_app_settings(_set)

    try:
        from app.core.activity_log import log_activity
        log_activity("uniweb_settings_saved", detail="Uniweb credentials updated")
    except Exception as e:
        logger.debug("Failed to log Uniweb settings activity: %s", e)

    return {"ok": True}
