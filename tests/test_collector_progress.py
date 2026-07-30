"""The collector must not report progress for sections nobody selected.

Tenant Information always runs, selected or not, because every later section
needs its verified_domains. It used to report progress either way, so the
progress bar counted a section its denominator had excluded.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.modules.base import SectionResult, SectionStatus
from app.modules.m365_audit.collector import AuditCollector


class _StubTenantSection:
    """Stands in for TenantSection, recording the callback it was handed."""

    instances: list["_StubTenantSection"] = []

    def __init__(self, out_dir, graph, progress_cb=None):
        self.progress_cb = progress_cb
        self.verified_domains = ["example.com"]
        self.result = SectionResult(name="Tenant Information")
        _StubTenantSection.instances.append(self)

    async def collect(self):
        # Real sections report through the callback they were given; if that
        # callback is None they stay silent, which is the whole point here.
        if self.progress_cb:
            self.progress_cb("Tenant Information", SectionStatus.RUNNING, None)
            self.progress_cb("Tenant Information", SectionStatus.DONE, None)
        self.result.status = SectionStatus.DONE
        return self.result


class _NullAsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _StubExchangeSection:
    def __init__(self, out_dir, exo_data, verified_domains, progress_cb=None, *, graph):
        self.progress_cb = progress_cb
        self.result = SectionResult(name="Exchange Online")

    async def collect(self):
        if self.progress_cb:
            self.progress_cb("Exchange Online", SectionStatus.DONE, None)
        self.result.status = SectionStatus.DONE
        return self.result


class _StubAuth(_NullAsyncContext):
    credential = object()
    subscription_id = ""

    async def collect_exo_data(self, out_dir):
        return {}

    def list_subscriptions(self):
        return []


async def _run_collector(tmp_path, monkeypatch, sections_filter):
    """Drive AuditCollector.run() with everything but Tenant stubbed out."""
    _StubTenantSection.instances.clear()

    tenant_mod = SimpleNamespace(TenantSection=_StubTenantSection)
    monkeypatch.setitem(sys.modules, "app.modules.m365_audit.sections.tenant", tenant_mod)
    monkeypatch.setitem(
        sys.modules,
        "app.modules.m365_audit.sections.exchange",
        SimpleNamespace(ExchangeSection=_StubExchangeSection),
    )
    monkeypatch.setattr(
        "app.modules.m365_audit.collector.GraphClient",
        lambda credential: _NullAsyncContext(),
    )
    monkeypatch.setattr(AuditCollector, "_build_graph_sections", lambda self, g, d: [])

    reported: list[tuple[str, SectionStatus]] = []
    collector = AuditCollector(
        auth=_StubAuth(),
        out_dir=tmp_path / "out",
        progress_cb=lambda name, status, detail: reported.append((name, status)),
        sections_filter=sections_filter,
    )
    await collector.run()
    return reported


@pytest.mark.asyncio
async def test_deselected_tenant_runs_but_stays_silent(tmp_path, monkeypatch):
    reported = await _run_collector(tmp_path, monkeypatch, {"Users"})

    assert _StubTenantSection.instances, "tenant info must still be collected"
    assert _StubTenantSection.instances[0].verified_domains == ["example.com"]
    assert reported == [], f"unselected section reported progress: {reported}"


@pytest.mark.asyncio
async def test_selected_tenant_still_reports(tmp_path, monkeypatch):
    reported = await _run_collector(tmp_path, monkeypatch, {"Tenant Information"})

    assert ("Tenant Information", SectionStatus.DONE) in reported


@pytest.mark.asyncio
async def test_no_filter_reports_tenant(tmp_path, monkeypatch):
    reported = await _run_collector(tmp_path, monkeypatch, None)

    assert ("Tenant Information", SectionStatus.DONE) in reported
