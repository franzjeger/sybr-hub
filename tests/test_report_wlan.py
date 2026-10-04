"""Regression tests for open-WiFi findings in the report.

``network_audit._audit_unifi_controller`` built its WLAN summary with
``w.get("security", "open")``. A controller response that omitted the security
field — older firmware, a partial response — became the string "open", and two
consumers acted on it as fact:

  * the network risk (now ``_network_penalty``) charged 5 penalty points;
  * ``_build_recommendations`` raised a *critical* recommendation naming the
    SSID, telling a technician to go secure a network that may already be
    encrypted.

The template made it worse in the other direction: it coloured the cell red
only for the literal string "open" and green for everything else, so once the
default was removed a missing value would have rendered as a reassuring green
blank. Security state is three-valued here — open, encrypted, unknown — and
each has to render as itself.
"""

from __future__ import annotations

import pytest

from app.reports.recommendations import _build_recommendations
from app.reports.risk import _is_open_wlan, _network_penalty


def _network(wlans: list[dict]) -> dict:
    return {
        "has_data": True,
        "fortigate": None,
        "unifi": {"mode": "controller", "wlans": wlans},
    }


# ── The predicate ─────────────────────────────────────────────────────────────


def test_explicitly_open_wlan_is_still_detected():
    assert _is_open_wlan({"name": "Guest", "security": "open"}) is True


@pytest.mark.parametrize(
    "wlan",
    [
        {"name": "Corp"},  # field absent entirely
        {"name": "Corp", "security": None},  # present but null
        {"name": "Corp", "security": ""},
        {"name": "Corp", "security": "wpapsk"},
        {"name": "Corp", "security": "some-future-cipher"},
    ],
)
def test_unknown_or_encrypted_wlan_is_not_open(wlan):
    assert _is_open_wlan(wlan) is False


def test_security_label_is_preferred_when_present():
    """New audit files carry the classification; use it rather than re-deriving."""
    assert _is_open_wlan({"security": "open", "security_label": "Open"}) is True
    assert _is_open_wlan({"security": "wpa3", "security_label": "WPA3"}) is False


def test_label_from_an_older_file_still_falls_back_to_the_raw_value():
    assert _is_open_wlan({"security": "open"}) is True


# ── Risk scoring ──────────────────────────────────────────────────────────────


def test_missing_security_field_does_not_cost_penalty_points():
    assert _network_penalty(_network([{"name": "Corp", "enabled": True}])) == 0


def test_a_real_open_wlan_still_costs_penalty_points():
    assert _network_penalty(_network([{"name": "Guest", "security": "open", "enabled": True}])) == 5


def test_two_open_wlans_cost_the_same_as_one():
    wlans = [
        {"name": "Guest", "security": "open", "enabled": True},
        {"name": "Lobby", "security": "open", "enabled": True},
    ]
    assert _network_penalty(_network(wlans)) == 5


def test_a_disabled_open_wlan_is_not_penalised():
    network = _network([{"name": "Old-Guest", "security": "open", "enabled": False}])
    assert _network_penalty(network) == 0


def test_the_network_penalty_is_capped_at_fifteen():
    network = {
        "has_data": True,
        "fortigate": {"admins": [{"two_factor": False}] * 3, "policy_warnings": []},
        "unifi": {"mode": "direct", "default_creds_count": 3, "eol_count": 2},
    }
    assert _network_penalty(network) == 15


# ── Recommendations ───────────────────────────────────────────────────────────


def _open_wifi_rec(network: dict):
    recs = _build_recommendations(
        mfa={"has_data": True, "pct": 100.0, "no_mfa": 0},
        spf_dmarc=[],
        secure_score={"has_data": True, "pct": 90.0, "improvements": []},
        ext_fwd="",
        risky_users="",
        licenses=[],
        network=network,
    )
    return next((r for r in recs if r.get("finding_id") == "finding-uf-open-wifi"), None)


def test_no_critical_open_wifi_recommendation_from_a_missing_field():
    """This was the loudest false finding the network audit could produce."""
    assert _open_wifi_rec(_network([{"name": "Corp", "enabled": True}])) is None


def test_encrypted_wlans_produce_no_open_wifi_recommendation():
    rec = _open_wifi_rec(
        _network(
            [
                {"name": "Corp", "security": "wpa3", "enabled": True},
                {"name": "IoT", "security": "wpapsk", "enabled": True},
            ]
        )
    )
    assert rec is None


