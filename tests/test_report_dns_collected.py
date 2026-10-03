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

    assert _verdicts(records) == {
        ("5.2.1", "acme.example"): "pass",
        ("5.2.2", "acme.example"): "pass",
        ("5.2.3", "acme.example"): "pass",
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
