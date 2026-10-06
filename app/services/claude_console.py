"""Claude AI Console service — streaming chat with tool calling.

Provides an async generator that yields SSE-compatible events while
interacting with the Anthropic Messages API.  Tool schemas map to
the SSH, VPN, FortiGate, and UniFi service layers so the model can
take actions on behalf of the technician.

The ``anthropic`` SDK is imported conditionally so the rest of the
application works even when it is not installed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

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

DEFAULT_MODEL = "claude-opus-5"
# Adaptive thinking is on by default on this model and its tokens count against
# max_tokens, so the previous 4096 would have truncated ordinary answers
# mid-sentence. This is a ceiling, not a spend: only what is generated is
# billed. The console streams, so a large ceiling costs no request timeout.
MAX_TOKENS = 16000


def _get_mode() -> str:
    """Get configured mode: 'api' or 'cli'."""
    try:
        from app.core.config import load_app_settings

        return load_app_settings().get("claude_mode", "api")
    except Exception:
        logger.debug("Could not read claude_mode; using the default", exc_info=True)
        return "api"


def _get_model() -> str:
    """Get configured model."""
    try:
        from app.core.config import load_app_settings

        return load_app_settings().get("claude_model", DEFAULT_MODEL)
    except Exception:
        logger.debug("Could not read claude_model; using the default", exc_info=True)
        return DEFAULT_MODEL


BASE_SYSTEM_PROMPT = """\
Du er en AI-assistent for MSP-teknikere hos SYBR AS som bruker Sybr HUB.
Du snakker norsk med teknisk presisjon. Du kan utføre handlinger på vegne av teknikeren.

## Verktøy du har tilgang til

### SSH
- `ssh_list_hosts` — list alle registrerte vertsmaskiner med status
- `ssh_list_keys` — list SSH-nøkler (fingerprint, type)
- `ssh_execute` — kjør kommandoer på en vert (krever host_id + kommando)
- `ssh_test_connection` — test om en vert er tilgjengelig

### VPN
- `vpn_status` — vis nåværende VPN-tilkobling
- `vpn_list_profiles` — list VPN-profilene du har tilgang til (FortiGate IPsec, WireGuard, OpenVPN, Azure)
- `vpn_connect` — koble til en VPN-profil
- `vpn_disconnect` — koble fra aktiv VPN

### FortiGate
- `fortigate_dashboard` — hent live-data fra en kundes FortiGate (CPU, minne, sesjoner, VPN-tunneler, interfaces, regler)
- `fortigate_compliance` — kjør CIS compliance-sjekk mot en FortiGate
- `fortigate_backup` — ta backup av FortiGate-konfigurasjon

### UniFi
- `unifi_devices` — list UniFi-enheter for en kunde
- `unifi_sites` — hent alle UniFi-siter fra Site Manager API (bare for kontoer med tilgang til alle kunder)

### Kunder
- `list_customers` — list alle kunder med status
- `customer_status` — hent detaljert status for kunden samtalen gjelder

