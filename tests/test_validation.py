"""Tests for input validators guarding config files and device CLIs.

The values covered here previously reached a swanctl config written via
``sudo tee`` (arbitrary root-owned file write) and a FortiOS CLI session over
SSH (arbitrary firewall commands), unvalidated.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.core.validation import (
    quote_conf_value,
    validate_cidr,
    validate_cidr_list,
    validate_host,
    validate_host_list,
    validate_identifier,
    validate_ssh_public_key,
)
from app.services.vpn_backends.fortigate_ipsec import _build_swanctl_conf, _conf_path

# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["msp-fg", "root", "msp_api_admin", "super_admin", "fg.1"])
def test_valid_identifiers_pass(value):
    assert validate_identifier(value, "field") == value


@pytest.mark.parametrize(
    "value",
    [
        "../../etc/cron.d/pwn",      # path traversal
        "a/b",                       # path separator
        "a\\b",                      # windows separator
        'name" evil "',              # quote break-out
        "name\nset password x",      # newline → extra CLI command
        "name; reboot",              # command separator
        "name with spaces",
        "{braces}",
        "",                          # empty
        "-leading-dash",             # must start alphanumeric
    ],
)
def test_dangerous_identifiers_are_rejected(value):
    with pytest.raises(ValidationError):
        validate_identifier(value, "field")


def test_identifier_length_is_bounded():
    with pytest.raises(ValidationError):
        validate_identifier("a" * 40, "field", max_length=35)


# ---------------------------------------------------------------------------
# Hosts and CIDRs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["10.0.0.1", "vpn.example.com", "fw-01.corp.local"])
def test_valid_hosts_pass(value):
    assert validate_host(value) == value


@pytest.mark.parametrize("value", ["10.0.0.1\nremote_addrs = evil", "host name", "", "a|b"])
def test_dangerous_hosts_are_rejected(value):
    with pytest.raises(ValidationError):
        validate_host(value)


def test_host_list_accepts_comma_separated():
    assert validate_host_list("10.0.0.1, vpn.example.com", "host") == "10.0.0.1,vpn.example.com"


def test_host_list_rejects_an_injected_member():
    with pytest.raises(ValidationError):
        validate_host_list("10.0.0.1,evil host", "host")


def test_cidr_normalises():
    assert validate_cidr("10.0.0.0/24") == "10.0.0.0/24"
    assert validate_cidr("10.0.0.5") == "10.0.0.5"


@pytest.mark.parametrize("value", ["not-a-cidr", "10.0.0.0/33", "", "0.0.0.0/0 ; reboot"])
def test_bad_cidrs_are_rejected(value):
    with pytest.raises(ValidationError):
        validate_cidr(value)


def test_cidr_list_splits_on_commas_and_whitespace():
    assert validate_cidr_list("10.0.0.0/24, 192.168.1.0/24") == [
        "10.0.0.0/24",
        "192.168.1.0/24",
    ]
    assert validate_cidr_list("10.0.0.0/24 192.168.1.0/24") == [
        "10.0.0.0/24",
        "192.168.1.0/24",
    ]


def test_cidr_list_rejects_trailing_cli_injection():
    with pytest.raises(ValidationError):
        validate_cidr_list('0.0.0.0/0\n            next\n        end\n    set accprofile x')


# ---------------------------------------------------------------------------
# SSH public keys
# ---------------------------------------------------------------------------


def test_valid_ssh_key_passes():
    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyMaterialHere tech@sybr"
    assert validate_ssh_public_key(key) == key


@pytest.mark.parametrize(
    "value",
    [
        'ssh-ed25519 AAAA" set password "x',   # quote break-out into FortiOS
        "ssh-ed25519 AAAA\nset admintimeout 480",
        "not-a-key",
        "",
    ],
)
def test_bad_ssh_keys_are_rejected(value):
    with pytest.raises(ValidationError):
        validate_ssh_public_key(value)


# ---------------------------------------------------------------------------
# Config-value quoting
# ---------------------------------------------------------------------------


def test_quote_escapes_quotes_and_backslashes():
    assert quote_conf_value('a"b', "psk") == 'a\\"b'
    assert quote_conf_value("a\\b", "psk") == "a\\\\b"


@pytest.mark.parametrize("value", ["a\nb", "a\rb", "a\x00b"])
def test_quote_rejects_control_characters(value):
    with pytest.raises(ValidationError):
        quote_conf_value(value, "psk")


# ---------------------------------------------------------------------------
# swanctl config path + rendering
# ---------------------------------------------------------------------------


def test_conf_path_stays_inside_conf_dir():
    from app.services.vpn_backends.fortigate_ipsec import CONF_DIR

    assert _conf_path("msp-fg") == (CONF_DIR / "msp-fg.conf").resolve()


@pytest.mark.parametrize(
    "conn_name",
    ["../../etc/cron.d/pwn", "../../../root/.ssh/authorized_keys", "a/b", ""],
)
def test_conf_path_refuses_to_escape_conf_dir(conn_name):
    """Regression: conn_name came from a user profile and was written via sudo tee."""
    with pytest.raises(ValidationError):
        _conf_path(conn_name)


def test_swanctl_conf_renders_for_a_sane_profile():
    conf = _build_swanctl_conf(
        {
            "host": "vpn.example.com",
            "username": "tech",
            "password": "hunter2",
            "psk": "sharedsecret",
            "routes": ["10.0.0.0/24"],
        },
        "msp-fg",
    )
    assert "remote_addrs = vpn.example.com" in conf
    assert 'secret = "sharedsecret"' in conf
    assert "remote_ts = 10.0.0.0/24" in conf


def test_swanctl_conf_escapes_a_quote_in_the_psk():
    """A quote in a secret must not close its field and open a new directive."""
    conf = _build_swanctl_conf(
        {"host": "10.0.0.1", "username": "tech", "password": "p", "psk": 'x" evil "y'},
        "msp-fg",
    )
    assert 'secret = "x\\" evil \\"y"' in conf


@pytest.mark.parametrize(
    "config",
    [
        {"host": "10.0.0.1\nvips = 1.2.3.4", "username": "u", "password": "p", "psk": "s"},
        {"host": "10.0.0.1", "username": "u\nid = admin", "password": "p", "psk": "s"},
        {"host": "10.0.0.1", "username": "u", "password": "p\n", "psk": "s"},
        {"host": "10.0.0.1", "username": "u", "password": "p", "psk": "s\nsecret = t"},
        {"host": "10.0.0.1", "username": "u", "password": "p", "psk": "s",
         "routes": ["10.0.0.0/24\n        start_action = start"]},
    ],
)
def test_swanctl_conf_rejects_injected_newlines(config):
    with pytest.raises(ValidationError):
        _build_swanctl_conf(config, "msp-fg")


def test_swanctl_conf_rejects_bad_conn_name():
    with pytest.raises(ValidationError):
        _build_swanctl_conf(
            {"host": "10.0.0.1", "username": "u", "password": "p", "psk": "s"},
            "../../evil",
        )


# ---------------------------------------------------------------------------
# FortiOS CLI parameters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"api_admin_name": 'x" \n set accprofile "super_admin'},
        {"accprofile": "super_admin\n set password x"},
        {"vdom": 'root" \n edit "admin'},
        {"trusted_hosts": "0.0.0.0/0\n next\n end\n execute reboot"},
        {"trusted_hosts": "not-a-cidr"},
    ],
)
async def test_generate_api_token_rejects_cli_injection(kwargs):
    """Regression: these four fields were f-stringed straight into a CLI script.

    Validation must happen before any connection is attempted, so a bad value
    can never reach the firewall.
    """
    from app.services.fortigate_api import generate_api_token

    params = {
        "ssh_host": "10.0.0.1",
        "ssh_port": 22,
        "ssh_user": "admin",
        "ssh_password": "pw",
        **kwargs,
    }
    with pytest.raises(ValidationError):
        await generate_api_token(**params)


@pytest.mark.parametrize(
    ("admin_user", "public_key"),
    [
        ("../../monitor/system/status", "ssh-ed25519 AAAAC3Nza key"),
        ("admin", 'ssh-ed25519 AAAA" set password "x'),
        ("admin", "definitely-not-a-key"),
    ],
)
async def test_deploy_ssh_key_rejects_bad_input(admin_user, public_key):
    """admin_user lands in a URL path; public_key lands in a FortiOS config field."""
    from app.services.fortigate_api import deploy_ssh_key

    with pytest.raises(ValidationError):
        await deploy_ssh_key({"FortiGateHost": "10.0.0.1"}, "token", admin_user, public_key)


async def test_factory_bootstrap_rejects_injected_api_admin_name():
    from app.services.fortigate_api import factory_bootstrap

    with pytest.raises(ValidationError):
        await factory_bootstrap(host="10.0.0.1", api_admin_name='x" \n execute reboot')
