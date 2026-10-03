"""A provisioning deploy reports what the device actually did.

deploy_config answered ``{"ok": True}`` whatever happened. The REST deploy's
own verdict sat two levels down, where only the route dug for it; the SSH
deploy skipped lines and never read the device's answer, then reported ok with
a command count; and the REST deploy read any FortiOS HTTP 500 as "already
exists" and overwrote with a PUT. The REST deploy itself was one function of
nearly a thousand lines with no tests.

These tests drive the REST deploy against a fake FortiGate that records every
call, and the SSH deploy against a fake connection, and pin three things: the
calls made and their order (the decomposition into named steps must send what
the single function sent), what is reported per step (applied, skipped,
failed with the reason, not run), and that ok is true only when every
required step got through.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.exceptions import IntegrationError, ValidationError
from app.modules.api_result import ApiDict, ApiList
from app.services import provisioning
from app.services.provisioning import StepStatus
from app.services.ssh_connection import CommandResult

# ── A fake FortiGate ─────────────────────────────────────────────────────────


class FakeResponse:
    """The parts of an httpx.Response the deploy reads."""

    def __init__(self, status: int = 200, body: object = None, text: str | None = None):
        self.status_code = status
        self._body = {"status": "success", "http_status": status} if body is None else body
        self.text = json.dumps(self._body) if text is None else text

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        if isinstance(self._body, BaseException):
            raise self._body
        return self._body


def fortios_error(code: int, cli_error: str = "", text: str | None = None) -> FakeResponse:
    """FortiOS's answer to a refused write: HTTP 500 and a numeric error code."""
    body = {"http_method": "POST", "status": "error", "http_status": 500, "error": code}
    if cli_error:
        body["cli_error"] = cli_error
    return FakeResponse(500, body, text)