## Regler
- Bekreft alltid destruktive handlinger (reboot, wipe, slett) før du utfører dem
- Formater teknisk data med tabeller eller lister
- Hvis et verktøy feiler, forklar feilen og foreslå løsning
- Vær proaktiv — foreslå relevante handlinger basert på konteksten
"""


def _build_system_prompt(context: dict | None = None) -> str:
    """Build system prompt with current context."""
    prompt = BASE_SYSTEM_PROMPT

    if context:
        prompt += "\n## Nåværende kontekst\n"
        if context.get("customer_name"):
            prompt += f"- Valgt kunde: **{context['customer_name']}**\n"
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
        "description": "List the VPN profiles the technician may use.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "vpn_connect",
        "description": "Connect to a VPN using the specified profile.",
        "input_schema": {
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "string",
                    "description": "UUID of the VPN profile to connect.",
                },
            },
            "required": ["profile_id"],
        },
    },
    {
        "name": "vpn_disconnect",
        "description": (
            "Disconnect a VPN connection. Without profile_id, the first active "
            "connection on a profile the technician may use is closed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "string",
                    "description": "UUID of the VPN profile to disconnect (optional).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "fortigate_dashboard",
        "description": "Fetch live FortiGate dashboard stats (CPU, memory, sessions, VPN tunnels) for a customer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Customer UUID whose FortiGate to query.",
                },
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
                "customer_id": {
                    "type": "string",
                    "description": "Customer UUID whose UniFi controller to query.",
                },
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
        "description": (
            "List all UniFi sites from Site Manager API with device counts, client counts, "
            "and status. MSP-wide data: only available to accounts with access to every customer."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_customers",
        "description": "List all customers with their IDs, names, and domains.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "customer_status",
        "description": "Get detailed status for a customer: the one given, else the one this conversation is about.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Customer ID. Omit for the conversation's customer.",
                },
            },
            "required": [],
        },
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
            "available": False,
            "reason": "CLI execution is disabled; configure API mode",
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
    _expire_conversations()
    result = []
    for cid, conv in _conversations.items():
        if not _owns(conv, user_id):
            continue
        result.append(
            {
                "conversation_id": cid,
                "title": conv.get("title", "Untitled"),
                "created_at": conv.get("created_at", ""),
                "message_count": len(conv.get("messages", [])),
            }
        )
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
    if conv is None or not _owns(conv, user_id) or conversation_id in _active_streams:
        return False
    del _conversations[conversation_id]
    return True


def save_api_key(api_key: str) -> None:
    """Persist the Anthropic API key in app settings (encrypted on disk)."""
    from app.core.config import update_app_settings

    update_app_settings(lambda s: s.__setitem__("claude_api_key", api_key))


# ── Streaming chat ─────────────────────────────────────────────────────────

_active_streams: dict[str, str] = {}
MAX_CONVERSATIONS = 200
MAX_PER_USER = 20
MAX_TOOL_ROUNDS = 6


def _expire_conversations() -> None:
    now = time.monotonic()
    for cid, conv in list(_conversations.items()):
        if cid not in _active_streams and now - conv.get("last_used", now) > 86400:
            del _conversations[cid]


async def stream_message(
    conversation_id=None, message="", customer_id=None, user_id=None, user=None, context=None
):
    """Bound memory, concurrency and total wall time for every conversation."""
    _expire_conversations()
    owner = str(user_id or "")
    cid = conversation_id or str(uuid.uuid4())
    if not isinstance(message, str) or not 1 <= len(message) <= 16000:
        yield {"type": "error", "error": "Meldingen må være mellom 1 og 16000 tegn."}
        return
    if cid in _active_streams or len(_active_streams) >= 4 or owner in _active_streams.values():
        yield {
            "type": "error",
            "error": "En samtale kjører allerede. Prøv igjen når den er ferdig.",
        }
        return
    conv = _conversations.get(cid)
    if conv is None and (
        len(_conversations) >= MAX_CONVERSATIONS
        or sum(_owns(c, owner) for c in _conversations.values()) >= MAX_PER_USER
    ):
        yield {"type": "error", "error": "Samtalegrensen er nådd. Slett en eldre samtale."}
        return
    if conv and (len(conv["messages"]) >= 80 or len(json.dumps(conv["messages"])) > 500000):
        yield {"type": "error", "error": "Samtalen er full. Start en ny samtale."}
        return
    _active_streams[cid] = owner
    try:
        async with asyncio.timeout(120):
            generator = _stream_message_impl(cid, message, customer_id, user_id, user, context)
            try:
                async for event in generator:
                    yield event
            finally:
                await generator.aclose()
    except TimeoutError:
        yield {"type": "error", "error": "Samtalen nådde tidsgrensen på 120 sekunder."}
    finally:
        _active_streams.pop(cid, None)
        if cid in _conversations:
            _conversations[cid]["last_used"] = time.monotonic()


async def _stream_message_impl(
    conversation_id: str | None,
    message: str,
    customer_id: str | None = None,
    user_id: str | None = None,
    user: User | None = None,
    context: dict | None = None,
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
        yield {
            "type": "error",
            "error": "CLI-modus er deaktivert: vertstilgang mangler sikker handlingsgodkjenning. Bruk API-modus.",
        }
        return

    if not _HAS_ANTHROPIC:
        yield {
            "type": "error",
            "error": "Anthropic SDK er ikke installert. Installer med: pip install anthropic",
        }
        return

    api_key = _get_api_key()
    if not api_key:
        yield {
            "type": "error",
            "error": "API-nøkkel ikke konfigurert. Gå til Integrasjoner → Claude AI.",
        }
        return

    # Resolve or create conversation
    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    existing = _conversations.get(conversation_id)
    if existing is None:
        _conversations[conversation_id] = {
            "owner_user_id": str(user_id) if user_id else "",
            "messages": [],
            "created_at": datetime.now(UTC).isoformat(),
            "title": message[:80] if message else "New conversation",
        }
    elif not _owns(existing, user_id):
        # Continuing someone else's conversation would both disclose its
        # history to the model's context and append to it. The id is supplied
        # by the client, so this is reachable by anyone who has one.
        yield {"type": "error", "error": "Samtale ikke funnet"}
        return

    conv = _conversations[conversation_id]

    history_start = len(conv["messages"])
    completed = False
    # Append user message
    conv["messages"].append({"role": "user", "content": message})

    # Yield conversation_id so the client knows which conversation this is
    yield {"type": "conversation_id", "conversation_id": conversation_id}

    # Build the Anthropic client
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=30.0, max_retries=1)

    try:
        # We may loop several times if the model makes tool calls
        for _round in range(MAX_TOOL_ROUNDS):
            async with client.messages.stream(
                model=_get_model(),
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
            waiting_for_approval = False
            for block in final.content:
                if getattr(block, "type", None) != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_use_id = block.id

                logger.info("AI tool requested: %s", tool_name)

                try:
                    result = await _dispatch_tool(tool_name, tool_input, customer_id, user)
                    from app.services.ai_actions import provider_result

                    if isinstance(result, dict) and result.get("approval_required"):
                        waiting_for_approval = True
                        yield {"type": "approval_required", **result}
                        # The approval nonce and concrete parameters belong to the
                        # operator UI. They are never sent back to the model.
                        result = {
                            "approval_required": True,
                            "message": "Waiting for operator approval.",
                        }
                    result_str = provider_result(result)
                except Exception as exc:
                    logger.warning("AI tool %s failed (%s)", tool_name, type(exc).__name__)
                    from app.services.ai_actions import provider_result

                    result_str = provider_result({"error": str(exc)})

                yield {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "tool_name": tool_name,
                    "result": result_str,
                }

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_str,
                    }
                )

            # Append tool results and loop for the model's next turn
            conv["messages"].append({"role": "user", "content": tool_results})
            if len(json.dumps(conv["messages"])) > 500000:
                yield {"type": "error", "error": "Historikkgrensen er nådd. Start en ny samtale."}
                return
            if waiting_for_approval:
                break
        else:
            yield {"type": "error", "error": "Grensen på seks verktøyrunder er nådd."}

        completed = True

    except anthropic.APIError as exc:
        logger.warning("Anthropic API failure (%s)", type(exc).__name__)
        yield {"type": "error", "error": "AI-leverandøren avviste forespørselen. Se serverloggen."}
        return
    except Exception as exc:
        logger.warning("AI stream failure (%s)", type(exc).__name__)
        yield {"type": "error", "error": "AI-samtalen feilet. Prøv en ny samtale."}
        return

    finally:
        if not completed:
            del conv["messages"][history_start:]
        await client.close()

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
#
# The approval gate on write tools is no substitute: the technician who
# proposes an action is the one who approves it, so it adds a confirmation,
# not an authorization.

_HOST_SCOPED_TOOLS = {"ssh_execute", "ssh_test_connection"}
_CUSTOMER_SCOPED_TOOLS = {
    "fortigate_dashboard",
    "fortigate_compliance",
    "fortigate_backup",
    "unifi_devices",
    "customer_status",
}
# vpn_connect names a profile; vpn_disconnect may. Without one, disconnect only
# ever picks among the caller's own profiles.
_PROFILE_SCOPED_TOOLS = {"vpn_connect", "vpn_disconnect"}
# Opening or closing a tunnel is refused while the system account holds one.
_TUNNEL_TOOLS = {"vpn_connect", "vpn_disconnect"}
# MSP-wide reads with no customer to scope them to.
_ESTATE_TOOLS = {"unifi_sites"}

_ID_PARAMS = ("host_id", "customer_id", "profile_id")

_SCOPE_DENIED = {
    "error": "Du har ikke tilgang til denne kunden eller hosten.",
    "forbidden": True,
}
_PROFILE_DENIED = {
    "error": "Du har ikke tilgang til denne VPN-profilen.",
    "forbidden": True,
}
_ESTATE_DENIED = {
    "error": "Dette verktøyet viser data for alle kunder og krever tilgang til alle kunder.",
    "forbidden": True,
}


def _normalize_ids(params: Any) -> dict[str, Any]:
    """Strip the id parameters once, so the value checked is the value used.

    A non-string id becomes empty, which every scope check below refuses.
    """
    if not isinstance(params, dict):
        return {}
    clean = dict(params)
    for key in _ID_PARAMS:
        if key in clean:
            value = clean[key]
            clean[key] = value.strip() if isinstance(value, str) else ""
    return clean


def _effective_customer_id(params: dict[str, Any], customer_id: str | None) -> str:
    """The customer a customer-scoped tool acts on: its own id, else the conversation's."""
    cid = params.get("customer_id") or customer_id or ""
    return cid.strip() if isinstance(cid, str) else ""


