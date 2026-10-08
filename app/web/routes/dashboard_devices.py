"""Device status from the dashboard poller: the cached snapshot, and a poll now."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.models.user import Role, User
from app.web.middleware.auth import get_current_user, require_customer_access

router = APIRouter()


# ── REST: snapshot of current device status ──────────────────────────────────


@router.get("/dashboard/devices/{customer_id}")
async def get_dashboard_devices(
    customer_id: str,
    user: User = Depends(require_customer_access(Role.viewer)),
):
    """Return current cached device status for a customer."""
    from app.services.dashboard_poller import poller

    devices = poller.get_devices(customer_id)
    return {"devices": devices, "customer_id": customer_id}


@router.get("/dashboard/devices")
async def get_all_dashboard_devices(user: User = Depends(get_current_user)):
    """Return cached device statuses for the customers this user may see.

    The per-customer endpoint above is scoped; this "all" endpoint must be
    too, or a viewer assigned to one customer could enumerate every
    customer's devices (WAN IPs, firmware, tunnel counts) by calling it.
    """
    from app.core.rbac import get_accessible_customer_ids
    from app.services.dashboard_poller import poller

    allowed = await get_accessible_customer_ids(user)
    devices = poller.get_devices()
    if allowed is not None:
        devices = [d for d in devices if d.get("customer_id") in allowed]
    return {"devices": devices}


@router.post("/dashboard/poll/{customer_id}")
async def force_poll(
    customer_id: str,
    user: User = Depends(require_customer_access(Role.technician)),
):
    """Force an immediate poll for a customer."""
    from app.services.dashboard_poller import poller

    devices = await poller.poll_now(customer_id)
    return {"devices": devices, "customer_id": customer_id}
