"""SPF that redirects and DMARC that is inherited are not missing.

* "v=spf1 redirect=_spf.example.com" carries no "all" of its own; the policy is
  the target's. It was classified "PRESENT (no 'all' mechanism)", which fails
  the CIS control for a domain whose SPF is as strict as the record it points to.
* DMARC was looked up at _dmarc.<domain> only. A verified subdomain without its
  own record takes the parent's policy (its sp= tag when there is one), but it
  was reported MISSING: a CIS failure and eight points off the score.

The real _check_domain runs here; only the DNS-over-HTTPS query is answered
from a table.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.modules.m365_audit.sections import dns as dns_section


async def _check(domain: str, zone: dict[tuple[str, str], list[str]]) -> tuple[dict, list[str]]:
    asked: list[str] = []

    async def _query(client, name, qtype):
        asked.append(name)
        return zone.get((name, qtype), [])

    with patch.object(dns_section, "_doh_query", side_effect=_query):
        result = await dns_section._check_domain(httpx.AsyncClient(), domain)
    return result, asked


async def test_spf_redirect_is_judged_by_its_target():
    zone = {
        ("acme.example", "TXT"): ["v=spf1 redirect=_spf.acme.example"],
        ("_spf.acme.example", "TXT"): ["v=spf1 include:spf.protection.outlook.com -all"],
    }

    result, _ = await _check("acme.example", zone)

    assert result["spf_status"] == "OK (-all hardfail) via redirect=_spf.acme.example"
    assert result["spf_record"] == "v=spf1 redirect=_spf.acme.example", "what is published"


async def test_spf_redirect_to_nothing_stays_a_finding():
    zone = {("acme.example", "TXT"): ["v=spf1 redirect=_spf.acme.example"]}

    result, _ = await _check("acme.example", zone)

    assert result["spf_status"] == "PRESENT (no 'all' mechanism)"


async def test_a_subdomain_inherits_the_parent_dmarc_policy():
    zone = {("_dmarc.acme.example", "TXT"): ["v=DMARC1; p=reject; rua=mailto:d@acme.example"]}

    result, asked = await _check("mail.sales.acme.example", zone)

    assert result["dmarc_status"] == "OK (p=reject) inherited from acme.example"
    assert result["dmarc_inherited_from"] == "acme.example"
    assert "_dmarc.example" not in asked, "a public suffix is never asked"


@pytest.mark.parametrize(
    ("parent_record", "status"),
    [
        # sp= is the policy for subdomains; p= applies only without it.
        ("v=DMARC1; p=reject; sp=none", "WEAK (p=none) inherited from acme.example"),
        ("v=DMARC1; p=none; sp=reject", "OK (p=reject) inherited from acme.example"),
    ],
)
async def test_the_inherited_policy_is_the_parents_sp_tag(parent_record, status):
    zone = {("_dmarc.acme.example", "TXT"): [parent_record]}

    result, _ = await _check("mail.acme.example", zone)

    assert result["dmarc_status"] == status


async def test_a_domain_with_its_own_record_does_not_look_further():
    zone = {
        ("_dmarc.mail.acme.example", "TXT"): ["v=DMARC1; p=none"],
        ("_dmarc.acme.example", "TXT"): ["v=DMARC1; p=reject"],
    }

    result, asked = await _check("mail.acme.example", zone)

    assert result["dmarc_status"] == "WEAK (p=none)"
    assert "_dmarc.acme.example" not in asked


async def test_no_record_anywhere_is_still_missing():
    result, _ = await _check("mail.acme.example", {})

    assert result["dmarc_status"] == "MISSING"
    assert "dmarc_inherited_from" not in result
