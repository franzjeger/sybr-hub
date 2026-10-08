"""The Datto RMM driver, against a fake Datto at the HTTP layer (TODO D19).

These pin what the driver *sends* and how it reads what comes back. They prove
nothing about what a live Datto tenant answers: the driver was written from
Datto's published API page and OpenAPI document, and no Datto credentials
exist here. ``test_connection()`` against a real account is that check.

What they do catch: a token request in the wrong shape, a secret where it
must not be, a failed or partial read turning into an empty list, and a Web
Remote link that is not safe to put in front of a technician.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import pytest

from app.integrations.datto_rmm import DattoRMMClient, normalise_api_url
from app.integrations.rmm import RMMError

API = "https://concord-api.centrastage.net"
KEY = "synthetic-api-key"
SECRET = "synthetic-api-secret"
TOKEN = "synthetic-access-token"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> DattoRMMClient:
    client = DattoRMMClient(API, KEY, SECRET)
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers=client._client.headers
    )
    return client


def _datto(routes: dict[str, object], seen: list[httpx.Request] | None = None):
    """A fake Datto: the token endpoint, then answers by path (and page)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if request.url.path == "/auth/oauth/token":
            return httpx.Response(200, json={"access_token": TOKEN, "token_type": "bearer"})
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        page = request.url.params.get("page")
        answer = routes.get(f"{request.url.path}?page={page}", routes.get(request.url.path))
        if answer is None:
            return httpx.Response(404, json={"message": "not found"})
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(200, json=answer)

    return handler


def _device(uid: str, hostname: str, site: str = "site-a", **extra: object) -> dict:
    return {
        "uid": uid,
        "hostname": hostname,
        "siteUid": site,
        "operatingSystem": "Microsoft Windows 11 Pro",
        "online": True,
        "deleted": False,
        "webRemoteUrl": f"https://concord.centrastage.net/csm/remote/{uid}",
        **extra,
    }


# ── The token ────────────────────────────────────────────────────────────────


async def test_the_token_request_is_the_documented_password_grant():
    """Datto's page: [API URL]/auth/oauth/token, public-client/public as Basic auth.

    The key and secret go in the form body, never in the URL, and one token
    serves every read the client makes.
    """
    seen: list[httpx.Request] = []
    client = _client(_datto({"/api/v2/account/sites": {"sites": [], "pageDetails": {}}}, seen))
    async with client:
        await client.list_sites()
        await client.list_sites()

    tokens = [r for r in seen if r.url.path == "/auth/oauth/token"]
    assert len(tokens) == 1
    token = tokens[0]
    assert token.method == "POST"
    assert str(token.url) == f"{API}/auth/oauth/token"
    basic = base64.b64decode(token.headers["Authorization"].split()[1]).decode()
    assert basic == "public-client:public"
    form = parse_qs(token.content.decode())
    assert form == {"grant_type": ["password"], "username": [KEY], "password": [SECRET]}
    for request in seen:
        assert KEY not in str(request.url) and SECRET not in str(request.url)
    reads = [r for r in seen if r.url.path != "/auth/oauth/token"]
    assert all(str(r.url).startswith(f"{API}/api/v2/") for r in reads)


