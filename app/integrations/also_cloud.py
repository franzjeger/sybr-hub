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
from typing import Optional

import httpx

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
    pass


class AlsoCloudClient:
    """Client for the ALSO Cloud Marketplace SimpleAPI."""

    def __init__(self, username: str, password: str, country: str = "no"):
        self.username = username
        self.password = password
        base = ALSO_URLS.get(country.lower(), ALSO_URLS["no"])
        self.base_url = f"{base}{API_PATH}"
        self._session_token: Optional[str] = None
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
                pass
        await self._client.aclose()

    # ── Authentication ────────────────────────────────────────────────────

    async def authenticate(self) -> str:
        """Get a session token."""
        resp = await self._client.post(
            f"{self.base_url}/GetSessionToken",
            json={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        token = resp.text.strip().strip('"')
        if not token or "error" in token.lower() or "<" in token:
            raise AlsoCloudError(f"Authentication failed: {resp.text[:200]}")
        self._session_token = token
        logger.info("ALSO Cloud authenticated (token: %s...)", token[:8])
        return token

    async def ping(self) -> bool:
        """Verify session is alive."""
        try:
            result = await self._post("PingPong", {})
            return True
        except Exception:
            return False

    # ── API call tracking ────────────────────────────────────────────────
    _call_log: list[dict] = []  # shared across instances

    @classmethod
    def get_api_stats(cls) -> dict:
        """Return API usage stats for the current session."""
        calls = cls._call_log
        if not calls:
            return {"total_calls": 0, "session_start": None}
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
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
        from datetime import datetime, timezone

        if not self._session_token:
            await self.authenticate()

        headers = {
            "Content-Type": "application/json",
            "Authenticate": f"CCPSessionId {self._session_token}",
        }
        t0 = time.monotonic()
        resp = await self._client.post(
            f"{self.base_url}/{endpoint}",
            json=payload,
            headers=headers,
        )
        elapsed_ms = round((time.monotonic() - t0) * 1000)

        # Handle XML error responses
        if resp.headers.get("content-type", "").startswith("text/xml"):
            self._call_log.append({"ts": datetime.now(timezone.utc), "endpoint": endpoint, "status": resp.status_code, "ms": elapsed_ms, "error": "XML"})
            raise AlsoCloudError(f"API error (XML): {resp.text[:300]}")

        if resp.status_code == 401:
            # Re-authenticate and retry once
            await self.authenticate()
            headers["Authenticate"] = f"CCPSessionId {self._session_token}"
            t0 = time.monotonic()
            resp = await self._client.post(
                f"{self.base_url}/{endpoint}",
                json=payload,
                headers=headers,
            )
            elapsed_ms = round((time.monotonic() - t0) * 1000)

        # Log the call
        self._call_log.append({
            "ts": datetime.now(timezone.utc),
            "endpoint": endpoint,
            "status": resp.status_code,
            "ms": elapsed_ms,
            "error": None if resp.status_code < 400 else resp.status_code,
        })

        if resp.status_code >= 400:
            logger.warning("ALSO API %s → %d (%dms) [calls: %d in session, %d/min]",
                        endpoint, resp.status_code, elapsed_ms,
                        len(self._call_log),
                        len([c for c in self._call_log if (datetime.now(timezone.utc) - c["ts"]).total_seconds() < 60]))

        resp.raise_for_status()

        try:
            return resp.json()
        except Exception:
            # Some endpoints return plain text
            return {"_raw": resp.text}

    # ── Company / Customer endpoints ──────────────────────────────────────

    async def get_companies(self, parent_account_id: str = "") -> list[dict]:
        """Get all end-customer companies."""
        payload = {}
        if parent_account_id:
            payload["ParentAccountId"] = parent_account_id
        result = await self._post("GetCompanies", payload)
        return result if isinstance(result, list) else result.get("Accounts", result.get("value", []))

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
        return result if isinstance(result, list) else result.get("Accounts", result.get("value", []))

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
        result = await self._post("GetPossibleServicesForParent", {"ParentAccountId": parent_account_id})
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
