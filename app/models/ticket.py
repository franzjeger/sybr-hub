"""Ticket and remediation data models, and the remediation request body."""

from pydantic import BaseModel, ConfigDict
from sqlalchemy import CheckConstraint, UniqueConstraint, text
from sqlmodel import Field, SQLModel


class FindingTicket(SQLModel, table=True):
    __tablename__ = "finding_tickets"
    __table_args__ = (UniqueConstraint("customer_id", "rec_id", "system"),)

    id: int | None = Field(default=None, primary_key=True)
    customer_id: str
    rec_id: str
    system: str
    external_id: str
    external_url: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    title: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    created_at: str
    created_by: str = Field(default="", sa_column_kwargs={"server_default": text("''")})


class FindingOperation(SQLModel, table=True):
    __tablename__ = "finding_operations"
    __table_args__ = (
        UniqueConstraint("customer_id", "rec_id", "system"),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'unknown')", name="ck_finding_operations_status"
        ),
    )

    operation_id: str = Field(primary_key=True)
    customer_id: str
    rec_id: str
    system: str
    status: str
    created_at: str
    created_by: str


class RemediationItem(SQLModel, table=True):
    __tablename__ = "remediation_items"
    __table_args__ = (UniqueConstraint("customer_id", "recommendation_id"),)

    id: int | None = Field(default=None, primary_key=True)
    customer_id: str
    recommendation_id: str
    status: str = Field(default="open", sa_column_kwargs={"server_default": text("'open'")})
    notes: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    assigned_to: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    created_at: str
    updated_at: str


class RemediationUpdate(BaseModel):
    """A status change on one recommendation of the customer named in the path.

    ``rec_id`` is the stable identity. ``title`` is still accepted in its place
    for a client that has not reloaded since that changed, and for rows written
    before recommendations had ids. ``status`` stays free text here so an
    unknown one keeps the handler's translated message.
    """

    model_config = ConfigDict(extra="forbid")

    rec_id: str | None = None
    title: str | None = None
    status: str = "open"
    notes: str = ""
