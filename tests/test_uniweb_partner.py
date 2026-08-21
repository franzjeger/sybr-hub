"""The Uniweb Partner API client — the structured replacement for the scraper.

These run the real client against an httpx.MockTransport, the same way
tests/test_autotask.py exercises the Autotask client, and cover the plumbing
that matters: the session cookies are actually attached, a 401 says re-login
rather than "no data", an error never echoes a body that could carry a secret,
and the secret-bearing fields are projected out before anything reaches the UI.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.uniweb_client import _uniweb_cookies_from_cdp
from app.services.uniweb_partner import (
    UniwebAuthError,
    UniwebPartnerClient,
    UniwebPartnerError,
    public_subscription,
)

_COOKIES = {"session": "sess-abc", "grant": "grant-xyz"}


def _mock(handler, cookies=None) -> UniwebPartnerClient:
    """A client whose transport is a mock, with the real cookie header kept."""
    c = UniwebPartnerClient(cookies or _COOKIES)
    headers = dict(c._client.headers)
    c._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers=headers
    )
    return c


_SUB = {
    "id": 1234, "customer": 99, "username": "domain.no", "tsig": "SECRET-TSIG",
    "product": {"id": 102091, "text": ".no domene", "code": "dns"},
    "otc": 60.0, "rc": 179.0, "inOtc": 50.0, "inRc": 85.5, "renew": True,
    "created": "2020-05-08",
    "period": {"from": "2020-05-08", "to": "2021-03-09", "qty": 1},
}


@pytest.mark.asyncio
async def test_subscriptions_parse_and_carry_pricing():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/partner/subscriptions"
        return httpx.Response(200, json=[_SUB])

    subs = await _mock(handler).list_subscriptions()
    assert len(subs) == 1
    assert subs[0]["rc"] == 179.0 and subs[0]["inRc"] == 85.5  # charge vs cost


@pytest.mark.asyncio
async def test_the_session_cookies_are_attached():
    """Auth is the whole game here — the cookies must reach the request."""
    def handler(request: httpx.Request) -> httpx.Response:
        cookie = request.headers.get("cookie", "")
        assert "session=sess-abc" in cookie and "grant=grant-xyz" in cookie
        return httpx.Response(200, json=[])

    await _mock(handler).list_subscriptions()


@pytest.mark.asyncio
async def test_subscriptions_for_customer_hits_the_right_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/partner/subscriptions/customer/99"
        return httpx.Response(200, json=[_SUB])

    assert await _mock(handler).subscriptions_for_customer(99)


@pytest.mark.asyncio
async def test_email_count_returns_an_int():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/partner/email/count"
        return httpx.Response(200, json={"count": 1234})

    assert await _mock(handler).email_count() == 1234


@pytest.mark.asyncio
async def test_a_401_says_re_login_not_no_data():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)  # the API answers 401 with no body

    with pytest.raises(UniwebAuthError) as ei:
        await _mock(handler).list_customers()
    assert "control-panel login" in str(ei.value)


@pytest.mark.asyncio
async def test_an_error_never_echoes_the_body():
    """A Uniweb response can carry a tsig or a private key — an error must not
    leak one into an exception message or a log."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="tsig=SECRET-TSIG leaked in a stack trace")

    with pytest.raises(UniwebPartnerError) as ei:
        await _mock(handler).list_subscriptions()
    assert "SECRET-TSIG" not in str(ei.value)


def test_public_subscription_drops_secrets_and_keeps_margin():
    pub = public_subscription(_SUB)
    assert "tsig" not in pub
    assert pub["rc"] == 179.0 and pub["inRc"] == 85.5  # margin still derivable
    assert pub["product"]["code"] == "dns"


def test_empty_cookies_is_an_auth_error_at_construction():
    with pytest.raises(UniwebAuthError):
        UniwebPartnerClient({})


def test_cookie_filter_keeps_uniweb_and_drops_others():
    cdp = [
        {"name": "session", "value": "s", "domain": "www.uniweb.no"},
        {"name": "grant", "value": "g", "domain": ".uniweb.no"},
        {"name": "tracker", "value": "t", "domain": "ads.example.com"},
    ]
    got = _uniweb_cookies_from_cdp(cdp)
    assert got == {"session": "s", "grant": "g"}


def test_the_route_summary_projects_secrets_out_and_sums_margin():
    """The subscriptions summary hands back margin, never a secret."""
    from app.web.routes.uniweb import _subscription_summary

    out = _subscription_summary("acme", [
        _SUB,  # rc 179.0 / inRc 85.5, carries a tsig
        {"id": 2, "rc": 100.0, "inRc": 40.0, "tsig": "X", "product": {"code": "web"}},
    ])
    assert out["matched"] is True
    assert out["count"] == 2
    assert out["monthly_revenue"] == 279.0   # 179 + 100
    assert out["monthly_cost"] == 125.5      # 85.5 + 40
    assert out["monthly_margin"] == 153.5
    assert all("tsig" not in s for s in out["subscriptions"])