class FakeFortiGate:
    """Stands in for FortiGateClient: records every call, answers from a script.

    Writes succeed unless a rule set with ``answer()`` matches; reads come
    from ``reads`` (an ApiList carrying .error is a failed read).
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.opened: list[dict] = []
        self._rules: list[tuple[str, str, str | None, object]] = []
        self._client = self  # the deploy writes through fg._client.put/post
        self.reads: dict[str, object] = {
            "system/global": ApiDict({"timezone": "Europe/Oslo"}),
            "system/interface": ApiList(
                [
                    {
                        "name": "wan1",
                        "type": "physical",
                        "role": "wan",
                        "ip": "203.0.113.10 255.255.255.0",
                    },
                    {
                        "name": "internal",
                        "type": "hard-switch",
                        "role": "lan",
                        "ip": "192.168.1.99 255.255.255.0",
                    },
                    {
                        "name": "internal4",
                        "type": "physical",
                        "role": "lan",
                        "ip": "0.0.0.0 0.0.0.0",
                    },
                    {
                        "name": "internal5",
                        "type": "physical",
                        "role": "lan",
                        "ip": "0.0.0.0 0.0.0.0",
                    },
                ]
            ),
            "system.dhcp/server": ApiList([]),
            "system/virtual-switch/internal": ApiDict(
                {"name": "internal", "port": [{"name": "internal4"}, {"name": "internal5"}]}
            ),
            "system/interface/internal": ApiDict(
                {"name": "internal", "ip": "192.168.1.99 255.255.255.0"}
            ),
        }

    # FortiGateClient(host, api_token, port=..., vdom=..., verify_ssl=...)
    def __call__(self, host: str, api_token: str, **kwargs) -> FakeFortiGate:
        self.opened.append({"host": host, "api_token": api_token, **kwargs})
        return self

    async def __aenter__(self) -> FakeFortiGate:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def answer(self, method: str, path: str, response: object, *, name: str | None = None) -> None:
        """Answer *method* on *path* (and, if given, payload name) with *response*."""
        self._rules.append((method, path, name, response))

    async def get_cmdb(self, path: str, params: dict | None = None):
        self.calls.append(("GET", path, params))
        value = self.reads.get(path, ApiList())
        if isinstance(value, BaseException):
            raise value
        return value

    async def put(self, url: str, json: dict | None = None, params: dict | None = None):
        return self._write("PUT", url, json, params)

    async def post(self, url: str, json: dict | None = None, params: dict | None = None):
        return self._write("POST", url, json, params)

    def _write(self, method: str, url: str, payload: dict | None, params: dict | None):
        assert url.startswith("/api/v2/cmdb/"), url
        assert params == {"vdom": "root"}, params
        path = url.removeprefix("/api/v2/cmdb/")
        self.calls.append((method, path, payload))
        for m, p, name, response in self._rules:
            if m == method and p == path and (name is None or (payload or {}).get("name") == name):
                if isinstance(response, BaseException):
                    raise response
                return response
        return FakeResponse(200)

    @property
    def sequence(self) -> list[tuple[str, str]]:
        return [(method, path) for method, path, _ in self.calls]

    @property
    def writes(self) -> list[tuple[str, str]]:
        return [(method, path) for method, path, _ in self.calls if method != "GET"]

    def payload(self, method: str, path: str, name: str | None = None) -> dict:
        for m, p, body in self.calls:
            if m == method and p == path and (name is None or (body or {}).get("name") == name):
                return body
        raise AssertionError(f"no {method} {path} {name or ''}")


@pytest.fixture()
def fortigate(monkeypatch) -> FakeFortiGate:
    fake = FakeFortiGate()
    monkeypatch.setattr("app.modules.fortigate_audit.client.FortiGateClient", fake)
    # No DNS lookups and no random secrets in a test.
    monkeypatch.setattr(provisioning, "_unifi_option43", lambda host: "0104c0000232")
    monkeypatch.setattr(provisioning, "_gen_password", lambda length=24: "p" * length)
    return fake


WIZARD = {
    1: {"name": "Testkunde AS"},
    2: {
        "lan_subnet": "10.42.0.0/24",
        "vlans": [
            {"name": "Servere", "id": 10, "subnet": "10.42.10.0/24"},
            {"name": "Gjest", "id": 20, "subnet": "10.42.20.0/24"},
            {"name": "Management", "id": 99, "subnet": "10.42.99.0/24"},
        ],
    },
    3: {"syslog_server": "198.51.100.5"},
    4: {},
}

CONN = {
    "host": "192.0.2.1",
    "port": 8443,
    "vdom": "root",
    "verify_ssl": False,
    "api_token": "TEST-TOKEN",
    "admin_user": "admin",
    "admin_password": "",
    "customer_id": "",
    "customer_name": "",
}

# Every call a clean REST deploy of WIZARD makes, in order, grouped by step.
CLEAN_RUN = [
    # discover
    ("GET", "system/global"),
    ("GET", "system/interface"),
    # system_global, password_policy, dns, ntp, wan_interface
    ("PUT", "system/global"),
    ("PUT", "system/password-policy"),
    ("PUT", "system/dns"),
    ("PUT", "system/ntp"),
    ("PUT", "system/interface/wan1"),
    # vlan_interfaces
    ("POST", "system/interface"),
    ("POST", "system/interface"),
    ("POST", "system/interface"),
    # address_objects, address_group
    ("POST", "firewall/address"),
    ("POST", "firewall/address"),
    ("POST", "firewall/address"),
    ("POST", "firewall/address"),
    ("POST", "firewall/addrgrp"),
    # dhcp_servers: LAN + three VLANs, each looked up before it is created
    ("GET", "system.dhcp/server"),
    ("POST", "system.dhcp/server"),
    ("GET", "system.dhcp/server"),
    ("POST", "system.dhcp/server"),
    ("GET", "system.dhcp/server"),
    ("POST", "system.dhcp/server"),
    ("GET", "system.dhcp/server"),
    ("POST", "system.dhcp/server"),
    # mgmt_port
    ("GET", "system/interface"),
    ("GET", "system/virtual-switch/internal"),
    ("PUT", "system/virtual-switch/internal"),
    ("PUT", "system/interface/internal5"),
    ("GET", "system.dhcp/server"),
    ("POST", "system.dhcp/server"),
    # logging
    ("PUT", "log/setting"),
    ("PUT", "log.syslogd/setting"),
    # firewall_policies
    *[("POST", "firewall/policy")] * 8,
    # vpn
    ("POST", "user/local"),
    ("POST", "user/group"),
    ("POST", "firewall/address"),
    ("POST", "firewall/addrgrp"),
    ("POST", "vpn.ipsec/phase1-interface"),
    ("POST", "vpn.ipsec/phase2-interface"),
    # vpn_policies
    ("POST", "firewall/policy"),
    ("POST", "firewall/policy"),
    # lan_address: read, then the change that must be the last call
    ("GET", "system/interface/internal"),
    ("PUT", "system/interface/internal"),
]

STEP_ORDER = [
    "discover",
    "system_global",
    "password_policy",
    "dns",
    "ntp",
    "wan_interface",
    "vlan_interfaces",
    "address_objects",
    "address_group",
    "dhcp_servers",
    "mgmt_port",
    "logging",
    "firewall_policies",
    "vpn",
    "vpn_policies",
    "lan_address",
]


async def _deploy(conn: dict | None = None, wizard: dict | None = None):
    return await provisioning._deploy_via_rest(
        "192.0.2.1", (conn or CONN)["api_token"], wizard or WIZARD, conn=dict(conn or CONN)
    )


def _statuses(result) -> dict[str, StepStatus]:
    return {s.name: s.status for s in result.steps}


def _step(result, name: str):
    return next(s for s in result.steps if s.name == name)


# ── REST: the clean run ──────────────────────────────────────────────────────


async def test_a_clean_run_makes_every_call_in_order_and_is_ok(fortigate):
    result = await _deploy()

    assert fortigate.sequence == CLEAN_RUN
    assert fortigate.opened == [
        {
            "host": "192.0.2.1",
            "api_token": "TEST-TOKEN",
            "port": 8443,
            "vdom": "root",
            "verify_ssl": False,
        }
    ]
    assert [s.name for s in result.steps] == STEP_ORDER
    assert all(s.status is StepStatus.APPLIED for s in result.steps)
    assert result.ok is True

    out = result.as_dict()
    assert out["ok"] is True
    assert out["stopped_at"] is None
    assert out["failed"] == 0 and out["not_run"] == 0
    assert out["success"] == out["total"]
    assert "discover" not in out["applied_steps"]  # a read changes nothing
    assert out["applied_steps"] == STEP_ORDER[1:]
    assert out["lan_ip_changed"] is True
    assert (out["old_ip"], out["new_ip"]) == ("192.0.2.1", "10.42.0.1")
    assert out["config_summary"]["vpn"]["psk"] == "p" * 32


async def test_the_payloads_are_the_ones_the_deploy_always_sent(fortigate):
    await _deploy()

    assert fortigate.payload("POST", "system/interface", "V010_SERVERE") == {
        "name": "V010_SERVERE",
        "vdom": "root",
        "type": "vlan",
        "interface": "internal",
        "vlanid": 10,
        "alias": "TESTKUNDE-AS-SERVERE",
        "mode": "static",
        "ip": "10.42.10.1 255.255.255.0",
        "allowaccess": "ping",
        "description": "VLAN 10 — Servere — 10.42.10.0/24",
    }
    assert fortigate.payload("POST", "firewall/addrgrp", "GRP_TESTKUNDE-AS_ALL-INTERNAL")[
        "member"
    ] == [
        {"name": "NET_TESTKUNDE-AS_LAN"},
        {"name": "NET_TESTKUNDE-AS_SERVERE"},
        {"name": "NET_TESTKUNDE-AS_GJEST"},
        {"name": "NET_TESTKUNDE-AS_MANAGEMENT"},
    ]
    dhcp_lan = fortigate.calls[CLEAN_RUN.index(("POST", "system.dhcp/server"))][2]
    assert dhcp_lan["interface"] == "internal"
    assert dhcp_lan["options"] == [{"id": 1, "code": 43, "type": "hex", "value": "0104c0000232"}]

    policies = [
        body["name"] for m, p, body in fortigate.calls if (m, p) == ("POST", "firewall/policy")
    ]
    assert policies == [
        "TESTKUNDE-AS_LAN-to-WAN_ALLOW",
        "TESTKUNDE-AS_SERVERE-to-WAN",
        "TESTKUNDE-AS_GJEST-to-WAN",
        "TESTKUNDE-AS_MANAGEMENT-to-ALL",
        "TESTKUNDE-AS_MGMT-PORT-to-ALL",
        "TESTKUNDE-AS_SERVERE-INTERNAL_DENY",
        "TESTKUNDE-AS_GJEST-INTERNAL_DENY",
        "TESTKUNDE-AS_LAN-INTERNAL_DENY",
        "TESTKUNDE-AS_VPN-to-ALL_ADMIN",
        "TESTKUNDE-AS_VPN-to-WAN_NAT",
    ]
    assert fortigate.calls[-1] == (
        "PUT",
        "system/interface/internal",
        {
            "alias": "TESTKUNDE-AS-LAN",
            "mode": "static",
            "ip": "10.42.0.1 255.255.255.0",
            "allowaccess": "ping https ssh",
            "description": "LAN — 10.42.0.0/24",
        },
    )


async def test_the_session_ntp_list_is_not_padded_in_place(fortigate):
    wizard = {**WIZARD, 3: {"ntp_servers": ["ntp.example.test"]}}
    await _deploy(wizard=wizard)
    assert wizard[3]["ntp_servers"] == ["ntp.example.test"]
    assert fortigate.payload("PUT", "system/ntp")["ntpserver"] == [
        {"id": 1, "server": "ntp.example.test"},
        {"id": 2, "server": "0.pool.ntp.org"},
        {"id": 3, "server": "1.pool.ntp.org"},
    ]


# ── REST: an object that already exists ─────────────────────────────────────


async def test_a_fortios_duplicate_is_updated_in_place(fortigate):
    fortigate.answer("POST", "system/interface", fortios_error(-5), name="V010_SERVERE")

    result = await _deploy()

    i = fortigate.calls.index(
        ("POST", "system/interface", fortigate.payload("POST", "system/interface", "V010_SERVERE"))
    )
    method, path, body = fortigate.calls[i + 1]
    assert (method, path) == ("PUT", "system/interface/V010_SERVERE")
    assert body["name"] == "V010_SERVERE"
    op = _step(result, "vlan_interfaces").operations[0]
    assert op.status is StepStatus.APPLIED
    assert "Fantes fra før" in op.reason
    assert result.ok is True


@pytest.mark.parametrize("code", [-15, -100])
async def test_every_documented_duplicate_code_counts(fortigate, code):
    fortigate.answer("POST", "user/local", fortios_error(code), name="sybr_admin")
    result = await _deploy()
    assert ("PUT", "user/local/sybr_admin") in fortigate.writes
    assert result.ok is True


async def test_a_duplicate_policy_is_updated_by_its_policyid(fortigate):
    name = "TESTKUNDE-AS_LAN-to-WAN_ALLOW"
    fortigate.answer("POST", "firewall/policy", fortios_error(-5), name=name)
    fortigate.reads["firewall/policy"] = ApiList([{"policyid": 7, "name": name}])

    result = await _deploy()

    assert ("GET", "firewall/policy", {"filter": f"name=={name}"}) in fortigate.calls
    assert ("PUT", "firewall/policy/7") in fortigate.writes
    assert ("PUT", f"firewall/policy/{name}") not in fortigate.writes
    assert result.ok is True


async def test_a_duplicate_that_names_its_id_is_updated_there(fortigate):
    name = "TESTKUNDE-AS_LAN-to-WAN_ALLOW"
    response = fortios_error(-5, text=f"Name '{name}' already used by policy '12'")
    fortigate.answer("POST", "firewall/policy", response, name=name)

    await _deploy()

    assert ("PUT", "firewall/policy/12") in fortigate.writes
    assert not any(m == "GET" and p == "firewall/policy" for m, p, _ in fortigate.calls)


async def test_a_duplicate_policy_that_cannot_be_found_fails(fortigate):
    name = "TESTKUNDE-AS_LAN-to-WAN_ALLOW"
    fortigate.answer("POST", "firewall/policy", fortios_error(-5), name=name)
    fortigate.reads["firewall/policy"] = ApiList([])

    result = await _deploy()

    assert result.ok is False
    assert result.stopped_at.name == "firewall_policies"
    assert "policyid" in result.stopped_at.reason


# ── REST: failures ───────────────────────────────────────────────────────────


async def test_a_500_that_is_not_a_duplicate_fails_and_is_not_overwritten(fortigate):
    # -651 is FortiOS's "input value is invalid". The old deploy took every 500
    # for "already exists" and PUT the same payload over whatever was there.
    bad = "NET_TESTKUNDE-AS_GJEST"
    fortigate.answer("POST", "firewall/address", fortios_error(-651, "invalid subnet"), name=bad)

    result = await _deploy()

    assert fortigate.calls[-1][:2] == ("POST", "firewall/address")
    assert fortigate.calls[-1][2]["name"] == bad
    assert not any(m == "PUT" and p.startswith("firewall/address") for m, p in fortigate.writes)
    assert result.ok is False
    stop = result.stopped_at
    assert stop.name == "address_objects"
    assert (
        "-651" in stop.reason and "ugyldig verdi" in stop.reason and "invalid subnet" in stop.reason
    )
    assert [op.status for op in stop.operations] == [
        StepStatus.APPLIED,
        StepStatus.APPLIED,
        StepStatus.FAILED,
    ]


async def test_a_500_without_a_fortios_code_is_a_failure(fortigate):
    response = FakeResponse(500, ValueError("not json"), text="Internal Server Error")
    fortigate.answer("POST", "firewall/addrgrp", response)

    result = await _deploy()

    assert result.ok is False
    assert result.stopped_at.name == "address_group"
    assert result.stopped_at.reason.endswith("HTTP 500")
    assert ("PUT", "firewall/addrgrp/GRP_TESTKUNDE-AS_ALL-INTERNAL") not in fortigate.writes


async def test_a_timeout_fails_the_step_and_stops_the_run(fortigate):
    fortigate.answer("PUT", "system/dns", httpx.ReadTimeout("timed out"))

    result = await _deploy()

    assert fortigate.calls[-1][:2] == ("PUT", "system/dns")
    assert result.ok is False
    assert result.stopped_at.name == "dns"
    assert "Tidsavbrudd" in result.stopped_at.reason
    assert _statuses(result)["ntp"] is StepStatus.NOT_RUN
    assert "«DNS» feilet" in _step(result, "ntp").reason


async def test_a_mid_run_failure_reports_exactly_what_was_applied(fortigate):
    fortigate.answer("POST", "system/interface", fortios_error(-651), name="V020_GJEST")

    result = await _deploy()

    statuses = _statuses(result)
    assert [statuses[n] for n in STEP_ORDER[:6]] == [StepStatus.APPLIED] * 6
    assert statuses["vlan_interfaces"] is StepStatus.FAILED
    assert all(statuses[n] is StepStatus.NOT_RUN for n in STEP_ORDER[7:])
    vlan_ops = _step(result, "vlan_interfaces").operations
    assert [(op.label, op.status) for op in vlan_ops] == [
        ("VLAN 10 (Servere)", StepStatus.APPLIED),
        ("VLAN 20 (Gjest)", StepStatus.FAILED),
    ]
    # VLAN 99 was never attempted, and the LAN address was never touched.
    assert ("PUT", "system/interface/internal") not in fortigate.writes
    assert fortigate.sequence == CLEAN_RUN[:9]

    out = result.as_dict()
    assert out["ok"] is False
    assert out["stopped_at"] == "vlan_interfaces"
    assert out["applied_steps"] == STEP_ORDER[1:6]
    assert out["failed"] == 1
    assert out["not_run"] == len(STEP_ORDER) - 7
    assert out["error"].startswith("VLAN-grensesnitt: VLAN 20 (Gjest): HTTP 500, FortiOS-feil -651")
    assert out["lan_ip_changed"] is False
    assert out["customer_updated"] is False
    assert "vpn" not in out["config_summary"]  # no credentials for a tunnel that is not there


async def test_an_unreadable_device_gets_no_writes(fortigate):
    fortigate.reads["system/interface"] = ApiList(error="HTTP 401")

    result = await _deploy()

    assert fortigate.writes == []
    assert result.ok is False
    assert result.stopped_at.name == "discover"
    assert "HTTP 401" in result.stopped_at.reason
    assert result.applied_steps == []


async def test_a_failed_dhcp_lookup_fails_instead_of_adding_a_second_server(fortigate):
    fortigate.reads["system.dhcp/server"] = ApiList(error="HTTP 500")

    result = await _deploy()

    assert ("POST", "system.dhcp/server") not in fortigate.writes
    assert result.stopped_at.name == "dhcp_servers"


async def test_an_existing_dhcp_server_is_updated_by_id(fortigate):
    fortigate.reads["system.dhcp/server"] = ApiList([{"id": 4, "interface": {"name": "internal"}}])
    result = await _deploy()
    assert ("PUT", "system.dhcp/server/4") in fortigate.writes
    assert result.ok is True


async def test_a_step_that_crashes_is_recorded_and_stops_the_run(fortigate):
    fortigate.reads["system.dhcp/server"] = ApiList([{"interface": "internal"}])  # no id

    result = await _deploy()

    assert result.stopped_at.name == "dhcp_servers"
    assert "Uventet feil: KeyError" in result.stopped_at.reason
    assert _statuses(result)["firewall_policies"] is StepStatus.NOT_RUN


async def test_without_a_token_the_device_is_never_contacted(fortigate):
    result = await _deploy(conn={**CONN, "api_token": ""})

    assert fortigate.opened == [] and fortigate.calls == []
    assert [(s.name, s.status) for s in result.steps] == [("preflight", StepStatus.FAILED)]
    out = result.as_dict()
    # The wizard renders "failed"; a zero there used to read as success.
    assert out["failed"] == 1 and out["ok"] is False


async def test_the_missing_connection_is_an_internal_error_not_a_fallback():
    with pytest.raises(ValueError):
        await provisioning._deploy_via_rest("192.0.2.1", "T", WIZARD, conn=None)


# ── REST: optional steps ─────────────────────────────────────────────────────


async def test_a_failed_optional_step_is_reported_and_the_run_goes_on(fortigate):
    fortigate.answer("PUT", "log/setting", fortios_error(-651))

    result = await _deploy()

    assert _statuses(result)["logging"] is StepStatus.FAILED
    assert ("PUT", "log.syslogd/setting") not in fortigate.writes
    assert fortigate.sequence[-1] == ("PUT", "system/interface/internal")
    assert result.ok is True  # every required step applied
    assert [s.name for s in result.warnings] == ["logging"]
    assert result.as_dict()["failed"] == 1
    assert "valgfritt steg feilet" in result.summary()


async def test_a_failed_mgmt_port_gets_no_mgmt_policy(fortigate):
    fortigate.answer("PUT", "system/interface/internal5", fortios_error(-651))

    result = await _deploy()

    assert _statuses(result)["mgmt_port"] is StepStatus.FAILED
    policies = [b["name"] for m, p, b in fortigate.calls if (m, p) == ("POST", "firewall/policy")]
    assert "TESTKUNDE-AS_MGMT-PORT-to-ALL" not in policies
    assert result.ok is True


async def test_no_free_port_skips_the_mgmt_step(fortigate):
    fortigate.reads["system/interface"] = ApiList(
        [
            {"name": "wan1", "type": "physical", "role": "wan", "ip": "203.0.113.10 255.255.255.0"},
            {
                "name": "internal",
                "type": "hard-switch",
                "role": "lan",
                "ip": "192.168.1.99 255.255.255.0",
            },
        ]
    )
    result = await _deploy()
    step = _step(result, "mgmt_port")
    assert step.status is StepStatus.SKIPPED
    assert "ledig" in step.reason
    assert result.ok is True


# ── REST: the LAN address and the customer record ────────────────────────────


@pytest.fixture()
def customers(monkeypatch):
    saved: list[dict] = []
    store = {
        "kunde-a": {
            "_id": "kunde-a",
            "_dir": "/tmp/x",
            "CustomerId": "kunde-a",
            "CustomerName": "Kunde A",
            "FortiGateHost": "192.0.2.1",
        }
    }
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer",
        staticmethod(lambda cid: dict(store[cid]) if cid in store else None),
    )
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_active",
        staticmethod(
            lambda: {"_id": "kunde-b", "CustomerId": "kunde-b", "CustomerName": "Kunde B"}
        ),
    )
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.save_customer",
        staticmethod(lambda cfg, **kw: saved.append(cfg) or cfg.get("CustomerId", "")),
    )
    return saved


async def test_a_confirmed_lan_change_updates_the_sessions_customer(fortigate, customers):
    result = await _deploy(conn={**CONN, "customer_id": "kunde-a"})

    assert result.ok is True
    assert result.extra["customer_updated"] is True
    # The session's customer, not the active one, and only the public keys.
    assert len(customers) == 1
    saved = customers[0]
    assert saved["CustomerId"] == "kunde-a"
    assert saved["FortiGateHost"] == "10.42.0.1"
    assert saved["FortiGatePort"] == 8443
    assert not any(k.startswith("_") for k in saved)


async def test_a_lan_change_without_an_answer_is_not_reported_as_applied(fortigate, customers):
    fortigate.answer("PUT", "system/interface/internal", httpx.ReadTimeout(""))

    result = await _deploy(conn={**CONN, "customer_id": "kunde-a"})

    step = _step(result, "lan_address")
    assert step.status is StepStatus.FAILED
    assert "https://10.42.0.1:8443" in step.reason
    assert "Tidsavbrudd" in step.reason
    assert result.ok is False
    # Unconfirmed: the customer record keeps the address that is known to work.
    assert customers == []
    assert result.extra["lan_ip_changed"] is False
    assert result.extra["customer_updated"] is False
    # Every other step did apply, and the VPN credentials are not lost.
    assert result.extra["config_summary"]["vpn"]["user_password"] == "p" * 20


async def test_an_unchanged_lan_address_is_still_applied(fortigate, customers):
    fortigate.reads["system/interface/internal"] = ApiDict({"ip": "10.42.0.1 255.255.255.0"})
    result = await _deploy(conn={**CONN, "customer_id": "kunde-a"})
    assert result.extra["lan_ip_changed"] is False
    assert customers[0]["FortiGateHost"] == "192.0.2.1"  # unchanged
    assert customers[0]["FortiGatePort"] == 8443


# ── SSH: a fake connection ───────────────────────────────────────────────────


class FakeSsh:
    """Stands in for SshSession: records every command, answers from a script."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.connects: list[tuple] = []
        self.connect_error: Exception | None = None
        self.answer = lambda command: CommandResult(0, "")

    async def connect(self, hostname, username, password=None, **kwargs) -> FakeSsh:
        self.connects.append((hostname, username, password))
        if self.connect_error:
            raise self.connect_error
        return self

    async def __aenter__(self) -> FakeSsh:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def exec(self, command: str, timeout: int = 30) -> CommandResult:
        self.sent.append(command)
        out = self.answer(command)
        if isinstance(out, BaseException):
            raise out
        return out


