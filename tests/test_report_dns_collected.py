"""SPF, DMARC, DKIM and MTA-STS, from the files the DNS collector actually writes.

The collector resolves through Google's DNS-over-HTTPS in dns._doh_query. These
tests answer that one call from a dict, so the real _check_domain classifies
every record and the real section writes 26_email_dns_spf_dmarc.txt and its
sidecar; the report then reads the run back as build_report_context does
(tests/collector_rig.py).
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections import dns as dns_mod
from app.reports.compliance import _build_compliance_map
from app.reports.generator import build_report_context
from app.reports.parsers.email import _parse_spf_dmarc, _spf_dmarc_records
from tests.collector_rig import run_sections

M365_CNAME = "selector1-acme-example._domainkey.acme.onmicrosoft.example."

# (name, type) -> records, or an exception. Anything not listed has no record.
ANSWERS = {
    # acme.example: everything in place.
    ("acme.example", "TXT"): ["v=spf1 include:spf.protection.outlook.com -all"],
    ("_dmarc.acme.example", "TXT"): ["v=DMARC1; p=reject; rua=mailto:dmarc@acme.example"],
    ("selector1._domainkey.acme.example", "CNAME"): [M365_CNAME],
    ("selector2._domainkey.acme.example", "CNAME"): [M365_CNAME.replace("1", "2", 1)],
    ("_mta-sts.acme.example", "TXT"): ["v=STSv1; id=20261001T000000;"],
    # svak.example: soft SPF, monitor-only DMARC, a third-party key only.
    ("svak.example", "TXT"): ["v=spf1 include:_spf.mail.example ~all"],
    ("_dmarc.svak.example", "TXT"): ["v=DMARC1; p=none; sp=reject"],
    ("google._domainkey.svak.example", "TXT"): ["v=DKIM1; k=rsa; p=MIIB"],
    # brutt.example: the SPF and M365 DKIM lookups fail, DMARC is absent.
    ("brutt.example", "TXT"): dns_mod.DnsLookupError("TXT brutt.example: DoH status 2 (ServFail)"),
    ("selector1._domainkey.brutt.example", "CNAME"): dns_mod.DnsLookupError("timeout"),
    ("selector1._domainkey.brutt.example", "TXT"): dns_mod.DnsLookupError("timeout"),
}
DOMAINS = ["acme.example", "svak.example", "brutt.example", "acme.onmicrosoft.com"]


async def _collect(tmp_path, monkeypatch, *, sidecars=True, answers=ANSWERS) -> dict:
    async def doh_query(_client, name, qtype):
        answer = answers.get((name, qtype), [])
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(dns_mod, "_doh_query", doh_query)
    return await run_sections(dns_mod.DnsSection(tmp_path, DOMAINS), sidecars=sidecars)


def _verdicts(records: list[dict]) -> dict[tuple[str, str], str]:
    rows = _build_compliance_map({"spf_dmarc": records, "file_contents": {}})
    return {
        (r["cis_id"], r["title"].rsplit("(", 1)[-1].rstrip(")")): r["status"]
        for r in rows
        if r["cis_id"] in ("5.2.1", "5.2.2", "5.2.3")
    }


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_every_domain_survives_the_round_trip(tmp_path, monkeypatch, sidecars):
    files = await _collect(tmp_path, monkeypatch, sidecars=sidecars)
    assert ("26_email_dns_spf_dmarc.json" in files) is sidecars

    records = _spf_dmarc_records(files)

    assert [r["domain"] for r in records] == ["acme.example", "svak.example", "brutt.example"]
    acme, svak, brutt = records
    assert acme["spf"] == "OK (-all hardfail)"
    assert acme["dmarc_record"].startswith("v=DMARC1; p=reject")
    assert acme["dkim1"] == f"selector1: CNAME -> {M365_CNAME} | selector2: " + (
        f"CNAME -> {M365_CNAME.replace('1', '2', 1)}"
    )
    assert acme["mta_sts"] == "v=STSv1; id=20261001T000000;"
    assert svak["dmarc"] == "WEAK (p=none)"
    assert svak["dkim2"].startswith("google: TXT present | k1: MISSING")
    assert svak["dkim_found"] == "google"
    assert brutt["spf"].startswith("ERROR (")
    assert "spf_record" not in brutt, "a failed lookup has no record, not an empty one"
    assert brutt["dmarc"] == "MISSING" and brutt["dmarc_record"] == ""
    assert brutt["dkim_found"] == "(none)"

    # DKIM is decided on Exchange's signing config, which only the Exchange
    # section collects (see the DKIM tests below). Without it, acme.example's
    # published M365 selectors say signing was set up, not that it is on:
    # cannot verify. svak.example has no M365 selector, so Exchange cannot
    # sign with it, and its Google key does not count, since its SPF record
    # does not say Google sends its mail: a failed control.
    assert _verdicts(records) == {
        ("5.2.1", "acme.example"): "pass",
        ("5.2.2", "acme.example"): "pass",
        ("5.2.3", "acme.example"): "info",
        ("5.2.1", "svak.example"): "fail",
        ("5.2.2", "svak.example"): "partial",
        ("5.2.3", "svak.example"): "fail",
        ("5.2.1", "brutt.example"): "info",
        ("5.2.2", "brutt.example"): "fail",
        ("5.2.3", "brutt.example"): "info",
    }


async def test_the_sidecar_and_the_text_give_the_same_records(tmp_path, monkeypatch):
    """Every key, in the same order, so no consumer of the list can tell them apart."""
    files = await _collect(tmp_path, monkeypatch)

    from_sidecar = _spf_dmarc_records(files)
    from_text = _parse_spf_dmarc(files["26_email_dns_spf_dmarc.txt"])

    assert [list(r.items()) for r in from_sidecar] == [list(r.items()) for r in from_text]


async def test_the_records_come_from_the_sidecar(tmp_path, monkeypatch):
    files = await _collect(tmp_path, monkeypatch)
    files["26_email_dns_spf_dmarc.txt"] = ""  # only the sidecar can answer now

    assert [r["domain"] for r in _spf_dmarc_records(files)] == [
        "acme.example",
        "svak.example",
        "brutt.example",
    ]


async def test_the_report_context_reads_the_sidecar(tmp_path, monkeypatch):
    """build_report_context hands the sidecar's records to the controls, risk and advice."""
    run = tmp_path / "Acme_AS" / "2026-10-03_0900"
    run.mkdir(parents=True)
    await _collect(run, monkeypatch)
    (run / "26_email_dns_spf_dmarc.txt").write_text("", encoding="utf-8")

    ctx = build_report_context("Acme AS", "acme.example", run, [], persist_metrics=False)

    assert [r["domain"] for r in ctx["spf_dmarc"]] == [
        "acme.example",
        "svak.example",
        "brutt.example",
    ]


