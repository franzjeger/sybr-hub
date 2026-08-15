"""Live dashboard WebSocket and REST endpoints."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.core.rbac import check_customer_access
from app.models.user import Role, User
from app.web.middleware.auth import (
    get_current_user,
    get_current_user_ws,
    require_customer_access,
    require_role,
)

logger = logging.getLogger(__name__)
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


@router.post("/dashboard/interval")
async def set_poll_interval(
    request_body: dict,
    user: User = Depends(require_role(Role.admin)),
):
    """Set the polling interval in seconds (10-300)."""
    from app.services.dashboard_poller import poller
    seconds = request_body.get("interval", 60)
    poller.set_interval(int(seconds))
    return {"ok": True, "interval": poller._interval}


# ── WebSocket: real-time device updates ──────────────────────────────────────

@router.websocket("/ws/dashboard")
async def dashboard_websocket(
    websocket: WebSocket, user: User = Depends(get_current_user_ws)
):
    """WebSocket for live dashboard updates.

    Protocol:
    - Client sends JSON messages with "type" field
    - type: "subscribe" — {customer_ids: ["id1", "id2"]}
    - type: "unsubscribe" — remove subscription
    - type: "set_interval" — {interval: 30} (seconds)
    - type: "poll" — force immediate poll
    - Server sends: {type: "update", devices: [...]}

    Authenticated on the handshake. Each message is authorized separately: the
    REST endpoints above gate per customer and per role, and this socket
    reaches the same poller, so it has to apply the same rules — otherwise a
    viewer scoped to one customer could stream every customer's devices by
    asking for them here.
    """

    await websocket.accept()

    ws_id = str(uuid.uuid4())
    from app.services.dashboard_poller import poller

    async def send_updates(devices: list[dict]) -> None:
        await websocket.send_json({"type": "update", "devices": devices})

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "msg": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "subscribe":
                requested = msg.get("customer_ids", [])
                customer_ids = [
                    cid for cid in requested if await check_customer_access(user, cid)
                ]
                if len(customer_ids) != len(requested):
                    logger.info(
                        "Dashboard WS: dropped %d customer(s) from subscribe for user=%s",
                        len(requested) - len(customer_ids), user.username,
                    )
                poller.subscribe(ws_id, customer_ids, send_updates)
                # Send initial data
                devices = []
                for cid in customer_ids:
                    devices.extend(poller.get_devices(cid))
                await websocket.send_json({"type": "update", "devices": devices})

            elif msg_type == "unsubscribe":
                poller.unsubscribe(ws_id)
                await websocket.send_json({"type": "unsubscribed"})

            elif msg_type == "set_interval":
                # The poll interval is global, so it matches the admin floor on
                # the REST twin rather than a per-customer check.
                if user.role < Role.admin:
                    await websocket.send_json(
                        {"type": "error", "msg": "Krever admin-rolle"}
                    )
                    continue
                interval = msg.get("interval", 60)
                poller.set_interval(int(interval))
                await websocket.send_json({"type": "interval_set", "interval": poller._interval})

            elif msg_type == "poll":
                customer_id = msg.get("customer_id")
                if user.role < Role.technician or not await check_customer_access(
                    user, customer_id
                ):
                    await websocket.send_json(
                        {"type": "error", "msg": "Ingen tilgang til denne kunden"}
                    )
                    continue
                devices = await poller.poll_now(customer_id)
                await websocket.send_json({"type": "update", "devices": devices})

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("Dashboard WS error: %s", e)
    finally:
        poller.unsubscribe(ws_id)
