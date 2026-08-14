"""The Purview cards must agree with the raw data printed below them.

DLP, retention, anti-phish and anti-spam sections are all written as
``_section_block`` dumps: a title line, then per policy an ``[i]`` marker and
its ``Key: Value`` field lines, or ``(none)`` when empty. The count readers
treated every non-header line as a policy, so an empty section reported "1
policy" and a single six-field policy reported "7" — a summary card that
contradicts the appendix on the same page, which is the first thing an auditor
throws the report out for. These pin one policy per block, and zero for empty.
"""

from __future__ import annotations

from app.modules.m365_audit.sections.exchange import _section_block
from app.reports.generator import _extract_policy_names, _parse_purview


def _dlp(policies):
    return _section_block("PURVIEW DLP POLICIES", policies,
                          key_fields=["Name", "Mode", "Priority", "Workload"])


def _retention(policies):
    return _section_block("PURVIEW RETENTION POLICIES", policies,
                          key_fields=["Name", "Enabled", "RetentionRuleTypes"])


def _antiphish(policies):
    return _section_block("ANTI-PHISH POLICIES", policies)


# ── _extract_policy_names ─────────────────────────────────────────────────────


def test_an_empty_block_is_zero_policies():
    assert _extract_policy_names(_antiphish([])) == []


def test_a_single_policy_counts_once_not_once_per_field():
    block = _antiphish([{
        "Name": "Office365 AntiPhish Default",
        "Identity": "Office365 AntiPhish Default",
        "Enabled": True,
        "PhishThresholdLevel": 1,
        "TargetedUserProtection": False,
        "Action": "Quarantine",
    }])
    names = _extract_policy_names(block)
    assert names == ["Office365 AntiPhish Default"], (
        "a six-field policy carrying both Name and Identity must count once, not seven"
    )


def test_two_policies_count_as_two():
    block = _antiphish([
        {"Name": "Policy A", "Enabled": True},
        {"Name": "Policy B", "Enabled": False},
    ])
    assert _extract_policy_names(block) == ["Policy A", "Policy B"]


def test_a_policy_with_no_name_field_still_counts_by_its_marker():
    block = _antiphish([{"Enabled": True, "Action": "Quarantine"}])
    assert len(_extract_policy_names(block)) == 1


# ── _parse_purview DLP / retention ────────────────────────────────────────────


def test_empty_dlp_section_is_zero_not_one():
    out = _parse_purview({"19d_purview_dlp_policies.txt": _dlp([])})
    assert out["dlp_policy_count"] == 0, "the '(none)' placeholder was counted as a policy"
    assert out["dlp_policies"] == []


def test_one_real_dlp_policy_counts_once():
    out = _parse_purview({"19d_purview_dlp_policies.txt": _dlp([
        {"Name": "Default DLP", "Mode": "Enable", "Priority": 0, "Workload": "Exchange"},
    ])})
    assert out["dlp_policy_count"] == 1
    assert out["dlp_policies"][0]["name"] == "Default DLP"


def test_empty_retention_section_is_zero_not_one():
    out = _parse_purview({"19e_purview_retention_policies.txt": _retention([])})
    assert out["retention_policy_count"] == 0


def test_two_retention_policies_count_as_two():
    out = _parse_purview({"19e_purview_retention_policies.txt": _retention([
        {"Name": "Keep 7y", "Enabled": True},
        {"Name": "Delete 30d", "Enabled": True},
    ])})
    assert out["retention_policy_count"] == 2
