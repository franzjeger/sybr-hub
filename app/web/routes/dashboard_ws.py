"""Live dashboard WebSocket and REST endpoints."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.models.user import Role, User
from app.web.middleware.auth import (
    get_current_user,
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
    """Return all cached device statuses."""
    from app.services.dashboard_poller import poller
    devices = poller.get_devices()
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
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket for live dashboard updates.

    Protocol:
    - Client sends JSON messages with "type" field
    - type: "subscribe" — {customer_ids: ["id1", "id2"]}
    - type: "unsubscribe" — remove subscription
    - type: "set_interval" — {interval: 30} (seconds)
    - type: "poll" — force immediate poll
    - Server sends: {type: "update", devices: [...]}

    Authentication: JWT via cookie, or first message {"type": "auth", "token": "..."}.
    Falls back to query param ?token=... for backwards compatibility.
    """
    from app.core.auth import decode_token, get_user_by_id, get_user_count

    user = None

    # Strategy 1: cookie (preferred — not logged in URLs)
    token = websocket.cookies.get("access_token", "")

    # Strategy 2: query param (backwards compat)
    if not token:
        token = websocket.query_params.get("token", "")

    if token:
        payload = await decode_token(token)
        if payload and payload.token_type == "access":
            user = await get_user_by_id(payload.sub)
            if user and not user.is_active:
                await websocket.close(code=4003, reason="User disabled")
                return

    # First-run bypass: no users exist
    if not user and await get_user_count() == 0:
        await websocket.accept()
    elif not user:
        # Accept and wait for auth message
        await websocket.accept()
        try:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "auth" and msg.get("token"):
                payload = await decode_token(msg["token"])
                if payload and payload.token_type == "access":
                    user = await get_user_by_id(payload.sub)
            if not user or not user.is_active:
                await websocket.send_json({"type": "error", "msg": "Authentication failed"})
                await websocket.close(code=4001, reason="Token required")
                return
        except Exception as e:
            logger.debug("Dashboard WS auth failed: %s", e)
            await websocket.close(code=4001, reason="Token required")
            return
    else:
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
                customer_ids = msg.get("customer_ids", [])
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
                interval = msg.get("interval", 60)
                poller.set_interval(int(interval))
                await websocket.send_json({"type": "interval_set", "interval": poller._interval})

            elif msg_type == "poll":
                customer_id = msg.get("customer_id")
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
