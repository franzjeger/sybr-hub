"""Live-log regressions: wrong identity URL, Exchange coverage and tenant domain."""

from pathlib import Path

import httpx
import pytest

from app.modules.base import SectionResult, SectionStatus
from app.modules.m365_audit.auth import AuthError, AuthManager
from app.modules.m365_audit.graph_client import GraphPermissionError
from app.modules.m365_audit.sections.exchange import ExchangeSection
from app.modules.m365_audit.sections.identity_security import IdentitySecuritySection
from app.reports.generator import build_report_context
from tests.audit_fixture import FULL_AUDIT
from tests.collector_rig import FakeGraph, refused


class _OpenGraph:
    """Reuse the rig's entered client without replacing its MockTransport."""

    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, *_):
        pass


async def test_risky_users_use_the_v1_identity_protection_endpoint(tmp_path):
    async with FakeGraph({"v1.0/identityProtection/riskyUsers": []}) as fake:
        await IdentitySecuritySection(tmp_path, fake.client)._collect_risky_users()
    assert fake.unrouted == []
    assert (tmp_path / "18_risky_users.json").exists()


async def test_pim_licence_refusal_is_not_a_generic_bad_query():
    body = refused(400, "AadPremiumLicenseRequired", "PIM requires Entra ID P2 or Governance.")
    async with FakeGraph({"roleManagement/directory/roleEligibilitySchedules": body}) as fake:
        with pytest.raises(GraphPermissionError) as raised:
            await fake.client.get_all("roleManagement/directory/roleEligibilitySchedules")
    assert raised.value.is_licence_gap
    assert raised.value.status == 400
    assert "Governance" in str(raised.value)


async def test_a_real_bad_query_remains_a_query_error():
    async with FakeGraph({"groups": refused(400, "BadRequest", "Invalid filter.")}) as fake:
        with pytest.raises(httpx.HTTPStatusError):
            await fake.client.get_all("groups")


async def test_risky_user_explicit_licence_refusal_is_not_missing_consent():
    body = refused(403, "Forbidden", "Your tenant is not licensed for this feature.")
    async with FakeGraph({"identityProtection/riskyUsers": body}) as fake:
        with pytest.raises(GraphPermissionError) as raised:
            await fake.client.get_all("identityProtection/riskyUsers")
    assert raised.value.is_licence_gap
    assert "missing a permission" not in str(raised.value)


@pytest.mark.parametrize(
    "results", [[], [SectionResult(name="Exchange Online", status=SectionStatus.DONE)]]
)
def test_exchange_failure_survives_history_report_regeneration(tmp_path, results):
    for name, content in FULL_AUDIT.items():
        (tmp_path / name).write_text(content)
    (tmp_path / "EXCHANGE_ERROR.txt").write_text(
        "Exchange Online data collection failed:\nUnAuthorized\n"
    )
    context = build_report_context(
        "Customer A", "acme.example", tmp_path, results, lang="en", persist_metrics=False
    )
    issues = context["risk"]["data_quality_issues"]
    assert len([issue for issue in issues if "Exchange Online" in issue]) == 1
    assert context["risk"]["has_full_data"] is False


def _auth(public_domain="acme.example"):
    return AuthManager(
        "tenant-a",
        "app-a",
        "synthetic-secret",
        "",
        public_domain,
        Path("cert.pfx"),
        "synthetic-password",
    )


async def test_exchange_resolves_initial_domain_without_requiring_is_verified():
    auth = _auth()
    routes = {
        "organization": [
            {
                "verifiedDomains": [
                    {"name": "acme.example", "isDefault": True},
                    {"name": "customer-a.onmicrosoft.com", "isInitial": True},
                ]
            }
        ]
    }
    async with FakeGraph(routes) as fake:
        auth._credential = fake.client._credential
        from unittest.mock import patch

        import app.modules.m365_audit.graph_client as graph_module

        with patch.object(graph_module, "GraphClient", return_value=_OpenGraph(fake.client)):
            assert await auth._exo_organization() == "customer-a.onmicrosoft.com"
    assert auth.org_domain == "acme.example", "the public/report domain must stay unchanged"


async def test_an_existing_exchange_domain_needs_no_graph_lookup():
    assert (
        await _auth("customer-a.onmicrosoft.com")._exo_organization()
        == "customer-a.onmicrosoft.com"
    )


@pytest.mark.parametrize("domains", [[], [{"name": "acme.example", "isInitial": True}]])
async def test_exchange_does_not_guess_a_missing_initial_domain(domains):
    auth = _auth()
    async with FakeGraph({"organization": [{"verifiedDomains": domains}]}) as fake:
        auth._credential = fake.client._credential
        from unittest.mock import patch

        import app.modules.m365_audit.graph_client as graph_module

        with (
            patch.object(graph_module, "GraphClient", return_value=_OpenGraph(fake.client)),
            pytest.raises(AuthError, match=r"onmicrosoft\.com"),
        ):
            await auth._exo_organization()


async def test_gdap_exchange_is_still_skipped_but_connection_failure_is_failed(tmp_path):
    async with FakeGraph({"beta/security/dataSecurityAndGovernance/sensitivityLabels": []}) as fake:
        for data, expected in [
            ({"error": "UnAuthorized"}, SectionStatus.FAILED),
            ({"error": "Certificate unavailable via GDAP", "skipped": True}, SectionStatus.SKIPPED),
        ]:
            result = await ExchangeSection(tmp_path, data, [], graph=fake.client).collect()
            assert result.status is expected
            assert result.error == data["error"]