@pytest.fixture()
def ssh(monkeypatch) -> FakeSsh:
    fake = FakeSsh()
    monkeypatch.setattr("app.services.ssh_connection.SshSession", fake)
    return fake


CLI = """# FortiGate Configuration
config system global
    set hostname "TESTKUNDE"
end

config system admin
    edit admin
        set password "********"
    next
end

config firewall address
    edit "NET_A"
        set subnet 10.0.0.0 255.255.255.0
    next
end
"""

SSH_CONN = {**CONN, "admin_password": "login-pw"}


async def _ssh(cli: str = CLI, new_admin_password: str = "new-pw", conn: dict | None = None):
    return await provisioning._deploy_via_ssh(conn or SSH_CONN, cli, new_admin_password)


async def test_ssh_sends_each_block_whole_and_is_ok(ssh):
    result = await _ssh()

    assert ssh.connects == [("192.0.2.1", "admin", "login-pw")]
    assert ssh.sent == [
        'config system global\nset hostname "TESTKUNDE"\nend',
        # The new admin password from step 4, not the login password.
        'config system admin\nedit admin\nset password "new-pw"\nnext\nend',
        'config firewall address\nedit "NET_A"\nset subnet 10.0.0.0 255.255.255.0\nnext\nend',
    ]
    assert [(s.name, s.status) for s in result.steps] == [
        ("preflight", StepStatus.APPLIED),
        ("connect", StepStatus.APPLIED),
        ("cli_01", StepStatus.APPLIED),
        ("cli_02", StepStatus.APPLIED),
        ("cli_03", StepStatus.APPLIED),
    ]
    assert result.ok is True
    assert result.extra["commands"] == 13
    assert result.applied_steps == ["cli_01", "cli_02", "cli_03"]


