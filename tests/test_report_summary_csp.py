"""The customer-summary report renders styled, end to end.

`test_report_artefact_csp.py` proves the policy is well-formed and that the
routes reference it. This proves the wiring survives the request: the response
that reaches the browser actually carries the artefact policy and not the
application one. The bug it locks in was visible — the summary opened as a
column of unstyled text because the app CSP's `style-src-elem 'self'` dropped
the report's entire <style> block, while the on-disk audit report (served by a
route that already set the artefact policy) looked correct. Two routes, two
renderings, one missing header.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.core.rbac import set_all_customers
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.middleware.security_headers import ARTEFACT_CSP
from app.web.server import create_app

_CUSTOMER_ID = "acme"


@pytest.fixture(autouse=True)
def _reset_state():
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

    record = {"_id": _CUSTOMER_ID, "CustomerName": "Acme AS", "PrimaryDomain": "acme.no"}
    monkeypatch.setattr(
        CustomerManager, "list_customers", staticmethod(lambda: [record])
    )
    yield record


@pytest.fixture()
async def client():
    user = await create_user("op", "Str0ng-Passphrase-For-Tests!", "Op", role=Role.admin)
    await set_all_customers(user.id, True)
    token = await create_access_token(user)
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def test_the_summary_response_carries_the_artefact_policy(client):
    r = client.get(f"/api/reports/customer-summary/{_CUSTOMER_ID}")

    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")

    csp = r.headers.get("content-security-policy", "")
    assert csp == ARTEFACT_CSP, (
        "the summary must reach the browser under the artefact policy, not the "
        f"application CSP that blocks its <style> block. Got: {csp!r}"
    )
    # The two directives whose absence caused the visible bug and the security
    # concern, checked by meaning rather than by string identity.
    assert "style-src 'unsafe-inline'" in csp, "its <style> block would be dropped"
    assert "style-src 'self'" not in csp, "that is the application policy, the bug"
    assert "sandbox" in csp, "a tenant-data document must stay in an opaque origin"


def test_the_summary_actually_embeds_the_style_block_it_needs(client):
    """If the report ever stops depending on a <style> element, the header no
    longer matters and this suite should say so rather than guard nothing."""
    r = client.get(f"/api/reports/customer-summary/{_CUSTOMER_ID}")
    assert "<style>" in r.text
