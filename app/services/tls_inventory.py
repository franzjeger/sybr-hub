"""The TLS certificates the hub has seen, per endpoint, kept between checks.

A TLS check used to be a live scan whose answer went to the browser that asked
and nowhere else. Nothing remembered an expiry date, so Varsler could only show
a certificate if the alert engine had sent an alert about it, and the engine
only records what reached a Teams or e-mail channel. With no channel set up, a
certificate expiring tomorrow appeared nowhere.

Every check now ends here. The row for an endpoint holds the certificate from
the last handshake that returned one, and the error and time of the last
attempt. An endpoint that stops answering keeps the expiry it was last seen
with: "it expires in five days, and today we could not reach it" is the true
state, and dropping the date would turn it into silence.

Access follows the customer the endpoint belongs to. An endpoint tied to no
customer is MSP-wide and only an unrestricted account sees it, the rule
``customer_in_scope`` applies everywhere else.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.core.database import get_db
from app.core.rbac import customer_in_scope

log = logging.getLogger(__name__)

# Varsler's horizon, the same 30 days credentials and renewals use.
EXPIRY_HORIZON_DAYS = 30
CRITICAL_DAYS = 7

# A self-signed certificate on a firewall's management page is usually a
# choice, not an accident. Listed as information, every FortiGate would put a
# line in Varsler the night the re-check first ran, burying what does need
# someone. Varsler leaves it out; the TLS tab still shows it, and its expiry is
# listed like any other certificate's.
_QUIET_CHAIN_PROBLEMS = {"self_signed"}

_COLUMNS = (
    "host",
    "port",
    "customer_id",
    "label",
    "source",
    "subject",
    "issuer",
    "not_after",
    "chain_valid",
    "chain_problem",
    "weak_tls",
    "error",
    "checked_at",
    "cert_seen_at",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _name(value) -> str:
    """The readable part of a subject or issuer, whichever shape it came in."""
    if isinstance(value, dict):
        return str(
            value.get("commonName")
            or value.get("organizationName")
            or next(iter(value.values()), "")
        )
    return str(value or "")


def _issuer(value) -> str:
    if isinstance(value, dict):
        return str(value.get("organizationName") or value.get("commonName") or "")
    return str(value or "")


def _normalise(host: str) -> str:
    return (host or "").strip().lower().rstrip(".")


async def record_results(
    results: list[dict],
    *,
    allowed: set[str] | None,
    may_add: bool,
    customer_id: str | None = None,
) -> int:
    """Store what a batch of checks found. Returns how many rows it touched.

    *allowed* is the caller's customer scope (None: unrestricted). A result
    may name a customer (``customer_id``, from discovery) or the call may name
    one for all of them; either is taken only when the endpoint is not already
    filed under a customer outside that scope, so a scoped account cannot move
    another customer's endpoint into its own list by checking it.

    *may_add* False refreshes endpoints the hub already knows and adds none.
    A read-only account's check is a lookup: it may bring a reading up to date,
    but it does not put a new endpoint on the daily re-check list.

    A scoped account adds only endpoints filed under one of its customers. An
    endpoint with no customer is MSP-wide, and an account that will never be
    shown it has no business putting it on everybody else's list.
    """
    now = _now().isoformat()
    touched = 0
    async with get_db() as db:
        for r in results:
            host = _normalise(r.get("host", ""))
            try:
                port = int(r.get("port") or 443)
            except (TypeError, ValueError):
                continue
            if not host:
                continue
            async with db.execute(
                "SELECT * FROM tls_endpoints WHERE host = ? AND port = ?", (host, port)
            ) as cur:
                existing = await cur.fetchone()
            if existing is None and not may_add:
                continue
            row = dict(existing) if existing is not None else {c: None for c in _COLUMNS}
            row["host"], row["port"] = host, port

            wanted = r.get("customer_id") or customer_id
            held = row["customer_id"]
            if (
                wanted
                and customer_in_scope(wanted, allowed)
                and (held is None or customer_in_scope(held, allowed))
            ):
                row["customer_id"] = wanted
            if existing is None and allowed is not None and not row["customer_id"]:
                continue
            if r.get("label"):
                row["label"] = str(r["label"])
            if r.get("source"):
                row["source"] = str(r["source"])
            row["label"] = row["label"] or ""
            row["source"] = row["source"] or ("manual" if existing is None else "")

            if r.get("not_after"):
                row["subject"] = _name(r.get("subject"))
                row["issuer"] = _issuer(r.get("issuer"))
                row["not_after"] = str(r["not_after"])
                row["chain_valid"] = 0 if r.get("chain_valid") is False else 1
                row["chain_problem"] = str(r.get("chain_problem") or "")
                row["weak_tls"] = 1 if (r.get("weak_protocol") or r.get("weak_cipher")) else 0
                row["error"] = ""
                row["cert_seen_at"] = now
            else:
                # No certificate this time. What the last one said stands; the
                # failure is recorded beside it, not instead of it.
                row["error"] = str(r.get("error") or "No certificate returned")
                if r.get("chain_valid") is False:
                    row["chain_valid"] = 0
                    row["chain_problem"] = str(r.get("chain_problem") or "other")
            for key in ("subject", "issuer", "chain_problem", "error"):
                row[key] = row[key] or ""
            row["weak_tls"] = row["weak_tls"] or 0
            row["checked_at"] = now

            await db.execute(
                f"INSERT OR REPLACE INTO tls_endpoints ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
                tuple(row[c] for c in _COLUMNS),
            )
            touched += 1
        await db.commit()
    return touched


async def record_quietly(results: list[dict], **kwargs) -> None:
    """record_results for callers whose own answer must not depend on storage.

    A check that worked is still an answer for the person who asked, even if
    the database refused it; the failure goes to the log at warning level
    rather than disappearing.
    """
    try:
        await record_results(results, **kwargs)
    except Exception as exc:
        log.warning("TLS results not stored: %s", exc)


def classify(row: dict, now: datetime | None = None) -> dict:
    """The state of one stored endpoint, as the list and Varsler show it.

    ``status`` is the most urgent of: ``expired``, ``expiring`` (within 30
    days), ``invalid_chain``, ``weak``, ``ok``; or ``unreachable`` when no
    certificate has ever been read and the last attempt failed. ``stale`` is
    True when the last attempt failed but an earlier one read a certificate,
    so the dates shown are the last ones seen.
    """
    now = now or _now()
    out = dict(row)
    out["days_remaining"] = None
    out["stale"] = bool(row.get("error")) and bool(row.get("not_after"))
    not_after = row.get("not_after")
    if not not_after:
        out["status"] = "unreachable" if row.get("error") else "unknown"
        return out
    try:
        end = datetime.fromisoformat(str(not_after).replace("Z", "+00:00"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
    except ValueError:
        out["status"] = "unknown"
        return out
    days = (end - now).days
    out["days_remaining"] = days
    if now > end:
        out["status"] = "expired"
    elif days < EXPIRY_HORIZON_DAYS:
        out["status"] = "expiring"
    elif row.get("chain_valid") == 0:
        out["status"] = "invalid_chain"
    elif row.get("weak_tls"):
        out["status"] = "weak"
    else:
        out["status"] = "ok"
    return out


def _customer_names() -> dict[str, str]:
    from app.core.customer import CustomerManager

    return {c.get("_id", ""): c.get("CustomerName", "") for c in CustomerManager.list_customers()}


async def list_endpoints(
    allowed: set[str] | None,
    customer_id: str | None = None,
    *,
    names: dict[str, str] | None = None,
) -> list[dict]:
    """Every stored endpoint the caller may see, classified, most urgent first.

    An endpoint filed under a customer that no longer exists is left out: the
    customer was retired, and its rows wait for the purge rather than for a
    technician.
    """
    names = names if names is not None else _customer_names()
    query = "SELECT * FROM tls_endpoints"
    params: tuple = ()
    if customer_id is not None:
        query += " WHERE customer_id = ?"
        params = (customer_id,)
    async with get_db() as db, db.execute(query, params) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    now = _now()
    out = []
    for row in rows:
        cid = row.get("customer_id")
        if not customer_in_scope(cid, allowed):
            continue
        if cid and cid not in names:
            continue
        item = classify(row, now)
        item["customer_name"] = names.get(cid, "") if cid else ""
        item["chain_valid"] = None if row.get("chain_valid") is None else bool(row["chain_valid"])
        item["weak_tls"] = bool(row.get("weak_tls"))
        out.append(item)
    order = {"expired": 0, "expiring": 1, "invalid_chain": 2, "unreachable": 3, "weak": 4}
    out.sort(
        key=lambda i: (
            order.get(i["status"], 5),
            i["days_remaining"] if i["days_remaining"] is not None else 10**6,
            i["host"],
            i["port"],
        )
    )
    return out


async def forget(host: str, port: int, allowed: set[str] | None) -> bool:
    """Remove an endpoint the caller may see. False when there was none."""
    host = _normalise(host)
    async with get_db() as db:
        async with db.execute(
            "SELECT customer_id FROM tls_endpoints WHERE host = ? AND port = ?", (host, port)
        ) as cur:
            row = await cur.fetchone()
        if row is None or not customer_in_scope(row["customer_id"], allowed):
            return False
        await db.execute("DELETE FROM tls_endpoints WHERE host = ? AND port = ?", (host, port))
        await db.commit()
    return True


async def attention(allowed: set[str] | None, names: dict[str, str] | None = None) -> list[dict]:
    """What Varsler lists: certificates expired or expiring within 30 days,
    and chains that do not validate for a reason other than being
    self-signed. Unreachable endpoints are not listed: "we could not connect"
    is not a certificate problem, and the TLS tab shows them."""
    items = []
    for e in await list_endpoints(allowed, names=names):
        status = e["status"]
        expiring = status in ("expired", "expiring")
        if not expiring and (
            e.get("chain_valid") is not False or e["chain_problem"] in _QUIET_CHAIN_PROBLEMS
        ):
            continue
        if expiring:
            days = e["days_remaining"]
            category = "critical" if days < CRITICAL_DAYS else "warning"
            kind = "expired" if status == "expired" else "expiring"
        else:
            category = "warning"
            kind = "chain"
        items.append(
            {
                "host": e["host"],
                "port": e["port"],
                "label": e["label"],
                "customer_id": e["customer_id"] or "",
                "customer_name": e["customer_name"],
                "subject": e["subject"],
                "issuer": e["issuer"],
                "not_after": (e["not_after"] or "")[:10],
                "days_remaining": e["days_remaining"] if expiring else None,
                "chain_problem": e["chain_problem"] if e.get("chain_valid") is False else "",
                "kind": kind,
                "category": category,
                "checked_at": e["checked_at"],
                "stale": e["stale"],
            }
        )
    return items


async def coverage(allowed: set[str] | None, names: dict[str, str] | None = None) -> dict:
    """How much the hub knows, so an empty Varsler is not read as all clear
    when nothing was ever checked."""
    endpoints = await list_endpoints(allowed, names=names)
    checked = [e["checked_at"] for e in endpoints if e.get("checked_at")]
    return {
        "endpoints": len(endpoints),
        "unreachable": sum(1 for e in endpoints if e["status"] in ("unreachable", "unknown")),
        "last_checked": max(checked) if checked else None,
    }


async def recheck_known() -> dict:
    """Check every stored endpoint again, and the ones configuration names.

    The daily job. Discovery adds the firewalls, controllers and appliances the
    customers' settings point at, so a new FortiGate is watched from the first
    morning after it is configured rather than after somebody presses Scan.
    """
    from app.services.tls_monitor import discover_tls_endpoints, scan_customer_endpoints

    async with get_db() as db, db.execute("SELECT host, port FROM tls_endpoints") as cur:
        stored = [{"host": r["host"], "port": r["port"]} for r in await cur.fetchall()]
    endpoints: dict[tuple[str, int], dict] = {(e["host"], int(e["port"])): e for e in stored}
    for e in await discover_tls_endpoints():
        endpoints[(_normalise(e["host"]), int(e["port"]))] = e
    if not endpoints:
        return {"checked": 0, "expired": 0, "expiring_soon": 0, "errors": 0}
    scan = await scan_customer_endpoints(list(endpoints.values()))
    await record_results(scan["results"], allowed=None, may_add=True)
    return {
        "checked": scan["total"],
        "expired": scan["expired"],
        "expiring_soon": scan["expiring_soon"],
        "errors": scan["errors"],
    }