async def test_ssh_a_line_the_device_refuses_fails_and_stops(ssh):
    def answer(command):
        if "set password" in command:
            return CommandResult(
                0, "value parse error before 'new-pw'\nCommand fail. Return code -651\n"
            )
        return CommandResult(0, "")

    ssh.answer = answer

    result = await _ssh()

    assert len(ssh.sent) == 2  # the block after the refusal is never sent
    assert result.ok is False
    stop = result.stopped_at
    assert stop.name == "cli_02"
    assert "Command fail. Return code -651" in stop.reason
    assert "new-pw" not in stop.reason  # the echoed password is masked
    assert _statuses(result)["cli_03"] is StepStatus.NOT_RUN
    assert result.extra["commands"] == 3  # only the first block's lines were taken
    assert result.applied_steps == ["cli_01"]


async def test_ssh_a_positive_exit_status_is_a_refusal(ssh):
    ssh.answer = lambda command: CommandResult(1, "")
    result = await _ssh()
    assert result.stopped_at.name == "cli_01"
    assert "kode 1" in result.stopped_at.reason


async def test_ssh_a_missing_exit_status_alone_is_not_a_refusal(ssh):
    # FortiOS does not reliably send an exit status; SshSession reports -1.
    ssh.answer = lambda command: CommandResult(-1, "")
    result = await _ssh()
    assert result.ok is True


