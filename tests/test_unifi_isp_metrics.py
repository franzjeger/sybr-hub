"""The ISP summary reads the shape the API actually returns.

The previous parser looked for ``entry["data"]["wan"]``. A site entry has no
``data`` key — the readings sit under ``entry["periods"][]["data"]["wan"]`` —
so every field resolved to nothing and was rendered as a hard zero, including a
red 0% WAN uptime on links reporting 100%. Nothing caught it because the only
way to exercise the parser was against the live API.

The payloads below are the shape confirmed against that API: 29 site entries,
each with ~283 readings for 5m/24h, WAN fields ``download_kbps``,
``upload_kbps``, ``avgLatency``, ``maxLatency``, ``packetLoss``, ``uptime``,
``downtime``, ``ispName`` and ``ispAsn``.
"""

from __future__ import annotations

from app.services.unifi_api import summarise_isp_sites


def _reading(**overrides):
    wan = {
        "download_kbps": 658000,
        "upload_kbps": 100000,
        "avgLatency": 4,
        "maxLatency": 13,
        "packetLoss": 0,
        "uptime": 100,
        "downtime": 0,
        "ispName": "Example ISP",
        "ispAsn": "AS64496",
    }
    wan.update(overrides)
    return {"metricTime": "2026-08-08T00:00:00Z", "data": {"wan": wan}}


def _site(readings, site_id="site-1"):
    return {"siteId": site_id, "hostId": "host-1", "periods": readings}


def test_readings_under_periods_are_found():
    [summary] = summarise_isp_sites([_site([_reading(), _reading(avgLatency=6)])])
    assert summary["has_readings"] is True
    assert summary["data_points"] == 2
    assert summary["latest"]["latency_ms"] == 6
    assert summary["latest"]["download_mbps"] == 658.0
    assert summary["isp"] == "Example ISP"


def test_the_old_top_level_data_path_yields_nothing():
    # The exact shape the previous parser assumed. If a future edit starts
    # reading it again, this fails rather than quietly rendering zeros.
    legacy = {"siteId": "site-1", "data": {"wan": {"download_kbps": 658000}}}
    [summary] = summarise_isp_sites([legacy])
    assert summary["has_readings"] is False
    assert summary["data_points"] == 0


def test_a_site_without_readings_reports_none_not_zero():
    [summary] = summarise_isp_sites([_site([])])
    assert summary["has_readings"] is False
    # None renders as a dash. Zero renders as a red outage that is not
    # happening — which is the bug this whole test file exists for.
    assert summary["averages"]["uptime_pct"] is None
    assert summary["latest"]["download_mbps"] is None
    assert summary["worst"]["packet_loss"] is None


def test_averages_span_every_reading():
    site = _site([_reading(avgLatency=2), _reading(avgLatency=4), _reading(avgLatency=9)])
    [summary] = summarise_isp_sites([site])
    assert summary["averages"]["latency_ms"] == 5.0
    assert summary["data_points"] == 3


def test_the_worst_reading_survives_averaging():
    # A 24-hour average hides a five-minute outage, which is precisely the
    # event a technician is looking for.
    site = _site([_reading(packetLoss=0, maxLatency=5)] * 100 + [_reading(packetLoss=37, maxLatency=900)])
    [summary] = summarise_isp_sites([site])
    assert summary["averages"]["packet_loss"] < 1
    assert summary["worst"]["packet_loss"] == 37
    assert summary["worst"]["max_latency_ms"] == 900


def test_kbps_becomes_mbps():
    [summary] = summarise_isp_sites([_site([_reading(download_kbps=1000000)])])
    assert summary["latest"]["download_mbps"] == 1000.0


def test_a_site_is_identified_even_without_a_site_id():
    [summary] = summarise_isp_sites([{"hostId": "host-9", "periods": [_reading()]}])
    assert summary["site_id"] == "host-9"
