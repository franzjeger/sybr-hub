"""The device clients tried once and gave up.

Graph has backed off since it was written. The write-side integrations were put
behind ``send_with_retry`` when they were built. The FortiGate and UniFi
clients — the two that talk to hardware at the far end of a VPN tunnel to a
customer site, where a transient failure is routine rather than exceptional —
had nothing. A controller answering 429 to the login every audit begins with
was recorded as an unreachable site.

The other half of this is the risk that adopting the layer introduced, and it
is the more interesting one. ``send_with_retry`` used to catch
``httpx.TimeoutException``, which covers ``ReadTimeout`` as well as
``ConnectTimeout``, and retried it for any method on the reasoning that a
connection which never opened cannot have applied a write. A read timeout means
the request *was* sent. Putting FortiGate and UniFi configuration writes behind
that would have made "the answer got lost" and "apply it again" the same thing.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.modules.api_result import read_failed

_real_sleep = asyncio.sleep


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    async def _instant(_seconds):
        await _real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _instant)


def _counting(responses):
    """A MockTransport handler walking `responses`, counting requests."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        item = responses[i]
        if isinstance(item, Exception):
            raise item
        return item

    return handler, calls


# ── FortiGate ────────────────────────────────────────────────────────────────

def _fortigate(handler):
    from app.modules.fortigate_audit.client import FortiGateClient

    fg = FortiGateClient("10.0.0.1", api_token="t", verify_ssl=False)
    fg._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=fg.base_url,
        headers=fg._client.headers,
    )
    return fg


async def test_a_throttled_fortigate_read_is_retried():
    handler, calls = _counting([
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"results": [{"name": "port1"}]}),
    ])
    fg = _fortigate(handler)
    result = await fg.get_cmdb("system/interface")
    await fg.close()

    assert calls["n"] == 2
    assert result == [{"name": "port1"}]


async def test_a_flaky_tunnel_does_not_lose_the_whole_read():
    """The case this exists for: the tunnel drops, the retry lands."""
    handler, calls = _counting([
        httpx.ConnectError("no route to host"),
        httpx.Response(200, json={"results": []}),
    ])
    fg = _fortigate(handler)
    assert await fg.get_cmdb("firewall/policy") == []
    await fg.close()
    assert calls["n"] == 2


async def test_a_fortigate_that_stays_down_reports_an_error_not_a_crash():
    """A section that cannot read its device must degrade, not raise."""
    handler, calls = _counting([httpx.ConnectError("down")])
    fg = _fortigate(handler)
    result = await fg.get_monitor("system/status")
    await fg.close()

    assert calls["n"] == 3, "should have used its attempts"
    assert read_failed(result), "a stayed-down read must be marked failed, not empty-clean"


async def test_a_403_is_not_retried():
    """Permission does not improve on a second attempt, and an audit that
    retries every refusal takes three times as long to say the same thing."""
    handler, calls = _counting([httpx.Response(403)])
    fg = _fortigate(handler)
    result = await fg.get_cmdb("firewall/policy")
    await fg.close()

    assert calls["n"] == 1
    assert read_failed(result), "a refused read must carry its error, not read as clean"


# ── UniFi controller ─────────────────────────────────────────────────────────

def _unifi(handler, *, is_unifi_os: bool = True):
    from app.modules.unifi_audit.client import UniFiControllerClient

    uf = UniFiControllerClient("https://10.0.0.2", "admin", "pw", is_unifi_os=is_unifi_os)
    uf._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=uf.host,
    )
    return uf


async def test_a_throttled_login_is_retried():
    """The call a controller rate-limits hardest, and the first one an audit
    makes — so giving up on it used to cost the entire site."""
    handler, calls = _counting([
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={}),
    ])
    uf = _unifi(handler)
    await uf._login()
    # Asserted before close(), which logs out and clears the flag.
    assert uf._logged_in is True
    assert calls["n"] >= 2
    await uf.close()


async def test_an_unreachable_controller_says_so_rather_than_wrong_password():
    """Two very different things for the operator reading the message."""
    handler, _ = _counting([httpx.ConnectError("refused")])
    uf = _unifi(handler)
    with pytest.raises(ConnectionError, match="unreachable"):
        await uf._login()
    await uf._client.aclose()


async def test_a_rejected_login_still_says_login_failed():
    handler, _ = _counting([httpx.Response(401)])
    uf = _unifi(handler)
    with pytest.raises(ConnectionError, match="login failed"):
        await uf._login()
    await uf._client.aclose()


async def test_a_throttled_device_read_is_retried():
    handler, calls = _counting([
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"data": [{"name": "ap-1"}]}),
    ])
    uf = _unifi(handler)
    devices = await uf.get_devices("default")
    await uf.close()

    assert calls["n"] == 2
    assert devices == [{"name": "ap-1"}]


async def test_a_controller_write_is_not_repeated_after_a_read_timeout():
    """The risk adopting the retry layer introduced.

    A POST to a controller changes something. If the answer is lost the change
    may well have been applied, and a second attempt applies it twice.
    """
    handler, calls = _counting([httpx.ReadTimeout("no answer")])
    uf = _unifi(handler)
    result = await uf._post("/api/s/default/cmd/devmgr", {"cmd": "restart"})
    await uf.close()

    assert calls["n"] == 1, "a write that may have landed must not be repeated"
    assert result["meta"]["rc"] == "error"


async def test_a_controller_write_is_retried_when_nothing_was_sent():
    """A connection that never opened carries no such risk."""
    handler, calls = _counting([
        httpx.ConnectError("refused"),
        httpx.Response(200, json={"data": [], "meta": {"rc": "ok"}}),
    ])
    uf = _unifi(handler)
    result = await uf._post("/api/s/default/cmd/devmgr", {"cmd": "restart"})
    await uf.close()

    assert calls["n"] == 2
    assert result["meta"]["rc"] == "ok"


async def test_a_failed_read_keeps_the_controllers_own_error_shape():
    """So a caller checking meta.rc catches a transport failure too, rather
    than a transport failure arriving as a shape nobody checks for."""
    handler, _ = _counting([httpx.ConnectError("down")])
    uf = _unifi(handler)
    data = await uf._get("/api/self/sites")
    await uf.close()

    assert data["meta"]["rc"] == "error"
    assert data["data"] == []


# ── Coverage ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module,label", [
    ("app.modules.fortigate_audit.client", "FortiGate"),
    ("app.modules.unifi_audit.client", "UniFi controller"),
    ("app.services.unifi_api", "UniFi Site Manager"),
    ("app.integrations.autotask", "Autotask"),
    ("app.integrations.myitprocess", "myITprocess"),
    ("app.integrations.itglue", "IT Glue"),
    ("app.integrations.also_cloud", "ALSO"),
    ("app.integrations.partner_center", "Partner Center"),
])
def test_every_upstream_client_goes_through_the_retry_layer(module, label):
    """The ratchet. Adding a client that calls the transport directly fails
    here rather than being discovered as a customer's audit that gave up on
    the first 429."""
    import importlib
    import inspect

    src = inspect.getsource(importlib.import_module(module))
    assert "send_with_retry" in src, f"{label} does not back off"


def test_graph_has_its_own_backoff_and_is_deliberately_not_in_that_list():
    """Named so the omission reads as a decision rather than an oversight.

    GraphClient waits on Retry-After itself, with paging and throttling
    behaviour the shared helper does not model.
    """
    import inspect

    from app.modules.m365_audit import graph_client

    src = inspect.getsource(graph_client)
    assert "Retry-After" in src or "retry_after" in src.lower()
