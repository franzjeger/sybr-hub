"""Claude AI Console service — streaming chat with tool calling.

Provides an async generator that yields SSE-compatible events while
interacting with the Anthropic Messages API.  Tool schemas map to
the SSH, VPN, FortiGate, and UniFi service layers so the model can
take actions on behalf of the technician.

The ``anthropic`` SDK is imported conditionally so the rest of the
application works even when it is not installed.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncGenerator, Optional

if TYPE_CHECKING:
    from app.models.user import User

logger = logging.getLogger(__name__)

# ── Conditional SDK import ──────────────────────────────────────────────────

try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    anthropic = None  # type: ignore[assignment]
    _HAS_ANTHROPIC = False

# ── Constants ───────────────────────────────────────────────────────────────

DEFAULT_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096


def _get_mode() -> str:
    """Get configured mode: 'api' or 'cli'."""
    try:
        from app.core.config import load_app_settings
        return load_app_settings().get("claude_mode", "api")
    except Exception:
        return "api"


def _get_model() -> str:
    """Get configured model."""
    try:
        from app.core.config import load_app_settings
        return load_app_settings().get("claude_model", DEFAULT_MODEL)
    except Exception:
        return DEFAULT_MODEL

BASE_SYSTEM_PROMPT = """\
Du er en AI-assistent for MSP-teknikere hos SYBR AS som bruker MSP Toolkit V2.
Du snakker norsk med teknisk presisjon. Du kan utføre handlinger på vegne av teknikeren.

## Verktøy du har tilgang til

### SSH
- `ssh_list_hosts` — list alle registrerte vertsmaskiner med status
- `ssh_list_keys` — list SSH-nøkler (fingerprint, type)
- `ssh_execute` — kjør kommandoer på en vert (krever host_id + kommando)
- `ssh_test_connection` — test om en vert er tilgjengelig

### VPN
- `vpn_status` — vis nåværende VPN-tilkobling
- `vpn_list_profiles` — list alle VPN-profiler (FortiGate IPsec, WireGuard, OpenVPN, Azure)
- `vpn_connect` — koble til en VPN-profil
- `vpn_disconnect` — koble fra aktiv VPN

### FortiGate
- `fortigate_dashboard` — hent live-data fra en kundes FortiGate (CPU, minne, sesjoner, VPN-tunneler, interfaces, regler)
- `fortigate_compliance` — kjør CIS compliance-sjekk mot en FortiGate
- `fortigate_backup` — ta backup av FortiGate-konfigurasjon

### UniFi
- `unifi_devices` — list UniFi-enheter for en kunde
- `unifi_sites` — hent alle UniFi-siter fra Site Manager API

### Kunder
- `list_customers` — list alle kunder med status
- `customer_status` — hent detaljert status for aktiv kunde

