"""Regression tests for data-quality fixes in collectors.

These tests lock in five behaviors:

1. DNS queries (DoH section + service-level dnspython) distinguish a
   transport error from "the record doesn't exist". A SERVFAIL or HTTP
   failure must NOT render as 'MISSING' in the email security audit —
   that produces false negatives ("configure SPF" findings when in
   reality we couldn't check).
2. The Microsoft Graph client raises (rather than returning ``{}``) when
   it cannot get a successful response, so callers can never mistake
   "throttled out" for "no data".
3. ITGlueClient.list_organizations walks every page so MSPs with >250
   organizations see the full list.
4. The sign-in activity collector keeps "unknown" events separate from
   successes. Defaulting a missing status.errorCode to 0 (= success)
   under-reports failures.
5. A per-user MFA methods lookup that fails is reported as unknown, not
   as "this user has no MFA". Same shape as (1) and (2): the collector
   must not launder a transport failure into a definite finding.

The report layer has the same invariant on the presentation side; see
``tests/test_report_radar.py``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import dns.exception
import dns.resolver
import httpx
import pytest


# ── DNS: error vs. missing ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_doh_query_transport_failure_raises_dnslookuperror():
    """An httpx-level failure must surface as DnsLookupError, not [].

    Returning [] in this case is what produced the false 'MISSING' SPF
    classification in v10.10 — fix that and keep it broken.
    """
    from app.modules.m365_audit.sections.dns import DnsLookupError, _doh_query

    async def _raise(*_a, **_kw):
        raise httpx.ConnectError("network is unreachable")

    client = httpx.AsyncClient()
    client.get = _raise  # type: ignore[assignment]

    with pytest.raises(DnsLookupError):
        await _doh_query(client, "example.com", "TXT")


@pytest.mark.asyncio
async def test_doh_query_nxdomain_returns_empty():
    """NXDOMAIN (Status=3) is a definitive 'no record' — return []."""
    from app.modules.m365_audit.sections.dns import _doh_query

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"Status": 3, "Answer": []}

    client = httpx.AsyncClient()
    client.get = AsyncMock(return_value=_Resp())  # type: ignore[assignment]

    assert await _doh_query(client, "nonexistent.invalid", "TXT") == []


@pytest.mark.asyncio
async def test_doh_query_servfail_raises():
    """SERVFAIL (Status=2) means the upstream resolver gave up — that is
    NOT 'record absent' and must not be conflated with one."""
    from app.modules.m365_audit.sections.dns import DnsLookupError, _doh_query

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"Status": 2, "Answer": []}

    client = httpx.AsyncClient()
    client.get = AsyncMock(return_value=_Resp())  # type: ignore[assignment]

    with pytest.raises(DnsLookupError):
        await _doh_query(client, "broken.example.com", "TXT")


@pytest.mark.asyncio
async def test_check_domain_marks_error_not_missing_on_lookup_failure():
    """The classification for a domain whose SPF lookup failed must be
    'ERROR (...)', not 'MISSING'. Auditors interpret 'MISSING' as
    'configure SPF' — a wrong recommendation when the truth is 'we
    don't know'."""
    from app.modules.m365_audit.sections import dns as dns_section

    async def _query(client, name, qtype):
        # Every query fails — simulate a DoH outage
        raise dns_section.DnsLookupError(f"simulated: {qtype} {name}")

    with patch.object(dns_section, "_doh_query", side_effect=_query):
        result = await dns_section._check_domain(
            httpx.AsyncClient(), "example.com"
        )

    assert result["spf_status"].startswith("ERROR")
    assert result["dmarc_status"].startswith("ERROR")
    assert "_lookup_errors" in result
    # MTA-STS uses MISSING for "name exists but no record" — distinct from ERROR
    assert result["mta_sts"].startswith("ERROR")


# ── Graph client: never return {} silently ────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_client_raises_after_three_throttles():
    """If every retry comes back 429, raise — never return {}.

    Silently returning an empty dict was the original v10.10 bug: callers
    that called .get('value', []) saw 'no policies', and the audit shipped
    a report claiming the tenant had none."""
    from app.modules.m365_audit.graph_client import GraphClient

    class _Cred:
        async def get_token(self, _scope):
            class _T:
                token = "x"

            return _T()

    class _Resp:
        status_code = 429
        headers = {"Retry-After": "0"}
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {}

    async with GraphClient(_Cred(), timeout=1) as g:
        g._http.get = AsyncMock(return_value=_Resp())  # type: ignore[assignment]
        with pytest.raises(httpx.HTTPError):
            await g._get("https://graph.microsoft.com/v1.0/foo")


@pytest.mark.asyncio
async def test_graph_client_401_returns_error_dict():
    """401/403 still returns a structured error dict — callers depend on
    that contract (see validate_permissions). Keep the contract while
    fixing the throttling case."""
    from app.modules.m365_audit.graph_client import GraphClient

    class _Cred:
        async def get_token(self, _scope):
            class _T:
                token = "x"

            return _T()

    class _Resp:
        status_code = 401
        text = "no auth"
        headers: dict = {}

        def raise_for_status(self):
            raise httpx.HTTPStatusError("401", request=None, response=None)  # type: ignore[arg-type]

        def json(self):
            return {}

    async with GraphClient(_Cred(), timeout=1) as g:
        g._http.get = AsyncMock(return_value=_Resp())  # type: ignore[assignment]
        out = await g._get("https://graph.microsoft.com/v1.0/foo")

    assert out["error"] == 401


# ── IT Glue: list_organizations walks all pages ───────────────────────────────


@pytest.mark.asyncio
async def test_itglue_list_organizations_loops_pages():
    """When the first page is full (250 entries) the client must request a
    second page — without this loop, MSPs with >250 customers silently see
    only the first 250."""
    from app.integrations.itglue import ITGlueClient

    client = ITGlueClient(api_key="dummy", region="eu")
    try:
        # First call returns 250 (full page) — must trigger a second call.
        # Second call returns 50 (partial) — terminates the loop.
        page_1 = {"data": [{"id": str(i)} for i in range(250)]}
        page_2 = {"data": [{"id": str(i)} for i in range(250, 300)]}
        client._get = AsyncMock(side_effect=[page_1, page_2])  # type: ignore[assignment]

        orgs = await client.list_organizations()
    finally:
        await client.close()

    assert len(orgs) == 300
    assert client._get.await_count == 2
    # Second call must specify page[number]=2
    second_args = client._get.await_args_list[1]
    assert second_args.args[1]["page[number]"] == 2


# ── Service-level DNS checker: error vs. missing ──────────────────────────────


def test_service_dns_checker_propagates_unexpected_resolution_errors():
    """dns_checker._resolve used to swallow non-timeout exceptions and
    return []. That made check_spf misclassify a real network failure as
    'No SPF record found' — a false finding. The contract is now: only
    NXDOMAIN / NoAnswer / NoNameservers return []; everything else
    raises DnsResolutionError so check_* can render 'unverifiable'."""
    from app.services import dns_checker

    def _boom(*_a, **_kw):
        # A weird-but-real failure mode (dnspython raises this when it
        # fails to parse an answer it received).
        raise dns.exception.FormError("malformed packet")

    with patch.object(dns.resolver.Resolver, "resolve", side_effect=_boom):
        with pytest.raises(dns_checker.DnsResolutionError):
            dns_checker._resolve("example.com", "TXT")


def test_service_check_spf_renders_unverifiable_on_network_failure():
    """check_spf used to report 'fail / No SPF record found' on any DNS
    error — that's the SPF false-negative bug. It must now report
    'unverifiable' so the report shows we couldn't check rather than
    a fabricated finding."""
    from app.services import dns_checker

    def _boom(*_a, **_kw):
        raise OSError("network unreachable")

    with patch.object(dns.resolver.Resolver, "resolve", side_effect=_boom):
        result = dns_checker.check_spf("example.com")

    assert result["status"] == "unverifiable"
    assert result["record"] is None


def test_dnstimeout_still_caught_by_old_callsites():
    """DnsTimeout is now a subclass of DnsResolutionError. Anything that
    used to `except DnsTimeout` must still catch a real timeout. Without
    this, the LifetimeTimeout branch added in v10.10.2 wouldn't route
    through the existing unverifiable handlers."""
    from app.services.dns_checker import DnsResolutionError, DnsTimeout

    # The exception hierarchy itself is what callers depend on.
    assert issubclass(DnsTimeout, DnsResolutionError)


# ── Sign-ins: missing errorCode counts as unknown, not success ────────────────


@pytest.mark.asyncio
async def test_signin_missing_status_errorcode_not_counted_as_success():
    """A sign-in event whose `status.errorCode` is missing must end up in
    the 'unknown' bucket, not 'success'. The old code defaulted to 0 →
    counted as success → under-reported failures."""
    from pathlib import Path
    from app.modules.m365_audit.sections.signins import SignInsSection

    # The collector reads self.graph.get_all; stub it to return events
    # that span every status shape we expect to see in Graph.
    events = [
        {"userPrincipalName": "ok@example.com", "status": {"errorCode": 0}},
        {"userPrincipalName": "ok@example.com", "status": {"errorCode": 0}},
        {"userPrincipalName": "bad@example.com", "status": {"errorCode": 50126}},
        {"userPrincipalName": "ghost@example.com", "status": {}},   # missing field
        {"userPrincipalName": "ghost@example.com", "status": None}, # null whole obj
        {"userPrincipalName": "ghost@example.com"},                 # no status key
    ]

    class _Graph:
        async def get_all(self, *_a, **_kw):
            return events

    section = SignInsSection(out_dir=Path("/tmp"), graph=_Graph())  # type: ignore[arg-type]
    section._save = lambda *_a, **_kw: None  # type: ignore[assignment]

    await section.collect()

    # Three of the six events lacked a usable errorCode; they must be
    # counted as unknown, not as success.
    warns = " ".join(section.result.warns)
    assert "3 sign-in event(s) had no status.errorCode" in warns


# ── MFA methods: throttled lookup is not "no MFA" ─────────────────────────────


@pytest.mark.asyncio
async def test_mfa_methods_lookup_failure_is_not_reported_as_no_mfa():
    """A failed per-user methods lookup must be 'unknown', not 'no MFA'.

    The Graph client raises rather than returning empty precisely so callers
    cannot mistake "throttled out" for "no data" — but catching that in the
    collector and returning [] undid it at the call site. A throttled run then
    reported healthy users as having no MFA, and mfa_coverage_pct reaches the
    customer-facing report and the IT Glue asset, so the dip was visible.
    """
    from pathlib import Path

    from app.modules.m365_audit.sections.users_mfa import MFASection

    users = [
        {"id": "u1", "displayName": "Has MFA", "userPrincipalName": "a@example.com",
         "accountEnabled": True, "userType": "Member"},
        {"id": "u2", "displayName": "No MFA", "userPrincipalName": "b@example.com",
         "accountEnabled": True, "userType": "Member"},
        {"id": "u3", "displayName": "Throttled", "userPrincipalName": "c@example.com",
         "accountEnabled": True, "userType": "Member"},
    ]

    class _Graph:
        async def get(self, path, **_kw):
            if path.startswith("users/u1/"):
                return {"value": [{"@odata.type": "#microsoft.graph.fido2AuthenticationMethod"}]}
            if path.startswith("users/u2/"):
                return {"value": []}
            raise httpx.HTTPError("429 throttled")

    saved: dict[str, str] = {}
    section = MFASection(  # type: ignore[arg-type]
        out_dir=Path("/tmp"), graph=_Graph(), users=users,
    )
    section._save = lambda name, body: saved.__setitem__(name, body)  # type: ignore[assignment]

    await section.collect()

    warns = " ".join(section.result.warns)
    # Exactly one user genuinely lacks MFA — the throttled one is not counted.
    assert "1 enabled member user(s) have no MFA methods registered" in warns
    # And the unknown is surfaced rather than hidden.
    assert "could not be determined for 1 user(s)" in warns

    report = saved.get("04_mfa_methods.txt", "")
    assert "(lookup failed)" in report
    assert "NOT counted as lacking MFA" in report