def test_a_genuinely_open_wlan_is_still_reported_by_name():
    rec = _open_wifi_rec(
        _network(
            [
                {"name": "Corp", "security": "wpa3", "enabled": True},
                {"name": "FreeWiFi", "security": "open", "enabled": True},
            ]
        )
    )
    assert rec is not None
    assert rec["priority"] == "critical"
    assert rec["sub_items"] == ["FreeWiFi"]


def test_wlan_without_a_name_does_not_raise():
    """The old list comprehension indexed w["name"] directly."""
    rec = _open_wifi_rec(_network([{"security": "open", "enabled": True}]))
    assert rec is not None
    assert rec["sub_items"] == [""]


# ── Template rendering: three states, three colours ───────────────────────────


def _render_wlan_row(wlan: dict, lang: str = "en") -> str:
    """Render just the WLAN table row markup from the report template.

    Extracting the loop keeps this from depending on a full report context
    while still exercising the real template source rather than a copy.
    """
    import re
    from pathlib import Path

    from jinja2 import Environment

    from app.reports.i18n import T

    tpl_path = Path("app/reports/templates/report_customer.html.j2")
    src = tpl_path.read_text(encoding="utf-8")
    m = re.search(r"(\{% for w in uf\.wlans %\}.*?\{% endfor %\})", src, re.S)
    assert m, "WLAN loop not found — update this test alongside the template"
    env = Environment(autoescape=True)
    return env.from_string(m.group(1)).render(uf={"wlans": [wlan]}, t=T(lang))


def test_open_wlan_renders_red():
    row = _render_wlan_row({"name": "FreeWiFi", "security": "open", "security_label": "Open"})
    assert "var(--red" in row
    assert ">Open<" in row


def test_unknown_security_renders_amber_not_green():
    """The old rule coloured everything that wasn't 'open' green."""
    row = _render_wlan_row({"name": "Corp", "security": None, "security_label": "Unknown"})
    assert "var(--orange" in row
    assert "green" not in row
    assert ">Unknown<" in row


def test_encrypted_wlan_renders_green():
    row = _render_wlan_row({"name": "Corp", "security": "wpa3", "security_label": "WPA3"})
    assert "green" in row
    assert "var(--red" not in row and "var(--orange" not in row


def test_wep_renders_red_rather_than_green():
    """WEP is not "not open", it is broken — it must not share green with WPA3."""
    row = _render_wlan_row(
        {"name": "Legacy", "security": "wep", "security_label": "WEP (insecure)"}
    )
    assert "var(--red" in row
    assert "green" not in row


def test_a_file_without_security_label_still_renders_something():
    row = _render_wlan_row({"name": "Corp", "security": "wpapsk"})
    assert ">wpapsk<" in row


def test_a_file_with_neither_field_renders_unknown_not_blank():
    row = _render_wlan_row({"name": "Corp"})
    assert ">Unknown<" in row
    assert "var(--orange" in row


# ── The collector's English labels, in a Norwegian report ─────────────────────


@pytest.mark.parametrize(
    ("wlan", "shown", "colour"),
    [
        ({"security": None, "security_label": "Unknown"}, ">Ukjent<", "var(--orange"),
        ({}, ">Ukjent<", "var(--orange"),
        ({"security": "x9", "security_label": "Unknown (x9)"}, ">Ukjent (x9)<", "var(--orange"),
        ({"security": "open", "security_label": "Open"}, ">Åpen<", "var(--red"),
        ({"security": "open"}, ">Åpen<", "var(--red"),
        ({"security": "wep", "security_label": "WEP (insecure)"}, ">WEP (usikker)<", "var(--red"),
        ({"security": "wpa3", "security_label": "WPA3"}, ">WPA3<", "green"),
    ],
    ids=["unknown", "neither field", "unrecognised", "open", "open, older file", "wep", "wpa3"],
)
def test_a_norwegian_report_names_the_security_in_norwegian(wlan, shown, colour):
    row = _render_wlan_row({"name": "Corp", **wlan}, lang="no")
    assert shown in row
    assert colour in row


def test_an_older_file_with_raw_wep_is_red_not_green():
    """The colour rule matched "WEP" case-sensitively, and an older file says "wep"."""
    row = _render_wlan_row({"name": "Legacy", "security": "wep"})
    assert "var(--red" in row
    assert "green" not in row