## Regler
- Bekreft alltid destruktive handlinger (reboot, wipe, slett) før du utfører dem
- Formater teknisk data med tabeller eller lister
- Hvis et verktøy feiler, forklar feilen og foreslå løsning
- Vær proaktiv — foreslå relevante handlinger basert på konteksten
"""


def _build_system_prompt(context: Optional[dict] = None) -> str:
    """Build system prompt with current context."""
    prompt = BASE_SYSTEM_PROMPT

    if context:
        prompt += "\n## Nåværende kontekst\n"
        if context.get("customer_name"):
            prompt += f"- Aktiv kunde: **{context['customer_name']}**\n"
        if context.get("customer_domain"):
            prompt += f"- Domene: {context['customer_domain']}\n"
        if context.get("fortigate_host"):
            prompt += f"- FortiGate: {context['fortigate_host']}\n"
        if context.get("vpn_state"):
            prompt += f"- VPN: {context['vpn_state']}\n"
        if context.get("ssh_hosts"):
            prompt += f"- SSH-verter: {context['ssh_hosts']} registrert\n"
        if context.get("focus"):
            focus_map = {
                "general": "Generell MSP-assistent — hjelp med hva som helst",
                "network": "Nettverksadministrasjon — FortiGate, UniFi, VPN, SSH",
                "security": "Sikkerhetsaudit — sjekk konfigurasjoner, CIS compliance, MFA, policies",
                "troubleshoot": "Feilsøking — diagnostiser problemer, sjekk tilkoblinger, les logger",
                "provision": "Provisjonering — sett opp nye kunder, generer konfigurasjoner",
            }
            prompt += f"\n## Fokus\n{focus_map.get(context['focus'], context['focus'])}\n"

    return prompt

# ── Tool definitions (Anthropic tool-use schema) ───────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "name": "ssh_list_hosts",
        "description": "List all configured SSH hosts.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "ssh_list_keys",
        "description": "List all stored SSH keys (public metadata only).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "ssh_execute",
        "description": "Execute a shell command on a remote SSH host.  Returns stdout, stderr, and exit code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host_id": {"type": "string", "description": "UUID of the target SSH host."},
                "command": {"type": "string", "description": "Shell command to run."},
            },
            "required": ["host_id", "command"],
        },
    },
    {
        "name": "ssh_test_connection",
        "description": "Test SSH connectivity to a host.  Returns reachability status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host_id": {"type": "string", "description": "UUID of the SSH host to test."},
            },
            "required": ["host_id"],
        },
    },
    {
        "name": "vpn_status",
        "description": "Get the current VPN connection state (connected/disconnected/error).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "vpn_list_profiles",
        "description": "List all configured VPN profiles.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "vpn_connect",
        "description": "Connect to a VPN using the specified profile.",
        "input_schema": {
            "type": "object",
            "properties": {
                "profile_id": {"type": "string", "description": "UUID of the VPN profile to connect."},
            },
            "required": ["profile_id"],
        },
    },
    {
        "name": "vpn_disconnect",
        "description": "Disconnect the active VPN connection.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "fortigate_dashboard",
        "description": "Fetch live FortiGate dashboard stats (CPU, memory, sessions, VPN tunnels) for a customer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer UUID whose FortiGate to query."},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "unifi_devices",
        "description": "List UniFi devices with stats (model, firmware, clients, status) for a customer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer UUID whose UniFi controller to query."},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "fortigate_compliance",
        "description": "Run CIS compliance check against a customer's FortiGate. Returns pass/fail findings with score.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer UUID."},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "fortigate_backup",
        "description": "Trigger a config backup of a customer's FortiGate firewall.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer UUID."},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "unifi_sites",
        "description": "List all UniFi sites from Site Manager API with device counts, client counts, and status.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_customers",
        "description": "List all customers with their IDs, names, and domains.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "customer_status",
        "description": "Get detailed status for the currently active customer including config, expiry warnings, and tags.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

# ── In-memory conversation store ───────────────────────────────────────────

# {conversation_id: {"owner_user_id": str, "messages": [...], "created_at": str,
#                    "title": str}}
#
# One process serves every technician, so this dict is shared. The owner is
# recorded because nothing else here can tell two users apart: a conversation
# holds what someone typed into the console — customer names, hostnames,
# whatever they pasted in — and the store had no notion of whose it was.
_conversations: dict[str, dict[str, Any]] = {}


def _owns(conv: dict[str, Any], user_id: str | None) -> bool:
    """Whether *user_id* may see this conversation.

    A conversation with no recorded owner belongs to nobody. The store is
    in-memory and does not survive a restart, so that case only arises for
    entries written by code that predates this check.
    """
    owner = conv.get("owner_user_id")
    return bool(owner) and bool(user_id) and str(owner) == str(user_id)


# ── Public helpers ─────────────────────────────────────────────────────────

def is_available() -> bool:
    """Return True if Claude is usable (API key or CLI available)."""
    mode = _get_mode()
    if mode == "cli":
        import shutil
        return shutil.which("claude") is not None
    return _HAS_ANTHROPIC and bool(_get_api_key())


def get_status() -> dict[str, Any]:
    """Return availability status and model info."""
    mode = _get_mode()
    model = _get_model()
    api_key = _get_api_key()

    if mode == "cli":
        import shutil
        cli_path = shutil.which("claude")
        return {
            "available": cli_path is not None,
            "mode": "cli",
            "cli_found": cli_path is not None,
            "model": model,
        }

    return {
        "available": _HAS_ANTHROPIC and bool(api_key),
        "mode": "api",
        "sdk_installed": _HAS_ANTHROPIC,
        "api_key_configured": bool(api_key),
        "model": model,
    }


def list_conversations(user_id: str | None = None) -> list[dict[str, Any]]:
    """Return metadata for the conversations *user_id* owns.

    This used to return every conversation in the process to any authenticated
    caller, so one technician's console history — titled with the first eighty
    characters of what they typed — was listed to all the others.
    """
    result = []
    for cid, conv in _conversations.items():
        if not _owns(conv, user_id):
            continue
        result.append({
            "conversation_id": cid,
            "title": conv.get("title", "Untitled"),
            "created_at": conv.get("created_at", ""),
            "message_count": len(conv.get("messages", [])),
        })
    # Most recent first
    result.sort(key=lambda c: c["created_at"], reverse=True)
    return result


def delete_conversation(conversation_id: str, user_id: str | None = None) -> bool:
    """Delete one of *user_id*'s conversations. True if it existed and was theirs.

    Returning False for someone else's id rather than raising keeps the route's
    404 from distinguishing "no such conversation" from "not yours", which
    would otherwise let a caller enumerate the ids in use.
    """
    conv = _conversations.get(conversation_id)
    if conv is None or not _owns(conv, user_id):
        return False
    del _conversations[conversation_id]
    return True


def save_api_key(api_key: str) -> None:
    """Persist the Anthropic API key in app settings (encrypted on disk)."""
    from app.core.config import update_app_settings
    update_app_settings(lambda s: s.__setitem__("claude_api_key", api_key))


# ── Streaming chat ─────────────────────────────────────────────────────────

async def stream_message(
    conversation_id: Optional[str],
    message: str,
    customer_id: Optional[str] = None,
    user_id: Optional[str] = None,
    user: User | None = None,
    context: Optional[dict] = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Send a user message and yield SSE-compatible event dicts.

    ``user`` is the authenticated caller. It is required for any tool that
    touches a specific customer or host: the tool layer enforces the same
    per-customer scope the HTTP routes do (see ``_enforce_tool_scope``), and
    it can only do that if it knows who is asking.

    Event types:
        text          — partial assistant text (delta)
        tool_use      — model wants to call a tool
        tool_result   — result of executing the tool
        done          — stream complete
        error         — something went wrong
    """
    mode = _get_mode()

    if mode == "cli":
        # CLI mode spawns the `claude` CLI with Bash(*) on the hub host — the
        # same power the local terminal guards behind admin (see
        # terminal.py). A technician must not reach a host shell through the
        # console, so gate it the same way rather than leaving the console's
        # technician floor as an escalation path.
        from app.models.user import Role
        if user is None or user.role < Role.admin:
            yield {"type": "error", "error": "CLI-modus krever admin-rolle."}
            return
        async for event in _stream_via_cli(conversation_id, message, context, user_id):
            yield event
        return

    if not _HAS_ANTHROPIC:
        yield {"type": "error", "error": "Anthropic SDK er ikke installert. Installer med: pip install anthropic"}
        return

    api_key = _get_api_key()
    if not api_key:
        yield {"type": "error", "error": "API-nøkkel ikke konfigurert. Gå til Integrasjoner → Claude AI."}
        return

    # Resolve or create conversation
    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    existing = _conversations.get(conversation_id)
    if existing is None:
        _conversations[conversation_id] = {
            "owner_user_id": str(user_id) if user_id else "",
            "messages": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "title": message[:80] if message else "New conversation",
        }
    elif not _owns(existing, user_id):
        # Continuing someone else's conversation would both disclose its
        # history to the model's context and append to it. The id is supplied
        # by the client, so this is reachable by anyone who has one.
        yield {"type": "error", "error": "Samtale ikke funnet"}
        return

    conv = _conversations[conversation_id]

    # Append user message
    conv["messages"].append({"role": "user", "content": message})

    # Yield conversation_id so the client knows which conversation this is
    yield {"type": "conversation_id", "conversation_id": conversation_id}

    # Build the Anthropic client
    client = anthropic.AsyncAnthropic(api_key=api_key)

    try:
        # We may loop several times if the model makes tool calls
        while True:
            async with client.messages.stream(
                model=DEFAULT_MODEL,
                max_tokens=MAX_TOKENS,
                system=_build_system_prompt(context),
                messages=conv["messages"],
                tools=TOOLS,
            ) as stream:
                assistant_content: list[dict[str, Any]] = []
                full_text = ""

                async for event in stream:
                    # Text delta
                    if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                        full_text += event.delta.text
                        yield {"type": "text", "text": event.delta.text}

                    # Content block start — detect tool_use blocks
                    elif event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            yield {
                                "type": "tool_use",
                                "tool_name": event.content_block.name,
                                "tool_use_id": event.content_block.id,
                            }

                # Get the final message for stop_reason and full content
                final = await stream.get_final_message()

            # Store the assistant turn
            assistant_content = [_block_to_dict(b) for b in final.content]
            conv["messages"].append({"role": "assistant", "content": assistant_content})

            # If the model didn't request tool use, we're done
            if final.stop_reason != "tool_use":
                break

            # Dispatch tool calls and build tool results
            tool_results: list[dict[str, Any]] = []
            for block in final.content:
                if getattr(block, "type", None) != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_use_id = block.id

                logger.info("Tool call: %s(%s)", tool_name, json.dumps(tool_input)[:200])

                try:
                    result = await _dispatch_tool(tool_name, tool_input, customer_id, user)
                    result_str = json.dumps(result, default=str)
                except Exception as exc:
                    logger.exception("Tool %s failed", tool_name)
                    result_str = json.dumps({"error": str(exc)})

                yield {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "tool_name": tool_name,
                    "result": result_str,
                }

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result_str,
                })

            # Append tool results and loop for the model's next turn
            conv["messages"].append({"role": "user", "content": tool_results})

    except anthropic.APIError as exc:
        logger.exception("Anthropic API error")
        yield {"type": "error", "error": f"API error: {exc.message}"}
        return
    except Exception as exc:
        logger.exception("Unexpected error in Claude console stream")
        yield {"type": "error", "error": str(exc)}
        return

    yield {"type": "done"}


