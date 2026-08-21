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
from typing import Any
from urllib.parse import quote

import httpx

from app.integrations.http_retry import RetryExhausted, send_with_retry

logger = logging.getLogger(__name__)

BASE_URL = "https://www.uniweb.no/api/partner"

# Fields that carry secrets. Never log them; never hand them to the UI as-is.
_SENSITIVE_FIELDS = frozenset({
    "tsig", "key", "password", "keySigningKey", "zoneSigningKey",
    "combinedSigningKey", "keystore",
})

# The non-secret subscription fields the Hub view needs — identity, product,
# pricing (charge vs cost, so margin is derivable) and period.
_PUBLIC_SUBSCRIPTION_FIELDS = (
    "id", "customer", "username", "product", "otc", "rc", "inOtc", "inRc",
    "renew", "created", "period", "disk", "xfer", "concurrency", "cpu",
    "mem", "dmem",
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
