"""SSH host and key data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import JSON, Column
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel

from app.core.validation import validate_display_text, validate_host, validate_login_name


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


class SshKey(SQLModel, table=True):
    __tablename__ = "ssh_keys"
    id: str = SQLField(primary_key=True)
    name: str
    description: str = ""
    key_type: SshKeyType
    public_key: str  # OpenSSH format
    fingerprint: str  # SHA256:<base64>
    tags: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    created_at: datetime
    updated_at: datetime
    created_by: str | None = SQLField(default=None, foreign_key="users.id")
    # None is an MSP-wide key: only callers with access to every customer may
    # see it or attach it to a host.
    customer_id: str | None = None


class SshHost(SQLModel, table=True):
    __tablename__ = "ssh_hosts"
    id: str = SQLField(primary_key=True)
    label: str
    hostname: str
    port: int = 22
    username: str
    group_name: str = ""
    device_type: DeviceType = DeviceType.linux
    auth_method: AuthMethod = AuthMethod.key
    auth_key_id: str | None = None
    customer_id: str | None = None
    tags: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    notes: str = ""
    last_seen: datetime | None = None
    is_reachable: bool | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str | None = SQLField(default=None, foreign_key="users.id")


class SshKeyDeployment(SQLModel, table=True):
    __tablename__ = "ssh_key_deployments"
    key_id: str = SQLField(primary_key=True, foreign_key="ssh_keys.id", ondelete="CASCADE")
    host_id: str = SQLField(primary_key=True, foreign_key="ssh_hosts.id", ondelete="CASCADE")
    deployed_at: datetime
    deployed_by: str | None = SQLField(default=None, foreign_key="users.id")


class SshAuditEntry(SQLModel, table=True):
    __tablename__ = "ssh_audit_log"
    id: int = SQLField(default=None, primary_key=True)
    timestamp: datetime
    action: str
    key_name: str | None = None
    key_fingerprint: str | None = None
    host_label: str | None = None
    hostname: str | None = None
    port: int | None = None
    success: bool
    user_id: str | None = None
    detail: str = ""


# ── Request schemas ──────────────────────────────────────────────────────────


class KeyGenerateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    key_type: SshKeyType = SshKeyType.ed25519
    description: str = ""
    tags: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    customer_id: str | None = None


class KeyImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    private_key_pem: str
    description: str = ""
    tags: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    customer_id: str | None = None


class _HostFieldRules(BaseModel):
    """Validation shared by host create and update.

    These values are written into a generated SSH config, xfreerdp arguments
    and a .rdp file, so a control character in any of them is a new directive
    rather than odd-looking text. The validators raise the app's
    ValidationError, which reaches the client as a 400 with the message.
    """

    @field_validator("hostname", check_fields=False)
    @classmethod
    def _valid_hostname(cls, v: str | None) -> str | None:
        return None if v is None else validate_host(v.strip(), "hostname")

    @field_validator("username", check_fields=False)
    @classmethod
    def _valid_username(cls, v: str | None) -> str | None:
        return None if v is None else validate_login_name(v.strip(), "username")

    @field_validator("label", "group_name", check_fields=False)
    @classmethod
    def _valid_short_text(cls, v: str | None, info) -> str | None:
        return None if v is None else validate_display_text(v, info.field_name, max_length=128)

    @field_validator("notes", check_fields=False)
    @classmethod
    def _valid_notes(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_display_text(v, "notes", max_length=4000, multiline=True)

    @field_validator("tags", check_fields=False)
    @classmethod
    def _valid_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [validate_display_text(t, "tags", max_length=64) for t in v]


class HostCreateRequest(_HostFieldRules):
    label: str = Field(..., min_length=1, max_length=128)
    hostname: str = Field(..., min_length=1)
    port: int = Field(22, ge=1, le=65535)
    username: str = Field(..., min_length=1)
    password: str | None = None
    group_name: str = ""
    device_type: DeviceType = DeviceType.linux
    auth_method: AuthMethod = AuthMethod.key
    auth_key_id: str | None = None
    customer_id: str | None = None
    tags: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    notes: str = ""


class HostUpdateRequest(_HostFieldRules):
    label: str | None = Field(None, min_length=1, max_length=128)
    hostname: str | None = None
    port: int | None = Field(None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    group_name: str | None = None
    device_type: DeviceType | None = None
    auth_method: AuthMethod | None = None
    auth_key_id: str | None = None
    customer_id: str | None = None
    tags: list[str] | None = None
    notes: str | None = None


class KeyPushRequest(BaseModel):
    host_ids: list[str]
    use_sudo: bool = False


class BatchExecRequest(BaseModel):
    host_ids: list[str]
    command: str = Field(..., min_length=1)


class HostSelection(BaseModel):
    """Which hosts a health check or a generated SSH config covers.

    Absent, null or empty means "every host the caller may see" — the handler
    decides that scope, never the whole box.
    """

    model_config = ConfigDict(extra="forbid")

    host_ids: list[str] | None = None


class RdpLaunchRequest(BaseModel):
    """Start a local RDP client against a registered host.

    The hostname always comes from the registered host. The old client also
    sent ``host``; it is accepted so that body still parses and is never read,
    which is the point — a caller-supplied address would let this route start
    a client against anything. Missing ``host_id``, and a port or domain the
    handler rejects, keep the handler's own messages.
    """

    model_config = ConfigDict(extra="forbid")

    host_id: str | None = None
    host: str | None = None
    username: str | None = None
    port: int = 3389
    domain: str | None = None
    password: str | None = None


class ExecResult(BaseModel):
    host_id: str = SQLField(primary_key=True, foreign_key="ssh_hosts.id", ondelete="CASCADE")
    host_label: str
    hostname: str
    exit_code: int
    stdout: str
    stderr: str
    error: str | None = None
