"""The firmware each customer device was last seen running.

Read-only lists over app/services/firmware_inventory.py, which the FortiGate
poller, the UniFi firmware check, the network audit, the network inventory and
the daily firmware job write to. Nothing here reaches a device.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.rbac import get_accessible_customer_ids
from app.models.user import Role, User
from app.services import firmware_inventory
from app.web.middleware.auth import get_current_user, require_customer_access, require_feature

# Firmware is part of the network tools (app/core/features.py).
router = APIRouter(tags=["firmware"], dependencies=[Depends(require_feature("network"))])


def _summary(devices: list[dict]) -> dict:
    counts = dict.fromkeys(firmware_inventory.STATUSES, 0)
    for d in devices:
        counts[d["status"]] = counts.get(d["status"], 0) + 1
    return counts


@router.get("/firmware/devices")
async def firmware_devices(user: User = Depends(get_current_user)):
    """Every device of every customer the caller holds: end of life first,
    then outdated, unknown and current."""
    devices = await firmware_inventory.list_devices(await get_accessible_customer_ids(user))
    return {"devices": devices, "count": len(devices), "summary": _summary(devices)}


@router.get("/firmware/devices/{customer_id}")
async def firmware_devices_for_customer(
    customer_id: str, user: User = Depends(require_customer_access(Role.technician))
):
    """One customer's devices."""
    devices = await firmware_inventory.list_devices(
        await get_accessible_customer_ids(user), customer_id
    )
    return {
        "customer_id": customer_id,
        "devices": devices,
        "count": len(devices),
        "summary": _summary(devices),
    }
