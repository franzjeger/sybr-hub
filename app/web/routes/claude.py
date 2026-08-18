"""Claude AI Console routes — chat, status, and settings."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.user import Role, User
from app.web.middleware.auth import get_current_user, require_role

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Status ─────────────────────────────────────────────────────────────────

@router.get("/claude/status")
async def claude_status(user: User = Depends(get_current_user)):
    """Check whether the Claude AI console is available and configured."""
    from app.services.claude_console import get_status
    return get_status()


# ── Send message (SSE stream) ─────────────────────────────────────────────

@router.post("/claude/message")
async def claude_message(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Send a message and receive a streaming SSE response.

    Request body::

        {
            "conversation_id": "optional-uuid",
            "message": "show me the FortiGate dashboard for Acme",
            "customer_id": "optional-customer-uuid"
        }

    Response: ``text/event-stream`` with JSON event lines.
    """
    from app.services.claude_console import stream_message

    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        raise ValidationError("Melding er påkrevd")

    conversation_id = body.get("conversation_id") or None
    customer_id = body.get("customer_id") or None
    focus = body.get("focus") or "general"

    # Build context from current state
    context = {"focus": focus}
    try:
        from app.core.credentials import load_config
        from app.core.customer import CustomerManager
        if customer_id:
            cust = CustomerManager.get_customer(customer_id)
            if cust:
                context["customer_name"] = cust.get("CustomerName", "")
                context["customer_domain"] = cust.get("PrimaryDomain", "")
                context["fortigate_host"] = cust.get("FortiGateHost", "")
        from app.services.vpn_manager import get_status as _vpn_st
        vpn = await _vpn_st()
        context["vpn_state"] = vpn.get("state", "disconnected")
        from app.services.ssh_manager import list_hosts as _ssh_hosts
        hosts = await _ssh_hosts()
        context["ssh_hosts"] = len(hosts)
    except Exception as e:
        logger.debug("Failed to build Claude message context: %s", e)

    async def _event_generator():
        async for event in stream_message(
            conversation_id=conversation_id,
            message=message,
            customer_id=customer_id,
            user_id=user.id,
            user=user,
            context=context,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Conversation management ───────────────────────────────────────────────

@router.get("/claude/conversations")
async def claude_conversations(user: User = Depends(get_current_user)):
    """List the conversations this user owns."""
    from app.services.claude_console import list_conversations
    return {"conversations": list_conversations(str(user.id))}


@router.delete("/claude/conversations/{conversation_id}")
async def claude_delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
):
    """Delete a conversation by ID."""
    from app.services.claude_console import delete_conversation

    if delete_conversation(conversation_id, str(user.id)):
        return {"ok": True}
    raise NotFoundError("Samtale ikke funnet")


# ── Settings (admin only) ─────────────────────────────────────────────────

@router.post("/claude/settings")
async def claude_save_settings(
    request: Request,
    user: User = Depends(require_role(Role.admin)),
):
    """Save Claude AI settings (API key).

    Request body::

        {"api_key": "sk-ant-..."}
    """
    from app.core.config import update_app_settings
    from app.services.claude_console import save_api_key

    body = await request.json()
    mode = body.get("mode", "api")
    model = body.get("model", "")

    if mode == "api":
        api_key = body.get("api_key", "").strip()
        if not api_key:
            raise ValidationError("API-nøkkel er påkrevd for API-modus")
        save_api_key(api_key)

    def _set(s: dict) -> None:
        s["claude_mode"] = mode
        if model:
            s["claude_model"] = model

    update_app_settings(_set)

    from app.core.activity_log import log_activity
    log_activity("claude_settings_updated", detail=f"mode={mode}", user=user.username)

    return {"ok": True}


@router.get("/claude/cli-status")
async def claude_cli_status(user: User = Depends(get_current_user)):
    """Check if Claude CLI is available for subscription mode."""
    import asyncio
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode == 0:
            version = stdout.decode().strip() or stderr.decode().strip()
            return {"available": True, "version": version}
        return {"available": False, "error": "CLI returnerte feilkode"}
    except FileNotFoundError:
        return {"available": False, "error": "claude CLI ikke funnet i PATH"}
    except asyncio.TimeoutError:
        return {"available": False, "error": "CLI svarte ikke innen 5s"}
    except Exception as e:
        return {"available": False, "error": str(e)}
