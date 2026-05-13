"""VPN data models — ported from SuperManager supermgr-core/src/vpn/."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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
    endpoint: Optional[str] = None
    allowed_ips: list[str] = []
    preshared_key: Optional[str] = None
    persistent_keepalive: Optional[int] = None


class WireGuardConfig(BaseModel):
    addresses: list[str] = []
    dns: list[str] = []
    mtu: Optional[int] = None
    listen_port: Optional[int] = None
    peers: list[WireGuardPeer] = []
    split_routes: list[str] = []


class FortiGateIpsecConfig(BaseModel):
    host: str
    username: str
    dns_servers: list[str] = []
    routes: list[str] = []


class OpenVpnConfig(BaseModel):
    config_file: Optional[str] = None  # path or inline content
    config_content: Optional[str] = None
    username: Optional[str] = None


class AzureVpnConfig(BaseModel):
    gateway_fqdn: str
    tenant_id: str
    client_id: str
    server_secret_hex: str  # tls-crypt key
    ca_cert_pem: str
    routes: list[str] = []
    dns_servers: list[str] = []


class VpnProfile(BaseModel):
    id: str
    name: str
    description: str = ""
    protocol: VpnProtocol
    config: dict  # JSON blob — parsed by backend
    full_tunnel: bool = False
    auto_connect: bool = False
    kill_switch: bool = False
    customer_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None


class TunnelStats(BaseModel):
    bytes_sent: int = 0
    bytes_received: int = 0
    last_handshake: Optional[str] = None
    connected_since: Optional[str] = None
    interface: Optional[str] = None


# Request schemas


class ProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    protocol: VpnProtocol
    config: dict
    description: str = ""
    full_tunnel: bool = False
    customer_id: Optional[str] = None


class ProfileImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    file_content: str  # .conf, .ovpn, or Azure XML content
    file_type: str = "auto"  # "wireguard", "openvpn", "azure", "auto"


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    full_tunnel: Optional[bool] = None
    auto_connect: Optional[bool] = None
    kill_switch: Optional[bool] = None
    customer_id: Optional[str] = None
