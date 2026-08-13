"""One finding becomes one ticket, and only an operator can make it happen.

The workshop rejected automatic ticket creation outright: operator discretion
is the workflow, not a setting on it. That promise is not kept by the client —
``AutotaskClient.create_ticket`` will raise a ticket for anyone who calls it —
so it has to be kept where callers are, and asserted rather than assumed. Hence
``test_nothing_scheduled_can_reach_the_write_side``.

The other half is idempotency. An audit re-runs weekly and a technician clicks
what looks unfamiliar; two clicks on one finding must not be two tickets in a
customer's PSA, because nobody reconciles those. The uniqueness is a database
constraint rather than a check in Python, and the tests below drive the case
that a check in Python would lose.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.integrations.autotask import AutotaskClient, AutotaskError
from app.models.user import Role, User
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

_CUSTOMER_ID = "acme"
_REC_ID = "rec_mfa_title"
_ZONE = {"url": "https://webservices12.autotask.net/atservicesrest/"}


# ── Fixtures ─────────────────────────────────────────────────────────────────

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
        "PrimaryDomain": "acme.no",
        "AutotaskAccountId": 4242,
    }
    monkeypatch.setattr(
        CustomerManager, "get_customer",
        staticmethod(lambda cid: dict(record) if cid == _CUSTOMER_ID else None),
    )
    return record


@pytest.fixture(autouse=True)
def _autotask_configured(monkeypatch):
    from app.core.config import load_app_settings, save_app_settings

    settings = load_app_settings()
    settings.update({
        "autotask_integration_code": "code",
        "autotask_username": "api@acme.no",
        "autotask_secret": "s3cret",
        "autotask_zone_url": _ZONE["url"],
    })
    save_app_settings(settings)


@pytest.fixture(autouse=True)
def _one_finding(monkeypatch):
    """The customer's latest run raises exactly one recommendation."""
    from app.services import finding_tickets as ft

    def _find(customer_id, rec_id, lang):
        if customer_id != _CUSTOMER_ID or rec_id != _REC_ID:
            return None
        return ft.Finding(
            rec_id=_REC_ID,
            title="3 brukere mangler MFA",
            detail="Tre kontoer har ingen sterk autentiseringsmetode registrert.",
            priority="critical",
            audit_date="2026-08-01_0900",
        )

    monkeypatch.setattr(ft, "find_recommendation", _find)
    # hub.py imports it inside the handler, so patching the source module is
    # what the handler actually sees.
    return _find


class _Autotask:
    """A stand-in Autotask that counts the tickets it was asked to create."""

    def __init__(self, *, create_status: int = 200, next_id: int = 9001):
        self.created: list[dict] = []
        self.create_status = create_status
        self._next_id = next_id

    def handler(self, request: httpx.Request) -> httpx.Response:
        if "zoneInformation" in str(request.url):
            return httpx.Response(200, json=_ZONE)
        if str(request.url).endswith("/V1.0/Tickets"):
            self.created.append(json.loads(request.content))
            if self.create_status != 200:
                return httpx.Response(self.create_status, text="nope")
            ticket_id = self._next_id
            self._next_id += 1
            return httpx.Response(200, json={"itemId": ticket_id})
        return httpx.Response(404, json={})


@pytest.fixture()
def autotask(monkeypatch) -> _Autotask:
    fake = _Autotask()
    real_init = AutotaskClient.__init__

    def _patched(self, *a, **kw):
        real_init(self, *a, **kw)
        self._client = httpx.AsyncClient(
            transport=httpx.MockTransport(fake.handler),
            headers=self._client.headers,
        )

    monkeypatch.setattr(AutotaskClient, "__init__", _patched)
    return fake


async def _client_for(role: Role, *, can_write: bool) -> TestClient:
    from app.core.auth import get_user_by_id
    from app.core.rbac import set_all_customers, set_can_write

    user = await create_user(
        username=f"u_{role.value}_{int(can_write)}",
        password="Test1234!xyz",
        display_name="U",
        role=role,
    )
    # Customer scope, always. Without it every account here is refused for
    # reaching the customer at all, and the role-floor tests below would pass
    # on the wrong 403 — which is exactly what happened the first time.
    await set_all_customers(user.id, True)
    if can_write:
        await set_can_write(user.id, True)
    user = await get_user_by_id(user.id)
    token = await create_access_token(user)
    c = TestClient(create_app(), raise_server_exceptions=False)
    c.headers.update({"Authorization": f"Bearer {token}"})
    return c


