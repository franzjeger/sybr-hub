"""Datto RMM driver for the RMM deep-link (``app/integrations/rmm.py``).

Read-only, and only what the deep-link needs: the account's sites, one site's
devices, and a device by MAC address. No job, no variable, no quick job: the
Hub opens nothing in the customer's network, it hands the technician Datto's
own Web Remote link.

**Sources.** Every endpoint, field and step below is from Datto's published
documentation, not from a live tenant; nothing here has answered a real
request yet. ``test_connection()`` reports the field names a site came back
with, so the first real run is the check.

* Datto RMM API v2 help, https://rmm.datto.com/help/en/Content/2SETUP/APIv2.htm:
  the API URL per platform (``https://<platform>-api.centrastage.net``, six
  platforms listed); the token endpoint ``[API URL]/auth/oauth/token`` with
  client id ``public-client`` and client secret ``public`` sent as a Basic
  Auth header; tokens expire after 100 hours; 600 read requests per 60
  seconds, a 429 past it and a 403 with a five-minute block for persistent
  breaches; at most 250 results a page, paged with ``page`` and ``max``, with
  ``pageDetails.nextPageUrl`` null on the last page; and the endpoints
  ``GET /v2/account/sites``, ``GET /v2/site/{siteUid}``,
  ``GET /v2/site/{siteUid}/devices`` and ``GET /v2/device/macAddress/{macAddress}``
  (the address as twelve characters, no separators).
* The OpenAPI document that page links to,
  https://concord-api.centrastage.net/api/v3/api-docs/Datto-RMM-v2: the server
  base ``<API URL>/api``; a site's ``uid`` and ``name``; a device's ``uid``,
  ``siteUid``, ``hostname``, ``operatingSystem``, ``online``, ``deleted`` and
  ``webRemoteUrl``; the devices page's ``devices`` array; the MAC lookup
  answering an array of devices, and 404 when there is none.
* The grant type. Datto's own token examples are screenshots, so the text of
  the request is taken from the Datto RMM PowerShell module that page links
  to (``functions/New-ApiAccessToken.ps1`` in
  https://github.com/aaronengels/DattoRMM): ``grant_type=password`` with the
  API key as username and the API secret key as password, form-encoded. The
  same module reads ``sites`` from the sites page and counts pages from 0.

The access token is kept on the instance for the instance's life, which is one
request: no token is written anywhere, and none outlives the client.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.integrations.http_retry import RetryExhausted, send_with_retry
from app.integrations.rmm import RMMDevice, RMMError, RMMSite, normalise_mac

# Datto's public OAuth client, as its API page gives it. Not a secret: every
# Datto RMM API user sends these two values.
_CLIENT = ("public-client", "public")

_MAX_PAGE = 250
# A site or an account with more than this many pages is not one this read
# should walk; stopping is said, never returned as the whole list.
_MAX_PAGES = 100

_API_URL = re.compile(r"https://([a-z]+)-api\.centrastage\.net")


def normalise_api_url(url: str) -> str:
    """``https://<platform>-api.centrastage.net``, or ValueError.

    The shape Datto's API page gives for every platform. Anything else is
    refused: this is where the API key and secret are sent.
    """
    candidate = str(url or "").strip().lower().rstrip("/")
    if not _API_URL.fullmatch(candidate):
        raise ValueError("not a Datto RMM API URL")
    return candidate


class DattoRMMClient:
    """Async, read-only client for the Datto RMM API v2."""

    label = "Datto RMM"

    def __init__(self, api_url: str, api_key: str, api_secret: str) -> None:
        self.api_url = normalise_api_url(api_url)
        self._key = api_key
        self._secret = api_secret
        self._token = ""
        self._client = httpx.AsyncClient(timeout=30.0, headers={"Accept": "application/json"})

    async def __aenter__(self) -> DattoRMMClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # ── Plumbing ──────────────────────────────────────────────────────────

    async def _access_token(self) -> str:
        if self._token:
            return self._token
        url = f"{self.api_url}/auth/oauth/token"
        try:
            resp = await send_with_retry(
                lambda: self._client.post(
                    url,
                    auth=_CLIENT,
                    data={
                        "grant_type": "password",
                        "username": self._key,
                        "password": self._secret,
                    },
                ),
                method="POST",
                target="Datto RMM token",
            )
        except RetryExhausted as exc:
            raise RMMError(str(exc)) from exc
        if resp.status_code != 200:
            # The body is not quoted: an OAuth error page can echo the request.
            raise RMMError(
                f"Datto RMM refused the API key and secret ({resp.status_code}). Check both, "
                "and that API access is enabled for the account and the user."
            )
        token = _json(resp).get("access_token")
        if not isinstance(token, str) or not token:
            raise RMMError("Datto RMM answered the token request without an access token.")
        self._token = token
        return token

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        token = await self._access_token()
        url = f"{self.api_url}/api{path}"
        try:
            return await send_with_retry(
                lambda: self._client.get(
                    url, params=params, headers={"Authorization": f"Bearer {token}"}
                ),
                method="GET",
                target="Datto RMM API",
            )
        except RetryExhausted as exc:
            raise RMMError(str(exc)) from exc

    def _refused(self, resp: httpx.Response, what: str) -> RMMError:
        if resp.status_code == 401:
            return RMMError(f"Datto RMM did not accept the access token reading {what} (401).")
        if resp.status_code == 403:
            return RMMError(
                f"Datto RMM refused to read {what} (403). The API user's security level may "
                "not reach it, or the rate limit has blocked this address for five minutes."
            )
        return RMMError(f"Datto RMM could not read {what} ({resp.status_code}).")

    async def _pages(self, path: str, key: str, what: str) -> list[dict[str, Any]]:
        """Every item of a paged collection, or RMMError. Never a partial list."""
        items: list[dict[str, Any]] = []
        for page in range(_MAX_PAGES):
            resp = await self._get(path, {"max": _MAX_PAGE, "page": page})
            if resp.status_code != 200:
                raise self._refused(resp, what)
            body = _json(resp)
            batch = body.get(key)
            if not isinstance(batch, list):
                raise RMMError(f"Datto RMM answered {what} without a '{key}' list.")
            items.extend(i for i in batch if isinstance(i, dict))
            details = body.get("pageDetails")
            if not isinstance(details, dict) or not details.get("nextPageUrl"):
                return items
        raise RMMError(f"Datto RMM listed more than {_MAX_PAGES} pages of {what}; stopped.")

    def _device(self, raw: dict[str, Any]) -> RMMDevice:
        online = raw.get("online")
        return RMMDevice(
            uid=str(raw.get("uid") or ""),
            hostname=str(raw.get("hostname") or ""),
            site_uid=str(raw.get("siteUid") or ""),
            web_remote_url=self._safe_link(raw.get("webRemoteUrl")),
            online=online if isinstance(online, bool) else None,
            operating_system=str(raw.get("operatingSystem") or ""),
        )

    def _safe_link(self, value: object) -> str:
        """Datto's Web Remote link, if it is one a browser may be sent to.

        https only, no user name or password in it, and none of the Hub's own
        secrets: the link is put in front of a technician and opened in a new
        tab, so it must carry nothing but what Datto gave for the device.
        """
        url = str(value or "").strip()
        if not url:
            return ""
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            return ""
        secrets = [s for s in (self._key, self._secret, self._token) if s]
        if any(s in url for s in secrets):
            return ""
        return url

    # ── The provider interface ────────────────────────────────────────────

    async def list_sites(self) -> list[RMMSite]:
        raw = await self._pages("/v2/account/sites", "sites", "the account's sites")
        return [
            RMMSite(uid=str(s.get("uid") or ""), name=str(s.get("name") or ""))
            for s in raw
            if s.get("uid")
        ]

    async def get_site(self, site_uid: str) -> RMMSite | None:
        """The site, or None when Datto has none with this uid (404)."""
        resp = await self._get(f"/v2/site/{quote(site_uid, safe='')}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise self._refused(resp, "the site")
        body = _json(resp)
        uid = str(body.get("uid") or "")
        if not uid:
            raise RMMError("Datto RMM answered the site without a uid.")
        return RMMSite(uid=uid, name=str(body.get("name") or ""))

    async def list_site_devices(self, site_uid: str) -> list[RMMDevice]:
        """The site's devices. A deleted device is no device to open a session on."""
        raw = await self._pages(
            f"/v2/site/{quote(site_uid, safe='')}/devices", "devices", "the site's devices"
        )
        return [self._device(d) for d in raw if d.get("uid") and d.get("deleted") is not True]

    async def devices_by_mac(self, mac: str) -> list[RMMDevice]:
        """The devices with this MAC address, in any site; [] when Datto has none."""
        normalised = normalise_mac(mac)
        if normalised is None:
            return []
        resp = await self._get(f"/v2/device/macAddress/{normalised}")
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            raise self._refused(resp, "a device by MAC address")
        try:
            body = resp.json()
        except ValueError as exc:
            raise RMMError("Datto RMM answered a MAC address lookup with no JSON.") from exc
        if not isinstance(body, list):
            raise RMMError("Datto RMM answered a MAC address lookup without a list.")
        return [
            self._device(d)
            for d in body
            if isinstance(d, dict) and d.get("uid") and d.get("deleted") is not True
        ]

    async def test_connection(self) -> dict[str, Any]:
        """A token and one page of one site, reporting the field names that came back.

        The site, not the field names, stays here: a connection test has no
        reason to put a customer's record on screen.
        """
        result: dict[str, Any] = {"ok": False, "sample_fields": []}
        try:
            resp = await self._get("/v2/account/sites", {"max": 1, "page": 0})
            if resp.status_code != 200:
                raise self._refused(resp, "the account's sites")
            sites = _json(resp).get("sites")
            if not isinstance(sites, list):
                raise RMMError("Datto RMM answered the sites without a 'sites' list.")
            result["ok"] = True
            result["returned"] = len(sites)
            if sites and isinstance(sites[0], dict):
                result["sample_fields"] = sorted(sites[0])
        except RMMError as exc:
            result["error"] = str(exc)
        except httpx.HTTPError as exc:
            result["error"] = f"Could not reach Datto RMM: {type(exc).__name__}"
        return result


def _json(resp: httpx.Response) -> dict[str, Any]:
    try:
        body = resp.json()
    except ValueError as exc:
        raise RMMError("Datto RMM answered with something that is not JSON.") from exc
    if not isinstance(body, dict):
        raise RMMError("Datto RMM answered with an unexpected shape.")
    return body
