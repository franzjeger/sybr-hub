"""The site summary reports what the gateway said, and nothing it did not.

/v1/sites carries device and client counts, WAN health and the gateway's IPS
posture for every site in one call. Two thirds of the sites in a real account
report no gateway block at all, so the interesting question is not what the
summary does with data — it is what it does without any.
"""

from __future__ import annotations

from app.services.unifi_api import classify_ips_mode, summarise_sites


def _site(**stats):
    return {
        "siteId": "site-1",
        "hostId": "host-1",
        "meta": {"name": "Kontoret", "desc": "", "timezone": "Europe/Oslo"},
        "statistics": stats,
    }


def test_prevention_and_detection_are_not_the_same_posture():
    # IDS raises an alert and lets the traffic through. Calling both "enabled"
    # would flatter a gateway that is not blocking anything.
    assert classify_ips_mode("ips") == ("IPS", "ok")
    assert classify_ips_mode("ids") == ("IDS", "warn")
    assert classify_ips_mode("disabled") == ("Disabled", "bad")


def test_an_unreported_gateway_is_unknown_not_disabled():
    for absent in (None, "", "   "):
        label, severity = classify_ips_mode(absent)
        assert label == "Unknown"
        assert severity == "unknown"


def test_a_site_without_a_gateway_raises_no_finding():
    # 42 of 77 sites in a live account report no gateway. Rendering those as
    # "IPS off" would invent a security finding per site — the mistake
    # wlan_security_label exists to avoid for open WiFi.
    [row] = summarise_sites([_site(counts={"totalDevice": 4})])
    assert row["gateway"]["ips_severity"] == "unknown"
    assert row["findings"] == []


def test_findings_name_what_a_technician_would_act_on():
    [row] = summarise_sites([_site(
        counts={
            "totalDevice": 11, "offlineDevice": 3,
            "pendingUpdateDevice": 2, "criticalNotification": 1,
        },
        gateway={"ipsMode": "disabled", "shortname": "UDMPRO"},
    )])
    joined = " | ".join(row["findings"])
    assert "1 kritiske varsler" in joined
    assert "3 enheter offline" in joined
    assert "gateway blokkerer ikke" in joined
    assert "2 venter fastvareoppdatering" in joined


def test_a_healthy_site_reports_nothing():
    [row] = summarise_sites([_site(
        counts={"totalDevice": 6, "offlineDevice": 0, "wifiClient": 20},
        gateway={"ipsMode": "ips", "ipsSignature": {"rulesCount": 32687, "type": "ET"}},
    )])
    assert row["findings"] == []
    assert row["gateway"]["ips_severity"] == "ok"
    assert row["gateway"]["ips_rules"] == 32687


def test_logged_downtime_is_reported_separately_from_an_issue_count():
    # "Degraded" and "was down" are different conversations with a customer.
    [row] = summarise_sites([_site(wans={
        "WAN": {"externalIp": "203.0.113.9", "wanUptime": 100, "wanIssues": []},
        "WAN2": {"wanUptime": 92, "wanIssues": [{"count": 4, "wanDowntime": True}]},
    })])
    primary, secondary = row["wans"]
    assert primary["issue_count"] == 0 and primary["had_downtime"] is False
    assert secondary["issue_count"] == 4 and secondary["had_downtime"] is True
    assert "WAN har hatt nedetid" in row["findings"]


def test_clients_are_totalled_without_double_counting_guests():
    [row] = summarise_sites([_site(counts={
        "wifiClient": 30, "wiredClient": 12, "guestClient": 5,
    })])
    assert row["clients"]["total"] == 42
    assert row["clients"]["guest"] == 5


def test_missing_statistics_do_not_raise():
    [row] = summarise_sites([{"siteId": "s", "hostId": "h"}])
    assert row["devices"]["total"] == 0
    assert row["wans"] == []
    assert row["findings"] == []
