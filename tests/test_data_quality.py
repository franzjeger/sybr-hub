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


def test_failed_lookups_are_not_reported_as_clean_passes():
    """A lookup that never answered must not read as OK in a customer report.

    _severity() fell through to "ok" for statuses like "ERROR: timeout" or
    "SPF QUERY FAILED", so a transport failure was presented to the customer as
    a passing check. The fix existed on the port branch and was lost when that
    branch was superseded rather than merged.
    """
    from app.reports.generator import _severity

    for status in ("ERROR: connection refused", "ERROR", "SPF QUERY FAILED",
                   "DMARC query failed"):
        assert _severity(status) == "warning", f"{status!r} scored as {_severity(status)}"

    # Unchanged for everything else.
    assert _severity("MISSING") == "critical"
    assert _severity("WEAK cipher") == "warning"
    assert _severity("ENABLED") == "ok"


async def test_get_all_retries_without_top_when_the_endpoint_rejects_it():
    """Several Graph collections answer 400 to $top instead of ignoring it.

    /directoryRoles, /settings, accessReviews/definitions and
    authenticationStrength/policies all did, and each took its whole audit
    section down — five dead sections in one run before one was traced back to
    the query string. The retry belongs here because the section cannot see the
    cause; it only sees an exception.
    """
    import httpx

    from app.modules.m365_audit.graph_client import GraphClient

    calls: list[dict | None] = []

    class FakeResponse:
        status_code = 400
        text = "Bad Request"

        def json(self):
            return {}

    client = GraphClient.__new__(GraphClient)

    async def fake_get(url, params=None, extra_headers=None):
        calls.append(params)
        if params and "$top" in params:
            raise httpx.HTTPStatusError(
                "400", request=httpx.Request("GET", url), response=httpx.Response(400)
            )
        return {"value": [{"id": "1"}]}

    client._get = fake_get

    items = await client.get_all("directoryRoles", params={"$top": "999"})

    assert items == [{"id": "1"}]
    assert calls[0] == {"$top": "999"}, "first attempt should carry $top"
    assert calls[1] is None, "retry should drop $top entirely"


def test_a_failed_section_is_not_parsed_as_data():
    """A collector's error must not become a finding.

    Real case: /beta/.../sensitivityLabels answered 404, the section wrote the
    two-line error into its file, and the label parser split those lines on
    whitespace and counted them as two published labels — so the CIS control
    "Ensure sensitivity labels are published" passed, citing "2 sensitivity
    labels published", on a tenant where the query had failed outright.
    """
    from app.reports.generator import _is_error_payload

    four_oh_four = (
        "Error: Client error '404 Not Found' for url "
        "'https://graph.microsoft.com/beta/security/informationProtection/"
        "sensitivityLabels?%24top=999'\n"
        "For more information check: "
        "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404\n"
    )
    assert _is_error_payload(four_oh_four)
    assert _is_error_payload("Exchange Online data collection failed:\nEXO helper exited 1")
    assert _is_error_payload(
        "Error fetching authentication strength policies: Client error '400 Bad Request'"
    )

    # Data that merely mentions errors must survive — these open with a header
    # rule and describe failed sign-ins, which is the finding, not a failure.
    signin_failures = (
        "=" * 70 + "\n  SIGN-IN FAILURES\n" + "=" * 70 + "\n"
        "  user@example.com  52 failures (error code != 0)\n"
    )
    assert not _is_error_payload(signin_failures)
    assert not _is_error_payload("")