async def test_ssh_a_command_without_an_answer_fails(ssh):
    ssh.answer = lambda command: IntegrationError("SSH-kommandoen timet ut etter 30s")
    result = await _ssh()
    assert result.stopped_at.name == "cli_01"
    assert "Ingen bekreftelse" in result.stopped_at.reason
    assert len(ssh.sent) == 1


async def test_ssh_a_line_outside_the_allowlist_fails_before_connecting(ssh):
    cli = CLI + "execute factoryreset\n"

    result = await _ssh(cli)

    assert ssh.connects == [] and ssh.sent == []
    assert [(s.name, s.status) for s in result.steps] == [("preflight", StepStatus.FAILED)]
    assert "execute factoryreset" in result.steps[0].reason
    assert "Ingenting er sendt" in result.steps[0].reason
    assert result.ok is False


@pytest.mark.parametrize(
    "cli,needle",
    [
        ("config system global\nset hostname x\n", "uten avsluttende"),
        ("end\n", "uten «config»"),
        ("# only comments\n\n", "ingen kommandoer"),
        ("next-thing\n", "ikke tillatt"),
    ],
)
async def test_ssh_malformed_cli_fails_before_connecting(ssh, cli, needle):
    result = await _ssh(cli)
    assert ssh.connects == []
    assert needle in result.steps[0].reason


