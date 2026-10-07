"""Intune refuses reads for multiple reasons; no refusal may become zero devices."""

import json

import pytest

from app.core.encryption import encrypted_read_text
from app.modules.m365_audit.graph_client import GraphPermissionError
from app.modules.m365_audit.sections.intune import IntuneSection
from app.reports.evidence import _evidence_unavailable
from tests.collector_rig import FakeGraph


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("service_body", [False, True])
async def test_intune_refusal_does_not_rule_out_permissions_or_guess_a_subscription(
    tmp_path, status, service_body
):
    if service_body:
        message = json.dumps(
            {
                "ErrorCode": "Forbidden",
                "Message": "https://proxy.example.manage.microsoft.com/deviceManagement/managedDevices",
            }
        )
        code = "UnknownError"
    else:
        message, code = "Insufficient privileges.", "Authorization_RequestDenied"
    body = json.dumps({"error": {"code": code, "message": message}})

    class Graph:
        async def get_all(self, path, **kwargs):
            raise GraphPermissionError(path, status, body)

    section = IntuneSection(tmp_path, Graph())
    await section._collect_devices()
    evidence = encrypted_read_text(tmp_path / "10_intune_devices.txt")
    assert _evidence_unavailable(evidence)
    assert "DeviceManagementManagedDevices.Read.All" in evidence
    assert "admin consent" in evidence
    assert "active Intune licence" in evidence
    assert "does not establish" in evidence
    assert "permission is not the problem" not in evidence
    assert "most likely has no" not in evidence
    assert not (tmp_path / "10_intune_devices.json").exists()
    assert not (tmp_path / "10_intune_devices_count.txt").exists()
    assert len(section._failures) == 1


def test_a_premium_licence_error_does_not_identify_a_missing_intune_sku(tmp_path):
    error = GraphPermissionError(
        "deviceManagement/managedDevices",
        403,
        json.dumps(
            {
                "error": {
                    "code": "Authentication_RequestFromNonPremiumTenantOrB2CTenant",
                    "message": "Tenant does not have premium license",
                },
            }
        ),
    )
    reason = IntuneSection(tmp_path, None)._reason("10_intune_devices.txt", error)
    assert "reporting a licence gap" in reason
    assert "does not identify a specific missing Intune SKU" in reason


async def test_modern_intune_policy_collections_use_the_beta_endpoints(tmp_path):
    """v1.0 returned 400 on the live Settings Catalog and ADMX collections."""
    async with FakeGraph(
        {
            "beta/deviceManagement/configurationPolicies": [
                {"id": "catalog-a", "name": "Workplace baseline"}
            ],
            "beta/deviceManagement/groupPolicyConfigurations": [
                {"id": "admx-a", "displayName": "Browser baseline"}
            ],
        }
    ) as fake:
        section = IntuneSection(tmp_path, fake.client)
        await section._collect_settings_catalog()
        await section._collect_admin_templates()
    assert fake.unrouted == []
    assert "Workplace baseline" in encrypted_read_text(tmp_path / "12b_intune_settings_catalog.txt")
    assert "Browser baseline" in encrypted_read_text(tmp_path / "12c_intune_admin_templates.txt")
    assert section.result.warns == []