def test_progress_cb_never_lands_in_another_sections_parameter():
    """A misplaced positional argument corrupted a section silently.

    The collector passed progress_cb third to IdentitySecuritySection, whose
    third parameter is global_admin_ids. A function is truthy, so the "no admin
    ids — skip" guard passed it through to `for uid in <function>`, and the
    break-glass check raised on every audit that has ever run. Nothing failed
    loudly: the section caught it as a warning and carried on, and the report
    said "cannot be verified — data unavailable", which reads like a tenant
    condition rather than a bug.

    Most sections take progress_cb third and are fine positionally; the
    invariant is that it must not land in a parameter that is not progress_cb.
    """
    import ast
    import pathlib

    root = pathlib.Path("app/modules")
    signatures: dict[str, list[str]] = {}
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ClassDef):
                continue
            for body in node.body:
                if isinstance(body, ast.FunctionDef) and body.name == "__init__":
                    signatures[node.name] = [
                        a.arg for a in body.args.args if a.arg != "self"
                    ]

    collector = pathlib.Path("app/modules/m365_audit/collector.py")
    offenders = []
    for node in ast.walk(ast.parse(collector.read_text())):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        params = signatures.get(node.func.id)
        if not params:
            continue
        for index, arg in enumerate(node.args):
            if "progress_cb" not in ast.unparse(arg):
                continue
            if index < len(params) and params[index] != "progress_cb":
                offenders.append(
                    f"{node.func.id} line {node.lineno}: progress_cb lands in "
                    f"'{params[index]}'"
                )

    assert not offenders, "; ".join(offenders)