# ── Authorization: keep console tools inside the caller's customer scope ─────
#
# The HTTP routes gate every host- and customer-scoped action behind
# require_host_access / require_customer_access. The console reaches the same
# service functions, so without the equivalent check a customer-scoped
# technician could read or act on any customer's devices simply by naming its
# id in a tool call. These sets name the tools whose inputs carry such an id;
# _enforce_tool_scope refuses the call before dispatch when the id is out of
# scope, and the list tools below filter their results the same way.

_HOST_SCOPED_TOOLS = {"ssh_execute", "ssh_test_connection"}
_CUSTOMER_SCOPED_TOOLS = {
    "fortigate_dashboard",
    "fortigate_compliance",
    "fortigate_backup",
    "unifi_devices",
}

_SCOPE_DENIED = {
    "error": "Du har ikke tilgang til denne kunden eller hosten.",
    "forbidden": True,
}


async def _may_see_host(user: User | None, host) -> bool:
    """Whether *user* may act on *host* — mirrors the SSH routes' rule."""
    from app.core.rbac import check_customer_access, get_accessible_customer_ids

    if user is None or host is None:
        return False
    if host.customer_id:
        return await check_customer_access(user, host.customer_id)
    # A host with no customer is estate-wide infrastructure: only an
    # unrestricted account may touch it.
    return await get_accessible_customer_ids(user) is None


