"""Single-use, actor-bound approvals for concrete AI actions."""

import copy
import json
import re
import secrets
import time
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError

WRITE_TOOLS = frozenset({"ssh_execute", "vpn_connect", "vpn_disconnect", "fortigate_backup"})
_pending: dict[str, dict[str, Any]] = {}
_SECRET_KEYS = re.compile(r"password|secret|token|private.?key|authorization|api.?key|config", re.I)


def expire() -> None:
    for key, action in list(_pending.items()):
        if action["expires"] < time.monotonic():
            del _pending[key]


def propose(user_id: str, name: str, params: dict, customer_id: str | None) -> dict:
    expire()
    if not isinstance(params, dict) or len(json.dumps(params)) > 16384:
        raise ConflictError("AI action parameters are too large")
    if name == "ssh_execute" and (
        not isinstance(params.get("command"), str) or len(params["command"]) > 8192
    ):
        raise ConflictError("SSH command is invalid or too large")
    if len(_pending) >= 200 or sum(a["user_id"] == user_id for a in _pending.values()) >= 20:
        raise ConflictError("Too many pending AI approvals; approve, reject or wait ten minutes.")
    token = secrets.token_urlsafe(24)
    _pending[token] = {
        "user_id": user_id,
        "name": name,
        "params": copy.deepcopy(params),
        "customer_id": customer_id,
        "expires": time.monotonic() + 600,
    }
    return {
        "approval_required": True,
        "approval_id": token,
        "tool_name": name,
        "parameters": params,
        "customer_id": customer_id,
        "expires_in": 600,
    }


async def decide(token: str, user, *, approve: bool) -> dict:
    from app.core.capabilities import require_write
    from app.services.claude_console import _dispatch_tool

    expire()
    action = _pending.get(token)
    if action is None or action["user_id"] != str(user.id):
        raise NotFoundError("Approval not found or expired")
    require_write(user)
    # Consume before awaiting: repeated submissions cannot repeat an action.
    del _pending[token]
    if not approve:
        return {"ok": True, "rejected": True}
    result = await _dispatch_tool(
        action["name"], action["params"], action["customer_id"], user, approved=True
    )
    return {"ok": True, "result": json.loads(provider_result(result))}


def provider_result(result: Any) -> str:
    """Bound payloads and remove structured secrets before sending externally.

    Free text redaction is heuristic. It does not establish that arbitrary
    command output is non-sensitive; the operator must approve that disclosure.
    """
    from app.core.redact import redact

    def clean(value):
        if isinstance(value, dict):
            return {
                str(k): "[REDACTED]" if _SECRET_KEYS.search(str(k)) else clean(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [clean(v) for v in value[:200]]
        if isinstance(value, str):
            return redact(value[:16000])
        return value

    rendered = json.dumps(clean(result), default=str)
    if len(rendered) > 32000:
        rendered = json.dumps({"truncated": True, "preview": rendered[:16000]})
    return rendered
