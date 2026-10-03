"""Which customer each Tailscale node belongs to.

The tailnet has no notion of a customer, so a node is mapped one of two ways,
and the first that answers wins:

1. **By hand.** A technician assigned the node to a customer; the assignment
   is a row in ``tailscale_node_customers``. It wins over a tag, so a node
   tagged for one customer but serving another can be put right without
   touching the tailnet's ACLs.
2. **By tag.** The node carries ``tag:customer-<slug>`` in the tailnet, where
   ``<slug>`` is the customer's id lowercased with anything but a-z, 0-9 and
   "-" turned into "-" (``customer_tag`` below). Tagging is done in Tailscale
   (admin console, ACL ``tagOwners``, or an auth key minted with the tag), so
   a node that joins already tagged lands on its customer with nobody here
   doing anything.

A tag that two customers' slugs share names neither: those nodes need a hand
assignment. A node with neither belongs to no customer and shows only under
Verktøy > Tailscale.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlmodel import delete, select

from app.core.orm import get_session
from app.models.tailscale import TailscaleNodeCustomer

TAG_PREFIX = "tag:customer-"
SOURCE_MANUAL = "manual"
SOURCE_TAG = "tag"


def customer_slug(customer_id: str) -> str:
    """The tag-safe form of a customer id: "Kunde_A" -> "kunde-a"."""
    slug = re.sub(r"[^a-z0-9-]+", "-", (customer_id or "").lower())
    return re.sub(r"-{2,}", "-", slug).strip("-")


def customer_tag(customer_id: str) -> str:
    """The tailnet tag that maps a node to this customer."""
    return TAG_PREFIX + customer_slug(customer_id)


async def manual_assignments() -> dict[str, str]:
    """{device_id: customer_id} for every node assigned by hand."""
    async with get_session() as session:
        rows = (await session.execute(select(TailscaleNodeCustomer))).scalars().all()
    return {row.device_id: row.customer_id for row in rows}


async def assign(device_id: str, customer_id: str | None, assigned_by: str) -> None:
    """Assign a node to a customer by hand, or drop its assignment (None)."""
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


def resolve(
    devices: list[dict], customer_ids: list[str], manual: dict[str, str]
) -> dict[str, tuple[str, str]]:
    """{device_id: (customer_id, source)} for each node that has a customer.

    ``customer_ids`` is every registered customer, so a hand assignment to a
    customer since archived is ignored rather than shown under nobody, and a
    tag is matched against all slugs to catch a collision.
    """
    known = set(customer_ids)
    by_slug: dict[str, list[str]] = {}
    for cid in customer_ids:
        by_slug.setdefault(customer_slug(cid), []).append(cid)

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
            if isinstance(tag, str) and tag.startswith(TAG_PREFIX)
            for cid in by_slug.get(tag[len(TAG_PREFIX) :], [])
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