async def _in_scope(user: User | None, record) -> bool:
    """Whether *user* may reach a host or VPN profile.

    The rule the SSH and VPN routes apply (``_may_see_host`` in routes/ssh.py,
    ``_may_use_profile`` in routes/vpn.py): a record that belongs to a customer
    follows that customer's access, and one with no customer is estate-wide
    infrastructure that stays with unrestricted accounts. Services may not
    import the web layer, so the parity with the route helpers is pinned by a
    test rather than by sharing the function.
    """
    from app.core.rbac import check_customer_access, get_accessible_customer_ids

    if user is None or record is None:
        return False
    if record.customer_id:
        return await check_customer_access(user, record.customer_id)
    return await get_accessible_customer_ids(user) is None


async def _visible_profile_ids(user: User | None) -> set[str]:
    """Ids of the VPN profiles *user* may see, for filtering status and lists."""
    from app.services.vpn_manager import list_profiles

    return {profile.id for profile in await list_profiles() if await _in_scope(user, profile)}


async def _system_hold_refusal(user: User | None) -> dict | None:
    """Refuse a tunnel change while the collectors hold a tunnel open.

    The same lock the VPN routes enforce. Profiles the caller may not see are
    counted rather than named.
    """
    from app.services.vpn_manager import get_profile, system_held

    held = system_held()
    if not held:
        return None
    names: list[str] = []
    hidden = 0
    for pid in held:
        profile = await get_profile(pid)
        if await _in_scope(user, profile):
            names.append(getattr(profile, "name", None) or pid)
        else:
            hidden += 1
    if hidden == 1:
        names.append("én profil du ikke har tilgang til")
    elif hidden:
        names.append(f"{hidden} profiler du ikke har tilgang til")
    return {
        "error": (
            "Systemkontoen holder VPN-tunneler åpne for statistikkinnhenting: "
            + ", ".join(names)
            + ". Vent til innhentingen er ferdig, eller stopp den planlagte jobben først."
        ),
        "forbidden": True,
    }


