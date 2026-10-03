"""Request models for the FortiGate, UniFi, TLS/DNS-check and device-dashboard endpoints.

These routes decide where a customer's stored device credentials travel, so
the models are strict about shape (``extra="forbid"``, typed fields) and
leave the checks that carry a specific message where they were: host and port
validation, "host and token are required", the admin-only retarget rule. A
port arrives from the forms as a number, the text of one, an empty string or
null, and the handlers' own parser already turns each into a port or a 400
naming the value — so ports are admitted in those shapes and parsed there.
"""

from __future__ import annotations

from typing import Any, Union

from pydantic import BaseModel, ConfigDict, Field

# A port as the forms send it; the handler's parser has the message for a bad one.
PortValue = Union[int, str, None]


# ── FortiGate ────────────────────────────────────────────────────────────────


class FortiGateTestRequest(BaseModel):
    """Try a FortiGate REST API token against an address the caller names."""

    model_config = ConfigDict(extra="forbid")

    host: str | None = None
    port: PortValue = None
    api_token: str | None = None
    vdom: str | None = None
    verify_ssl: bool = True


class FortiGateSaveRequest(BaseModel):
    """The active customer's FortiGate connection.

    Every field is "absent or null means leave alone" — the handler writes only
    what is present, because a field that used to be reset by omission left a
    customer holding credentials with no address recorded for them. An empty
    host string is the one deliberate clear.
    """

    model_config = ConfigDict(extra="forbid")

    host: str | None = None
    port: PortValue = None
    vdom: str | None = None
    verify_ssl: bool | None = None
    api_token: str | None = None


class FortiGateDeployKey(BaseModel):
    """An SSH public key for a FortiGate admin user."""

    model_config = ConfigDict(extra="forbid")

    admin_user: str = ""
    public_key: str = ""


class FortiGateGenerateToken(BaseModel):
    """Create a REST API admin over SSH. Defaults are the handler's old ones."""

    model_config = ConfigDict(extra="forbid")

    ssh_host: str = ""
    ssh_port: int = 22
    ssh_user: str = "admin"
    ssh_password: str = ""
    api_admin_name: str = "msp_api_admin"
    vdom: str = "root"
    trusted_hosts: str = "0.0.0.0/0"
    accprofile: str = "super_admin"


class FortiGateBootstrap(BaseModel):
    """Bootstrap a factory-default FortiGate reachable at ``host``."""

    model_config = ConfigDict(extra="forbid")

    host: str = ""
    ssh_port: PortValue = None
    hostname: str = ""
    api_admin_name: str = "msp_api_admin"


# ── UniFi ────────────────────────────────────────────────────────────────────


class UniFiTestRequest(BaseModel):
    """Try a controller login against an address the caller names."""

    model_config = ConfigDict(extra="forbid")

    host: str | None = None
    username: str | None = None
    password: str | None = None
    is_unifi_os: bool = False


class UniFiDeviceLogin(BaseModel):
    """A standalone UniFi device and the SSH login to reach it.

    ``ubnt``/``ubnt`` is the factory login, and was the handlers' default.
    """

    model_config = ConfigDict(extra="forbid")

    host: str = ""
    username: str = "ubnt"
    password: str = "ubnt"


class UniFiDeviceTest(UniFiDeviceLogin):
    # The device list sends each entry's ``type``, which may be missing or null.
    device_type: str | None = "ap"


class UniFiSetInform(UniFiDeviceLogin):
    controller_url: str = ""


class NetworkScanRequest(BaseModel):
    """A subnet to probe for UniFi devices.

    ``max_concurrent`` sizes a semaphore: zero waited forever and a negative
    number was a 500. The scanner refuses subnets above 1024 hosts, so more
    probes than that buy nothing.
    """

    model_config = ConfigDict(extra="forbid")

    subnet: str = ""
    max_concurrent: int = Field(default=50, ge=1, le=1024)


class NetworkConfigBackup(BaseModel):
    """A device's running config, as fetched by /unifi/device-config."""

    model_config = ConfigDict(extra="forbid")

    host: str = ""
    config: str = ""


class UniFiSaveRequest(BaseModel):
    """The active customer's UniFi connection, or its direct-device list.

    "Absent or null means leave alone" for every field, for the same reason as
    the FortiGate save. ``devices`` is stored as given, so its entries stay
    free-form objects; the handler validates each one's host.
    """

    model_config = ConfigDict(extra="forbid")

    mode: str | None = None
    host: str | None = None
    is_unifi_os: bool | None = None
    site: str | None = None
    devices: list[dict[str, Any]] | None = None
    username: str | None = None
    password: str | None = None


class SiteManagerAuth(BaseModel):
    """Sign in to UniFi Site Manager with an API key or an SSO login."""

    model_config = ConfigDict(extra="forbid")

    api_key: str = ""
    username: str = ""
    password: str = ""
    customer_id: str | None = None


class SiteManagerVerify2fa(BaseModel):
    """The second step of an SSO sign-in that asked for a TOTP code."""

    model_config = ConfigDict(extra="forbid")

    session_token: str = ""
    code: str = ""
    customer_id: str | None = None


class SiteMatchPair(BaseModel):
    """One accepted site → customer link.

    ``extra="ignore"``: the proposals GET /unifi/site-matches returns carry
    names, a score and a confidence beside the two ids, and a client applying
    them sends them back as they came. Only the ids are read.
    """

    model_config = ConfigDict(extra="ignore")

    customer_id: str | None = None
    host_id: str | None = None


class SiteMatchesApply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matches: list[SiteMatchPair] | None = None


# ── TLS and DNS checks ───────────────────────────────────────────────────────


class TlsCheckRequest(BaseModel):
    """One endpoint to check. A missing host keeps the handler's message."""

    model_config = ConfigDict(extra="forbid")

    host: str = ""
    port: int = 443


class TlsEndpoint(BaseModel):
    """An endpoint as GET /tls/auto-discover lists it, sent back for a scan."""

    model_config = ConfigDict(extra="forbid")

    host: str = ""
    port: int = 443
    label: str = ""
    source: str | None = None
    # The customer discovery found it under; the scan route refuses one the
    # caller does not hold, and files the reading under it.
    customer_id: str | None = Field(default=None, max_length=128)


class TlsScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoints: list[TlsEndpoint] = []


class DnsCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str | None = None


class DnsBulkCheckRequest(BaseModel):
    """Domains to check; the handler checks the first 50."""

    model_config = ConfigDict(extra="forbid")

    domains: list[str] = []


# ── Device dashboard ─────────────────────────────────────────────────────────


class PollInterval(BaseModel):
    """Seconds between device polls; the poller clamps it to 10-300."""

    model_config = ConfigDict(extra="forbid")

    interval: int = 60
