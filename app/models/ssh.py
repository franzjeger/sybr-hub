"""SSH host and key data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DeviceType(str, Enum):
    linux = "linux"
    unifi = "unifi"
    pfsense = "pfsense"
    openwrt = "openwrt"
    fortigate = "fortigate"
    windows = "windows"
    custom = "custom"


class AuthMethod(str, Enum):
    password = "password"
    key = "key"
    certificate = "certificate"


class SshKeyType(str, Enum):
    ed25519 = "ed25519"
    rsa2048 = "rsa2048"
    rsa4096 = "rsa4096"


# ── Stored records ───────────────────────────────────────────────────────────

class SshKey(BaseModel):
    id: str
    name: str
    description: str = ""
    key_type: SshKeyType
    public_key: str           # OpenSSH format
    fingerprint: str          # SHA256:<base64>
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None


class SshHost(BaseModel):
    id: str
    label: str
    hostname: str
    port: int = 22
    username: str
    group_name: str = ""
    device_type: DeviceType = DeviceType.linux
    auth_method: AuthMethod = AuthMethod.key
    auth_key_id: Optional[str] = None
    customer_id: Optional[str] = None
    tags: list[str] = []
    notes: str = ""
    last_seen: Optional[datetime] = None
    is_reachable: Optional[bool] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None


class SshKeyDeployment(BaseModel):
    key_id: str
    host_id: str
    deployed_at: datetime
    deployed_by: Optional[str] = None


class SshAuditEntry(BaseModel):
    id: int
    timestamp: datetime
    action: str
    key_name: Optional[str] = None
    key_fingerprint: Optional[str] = None
    host_label: Optional[str] = None
    hostname: Optional[str] = None
    port: Optional[int] = None
    success: bool
    user_id: Optional[str] = None
    detail: str = ""


# ── Request schemas ──────────────────────────────────────────────────────────

class KeyGenerateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    key_type: SshKeyType = SshKeyType.ed25519
    description: str = ""
    tags: list[str] = []


class KeyImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    private_key_pem: str
    description: str = ""
    tags: list[str] = []


class HostCreateRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=128)
    hostname: str = Field(..., min_length=1)
    port: int = Field(22, ge=1, le=65535)
    username: str = Field(..., min_length=1)
    password: Optional[str] = None
    group_name: str = ""
    device_type: DeviceType = DeviceType.linux
    auth_method: AuthMethod = AuthMethod.key
    auth_key_id: Optional[str] = None
    customer_id: Optional[str] = None
    tags: list[str] = []
    notes: str = ""


class HostUpdateRequest(BaseModel):
    label: Optional[str] = None
    hostname: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    group_name: Optional[str] = None
    device_type: Optional[DeviceType] = None
    auth_method: Optional[AuthMethod] = None
    auth_key_id: Optional[str] = None
    customer_id: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


class KeyPushRequest(BaseModel):
    host_ids: list[str]
    use_sudo: bool = False


class BatchExecRequest(BaseModel):
    host_ids: list[str]
    command: str = Field(..., min_length=1)


class ExecResult(BaseModel):
    host_id: str
    host_label: str
    hostname: str
    exit_code: int
    stdout: str
    stderr: str
    error: Optional[str] = None