@pytest.fixture()
async def operator():
    with await _client_for(Role.technician, can_write=True) as c:
        yield c


@pytest.fixture()
async def admin():
    """Settings are admin-only; raising a ticket is not. Two different floors,
    so the tests need two different accounts."""
    with await _client_for(Role.admin, can_write=True) as c:
        yield c


def _post(client, **overrides):
    body = {"rec_id": _REC_ID}
    body.update(overrides)
    return client.post(f"/api/hub/{_CUSTOMER_ID}/tickets", json=body)


# ── The promise: operator-initiated only ─────────────────────────────────────

def test_nothing_scheduled_can_reach_the_write_side():
    """The workshop's rule, asserted instead of trusted.

    ``create_ticket`` has no guard of its own. Anything that runs unattended —
    the scheduler, the site collector, the alert engine — must not be able to
    call it, and the way to keep that true is to fail here when somebody adds
    the import.
    """
    import pathlib

    unattended = [
        "app/core/scheduler.py",
        "app/services/scheduler.py",
        "app/services/site_collector.py",
        "app/services/alert_engine.py",
        "app/services/webhook_sender.py",
    ]
    offenders = []
    for rel in unattended:
        path = pathlib.Path(rel)
        if not path.exists():
            continue
        src = path.read_text()
        if "create_ticket" in src or "finding_tickets" in src:
            offenders.append(rel)

    assert not offenders, (
        f"unattended code reaching the ticket write side: {offenders}"
    )


async def test_a_viewer_cannot_raise_a_ticket(autotask):
    """The stub's floor was `viewer`. Wiring it without raising that would have
    let a read-only account write into a customer's PSA."""
    with await _client_for(Role.viewer, can_write=True) as c:
        r = _post(c)
    assert r.status_code == 403
    assert autotask.created == []


async def test_a_technician_without_can_write_cannot_raise_a_ticket(autotask):
    """WriteGuard, not the route. The endpoint is not in its exemption table."""
    with await _client_for(Role.technician, can_write=False) as c:
        r = _post(c)
    assert r.status_code == 403
    assert autotask.created == []


async def test_an_unauthenticated_request_cannot_raise_a_ticket(autotask):
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        r = _post(c)
    assert r.status_code == 401
    assert autotask.created == []


# ── The happy path ───────────────────────────────────────────────────────────

async def test_an_operator_raises_one_ticket(operator, autotask):
    r = _post(operator)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] is True
    assert body["ticket"]["external_id"] == "9001"
    assert len(autotask.created) == 1


async def test_the_ticket_carries_the_finding(operator, autotask):
    _post(operator)
    sent = autotask.created[0]
    assert sent["companyID"] == 4242
    assert sent["title"] == "3 brukere mangler MFA"
    assert "sterk autentiseringsmetode" in sent["description"]


async def test_the_ticket_says_where_it_came_from(operator, autotask):
    """A ticket outlives the report. Without this, the first thing the
    technician picking it up does is re-run the audit to find out what it means."""
    _post(operator)
    description = autotask.created[0]["description"]
    assert _REC_ID in description
    assert "2026-08-01_0900" in description


async def test_operator_notes_reach_the_ticket(operator, autotask):
    _post(operator, notes="Avtalt med kunden i dag, haster ikke.")
    assert "Avtalt med kunden i dag" in autotask.created[0]["description"]


async def test_the_operator_can_override_title_and_queue(operator, autotask):
    _post(operator, title="MFA-utrulling Acme", queue_id=17, priority=1)
    sent = autotask.created[0]
    assert sent["title"] == "MFA-utrulling Acme"
    assert sent["queueID"] == 17
    assert sent["priority"] == 1


async def test_the_activity_log_records_who_did_it(operator, autotask, monkeypatch):
    seen = []
    import app.core.activity_log as al

    monkeypatch.setattr(al, "log_activity", lambda action, **kw: seen.append((action, kw)))
    _post(operator)
    actions = [a for a, _ in seen]
    assert "autotask_ticket_created" in actions


# ── Idempotency ──────────────────────────────────────────────────────────────

async def test_a_second_click_does_not_raise_a_second_ticket(operator, autotask):
    first = _post(operator)
    second = _post(operator)

    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert second.json()["ticket"]["external_id"] == "9001"
    assert len(autotask.created) == 1, "Autotask was asked twice"


