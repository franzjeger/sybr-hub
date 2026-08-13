"""The other bucket: something to plan, not something to fix this week.

Same guards and same idempotency as the Autotask ticket, so most of what is
asserted here is that the shared ``_push_finding`` really is shared — a second
copy of those seven steps is a second chance to get the duplicate-race handling
wrong.

Two things are genuinely different and get their own tests.

**A finding may have both.** The uniqueness is per system, so a DKIM gap can be
a ticket *and* a recommendation. What must not happen is two recommendations
for one finding: they arrive in the customer's quarterly review as two agenda
items nobody can tell apart.

**Nothing here has met a real server.** ``app.myitprocess.com`` was unreachable
from the environment this was built in, so the request shape comes from the
contract the old stub declared rather than from a document somebody read. The
client is therefore written to be diagnosable — a response it cannot read says
what it got — and these tests pin *that* behaviour rather than pretending to
verify field names.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.integrations.myitprocess import MyITProcessClient, MyITProcessError
from app.models.user import Role, User
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

_CUSTOMER_ID = "acme"
_REC_ID = "rec_dmarc_title:acme.no"
_ACCOUNT = "mip-4242"


@pytest.fixture(autouse=True)
def _reset_middleware_state():
    import app.web.middleware.rate_limit as rl

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


@pytest.fixture(autouse=True)
def _customer(monkeypatch):
    from app.core.customer import CustomerManager

    record = {
        "CustomerId": _CUSTOMER_ID,
        "CustomerName": "Acme AS",
        "MyITProcessAccountId": _ACCOUNT,
        "AutotaskAccountId": 4242,
    }
    monkeypatch.setattr(
        CustomerManager, "get_customer",
        staticmethod(lambda cid: dict(record) if cid == _CUSTOMER_ID else None),
    )
    return record


@pytest.fixture(autouse=True)
def _configured():
    from app.core.config import load_app_settings, save_app_settings

    settings = load_app_settings()
    settings["myitprocess_api_key"] = "mip-key"
    save_app_settings(settings)


@pytest.fixture(autouse=True)
def _one_finding(monkeypatch):
    from app.services import finding_tickets as ft

    def _find(customer_id, rec_id, lang):
        if customer_id != _CUSTOMER_ID or rec_id != _REC_ID:
            return None
        return ft.Finding(
            rec_id=_REC_ID,
            title="DMARC mangler på acme.no",
            detail="Domenet har ingen DMARC-post, så spoofing kan ikke oppdages.",
            priority="high",
            audit_date="2026-08-01_0900",
        )

    monkeypatch.setattr(ft, "find_recommendation", _find)


class _MyITProcess:
    """A stand-in that counts what it was asked to create."""

    def __init__(self, *, status: int = 200, body: dict | None = None):
        self.created: list[dict] = []
        self.status = status
        self.body = body
        self._next = 501

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": _ACCOUNT, "name": "Acme AS"}])
        self.created.append(json.loads(request.content))
        if self.status != 200:
            return httpx.Response(self.status, text="nope")
        if self.body is not None:
            return httpx.Response(200, json=self.body)
        rid = self._next
        self._next += 1
        return httpx.Response(200, json={"recommendationId": rid})


def _install(monkeypatch, fake: _MyITProcess) -> None:
    real_init = MyITProcessClient.__init__

    def _patched(self, *a, **kw):
        real_init(self, *a, **kw)
        self._client = httpx.AsyncClient(
            transport=httpx.MockTransport(fake.handler),
            headers=self._client.headers,
            base_url=self.base_url,
        )

    monkeypatch.setattr(MyITProcessClient, "__init__", _patched)


@pytest.fixture()
def mip(monkeypatch) -> _MyITProcess:
    fake = _MyITProcess()
    _install(monkeypatch, fake)
    return fake


async def _client_for(role: Role, *, can_write: bool) -> TestClient:
    from app.core.auth import get_user_by_id
    from app.core.rbac import set_all_customers, set_can_write

    user = await create_user(
        username=f"u_{role.value}_{int(can_write)}",
        password="Test1234!xyz", display_name="U", role=role,
    )
    await set_all_customers(user.id, True)
    if can_write:
        await set_can_write(user.id, True)
    user = await get_user_by_id(user.id)
    c = TestClient(create_app(), raise_server_exceptions=False)
    c.headers.update({"Authorization": f"Bearer {await create_access_token(user)}"})
    return c


@pytest.fixture()
async def operator():
    with await _client_for(Role.technician, can_write=True) as c:
        yield c


def _post(client, **overrides):
    body = {"rec_id": _REC_ID}
    body.update(overrides)
    return client.post(f"/api/hub/{_CUSTOMER_ID}/recommendations", json=body)


# ── Operator-initiated only ──────────────────────────────────────────────────

def test_nothing_scheduled_can_reach_the_write_side():
    import pathlib

    offenders = [
        rel for rel in (
            "app/core/scheduler.py",
            "app/services/scheduler.py",
            "app/services/site_collector.py",
            "app/services/alert_engine.py",
            "app/services/webhook_sender.py",
        )
        if pathlib.Path(rel).exists()
        and "myitprocess" in pathlib.Path(rel).read_text().lower()
    ]
    assert not offenders, f"unattended code reaching myITprocess: {offenders}"


async def test_a_viewer_cannot_push_a_recommendation(mip):
    with await _client_for(Role.viewer, can_write=True) as c:
        assert _post(c).status_code == 403
    assert mip.created == []


async def test_a_technician_without_can_write_cannot_push(mip):
    with await _client_for(Role.technician, can_write=False) as c:
        assert _post(c).status_code == 403
    assert mip.created == []


# ── The happy path ───────────────────────────────────────────────────────────

async def test_an_operator_pushes_one_recommendation(operator, mip):
    r = _post(operator)
    assert r.status_code == 201, r.text
    assert r.json()["created"] is True
    assert r.json()["ticket"]["external_id"] == "501"
    assert len(mip.created) == 1


async def test_the_recommendation_carries_the_finding_and_its_source(operator, mip):
    _post(operator)
    sent = mip.created[0]
    assert sent["accountId"] == _ACCOUNT
    assert sent["title"] == "DMARC mangler på acme.no"
    assert "DMARC-post" in sent["description"]
    # Provenance travels to the other system too, not only in our database.
    assert sent["externalReferenceId"] == _REC_ID
    assert _REC_ID in sent["description"]


async def test_the_findings_priority_is_used_when_the_operator_picks_none(
    operator, mip
):
    """Otherwise a critical finding arrives in the review looking routine."""
    _post(operator)
    assert mip.created[0]["priority"] == "high"


async def test_the_operator_can_override_title_category_and_priority(operator, mip):
    _post(operator, title="E-postsikkerhet Q4", category="Security", priority="Low")
    sent = mip.created[0]
    assert sent["title"] == "E-postsikkerhet Q4"
    assert sent["category"] == "Security"
    assert sent["priority"] == "Low"


# ── Idempotency, and the one thing that differs from Autotask ────────────────

async def test_a_second_push_does_not_create_a_second_recommendation(operator, mip):
    first, second = _post(operator), _post(operator)
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert len(mip.created) == 1


async def test_a_finding_may_have_both_a_ticket_and_a_recommendation(operator, mip):
    """The uniqueness is per system. A DKIM gap can be fixed this week *and*
    planned properly next quarter, and blocking the second would be wrong."""
    from app.services.finding_tickets import (
        SYSTEM_AUTOTASK,
        SYSTEM_MYITPROCESS,
        get_ticket,
        record_ticket,
    )

    await record_ticket(
        _CUSTOMER_ID, _REC_ID, SYSTEM_AUTOTASK, "9001", "", "T", "alice",
    )
    r = _post(operator)

    assert r.json()["created"] is True, "an Autotask ticket must not block this"
    assert (await get_ticket(_CUSTOMER_ID, _REC_ID, SYSTEM_AUTOTASK)).external_id == "9001"
    assert (await get_ticket(_CUSTOMER_ID, _REC_ID, SYSTEM_MYITPROCESS)).external_id == "501"


async def test_the_two_lists_do_not_shadow_each_other(operator, mip):
    """One dict keyed on rec_id across both systems would drop whichever row
    the database returned second."""
    from app.services.finding_tickets import SYSTEM_AUTOTASK, record_ticket

    await record_ticket(
        _CUSTOMER_ID, _REC_ID, SYSTEM_AUTOTASK, "9001", "", "T", "alice",
    )
    _post(operator)

    tickets = operator.get(f"/api/hub/{_CUSTOMER_ID}/tickets").json()["tickets"]
    recs = operator.get(f"/api/hub/{_CUSTOMER_ID}/recommendations").json()["recommendations"]
    assert tickets[_REC_ID]["external_id"] == "9001"
    assert recs[_REC_ID]["external_id"] == "501"


# ── Refusals ─────────────────────────────────────────────────────────────────

async def test_an_unconfigured_install_is_refused_before_the_binding(operator, mip):
    from app.core.config import load_app_settings, save_app_settings

    settings = load_app_settings()
    settings.pop("myitprocess_api_key", None)
    save_app_settings(settings)

    r = _post(operator)
    assert r.status_code == 400
    assert "ikke konfigurert" in r.json()["error"]
    assert mip.created == []


async def test_a_customer_with_no_binding_is_refused(operator, mip, monkeypatch):
    from app.core.customer import CustomerManager

    monkeypatch.setattr(
        CustomerManager, "get_customer",
        staticmethod(lambda cid: {"CustomerId": cid, "CustomerName": "Acme AS"}),
    )
    r = _post(operator)
    assert r.status_code == 400
    assert mip.created == []


async def test_a_finding_the_latest_run_does_not_raise_is_refused(operator, mip):
    assert _post(operator, rec_id="rec_nope").status_code == 404
    assert mip.created == []


async def test_a_rejected_push_is_not_recorded(operator, monkeypatch):
    """A 400 means nothing exists there. A row would block every later push."""
    _install(monkeypatch, _MyITProcess(status=400))
    assert _post(operator).status_code >= 400

    from app.services.finding_tickets import SYSTEM_MYITPROCESS, get_ticket
    assert await get_ticket(_CUSTOMER_ID, _REC_ID, SYSTEM_MYITPROCESS) is None


async def test_an_unreadable_response_is_not_recorded(operator, monkeypatch):
    """Accepting a made-up id records something nobody can open, and blocks
    the retry that would have worked."""
    _install(monkeypatch, _MyITProcess(body={"status": "queued"}))
    r = _post(operator)
    assert r.status_code >= 400

    from app.services.finding_tickets import SYSTEM_MYITPROCESS, get_ticket
    assert await get_ticket(_CUSTOMER_ID, _REC_ID, SYSTEM_MYITPROCESS) is None


async def test_an_unknown_body_field_is_refused(operator, mip):
    assert _post(operator, queue_id=7).status_code == 422
    assert mip.created == []


# ── The client, on its own ───────────────────────────────────────────────────

def _direct(handler) -> MyITProcessClient:
    c = MyITProcessClient("key")
    c._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers=c._client.headers,
        base_url=c.base_url,
    )
    return c


async def test_a_create_is_never_retried_on_a_5xx():
    """A POST that applied the write and failed on the way out would become a
    second agenda item in the customer's review."""
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(500, text="boom")

    client = _direct(handler)
    with pytest.raises(MyITProcessError):
        await client.create_recommendation("a", "t", "d")
    await client.close()
    assert attempts["n"] == 1