async def test_a_section_that_fails_writes_no_sidecar(tmp_path, monkeypatch):
    async def check_domain(_client, _domain):
        raise RuntimeError("resolver unreachable")

    monkeypatch.setattr(dns_mod, "_check_domain", check_domain)
    files = await run_sections(dns_mod.DnsSection(tmp_path, DOMAINS))

    assert "26_email_dns_spf_dmarc.json" not in files
    assert _spf_dmarc_records(files) == []


# ── DKIM (CIS 5.2.3): Exchange's signing config and who sends the mail ───────
#
# The Exchange section writes 25_exchange_dkim.txt from Get-DkimSigningConfig,
# the DNS section 26 from the published records. 5.2.3 reads both: whether
# Exchange signs for a domain, and, for a domain whose SPF record says a third
# party sends its mail, whether that third party's key is published.

LONG_DOMAIN = "regnskap-og-lonn.datterselskap-nord.acme-holding.example"
assert len(LONG_DOMAIN) > 45

DKIM_ANSWERS = {
    # acme.example: Exchange sends, and signs.
    ("acme.example", "TXT"): ["v=spf1 include:spf.protection.outlook.com -all"],
    ("selector1._domainkey.acme.example", "CNAME"): [M365_CNAME],
    # av.example: Exchange sends, M365 selectors published, signing switched
    # off in Exchange; a Mailchimp k1 CNAME beside it.
    ("av.example", "TXT"): ["v=spf1 include:spf.protection.outlook.com -all"],
    ("selector1._domainkey.av.example", "CNAME"): [M365_CNAME],
    ("k1._domainkey.av.example", "CNAME"): ["dkim.mcsv.example."],
    # gmail.example: Google Workspace sends its mail, and its key is published.
    ("gmail.example", "TXT"): ["v=spf1 include:_spf.google.com -all"],
    ("google._domainkey.gmail.example", "TXT"): ["v=DKIM1; k=rsa; p=MIIB"],
    # svak.example: someone else sends; a Google key that Google does not use.
    ("svak.example", "TXT"): ["v=spf1 include:_spf.mail.example ~all"],
    ("google._domainkey.svak.example", "TXT"): ["v=DKIM1; k=rsa; p=MIIB"],
    # parkert.example: sends no mail at all.
    ("parkert.example", "TXT"): ["v=spf1 -all"],
    # A domain longer than the 25 table's 45-character column, which Exchange signs.
    (LONG_DOMAIN, "TXT"): ["v=spf1 include:spf.protection.outlook.com -all"],
}
DKIM_DOMAINS = [
    "acme.example",
    "av.example",
    "gmail.example",
    "svak.example",
    "parkert.example",
    LONG_DOMAIN,
]
DKIM_CONFIGS = [
    {"Domain": "acme.example", "Enabled": True, "Status": "Valid", "KeySize": 2048},
    {"Domain": "av.example", "Enabled": False, "Status": "Valid", "KeySize": 2048},
    {"Domain": LONG_DOMAIN, "Enabled": True, "Status": "Valid", "KeySize": 2048},
    {"Domain": "acme.onmicrosoft.com", "Enabled": True, "Status": "Valid", "KeySize": 2048},
]