def _log_denied(kind: str, user: User | None, name: str, target: Any) -> None:
    logger.info(
        "console 403 %s: user=%s tool=%s target=%s",
        kind,
        getattr(user, "username", "?"),
        name,
        target,
    )


async def _enforce_tool_scope(
    user: User | None,
    name: str,
    params: dict[str, Any],
    customer_id: str | None,
) -> dict | None:
    """Return an error dict if this tool call escapes the caller's scope.

    Fails closed: a scoped tool invoked without an authenticated user, or
    naming an id the user cannot reach, is refused before the underlying
    service function runs. *params* must already be normalized.
    """
    if name in _HOST_SCOPED_TOOLS:
        from app.services.ssh_manager import get_host

        host_id = params.get("host_id") or ""
        host = await get_host(host_id) if host_id else None
        if not await _in_scope(user, host):
            _log_denied("host-access", user, name, host_id)
            return _SCOPE_DENIED
    if name in _CUSTOMER_SCOPED_TOOLS:
        from app.core.rbac import check_customer_access

        cid = _effective_customer_id(params, customer_id)
        if user is None or not cid or not await check_customer_access(user, cid):
            _log_denied("customer-access", user, name, cid)
            return _SCOPE_DENIED
    if name in _PROFILE_SCOPED_TOOLS:
        from app.services.vpn_manager import get_profile

        profile_id = params.get("profile_id") or ""
        if user is None:
            _log_denied("profile-access", user, name, profile_id)
            return _PROFILE_DENIED
        if profile_id or name == "vpn_connect":
            profile = await get_profile(profile_id) if profile_id else None
            if not await _in_scope(user, profile):
                _log_denied("profile-access", user, name, profile_id)
                return _PROFILE_DENIED
    if name in _ESTATE_TOOLS:
        from app.core.rbac import get_accessible_customer_ids

        if user is None or await get_accessible_customer_ids(user) is not None:
            _log_denied("estate-access", user, name, "")
            return _ESTATE_DENIED
    return None


