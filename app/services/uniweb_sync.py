"""Uniweb collection and persistence independent of HTTP request handlers."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from difflib import SequenceMatcher

from sqlmodel import select, update

from app.core.config import load_app_settings
from app.core.orm import get_session
from app.models.integrations import UniwebAccount

logger = logging.getLogger(__name__)

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


async def _run_sync(email: str, password: str) -> None:
    """Background sync task — runs the Uniweb scraper in a thread."""
    global _sync_status
    if _sync_status["running"]:
        # Single-flight, enforced here so neither entry point can bypass it: the
        # HTTP route checks this for a friendly message, but the scheduled task
        # (scheduler._do_uniweb_sync) calls _run_sync directly and used to skip
        # the check. Two concurrent runs would each spin up a headless Chromium
        # and race on uniweb_accounts, and whichever finished first would clear
        # `running` in its finally while the other was still going — re-opening
        # the guard for a third. The check-and-set below is synchronous (no await
        # in between), so it is atomic within the event loop.
        logger.info("Uniweb sync already running — skipping this trigger")
        return
    _sync_status["running"] = True
    _sync_status["last_error"] = None
    _sync_status["accounts_synced"] = 0
    _sync_status["current_account"] = ""
    _sync_status["domains_found"] = 0
    _sync_status["errors_count"] = 0
    _sync_status["sync_start_time"] = datetime.now(UTC).isoformat()

    try:
        from app.services.uniweb_client import UniwebClient, UniwebScrapeError

        def _do_sync():
            client = UniwebClient()
            try:
                if not client.login(email, password):
                    detail = client.last_login_error or ""
                    raise RuntimeError(
                        "Innlogging til Uniweb feilet" + (f": {detail}" if detail else "")
                    )

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
                            _sync_status["domains_found"] += len(acct["data"].get("domains", []))
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

        # Store results in database. One account that could not be opened —
        # or one that refuses to write — must never discard the whole batch.
        now = datetime.now(UTC).isoformat()
        stored = await _persist_sync_results(results, now)

        # Auto-match by name similarity
        await _auto_match_accounts()

        _sync_status["last_sync"] = now
        logger.info("Uniweb sync complete: %d/%d accounts stored", stored, len(results))

    except Exception as e:
        _sync_status["last_error"] = str(e)
        logger.error("Uniweb sync failed: %s", e)
    finally:
        _sync_status["running"] = False


async def _persist_sync_results(results: list[dict], now: str) -> int:
    """Write scraped account data to ``uniweb_accounts``; return how many stored.

    Two failure modes used to take out the whole run. An account that could
    not be opened this pass carries no ``data`` key — only ``unavailable`` (set
    in ``_do_sync`` so "we could not read this page" never masquerades as "this
    customer has no domains"). The old persist loop did ``dict(account["data"])``
    unconditionally, so the first such account raised ``KeyError('data')`` inside
    the ``async with get_db()`` block *before* the commit, unwound every
    already-queued write, and was swallowed by the broad ``except`` above as a
    cryptic ``last_error = "'data'"`` — meaning one un-openable account in a
    multi-account run discarded every account that *had* been read.

    So: an account with no fresh data is skipped, leaving its last good row
    intact rather than overwriting it with an empty zone; and each write is
    isolated, so one row that will not persist cannot abort the batch.
    """
    stored = 0
    async with get_session() as session:
        for account in results:
            data = account.get("data")
            if data is None:
                # Unavailable this pass. Keep the previous row and do not
                # advance its last_sync — a refusal is not zero domains.
                continue
            try:
                # Preserve existing customer_id mapping
                result = await session.execute(
                    select(UniwebAccount).where(UniwebAccount.id == account["id"])
                )
                db_account = result.scalar_one_or_none()

                # Include parent info in data_json for sub-customers
                data_to_store = dict(data)
                if account.get("parent_id"):
                    data_to_store["parent_id"] = account["parent_id"]
                    data_to_store["parent_name"] = account.get("parent_name", "")

                data_json_str = json.dumps(data_to_store, ensure_ascii=False)

                if db_account:
                    db_account.name = account["name"]
                    db_account.last_sync = now
                    db_account.data_json = data_json_str
                else:
                    db_account = UniwebAccount(
                        id=account["id"],
                        name=account["name"],
                        last_sync=now,
                        data_json=data_json_str,
                    )
                    session.add(db_account)

                stored += 1
                _sync_status["accounts_synced"] = stored
            except Exception as exc:
                # One un-writable record is an error to surface, not a reason
                # to drop the rest of a scrape that may have taken minutes.
                _sync_status["errors_count"] += 1
                logger.warning(
                    "Uniweb sync: could not persist account %s: %s",
                    account.get("id"),
                    exc,
                )
        await session.commit()
    return stored


async def _auto_match_accounts() -> int:
    """Auto-match unmatched Uniweb accounts to MSP customers by name similarity."""
    from app.core.customer import CustomerManager

    customers = CustomerManager.list_customers()
    if not customers:
        return 0

    matched_count = 0
    async with get_session() as session:
        result = await session.execute(
            select(UniwebAccount.id, UniwebAccount.name).where(UniwebAccount.customer_id.is_(None))
        )
        unmatched = result.mappings().all()

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
                    await session.execute(
                        update(UniwebAccount)
                        .where(UniwebAccount.id == row["id"])
                        .values(customer_id=cust_id)
                    )
                    matched_count += 1
                    logger.info(
                        "Auto-matched Uniweb '%s' -> customer '%s' (score=%.2f)",
                        row["name"],
                        best_match.get("CustomerName"),
                        best_score,
                    )

        if matched_count:
            await session.commit()

    return matched_count
