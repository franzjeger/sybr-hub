"""Which customer each Tailscale node belongs to.

The tailnet has no notion of a customer, so a node is mapped one of two ways,
and the first that answers wins:

1. **By hand.** A technician assigned the node to a customer; the assignment
   is a row in ``tailscale_node_customers``. It wins over a tag, so a node
   tagged for one customer but serving another can be put right without
   touching the tailnet's ACLs.
2. **By tag.** The node carries the customer's tag in the tailnet:
   ``tag:customer-<slug>``, where ``<slug>`` is the customer's id lowercased
   with anything but a-z, 0-9 and "-" turned into "-" (``customer_tag``
   below), unless an administrator gave the customer a tag of its own
   (``tailscale_customer_tags``), for a tailnet that names its tags otherwise.
   Tagging is done in Tailscale (admin console, ACL ``tagOwners``, or an auth
   key minted with the tag), so a node that joins already tagged lands on its
   customer with nobody here doing anything.

A tag that two customers share names neither: those nodes need a hand
assignment. A node with neither belongs to no customer and shows only under
Verktøy > Tailscale.

The customer page's Tilgang tab reads a customer's nodes through a short cache
(``cached_nodes``), which any change to a mapping empties.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime

from sqlmodel import delete, select

from app.core.orm import get_session
from app.models.tailscale import TailscaleCustomerTag, TailscaleNodeCustomer

TAG_PREFIX = "tag:customer-"
SOURCE_MANUAL = "manual"
SOURCE_TAG = "tag"


def customer_slug(customer_id: str) -> str:
    """The tag-safe form of a customer id: "Kunde_A" -> "kunde-a"."""
    slug = re.sub(r"[^a-z0-9-]+", "-", (customer_id or "").lower())
    return re.sub(r"-{2,}", "-", slug).strip("-")


def customer_tag(customer_id: str) -> str:
    """The tag made from the customer's id, which maps a node to it by default."""
    return TAG_PREFIX + customer_slug(customer_id)


# Tailscale's own rule (tailcfg.CheckTag): "tag:", then a letter, then letters,
# digits and "-". Tailscale reads tags without regard to case and writes them
# in lower case, so a tag is kept in lower case here too.
_TAG = re.compile(r"tag:[a-z][a-z0-9-]*")


def normalize_tag(tag: str) -> str | None:
    """*tag* in the form Tailscale keeps it, or None if Tailscale would refuse it."""
    tag = tag.strip().lower()
    return tag if _TAG.fullmatch(tag) else None


async def tag_overrides() -> dict[str, str]:
    """{customer_id: tag} for every customer an administrator gave its own tag."""
    async with get_session() as session:
        rows = (await session.execute(select(TailscaleCustomerTag))).scalars().all()
    return {row.customer_id: row.tag for row in rows}


def effective_tags(customer_ids: list[str], overrides: dict[str, str]) -> dict[str, str]:
    """{customer_id: the tag that maps a node to it}: its own, or the one from its id."""
    return {cid: overrides.get(cid) or customer_tag(cid) for cid in customer_ids}


async def set_tag_override(customer_id: str, tag: str | None, set_by: str) -> None:
    """Give the customer its own tag, or go back to the one from its id (None).

    *tag* is already normalised. Every cached node list is dropped: the tag can
    take nodes from another customer, or leave them with nobody.
    """
    async with get_session() as session:
        await session.execute(
            delete(TailscaleCustomerTag).where(TailscaleCustomerTag.customer_id == customer_id)
        )
        if tag:
            session.add(
                TailscaleCustomerTag(
                    customer_id=customer_id,
                    tag=tag,
                    set_by=set_by,
                    set_at=datetime.now(UTC).isoformat(),
                )
            )
        await session.commit()
    invalidate_nodes()