async def test_ssh_a_masked_password_needs_the_new_admin_password(ssh):
    result = await _ssh(new_admin_password="")
    assert ssh.connects == []
    assert "steg 4" in result.steps[0].reason


async def test_ssh_a_password_that_could_inject_cli_is_refused(ssh):
    result = await _ssh(new_admin_password='x"\nexecute factoryreset')
    assert ssh.connects == [] and ssh.sent == []
    assert result.ok is False


async def test_ssh_a_failed_connection_is_reported(ssh):
    ssh.connect_error = IntegrationError("Vertsnøkkelen er endret")
    result = await _ssh()
    assert [(s.name, s.status) for s in result.steps] == [
        ("preflight", StepStatus.APPLIED),
        ("connect", StepStatus.FAILED),
    ]
    assert "Vertsnøkkelen" in result.stopped_at.reason
    assert ssh.sent == []


async def test_ssh_without_a_password_nothing_is_tried(ssh):
    result = await _ssh(conn={**SSH_CONN, "admin_password": ""})
    assert ssh.connects == []
    assert result.as_dict()["failed"] == 1


@pytest.mark.parametrize("with_admin_password", [True, False])
async def test_the_cli_template_only_holds_lines_the_ssh_deploy_sends(ssh, with_admin_password):
    # The template used to emit "config system session-helper / purge", which
    # the allowlist always refused: skipped silently then, a failed deploy now.
    network = {**provisioning.generate_subnets("Testkunde AS"), "fg_ports": 10}
    security = {"admin_password": "new-pw"} if with_admin_password else {}
    cli = provisioning._generate_fortigate_cli(
        {"name": "Testkunde AS"}, network, {"syslog_server": "198.51.100.5"}, security
    )
    assert "purge" not in cli

    result = await _ssh(cli, new_admin_password=security.get("admin_password", ""))

    assert result.ok is True, result.error or result.steps[0].reason
    assert all(s.status is StepStatus.APPLIED for s in result.steps)
    assert any('set password "new-pw"' in block for block in ssh.sent) is with_admin_password


