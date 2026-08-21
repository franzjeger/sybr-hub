"""Client for the Uniweb Partner API (https://www.uniweb.no/api/partner).

The structured JSON replacement for the control-panel scraper in
``uniweb_client.py``. Everything that scraper parses out of the control-panel
DOM — subscriptions, customers, domains, SSL, DNS, email — is a first-class
endpoint here, returned as JSON, so the read paths no longer depend on a
headless browser or the panel's markup staying still.

Auth is cookie-based. The API accepts the *session* and *grant* cookies minted
by a control-panel login; ``UniwebClient.harvest_cookies()`` extracts them after
logging in, and they are handed to this client. There is no API key — the same
session the scraper already establishes is reused, hitting JSON instead of the
DOM.

Read-only by design in this phase: no create/migrate calls live here.

Two response fields carry secrets — a subscription's ``tsig`` (a domain's DNS
update secret) and, for SSL subscriptions, the private ``key``. This client
never logs response bodies, and ``public_subscription()`` projects a
subscription down to the non-secret fields the Hub view needs, so a caller
cannot accidentally surface or persist a TSIG or a private key.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from urllib.parse import quote

import httpx

from app.integrations.http_retry import RetryExhausted, send_with_retry

logger = logging.getLogger(__name__)

BASE_URL = "https://www.uniweb.no/api/partner"

# Fields that carry secrets. Never log them; never hand them to the UI as-is.
# ``shareableRef`` is a capability token — a link that opens (and can pay) the
# invoice without a login — so it belongs here beside the DNS/SSL secrets.
_SENSITIVE_FIELDS = frozenset({
    "tsig", "key", "password", "keySigningKey", "zoneSigningKey",
    "combinedSigningKey", "keystore", "shareableRef",
})

# The non-secret subscription fields the Hub view needs — identity, product,
# pricing (charge vs cost, so margin is derivable) and period.
_PUBLIC_SUBSCRIPTION_FIELDS = (
    "id", "customer", "username", "product", "otc", "rc", "inOtc", "inRc",
    "renew", "created", "period", "disk", "xfer", "concurrency", "cpu",
    "mem", "dmem",
)

# The non-secret invoice fields the AR view needs. Deliberately excludes
# ``shareableRef`` (a pay-this-invoice token) and ``invoiceId`` (the internal
# UUID that addresses it) — identity for display is ``invoiceNo``.
_PUBLIC_INVOICE_FIELDS = (
    "id", "invoiceNo", "externalInvoiceNo", "created", "invoiceDate",
    "invoiceDue", "invoiceSum", "paid", "credited", "lost", "waived",
    "invoiceType",
)


class UniwebPartnerError(Exception):
    """A Uniweb Partner API call failed."""


class UniwebAuthError(UniwebPartnerError):
    """The session/grant cookies were missing, invalid or expired.

    The API answers 401 with no body, so that is the whole story: the
    control-panel login must be re-run to mint fresh cookies.
    """


def public_subscription(sub: dict) -> dict:
    """A subscription with only the non-secret fields the Hub view needs.

    Drops ``tsig`` (a domain's DNS secret) and any SSL key/cert material while
    keeping identity, product, pricing and period — so margin (``rc`` charged
    vs ``inRc`` cost) can be shown without ever surfacing a secret.
    """
    return {k: sub.get(k) for k in _PUBLIC_SUBSCRIPTION_FIELDS if k in sub}


def _first(rec: dict, *keys: str) -> str:
    """First non-empty value among ``keys``, as a string."""
    for k in keys:
        v = rec.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def dns_record_view(rec: dict) -> dict:
    """A DNS record projected to ``{hostname, type, value, ttl}``.

    The Partner API returns one record as a type-tagged bag of fields — an
    ``A`` carries ``address``, an ``MX`` a ``priority`` and ``target``, a
    ``TXT`` a ``strings`` array, and so on. The Hub renders a single value
    column, so this flattens each type to the one human-readable string that
    column shows, matching what the old scraper parsed out of the panel.

    It is also the projection boundary: only these four fields survive, so a
    zone's DNSSEC signing keys can never ride a record out to the UI even if
    the endpoint were to include them.
    """
    rtype = str(rec.get("type") or "").upper()
    ttl = rec.get("ttl")

    if rtype in ("A", "AAAA"):
        value = _first(rec, "address")
    elif rtype == "CNAME":
        value = _first(rec, "alias", "target")
    elif rtype == "TXT":
        strings = rec.get("strings")
        # A long TXT is split into <=255-char chunks on the wire; concatenating
        # (no separator) reconstructs the record faithfully.
        value = "".join(str(s) for s in strings) if isinstance(strings, list) \
            else _first(rec, "value", "data")
    elif rtype == "MX":
        value = " ".join(p for p in (_first(rec, "priority"), _first(rec, "target")) if p)
    elif rtype == "SRV":
        value = " ".join(p for p in (
            _first(rec, "priority"), _first(rec, "weight"),
            _first(rec, "port"), _first(rec, "target"),
        ) if p)
    elif rtype == "NS":
        value = _first(rec, "target")
    elif rtype == "WEBFORWARD":
        value = _first(rec, "url")
    elif rtype == "CAA":
        value = " ".join(p for p in (
            _first(rec, "flags"), _first(rec, "tag"), _first(rec, "value"),
        ) if p)
    elif rtype == "SSHFP":
        value = " ".join(p for p in (
            _first(rec, "algorithm"), _first(rec, "digest"), _first(rec, "fingerprint"),
        ) if p)
    elif rtype == "TLSA":
        value = " ".join(p for p in (
            _first(rec, "certificateUsage"), _first(rec, "selector"),
            _first(rec, "matchingType"), _first(rec, "data"),
        ) if p)
    else:
        value = _first(rec, "address", "target", "alias", "url", "value", "data")

    return {
        "hostname": _first(rec, "name"),
        "type": rtype,
        "value": value,
        "ttl": ttl if isinstance(ttl, int) else _first(rec, "ttl"),
    }


def _money(order: dict, key: str) -> float:
    try:
        return float(order.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def order_outstanding(order: dict) -> float:
    """What is still owed on an invoice: billed minus everything settled.

    ``invoiceSum`` less ``paid``, ``credited``, ``lost`` and ``waived``. The
    plain ``/orders`` list omits the last three, so they read as 0 there — which
    is the right answer for an invoice that was neither credited nor written off,
    and the query shape fills them in when they aren't.
    """
    return round(
        _money(order, "invoiceSum") - _money(order, "paid")
        - _money(order, "credited") - _money(order, "lost") - _money(order, "waived"),
        2,
    )


def open_invoice(order: dict) -> dict:
    """An invoice projected to its non-secret fields plus outstanding balance.

    The same whitelist boundary ``public_subscription`` draws for a ``tsig``:
    the pay-this-invoice token (``shareableRef``) and the internal ``invoiceId``
    never survive. The customer is flattened to id + name when the order carries
    one (the query shape does; the plain list does not).
    """
    pub = {k: order.get(k) for k in _PUBLIC_INVOICE_FIELDS if k in order}
    cust = order.get("customer") or {}
    pub["customer_id"] = cust.get("id")
    pub["customer_name"] = cust.get("name") or ""
    pub["outstanding"] = order_outstanding(order)
    return pub


def _due_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def ar_aging(orders: list[dict], today: date) -> dict:
    """Accounts-receivable summary: outstanding, overdue, and aged by due date.

    Only invoices with a positive balance count as open. Each is aged into the
    standard buckets by how far past its due date it is (current = not yet due).
    Pure, so the arithmetic and the bucketing are unit-tested without a login,
    and every listed invoice is an ``open_invoice`` projection — no share token
    reaches the summary.
    """
    buckets = {"current": 0.0, "d1_30": 0.0, "d31_60": 0.0, "d61_90": 0.0, "d90_plus": 0.0}
    invoices: list[dict] = []
    total_outstanding = 0.0
    overdue_total = 0.0

    for order in orders:
        outstanding = order_outstanding(order)
        if outstanding <= 0:
            continue
        due = _due_date(order.get("invoiceDue"))
        days_overdue = (today - due).days if due else 0
        total_outstanding += outstanding
        if days_overdue > 0:
            overdue_total += outstanding
        bucket = (
            "current" if days_overdue <= 0
            else "d1_30" if days_overdue <= 30
            else "d31_60" if days_overdue <= 60
            else "d61_90" if days_overdue <= 90
            else "d90_plus"
        )
        buckets[bucket] += outstanding
        inv = open_invoice(order)
        inv["days_overdue"] = max(0, days_overdue)
        invoices.append(inv)

    invoices.sort(key=lambda i: i["days_overdue"], reverse=True)
    return {
        "open_count": len(invoices),
        "total_outstanding": round(total_outstanding, 2),
        "overdue_count": sum(1 for i in invoices if i["days_overdue"] > 0),
        "overdue_total": round(overdue_total, 2),
        "aging": {k: round(v, 2) for k, v in buckets.items()},
        "invoices": invoices,
    }


class UniwebPartnerClient:
    """Async, read-only client for the Uniweb Partner API.

    Construct it with the ``session`` and ``grant`` cookies from a control-panel
    login (see ``UniwebClient.harvest_cookies``). Every method raises rather than
    returning an empty result on a transport or auth failure: "we could not ask"
    must never read like "there is none".
    """

    def __init__(
        self,
        cookies: dict[str, str],
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
    ):
        if not cookies:
            raise UniwebAuthError(
                "No Uniweb cookies supplied — run the control-panel login first."
            )
        self._base = base_url.rstrip("/")
        # The API host (www.uniweb.no) differs from the login host (uniweb.no),
        # so the cookies go in an explicit header rather than through the jar's
        # domain matching, which would drop them across the sub-domain.
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        self._client = httpx.AsyncClient(
            headers={"Cookie": cookie_header, "Accept": "application/json"},
            timeout=timeout,
        )

    async def __aenter__(self) -> UniwebPartnerClient:
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # ── Plumbing ──────────────────────────────────────────────────────────

    async def _get(self, path: str) -> Any:
        url = f"{self._base}{path}"
        try:
            resp = await send_with_retry(
                lambda: self._client.get(url),
                method="GET", target=f"Uniweb GET {path}",
            )
        except RetryExhausted as exc:
            raise UniwebPartnerError(str(exc)) from exc
        return self._parse(resp, path)

    async def _post(self, path: str, body: Any) -> Any:
        url = f"{self._base}{path}"
        try:
            resp = await send_with_retry(
                lambda: self._client.post(url, json=body),
                method="POST", target=f"Uniweb POST {path}",
            )
        except RetryExhausted as exc:
            raise UniwebPartnerError(str(exc)) from exc
        return self._parse(resp, path)

    @staticmethod
    def _parse(resp: httpx.Response, path: str) -> Any:
        if resp.status_code == 401:
            raise UniwebAuthError(
                "Uniweb refused the session (401). The session/grant cookies are "
                "missing or expired — re-run the control-panel login."
            )
        if resp.status_code >= 400:
            # Never echo the body: a Uniweb response can carry a tsig or a
            # private key, and an error page is not worth leaking one.
            raise UniwebPartnerError(f"Uniweb {path} failed with {resp.status_code}.")
        try:
            return resp.json()
        except ValueError as exc:
            raise UniwebPartnerError(
                f"Uniweb {path} did not return JSON (status {resp.status_code})."
            ) from exc

    # ── Reads (the scraper's replacements) ────────────────────────────────

    async def list_subscriptions(self) -> list[dict]:
        """Every subscription under the partner."""
        return await self._get("/subscriptions") or []

    async def subscriptions_for_customer(self, customer_id: int | str) -> list[dict]:
        """Every subscription for one customer — the per-customer service list."""
        return await self._get(f"/subscriptions/customer/{quote(str(customer_id))}") or []

    async def get_subscription(self, subscription_id: int | str) -> dict:
        return await self._get(f"/subscriptions/{quote(str(subscription_id))}") or {}

    async def get_subscription_by(self, sub_type: str, username: str) -> dict:
        """A subscription by type + username, e.g. (``dns``, ``domain.no``) or
        (``ssl``, ``domain.no``). For SSL the cert/key fields may be populated —
        handle with care."""
        return await self._get(
            f"/subscriptions/{quote(sub_type)}/{quote(username)}"
        ) or {}

    async def list_customers(self) -> list[dict]:
        """Every customer under the partner — structured, with contacts."""
        return await self._get("/customers") or []

    async def dns_records(self, domain: str) -> list[dict]:
        """DNS records for a clustered domain (replaces scrape_domain_dns)."""
        return await self._get(f"/domain/{quote(domain)}/dns/record") or []

    async def list_products(self, code: str | None = None) -> list[dict]:
        path = "/products" + (f"?code={quote(code)}" if code else "")
        return await self._get(path) or []

    async def list_pricelists(self) -> list[dict]:
        return await self._get("/pricelists") or []

    async def email_count(self) -> int:
        """The number of email addresses under the partner."""
        data = await self._get("/email/count") or {}
        try:
            return int(data.get("count") or 0)
        except (ValueError, TypeError):
            return 0

    # ── Orders / invoices (the AR view) ───────────────────────────────────

    async def list_orders(self, latest_seen_invoice_no: int | str | None = None) -> list[dict]:
        """Every order/invoice under the partner: id, dates, invoiceSum, paid.

        Pass ``latest_seen_invoice_no`` to page only invoiced orders newer than
        one already seen — the API's incremental cursor for a long history.
        """
        path = "/orders"
        if latest_seen_invoice_no is not None:
            path += f"?latestSeenInvoiceNo={quote(str(latest_seen_invoice_no))}"
        return await self._get(path) or []

    async def query_orders(self, filters: dict | None = None) -> list[dict]:
        """Orders/invoices matching ``filters`` — the richer shape, carrying the
        customer and the full financial breakdown (credited / lost / waived).
        An empty query returns everything the partner can see."""
        return await self._post("/orders/query", filters or {}) or []

    async def order_lines(self, order_id: int | str) -> list[dict]:
        """The line items on one order."""
        return await self._get(f"/orders/{quote(str(order_id))}/orderlines") or []