async def manual_assignments() -> dict[str, str]:
    """{device_id: customer_id} for every node assigned by hand."""
    async with get_session() as session:
        rows = (await session.execute(select(TailscaleNodeCustomer))).scalars().all()
    return {row.device_id: row.customer_id for row in rows}


async def assign(device_id: str, customer_id: str | None, assigned_by: str) -> None:
    """Assign a node to a customer by hand, or drop its assignment (None).

    Every cached node list is dropped, not only the two customers': the node
    also leaves, or joins, the list of nodes nobody has.
    """
    async with get_session() as session:
        await session.execute(
            delete(TailscaleNodeCustomer).where(TailscaleNodeCustomer.device_id == device_id)
        )
        if customer_id:
            session.add(
                TailscaleNodeCustomer(
                    device_id=device_id,
                    customer_id=customer_id,
                    assigned_by=assigned_by,
                    assigned_at=datetime.now(UTC).isoformat(),
                )
            )
        await session.commit()
    invalidate_nodes()


def resolve(
    devices: list[dict],
    customer_ids: list[str],
    manual: dict[str, str],
    overrides: dict[str, str],
) -> dict[str, tuple[str, str]]:
    """{device_id: (customer_id, source)} for each node that has a customer.

    ``customer_ids`` is every registered customer, so a hand assignment to a
    customer since archived is ignored rather than shown under nobody, and a
    tag is matched against every customer's tag to catch a collision.
    ``overrides`` are the customers' own tags (``tag_overrides``).
    """
    known = set(customer_ids)
    by_tag: dict[str, list[str]] = {}
    for cid, tag in effective_tags(customer_ids, overrides).items():
        by_tag.setdefault(tag, []).append(cid)

    out: dict[str, tuple[str, str]] = {}
    for device in devices:
        device_id = str(device.get("id") or "")
        if not device_id:
            continue
        assigned = manual.get(device_id)
        if assigned and assigned in known:
            out[device_id] = (assigned, SOURCE_MANUAL)
            continue
        matches = {
            cid
            for tag in device.get("tags") or []
            if isinstance(tag, str)
            for cid in by_tag.get(tag, [])
        }
        if len(matches) == 1:
            out[device_id] = (matches.pop(), SOURCE_TAG)
    return out


def connect_info(device: dict) -> dict:
    """What a technician needs to reach the node: its addresses and DNS name."""
    addresses = [a for a in device.get("addresses") or [] if isinstance(a, str)]
    ipv4 = next((a for a in addresses if ":" not in a), "")
    return {
        "ip": ipv4 or (addresses[0] if addresses else ""),
        "addresses": addresses,
        # The MagicDNS name, which the API reports as the device's full name.
        "dns_name": device.get("name") or "",
    }


# ── The Tilgang tab's node list, cached ──────────────────────────────────────
# The tab is opened to find a customer's node and connect to it, and opened
# again within a minute as often as not: back from another tab, or to the next
# customer and back. Each open asked Tailscale for the whole tailnet. A minute
# is short enough that the online state it shows still decides whether to try
# a node, and the list of nodes nobody has is no older than the open tab's.
# The cache holds no failure and no "not configured".
NODES_TTL_SECONDS = 60.0

_nodes_cache: dict[str, tuple[float, dict]] = {}


def cached_nodes(customer_id: str) -> dict | None:
    """The customer's node list as last read, if it is younger than the TTL."""
    entry = _nodes_cache.get(customer_id)
    if entry is None or time.monotonic() - entry[0] > NODES_TTL_SECONDS:
        return None
    return entry[1]


def cache_nodes(customer_id: str, payload: dict) -> None:
    _nodes_cache[customer_id] = (time.monotonic(), payload)


def invalidate_nodes() -> None:
    """Drop every customer's cached node list.

    For any change to a mapping: a hand assignment, a customer's own tag, the
    tailnet or its key. All of them rather than one, because a change for one
    customer moves nodes to or from another, or to or from nobody.
    """
    _nodes_cache.clear()
