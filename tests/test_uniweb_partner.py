"""The Uniweb Partner API client — the structured replacement for the scraper.

These run the real client against an httpx.MockTransport, the same way
tests/test_autotask.py exercises the Autotask client, and cover the plumbing
that matters: the session cookies are actually attached, a 401 says re-login
rather than "no data", an error never echoes a body that could carry a secret,
and the secret-bearing fields are projected out before anything reaches the UI.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.services.uniweb_client import _uniweb_cookies_from_cdp
from app.services.uniweb_partner import (
    UniwebAuthError,
    UniwebPartnerClient,
    UniwebPartnerError,
    dns_record_view,
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


# ── DNS: the API record → the one value the Hub column shows ─────────────────


@pytest.mark.asyncio
async def test_dns_records_hits_the_clustered_zone_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/partner/domain/domain.no/dns/record"
        return httpx.Response(200, json=[{"type": "A", "name": "@", "address": "1.2.3.4", "ttl": 3600}])

    recs = await _mock(handler).dns_records("domain.no")
    assert recs[0]["address"] == "1.2.3.4"


def test_dns_record_view_flattens_each_type_to_its_value():
    """Every record type collapses to the single value column the Hub renders."""
    def v(rec):
        return dns_record_view(rec)["value"]

    assert v({"type": "A", "name": "@", "address": "1.2.3.4", "ttl": 3600}) == "1.2.3.4"
    assert v({"type": "CNAME", "name": "www", "alias": "domain.no"}) == "domain.no"
    assert v({"type": "MX", "name": "@", "target": "mail.domain.no", "priority": 10}) == "10 mail.domain.no"
    assert v({"type": "SRV", "name": "_sip._tcp", "priority": 10, "weight": 20,
              "port": 5060, "target": "sip.domain.no"}) == "10 20 5060 sip.domain.no"
    assert v({"type": "NS", "name": "@", "target": "ns1.uniweb.no"}) == "ns1.uniweb.no"
    assert v({"type": "WEBFORWARD", "name": "www", "url": "https://domain.no"}) == "https://domain.no"
    # A >255-char TXT arrives pre-split; concatenation reconstructs the record.
    assert v({"type": "TXT", "name": "@",
              "strings": ["v=spf1 ", "include:_spf.google.com ~all"]}) \
        == "v=spf1 include:_spf.google.com ~all"


def test_dns_record_view_keeps_hostname_and_ttl_and_drops_everything_else():
    """The projection is the boundary: only the four display fields survive, so
    a zone's DNSSEC signing key can never ride a record out to the UI."""
    view = dns_record_view({
        "type": "A", "name": "host.domain.no", "address": "1.2.3.4", "ttl": 10800,
        "keySigningKey": "SECRET", "zoneSigningKey": "SECRET",
    })
    assert view == {"hostname": "host.domain.no", "type": "A", "value": "1.2.3.4", "ttl": 10800}


# ── Expiry alerts derived from live subscriptions ────────────────────────────

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _sub(customer, code, username, to, **extra):
    return {"customer": customer, "username": username,
            "product": {"code": code, "text": code},
            "period": {"to": to}, **extra}


def test_expiry_items_derive_dates_types_and_customer_from_the_live_list():
    from app.web.routes.uniweb import _expiry_items

    accounts = {"99": {"customer_id": "acme", "customer_name": "Acme AS", "account_name": "acme-uw"}}
    subs = [
        _sub(99, "dns", "acme.no", "2026-01-20"),      # domain, 19 days
        _sub(99, "ssl", "acme.no", "2026-01-04"),      # ssl, 3 days (critical)
        _sub(99, "web", "acme.no", "2027-06-01"),      # web, beyond a year
        _sub(99, "dns", "old.no", ""),                 # no date → skipped
    ]
    items = _expiry_items(subs, accounts, _NOW, max_days=365)

    assert [i["type"] for i in items] == ["ssl", "domain"]     # sorted soonest-first, web excluded
    assert items[0]["days_remaining"] == 3 and items[0]["category"] == "critical"
    assert items[1]["days_remaining"] == 19 and items[1]["category"] == "upcoming"
    assert all(i["customer_name"] == "Acme AS" and i["customer_id"] == "acme" for i in items)


def test_expiry_items_name_an_unmatched_service_after_itself_not_nothing():
    """A subscription whose Uniweb customer isn't matched to a Sybr customer
    still appears, labelled by its own username rather than dropped."""
    from app.web.routes.uniweb import _expiry_items

    items = _expiry_items([_sub(404, "dns", "orphan.no", "2026-01-10")], {}, _NOW, max_days=365)
    assert len(items) == 1
    assert items[0]["customer_name"] == "orphan.no" and items[0]["customer_id"] == ""
