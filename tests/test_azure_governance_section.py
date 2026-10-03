import pytest

from app.modules.base import SectionStatus
from app.modules.m365_audit.sections.azure_governance import AzureGovernanceSection


@pytest.mark.asyncio
async def test_azure_governance_reports_failed_when_collector_fails(tmp_path):
    class DummyAuth:
        def advisor_client_for(self, sub_id):
            raise Exception("Forced failure")

        def compute_client_for(self, sub_id):
            raise Exception("Forced failure")

        def cost_client_for(self, sub_id):
            raise Exception("Forced failure")

    class FailingSection(AzureGovernanceSection):
        def __init__(self, *args, **kwargs):
            # Stub out init to avoid actual auth/HTTP requirements
            self.result = None
            self._out_dir = tmp_path
            from app.modules.base import SectionResult

            self.result = SectionResult(name="Azure Governance", status=SectionStatus.PENDING)
            self.auth = DummyAuth()
            self._sub_id = "1234"

        async def _collect_advisor(self):
            raise Exception("Forced failure")

        def _warn(self, msg):
            pass

        def _report(self, status):
            self.result.status = status

    section = FailingSection()

    # Overwrite the other collectors to not fail so we isolate the behavior to one failure
    async def noop():
        pass

    section._collect_backup = noop
    section._collect_log_analytics = noop
    section._collect_resource_inventory = noop
    section._collect_orphaned_resources = noop
    section._collect_cost = noop

    # collect(), not run(): run() is BaseModule's entry point, BaseSection's is
    # collect(). The test could never have passed as written.
    result = await section.collect()

    # The fix ensures that if any collector fails, the section reports FAILED
    assert result.status == SectionStatus.FAILED