async def _enforce_tool_scope(
    user: User | None,
    name: str,
    params: dict[str, Any],
    customer_id: str | None,
) -> dict | None:
    """Return an error dict if this tool call escapes the caller's scope.

    Fails closed: a host- or customer-scoped tool invoked without an
    authenticated user, or naming an id the user cannot reach, is refused
    before the underlying service function runs.
    """
    if name in _HOST_SCOPED_TOOLS:
        from app.services.ssh_manager import get_host
        host = await get_host((params.get("host_id") or "").strip())
        if not await _may_see_host(user, host):
            logger.info(
                "console 403 host-access: user=%s tool=%s host=%s",
                getattr(user, "username", "?"), name, params.get("host_id"),
            )
            return _SCOPE_DENIED
    if name in _CUSTOMER_SCOPED_TOOLS:
        from app.core.rbac import check_customer_access
        cid = (params.get("customer_id") or customer_id or "").strip()
        if user is None or not cid or not await check_customer_access(user, cid):
            logger.info(
                "console 403 customer-access: user=%s tool=%s customer=%s",
                getattr(user, "username", "?"), name, cid,
            )
            return _SCOPE_DENIED
    return None


# ── Tool dispatch ──────────────────────────────────────────────────────────

async def _dispatch_tool(
    name: str,
    params: dict[str, Any],
    customer_id: Optional[str] = None,
    user: User | None = None,
) -> Any:
    """Route a tool call to the appropriate service function.

    ``user`` is the authenticated caller. Host- and customer-scoped tools are
    refused here when the requested id is outside the caller's access, and the
    list tools filter their output to what the caller may see — so the console
    cannot reach across customers the way the HTTP routes already prevent.
    """
    scope_error = await _enforce_tool_scope(user, name, params, customer_id)
    if scope_error is not None:
        return scope_error

    # -- SSH tools --
    if name == "ssh_list_hosts":
        from app.core.rbac import get_accessible_customer_ids
        from app.services.ssh_manager import list_hosts
        allowed = await get_accessible_customer_ids(user) if user else set()
        hosts = await list_hosts()
        if allowed is not None:
            # Restricted account: only hosts belonging to a customer it may
            # access. A host with no customer is estate-wide, so it stays
            # hidden from restricted accounts (matches _may_see_host).
            hosts = [h for h in hosts if h.customer_id and h.customer_id in allowed]
        return [
            {
                "id": h.id, "label": h.label, "hostname": h.hostname,
                "port": h.port, "device_type": h.device_type.value,
                "is_reachable": h.is_reachable,
            }
            for h in hosts
        ]

    if name == "ssh_list_keys":
        from app.services.ssh_manager import list_keys
        keys = await list_keys()
        return [
            {
                "id": k.id, "name": k.name, "key_type": k.key_type.value,
                "fingerprint": k.fingerprint,
            }
            for k in keys
        ]

    if name == "ssh_execute":
        from app.services.ssh_manager import batch_exec
        results = await batch_exec([params["host_id"]], params["command"])
        r = results[0]
        return {
            "host_id": r.host_id, "host_label": r.host_label,
            "exit_code": r.exit_code, "stdout": r.stdout,
            "stderr": r.stderr, "error": r.error,
        }

    if name == "ssh_test_connection":
        from app.services.ssh_manager import health_check
        results = await health_check([params["host_id"]])
        return results[0] if results else {"error": "No result"}

    # -- VPN tools --
    if name == "vpn_status":
        from app.services.vpn_manager import get_status
        return await get_status()

    if name == "vpn_list_profiles":
        from app.services.vpn_manager import list_profiles
        profiles = await list_profiles()
        return [
            {
                "id": p.id, "name": p.name, "protocol": p.protocol.value,
                "customer_id": p.customer_id,
            }
            for p in profiles
        ]

    if name == "vpn_connect":
        from app.services.vpn_manager import connect
        return await connect(params["profile_id"])

    if name == "vpn_disconnect":
        from app.services.vpn_manager import disconnect
        return await disconnect()

    # -- FortiGate tools --
    if name == "fortigate_dashboard":
        cid = params.get("customer_id") or customer_id
        if not cid:
            return {"error": "customer_id is required"}

        from app.core.credentials import get_secret
        from app.core.customer import CustomerManager
        from app.services.fortigate_api import get_dashboard

        config = CustomerManager.get_customer(cid)
        if not config:
            return {"error": f"Customer {cid} not found"}

        token = get_secret(cid, "fortigate_api_token")
        if not token:
            return {"error": "FortiGate API token not configured for this customer"}

        return await get_dashboard(config, token)

    if name == "fortigate_compliance":
        cid = params.get("customer_id") or customer_id
        if not cid:
            return {"error": "customer_id kreves"}
        from app.core.credentials import get_secret
        from app.core.customer import CustomerManager
        from app.services.fortigate_api import check_compliance
        config = CustomerManager.get_customer(cid)
        if not config:
            return {"error": f"Kunde {cid} ikke funnet"}
        token = get_secret(cid, "fortigate_api_token")
        if not token:
            return {"error": "FortiGate API-token ikke konfigurert"}
        return await check_compliance(config, token)

    if name == "fortigate_backup":
        cid = params.get("customer_id") or customer_id
        if not cid:
            return {"error": "customer_id kreves"}
        from app.core.credentials import get_secret
        from app.core.customer import CustomerManager
        from app.services.fortigate_api import backup_config
        config = CustomerManager.get_customer(cid)
        if not config:
            return {"error": f"Kunde {cid} ikke funnet"}
        token = get_secret(cid, "fortigate_api_token")
        if not token:
            return {"error": "FortiGate API-token ikke konfigurert"}
        return await backup_config(config, token)

    # -- UniFi tools --
    if name == "unifi_devices":
        cid = params.get("customer_id") or customer_id
        if not cid:
            return {"error": "customer_id kreves"}
        from app.modules.api_result import read_error, read_failed
        from app.services.unifi_api import get_enhanced_device_stats
        devices = await get_enhanced_device_stats(cid)
        # An ApiList serialises to [] over the tool boundary, dropping .error —
        # so a refused read would reach the model as "0 devices". Surface it.
        if read_failed(devices):
            return {"error": read_error(devices), "unavailable": True}
        return devices

    if name == "unifi_sites":
        from app.services.unifi_api import site_manager_list_sites
        return await site_manager_list_sites()

    # -- Customer tools --
    if name == "list_customers":
        from app.core.customer import CustomerManager
        from app.core.rbac import filter_customers, get_accessible_customer_ids
        allowed = await get_accessible_customer_ids(user) if user else set()
        customers = filter_customers(CustomerManager.list_customers(), allowed)
        return [{"id": c.get("_id", ""), "name": c.get("CustomerName", ""), "domain": c.get("PrimaryDomain", "")} for c in customers[:50]]

    if name == "customer_status":
        from app.core.credentials import config_exists, load_config
        if not config_exists():
            return {"error": "Ingen aktiv kunde"}
        cfg = load_config()
        return {
            "name": cfg.get("CustomerName", ""),
            "domain": cfg.get("PrimaryDomain", ""),
            "tenant_id": cfg.get("TenantId", ""),
            "fortigate": cfg.get("FortiGateHost", ""),
            "unifi": cfg.get("UniFiHost", ""),
        }

    return {"error": f"Ukjent verktøy: {name}"}


