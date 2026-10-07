"""Audit and Health models, and the request bodies of the audit routes."""

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from sqlmodel import Field, SQLModel


class AuditMetric(SQLModel, table=True):
    __tablename__ = "audit_metrics"

    id: int | None = Field(default=None, primary_key=True)
    customer_id: str
    customer_name: str
    audit_date: str
    risk_grade: str | None = None
    risk_score: float | None = None
    mfa_coverage_pct: float | None = None
    secure_score_pct: float | None = None
    total_users: int | None = None
    users_no_mfa: int | None = None
    ca_policies_enabled: int | None = None
    intune_compliance_pct: float | None = None
    admin_roles_ga_count: int | None = None
    metrics_json: str | None = None
    created_at: str


class HealthSnapshot(SQLModel, table=True):
    __tablename__ = "health_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    customer_id: str
    snapshot_date: str
    risk_score: float | None = None
    risk_grade: str | None = None
    mfa_pct: float | None = None
    secure_score_pct: float | None = None
    health_score: float | None = None
    health_grade: str | None = None
    total_users: int | None = None
    total_warns: int | None = None


# ── Request bodies ───────────────────────────────────────────────────────────


class AuditScope(BaseModel):
    """Which audit sections run for the customer named in the query.

    Stored as sent (``exclude_unset``): the page reads a stored list, even an
    empty one, as the operator's choice, and an absent one as "no choice yet".
    """

    model_config = ConfigDict(extra="forbid")

    enabled_sections: list[str] = []


class AuditPreset(BaseModel):
    """A named set of sections. A missing name keeps the handler's message."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    sections: list[str] = []


class PkceManualCallback(BaseModel):
    """The code and state from a sign-in redirect the operator pasted back."""

    model_config = ConfigDict(extra="forbid")

    code: str | None = None
    state: str | None = None
    renew_customer_id: str | None = PydanticField(default=None, min_length=1, max_length=255)


class HistoryLoad(BaseModel):
    """A previous audit run of one customer, by its directory, to build reports from.

    The customer is named rather than worked out from the folder: two
    customers can share a folder name, and the run is selected for the page
    that asked, not for whichever customer the account looked at last.
    """

    model_config = ConfigDict(extra="forbid")

    customer_id: str = PydanticField(min_length=1)
    path: str = ""


class HistoryDelete(BaseModel):
    """Audit run directories to delete. An empty list keeps the handler's message."""

    model_config = ConfigDict(extra="forbid")

    paths: list[str] = []


class HistoryDeleteCustomer(BaseModel):
    """A customer's audit directory name, to delete every run in it."""

    model_config = ConfigDict(extra="forbid")

    customer_dir: str = ""
