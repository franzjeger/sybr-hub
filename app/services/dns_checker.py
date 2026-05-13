"""Live DNS email-security checker (SPF, DKIM, DMARC).

Queries real DNS records for a domain — similar to MXToolbox but built-in.
Uses dnspython for reliable DNS resolution.

Design principles:
- Never report a false negative: if we can't verify, say so explicitly
- DKIM selectors are arbitrary strings — we probe common ones AND accept
  additional selectors from external sources (Uniweb DNS zone data)
- DMARC may be behind a CNAME (hosted DMARC) — follow the chain
- Three-state results: pass / warn / fail / unverifiable
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import dns.rdatatype
import dns.resolver

logger = logging.getLogger(__name__)

# Common DKIM selectors to probe (covers ~90% of providers)
DKIM_SELECTORS = [
    "selector1",     # Microsoft 365
    "selector2",     # Microsoft 365
    "google",        # Google Workspace
    "s1",            # SendGrid
    "s2",            # SendGrid
    "default",       # Generic / custom
    "dkim",          # Generic
    "k1",            # Mailchimp
    "mandrill",      # Mailchimp Transactional
    "everlytickey1", # Everlytic
    "everlytickey2", # Everlytic
    "cm",            # Campaign Monitor
    "protonmail",    # ProtonMail
    "protonmail2",   # ProtonMail
    "protonmail3",   # ProtonMail
    "mxvault",       # Mimecast
    "smtp",          # Generic SMTP
    "mail",          # Generic
]


class DnsResolutionError(Exception):
    """DNS lookup could not be answered authoritatively — distinct from
    "the name has no record of this type". Catching this branch is how
    callers render an 'unverifiable' verdict instead of fabricating a
    'record absent' one."""


class DnsTimeout(DnsResolutionError):
    """The DNS query timed out. Subclass kept for backwards compatibility —
    existing `except DnsTimeout` callsites still work, and new code can
    catch the broader DnsResolutionError to handle any unrecoverable
    lookup failure uniformly."""


def _resolve(qname: str, rdtype: str, timeout: float = 5.0) -> list[str]:
    """Resolve a DNS query and return list of record values.

    Returns empty list ONLY when the name authoritatively has no record
    of the requested type (NXDOMAIN / NoAnswer / NoNameservers). Every
    other failure (timeout, network error, malformed response, …) raises
    DnsResolutionError so the caller can mark the verdict as unverifiable
    instead of silently flipping a "record absent" classification.
    """
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        answers = resolver.resolve(qname, rdtype)
        results = []
        for rdata in answers:
            val = rdata.to_text().strip('"')
            results.append(val)
        return results
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return []
    except dns.exception.Timeout as e:
        raise DnsTimeout(f"DNS timeout for {qname} {rdtype}") from e
    except dns.resolver.LifetimeTimeout as e:
        # dnspython raises this when the overall query budget elapses —
        # functionally a timeout but a distinct exception class.
        raise DnsTimeout(f"DNS lifetime timeout for {qname} {rdtype}") from e
    except Exception as e:
        # Any other error (network issue, malformed packet, server failure)
        # — explicitly NOT 'record absent'. Surface it.
        raise DnsResolutionError(
            f"DNS resolution failed for {qname} {rdtype}: {e}"
        ) from e


def _resolve_following_cname(qname: str, rdtype: str = "TXT", max_depth: int = 5) -> list[str]:
    """Resolve a DNS query, following CNAME chains for the target type.

    Some providers (e.g. dmarcian, Valimail) use CNAME for _dmarc records.
    dnspython doesn't always auto-follow CNAME for TXT, so we do it manually.
    Propagates DnsTimeout to caller.
    """
    # First try direct resolution
    results = _resolve(qname, rdtype)
    if results:
        return results

    # Check for CNAME and follow it
    for _ in range(max_depth):
        cname_records = _resolve(qname, "CNAME")
        if not cname_records:
            break
        target = cname_records[0].rstrip(".")
        results = _resolve(target, rdtype)
        if results:
            return results
        qname = target  # Follow chain

    return []


def check_spf(domain: str) -> dict:
    """Check SPF record for a domain."""
    try:
        txt_records = _resolve(domain, "TXT")
    except DnsResolutionError as e:
        return {"status": "unverifiable", "record": None, "detail": f"DNS-oppslag feilet — kan ikke verifisere SPF ({e})"}

    spf_records = [r for r in txt_records if r.startswith("v=spf1")]

    if not spf_records:
        return {
            "status": "fail",
            "record": None,
            "detail": "No SPF record found",
        }

    record = spf_records[0]
    issues = []
    if len(spf_records) > 1:
        issues.append("Multiple SPF records (should be exactly one)")
    if "+all" in record:
        issues.append("Permissive +all allows any server to send (should be ~all or -all)")
    if "?all" in record:
        issues.append("Neutral ?all — consider ~all or -all")

    # Count DNS lookups (max 10 per RFC 7208)
    lookup_count = len(re.findall(r'\b(include:|a:|mx:|ptr:|redirect=)', record))
    if lookup_count > 10:
        issues.append(f"Too many DNS lookups ({lookup_count}/10 max)")

    status = "pass"
    if issues:
        status = "warn" if "-all" in record or "~all" in record else "fail"

    return {
        "status": status,
        "record": record,
        "detail": "; ".join(issues) if issues else "Valid SPF record",
    }


def _probe_dkim_selector(domain: str, sel: str) -> Optional[dict]:
    """Probe a single DKIM selector and return info if found."""
    qname = f"{sel}._domainkey.{domain}"

    # Try CNAME first (Microsoft, SendGrid, etc.)
    try:
        cname_records = _resolve(qname, "CNAME")
    except DnsResolutionError:
        return None  # Can't verify this selector — skip silently
    if cname_records:
        return {
            "selector": sel,
            "type": "CNAME",
            "value": cname_records[0],
            "valid": True,
        }

    # Try TXT (direct key publication)
    try:
        txt_records = _resolve(qname, "TXT")
    except DnsResolutionError:
        return None
    for txt in txt_records:
        if "p=" in txt:
            key_bits = None
            p_match = re.search(r'p=([A-Za-z0-9+/=]+)', txt)
            if p_match:
                key_bytes = len(p_match.group(1)) * 3 // 4
                key_bits = key_bytes * 8

            return {
                "selector": sel,
                "type": "TXT",
                "value": txt[:120] + "..." if len(txt) > 120 else txt,
                "key_bits": key_bits,
                "valid": True,
            }

    return None


def check_dkim(
    domain: str,
    selectors: list[str] | None = None,
    extra_selectors: list[str] | None = None,
) -> dict:
    """Check DKIM selectors for a domain.

    Args:
        domain: The domain to check.
        selectors: Override the default selector list. If None, uses DKIM_SELECTORS.
        extra_selectors: Additional selectors to probe (e.g. from Uniweb DNS zone).
                         Merged with the standard list.
    """
    probe_list = list(selectors or DKIM_SELECTORS)

    # Merge extra selectors (e.g. from Uniweb DNS zone data)
    if extra_selectors:
        existing = set(probe_list)
        for sel in extra_selectors:
            if sel not in existing:
                probe_list.append(sel)
                existing.add(sel)

    found = []
    for sel in probe_list:
        result = _probe_dkim_selector(domain, sel)
        if result:
            found.append(result)

    total_checked = len(probe_list)

    if not found:
        return {
            "status": "unverifiable",
            "selectors": [],
            "checked_count": total_checked,
            "detail": (
                f"No DKIM records found ({total_checked} selectors checked). "
                "A custom selector may exist that is not in the check list."
            ),
        }

    return {
        "status": "pass",
        "selectors": found,
        "checked_count": total_checked,
        "detail": f"{len(found)} DKIM selector(s) found: {', '.join(s['selector'] for s in found)}",
    }


def check_dmarc(domain: str) -> dict:
    """Check DMARC record for a domain. Follows CNAME chains (hosted DMARC)."""
    qname = f"_dmarc.{domain}"

    # Check for CNAME first (hosted DMARC services like dmarcian, Valimail)
    cname_target = None
    try:
        cname_records = _resolve(qname, "CNAME")
        if cname_records:
            cname_target = cname_records[0].rstrip(".")
    except DnsResolutionError as e:
        return {"status": "unverifiable", "record": None, "policy": None, "detail": f"DNS-oppslag feilet — kan ikke verifisere DMARC ({e})"}

    # Resolve TXT, following CNAME if needed
    try:
        txt_records = _resolve_following_cname(qname, "TXT")
    except DnsResolutionError as e:
        if cname_target:
            return {"status": "pass", "record": None, "policy": "hosted", "cname_target": cname_target, "detail": f"Hosted DMARC via CNAME → {cname_target}"}
        return {"status": "unverifiable", "record": None, "policy": None, "detail": f"DNS-oppslag feilet — kan ikke verifisere DMARC ({e})"}
    dmarc_records = [r for r in txt_records if "dmarc1" in r.lower()]

    if not dmarc_records:
        if cname_target:
            # CNAME exists but we couldn't resolve the target TXT
            return {
                "status": "pass",
                "record": None,
                "policy": "hosted",
                "cname_target": cname_target,
                "detail": f"Hosted DMARC via CNAME → {cname_target}",
            }
        return {
            "status": "fail",
            "record": None,
            "policy": None,
            "detail": "No DMARC record found",
        }

    record = dmarc_records[0]

    # Extract policy
    policy_match = re.search(r'p=(none|quarantine|reject)', record, re.IGNORECASE)
    policy = policy_match.group(1).lower() if policy_match else "unknown"

    # Extract sub-domain policy
    sp_match = re.search(r'sp=(none|quarantine|reject)', record, re.IGNORECASE)
    sub_policy = sp_match.group(1).lower() if sp_match else policy

    # Extract percentage
    pct_match = re.search(r'pct=(\d+)', record)
    pct = int(pct_match.group(1)) if pct_match else 100

    # Extract rua (aggregate reports)
    rua_match = re.search(r'rua=([^;]+)', record)
    rua = rua_match.group(1).strip() if rua_match else None

    issues = []
    if policy == "none":
        issues.append("Policy is 'none' (monitoring only) — consider quarantine or reject")
    if pct < 100:
        issues.append(f"Only {pct}% of messages are subject to DMARC policy")
    if not rua:
        issues.append("No rua (aggregate report) address — you won't receive DMARC reports")

    if policy == "reject":
        status = "pass"
    elif policy == "quarantine":
        status = "pass" if pct == 100 else "warn"
    elif policy == "none":
        status = "warn"
    else:
        status = "fail"

    result = {
        "status": status,
        "record": record,
        "policy": policy,
        "sub_policy": sub_policy,
        "pct": pct,
        "rua": rua,
        "detail": "; ".join(issues) if issues else f"DMARC policy: {policy} (enforced on {pct}%)",
    }
    if cname_target:
        result["cname_target"] = cname_target
    return result


def check_mx(domain: str) -> dict:
    """Check MX records for a domain."""
    try:
        mx_records = _resolve(domain, "MX")
    except DnsResolutionError as e:
        return {"status": "unverifiable", "records": [], "detail": f"DNS-oppslag feilet — kan ikke verifisere MX ({e})"}
    if not mx_records:
        return {"status": "fail", "records": [], "detail": "No MX records found"}

    records = []
    for mx in mx_records:
        parts = mx.split()
        if len(parts) >= 2:
            records.append({"priority": int(parts[0]), "host": parts[1].rstrip(".")})

    records.sort(key=lambda r: r["priority"])

    # Detect provider
    provider = "Unknown"
    hosts_lower = " ".join(r["host"].lower() for r in records)
    if "protection.outlook.com" in hosts_lower:
        provider = "Microsoft 365"
    elif "google" in hosts_lower or "googlemail" in hosts_lower:
        provider = "Google Workspace"
    elif "mimecast" in hosts_lower:
        provider = "Mimecast"
    elif "proofpoint" in hosts_lower or "pphosted" in hosts_lower:
        provider = "Proofpoint"
    elif "sendgrid" in hosts_lower:
        provider = "SendGrid"

    return {
        "status": "pass",
        "records": records,
        "provider": provider,
        "detail": f"{len(records)} MX record(s), provider: {provider}",
    }


def extract_dkim_selectors_from_dns_records(dns_records: list[dict]) -> list[str]:
    """Extract DKIM selector names from Uniweb/zone DNS records.

    Scans for hostnames matching *._domainkey and extracts the selector part.
    This catches custom selectors (like dkim54) that would never be in the
    standard probe list.
    """
    selectors = []
    for rec in dns_records:
        hostname = (rec.get("hostname") or "").lower()
        rtype = (rec.get("type") or "").upper()
        if "_domainkey" in hostname and rtype in ("CNAME", "TXT"):
            # Extract selector: "dkim54._domainkey" → "dkim54"
            parts = hostname.split("._domainkey")
            if parts[0] and parts[0] != "_domainkey":
                sel = parts[0].strip(".")
                if sel and sel not in selectors:
                    selectors.append(sel)
    return selectors


def check_domain(
    domain: str,
    uniweb_dns_records: list[dict] | None = None,
) -> dict:
    """Run full email security check on a domain (SPF + DKIM + DMARC + MX).

    Args:
        domain: Domain name to check.
        uniweb_dns_records: Optional DNS records from Uniweb zone data. Used to
            discover custom DKIM selectors that aren't in the standard probe list.
    """
    domain = domain.strip().lower().rstrip(".")

    # Extract any custom DKIM selectors from Uniweb zone data
    extra_selectors = None
    if uniweb_dns_records:
        extra_selectors = extract_dkim_selectors_from_dns_records(uniweb_dns_records)

    result = {
        "domain": domain,
        "mx": check_mx(domain),
        "spf": check_spf(domain),
        "dkim": check_dkim(domain, extra_selectors=extra_selectors),
        "dmarc": check_dmarc(domain),
    }

    # Overall grade
    checks = [result["spf"]["status"], result["dkim"]["status"], result["dmarc"]["status"]]

    # "unverifiable" is not a failure — treat it as neutral for grading
    effective = [("pass" if s == "unverifiable" else s) for s in checks]

    if all(s == "pass" for s in effective):
        result["grade"] = "A" if "unverifiable" not in checks else "B"
    elif "fail" not in effective:
        result["grade"] = "B"
    elif effective.count("fail") == 1:
        result["grade"] = "C"
    elif effective.count("fail") == 2:
        result["grade"] = "D"
    else:
        result["grade"] = "F"

    return result