# ── Internal helpers ───────────────────────────────────────────────────────

def _get_api_key() -> Optional[str]:
    """Load the Anthropic API key from app settings."""
    try:
        from app.core.config import load_app_settings
        settings = load_app_settings()
        return settings.get("claude_api_key") or None
    except Exception:
        return None


_active_cli_proc = None  # Track active CLI process

async def _stream_via_cli(
    conversation_id: Optional[str],
    message: str,
    context: Optional[dict] = None,
    user_id: Optional[str] = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream a response using the Claude CLI (subscription mode)."""
    global _active_cli_proc
    import asyncio

    # Kill previous CLI process if still running
    if _active_cli_proc and _active_cli_proc.returncode is None:
        try:
            _active_cli_proc.terminate()
        except Exception:
            pass

    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    yield {"type": "conversation_id", "conversation_id": conversation_id}

    model = _get_model()

    # CLI mode: concise system prompt with full tool access
    cli_context = (
        "Du er SYBR MSP Toolkit AI-assistent. Svar kort på norsk. "
        "Du har full tilgang til alle verktøy. "
        "REGEL: Aldri gjør destruktive endringer (slett, reboot, wipe) uten at brukeren eksplisitt ber om det. Lesing og sjekking er alltid OK. "
        "Bruk /tmp/msp-api ENDPOINT for MSP-data. Eksempel: /tmp/msp-api fortigate/all"
    )
    if context and context.get("customer_name"):
        cli_context += f" Kunde: {context['customer_name']}."

    # Generate a short-lived token for API access
    api_token = ""
    try:
        from app.core.auth import create_access_token, get_user_by_id
        if user_id:
            user = await get_user_by_id(user_id)
            if user:
                api_token = await create_access_token(user)
    except Exception:
        pass

    # Write a temporary helper script so Claude can call our API simply
    import stat
    import tempfile
    helper_path = "/tmp/msp-api"
    with open(helper_path, "w") as f:
        f.write(f'#!/bin/bash\ncurl -s -H "Authorization: Bearer {api_token}" "http://localhost:8099/api/$1"\n')
    import os
    os.chmod(helper_path, stat.S_IRWXU)

    # Helper script path already referenced in system prompt

    full_message = message

    try:
        _active_cli_proc = proc = await asyncio.create_subprocess_exec(
            "claude", "-p", full_message,
            "--model", model,
            "--output-format", "stream-json",
            "--verbose",
            "--system-prompt", cli_context,
            "--allowedTools", "Bash(*)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        seen_text = set()
        async for line in proc.stdout:
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                msg_type = data.get("type", "")

                # Skip init/system/rate_limit events
                if msg_type in ("system", "rate_limit_event"):
                    continue

                # Assistant message with content blocks
                if msg_type == "assistant":
                    msg = data.get("message", {})
                    for block in msg.get("content", []):
                        if block.get("type") == "text" and block.get("text"):
                            text = block["text"]
                            if text not in seen_text:
                                seen_text.add(text)
                                yield {"type": "text", "text": text}

                # Final result — stop streaming after this
                elif msg_type == "result":
                    text = data.get("result", "")
                    if text and text not in seen_text:
                        yield {"type": "text", "text": text}
                    break  # Done — don't read more output

            except json.JSONDecodeError:
                if line and not line.startswith("{"):
                    yield {"type": "text", "text": line + "\n"}

        await proc.wait()

        if proc.returncode != 0:
            stderr = await proc.stderr.read()
            err = stderr.decode("utf-8", errors="replace").strip()
            if err:
                yield {"type": "error", "error": f"Claude CLI feil: {err}"}

    except FileNotFoundError:
        yield {"type": "error", "error": "Claude CLI ikke funnet. Installer med: npm install -g @anthropic-ai/claude-code"}
    except Exception as e:
        yield {"type": "error", "error": str(e)}

    yield {"type": "done"}


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Convert an Anthropic content block to a JSON-serialisable dict."""
    if hasattr(block, "text"):
        return {"type": "text", "text": block.text}
    if hasattr(block, "name") and hasattr(block, "input"):
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    # Fallback
    return {"type": str(getattr(block, "type", "unknown"))}