async def test_exo_helper_gets_a_decrypted_certificate(tmp_path, monkeypatch):
    """PowerShell cannot read our encryption-at-rest wrapper.

    The .pfx is stored with the MSPTK header and AES-GCM body, and the helper
    was handed that path. X509Certificate2 got ciphertext and failed with
    "ASN1 corrupted data", so Exchange collection produced nothing from the day
    encryption-at-rest landed. Whatever path we pass must contain a real PKCS#12
    blob, and it must not survive the call.
    """
    import json

    from app.core.encryption import encrypt_bytes
    from app.modules.m365_audit import auth as auth_mod

    pfx_plain = b"\x30\x82fake-pkcs12-body"
    cert_file = tmp_path / "audit_cert.pfx"
    cert_file.write_bytes(encrypt_bytes(pfx_plain))
    assert cert_file.read_bytes().startswith(b"MSPTK"), "fixture must be encrypted"

    seen: dict = {}

    class FakeProc:
        returncode = 0

        async def communicate(self, input=None):
            payload = json.loads(input.decode())
            path = payload["CertPath"]
            seen["path"] = path
            seen["bytes"] = open(path, "rb").read()
            return (b'{"ok": true}', b"")

    async def fake_exec(*a, **k):
        return FakeProc()

    monkeypatch.setattr(auth_mod.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(auth_mod, "find_pwsh", lambda: "/usr/bin/pwsh")

    mgr = auth_mod.AuthManager.__new__(auth_mod.AuthManager)
    mgr.cert_path = cert_file
    mgr.cert_password = "pw"
    mgr.tenant_id = "t"
    mgr.client_id = "c"
    mgr.org_domain = "example.com"

    helper = (
        auth_mod.Path(auth_mod.__file__).parent.parent.parent / "helpers" / "exo_collector.ps1"
    )
    if not helper.exists():
        import pytest

        pytest.skip("EXO helper script not present")

    await mgr.collect_exo_data(tmp_path)

    assert seen["bytes"] == pfx_plain, "helper was handed ciphertext, not a certificate"
    assert not auth_mod.Path(seen["path"]).exists(), "plaintext certificate outlived the call"


def test_build_report_context_survives_a_failed_section(tmp_path):
    """End-to-end guard: the report must build when a section file holds an error.

    The error-payload filter shipped with a NameError on its own log line —
    the module had no logger — so every report generation raised, and the only
    coverage was a unit test of the predicate. Nothing exercised the function
    that reads the files. This does.
    """
    from app.reports.generator import build_report_context

    (tmp_path / "19c_purview_sensitivity_labels.txt").write_text(
        "Error: Client error '404 Not Found' for url '.../sensitivityLabels'\n"
        "For more information check: https://developer.mozilla.org/\n",
        encoding="utf-8",
    )
    (tmp_path / "03_users_count.txt").write_text(
        "=" * 40 + "\n  USER COUNTS\n" + "=" * 40 + "\n  Total: 10\n", encoding="utf-8"
    )

    context = build_report_context("Test AS", "test.example", tmp_path, [])

    assert isinstance(context, dict)
    # The failed section contributed nothing rather than two invented labels.
    assert context.get("purview", {}).get("sensitivity_label_count", 0) == 0


def test_a_failed_section_file_reaches_the_templates(tmp_path):
    """Blanking a failed section must not also erase the reason it was blanked.

    The context builder already knew which files held an error — it collected
    their names to decide what to blank — and then dropped the list on the
    floor when it returned. So a tenant whose Purview endpoint answered 404
    read "0 failed sections" (that count comes from section *results*, not
    from these files), saw CIS 3.2.1 as "cannot be verified", and had nothing
    anywhere connecting the two. The reason survived only as a section warning.

    The list must arrive under its own key: ``failed_sections`` is a count of
    sections whose collector reported failure, which is a different quantity
    from the files that hold an error, and the two disagree on exactly the
    tenants this matters for.
    """
    from app.reports.generator import build_report_context

    (tmp_path / "19c_purview_sensitivity_labels.txt").write_text(
        "Error: Client error '404 Not Found' for url '.../sensitivityLabels'\n"
        "For more information check: https://developer.mozilla.org/\n",
        encoding="utf-8",
    )
    (tmp_path / "03_users_count.txt").write_text(
        "=" * 40 + "\n  USER COUNTS\n" + "=" * 40 + "\n  Total: 10\n", encoding="utf-8"
    )

    context = build_report_context("Test AS", "test.example", tmp_path, [])

    error_files = context.get("error_files")
    assert error_files, "the names of the files that held an error must reach the templates"

    names = [e["name"] for e in error_files]
    assert "19c_purview_sensitivity_labels.txt" in names
    assert "03_users_count.txt" not in names, "a file that held data is not a failure"

    # Traceable in the direction a reader needs: this file is why 3.2.1 says
    # it cannot be verified. The evidence links cannot carry this — they
    # deliberately drop files whose contents were blanked.
    entry = next(e for e in error_files if e["name"] == "19c_purview_sensitivity_labels.txt")
    assert "3.2.1" in entry["controls"]

    # The existing key keeps its meaning: a count, computed from results.
    assert context["failed_sections"] == 0


def test_named_error_files_only_cite_controls_the_report_shows(tmp_path):
    """Every control named beside a failed file must exist in the CIS table.

    The control ids come from ``_EVIDENCE_MAP``, which is keyed by CIS id and
    maintained by hand. Naming an id the table does not list sends the reader
    looking for a row that is not there.
    """
    from app.reports.generator import build_report_context

    for name in ("19c_purview_sensitivity_labels.txt", "23_exchange_antiphish.txt",
                 "08_conditional_access.txt"):
        (tmp_path / name).write_text("Error: Client error '403 Forbidden'\n", encoding="utf-8")

    context = build_report_context("Test AS", "test.example", tmp_path, [])

    shown = {c["cis_id"] for c in context["compliance"]}
    cited = {cid for e in context["error_files"] for cid in e["controls"]}
    assert cited, "these files back CIS controls; the mapping must resolve"
    assert cited <= shown, f"cites controls absent from the table: {sorted(cited - shown)}"


def test_exo_timeout_exceeds_a_measured_real_connection():
    """Connect-ExchangeOnline is slow; the budget must not cut it short.

    Measured 346 seconds against a live tenant on a run that succeeded and
    returned data. The 300-second budget killed it at the last moment, and the
    audit reported "EXO helper timed out" — indistinguishable, to a reader,
    from Exchange being unreachable.
    """
    from app.modules.m365_audit.auth import _EXO_TIMEOUT_SECONDS

    assert _EXO_TIMEOUT_SECONDS >= 600, (
        "a real certificate connection took 346s; leave real headroom"
    )


def test_exo_helper_skips_absent_mailbox_types():
    """One missing recipient type must not discard the whole inventory.

    Get-Mailbox returns $null when a tenant has no room or equipment
    mailboxes, and "+= $null" appends a null element. That reached
    Get-MailboxStatistics, threw, and the catch dropped every mailbox already
    collected — the section reported a bind error instead of the mailboxes it
    had.
    """
    import pathlib

    helper = pathlib.Path("app/helpers/exo_collector.ps1").read_text(encoding="utf-8")
    assert "if ($found) { $mbx += $found }" in helper, "null results must not be appended"
    assert "Where-Object { $_ -and $_.Identity }" in helper, "null rows must be filtered"


async def test_break_glass_check_receives_the_global_admins():
    """The check ran but had nothing to check.

    AdminRolesSection counted Global Administrators and discarded their ids, so
    IdentitySecuritySection was constructed without them and wrote "No Global
    Admin IDs provided — skipping check" on every audit. The report then said
    "cannot be verified — data unavailable", which reads as a tenant condition
    rather than nothing having been wired up.
    """
    import tempfile
    from pathlib import Path

    from app.modules.m365_audit.sections.groups_roles import AdminRolesSection

    class FakeGraph:
        async def get_all(self, path, **kw):
            if path == "directoryRoles":
                return [{"id": "role-ga", "displayName": "Global Administrator"}]
            return [{"id": "admin-1", "userPrincipalName": "ga@example.com"},
                    {"id": "admin-2", "userPrincipalName": "ga2@example.com"}]
        async def get(self, *a, **k):
            return {}

    section = AdminRolesSection(Path(tempfile.mkdtemp()), FakeGraph())
    shared = section.global_admin_ids          # captured at construction time
    await section.collect()

    assert shared is section.global_admin_ids, "list was replaced, breaking the shared reference"
    assert section.global_admin_ids == ["admin-1", "admin-2"]


def test_break_glass_does_not_claim_ca_status_it_never_collected():
    """An empty exclusion set means unknown, not "not excluded"."""
    import inspect

    from app.modules.m365_audit.sections import identity_security

    src = inspect.getsource(identity_security)
    assert 'ca_str      = ("Yes" if ca_excluded else "No") if ca_known else "Unknown"' in src


# ── Report must not invent findings from empty sections ──────────────────────


def test_branch_one_banner_declaring_zero_settles_it():
    """Gren 1: a zero banner ends the question; rows are never counted.

    Taken from a real run: the Purview endpoint returned nothing and the
    section wrote a "(none)" placeholder under a "(0 entries)" banner. Counting
    that placeholder as a row passed the CIS control for having DLP policies,
    citing one policy, on a tenant that has none.
    """
    from app.reports.generator import _count_data_lines

    dlp = (
        "=" * 80 + "\n  PURVIEW DLP POLICIES  (0 entries)\n" + "=" * 80 + "\n  (none)\n"
    )
    assert _count_data_lines(dlp) == 0

    intune = (
        "=" * 80 + "\n  INTUNE COMPLIANCE POLICIES  (0 total)\n" + "=" * 80 + "\n"
        "  Policy Name                Platform             Created\n"
        "  " + "-" * 60 + "\n" + "=" * 80 + "\n"
    )
    assert _count_data_lines(intune) == 0

    alerts = (
        "=" * 80 + "\n  DEFENDER ACTIVE ALERTS  (0 unresolved)\n" + "=" * 80 + "\n"
        "  Alert Title          Severity     Status          Created\n"
        "  " + "-" * 60 + "\n" + "=" * 80 + "\n"
    )
    assert _count_data_lines(alerts) == 0


def test_branch_two_multiline_records_trust_the_banner():
    """Gren 2: one record spanning many lines must not read as many records.

    Verbatim shape of 21_exchange_transport_rules.txt from the same run: a
    single rule whose free-text Description wraps over four lines. Row counting
    makes that nine.
    """
    from app.reports.generator import _count_data_lines, _is_multiline_record_format

    rules = (
        "=" * 80 + "\n  EXCHANGE TRANSPORT RULES  (1 entries)\n" + "=" * 80 + "\n\n"
        "  [1]\n"
        "    Name: Scanner spam-bypass\n"
        "    State: Disabled\n"
        "    Priority: 0\n"
        "    Description: If the message:\n"
        "\tsender's address domain portion belongs to any of these domains: 'x.no'\n"
        "Take the following actions:\n"
        "\tSet the spam confidence level (SCL) to '-1'\n"
        "Activation date: 3/11/2025 12:30:00 PM\n\n\n" + "=" * 80 + "\n"
    )
    assert _is_multiline_record_format(rules)
    assert _count_data_lines(rules) == 1


def test_branch_three_tabular_rows_win_over_the_banner():
    """Gren 3: one record per line — count the rows, banner is a sanity check.

    A bannerless table must skip its own furniture: a real 03_users.txt with
    216 users read as 217 because the "USER INVENTORY" title counted as a user.
    Where a banner disagrees with the rows the smaller honest number is used.
    """
    from app.reports.generator import _count_data_lines

    users = (
        "=" * 80 + "\n  USER INVENTORY\n" + "=" * 80 + "\n"
        "  Display Name        UPN                 Enabled\n"
        "  " + "-" * 60 + "\n"
        "  Ann Berg            ann@example.com         Yes\n"
        "  Bo Dahl             bo@example.com          Yes\n"
    )
    assert _count_data_lines(users) == 2

    truncated = (
        "=" * 80 + "\n  SECURITY ALERTS  (12 found)\n" + "=" * 80 + "\n"
        "  Suspicious sign-in\n" + "=" * 80 + "\n"
    )
    assert _count_data_lines(truncated) == 1


def test_branch_one_wins_over_rows_when_the_banner_says_zero():
    """Gren 1 has priority: a zero banner is not overruled by stray rows.

    Contradictory output — the banner declares nothing was found, yet a row is
    present. The rule is that zero settles it, so this returns 0 rather than
    reporting a record the collector says it did not find.
    """
    from app.reports.generator import _count_data_lines

    contradictory = (
        "=" * 80 + "\n  DEFENDER ACTIVE ALERTS  (0 unresolved)\n" + "=" * 80 + "\n"
        "  leftover row from a previous write\n" + "=" * 80 + "\n"
    )
    assert _count_data_lines(contradictory) == 0


def test_capabilities_require_an_assigned_seat():
    """An owned but unassigned licence grants nobody anything.

    The tenant this came from holds one AAD_PREMIUM_P2 with zero seats used.
    Treating that as "has P2" would score PIM as a config failure the customer
    cannot fix without first assigning the licence.
    """
    from app.reports.generator import _licensed_capabilities

    assert _licensed_capabilities([{"part": "AAD_PREMIUM_P2", "used": 0, "total": 1}]) == set()
    assert "entra_p2" in _licensed_capabilities(
        [{"part": "AAD_PREMIUM_P2", "used": 3, "total": 5}]
    )

    # O365_BUSINESS_PREMIUM is Business *Standard* and carries none of these.
    standard = _licensed_capabilities([{"part": "O365_BUSINESS_PREMIUM", "used": 42, "total": 42}])
    assert standard == set()

    # SPB is the real Business Premium.
    assert "intune" in _licensed_capabilities([{"part": "SPB", "used": 1, "total": 5}])


def test_sharepoint_counts_sites_not_furniture():
    """The site total counted the banner, the column header and the rule.

    A tenant with 105 sites was reported as having 108. The local loop skipped
    only "===" lines, so every other piece of table furniture became a site.
    """
    from app.reports.generator import _parse_sharepoint_settings

    sites = (
        "=" * 110 + "\n  SHAREPOINT SITES  (105 total)\n" + "=" * 110 + "\n"
        "  Site Name          Web URL                                    Created\n"
        "  " + "-" * 100 + "\n"
        "  Basene             https://x.sharepoint.com/sites/basar       2024-11-20\n"
        "  Teknisk            https://x.sharepoint.com/sites/teknisk     2024-11-21\n"
    )
    result = _parse_sharepoint_settings("", sites)
    assert result["site_count"] == 2


def test_a_site_named_personal_is_not_a_onedrive():
    """Classification is by host, not by the word appearing on the line.

    This tenant has an ordinary team site called "Personal FF HF" at
    /sites/pers. Substring-matching "personal" across the whole line filed it
    as a personal site, so the report claimed one OneDrive where there are
    none.
    """
    from app.reports.generator import _parse_sharepoint_settings

    sites = (
        "=" * 110 + "\n  SHAREPOINT SITES  (2 total)\n" + "=" * 110 + "\n"
        "  Site Name          Web URL                                    Created\n"
        "  " + "-" * 100 + "\n"
        "  Personal FF HF     https://x.sharepoint.com/sites/pers        2024-11-20\n"
        "  Anna Berg          https://x-my.sharepoint.com/personal/anna  2024-11-21\n"
    )
    result = _parse_sharepoint_settings("", sites)
    assert result["personal_sites"] == 1, "only the -my.sharepoint.com host counts"


def test_role_scoped_ca_policy_is_not_reported_as_targeting_nobody():
    """Reading only includeUsers made an admin policy look empty.

    "Require multifactor authentication for admins" is scoped by directory
    role: includeUsers is empty and includeRoles carries the admin templates.
    The summary rendered "0 user(s)", which reads as a policy protecting
    nobody — the most alarming thing a reader could be told about the one
    policy covering every administrator, and false.
    """
    from app.modules.m365_audit.sections.conditional_access import _summarise_conditions

    admin_policy = {
        "users": {"includeUsers": [], "includeRoles": ["tmpl-ga", "tmpl-ea", "tmpl-sa"]},
        "applications": {"includeApplications": ["All"]},
    }
    scope, _ = _summarise_conditions(admin_policy)
    assert scope == "3 role(s)"
    assert "0 user" not in scope


def test_a_ca_policy_scoped_to_nothing_still_says_so():
    """The real empty case must remain visible, and now means what it says."""
    from app.modules.m365_audit.sections.conditional_access import _summarise_conditions

    empty = {"users": {"includeUsers": []}, "applications": {"includeApplications": ["All"]}}
    assert _summarise_conditions(empty)[0] == "none"

    guests = {
        "users": {"includeUsers": [], "includeGuestsOrExternalUsers": {"guestOrExternalUserTypes": "b2b"}},
        "applications": {"includeApplications": ["All"]},
    }
    assert _summarise_conditions(guests)[0] == "guests/external"


async def test_ca_policy_records_its_template_and_creation_date():
    """Provenance is recorded, not inferred.

    A technician reads "Microsoft enabled this automatically" very differently
    from "the customer configured this", and the report could not tell them
    apart. No property states it: conditionalAccessPolicy in v1.0 has no
    createdBy, and the "Microsoft-managed:" prefix visible in the audit log is
    not part of displayName.

    templateId turned out to carry the signal, confirmed against a live tenant:
    four policies matching Microsoft's published managed-policy names each had
    one, three created the same day in a bulk rollout, while the customer's own
    policy had none. The wording stays at "from template" rather than
    "Microsoft-managed" because an administrator can also create a policy from
    a template by hand, and the data cannot separate those two.
    """
    import pathlib
    import tempfile

    from app.core.encryption import encrypted_read_text
    from app.modules.m365_audit.sections.conditional_access import ConditionalAccessSection

    class FakeGraph:
        async def get_all(self, path, **kwargs):
            if "namedLocations" in path:
                return []
            return [
                {
                    "displayName": "Require multifactor authentication for admins",
                    "state": "enabled",
                    "templateId": "tmpl-abc",
                    "createdDateTime": "2025-03-11T12:30:00Z",
                    "conditions": {
                        "users": {"includeUsers": [], "includeRoles": ["r1", "r2"]},
                        "applications": {"includeApplications": ["All"]},
                    },
                    "grantControls": {"builtInControls": ["mfa"]},
                },
                {
                    "displayName": "Egendefinert policy",
                    "state": "enabled",
                    "templateId": None,
                    "createdDateTime": "2024-01-05T09:00:00Z",
                    "conditions": {
                        "users": {"includeUsers": ["All"]},
                        "applications": {"includeApplications": ["All"]},
                    },
                    "grantControls": {"builtInControls": ["mfa"]},
                },
            ]

        async def get(self, *args, **kwargs):
            return {}

    out_dir = pathlib.Path(tempfile.mkdtemp())
    await ConditionalAccessSection(out_dir, FakeGraph()).collect()
    written = encrypted_read_text(out_dir / "08_conditional_access.txt")

    assert "origin: from template (tmpl-abc)" in written
    assert "created: 2025-03-11" in written
    assert "origin: custom" in written, "a policy without a template must say so"
    # And the two must not be confusable: the custom one carries no template id.
    custom_line = next(ln for ln in written.splitlines() if "origin: custom" in ln)
    assert "tmpl-abc" not in custom_line
    # The scope fix must survive alongside it.
    assert "2 role(s)" in written


async def test_sensitivity_labels_survive_a_failed_exo_helper():
    """19c comes from Graph, so a dead PowerShell helper must not erase it.

    The Purview trio (19c/19d/19e) is owned by ExchangeSection, and that
    section returns early when the EXO helper reports an error. Labels are the
    one member of the trio Graph supplies, so collecting them below that guard
    would mean every failed EXO connection produced no labels file at all. That
    is not a rare path: the helper needs a working PowerShell and certificate.
    The compliance control reads an absent file as "not checked" only because
    the file is absent for the right reason, and "Graph was never asked" is the
    wrong one.
    """
    import pathlib
    import tempfile

    from app.core.encryption import encrypted_read_text
    from app.modules.base import SectionStatus
    from app.modules.m365_audit.sections.exchange import ExchangeSection

    asked = []

    class FakeGraph:
        async def get_all(self, path, **kwargs):
            asked.append(path)
            return [{"name": "Konfidensiell", "priority": 1, "isActive": True}]

    out_dir = pathlib.Path(tempfile.mkdtemp())
    result = await ExchangeSection(
        out_dir,
        {"error": "Connect-ExchangeOnline failed"},
        [],
        graph=FakeGraph(),
    ).collect()

    assert any("sensitivityLabels" in p for p in asked), "Graph was never asked"
    written = encrypted_read_text(out_dir / "19c_purview_sensitivity_labels.txt")
    assert "Konfidensiell" in written
    assert "1 total" in written

    # The EXO half must still report its own failure honestly.
    assert result.status is SectionStatus.SKIPPED
    assert (out_dir / "EXCHANGE_ERROR.txt").exists()


async def test_identity_security_no_longer_writes_the_purview_file():
    """One owner for 19c, so the duplicate collector cannot come back.

    IdentitySecuritySection carried a byte-identical copy of the labels
    collector for as long as the dead PurviewSection did. Both wrote the same
    filename, so whichever ran last won and neither was obviously redundant.
    """
    import pathlib
    import tempfile

    from app.modules.m365_audit.sections.identity_security import IdentitySecuritySection

    class FakeGraph:
        async def get_all(self, path, **kwargs):
            assert "sensitivityLabels" not in path, "labels moved to ExchangeSection"
            return []

        async def get(self, *args, **kwargs):
            return {}

    out_dir = pathlib.Path(tempfile.mkdtemp())
    await IdentitySecuritySection(out_dir, FakeGraph()).collect()

    assert not (out_dir / "19c_purview_sensitivity_labels.txt").exists()


# ── Warning severity travels with the warning ────────────────────────────────


def test_warn_records_a_level_for_every_message():
    """warns and warn_levels are parallel lists; nothing else appends to either.

    Kept alongside rather than folded into one list because warns is consumed
    as plain strings by the scheduler, the SSE payload and three places in the
    UI. The invariant is only safe while _warn is the sole writer.
    """
    from app.modules.base import BaseSection, SectionResult

    class _S(BaseSection):
        name = "T"
        async def collect(self) -> SectionResult:
            return self.result

    import pathlib, tempfile
    s = _S(pathlib.Path(tempfile.mkdtemp()))
    s._warn("ordinary")
    s._warn("an active exposure", level="critical")
    s._warn("nonsense level", level="banana")

    assert s.result.warns == ["ordinary", "an active exposure", "nonsense level"]
    assert s.result.warn_levels == ["warn", "critical", "warn"], (
        "an unknown level falls back rather than reaching the UI"
    )
    assert len(s.result.warns) == len(s.result.warn_levels)


@pytest.mark.asyncio
async def test_external_forwarding_is_marked_critical():
    """The severity belongs to the collector that found it, not to a pattern
    match over the message downstream."""
    import pathlib, tempfile

    from app.modules.m365_audit.sections.exchange import ExchangeSection

    class _G:
        async def get_all(self, *a, **k): return []
        async def get(self, *a, **k): return {}

    section = ExchangeSection(
        pathlib.Path(tempfile.mkdtemp()),
        {"forwarding": [{"DisplayName": "Anna", "ForwardingSmtp": "anna@gmail.com"}]},
        ["example.no"], graph=_G(),
    )
    section._save_forwarding()

    assert section.result.warns, "the finding should be recorded"
    assert "critical" in section.result.warn_levels
