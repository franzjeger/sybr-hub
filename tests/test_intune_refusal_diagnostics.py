"""Intune refuses reads for multiple reasons; no refusal may become zero devices."""

import json

import pytest

from app.core.encryption import encrypted_read_text
from app.modules.m365_audit.graph_client import GraphPermissionError
from app.modules.m365_audit.sections.intune import IntuneSection
from app.reports.evidence import _evidence_unavailable
from app.reports.i18n import T
from app.reports.parsers.common import unavailable_cause, unavailable_text
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
    # The file names the cause as a code, which the report words (TODO C15).
    cause = unavailable_cause(evidence)
    assert cause == {
        "code": "service_refused" if service_body else "refused",
        "status": str(status),
        "permission": "DeviceManagementManagedDevices.Read.All",
        "error": "",
    }
    for lang, words in (
        ("en", ("admin consent", "active Intune licence", "does not establish")),
        ("no", ("administratorsamtykket", "aktiv Intune-lisens", "Svaret alene sier ikke")),
    ):
        text = unavailable_text(cause, T(lang))
        assert "DeviceManagementManagedDevices.Read.All" in text
        for word in words:
            assert word in text, (lang, word)
        assert "permission is not the problem" not in text
        assert "most likely has no" not in text
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
    cause = IntuneSection(tmp_path, None)._cause("10_intune_devices.txt", error)
    assert (
        cause == "Cause: licence_gap status=403 permission=DeviceManagementManagedDevices.Read.All"
    )
    worded = unavailable_text(unavailable_cause(f"  {cause}"), T("no"))
    assert "svaret sier ikke hvilken Intune-lisens som mangler" in worded


@pytest.mark.parametrize(
    ("sentence", "code"),
    [
        (
            "Graph refused this collection with 403, reporting a licence gap. Verify the "
            "required licence for this endpoint; the response does not identify a specific "
            "missing Intune SKU.",
            "licence_gap",
        ),
        (
            "The Intune service refused this collection (403). Check "
            "DeviceManagementManagedDevices.Read.All and admin consent, an active Intune "
            "licence and tenant service provisioning.",
            "service_refused",
        ),
        (
            "Graph refused this collection with 401. Check "
            "DeviceManagementManagedDevices.Read.All and admin consent, token validity and an "
            "active Intune licence.",
            "refused",
        ),
        (
            "Graph refused this collection with 403: the app registration is missing "
            "DeviceManagementManagedDevices.Read.All or its admin consent.",
            "refused",
        ),
        ("The collection failed before it could be read: ReadTimeout", "failed"),
    ],
)
def test_an_old_runs_sentence_is_read_back_to_its_cause(sentence, code):
    """A run from before the codes holds the collector's English sentence."""
    banner = "=" * 80 + "\n  INTUNE MANAGED DEVICES  (not available)\n" + "=" * 80
    cause = unavailable_cause(f"{banner}\n\n  {sentence}\n")
    assert cause is not None and cause["code"] == code
    text = unavailable_text(cause, T("no"))
    assert "Graph refused" not in text and "The collection failed" not in text
    if code == "failed":
        assert text == "Innsamlingen feilet før dataene kunne leses: ReadTimeout"


def test_a_sentence_the_report_does_not_know_is_kept():
    assert (
        unavailable_cause("  INTUNE MANAGED DEVICES  (not available)\n\n  Something new.\n") is None
    )


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