async def _collect_dkim(run, monkeypatch, *, exo, sidecars=True) -> dict:
    """The DNS and Exchange sections into one run directory, read back."""
    from app.modules.m365_audit.sections.exchange import ExchangeSection
    from tests.collector_rig import FakeGraph

    async def doh_query(_client, name, qtype):
        return DKIM_ANSWERS.get((name, qtype), [])

    monkeypatch.setattr(dns_mod, "_doh_query", doh_query)
    labels = "beta/security/dataSecurityAndGovernance/sensitivityLabels"
    async with FakeGraph({labels: []}) as fake:
        return await run_sections(
            dns_mod.DnsSection(run, DKIM_DOMAINS),
            ExchangeSection(run, exo, DKIM_DOMAINS, graph=fake.client),
            sidecars=sidecars,
        )


def _dkim_rows(files: dict) -> dict[str, tuple[str, str]]:
    context = {"spf_dmarc": _spf_dmarc_records(files), "file_contents": files}
    return {
        r["title"].rsplit("(", 1)[-1].rstrip(")"): (r["status"], r["detail"])
        for r in _build_compliance_map(context)
        if r["cis_id"] == "5.2.3"
    }


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_dkim_is_decided_on_who_sends_each_domains_mail(tmp_path, monkeypatch, sidecars):
    files = await _collect_dkim(
        tmp_path, monkeypatch, exo={"dkim": DKIM_CONFIGS}, sidecars=sidecars
    )
    assert ("25_exchange_dkim.json" in files) is sidecars

    rows = _dkim_rows(files)
    statuses = {domain: status for domain, (status, _) in rows.items()}
    assert statuses == {
        "acme.example": "pass",
        # A Mailchimp CNAME used to pass an Exchange DKIM control.
        "av.example": "fail",
        # A Google key used to fail: the collector writes "TXT present", never "k=rsa".
        "gmail.example": "pass",
        "svak.example": "fail",
        "parkert.example": "pass",
        LONG_DOMAIN: "pass",
    }
    assert rows["av.example"][1].startswith(
        "DKIM-signering er ikke aktivert i Exchange Online for av.example"
    )
    assert "Mailchimp" in rows["av.example"][1]
    assert "Google Workspace" in rows["gmail.example"][1]
    assert "svak.example" in rows["svak.example"][1]


