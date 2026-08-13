"""A read that failed must not render as a customer with nothing wrong.

``/customer/{id}/unified`` used to answer::

    except Exception:
        result["audit"] = None

for its metrics, its SSH hosts and — by having no guard at all — took the whole
page down if the ALSO query raised. The architecture doc calls this out as the
defect class the audit pipeline was rebuilt to remove; it was still here, in
the screen a technician actually looks at.

The consequence was not a missing card. The front end builds its "Krever
handling" band from ``a.users_no_mfa || 0``, so a failed metrics read produced
a customer with no findings — the same page a genuinely healthy customer gets.
The reassuring answer was the one a database hiccup produced.

So these tests check both halves: that a failure is *named*, and that a real
absence is still distinguishable from it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import get_db, run_migrations
from app.models.user import Role, User
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

_CUSTOMER_ID = "acme"


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
    """One customer, registered in memory rather than on disk."""
    from app.core.customer import CustomerManager

    record = {
        "CustomerId": _CUSTOMER_ID,
        "CustomerName": "Acme AS",
        "PrimaryDomain": "acme.no",
        "AlsoAccountId": "12345",
    }
    monkeypatch.setattr(
        CustomerManager, "get_customer",
        staticmethod(lambda cid: record if cid == _CUSTOMER_ID else None),
    )
    yield record


@pytest.fixture()
async def client():
    user = await create_user(
        username="tech", password="Test1234!xyz",
        display_name="Tech", role=Role.admin,
    )
    token = await create_access_token(user)
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def _get(client) -> dict:
    r = client.get(f"/api/customer/{_CUSTOMER_ID}/unified")
    assert r.status_code == 200, r.text
    return r.json()


def _break_table(monkeypatch, table: str):
    """Make exactly one table unreadable, leaving the others alone.

    Patched on ``app.core.database`` rather than on the route module: the view
    imports ``get_db`` inside the handler, so it resolves from the source
    module at call time. Everything except the target table passes straight
    through, so auth and the rest of the request still work — which is the
    point, since the claim under test is that one broken table degrades one
    card.
    """
    import app.core.database as db_mod

    real_get_db = db_mod.get_db

    class _Boom:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *a, **kw):
            if table in sql:
                raise RuntimeError(f"no such table: {table}")
            return self._conn.execute(sql, *a, **kw)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    class _Ctx:
        def __init__(self):
            self._inner = real_get_db()

        async def __aenter__(self):
            return _Boom(await self._inner.__aenter__())

        async def __aexit__(self, *exc):
            return await self._inner.__aexit__(*exc)

    monkeypatch.setattr(db_mod, "get_db", lambda: _Ctx())


# ── A failure is named ───────────────────────────────────────────────────────

async def test_a_failed_audit_read_is_reported_not_silently_null(client, monkeypatch):
    _break_table(monkeypatch, "audit_metrics")
    data = _get(client)

    assert data["audit"] is None
    assert "audit" in data["unavailable"], (
        "a null with no entry here is indistinguishable from 'never audited'"
    )


async def test_a_failed_ssh_read_is_reported(client, monkeypatch):
    _break_table(monkeypatch, "ssh_hosts")
    data = _get(client)

    assert data["ssh_hosts"] is None
    assert "ssh_hosts" in data["unavailable"]


async def test_a_failed_also_read_does_not_take_the_page_down(client, monkeypatch):
    """This block had no guard at all, so the whole view answered 500."""
    _break_table(monkeypatch, "also_renewals")
    data = _get(client)

    assert data["also"] is None
    assert "also" in data["unavailable"]


async def test_one_broken_table_leaves_the_other_blocks_readable(client, monkeypatch):
    """Degrade the card, not the page."""
    _break_table(monkeypatch, "audit_metrics")
    data = _get(client)

    assert data["customer_name"] == "Acme AS"
    assert data["domain"] == "acme.no"
    assert list(data["unavailable"]) == ["audit"]


# ── A real absence is still an absence ───────────────────────────────────────

async def test_a_healthy_read_reports_nothing_unavailable(client):
    data = _get(client)
    assert data["unavailable"] == {}


async def test_an_empty_table_is_not_an_error(client):
    """Nothing stored is a measurement. It must not read as a failure."""
    data = _get(client)

    assert data["audit"] is None
    assert data["ssh_hosts"] is None
    assert "audit" not in data["unavailable"]
    assert "ssh_hosts" not in data["unavailable"]


async def test_real_data_still_comes_through(client):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO audit_metrics
                   (customer_id, customer_name, audit_date, risk_grade,
                    risk_score, users_no_mfa, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_CUSTOMER_ID, "Acme AS", "2026-08-01T09:00:00", "B", 78, 4,
             "2026-08-01T09:00:00"),
        )
        await db.commit()

    data = _get(client)
    assert data["unavailable"] == {}
    assert data["audit"]["risk_grade"] == "B"
    assert data["audit"]["users_no_mfa"] == 4


# ── The front end has to read it ─────────────────────────────────────────────

def test_the_frontend_renders_the_unavailable_block():
    """A field nothing displays is a field that does not exist.

    Static, because the alternative is a browser. It checks the three things
    that make the server-side flag reach a person: the field is read, the
    chips fall back to a failure label, and the band is emitted.
    """
    import pathlib

    js = pathlib.Path("app/web/static/app.js").read_text()

    assert "d.unavailable" in js, "the flag is never read"
    assert "st_read_failed" in js, "chips do not show a failure state"
    assert "hdr_incomplete_data" in js, "no banner naming what could not be read"


def test_the_banner_is_rendered_before_the_findings_band():
    """Order matters: the findings band is the thing that looks reassuring.

    If "Krever handling" renders above the warning, a reader sees an empty
    action list first and has already drawn a conclusion.
    """
    import pathlib

    js = pathlib.Path("app/web/static/app.js").read_text()
    banner = js.index("hdr_incomplete_data")
    findings = js.index("hdr_needs_action")
    assert banner < findings


@pytest.mark.parametrize("key", [
    "st_read_failed", "hdr_incomplete_data", "msg_block_unavailable",
    "blk_audit", "blk_ssh_hosts", "blk_also",
])
def test_the_new_keys_exist_in_both_languages(key):
    import json
    import pathlib

    d = json.loads(pathlib.Path("app/web/static/ui_i18n.json").read_text())
    assert key in d["no"], f"{key} missing from Norwegian"
    assert key in d["en"], f"{key} missing from English"
