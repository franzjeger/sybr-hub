"""Conditional Access, read back from what the Conditional Access collector writes.

08_conditional_access.txt now has a JSON twin, and _parse_ca_policies reads it
first. Over the same policies the two must give the same counts and the same
legacy-authentication verdict, which comes from each policy's state, grant
controls and client apps. The text has one thing it cannot say: a tenant with
no policies writes no "Client apps:" line, which is also what an audit taken
before client apps were collected looks like, so CIS 5.1.1 read such a tenant
as unverifiable. The sidecar says the client apps were collected.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections.conditional_access import ConditionalAccessSection
from app.reports.compliance import _build_compliance_map
from app.reports.parsers import _parse_ca_policies
from app.reports.parsers.common import _sidecar
from tests.collector_rig import FakeGraph, refused, run_sections

LONG_NAME = "Krev MFA for alle brukere utenfor kontoret i Kunde A sine lokasjoner"
assert len(LONG_NAME) > 45


def _policy(pid, name, state, client_apps, controls, *, groups=()) -> dict:
    return {
        "id": pid,
        "displayName": name,
        "state": state,
        "templateId": None,
        "createdDateTime": "2026-01-15T10:00:00Z",
        "conditions": {
            "users": {"includeUsers": [] if groups else ["All"], "includeGroups": list(groups)},
            "applications": {"includeApplications": ["All"]},
            "clientAppTypes": client_apps,
        },
        "grantControls": {"operator": "OR", "builtInControls": controls},
    }


POLICIES = [
    _policy("p1", LONG_NAME, "enabled", ["all"], ["mfa"], groups=["g-1"]),
    _policy(
        "p2", "Blokker eldre autentisering", "enabled", ["exchangeActiveSync", "other"], ["block"]
    ),
    _policy("p3", "Test i rapportmodus", "enabledForReportingButNotEnforced", ["all"], ["mfa"]),
    _policy("p4", "Gammel policy", "disabled", ["exchangeActiveSync", "other"], ["block"]),
]


async def _collect(tmp_path, policies, *, sidecars: bool) -> dict:
    routes = {
        "identity/conditionalAccess/policies": policies,
        "identity/conditionalAccess/namedLocations": [],
        "groups/g-1": {"id": "g-1", "displayName": "Alle ansatte"},
    }
    async with FakeGraph(routes) as fake:
        files = await run_sections(
            ConditionalAccessSection(tmp_path, fake.client), sidecars=sidecars
        )
        assert fake.unrouted == []
    return files


def _status(files: dict, ca: dict, cis_id: str) -> str:
    rows = _build_compliance_map({"file_contents": files, "ca": ca}, lang="no")
    return next(r["status"] for r in rows if r["cis_id"] == cis_id)


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_policies_read_the_same_from_either_file(tmp_path, sidecars):
    files = await _collect(tmp_path, POLICIES, sidecars=sidecars)
    sidecar = _sidecar(files, "08_conditional_access.txt")
    assert (sidecar is not None) is sidecars

    ca = _parse_ca_policies(files["08_conditional_access.txt"], sidecar)

    assert ca == {
        "enabled": 2,
        "disabled": 1,
        "report_only": 1,
        "has_data": True,
        "blocks_legacy_auth": True,
        "has_client_app_data": True,
    }
    assert _status(files, ca, "5.1.1") == "pass"


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_an_mfa_grant_scoped_to_legacy_clients_blocks_them_from_either_file(
    tmp_path, sidecars
):
    policies = [
        _policy("p1", "Eldre klienter", "enabled", ["exchangeActiveSync", "other"], ["mfa"])
    ]
    files = await _collect(tmp_path, policies, sidecars=sidecars)

    ca = _parse_ca_policies(
        files["08_conditional_access.txt"], _sidecar(files, "08_conditional_access.txt")
    )

    assert ca["blocks_legacy_auth"] is True


async def test_the_sidecar_is_what_the_reader_reads(tmp_path):
    files = await _collect(tmp_path, POLICIES, sidecars=True)
    sidecar = _sidecar(files, "08_conditional_access.txt")

    ca = _parse_ca_policies("", sidecar)

    assert (ca["enabled"], ca["disabled"], ca["report_only"]) == (2, 1, 1)
    assert ca["blocks_legacy_auth"] is True
    by_id = {p["id"]: p for p in sidecar["policies"]}
    assert by_id["p1"]["name"] == LONG_NAME
    assert by_id["p1"]["include_groups"] == [{"id": "g-1", "name": "Alle ansatte"}]


async def test_a_tenant_with_no_policies_is_graded_not_left_unverified(tmp_path):
    files = await _collect(tmp_path, [], sidecars=True)

    ca = _parse_ca_policies(
        files["08_conditional_access.txt"], _sidecar(files, "08_conditional_access.txt")
    )

    assert ca["has_data"] is True
    assert ca["has_client_app_data"] is True
    assert ca["blocks_legacy_auth"] is False
    assert _status(files, ca, "5.1.1") == "fail"

    text_only = _parse_ca_policies(files["08_conditional_access.txt"])
    assert text_only["has_client_app_data"] is False, "all the text can say"
    assert _status(files, text_only, "5.1.1") == "info"


async def test_a_refused_policy_read_writes_no_sidecar(tmp_path):
    routes = {
        "identity/conditionalAccess/policies": refused(),
        "identity/conditionalAccess/namedLocations": [],
    }
    async with FakeGraph(routes) as fake:
        files = await run_sections(ConditionalAccessSection(tmp_path, fake.client))

    assert "08_conditional_access.json" not in files
    ca = _parse_ca_policies(files["08_conditional_access.txt"], None)
    assert ca["has_data"] is False
