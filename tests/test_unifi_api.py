"""Tests for UniFi service-layer helpers."""

from __future__ import annotations

import pytest

from app.services.unifi_api import is_open_wlan_security, wlan_security_label


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("open", "Open"),
        ("wpapsk", "WPA2"),
        ("wpa2", "WPA2"),
        ("wpa3", "WPA3"),
        ("sae", "WPA3"),          # SAE is WPA3-Personal's handshake
        ("wpaeap", "WPA2-Enterprise"),
        ("wpa2eap", "WPA2-Enterprise"),
        ("wpa3eap", "WPA3-Enterprise"),
        ("wep", "WEP (insecure)"),
        ("WPA3", "WPA3"),         # case-insensitive
    ],
)
def test_known_security_values_are_labelled(value, expected):
    assert wlan_security_label(value) == expected


@pytest.mark.parametrize("value", ["", "   ", None, 123, [], {}])
def test_missing_or_non_string_security_is_unknown_not_open(value):
    """Regression: absent or malformed values fell through to "Open".

    The mapping was a chain of substring checks over a default of "Open", so a
    value it did not recognise — including None, which would also raise on
    .lower() — was reported as an unencrypted network.
    """
    assert wlan_security_label(value) == "Unknown"


def test_unrecognised_cipher_is_reported_as_unknown_with_its_value():
    """An unfamiliar cipher must not be reported as an open network.

    Either direction is a false finding: it sends a technician to secure a
    network that is already encrypted, and it would hide a genuinely open SSID
    behind the same label. Surfacing the raw value keeps it actionable.
    """
    label = wlan_security_label("some-future-cipher")
    assert label == "Unknown (some-future-cipher)"
    assert label != "Open"


def test_wep_is_named_rather_than_flattered_or_mislabelled():
    """WEP under the old mapping came out as "Open"."""
    assert wlan_security_label("wep") == "WEP (insecure)"


# ── is_open_wlan_security: the predicate the risk scorer acts on ──────────────


def test_only_a_positive_open_reading_is_an_open_network():
    assert is_open_wlan_security("open") is True
    assert is_open_wlan_security("OPEN") is True


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", 123, [], {}, "some-future-cipher", "wpapsk", "wpa3", "wep"],
)
def test_absent_or_unclassifiable_security_is_not_an_open_network(value):
    """An open-WiFi finding is critical-priority and names the SSID.

    Everything here is either encrypted or unreadable; neither may raise it.
    """
    assert is_open_wlan_security(value) is False