# ── Tool dispatch ──────────────────────────────────────────────────────────


async def _dispatch_tool(
    name: str,
    params: dict[str, Any],
    customer_id: str | None = None,
    user: User | None = None,
    *,
    approved: bool = False,
) -> Any:
    """Route a tool call to the appropriate service function.

    ``user`` is the authenticated caller. Host-, customer- and profile-scoped
    tools are refused here when the requested id is outside the caller's
    access, and the list tools filter their output to what the caller may see,
    so the console cannot reach across customers the way the HTTP routes
    already prevent. An approved action comes back through here, so every
    check runs again at execution time.
    """
    params = _normalize_ids(params)
    scope_error = await _enforce_tool_scope(user, name, params, customer_id)
    if scope_error is not None:
        return scope_error
    if name in _TUNNEL_TOOLS:
        refusal = await _system_hold_refusal(user)
        if refusal is not None:
            return refusal

    from app.services.ai_actions import WRITE_TOOLS, propose

    if name in WRITE_TOOLS:
        from app.core.capabilities import require_write

        if user is None:
            return _SCOPE_DENIED
        require_write(user)
        if not approved:
            return propose(str(user.id), name, params, customer_id)

    # -- SSH tools --
    if name == "ssh_list_hosts":
        from app.core.rbac import get_accessible_customer_ids
        from app.services.ssh_manager import list_hosts

        allowed = await get_accessible_customer_ids(user) if user else set()
        hosts = await list_hosts()
        if allowed is not None:
            # Restricted account: only hosts belonging to a customer it may
            # access. A host with no customer is estate-wide, so it stays
            # hidden from restricted accounts (matches _in_scope).
            hosts = [h for h in hosts if h.customer_id and h.customer_id in allowed]
        return [
            {
                "id": h.id,
                "label": h.label,
                "hostname": h.hostname,
                "port": h.port,
                "device_type": h.device_type.value,
                "is_reachable": h.is_reachable,
            }
            for h in hosts
        ]

    if name == "ssh_list_keys":
        from app.services.ssh_manager import list_keys

        # The rule /ssh/keys applies: a customer's key follows that customer's
        # access, an MSP-wide key stays with unrestricted accounts.
        keys = [k for k in await list_keys() if await _in_scope(user, k)]
        return [
            {
                "id": k.id,
                "name": k.name,
                "key_type": k.key_type.value,
                "fingerprint": k.fingerprint,
            }
            for k in keys
        ]

    if name == "ssh_execute":
        from app.services.ssh_manager import batch_exec

        results = await batch_exec([params["host_id"]], params["command"])
        r = results[0]
        return {
            "host_id": r.host_id,
            "host_label": r.host_label,
            "exit_code": r.exit_code,
            "stdout": r.stdout,
            "stderr": r.stderr,
            "error": r.error,
        }

    if name == "ssh_test_connection":
        from app.services.ssh_manager import health_check

        results = await health_check([params["host_id"]])
        return results[0] if results else {"error": "No result"}

    # -- VPN tools --
    if name == "vpn_status":
        from app.services.vpn_manager import get_status

        return await get_status(await _visible_profile_ids(user))

    if name == "vpn_list_profiles":
        from app.services.vpn_manager import list_profiles

        return [
            {
                "id": p.id,
                "name": p.name,
                "protocol": p.protocol.value,
                "customer_id": p.customer_id,
            }
            for p in await list_profiles()
            if await _in_scope(user, p)
        ]

    if name == "vpn_connect":
        from app.core.activity_log import log_activity
        from app.services.vpn_manager import connect, get_profile

        profile_id = params["profile_id"]
        profile = await get_profile(profile_id)
        result = await connect(profile_id, owned_by=user.username)
        if result.get("ok"):
            # Opening a tunnel into a customer network is worth a record of who did it.
            log_activity(
                "vpn_connect",
                detail=(
                    f"Koblet til VPN-profil {getattr(profile, 'name', profile_id)} "
                    f"({profile_id}) via AI-konsollen"
                ),
                customer=getattr(profile, "customer_id", None) or "",
                user=user.username,
            )
        return result

    if name == "vpn_disconnect":
        from app.core.activity_log import log_activity
        from app.services.vpn_manager import disconnect, get_profile, get_status

        profile_id = params.get("profile_id") or ""
        if not profile_id:
            status = await get_status(await _visible_profile_ids(user))
            profile_id = next(
                (
                    connection["profile_id"]
                    for connection in status["connections"]
                    if connection["state"] in {"connected", "connecting", "error"}
                ),
                "",
            )
        if not profile_id:
            return {"ok": True, "msg": "Already disconnected"}
        was_registered = bool((await get_status({profile_id}))["connections"])
        profile = await get_profile(profile_id)
        result = await disconnect(profile_id)
        if was_registered and result.get("ok"):
            log_activity(
                "vpn_disconnect",
                detail=(
                    f"Koblet fra VPN-profil {getattr(profile, 'name', profile_id)} "
                    f"({profile_id}) via AI-konsollen"
                ),
                customer=getattr(profile, "customer_id", None) or "",
                user=user.username,
            )
        return result

    # -- FortiGate tools --
    if name == "fortigate_dashboard":
        cid = _effective_customer_id(params, customer_id)
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
        cid = _effective_customer_id(params, customer_id)
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
        cid = _effective_customer_id(params, customer_id)
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
        return await backup_config(config, token, customer_id=cid)

    # -- UniFi tools --
    if name == "unifi_devices":
        cid = _effective_customer_id(params, customer_id)
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
        return [
            {
                "id": c.get("_id", ""),
                "name": c.get("CustomerName", ""),
                "domain": c.get("PrimaryDomain", ""),
            }
            for c in customers[:50]
        ]

    if name == "customer_status":
        from app.core.customer import CustomerManager

        # The customer the conversation is about, as the console sent it, or
        # one the model names; access was checked in _enforce_tool_scope. It
        # used to be the caller's active customer, which a second tab could
        # change mid-conversation.
        cid = _effective_customer_id(params, customer_id)
        cfg = CustomerManager.get_customer(cid) if cid else None
        if not cfg:
            return {"error": "Kunden finnes ikke"}
        return {
            "name": cfg.get("CustomerName", ""),
            "domain": cfg.get("PrimaryDomain", ""),
            "tenant_id": cfg.get("TenantId", ""),
            "fortigate": cfg.get("FortiGateHost", ""),
            "unifi": cfg.get("UniFiHost", ""),
        }

    return {"error": f"Ukjent verktøy: {name}"}


