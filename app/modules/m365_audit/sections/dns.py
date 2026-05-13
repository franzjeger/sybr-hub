"""Section 26 — DNS / Email Security (SPF, DMARC, DKIM, MTA-STS) via Google DoH."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx

from app.modules.base import BaseSection, SectionResult, SectionStatus

_DOH = "https://dns.google/resolve"
_HTTP_TIMEOUT = 15


class DnsLookupError(Exception):
    """Raised when a DNS-over-HTTPS query cannot be answered (transport
    error, non-2xx status, malformed JSON). Distinct from 'record absent',
    which is represented by an empty answer list."""


# DoH RCODE → human-readable string. 0 = NoError; any non-zero means the
# upstream resolver returned a structured error (NXDOMAIN, SERVFAIL, …) — we
# trust that NOERROR with no Answer means "the name exists, no records of
# this type", which is the case we want to render as MISSING.
_DOH_RCODES = {
    0: "NoError",
    1: "FormErr",
    2: "ServFail",
    3: "NXDomain",
    4: "NotImp",
    5: "Refused",
}


def _classify_spf(record: str) -> str:
    """Classify an SPF record as OK / WEAK / CRITICAL."""
    if not record:
        return "MISSING"
    if "~all" in record:
        return "WEAK (~all softfail)"
    if "-all" in record:
        return "OK (-all hardfail)"
    if "+all" in record:
        return "CRITICAL (+all — allows anyone)"
    if "?all" in record:
        return "WEAK (?all neutral)"
    return "PRESENT (no 'all' mechanism)"


def _classify_dmarc(record: str) -> str:
    if not record:
        return "MISSING"
    if "p=reject" in record:
        return "OK (p=reject)"
    if "p=quarantine" in record:
        return "WARN (p=quarantine)"
    if "p=none" in record:
        return "WEAK (p=none)"
    return "PRESENT (unknown policy)"


async def _doh_query(
    client: httpx.AsyncClient, name: str, qtype: str
) -> list[str]:
    """Query Google DNS-over-HTTPS and return answer data strings.

    Raises DnsLookupError on transport failures so the caller can distinguish
    "the record genuinely doesn't exist" (empty list) from "we never got a
    usable answer" (raised) — silently treating the latter as the former
    produces false 'MISSING' verdicts in the email-security audit.
    """
    try:
        resp = await client.get(
            _DOH,
            params={"name": name, "type": qtype},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as ex:
        raise DnsLookupError(f"{qtype} {name}: {ex}") from ex

    status_code = data.get("Status", 0)
    if status_code == 3:               # NXDOMAIN — name does not exist
        return []
    if status_code != 0:               # SERVFAIL / REFUSED / FORMERR / …
        raise DnsLookupError(
            f"{qtype} {name}: DoH status {status_code} "
            f"({_DOH_RCODES.get(status_code, 'unknown')})"
        )
    answers = data.get("Answer", [])
    return [a.get("data", "").strip('"') for a in answers]


async def _safe_query(
    client: httpx.AsyncClient, name: str, qtype: str
) -> tuple[list[str], Optional[str]]:
    """Run a DoH query and return (records, error_msg).

    `error_msg` is None on success (including a clean NXDOMAIN) and a short
    diagnostic string when the query itself failed — so the caller can
    render 'ERROR' instead of fabricating 'MISSING'.
    """
    try:
        return await _doh_query(client, name, qtype), None
    except DnsLookupError as ex:
        return [], str(ex)


async def _check_domain(
    client: httpx.AsyncClient, domain: str
) -> dict:
    """Return a dict of DNS check results for one domain.

    Each *_status field is either a classification, "ERROR (...)" when the
    underlying DoH query could not be answered, or "MISSING" when the name
    exists but has no matching record. Callers MUST treat ERROR distinctly
    from MISSING — a timeout is not the same as "no SPF configured".
    """
    result: dict[str, str] = {"domain": domain}
    errors: list[str] = []

    # SPF
    txt_records, err = await _safe_query(client, domain, "TXT")
    if err:
        errors.append(f"SPF lookup failed: {err}")
        result["spf_record"] = "(query failed)"
        result["spf_status"] = f"ERROR ({err})"
    else:
        spf_record = next((r for r in txt_records if r.startswith("v=spf1")), "")
        result["spf_record"] = spf_record or "(none)"
        result["spf_status"] = _classify_spf(spf_record)

    # DMARC
    dmarc_records, err = await _safe_query(client, f"_dmarc.{domain}", "TXT")
    if err:
        errors.append(f"DMARC lookup failed: {err}")
        result["dmarc_record"] = "(query failed)"
        result["dmarc_status"] = f"ERROR ({err})"
    else:
        dmarc_record = next(
            (r for r in dmarc_records if r.startswith("v=DMARC1")), ""
        )
        result["dmarc_record"] = dmarc_record or "(none)"
        result["dmarc_status"] = _classify_dmarc(dmarc_record)

    # DKIM — M365 + third-party selectors
    _third_party_selectors = ("google", "k1", "k2", "default", "dkim")
    for sel in ("selector1", "selector2") + _third_party_selectors:
        cname_data, cname_err = await _safe_query(
            client, f"{sel}._domainkey.{domain}", "CNAME"
        )
        txt_data, txt_err = await _safe_query(
            client, f"{sel}._domainkey.{domain}", "TXT"
        )
        if cname_err and txt_err:
            errors.append(f"DKIM {sel} lookup failed: {cname_err}")
            result[f"dkim_{sel}"] = f"ERROR ({cname_err})"
        elif cname_data:
            result[f"dkim_{sel}"] = f"CNAME -> {cname_data[0]}"
        elif txt_data:
            result[f"dkim_{sel}"] = "TXT present"
        else:
            result[f"dkim_{sel}"] = "MISSING"

    # MTA-STS
    mta_records, err = await _safe_query(client, f"_mta-sts.{domain}", "TXT")
    if err:
        errors.append(f"MTA-STS lookup failed: {err}")
        result["mta_sts"] = f"ERROR ({err})"
    else:
        mta_sts = next((r for r in mta_records if "v=STSv1" in r), "")
        result["mta_sts"] = mta_sts if mta_sts else "MISSING"

    if errors:
        result["_lookup_errors"] = "; ".join(errors)

    return result


class DnsSection(BaseSection):
    name = "DNS / Email Security"

    def __init__(
        self,
        out_dir: Path,
        verified_domains: list[str],
        progress_cb=None,
    ):
        super().__init__(out_dir, progress_cb)
        # Filter out onmicrosoft.com and other non-production domains
        _SKIP_SUFFIXES = (".onmicrosoft.com", ".inkyphishfence.com", ".mimecast.com",
                          ".pphosted.com", ".barracudanetworks.com")
        self.verified_domains = [
            d for d in verified_domains
            if not any(d.lower().endswith(s) for s in _SKIP_SUFFIXES)
        ]

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            async with httpx.AsyncClient() as client:
                results = [
                    await _check_domain(client, d)
                    for d in self.verified_domains
                ]

            has_issues = False
            lines = [
                "=" * 110,
                "  DNS / EMAIL SECURITY REPORT (SPF · DMARC · DKIM · MTA-STS)",
                "=" * 110,
            ]
            warn_lines = [
                "=" * 110,
                "  DNS / EMAIL SECURITY — WARNINGS",
                "=" * 110,
            ]

            _third_party_selectors = ("google", "k1", "k2", "default", "dkim")

            for r in results:
                domain = r["domain"]

                # Build DKIM (3rd party) summary
                tp_parts = []
                for sel in _third_party_selectors:
                    tp_parts.append(f"{sel}: {r.get(f'dkim_{sel}', 'MISSING')}")
                tp_summary = " | ".join(tp_parts)

                # Collect all found selectors for summary
                all_selectors = ("selector1", "selector2") + _third_party_selectors
                found_selectors = [
                    sel for sel in all_selectors
                    if r.get(f"dkim_{sel}", "MISSING") not in ("MISSING",)
                    and not r.get(f"dkim_{sel}", "").startswith("ERROR")
                ]

                lines += [
                    f"\n  Domain : {domain}",
                    f"    SPF            : {r['spf_status']}",
                    f"                   {r['spf_record']}",
                    f"    DMARC          : {r['dmarc_status']}",
                    f"                   {r['dmarc_record']}",
                    f"    DKIM (M365)    : selector1: {r['dkim_selector1']} | selector2: {r['dkim_selector2']}",
                    f"    DKIM (3rd party): {tp_summary}",
                ]
                if found_selectors:
                    lines.append(f"    DKIM found     : {', '.join(found_selectors)}")
                else:
                    lines.append(f"    DKIM found     : (none)")
                lines.append(f"    MTA-STS        : {r['mta_sts']}")

                if r.get("_lookup_errors"):
                    lines.append(f"    DNS errors     : {r['_lookup_errors']}")
                    self._warn(
                        f"[{domain}] DNS lookups failed — verdict is partial: "
                        f"{r['_lookup_errors']}"
                    )

                # Warnings — only when we have a real verdict. ERROR means the
                # query failed, so reporting "SPF MISSING" would be a lie.
                spf_s   = r["spf_status"]
                dmarc_s = r["dmarc_status"]
                domain_issues = []

                if not spf_s.startswith("ERROR") and (
                    "MISSING" in spf_s or "WEAK" in spf_s or "CRITICAL" in spf_s
                ):
                    domain_issues.append(f"SPF: {spf_s}")
                    self._warn(f"[{domain}] SPF issue: {spf_s}")
                if not dmarc_s.startswith("ERROR") and (
                    "MISSING" in dmarc_s or "WEAK" in dmarc_s
                ):
                    domain_issues.append(f"DMARC: {dmarc_s}")
                    self._warn(f"[{domain}] DMARC issue: {dmarc_s}")

                # DKIM warning if both M365 selectors are missing (not ERROR)
                sel1 = r.get("dkim_selector1", "MISSING")
                sel2 = r.get("dkim_selector2", "MISSING")
                m365_sel1_missing = sel1 == "MISSING"
                m365_sel2_missing = sel2 == "MISSING"
                if m365_sel1_missing and m365_sel2_missing:
                    domain_issues.append("DKIM: M365 DKIM not configured (both selector1 and selector2 missing)")
                    self._warn(f"[{domain}] M365 DKIM not configured — both selector1 and selector2 are missing")

                if domain_issues:
                    has_issues = True
                    warn_lines += [
                        f"\n  Domain : {domain}",
                        *[f"    ISSUE: {issue}" for issue in domain_issues],
                    ]

            lines += ["", "=" * 110, ""]
            self._save("26_email_dns_spf_dmarc.txt", "\n".join(lines))

            if has_issues:
                warn_lines += ["", "=" * 110, ""]
                self._save("26_email_dns_spf_dmarc_WARN.txt", "\n".join(warn_lines))

            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result
