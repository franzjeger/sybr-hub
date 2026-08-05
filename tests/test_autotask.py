"""Autotask read side.

These tests pin what the client *sends*. They prove nothing about what
Autotask replies — the client was written against the published reference and
has never spoken to a live instance, because no customer here has Autotask
credentials. That gap is real and named in the module docstring; the way to
close it is test_connection() against a real tenant.

What they do catch: a query built against the wrong entity or the wrong
field name, a filter silently dropped, and — the one that matters — a failed
call turning into an empty list.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.integrations.autotask import AutotaskClient, AutotaskError

_ZONE = {"zoneName": "z12", "url": "https://webservices12.autotask.net/atservicesrest/"}


def _client(handler) -> AutotaskClient:
    c = AutotaskClient("code", "api@user.no", "secret")
    c._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=c._client.headers,
    )
    return c


def _run(coro):
    return asyncio.run(coro)


def test_zone_discovery_happens_before_anything_else():
    """Every other call goes to the zone URL; the default host 404s."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "zoneInformation" in str(request.url):
            return httpx.Response(200, json=_ZONE)
        return httpx.Response(200, json={"items": [], "pageDetails": {}})

    c = _client(handler)
    _run(c.list_accounts())

    assert "zoneInformation" in seen[0]
    assert "user=api%40user.no" in seen[0] or "user=api@user.no" in seen[0]
    assert seen[1].startswith("https://webservices12.autotask.net/atservicesrest/V1.0/")


def test_accounts_query_asks_companies_for_active_records():
    """The REST entity is Companies; the UI's word for it is Account."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "zoneInformation" in str(request.url):
            return httpx.Response(200, json=_ZONE)
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"items": [{"id": 1, "companyName": "Acme"}]})

    c = _client(handler)
    out = _run(c.list_accounts(name_filter="Acm", limit=10))

    assert captured["url"].endswith("/V1.0/Companies/query")
    assert captured["body"]["MaxRecords"] == 10
    fields = {f["field"]: f for f in captured["body"]["Filter"]}
    assert fields["isActive"]["value"] is True, "archived companies must not be offered"
    assert fields["companyName"]["op"] == "contains"
    assert out[0]["companyName"] == "Acme"


def test_contracts_are_filtered_by_company_and_status():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "zoneInformation" in str(request.url):
            return httpx.Response(200, json=_ZONE)
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"items": []})

    c = _client(handler)
    _run(c.list_contracts_for_account(42))

    assert captured["url"].endswith("/V1.0/Contracts/query")
    fields = {f["field"]: f["value"] for f in captured["body"]["Filter"]}
    assert fields["companyID"] == 42
    assert fields["status"] == 1


def test_no_match_is_none_and_a_broken_call_is_not():
    """An id that does not exist is None. A call that could not run raises."""
    def found_nothing(request: httpx.Request) -> httpx.Response:
        if "zoneInformation" in str(request.url):
            return httpx.Response(200, json=_ZONE)
        return httpx.Response(200, json={"items": []})

    assert _run(_client(found_nothing).get_account(7)) is None

    def refused(request: httpx.Request) -> httpx.Response:
        if "zoneInformation" in str(request.url):
            return httpx.Response(200, json=_ZONE)
        return httpx.Response(401, text="bad credentials")

    with pytest.raises(AutotaskError, match="401"):
        _run(_client(refused).get_account(7))


def test_an_unexpected_shape_raises_rather_than_reading_as_empty():
    """The failure this codebase keeps finding, refused entry here.

    A 200 without `items` is not "no companies" — it is a response nobody
    modelled, and returning [] for it would put "this customer has no
    contracts" in front of a technician on the strength of it.
    """
    def odd(request: httpx.Request) -> httpx.Response:
        if "zoneInformation" in str(request.url):
            return httpx.Response(200, json=_ZONE)
        return httpx.Response(200, json={"error": "something else entirely"})

    with pytest.raises(AutotaskError, match="unexpected shape"):
        _run(_client(odd).list_accounts())


def test_test_connection_reports_the_field_names_it_saw():
    """The step that closes the verification gap once credentials exist."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "zoneInformation" in str(request.url):
            return httpx.Response(200, json=_ZONE)
        return httpx.Response(200, json={"items": [
            {"id": 1, "companyName": "Acme", "classification": 3, "isActive": True}
        ]})

    result = _run(_client(handler).test_connection())
    assert result["ok"] is True
    assert result["zone_url"].startswith("https://webservices12.")
    assert result["sample_fields"] == ["classification", "companyName", "id", "isActive"]


def test_test_connection_reports_a_failure_instead_of_raising():
    """It is a diagnostic. Raising would hide the thing being diagnosed."""
    def refused(request: httpx.Request) -> httpx.Response:
        if "zoneInformation" in str(request.url):
            return httpx.Response(200, json=_ZONE)
        return httpx.Response(401, text="nope")

    result = _run(_client(refused).test_connection())
    assert result["ok"] is False
    assert "401" in result["error"]


def test_the_write_side_is_still_refused():
    """The workshop put an operator in this loop. Keep them there."""
    c = AutotaskClient("code", "user", "secret")
    with pytest.raises(NotImplementedError, match="write-side"):
        _run(c.create_ticket(1, "title", "body"))


def test_queries_go_through_the_retry_layer():
    import pathlib

    src = pathlib.Path("app/integrations/autotask.py").read_text()
    assert "send_with_retry" in src
    bare = [
        line.strip() for line in src.splitlines()
        if "await self._client." in line
        and not any(k in line for k in ("aclose", "send_with_retry"))
    ]
    assert not bare, f"calls the transport directly: {bare}"


def test_the_settings_can_be_saved_and_not_just_read():
    """A key the GET reports but the POST ignores can never be set.

    Reading them back was the easy half; without the save branch the settings
    screen would show empty fields, accept input and silently discard it.
    """
    import pathlib

    src = pathlib.Path("app/web/routes/settings.py").read_text()
    for key in (
        "autotask_integration_code", "autotask_username",
        "autotask_secret", "autotask_zone_url",
    ):
        assert src.count(key) >= 2, f"{key} is read but never written"
    # And the masked placeholder must not be stored as if it were the secret.
    assert '"autotask_integration_code", "autotask_secret"' in src


def test_the_secrets_are_masked_on_the_way_out():
    import pathlib

    src = pathlib.Path("app/web/routes/settings.py").read_text()
    for key in ("autotask_integration_code", "autotask_secret"):
        assert f'"{key}": "••••••" if settings.get("{key}")' in src, (
            f"{key} is returned in clear text"
        )
