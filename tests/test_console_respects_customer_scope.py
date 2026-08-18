"""The console reaches the same host- and customer-scoped services the HTTP
routes guard behind require_host_access / require_customer_access.

Before the fix, ``_dispatch_tool`` never saw the caller, so a technician scoped
to one customer could run a command on any registered host, or pull any
customer's FortiGate config, just by naming its id in a tool call — the console
was a hole straight through the per-customer RBAC. These tests pin the gate:
an out-of-scope id is refused before the service runs, an in-scope id proceeds,
the list tools only reveal what the caller may see, and CLI mode (which spawns
a host shell) is admin-only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models.user import Role, User
from app.services import claude_console as cc


def _user(role: Role = Role.technician, all_customers: bool = False) -> User:
    return User(
        id="u1",
        username="tech",
        display_name="Tech",
        role=role,
        created_at=datetime.now(UTC),
        is_active=True,
        all_customers=all_customers,
    )


@pytest.fixture
def scoped(monkeypatch):
    """Caller may access customer 'allowed' only; hosts map to a customer."""
    import app.core.rbac as rbac
    import app.services.ssh_manager as sm

    async def _check(user, cid):
        if user.role == Role.admin or user.all_customers:
            return True
        return cid == "allowed"

    async def _accessible(user):
        if user.role == Role.admin or user.all_customers:
            return None  # unrestricted, matching the real contract
        return {"allowed"}

    async def _get_host(hid):
        mapping = {
            "host-allowed": SimpleNamespace(id="host-allowed", customer_id="allowed"),
            "host-other": SimpleNamespace(id="host-other", customer_id="other"),
            "host-estate": SimpleNamespace(id="host-estate", customer_id=None),
        }
        return mapping.get(hid)

    monkeypatch.setattr(rbac, "check_customer_access", _check)
    monkeypatch.setattr(rbac, "get_accessible_customer_ids", _accessible)
    monkeypatch.setattr(sm, "get_host", _get_host)


# ── Host-scoped tools ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ssh_execute_on_out_of_scope_host_is_refused_before_running(scoped, monkeypatch):
    import app.services.ssh_manager as sm

    def _boom(*a, **k):
        raise AssertionError("batch_exec ran on an out-of-scope host")

    monkeypatch.setattr(sm, "batch_exec", _boom)

    result = await cc._dispatch_tool(
        "ssh_execute",
        {"host_id": "host-other", "command": "rm -rf /"},
        None,
        _user(),
    )
    assert result is cc._SCOPE_DENIED


@pytest.mark.asyncio
async def test_ssh_execute_on_in_scope_host_runs(scoped, monkeypatch):
    import app.services.ssh_manager as sm

    async def _batch(host_ids, command, *a, **k):
        return [SimpleNamespace(
            host_id=host_ids[0], host_label="L", exit_code=0,
            stdout="ok", stderr="", error=None,
        )]

    monkeypatch.setattr(sm, "batch_exec", _batch)

    result = await cc._dispatch_tool(
        "ssh_execute",
        {"host_id": "host-allowed", "command": "uptime"},
        None,
        _user(),
    )
    assert result["exit_code"] == 0 and result["stdout"] == "ok"


@pytest.mark.asyncio
async def test_ssh_execute_without_a_user_fails_closed(scoped):
    result = await cc._dispatch_tool(
        "ssh_execute", {"host_id": "host-allowed", "command": "uptime"}, None, None,
    )
    assert result is cc._SCOPE_DENIED


@pytest.mark.asyncio
async def test_estate_host_is_hidden_from_a_restricted_technician(scoped, monkeypatch):
    import app.services.ssh_manager as sm
    monkeypatch.setattr(sm, "batch_exec",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    result = await cc._dispatch_tool(
        "ssh_test_connection", {"host_id": "host-estate"}, None, _user(),
    )
    assert result is cc._SCOPE_DENIED


# ── Customer-scoped tools ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fortigate_backup_on_out_of_scope_customer_is_refused(scoped):
    result = await cc._dispatch_tool(
        "fortigate_backup", {"customer_id": "other"}, None, _user(),
    )
    assert result is cc._SCOPE_DENIED


@pytest.mark.asyncio
async def test_customer_scoped_tool_falls_back_to_conversation_customer(scoped):
    # The effective id is params.customer_id or the conversation's customer_id;
    # an out-of-scope conversation id must be refused too, not just the param.
    result = await cc._dispatch_tool(
        "unifi_devices", {}, "other", _user(),
    )
    assert result is cc._SCOPE_DENIED


# ── List tools filter, they do not enumerate the estate ──────────────────────

@pytest.mark.asyncio
async def test_list_hosts_shows_only_hosts_the_caller_may_see(scoped, monkeypatch):
    import app.services.ssh_manager as sm

    async def _list():
        return [
            SimpleNamespace(id="host-allowed", label="A", hostname="a", port=22,
                            device_type=SimpleNamespace(value="linux"),
                            is_reachable=True, customer_id="allowed"),
            SimpleNamespace(id="host-other", label="B", hostname="b", port=22,
                            device_type=SimpleNamespace(value="linux"),
                            is_reachable=True, customer_id="other"),
            SimpleNamespace(id="host-estate", label="C", hostname="c", port=22,
                            device_type=SimpleNamespace(value="linux"),
                            is_reachable=True, customer_id=None),
        ]

    monkeypatch.setattr(sm, "list_hosts", _list)

    result = await cc._dispatch_tool("ssh_list_hosts", {}, None, _user())
    assert [h["id"] for h in result] == ["host-allowed"]


@pytest.mark.asyncio
async def test_list_hosts_unrestricted_admin_sees_all(scoped, monkeypatch):
    import app.services.ssh_manager as sm

    async def _list():
        return [
            SimpleNamespace(id="host-allowed", label="A", hostname="a", port=22,
                            device_type=SimpleNamespace(value="linux"),
                            is_reachable=True, customer_id="allowed"),
            SimpleNamespace(id="host-estate", label="C", hostname="c", port=22,
                            device_type=SimpleNamespace(value="linux"),
                            is_reachable=True, customer_id=None),
        ]

    monkeypatch.setattr(sm, "list_hosts", _list)

    result = await cc._dispatch_tool(
        "ssh_list_hosts", {}, None, _user(role=Role.admin, all_customers=True),
    )
    assert {h["id"] for h in result} == {"host-allowed", "host-estate"}


# ── CLI mode is admin-only ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cli_mode_is_refused_for_a_technician(monkeypatch):
    monkeypatch.setattr(cc, "_get_mode", lambda: "cli")

    events = [
        e async for e in cc.stream_message(
            conversation_id=None, message="hei", user_id="u1", user=_user(),
        )
    ]
    assert events and events[0]["type"] == "error"
    assert "admin" in events[0]["error"].lower()


@pytest.mark.asyncio
async def test_cli_mode_admin_reaches_the_cli(monkeypatch):
    monkeypatch.setattr(cc, "_get_mode", lambda: "cli")

    async def _fake_cli(*a, **k):
        yield {"type": "conversation_id", "conversation_id": "x"}

    monkeypatch.setattr(cc, "_stream_via_cli", _fake_cli)

    events = [
        e async for e in cc.stream_message(
            conversation_id=None, message="hei", user_id="u1",
            user=_user(role=Role.admin),
        )
    ]
    assert events == [{"type": "conversation_id", "conversation_id": "x"}]
