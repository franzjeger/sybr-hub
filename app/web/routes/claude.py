"""Claude AI Console routes — chat, status, and settings."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)
from app.models.ai import ActionDecision, ChatMessage, ClaudeSettings
from app.models.user import Role, User
from app.web.i18n import keyed, refusal
from app.web.middleware.auth import get_current_user, require_feature, require_module, require_role

logger = logging.getLogger(__name__)
# The whole module is the 'ai' feature (app/core/features.py); per-route
# floors below only ever raise it.
router = APIRouter(dependencies=[Depends(require_module("ai")), Depends(require_feature("ai"))])


@router.post("/claude/actions/{approval_id}")
async def claude_action(
    approval_id: str, body: ActionDecision, user: User = Depends(require_role(Role.technician))
):
    from app.services.ai_actions import decide

    return await decide(approval_id, user, approve=body.approve)


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
    body: ChatMessage,
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

    if not body.external_processing_consent:
        raise refusal(ValidationError, "err_claude_consent_required")
    message = body.message.strip()
    if not message:
        raise refusal(ValidationError, "err_claude_message_required")

    conversation_id = body.conversation_id or None
    customer_id = body.customer_id or None
    focus = body.focus or "general"
    from app.core.exceptions import ForbiddenError
    from app.core.rbac import check_customer_access, get_accessible_customer_ids

    if customer_id and not await check_customer_access(user, customer_id):
        raise refusal(ForbiddenError, "err_customer_no_access")

    # Build context from current state
    context = {"focus": focus}
    try:
        from app.core.customer import CustomerManager

        if customer_id:
            cust = CustomerManager.get_customer(customer_id)
            if cust:
                context["customer_name"] = cust.get("CustomerName", "")
                context["customer_domain"] = cust.get("PrimaryDomain", "")
                context["fortigate_host"] = cust.get("FortiGateHost", "")
        from app.core.rbac import customer_in_scope
        from app.services.vpn_manager import get_status as _vpn_st
        from app.services.vpn_manager import list_profiles as _vpn_profiles

        allowed = await get_accessible_customer_ids(user)
        # Only tunnels this user may see: otherwise the model, and through it
        # the user, learns whether another customer's tunnel is up.
        visible = None
        if allowed is not None:
            visible = {
                str(p.id)
                for p in await _vpn_profiles()
                if customer_in_scope(p.customer_id, allowed)
            }
        vpn = await _vpn_st(visible)
        context["vpn_state"] = vpn.get("state", "disconnected")
        from app.services.ssh_manager import list_hosts as _ssh_hosts

        hosts = await _ssh_hosts()
        if allowed is not None:
            hosts = [h for h in hosts if customer_in_scope(h.customer_id, allowed)]
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
    raise refusal(NotFoundError, "err_claude_conversation_not_found")


# ── Settings (admin only) ─────────────────────────────────────────────────


@router.post("/claude/settings")
async def claude_save_settings(
    body: ClaudeSettings,
    user: User = Depends(require_role(Role.admin)),
):
    """Save Claude AI settings (API key).

    Request body::

        {"api_key": "sk-ant-..."}
    """
    from app.core.config import update_app_settings
    from app.services.claude_console import save_api_key

    mode = body.mode
    model = body.model

    if mode == "api":
        api_key = body.api_key.strip()
        if not api_key:
            raise refusal(ValidationError, "err_claude_api_key_required")
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
async def claude_cli_status(request: Request, user: User = Depends(get_current_user)):
    """Check if Claude CLI is available for subscription mode."""
    import asyncio

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode == 0:
            version = stdout.decode().strip() or stderr.decode().strip()
            return {"available": True, "version": version}
        return {"available": False, **keyed("error", "err_claude_cli_exit_code", request)}
    except FileNotFoundError:
        return {"available": False, **keyed("error", "inf_claude_missing", request)}
    except TimeoutError:
        return {"available": False, **keyed("error", "err_claude_cli_timeout", request)}
    except Exception as e:
        return {"available": False, "error": str(e)}