# ── deploy_config ────────────────────────────────────────────────────────────


@pytest.fixture()
def session(monkeypatch):
    monkeypatch.setattr("app.core.customer.CustomerManager.get_active", staticmethod(lambda: None))
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer", staticmethod(lambda cid: None)
    )
    provisioning._sessions.clear()
    sid = provisioning.start_session("u1")["session_id"]
    raw = provisioning._sessions[sid]
    raw["steps"][1] = {"name": "Testkunde AS", "target_host": "192.0.2.1", "password": "login-pw"}
    raw["steps"][4] = {"admin_password": "new-pw"}
    raw["generated"] = {"fortigate_cli": CLI}
    yield raw
    provisioning._sessions.clear()


async def test_deploy_config_is_ok_only_when_every_device_is(ssh, session, monkeypatch):
    async def unifi_refused(*args, **kwargs):
        return {"ok": False, "error": "No UniFi credentials available"}

    monkeypatch.setattr(provisioning, "_deploy_unifi", unifi_refused)
    session["generated"]["unifi_json"] = "{}"

    report = await provisioning.deploy_config(session["id"], method="ssh")

    assert report.results["fortigate"].ok is True
    assert report.results["unifi"].ok is False
    assert report.ok is False  # used to be True no matter what
    out = report.as_dict()
    assert out["ok"] is False
    assert out["error"].startswith("unifi: UniFi-nettverk: No UniFi credentials")
    assert out["results"]["unifi"]["failed"] == 1


