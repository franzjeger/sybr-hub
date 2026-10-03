"""Azure profile values must not be able to add directives to the openvpn3 config.

The gateway FQDN went into ``remote {gw} 443`` and the CA PEM into a <ca>
block without any check, so a newline in the gateway, or text after the PEM
(``</ca>`` and then anything), became directives in the config openvpn3
starts. The importer also accepted a "certificate" that was not base64,
because b64decode silently skips characters outside its alphabet.
"""

from __future__ import annotations

import shutil

import pytest

import app.core.database as database_module
from app.core.database import run_migrations
from app.core.exceptions import ValidationError
from app.models.vpn import VpnProtocol
from app.services import vpn_manager
from app.services.vpn_backends import azure
from app.services.vpn_backends.azure import _build_ovpn_config

CERT = "-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIUQ0FQVUJMSUM=\n-----END CERTIFICATE-----"
CERT2 = "-----BEGIN CERTIFICATE-----\nMIIBtDCCAVqgAwIBAgIUSU5URVJNRUQ=\n-----END CERTIFICATE-----"
KEY_HEX = "ab" * 256


@pytest.fixture(autouse=True)
async def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(vpn_manager, "VPN_SECRETS_DIR", tmp_path / "vpn_secrets")
    await run_migrations()


@pytest.mark.parametrize(
    "gateway",
    [
        "gw.example.com\nscript-security 2",
        "gw.example.com 443\nup /bin/sh",
        "gw.example.com\r",
        "gw example.com",
        "-gw.example.com",
        "gw.example.com:443",
        "fe80::1%eth0",
    ],
)
def test_a_hostile_gateway_is_refused(gateway):
    with pytest.raises(ValidationError):
        _build_ovpn_config(gateway, CERT, KEY_HEX)


@pytest.mark.parametrize(
    "ca",
    [
        CERT + "\n</ca>\nup /bin/sh",
        "remote attacker.example.net 443\n" + CERT,
        CERT.replace("MIIBszCC", "MII Bsz\nup /bin/sh\nCC"),
        "-----BEGIN CERTIFICATE-----\n</ca>\n-----END CERTIFICATE-----",
        "not a certificate",
    ],
)
def test_text_outside_a_pem_certificate_is_refused(ca):
    with pytest.raises(ValidationError):
        _build_ovpn_config("gw.example.com", ca, KEY_HEX)


@pytest.mark.parametrize("key", ["ab\n</tls-auth>\nup /bin/sh", "zz" * 256, "abc", "ab" * 600])
def test_a_tls_key_that_is_not_hex_is_refused(key):
    with pytest.raises(ValidationError):
        _build_ovpn_config("gw.example.com", CERT, key)


def test_a_chain_and_crlf_line_endings_are_accepted():
    cfg = _build_ovpn_config("gw.example.com", (CERT + "\n\n" + CERT2).replace("\n", "\r\n"), "")
    assert f"<ca>\n{CERT}\n{CERT2}\n</ca>" in cfg


async def test_connect_refuses_before_writing_a_config(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/openvpn3")

    def _no_write(*_a, **_kw):
        raise AssertionError("wrote a config built from a hostile gateway")

    monkeypatch.setattr(azure, "_write_private", _no_write)
    with pytest.raises(ValidationError):
        await azure.connect({"gateway_fqdn": "gw.example.com\nup /bin/sh"}, "token")


async def test_a_hostile_profile_is_refused_when_saved():
    with pytest.raises(ValidationError):
        await vpn_manager.create_profile(
            "AZ",
            VpnProtocol.azure,
            {"gateway_fqdn": "gw.example.com", "tenant_id": "t", "ca_cert_pem": CERT + "\nup x"},
        )
    assert await vpn_manager.list_profiles() == []


async def test_a_valid_profile_is_stored_without_its_tls_key():
    profile = await vpn_manager.create_profile(
        "AZ",
        VpnProtocol.azure,
        {
            "gateway_fqdn": "azuregateway-1.vpn.azure.com",
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "client_id": "41b23e61-6c1e-4545-b367-cd054e0ed4b4",
            "ca_cert_pem": CERT,
            "server_secret_hex": KEY_HEX,
            "dns_servers": ["10.0.0.4"],
        },
    )
    stored = (await vpn_manager.get_profile(profile.id)).config
    assert "server_secret_hex" not in stored
    assert vpn_manager._read_secrets(profile.id)["server_secret_hex"] == KEY_HEX


async def test_import_refuses_a_ca_that_is_not_base64():
    xml = (
        "<AzVpnProfile><fqdn>gw.example.com</fqdn><audience>a</audience>"
        "<issuer>https://sts.windows.net/t/</issuer></AzVpnProfile>"
        "<!-- VPN_SETTINGS_SEPARATOR -->"
        "<VpnProfile><string>"
        + "QUJD" * 30
        + "\n&#10;-----END CERTIFICATE-----</string></VpnProfile>"
    )
    with pytest.raises(ValidationError):
        await vpn_manager.import_profile("AZ", xml, "azure")


async def test_import_of_a_real_profile_pair_still_works():
    ca_b64 = "MIIBszCCAVmgAwIBAgIU" * 8
    xml = (
        "<AzVpnProfile><fqdn>azuregateway-1.vpn.azure.com</fqdn>"
        "<audience>41b23e61-6c1e-4545-b367-cd054e0ed4b4</audience>"
        "<issuer>https://sts.windows.net/00000000-0000-0000-0000-000000000001/</issuer>"
        f"<serversecret>{KEY_HEX}</serversecret></AzVpnProfile>"
        "<!-- VPN_SETTINGS_SEPARATOR -->"
        f"<VpnProfile><string>{ca_b64}</string>"
        "<CustomDnsServers>10.0.0.4</CustomDnsServers></VpnProfile>"
    )
    profile = await vpn_manager.import_profile("AZ", xml, "azure")
    stored = (await vpn_manager.get_profile(profile.id)).config

    assert stored["gateway_fqdn"] == "azuregateway-1.vpn.azure.com"
    assert stored["tenant_id"] == "00000000-0000-0000-0000-000000000001"
    assert stored["ca_cert_pem"].startswith("-----BEGIN CERTIFICATE-----\n")
    assert stored["dns_servers"] == ["10.0.0.4"]
    assert vpn_manager._read_secrets(profile.id) == {"server_secret_hex": KEY_HEX}
