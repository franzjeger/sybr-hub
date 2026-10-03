"""Request models for the Tailscale endpoints.

Defaults are the handlers' old ones. A body that failed to parse used to land
in the handlers' blanket ``except Exception`` and come back as a 502
"integration error", as if Tailscale had refused it; now it is a 422 before
any call to Tailscale is made.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlmodel import Field, SQLModel


class TailscaleTags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: list[str] = []


class TailscaleAuthorize(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorized: bool = True


class TailscaleRename(BaseModel):
    """A device's new name. Empty keeps the handler's message."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""


class TailscaleKeyExpiry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disabled: bool = False


class TailscaleRoutes(BaseModel):
    """The full set of subnet routes to enable on a device."""

    model_config = ConfigDict(extra="forbid")

    routes: list[str] = []


class TailscaleKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reusable: bool = False
    ephemeral: bool = False
    preauthorized: bool = True
    tags: list[str] = []
    expiry_seconds: int = 86400
    description: str = ""


class TailscaleTest(BaseModel):
    """An API key to try before saving; the mask means "the stored one"."""

    model_config = ConfigDict(extra="forbid")

    api_key: str = ""
    tailnet: str = "-"


class TailscaleNodeCustomer(SQLModel, table=True):
    """A Tailscale node a technician assigned to a customer by hand."""

    __tablename__ = "tailscale_node_customers"

    device_id: str = Field(primary_key=True)
    customer_id: str
    assigned_by: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    assigned_at: str


class TailscaleNodeAssign(BaseModel):
    """The customer a node belongs to; null removes the manual assignment."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str | None = None
