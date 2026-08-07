"""Visiting each customer's site over VPN to read what is there.

The job the system account exists for. For every VPN profile bound to a
customer: bring the tunnel up as ``sybr-system``, run the network audit that
already knows how to read a FortiGate and a UniFi controller, store the result,
bring the tunnel down. Then the next customer.

**One at a time, and that is not a performance oversight.** Customer sites
overlap on RFC1918 — three of them will each claim 192.168.1.0/24 — so two
tunnels up at once means routes fighting, and the collector reading whichever
site won. Sequential is the only shape that produces trustworthy data.

**The tunnel always comes down.** In a ``finally``, and again in a sweep at the
end for anything the loop did not reach. A collector that dies holding a tunnel
into a customer network leaves the toolkit connected to somebody's site with
nobody aware of it, until a human notices VPN is refusing to work and asks why.

**It never takes a tunnel from a person.** The lock added with the system
account stops a technician tearing down a collection; this is the other
direction. A profile a human is already using is skipped and reported, because
a background job that disconnects somebody mid-session to gather statistics has
its priorities backwards.

**One site failing is not the run failing.** A customer whose VPN is down, or
whose firewall stopped answering, is recorded as that and the run moves on.
Every site is attempted; the summary says which produced data.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# How long one site gets: bring a tunnel up, read two appliances, drop it. A
# tunnel that will not establish is the usual reason this expires, and without a
# bound one unreachable site stalls every customer behind it.
SITE_TIMEOUT = 300

# Sites are visited in id order for a stable, reproducible run rather than
# whatever order the profile store happens to return.
COLLECTED, SKIPPED, FAILED = "collected", "skipped", "failed"


@dataclass
class SiteResult:
    """What happened at one customer's site."""

    profile_id: str
    profile_name: str
    customer_id: str
    outcome: str
    detail: str = ""
    data: dict | None = field(default=None, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id, "profile_name": self.profile_name,
            "customer_id": self.customer_id, "outcome": self.outcome,
            "detail": self.detail,
        }


def _store(customer_id: str, payload: dict) -> None:
    """Keep the reading beside the customer's audits, encrypted like the rest."""
    from app.core.config import get_audit_dir
    from app.core.encryption import encrypted_write_text

    stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    directory = get_audit_dir() / customer_id / "site_stats"
    directory.mkdir(parents=True, exist_ok=True)
    encrypted_write_text(directory / f"{stamp}.json", json.dumps(payload))


async def collect_site(profile, *, timeout: int = SITE_TIMEOUT) -> SiteResult:
    """Visit one site: connect, read, disconnect. Always disconnect."""
    from app.core.customer import CustomerManager
    from app.core.system_user import USERNAME
    from app.services.network_audit import run_quick_network_audit
    from app.services.vpn_manager import _is_connected, connect, disconnect, owner_of

    customer_id = str(getattr(profile, "customer_id", "") or "")
    result = SiteResult(
        profile_id=profile.id, profile_name=profile.name,
        customer_id=customer_id, outcome=SKIPPED,
    )

    if not customer_id:
        result.detail = "The profile is not bound to a customer, so there is nowhere to file what it finds."
        return result

    if _is_connected(profile.id):
        holder = owner_of(profile.id)
        if holder and holder != USERNAME:
            # A background job that disconnects somebody mid-session to gather
            # statistics has its priorities backwards.
            result.detail = f"{holder} is using this tunnel."
            return result

    customer = CustomerManager.get_customer(customer_id)
    if not customer:
        result.detail = f"No customer {customer_id!r} to read for."
        return result

    connected = False
    try:
        async with asyncio.timeout(timeout):
            outcome = await connect(profile.id, owned_by=USERNAME)
            if not outcome or outcome.get("state") == "error":
                result.outcome = FAILED
                result.detail = str((outcome or {}).get("error") or "The tunnel did not come up.")
                return result
            connected = True

            data = await run_quick_network_audit(customer, customer_id)
            if not any(data.get(k) for k in ("fortigate", "unifi")):
                result.outcome = FAILED
                result.detail = "The tunnel came up and neither appliance answered."
                return result

            _store(customer_id, {
                "collected_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "profile_id": profile.id,
                "profile_name": profile.name,
                "collected_by": USERNAME,
                **data,
            })
            result.outcome = COLLECTED
            result.data = data
            result.detail = ", ".join(
                k for k in ("fortigate", "unifi") if data.get(k)
            ) + " read"
            return result

    except TimeoutError:
        result.outcome = FAILED
        result.detail = f"Gave up after {timeout}s — the tunnel or the appliances did not answer."
        return result
    except Exception as exc:
        result.outcome = FAILED
        result.detail = str(exc)
        return result
    finally:
        if connected:
            # Deliberately outside the timeout above: a site that expired is
            # exactly the one most likely to still be holding a tunnel.
            try:
                await disconnect(profile.id)
            except Exception as exc:
                logger.error(
                    "Could not close the tunnel to %s after collecting: %s",
                    profile.name, exc,
                )


async def collect_all(*, timeout: int = SITE_TIMEOUT) -> dict[str, Any]:
    """Visit every customer site with a VPN profile, one at a time."""
    from app.core.system_user import USERNAME, ensure
    from app.services.vpn_manager import disconnect, list_profiles, system_held

    await ensure()

    profiles = sorted(
        [p for p in await list_profiles() if getattr(p, "customer_id", None)],
        key=lambda p: str(p.id),
    )
    logger.warning("Site collection starting for %d site(s)", len(profiles))

    results: list[SiteResult] = []
    try:
        for profile in profiles:
            results.append(await collect_site(profile, timeout=timeout))
    finally:
        # Anything the loop did not reach — a cancellation between connect and
        # the finally above, for instance. A collector that dies holding a
        # tunnel leaves the toolkit inside somebody's network unnoticed.
        for profile_id in system_held():
            logger.error("Tunnel %s was still open after collection; closing", profile_id)
            try:
                await disconnect(profile_id)
            except Exception as exc:
                logger.error("Could not close leftover tunnel %s: %s", profile_id, exc)

    summary = {
        "sites": len(profiles),
        "collected": sum(1 for r in results if r.outcome == COLLECTED),
        "skipped": sum(1 for r in results if r.outcome == SKIPPED),
        "failed": sum(1 for r in results if r.outcome == FAILED),
        "results": [r.as_dict() for r in results],
        "collected_by": USERNAME,
    }
    logger.warning(
        "Site collection finished: %(collected)d collected, %(skipped)d skipped, "
        "%(failed)d failed of %(sites)d", summary,
    )
    return summary
