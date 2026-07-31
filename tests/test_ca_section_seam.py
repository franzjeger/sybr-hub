"""The Conditional Access section writes what the report reads back.

Both sides of this seam have been wrong before, in opposite directions: the
report read only includeUsers from a policy scoped by role, and the control for
legacy authentication read a SharePoint file. Fixtures written by hand cannot
catch a drift between the two, because the fixture is the assumption. So these
run the real collector and feed its actual output to the real parser.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from app.core.encryption import encrypted_read_text
from app.modules.m365_audit.sections.conditional_access import ConditionalAccessSection
from app.reports.generator import _parse_ca_policies


class _FakeGraph:
    def __init__(self, policies):
        self._policies = policies

    async def get_all(self, path, **kwargs):
        return [] if "namedLocations" in path else self._policies

    async def get(self, *args, **kwargs):
        return {}


def _policy(name, state, client_apps, controls):
    return {
        "displayName": name,
        "state": state,
        "conditions": {
            "users": {"includeUsers": ["All"]},
            "applications": {"includeApplications": ["All"]},
            "clientAppTypes": client_apps,
        },
        "grantControls": {"builtInControls": controls},
    }


async def _collect(policies) -> str:
    out_dir = pathlib.Path(tempfile.mkdtemp())
    await ConditionalAccessSection(out_dir, _FakeGraph(policies)).collect()
    return encrypted_read_text(out_dir / "08_conditional_access.txt")


@pytest.mark.asyncio
async def test_collector_writes_the_client_app_scope():
    text = await _collect([
        _policy("Block legacy authentication", "enabled",
                ["exchangeActiveSync", "other"], ["block"]),
    ])
    assert "Client apps: exchangeActiveSync, other" in text


@pytest.mark.asyncio
async def test_the_parser_reads_back_what_the_collector_wrote():
    """The seam itself: real output, real parser, no hand-written fixture."""
    text = await _collect([
        _policy("All users require MFA", "enabled", ["all"], ["mfa"]),
        _policy("Block legacy authentication", "enabled",
                ["exchangeActiveSync", "other"], ["block"]),
    ])
    parsed = _parse_ca_policies(text)
    assert parsed["has_client_app_data"] is True
    assert parsed["blocks_legacy_auth"] is True
    assert parsed["enabled"] == 2


@pytest.mark.asyncio
async def test_a_tenant_without_the_policy_reads_back_as_not_blocking():
    text = await _collect([_policy("All users require MFA", "enabled", ["all"], ["mfa"])])
    parsed = _parse_ca_policies(text)
    assert parsed["has_client_app_data"] is True
    assert parsed["blocks_legacy_auth"] is False


@pytest.mark.asyncio
async def test_a_policy_with_no_client_app_scope_says_so():
    """Graph can return the field empty; that is not the same as legacy-scoped."""
    text = await _collect([_policy("Odd policy", "enabled", [], ["block"])])
    assert "Client apps: not specified" in text
    parsed = _parse_ca_policies(text)
    assert parsed["blocks_legacy_auth"] is False


@pytest.mark.asyncio
async def test_the_scope_line_does_not_disturb_the_state_counts():
    """The parser counts policies by their leading "[state]" marker."""
    text = await _collect([
        _policy("A", "enabled", ["all"], ["mfa"]),
        _policy("B", "disabled", ["exchangeActiveSync", "other"], ["block"]),
        _policy("C", "enabledForReportingButNotEnforced", ["all"], ["mfa"]),
    ])
    parsed = _parse_ca_policies(text)
    assert (parsed["enabled"], parsed["disabled"], parsed["report_only"]) == (1, 1, 1)
    assert parsed["blocks_legacy_auth"] is False, "a disabled policy blocks nothing"


@pytest.mark.asyncio
async def test_report_only_policies_are_not_counted_as_enforced():
    """Graph spells this state "enabledForReportingButNotEnforced".

    It starts with "enabled", so a prefix test for "[enabled" placed first
    swallowed the whole state — a tenant staging its Conditional Access in
    report-only mode, enforcing nothing, read as having those policies live.
    Found by feeding real collector output to the parser rather than a fixture.
    """
    text = await _collect([
        _policy("Staging MFA", "enabledForReportingButNotEnforced", ["all"], ["mfa"]),
    ])
    parsed = _parse_ca_policies(text)
    assert parsed["enabled"] == 0, "report-only enforces nothing"
    assert parsed["report_only"] == 1
