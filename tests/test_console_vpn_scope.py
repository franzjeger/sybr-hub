"""The console's VPN and estate-wide tools obey the same rules as the HTTP routes.

``vpn_connect`` and ``vpn_disconnect`` called the VPN manager directly: no
profile-access check, no refusal while the system account holds a tunnel, no
record of who opened it. The approval gate did not help, because the
technician who proposes an action is the one who approves it. A technician
scoped to one customer could therefore open a tunnel into any customer's
network, and ``vpn_list_profiles`` / ``vpn_status`` / ``unifi_sites`` listed
the whole estate. These tests drive ``_dispatch_tool`` and the approval flow
the way the console does and assert what reaches the VPN manager.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core import system_user
from app.models.user import Role, User
from app.models.vpn import VpnState
from app.services import ai_actions
from app.services import claude_console as cc

PROFILES = {
    "p-allowed": SimpleNamespace(
        id="p-allowed",
        name="Allowed HQ",
        customer_id="allowed",
        protocol=SimpleNamespace(value="wireguard"),
    ),
    "p-other": SimpleNamespace(
        id="p-other",
        name="Other HQ",
        customer_id="other",
        protocol=SimpleNamespace(value="wireguard"),
    ),
    "p-shared": SimpleNamespace(
        id="p-shared",
        name="Shared jump",
        customer_id=None,
        protocol=SimpleNamespace(value="openvpn"),
    ),
}


def _user(role: Role = Role.technician, all_customers: bool = False, uid: str = "u1") -> User:
    return User(
        id=uid,
        username=f"tech-{uid}",
        display_name="Tech",
        role=role,
        created_at=datetime.now(UTC),
        is_active=True,
        can_write=True,
        all_customers=all_customers,
    )


def _admin() -> User:
    return _user(role=Role.admin, uid="admin")


@pytest.fixture(autouse=True)
def _clean_pending():
    ai_actions._pending.clear()
    yield
    ai_actions._pending.clear()


@pytest.fixture
def access(monkeypatch):
    """Restricted callers reach customer 'allowed'; the set is mutable per test."""
    import app.core.rbac as rbac

    granted = {"allowed"}

    async def _check(user, cid):
        if user.role == Role.admin or user.all_customers:
            return True
        return cid in granted

    async def _accessible(user):
        if user.role == Role.admin or user.all_customers:
            return None
        return set(granted)

    monkeypatch.setattr(rbac, "check_customer_access", _check)
    monkeypatch.setattr(rbac, "get_accessible_customer_ids", _accessible)
    return granted


@pytest.fixture
def vpn(monkeypatch, access):
    """A VPN manager with three profiles and recorded connect/disconnect calls."""
    import app.services.vpn_manager as vm

    calls: dict[str, list] = {"connect": [], "disconnect": []}
    monkeypatch.setattr(vm, "_connections", {})

    async def _get_profile(pid):
        return PROFILES.get(pid)

    async def _list_profiles():
        return list(PROFILES.values())

    async def _connect(profile_id, *, owned_by=""):
        calls["connect"].append((profile_id, owned_by))
        vm._connections[profile_id] = {"state": VpnState.connected, "owned_by": owned_by}
        return {"ok": True}

    async def _disconnect(profile_id=None):
        calls["disconnect"].append(profile_id)
        vm._connections.pop(profile_id, None)
        return {"ok": True}

    monkeypatch.setattr(vm, "get_profile", _get_profile)
    monkeypatch.setattr(vm, "list_profiles", _list_profiles)
    monkeypatch.setattr(vm, "connect", _connect)
    monkeypatch.setattr(vm, "disconnect", _disconnect)

    logged: list[dict] = []
    monkeypatch.setattr(
        "app.core.activity_log.log_activity",
        lambda action, detail="", customer="", user="": logged.append(
            {"action": action, "detail": detail, "customer": customer, "user": user}
        ),
    )
    return SimpleNamespace(manager=vm, calls=calls, logged=logged)


def _hold(vm, pid: str, owner: str, state=VpnState.connected) -> None:
    vm._connections[pid] = {"state": state, "owned_by": owner}


async def _propose_and_approve(name: str, params: dict, user: User):
    proposal = await cc._dispatch_tool(name, params, None, user)
    assert proposal.get("approval_required"), proposal
    return await ai_actions.decide(proposal["approval_id"], user, approve=True)


# ── vpn_connect ──────────────────────────────────────────────────────────────


async def test_connect_to_another_customers_profile_is_refused_before_proposal(vpn):
    result = await cc._dispatch_tool("vpn_connect", {"profile_id": "p-other"}, None, _user())

    assert result is cc._PROFILE_DENIED
    assert ai_actions._pending == {}, "an out-of-scope tunnel reached the approval queue"
    assert vpn.calls["connect"] == []


async def test_connect_to_a_shared_profile_needs_an_unrestricted_account(vpn):
    refused = await cc._dispatch_tool("vpn_connect", {"profile_id": "p-shared"}, None, _user())
    assert refused is cc._PROFILE_DENIED

    proposed = await cc._dispatch_tool("vpn_connect", {"profile_id": "p-shared"}, None, _admin())
    assert proposed["approval_required"] is True


async def test_connect_to_an_unknown_profile_is_refused(vpn):
    result = await cc._dispatch_tool("vpn_connect", {"profile_id": "nope"}, None, _admin())
    assert result is cc._PROFILE_DENIED


async def test_approved_connect_records_who_opened_the_tunnel(vpn):
    user = _user()
    decision = await _propose_and_approve("vpn_connect", {"profile_id": "p-allowed"}, user)

    assert decision["result"] == {"ok": True}
    assert vpn.calls["connect"] == [("p-allowed", user.username)]
    assert vpn.manager.owner_of("p-allowed") == user.username
    assert vpn.logged == [
        {
            "action": "vpn_connect",
            "detail": "Koblet til VPN-profil Allowed HQ (p-allowed) via AI-konsollen",
            "customer": "allowed",
            "user": user.username,
        }
    ]


async def test_access_revoked_between_proposal_and_approval_is_refused(vpn, access):
    user = _user()
    proposal = await cc._dispatch_tool("vpn_connect", {"profile_id": "p-allowed"}, None, user)
    assert proposal["approval_required"] is True

    access.clear()
    decision = await ai_actions.decide(proposal["approval_id"], user, approve=True)

    assert decision["result"]["forbidden"] is True
    assert vpn.calls["connect"] == []


async def test_connect_is_refused_while_the_system_holds_a_tunnel(vpn):
    _hold(vpn.manager, "p-allowed", system_user.USERNAME)

    result = await cc._dispatch_tool("vpn_connect", {"profile_id": "p-allowed"}, None, _admin())

    assert result["forbidden"] is True
    assert "Allowed HQ" in result["error"]
    assert ai_actions._pending == {}
    assert vpn.calls["connect"] == []


async def test_system_lock_taken_after_proposal_still_refuses_the_approved_connect(vpn):
    user = _user()
    proposal = await cc._dispatch_tool("vpn_connect", {"profile_id": "p-allowed"}, None, user)

    _hold(vpn.manager, "p-other", system_user.USERNAME)
    decision = await ai_actions.decide(proposal["approval_id"], user, approve=True)

    assert decision["result"]["forbidden"] is True
    assert vpn.calls["connect"] == []


async def test_system_lock_message_does_not_name_profiles_outside_scope(vpn):
    _hold(vpn.manager, "p-other", system_user.USERNAME)

    result = await cc._dispatch_tool("vpn_connect", {"profile_id": "p-allowed"}, None, _user())

    assert result["forbidden"] is True
    assert "Other HQ" not in result["error"]
    assert "én profil du ikke har tilgang til" in result["error"]


async def test_connect_uses_the_same_profile_id_it_checked(vpn):
    await _propose_and_approve("vpn_connect", {"profile_id": "  p-allowed "}, _user())
    assert vpn.calls["connect"][0][0] == "p-allowed"


@pytest.mark.parametrize("bad", [["p-allowed"], {"id": "p-allowed"}, 7, None])
async def test_a_non_string_profile_id_is_refused(vpn, bad):
    result = await cc._dispatch_tool("vpn_connect", {"profile_id": bad}, None, _admin())
    assert result is cc._PROFILE_DENIED


async def test_vpn_tools_without_a_user_fail_closed(vpn):
    for name, params in (("vpn_connect", {"profile_id": "p-allowed"}), ("vpn_disconnect", {})):
        assert (await cc._dispatch_tool(name, params, None, None))["forbidden"] is True
    assert await cc._dispatch_tool("vpn_list_profiles", {}, None, None) == []
    assert (await cc._dispatch_tool("vpn_status", {}, None, None))["connections"] == []


# ── vpn_disconnect ───────────────────────────────────────────────────────────


async def test_disconnect_without_profile_never_picks_another_customers_tunnel(vpn):
    _hold(vpn.manager, "p-other", "someone-else")

    decision = await _propose_and_approve("vpn_disconnect", {}, _user())

    assert decision["result"] == {"ok": True, "msg": "Already disconnected"}
    assert vpn.calls["disconnect"] == []
    assert "p-other" in vpn.manager._connections


async def test_disconnect_without_profile_closes_the_callers_own_tunnel(vpn):
    user = _user()
    _hold(vpn.manager, "p-other", "someone-else")
    _hold(vpn.manager, "p-allowed", user.username)

    await _propose_and_approve("vpn_disconnect", {}, user)

    assert vpn.calls["disconnect"] == ["p-allowed"]
    assert "p-other" in vpn.manager._connections
    assert [entry["action"] for entry in vpn.logged] == ["vpn_disconnect"]


async def test_disconnect_naming_another_customers_profile_is_refused(vpn):
    _hold(vpn.manager, "p-other", "someone-else")

    result = await cc._dispatch_tool("vpn_disconnect", {"profile_id": "p-other"}, None, _user())

    assert result is cc._PROFILE_DENIED
    assert ai_actions._pending == {}


async def test_disconnect_is_refused_while_the_system_holds_a_tunnel(vpn):
    user = _admin()
    _hold(vpn.manager, "p-allowed", system_user.USERNAME)

    result = await cc._dispatch_tool("vpn_disconnect", {"profile_id": "p-allowed"}, None, user)

    assert result["forbidden"] is True
    assert vpn.calls["disconnect"] == []
    assert vpn.manager.system_held() == ["p-allowed"]


async def test_a_failed_system_tunnel_does_not_hold_the_lock(vpn):
    user = _user()
    _hold(vpn.manager, "p-other", system_user.USERNAME, state=VpnState.error)

    proposal = await cc._dispatch_tool("vpn_connect", {"profile_id": "p-allowed"}, None, user)

    assert proposal["approval_required"] is True


# ── Read tools ───────────────────────────────────────────────────────────────


async def test_list_profiles_shows_only_profiles_the_caller_may_use(vpn):
    restricted = await cc._dispatch_tool("vpn_list_profiles", {}, None, _user())
    unrestricted = await cc._dispatch_tool("vpn_list_profiles", {}, None, _admin())

    assert [p["id"] for p in restricted] == ["p-allowed"]
    assert {p["id"] for p in unrestricted} == set(PROFILES)


async def test_status_reports_only_the_callers_tunnels(vpn):
    _hold(vpn.manager, "p-other", "someone-else")

    status = await cc._dispatch_tool("vpn_status", {}, None, _user())

    assert status["connections"] == []
    assert status["state"] == "disconnected"


async def test_unifi_sites_is_refused_for_a_restricted_account(access, monkeypatch):
    import app.services.unifi_api as unifi_api

    async def _sites(*a, **k):
        raise AssertionError("MSP-wide Site Manager data was fetched for a restricted account")

    monkeypatch.setattr(unifi_api, "site_manager_list_sites", _sites)

    result = await cc._dispatch_tool("unifi_sites", {}, None, _user())

    assert result is cc._ESTATE_DENIED


async def test_unifi_sites_is_available_to_an_unrestricted_account(access, monkeypatch):
    import app.services.unifi_api as unifi_api

    async def _sites(*a, **k):
        return {"ok": True, "sites": []}

    monkeypatch.setattr(unifi_api, "site_manager_list_sites", _sites)

    for user in (_admin(), _user(all_customers=True)):
        assert await cc._dispatch_tool("unifi_sites", {}, None, user) == {"ok": True, "sites": []}
    assert await cc._dispatch_tool("unifi_sites", {}, None, None) is cc._ESTATE_DENIED


async def test_customer_status_answers_for_the_conversations_customer(access, monkeypatch):
    """The customer the console was asked about, never one remembered for the user.

    It read the caller's active customer, which another tab of the same
    account could change in the middle of a conversation.
    """
    from app.core.customer import CustomerManager

    records = {
        "other": {"CustomerName": "Other AS", "TenantId": "t-other"},
        "allowed": {"CustomerName": "Allowed AS", "TenantId": "t-allowed"},
    }
    monkeypatch.setattr(CustomerManager, "get_customer", staticmethod(records.get))

    # The conversation is about "other": a scoped user without it is refused.
    assert await cc._dispatch_tool("customer_status", {}, "other", _user()) is cc._SCOPE_DENIED
    assert await cc._dispatch_tool("customer_status", {}, "other", None) is cc._SCOPE_DENIED
    allowed = await cc._dispatch_tool("customer_status", {}, "other", _admin())
    assert allowed["name"] == "Other AS" and allowed["tenant_id"] == "t-other"
    # No customer in the conversation and none named: nobody's status.
    assert await cc._dispatch_tool("customer_status", {}, None, _admin()) is cc._SCOPE_DENIED
    # The model may name one, under the same check.
    named = await cc._dispatch_tool("customer_status", {"customer_id": "allowed"}, None, _user())
    assert named["name"] == "Allowed AS"


@pytest.mark.parametrize("bad", [["host-allowed"], 5, None])
async def test_a_non_string_host_id_is_refused(access, monkeypatch, bad):
    import app.services.ssh_manager as sm

    async def _get_host(hid):
        raise AssertionError("looked up a host from a non-string id")

    monkeypatch.setattr(sm, "get_host", _get_host)

    result = await cc._dispatch_tool(
        "ssh_execute", {"host_id": bad, "command": "uptime"}, None, _admin()
    )

    assert result is cc._SCOPE_DENIED


# ── Parity with the route helpers ────────────────────────────────────────────


async def test_console_scope_rule_matches_the_vpn_and_ssh_routes(access):
    """The console cannot import the route helpers, so pin that they agree."""
    from app.web.routes.ssh import _may_see_host
    from app.web.routes.vpn import _may_use_profile

    users = [_user(), _user(all_customers=True, uid="u2"), _admin()]
    records = [*PROFILES.values(), None]
    for user in users:
        for record in records:
            console = await cc._in_scope(user, record)
            assert console == await _may_use_profile(user, record), (user.id, record)
            assert console == await _may_see_host(user, record), (user.id, record)


# ── ssh_list_keys ────────────────────────────────────────────────────────────


@pytest.fixture
def keys(monkeypatch, access):
    import app.services.ssh_manager as sm

    def _key(kid, customer_id):
        return SimpleNamespace(
            id=kid,
            name=kid,
            key_type=SimpleNamespace(value="ed25519"),
            fingerprint=f"SHA256:{kid}",
            customer_id=customer_id,
        )

    async def _list_keys():
        return [_key("k-allowed", "allowed"), _key("k-other", "other"), _key("k-msp", None)]

    monkeypatch.setattr(sm, "list_keys", _list_keys)


async def test_list_keys_shows_a_restricted_caller_only_its_customers_keys(keys):
    result = await cc._dispatch_tool("ssh_list_keys", {}, None, _user())
    assert [k["id"] for k in result] == ["k-allowed"]


async def test_list_keys_shows_an_unrestricted_caller_every_key(keys):
    result = await cc._dispatch_tool("ssh_list_keys", {}, None, _admin())
    assert [k["id"] for k in result] == ["k-allowed", "k-other", "k-msp"]