async def test_without_exchanges_signing_config_dkim_cannot_be_verified(tmp_path, monkeypatch):
    """Published M365 selectors do not say signing is on: that is a separate switch."""
    files = await _collect_dkim(
        tmp_path, monkeypatch, exo={"dkim_error": "Get-DkimSigningConfig failed."}
    )

    rows = _dkim_rows(files)
    assert rows["acme.example"] == (
        "info",
        "Kan ikke verifiseres: DKIM-signeringen i Exchange Online for acme.example ble ikke "
        "hentet, men M365-selektorene er publisert i DNS",
    )
    # Exchange's state does not matter where the data says someone else sends.
    assert rows["gmail.example"][0] == "pass"
    assert rows["parkert.example"][0] == "pass"


async def test_the_report_context_reads_dkim_from_the_sidecars(tmp_path, monkeypatch):
    run = tmp_path / "Acme_AS" / "2026-10-03_0900"
    run.mkdir(parents=True)
    await _collect_dkim(run, monkeypatch, exo={"dkim": DKIM_CONFIGS})
    for name in ("25_exchange_dkim.txt", "26_email_dns_spf_dmarc.txt"):
        (run / name).write_text("", encoding="utf-8")  # only the sidecars can answer now

    ctx = build_report_context("Acme AS", "acme.example", run, [], persist_metrics=False)

    statuses = {
        r["title"].rsplit("(", 1)[-1].rstrip(")"): r["status"]
        for r in ctx["compliance"]
        if r["cis_id"] == "5.2.3"
    }
    assert statuses["acme.example"] == "pass"
    assert statuses["av.example"] == "fail"


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_customer_reports_dkim_cell_says_what_the_control_says(
    tmp_path, monkeypatch, sidecars
):
    """The email table judged DKIM on its own: "Found" unless every summary said MISSING.

    av.example has its M365 selectors published and signing switched off in
    Exchange: CIS 5.2.3 fails, and the table beside it printed "Found".
    """
    import re

    from app.reports.generator import _jinja_env
    from app.reports.i18n import T

    run = tmp_path / "Acme_AS" / "2026-10-03_0900"
    run.mkdir(parents=True)
    await _collect_dkim(run, monkeypatch, exo={"dkim": DKIM_CONFIGS}, sidecars=sidecars)
    if not sidecars:
        for path in run.glob("*.json"):
            path.unlink()
    ctx = build_report_context("Acme AS", "acme.example", run, [], lang="en", persist_metrics=False)
    ctx.update(t=T("en"), lang="en", theme="light")
    html = _jinja_env().get_template("report_customer.html.j2").render(**ctx)

    def dkim_cell(domain: str) -> str:
        row = re.search(
            rf'<td style="font-weight:600;">{re.escape(domain)}</td>(.*?)</tr>', html, re.DOTALL
        )
        assert row, domain
        return re.findall(r'<span class="status-pill [a-z]+">([^<]*)</span>', row.group(1))[2]

    assert dkim_cell("acme.example") == "OK"
    assert dkim_cell("av.example") == "Missing"
    assert dkim_cell("gmail.example") == "OK"