async def test_the_second_click_does_not_even_call_autotask(operator, autotask):
    """Answered from the database before the network is touched, so a double
    click costs nothing and cannot fail halfway."""
    _post(operator)
    autotask.created.clear()
    _post(operator)
    assert autotask.created == []


async def test_a_different_finding_gets_its_own_ticket(operator, autotask, monkeypatch):
    from app.services import finding_tickets as ft

    def _find(customer_id, rec_id, lang):
        return ft.Finding(rec_id=rec_id, title=f"T {rec_id}", detail="d",
                          priority="high", audit_date="2026-08-01_0900")

    monkeypatch.setattr(ft, "find_recommendation", _find)

    _post(operator)
    _post(operator, rec_id="rec_dmarc_title:acme.no")

    assert len(autotask.created) == 2


async def test_the_uniqueness_is_enforced_by_the_database(operator, autotask):
    """Not by the SELECT above it.

    Two technicians clicking at once both find nothing and both insert. The
    constraint is what makes the second one lose, and `record_ticket` reports
    that rather than presenting the stored ticket as the one it just created.
    """
    from app.services.finding_tickets import SYSTEM_AUTOTASK, record_ticket

    first, ours_first = await record_ticket(
        _CUSTOMER_ID, _REC_ID, SYSTEM_AUTOTASK, "9001", "", "T", "alice",
    )
    second, ours_second = await record_ticket(
        _CUSTOMER_ID, _REC_ID, SYSTEM_AUTOTASK, "9002", "", "T", "bob",
    )

    assert ours_first is True
    assert ours_second is False, "the loser must know it lost"
    assert first.external_id == second.external_id == "9001"


async def test_a_lost_race_reports_the_orphaned_ticket(operator, autotask):
    """The one case where a duplicate ticket really does exist in Autotask.

    Reporting the id is the whole point: it is real, nobody owns it, and a
    silent success would leave it for a customer to find.
    """
    from app.services.finding_tickets import SYSTEM_AUTOTASK, record_ticket

    # Somebody else got there between our lookup and our insert.
    await record_ticket(
        _CUSTOMER_ID, _REC_ID, SYSTEM_AUTOTASK, "8888", "", "T", "alice",
    )
    import app.services.finding_tickets as ft
    real_get = ft.get_ticket

    calls = {"n": 0}

    async def _first_time_nothing(customer_id, rec_id, system=SYSTEM_AUTOTASK):
        calls["n"] += 1
        if calls["n"] == 1:
            return None                       # the route's pre-check
        return await real_get(customer_id, rec_id, system)

    ft.get_ticket = _first_time_nothing
    try:
        r = _post(operator)
    finally:
        ft.get_ticket = real_get

    body = r.json()
    assert body["created"] is False
    assert body["ticket"]["external_id"] == "8888"
    assert body["duplicate_ticket_id"] == "9001"


# ── Refusals ─────────────────────────────────────────────────────────────────

async def test_a_finding_the_latest_run_does_not_raise_is_refused(operator, autotask):
    """A ticket claims the audit found something. Inventing one puts a sentence
    in a customer's PSA that no evidence supports."""
    r = _post(operator, rec_id="rec_that_does_not_exist")
    assert r.status_code == 404
    assert autotask.created == []


async def test_a_customer_with_no_autotask_binding_is_refused(
    operator, autotask, monkeypatch
):
    from app.core.customer import CustomerManager

    monkeypatch.setattr(
        CustomerManager, "get_customer",
        staticmethod(lambda cid: {"CustomerId": cid, "CustomerName": "Acme AS"}),
    )
    r = _post(operator)
    assert r.status_code == 400
    assert autotask.created == []


async def test_an_autotask_failure_is_not_recorded_as_a_ticket(operator, monkeypatch):
    """A 400 from Autotask means no ticket exists. Storing a row would make
    every later click return a ticket nobody can open."""
    fake = _Autotask(create_status=400)
    real_init = AutotaskClient.__init__

    def _patched(self, *a, **kw):
        real_init(self, *a, **kw)
        self._client = httpx.AsyncClient(
            transport=httpx.MockTransport(fake.handler), headers=self._client.headers,
        )

    monkeypatch.setattr(AutotaskClient, "__init__", _patched)

    r = _post(operator)
    assert r.status_code >= 400

    from app.services.finding_tickets import get_ticket
    assert await get_ticket(_CUSTOMER_ID, _REC_ID) is None


async def test_an_unknown_body_field_is_refused(operator, autotask):
    r = _post(operator, assignee="somebody")
    assert r.status_code == 422
    assert autotask.created == []