async def test_deploy_config_reports_a_refused_ssh_line(ssh, session):
    ssh.answer = lambda command: CommandResult(0, "Command fail. Return code -61")
    report = await provisioning.deploy_config(session["id"], method="ssh")
    assert report.ok is False
    assert report.changed_device is False
    assert report.as_dict()["results"]["fortigate"]["stopped_at"] == "cli_01"


async def test_an_unknown_method_is_refused_not_ignored(session):
    with pytest.raises(ValidationError):
        await provisioning.deploy_config(session["id"], method="telnet")


async def test_no_host_is_a_failed_report(session):
    session["steps"][1] = {"name": "Testkunde AS"}
    report = await provisioning.deploy_config(session["id"], method="ssh")
    assert report.ok is False
    assert report.as_dict() == {"ok": False, "error": report.error, "results": {}}
    assert "host" in report.error


# ── The route ────────────────────────────────────────────────────────────────


@pytest.fixture()
async def admin_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app.core.database as db_mod
    import app.web.middleware.rate_limit as rl
    from app.core.auth import create_access_token, create_user
    from app.core.database import run_migrations
    from app.core.rbac import set_can_write, set_tenant_write
    from app.models.user import Role
    from app.web.middleware.auth import _reset_users_exist_cache
    from app.web.server import create_app

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    customer = {"_id": "testkunde", "CustomerName": "Testkunde AS", "FortiGateHost": "192.0.2.1"}
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_active", staticmethod(lambda: dict(customer))
    )
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer",
        staticmethod(lambda cid: dict(customer) if cid == "testkunde" else None),
    )
    activity: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.core.activity_log.log_activity",
        lambda action, detail="", customer="", user="": activity.append((action, detail)),
    )
    u = await create_user("boss", "Str0ng-Passphrase-For-Tests!", "Boss", role=Role.admin)
    await set_can_write(u.id, True)
    await set_tenant_write(u.id, True)
    token = await create_access_token(u)
    provisioning._sessions.clear()
    with TestClient(create_app()) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c, activity
    provisioning._sessions.clear()
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


def _start_with_config(client) -> str:
    sid = client.post("/api/provisioning/start").json()["session_id"]
    client.put(
        f"/api/provisioning/{sid}/step/1",
        json={"name": "Testkunde AS", "target_host": "192.0.2.1", "password": "login-pw"},
    )
    client.put(f"/api/provisioning/{sid}/step/4", json={"admin_password": "new-pw"})
    provisioning._sessions[sid]["generated"] = {"fortigate_cli": CLI}
    return sid


async def test_the_route_returns_the_structured_result(admin_client, ssh):
    client, activity = admin_client
    ssh.answer = lambda cmd: (
        CommandResult(0, "Command fail. Return code -61")
        if "set password" in cmd
        else CommandResult(0, "")
    )
    sid = _start_with_config(client)

    r = client.post(f"/api/provisioning/{sid}/deploy", json={"method": "ssh"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    fg = body["results"]["fortigate"]
    assert fg["ok"] is False
    assert fg["stopped_at"] == "cli_02"
    assert fg["applied_steps"] == ["cli_01"]
    assert [s["status"] for s in fg["steps"]] == [
        "applied",
        "applied",
        "applied",
        "failed",
        "not_run",
    ]
    assert "new-pw" not in r.text and "login-pw" not in r.text
    # The first block changed the device, so this is a partial deploy.
    assert activity[-1][0] == "provisioning_deploy_partial"
    assert "stoppet ved" in activity[-1][1]


async def test_the_route_files_a_clean_deploy_as_completed(admin_client, ssh):
    client, activity = admin_client
    sid = _start_with_config(client)
    r = client.post(f"/api/provisioning/{sid}/deploy", json={"method": "ssh"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert activity[-1][0] == "provisioning_deploy_completed"


async def test_deploying_nothing_generated_is_a_400_not_a_crash(admin_client):
    client, activity = admin_client
    sid = client.post("/api/provisioning/start").json()["session_id"]

    r = client.post(f"/api/provisioning/{sid}/deploy", json={"method": "ssh"})

    assert r.status_code == 400
    assert "generert" in r.text
    assert activity[-1][0] == "provisioning_deploy_failed"