@pytest.mark.parametrize("payload,expected", [
    ({"recommendationId": 7}, "7"),
    ({"id": "abc"}, "abc"),
    ({"itemId": 12}, "12"),
    ({"data": {"id": 99}}, "99"),
    (42, "42"),
    ("rec-7", "rec-7"),
])
async def test_the_id_is_found_in_the_shapes_worth_guessing(payload, expected):
    """Not one hard-coded key. Nothing here has seen the real response, so a
    single guess would be a coin flip with a silent wrong answer on the tails."""
    client = _direct(lambda r: httpx.Response(200, json=payload))
    assert await client.create_recommendation("a", "t", "d") == expected
    await client.close()


async def test_an_unrecognised_response_says_what_it_got():
    """So the first real run is diagnostic rather than mysterious."""
    client = _direct(lambda r: httpx.Response(200, json={"status": "queued"}))
    with pytest.raises(MyITProcessError, match="queued"):
        await client.create_recommendation("a", "t", "d")
    await client.close()


@pytest.mark.parametrize("payload", [
    [{"id": 1}],
    {"data": [{"id": 1}]},
    {"items": [{"id": 1}]},
])
async def test_a_list_is_read_bare_or_wrapped(payload):
    client = _direct(lambda r: httpx.Response(200, json=payload))
    assert len(await client.list_accounts()) == 1
    await client.close()