# ── Internal helpers ───────────────────────────────────────────────────────


def _get_api_key() -> str | None:
    """Load the Anthropic API key from app settings."""
    try:
        from app.core.config import load_app_settings

        settings = load_app_settings()
        return settings.get("claude_api_key") or None
    except Exception:
        logger.warning("Could not read the Anthropic API key from settings", exc_info=True)
        return None


_active_cli_proc = None  # Track active CLI process


async def _stream_via_cli(*args, **kwargs):
    yield {"type": "error", "error": "CLI mode is disabled; use API mode with action approvals."}


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Convert an Anthropic content block to a JSON-serialisable dict.

    Thinking blocks have to survive the round trip intact. The assistant turn
    is appended to ``conv["messages"]`` and sent back on the next tool round,
    and a thinking block replayed without its ``signature`` is not the block
    the model produced. Dropping them to ``{"type": "thinking"}`` — which the
    fallback below would have done — corrupts the conversation on the second
    round of any tool call.
    """
    block_type = getattr(block, "type", None)
    if block_type == "thinking":
        return {
            "type": "thinking",
            "thinking": getattr(block, "thinking", ""),
            "signature": getattr(block, "signature", ""),
        }
    if block_type == "redacted_thinking":
        return {"type": "redacted_thinking", "data": getattr(block, "data", "")}
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
