"""ALSO Cloud Marketplace API client.

Base URL per country:
  Norway:  https://marketplace.also.no
  Sweden:  https://marketplace.also.se
  Denmark: https://marketplace.also.dk
  Finland: https://marketplace.also.fi

Auth: POST GetSessionToken with username/password → session token.
All subsequent requests use header: Authenticate: CCPSessionId <token>

API docs: https://app.swaggerhub.com/apis/MarketplaceSimpleAPI/MarketplaceSimpleAPI/1.0.0
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import UTC
from typing import ClassVar

import httpx

from app.integrations.http_retry import send_with_retry

logger = logging.getLogger(__name__)

# Country → base URL mapping
ALSO_URLS = {
    "no": "https://marketplace.also.no",
    "se": "https://marketplace.also.se",
    "dk": "https://marketplace.also.dk",
    "fi": "https://marketplace.also.fi",
    "de": "https://marketplace.also.de",
    "nl": "https://marketplace.also.nl",
    "ch": "https://marketplace.also.ch",
    "at": "https://marketplace.also.at",
}

API_PATH = "/SimpleAPI/SimpleAPIService.svc/rest"


class AlsoCloudError(Exception):
    """Raised on API errors."""

    def __init__(self, message: str, *, message_key: str | None = None):
        super().__init__(message)
        self.message_key = message_key


class AlsoCloudAuthError(AlsoCloudError):
    """ALSO rejected the supplied credentials, including XML faults with HTTP 500."""


def _authentication_fault(resp: httpx.Response) -> str:
    # SimpleAPI uses HTTP 500 for wrong credentials and unsupported MFA. Parse
    # only a small XML fault, never echo its body (which may contain secrets).
    if len(resp.content) > 16384 or b"<!DOCTYPE" in resp.content.upper():
        return ""
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return ""
    messages = " ".join(
        e.text or "" for e in root.iter() if e.tag.split("}")[-1] in ("Message", "Text")
    ).lower()
    return messages


class AlsoCloudClient:
    """Client for the ALSO Cloud Marketplace SimpleAPI."""

    def __init__(self, username: str, password: str, country: str = "no"):
        self.username = username
        self.password = password
        base = ALSO_URLS.get(country.lower(), ALSO_URLS["no"])
        self.base_url = f"{base}{API_PATH}"
        self._session_token: str | None = None
        self._client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        await self.authenticate()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        if self._session_token:
            try:
                await self._post("TerminateSessionToken", {})
            except Exception:
                # The token expires on its own; a failed logout is not worth
                # propagating out of close().
                logger.debug("ALSO session logout failed", exc_info=True)
        await self._client.aclose()

    # ── Authentication ────────────────────────────────────────────────────

    async def authenticate(self) -> str:
        """Get a session token."""
        # The token call too: throttled here, every later call fails with it.
        resp = await send_with_retry(
            lambda: self._client.post(
                f"{self.base_url}/GetSessionToken",
                json={"username": self.username, "password": self.password},
                headers={"Content-Type": "application/json"},
            ),
            method="POST",
            target="ALSO GetSessionToken",
        )
        fault = _authentication_fault(resp)
        if "users with enabled mfa are not supported" in fault:
            raise AlsoCloudAuthError(
                "MFA is enabled on the ALSO account. SimpleAPI does not support MFA sign-in.",
                message_key="err_also_mfa_unsupported",
            )
        if resp.status_code in (401, 403) or "check your username and password" in fault:
            raise AlsoCloudAuthError(
                "ALSO rejected the username or password. Check the Marketplace API credentials.",
                message_key="err_also_credentials",
            )
        if resp.is_error:
            raise AlsoCloudError(
                f"ALSO sign-in service returned HTTP {resp.status_code}.",
                message_key="err_also_unavailable",
            )
        token = resp.text.strip().strip('"')
        if not token or "error" in token.lower() or "<" in token:
            raise AlsoCloudError(
                "ALSO returned an invalid sign-in response.", message_key="err_also_unavailable"
            )
        self._session_token = token
        logger.info("ALSO Cloud authenticated")
        return token

    async def ping(self) -> bool:
        """Verify session is alive."""
        try:
            await self._post("PingPong", {})
            return True
        except Exception:
            logger.debug("ALSO ping failed", exc_info=True)
            return False

    # ── API call tracking ────────────────────────────────────────────────
    _call_log: ClassVar[list[dict]] = []  # shared across instances

    @classmethod
    def get_api_stats(cls) -> dict:
        """Return API usage stats for the current session."""
        calls = cls._call_log
        if not calls:
            return {"total_calls": 0, "session_start": None}
        from datetime import datetime

        now = datetime.now(UTC)
        last_1m = [c for c in calls if (now - c["ts"]).total_seconds() < 60]
        last_5m = [c for c in calls if (now - c["ts"]).total_seconds() < 300]
        errors = [c for c in calls if c.get("error")]
        avg_ms = sum(c["ms"] for c in calls) / len(calls) if calls else 0
        return {
            "total_calls": len(calls),
            "last_1min": len(last_1m),
            "last_5min": len(last_5m),
            "errors": len(errors),
            "avg_response_ms": round(avg_ms),
            "session_start": calls[0]["ts"].isoformat() if calls else None,
            "last_call": calls[-1]["ts"].isoformat() if calls else None,
            "last_endpoint": calls[-1]["endpoint"] if calls else None,
            "last_status": calls[-1].get("status") if calls else None,
        }

    @classmethod
    def reset_api_stats(cls) -> None:
        cls._call_log.clear()

    # ── Core API call ─────────────────────────────────────────────────────

    async def _post(self, endpoint: str, payload: dict) -> dict:
        """Make an authenticated API call."""
        import time
        from datetime import datetime

        if not self._session_token:
            await self.authenticate()

        headers = {
            "Content-Type": "application/json",
            "Authenticate": f"CCPSessionId {self._session_token}",
        }
        t0 = time.monotonic()
        # Every ALSO call is a POST, reads included, so only throttling is
        # retried here — a 5xx could be a half-applied write and this client
        # cannot tell which endpoints those are.
        resp = await send_with_retry(
            lambda: self._client.post(
                f"{self.base_url}/{endpoint}",
                json=payload,
                headers=headers,
            ),
            method="POST",
            target=f"ALSO {endpoint}",
        )
        elapsed_ms = round((time.monotonic() - t0) * 1000)

        # Handle XML error responses
        if resp.headers.get("content-type", "").startswith("text/xml"):
            self._call_log.append(
                {
                    "ts": datetime.now(UTC),
                    "endpoint": endpoint,
                    "status": resp.status_code,
                    "ms": elapsed_ms,
                    "error": "XML",
                }
            )
            raise AlsoCloudError(f"API error (XML): {resp.text[:300]}")

        if resp.status_code == 401:
            # Re-authenticate and retry once
            await self.authenticate()
            headers["Authenticate"] = f"CCPSessionId {self._session_token}"
            t0 = time.monotonic()
            resp = await send_with_retry(
                lambda: self._client.post(
                    f"{self.base_url}/{endpoint}",
                    json=payload,
                    headers=headers,
                ),
                method="POST",
                target=f"ALSO {endpoint} (after re-auth)",
            )
            elapsed_ms = round((time.monotonic() - t0) * 1000)

        # Log the call
        self._call_log.append(
            {
                "ts": datetime.now(UTC),
                "endpoint": endpoint,
                "status": resp.status_code,
                "ms": elapsed_ms,
                "error": None if resp.status_code < 400 else resp.status_code,
            }
        )

        if resp.status_code >= 400:
            logger.warning(
                "ALSO API %s → %d (%dms) [calls: %d in session, %d/min]",
                endpoint,
                resp.status_code,
                elapsed_ms,
                len(self._call_log),
                len(
                    [
                        c
                        for c in self._call_log
                        if (datetime.now(UTC) - c["ts"]).total_seconds() < 60
                    ]
                ),
            )

        resp.raise_for_status()

        try:
            return resp.json()
        except ValueError:
            # Some endpoints return plain text
            return {"_raw": resp.text}

    # ── Company / Customer endpoints ──────────────────────────────────────

    async def get_companies(self, parent_account_id: str = "") -> list[dict]:
        """Get all end-customer companies."""
        payload = {}
        if parent_account_id:
            payload["ParentAccountId"] = parent_account_id
        result = await self._post("GetCompanies", payload)
        return (
            result if isinstance(result, list) else result.get("Accounts", result.get("value", []))
        )

    async def get_company(self, account_id: str) -> dict:
        """Get a single company by ID."""
        return await self._post("GetCompany", {"AccountId": account_id})

    async def create_company(self, data: dict) -> dict:
        """Create a new end-customer company."""
        return await self._post("CreateCompany", data)

    async def update_company(self, data: dict) -> dict:
        """Update company details."""
        return await self._post("UpdateCompany", data)

    # ── Subscription / License endpoints ──────────────────────────────────

    async def get_subscriptions(self, account_id: str) -> list[dict]:
        """Get all subscriptions for a company.

        The ALSO SimpleAPI expects ``parentAccountId`` (int) — the company's
        AccountId under which subscriptions live.
        """
        aid = int(account_id) if str(account_id).isdigit() else account_id
        result = await self._post("GetSubscriptions", {"parentAccountId": aid})
        return (
            result if isinstance(result, list) else result.get("Accounts", result.get("value", []))
        )

    async def get_subscription(self, account_id: str) -> dict:
        """Get a single subscription by its accountId."""
        aid = int(account_id) if str(account_id).isdigit() else account_id
        return await self._post("GetSubscription", {"accountId": aid})

    async def get_subscription_with_addons(self, account_id: str) -> dict:
        """Get subscription with all addon services."""
        aid = int(account_id) if str(account_id).isdigit() else account_id
        return await self._post("GetSubscriptionWithAddons", {"accountId": aid})

    async def update_subscription(self, data: dict) -> dict:
        """Update a subscription (e.g., change seat count)."""
        return await self._post("UpdateSubscription", data)

    async def create_subscription(self, data: dict) -> dict:
        """Create a new subscription."""
        return await self._post("CreateSubscription", data)

    async def get_possible_services(self, parent_account_id: str) -> list[dict]:
        """List available services for a company."""
        result = await self._post(
            "GetPossibleServicesForParent", {"ParentAccountId": parent_account_id}
        )
        return result if isinstance(result, list) else result.get("Services", [])

    # ── Invoice / Billing endpoints ───────────────────────────────────────

    async def get_preview_invoices(self) -> list[dict]:
        """Get current month (unclosed) invoices."""
        result = await self._post("GetPreviewInvoices", {})
        return result if isinstance(result, list) else result.get("Invoices", [])

    async def get_latest_invoices(self) -> list[dict]:
        """Get last closed billing period invoices."""
        result = await self._post("GetLatestInvoices", {})
        return result if isinstance(result, list) else result.get("Invoices", [])

    async def get_invoices_for_period(self, year: int, month: int) -> list[dict]:
        """Get invoices for a specific period."""
        result = await self._post("GetLatestInvoicesForPeriod", {"Year": year, "Month": month})
        return result if isinstance(result, list) else result.get("Invoices", [])

    # ── Utility endpoints ─────────────────────────────────────────────────

    async def get_marketplaces(self) -> list[dict]:
        """List your marketplaces."""
        result = await self._post("GetMarketplaces", {})
        return result if isinstance(result, list) else result.get("Marketplaces", [])

    async def get_service_information(self, service_id: str) -> dict:
        """Get metadata about a service."""
        return await self._post("GetServiceInformation", {"ServiceId": service_id})
