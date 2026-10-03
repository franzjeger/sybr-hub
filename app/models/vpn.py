"""VPN data models — ported from SuperManager supermgr-core/src/vpn/."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Column
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


class VpnProtocol(str, Enum):
    wireguard = "wireguard"
    fortigate_ipsec = "fortigate_ipsec"
    openvpn = "openvpn"
    azure = "azure"


class VpnState(str, Enum):
    disconnected = "disconnected"
    connecting = "connecting"
    connected = "connected"
    disconnecting = "disconnecting"
    error = "error"


class WireGuardPeer(BaseModel):
    public_key: str
    endpoint: str | None = None
    allowed_ips: list[str] = []
    preshared_key: str | None = None
    persistent_keepalive: int | None = None


class WireGuardConfig(BaseModel):
    addresses: list[str] = []
    dns: list[str] = []
    mtu: int | None = None
    listen_port: int | None = None
    peers: list[WireGuardPeer] = []
    split_routes: list[str] = []


class FortiGateIpsecConfig(BaseModel):
    host: str
    username: str
    dns_servers: list[str] = []
    routes: list[str] = []


class OpenVpnConfig(BaseModel):
    config_file: str | None = None  # path or inline content
    config_content: str | None = None
    username: str | None = None


class AzureVpnConfig(BaseModel):
    gateway_fqdn: str
    tenant_id: str
    client_id: str
    server_secret_hex: str  # tls-crypt key
    ca_cert_pem: str
    routes: list[str] = []
    dns_servers: list[str] = []


class VpnProfile(SQLModel, table=True):
    __tablename__ = "vpn_profiles"

    id: str = SQLField(primary_key=True)
    name: str
    description: str = ""
    protocol: VpnProtocol
    config: dict = SQLField(sa_column=Column(JSON))  # JSON blob — parsed by backend
    full_tunnel: bool = False
    auto_connect: bool = False
    kill_switch: bool = False
    customer_id: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str | None = SQLField(default=None, foreign_key="users.id")


class TunnelStats(BaseModel):
    bytes_sent: int = 0
    bytes_received: int = 0
    last_handshake: str | None = None
    connected_since: str | None = None
    interface: str | None = None


# Request schemas


class ProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    protocol: VpnProtocol
    config: dict
    description: str = ""
    full_tunnel: bool = False
    customer_id: str | None = None


class ProfileImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    file_content: str  # .conf, .ovpn, or Azure XML content
    file_type: str = "auto"  # "wireguard", "openvpn", "azure", "auto"


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict | None = None
    full_tunnel: bool | None = None
    auto_connect: bool | None = None
    kill_switch: bool | None = None
    customer_id: str | None = None


class VpnProfileRef(BaseModel):
    """A profile id on its own, for the Azure sign-in steps.

    Empty is not refused here: it finds no profile, and the handler's 404 is
    the answer it has always had.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str = ""


class VpnDisconnectRequest(BaseModel):
    """Which tunnel to stop; no id means the caller's active one."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str | None = None


class AzurePkceComplete(BaseModel):
    """The redirect URL the operator pasted back, carrying code and state."""

    model_config = ConfigDict(extra="forbid")

    callback_url: str = ""


class AzureConnectWithToken(BaseModel):
    """Open an Azure tunnel with a token from the PKCE or device-code flow.

    A missing token keeps the handler's own message.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str = ""
    access_token: str = ""
