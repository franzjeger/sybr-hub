"""Cross-audit: a customer's Uniweb-held domains vs their email-security posture.

The M365 audit's DNS/email section (and the shared ``dns_checker``) already
grade SPF / DMARC / DKIM per domain. This joins that verdict to Uniweb's DNS
control: for each domain the customer holds at Uniweb, run the same check and
mark the gaps Uniweb can actually *fix* — the domains whose DNS Uniweb hosts (a
clustered zone), where adding the missing record is a Partner-API write away.

Read-only. The write that closes a gap lives separately (Phase 3b); this module
only tells the operator which gaps are closable here.
"""

from __future__ import annotations

import asyncio
import logging

from app.services.dns_checker import check_domain
from app.services.uniweb_partner import UniwebAuthError, UniwebPartnerError

logger = logging.getLogger(__name__)

# The sub-checks whose failure is a single-DNS-record fix (what 3b will target).
_FIXABLE_KINDS = ("spf", "dmarc", "dkim")
# A gap is a real negative verdict. "unverifiable" means the lookup failed —
# "we could not check", not "missing" — so it is never counted as a gap.
_GAP_STATUSES = ("fail", "warn")

# Bound the work: each domain is one Uniweb zone read plus a live email-security
# check (several DNS lookups). Past this many domains the caller is told the
# list was truncated rather than the request hanging on a huge portfolio.
_MAX_DOMAINS = 25


def dns_domains(subscriptions: list[dict]) -> list[str]:
    """The domain names a customer holds at Uniweb — its ``dns`` subscriptions.

    Pure: the product ``code`` is ``dns`` for a domain, and ``username`` is the
    domain itself. De-duplicated, lower-cased, order preserved.
    """
    seen: set[str] = set()
    out: list[str] = []
    for sub in subscriptions:
        if str((sub.get("product") or {}).get("code") or "").lower() != "dns":
            continue
        name = str(sub.get("username") or "").strip().lower().rstrip(".")
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def domain_health(domain: str, check: dict, uniweb_hosts_dns: bool) -> dict:
    """One domain's email-security posture, flagging the Uniweb-fixable gaps.

    ``check`` is a ``dns_checker.check_domain`` result. A gap is a spf/dmarc/dkim
    sub-check that failed or warned (never "unverifiable" — that is a failed
    lookup, not a missing record). ``fixable_here`` is true only when Uniweb
    hosts the zone, so the UI never offers a fix it cannot perform.
    """
    gaps: list[dict] = []
    for kind in _FIXABLE_KINDS:
        sub = check.get(kind) or {}
        if sub.get("status") in _GAP_STATUSES:
            gaps.append({
                "kind": kind,
                "status": sub.get("status"),
                "detail": sub.get("detail") or "",
            })
    return {
        "domain": domain,
        "grade": check.get("grade"),
        "spf": (check.get("spf") or {}).get("status"),
        "dmarc": (check.get("dmarc") or {}).get("status"),
        "dkim": (check.get("dkim") or {}).get("status"),
        "uniweb_hosts_dns": uniweb_hosts_dns,
        "gaps": gaps,
        "fixable_here": bool(uniweb_hosts_dns and gaps),
    }


def summarize(domains: list[dict], total: int) -> dict:
    """Wrap the per-domain results with the counts the card leads with."""
    return {
        "domains": domains,
        "checked": len(domains),
        "total": total,
        "truncated": total > len(domains),
        "with_gaps": sum(1 for d in domains if d["gaps"]),
        "fixable_count": sum(1 for d in domains if d["fixable_here"]),
    }


async def cross_audit(subscriptions: list[dict], client, *, checker=None) -> dict:
    """Per Uniweb-held domain: its email-security posture + Uniweb-fixable gaps.

    ``client`` is a ``UniwebPartnerClient`` — its zone read is what says whether
    Uniweb hosts the DNS (a clustered zone answers with records; a domain hosted
    elsewhere raises, which reads as "not hosted here", never as a hard error).
    ``checker(domain)`` runs the email-security check; it defaults to the shared
    blocking ``dns_checker.check_domain`` in a thread, and is injected in tests.
    Domains are processed concurrently so the wall-clock is the slowest one, not
    the sum.
    """
    domains = dns_domains(subscriptions)
    capped = domains[:_MAX_DOMAINS]
    if len(domains) > _MAX_DOMAINS:
        logger.info(
            "Uniweb email-DNS cross-audit: checking %d of %d domains (capped)",
            _MAX_DOMAINS, len(domains),
        )
    loop = asyncio.get_event_loop()

    async def _one(domain: str) -> dict:
        try:
            records = await client.dns_records(domain)
        except UniwebAuthError:
            raise
        except UniwebPartnerError:
            # Clustered-only endpoint: a non-auth failure means Uniweb does not
            # host this domain's DNS — it is simply not fixable here.
            records = []
        if checker is not None:
            check = checker(domain)
        else:
            check = await loop.run_in_executor(None, check_domain, domain)
        return domain_health(domain, check, bool(records))

    results = await asyncio.gather(*[_one(d) for d in capped])
    return summarize(list(results), len(domains))