async def test_a_refused_token_says_so_and_quotes_nothing_back():
    """An OAuth error page can echo the request; the message carries only the status."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant", "echo": SECRET})

    async with _client(handler) as client:
        with pytest.raises(RMMError) as raised:
            await client.list_sites()

    assert "400" in str(raised.value)
    assert SECRET not in str(raised.value) and KEY not in str(raised.value)


# ── Reads ─────────────────────────────────────────────────────────────────────


async def test_every_page_is_read_until_datto_says_there_is_no_next():
    routes = {
        "/api/v2/site/site-a/devices?page=0": {
            "pageDetails": {"nextPageUrl": f"{API}/api/v2/site/site-a/devices?page=1"},
            "devices": [_device("d1", "PC-01")],
        },
        "/api/v2/site/site-a/devices?page=1": {
            "pageDetails": {"nextPageUrl": None},
            "devices": [_device("d2", "PC-02")],
        },
    }
    seen: list[httpx.Request] = []
    async with _client(_datto(routes, seen)) as client:
        devices = await client.list_site_devices("site-a")

    assert [d.hostname for d in devices] == ["PC-01", "PC-02"]
    pages = [r.url.params for r in seen if r.url.path.endswith("/devices")]
    assert [(p["max"], p["page"]) for p in pages] == [("250", "0"), ("250", "1")]


async def test_a_deleted_device_is_no_device():
    routes = {
        "/api/v2/site/site-a/devices": {
            "pageDetails": {},
            "devices": [_device("d1", "PC-01"), _device("d2", "PC-OLD", deleted=True)],
        }
    }
    async with _client(_datto(routes)) as client:
        devices = await client.list_site_devices("site-a")

    assert [d.uid for d in devices] == ["d1"]


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(403, json={"message": "Forbidden"}),
        httpx.Response(500, text="oops"),
        {"pageDetails": {}},
        {"pageDetails": {}, "devices": "none"},
    ],
    ids=["403", "500", "no-list", "not-a-list"],
)
async def test_a_failed_read_raises_rather_than_reading_as_no_devices(answer):
    """The failure this codebase keeps finding: "could not ask" read as "none"."""
    async with _client(_datto({"/api/v2/site/site-a/devices": answer})) as client:
        with pytest.raises(RMMError):
            await client.list_site_devices("site-a")


async def test_a_collection_past_the_page_cap_is_refused_not_truncated(monkeypatch):
    monkeypatch.setattr("app.integrations.datto_rmm._MAX_PAGES", 2)
    endless = {"pageDetails": {"nextPageUrl": f"{API}/next"}, "sites": [{"uid": "s", "name": "S"}]}
    async with _client(_datto({"/api/v2/account/sites": endless})) as client:
        with pytest.raises(RMMError, match="more than 2 pages"):
            await client.list_sites()


async def test_a_site_datto_does_not_have_is_none():
    routes = {"/api/v2/site/site-a": {"uid": "site-a", "name": "Kunde A"}}
    async with _client(_datto(routes)) as client:
        assert (await client.get_site("site-a")).name == "Kunde A"
        assert await client.get_site("site-x") is None


async def test_a_mac_lookup_sends_the_twelve_digit_form_and_reads_none_as_empty():
    """Datto's page: the address as XXXXXXXXXXXX. A 404 is "no device"."""
    routes = {"/api/v2/device/macAddress/0A1B2C3D4E5F": [_device("d1", "MAC-01")]}
    seen: list[httpx.Request] = []
    async with _client(_datto(routes, seen)) as client:
        found = await client.devices_by_mac("0a:1b:2c:3d:4e:5f")
        missing = await client.devices_by_mac("0a-1b-2c-3d-4e-60")
        placeholder = await client.devices_by_mac("00:00:00:00:00:00")

    assert [d.uid for d in found] == ["d1"]
    assert missing == [] and placeholder == []
    assert not any(r.url.path.endswith("000000000000") for r in seen), "no lookup for a placeholder"


# ── The Web Remote link ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("link", "kept"),
    [
        ("https://concord.centrastage.net/csm/remote/d1", True),
        ("http://concord.centrastage.net/csm/remote/d1", False),
        ("javascript:alert(1)", False),
        ("https://user:pass@concord.centrastage.net/remote", False),
        (f"https://concord.centrastage.net/remote?token={TOKEN}", False),
        (f"https://concord.centrastage.net/remote?k={KEY}", False),
        ("", False),
    ],
)
async def test_only_a_plain_https_link_without_a_secret_reaches_the_page(link, kept):
    """The button opens this link in a new tab: nothing of the Hub's may ride in it."""
    routes = {"/api/v2/site/site-a/devices": {"devices": [_device("d1", "PC-01")]}}
    routes["/api/v2/site/site-a/devices"]["devices"][0]["webRemoteUrl"] = link
    async with _client(_datto(routes)) as client:
        device = (await client.list_site_devices("site-a"))[0]

    assert device.web_remote_url == (link if kept else "")


# ── The connection test and the URL ───────────────────────────────────────────


async def test_the_connection_test_reports_field_names_not_the_site():
    routes = {"/api/v2/account/sites": {"sites": [{"uid": "site-a", "name": "Kunde A"}]}}
    seen: list[httpx.Request] = []
    async with _client(_datto(routes, seen)) as client:
        result = await client.test_connection()

    assert result == {"ok": True, "sample_fields": ["name", "uid"], "returned": 1}
    read = next(r for r in seen if r.url.path == "/api/v2/account/sites")
    assert read.url.params["max"] == "1"


async def test_a_failed_connection_test_is_not_ok():
    async with _client(_datto({"/api/v2/account/sites": httpx.Response(401)})) as client:
        result = await client.test_connection()

    assert result["ok"] is False and "401" in result["error"]


@pytest.mark.parametrize(
    "url",
    [
        "https://concord-api.centrastage.net",
        "https://Merlot-API.centrastage.net/",
        " https://syrah-api.centrastage.net ",
    ],
)
def test_a_datto_api_url_is_accepted_in_the_form_datto_shows_it(url):
    assert normalise_api_url(url).endswith("-api.centrastage.net")


@pytest.mark.parametrize(
    "url",
    [
        "http://concord-api.centrastage.net",
        "https://concord-api.centrastage.net/api",
        "https://concord-api.centrastage.net.evil.example",
        "https://evil.example/concord-api.centrastage.net",
        "https://api.example",
        "",
    ],
)
def test_any_other_url_is_refused_because_the_secret_is_sent_there(url):
    with pytest.raises(ValueError):
        normalise_api_url(url)