async def test_an_out_of_range_priority_is_refused(operator, autotask):
    r = _post(operator, priority=99)
    assert r.status_code == 422
    assert autotask.created == []


# ── The ticket defaults ──────────────────────────────────────────────────────
# Status and priority are Autotask picklists. A customised instance renumbers
# them, so the write side must read them from settings rather than assume the
# stock values — and settings nothing can save is a setting that does not exist.

async def test_the_defaults_are_used_when_the_operator_sets_nothing(
    operator, autotask
):
    from app.core.config import load_app_settings, save_app_settings

    settings = load_app_settings()
    settings.update({
        "autotask_default_queue_id": 88,
        "autotask_default_priority": 4,
        "autotask_default_status": 9,
    })
    save_app_settings(settings)

    operator.post(f"/api/hub/{_CUSTOMER_ID}/tickets", json={"rec_id": _REC_ID})

    sent = autotask.created[0]
    assert sent["queueID"] == 88
    assert sent["priority"] == 4
    assert sent["status"] == 9


async def test_the_operators_choice_beats_the_default(operator, autotask):
    from app.core.config import load_app_settings, save_app_settings

    settings = load_app_settings()
    settings["autotask_default_priority"] = 4
    save_app_settings(settings)

    _post(operator, priority=1)
    assert autotask.created[0]["priority"] == 1


async def test_the_defaults_can_actually_be_saved(admin):
    """They are read on every ticket, so a settings form that cannot write
    them leaves the code reading a key nothing ever sets."""
    r = admin.post("/api/settings", json={
        "autotask_default_queue_id": 12,
        "autotask_default_priority": 3,
        "autotask_default_status": 1,
    })
    assert r.status_code == 200, r.text

    back = admin.get("/api/settings").json()
    assert back["autotask_default_queue_id"] == 12
    assert back["autotask_default_priority"] == 3


@pytest.mark.parametrize("payload", [
    {"autotask_default_priority": 0},
    {"autotask_default_priority": 99},
    {"autotask_default_queue_id": "not a number"},
    {"autotask_default_status": -1},
])
async def test_a_nonsense_default_is_refused_here_not_by_autotask(admin, payload):
    """Otherwise the operator discovers it as a 400 at the moment they click,
    on a screen that has nothing to do with settings."""
    r = admin.post("/api/settings", json=payload)
    assert r.status_code == 400, r.text


async def test_clearing_a_default_removes_it(admin):
    from app.core.config import load_app_settings

    admin.post("/api/settings", json={"autotask_default_queue_id": 12})
    admin.post("/api/settings", json={"autotask_default_queue_id": ""})
    assert "autotask_default_queue_id" not in load_app_settings()


# ── The client, on its own ───────────────────────────────────────────────────

def _direct_client(handler) -> AutotaskClient:
    c = AutotaskClient("code", "api@acme.no", "secret", zone_url=_ZONE["url"])
    c._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers=c._client.headers,
    )
    return c


async def test_a_create_is_never_retried_on_a_5xx():
    """The reason `send_with_retry` distinguishes methods at all.

    A POST that applied the write and then failed on the way out would, on
    retry, create a second ticket for the same finding.
    """
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(500, text="boom")

    client = _direct_client(handler)
    with pytest.raises(AutotaskError):
        await client.create_ticket(1, "t", "d")
    await client.close()

    assert attempts["n"] == 1, "a 5xx on create must not be retried"


async def test_a_429_is_still_retried():
    """Refused before it was processed, so repeating it changes only timing."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"itemId": 7})

    client = _direct_client(handler)
    assert await client.create_ticket(1, "t", "d") == 7
    await client.close()
    assert attempts["n"] == 2


async def test_a_response_with_no_id_raises():
    """Accepting it would record a ticket that may not exist."""
    client = _direct_client(lambda r: httpx.Response(200, json={"ok": True}))
    with pytest.raises(AutotaskError, match="no usable id"):
        await client.create_ticket(1, "t", "d")
    await client.close()


async def test_long_text_is_truncated_rather_than_refused():
    """A finding's detail is written for a report page and runs long. Losing
    the tail beats losing the ticket to a 400."""
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"itemId": 1})

    client = _direct_client(handler)
    await client.create_ticket(1, "T" * 400, "D" * 9000)
    await client.close()

    assert len(sent["title"]) == 255
    assert len(sent["description"]) == 8000
