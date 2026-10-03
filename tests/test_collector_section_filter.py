"""A scope filter that names an Azure section runs it, in every subscription."""

from __future__ import annotations

from pathlib import Path

from app.modules.m365_audit.collector import AuditCollector


def _collector(sections_filter):
    return AuditCollector(auth=None, out_dir=Path("/nonexistent"), sections_filter=sections_filter)


def test_every_azure_section_is_named_by_its_class_name():
    sections = _collector(None)._build_azure_sections("sub-1", "Prod", multi=True)
    assert {type(s).name for s in sections} == set(AuditCollector.AZURE_SECTION_NAMES)
    assert all("(Prod)" in s.name for s in sections), "the instance name carries the subscription"


def test_a_filter_naming_an_azure_section_enables_it_in_a_named_subscription():
    collector = _collector({"Azure Compute", "Azure Storage"})
    sections = collector._build_azure_sections("sub-1", "Prod", multi=True)
    enabled = {type(s).name for s in sections if collector._section_enabled(s)}
    assert enabled == {"Azure Compute", "Azure Storage"}


def test_no_filter_enables_everything():
    collector = _collector(None)
    assert all(collector._section_enabled(s) for s in collector._build_azure_sections("s", "A"))
