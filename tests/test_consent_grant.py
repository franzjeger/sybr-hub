"""Asking a Global Admin for the one permission the app cannot grant itself.

Sybr HUB holds twenty-two Graph permissions, all ending in .Read.All, and
deliberately not AppRoleAssignment.ReadWrite.All — the property that stops a
compromised toolkit becoming a way into every customer's tenant. So the only
honest route to a write permission is somebody with the authority signing in.

What follows is about the two halves being genuinely two, and about re-running
after an interruption being ordinary rather than an error.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.consent import (
    GRAPH_APP_ID,
    ConsentError,
    grant_application_permission,
)

ROLE_ID = "role-abc"
PERMISSION = "Policy.ReadWrite.ConditionalAccess"


class _FakeGraph:
    """Enough of Graph to exercise both halves and their idempotency."""

    def __init__(self, *, declared=False, assigned=False, app_exists=True, sp_exists=True):
        self.declared, self.assigned = declared, assigned
        self.app_exists, self.sp_exists = app_exists, sp_exists
        self.patched: list[dict] = []
        self.posted: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        params = kw.get("params") or {}
        flt = params.get("$filter", "")
        if "/applications" in url:
            value = [] if not self.app_exists else [{
                "id": "app-object-1",
                "requiredResourceAccess": (
                    [{"resourceAppId": GRAPH_APP_ID,
                      "resourceAccess": [{"id": ROLE_ID, "type": "Role"}]}]
                    if self.declared else []
                ),
            }]
        elif "/servicePrincipals/" in url and "appRoleAssignments" in url:
            value = [{"appRoleId": ROLE_ID, "resourceId": "graph-sp"}] if self.assigned else []
        elif "/servicePrincipals" in url and GRAPH_APP_ID in flt:
            value = [{
                "id": "graph-sp",
                "appRoles": [{
                    "id": ROLE_ID, "value": PERMISSION,
                    "allowedMemberTypes": ["Application"],
                }],
            }]
        elif "/servicePrincipals" in url:
            value = [{"id": "own-sp"}] if self.sp_exists else []
        else:
            value = []
        return _Resp({"value": value})

    async def patch(self, url, **kw):
        self.patched.append(kw.get("json") or {})
        return _Resp({})

    async def post(self, url, **kw):
        self.posted.append(kw.get("json") or {})
        return _Resp({})


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


@pytest.fixture()
def graph(monkeypatch):
    made = {}

    def factory(**kw):
        return made["client"]

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: made["client"])
    return made


async def test_a_fresh_registration_is_both_declared_and_assigned(graph):
    """Two things, and the portal doing them together makes them easy to
    conflate. Declaring lists the permission; assigning is the consent."""
    graph["client"] = _FakeGraph()

    result = await grant_application_permission("t", "client-1", PERMISSION)

    assert (result["declared"], result["assigned"]) == (True, True)
    assert graph["client"].patched, "the permission was never declared"
    assert graph["client"].posted, "the permission was never assigned"


async def test_declaring_without_assigning_still_reads_as_missing_consent(graph):
    """The state somebody lands in by adding a permission in the portal and
    forgetting the Grant admin consent button."""
    graph["client"] = _FakeGraph(declared=True, assigned=False)

    result = await grant_application_permission("t", "client-1", PERMISSION)

    assert result["declared"] is False, "it was already declared"
    assert result["assigned"] is True, "the assignment is what was missing"
    assert not graph["client"].patched
    assert graph["client"].posted


async def test_running_it_again_changes_nothing_and_is_not_an_error(graph):
    """Re-running after an interruption is the normal case, not a failure."""
    graph["client"] = _FakeGraph(declared=True, assigned=True)

    result = await grant_application_permission("t", "client-1", PERMISSION)

    assert result["already_complete"] is True
    assert not graph["client"].patched
    assert not graph["client"].posted


async def test_the_assignment_names_the_app_as_both_principal_and_target(graph):
    """An app-only role is assigned to the application's own service principal,
    with Graph as the resource. Getting either wrong grants nothing while
    looking like it worked."""
    graph["client"] = _FakeGraph()

    await grant_application_permission("t", "client-1", PERMISSION)

    body = graph["client"].posted[0]
    assert body == {"principalId": "own-sp", "resourceId": "graph-sp", "appRoleId": ROLE_ID}


async def test_a_registration_the_signed_in_account_cannot_see_is_named(graph):
    graph["client"] = _FakeGraph(app_exists=False)

    with pytest.raises(ConsentError, match="visible to the account"):
        await grant_application_permission("t", "client-1", PERMISSION)


async def test_an_application_with_no_service_principal_is_named(graph):
    """Nothing to assign the permission to — a real state for an app that was
    registered but never consented in this tenant."""
    graph["client"] = _FakeGraph(sp_exists=False)

    with pytest.raises(ConsentError, match="no service principal"):
        await grant_application_permission("t", "client-1", PERMISSION)


async def test_a_permission_graph_does_not_publish_is_refused(graph):
    graph["client"] = _FakeGraph()

    with pytest.raises(ConsentError, match="no application permission"):
        await grant_application_permission("t", "client-1", "Invented.Permission")