async def test_an_unreadable_list_raises_rather_than_returning_empty():
    """"We could not ask" and "there are none" must not look alike."""
    client = _direct(lambda r: httpx.Response(200, json={"nope": True}))
    with pytest.raises(MyITProcessError, match="unexpected shape"):
        await client.list_accounts()
    await client.close()


async def test_an_empty_list_is_a_real_answer():
    client = _direct(lambda r: httpx.Response(200, json=[]))
    assert await client.list_accounts() == []
    await client.close()


async def test_a_403_names_the_grant_that_is_missing():
    """Read access and write access are separate grants, and the difference is
    the whole content of a 403 here."""
    client = _direct(lambda r: httpx.Response(403, text=""))
    with pytest.raises(MyITProcessError, match="write access"):
        await client.create_recommendation("a", "t", "d")
    await client.close()


async def test_long_text_is_truncated_rather_than_refused():
    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"id": 1})

    client = _direct(handler)
    await client.create_recommendation("a", "T" * 400, "D" * 9000)
    await client.close()
    assert len(sent["title"]) == 200
    assert len(sent["description"]) == 8000


def test_the_deep_link_is_empty_for_a_custom_host():
    """A guessed path against somebody's own host goes somewhere wrong, which
    is worse than no link."""
    assert MyITProcessClient("k", base_url="https://mip.internal").recommendation_url("7") == ""
    assert MyITProcessClient("k").recommendation_url("7").endswith("/7")
