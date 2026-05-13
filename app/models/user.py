"""User and authentication models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Role(str, Enum):
    """User roles with ascending privilege level."""
    viewer = "viewer"
    technician = "technician"
    admin = "admin"

    @property
    def level(self) -> int:
        return {"viewer": 0, "technician": 1, "admin": 2}[self.value]

    def __ge__(self, other: "Role") -> bool:
        return self.level >= other.level

    def __gt__(self, other: "Role") -> bool:
        return self.level > other.level

    def __le__(self, other: "Role") -> bool:
        return self.level <= other.level

    def __lt__(self, other: "Role") -> bool:
        return self.level < other.level


class User(BaseModel):
    """Stored user record."""
    id: str
    username: str
    display_name: str
    email: Optional[str] = None
    role: Role = Role.viewer
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True


class TokenPayload(BaseModel):
    """JWT access token payload."""
    sub: str          # user_id
    username: str
    role: Role
    exp: datetime
    iat: datetime
    token_type: str = "access"
    session_id: Optional[str] = None


# ── Request / Response schemas ───────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=8, max_length=256)
    display_name: str = Field(..., min_length=1, max_length=128)
    email: Optional[str] = None
    role: Role = Role.technician


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=256)


class SetupRequest(BaseModel):
    """First-run admin account creation."""
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=8, max_length=256)
    display_name: str = Field(..., min_length=1, max_length=128)
    email: Optional[str] = None
