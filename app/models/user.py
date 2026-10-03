"""User and authentication models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Field, SQLModel


class Role(str, Enum):
    """User roles with ascending privilege level."""

    viewer = "viewer"
    technician = "technician"
    admin = "admin"

    @property
    def level(self) -> int:
        return {"viewer": 0, "technician": 1, "admin": 2}[self.value]

    def __ge__(self, other: Role) -> bool:
        return self.level >= other.level

    def __gt__(self, other: Role) -> bool:
        return self.level > other.level

    def __le__(self, other: Role) -> bool:
        return self.level <= other.level

    def __lt__(self, other: Role) -> bool:
        return self.level < other.level


class User(SQLModel, table=True):
    """Stored user record."""

    __tablename__ = "users"

    id: str = Field(primary_key=True)
    username: str = Field(unique=True)
    display_name: str
    email: str | None = None
    password_hash: str = Field(exclude=True)  # Added password_hash
    role: Role = Field(default=Role.viewer)
    created_at: datetime
    last_login: datetime | None = None
    is_active: bool = Field(default=True)
    # Blanket grant to every customer, independent of customer_access rows.
    # Defaults to False so a user built without it is scoped, not unrestricted.
    all_customers: bool = Field(default=False)
    # May push configuration into a customer's Microsoft tenant.
    #
    # Not part of Role, on purpose. Administering Sybr HUB and changing
    # settings inside somebody else's tenant are different powers: the first
    # is about this tool, the second reaches a customer's production. Rolling
    # them together would hand the second to every admin the day it shipped.
    #
    # Read stays the default for every account. This is the exception, granted
    # one user at a time and revocable on its own.
    is_system: bool = Field(default=False)
    can_write: bool = Field(default=False)
    tenant_write: bool = Field(default=False)
    # Sign-in lockout: 5 wrong passwords, then 5 minutes. `failures` is
    # deliberately not reset when the lock expires, so the next attempt
    # locks again immediately rather than handing back another free run
    # of five — the same shape app.core.mfa uses for one-time codes.
    failures: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    locked_until: float = Field(default=0.0, sa_column_kwargs={"server_default": text("0.0")})


class TokenPayload(BaseModel):
    """JWT access token payload."""

    sub: str  # user_id
    username: str
    role: Role
    exp: datetime
    iat: datetime
    token_type: str = "access"
    session_id: str | None = None


# ── Request / Response schemas ───────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)
    otp: str = Field(default="", max_length=32)


class ReauthenticateRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    otp: str = Field(default="", max_length=32)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=8, max_length=256)
    display_name: str = Field(..., min_length=1, max_length=128)
    email: str | None = None
    role: Role = Role.technician
    # Global access is an explicit grant, never a side effect of onboarding.
    all_customers: bool = False


class CustomerAccessUpdate(BaseModel):
    access_mode: Literal["all", "scoped"] = "scoped"
    customer_ids: list[str] = Field(default_factory=list, max_length=10_000)


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    # None means "not sent" — only an explicit true/false changes it.
    can_write: bool | None = None
    tenant_write: bool | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)


class SetupRequest(BaseModel):
    """First-run admin account creation."""

    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=8, max_length=256)
    display_name: str = Field(..., min_length=1, max_length=128)
    email: str | None = None


class UserSession(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="users.id", ondelete="CASCADE")
    refresh_token_hash: str
    created_at: datetime
    expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None


class TokenBlacklist(SQLModel, table=True):
    __tablename__ = "token_blacklist"

    token_hash: str = Field(primary_key=True)
    expires_at: datetime


class AppSecret(SQLModel, table=True):
    __tablename__ = "app_secrets"

    key: str = Field(primary_key=True)
    value: str


class CustomerAccess(SQLModel, table=True):
    __tablename__ = "customer_access"

    user_id: str = Field(primary_key=True, foreign_key="users.id", ondelete="CASCADE")
    customer_id: str = Field(primary_key=True)


class UserMfa(SQLModel, table=True):
    __tablename__ = "user_mfa"

    user_id: str = Field(primary_key=True, foreign_key="users.id", ondelete="CASCADE")
    secret: bytes
    enabled: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    expires_at: float = Field(default=0.0, sa_column_kwargs={"server_default": text("0.0")})
    last_counter: int = Field(default=-1, sa_column_kwargs={"server_default": text("-1")})
    recovery_hashes: str = Field(default="[]", sa_column_kwargs={"server_default": text("'[]'")})
    failures: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    locked_until: float = Field(default=0.0, sa_column_kwargs={"server_default": text("0.0")})


class MfaStepup(SQLModel, table=True):
    __tablename__ = "mfa_stepup"

    session_id: str = Field(primary_key=True, foreign_key="sessions.id", ondelete="CASCADE")
    verified_at: float
