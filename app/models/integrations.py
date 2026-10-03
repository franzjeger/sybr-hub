"""Integration records (ALSO, GDAP, Uniweb) and the request bodies of the
integration routes (GDAP, IT Glue, ALSO, Uniweb, Autotask, myITprocess)."""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict
from sqlalchemy import UniqueConstraint, text
from sqlmodel import Field, SQLModel


class AlsoRenewal(SQLModel, table=True):
    __tablename__ = "also_renewals"
    __table_args__ = (UniqueConstraint("customer_id", "subscription_id"),)

    id: int | None = Field(default=None, primary_key=True)
    customer_id: str
    customer_name: str
    subscription_id: str
    service_name: str
    service_display: str
    vendor: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    contract_id: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    contract_end: str | None = Field(default=None)
    billing_start: str | None = Field(default=None)
    account_state: str = Field(
        default="Active", sa_column_kwargs={"server_default": text("'Active'")}
    )
    handled: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    notes: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    scanned_at: str


class AlsoSubscriptionDetail(SQLModel, table=True):
    __tablename__ = "also_subscription_details"

    subscription_id: str = Field(primary_key=True)
    customer_id: str
    quantity: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    unit_price: float = Field(default=0.0, sa_column_kwargs={"server_default": text("0.0")})
    monthly_cost: float = Field(default=0.0, sa_column_kwargs={"server_default": text("0.0")})
    currency: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    fields_json: str = Field(default="[]", sa_column_kwargs={"server_default": text("'[]'")})
    priceable_items_json: str = Field(
        default="[]", sa_column_kwargs={"server_default": text("'[]'")}
    )
    cached_at: str


class UniwebAccount(SQLModel, table=True):
    __tablename__ = "uniweb_accounts"

    id: str = Field(primary_key=True)
    name: str
    customer_id: str | None = Field(default=None)
    last_sync: str | None = Field(default=None)
    data_json: str | None = Field(default=None)


class GdapCustomer(SQLModel, table=True):
    __tablename__ = "gdap_customers"

    tenant_id: str = Field(primary_key=True)
    company_name: str
    domain: str
    gdap_status: str = Field(
        default="active", sa_column_kwargs={"server_default": text("'active'")}
    )
    last_synced: str
    imported: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    local_customer_id: str | None = Field(default=None)


# ── Request bodies: GDAP / Partner Center ────────────────────────────────────


class GdapSetupRequest(BaseModel):
    """Partner Center credentials. An empty secret keeps the stored one.

    Null and absent both mean empty, as ``(body.get(k) or "")`` did; the
    handler has the messages for what is required.
    """

    model_config = ConfigDict(extra="forbid")

    partner_tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    # Stored with the config; the integrations card does not send it.
    app_display_name: str = "MSP Toolkit GDAP"


class GdapImportRequest(BaseModel):
    """Which GDAP tenants to import, and optionally which local customer each
    one is (``{tenant_id: customer_id}``, the discovery endpoint's proposals
    accepted). An empty list keeps the handler's message."""

    model_config = ConfigDict(extra="forbid")

    tenant_ids: list[str] = []
    links: dict[str, str] | None = None


# ── Request bodies: IT Glue ──────────────────────────────────────────────────

# An IT Glue organisation id as the pickers send it: the radio button's value
# (text) or the id from the organisation list (which may be a number).
_OrgId = Union[int, str, None]


class ITGlueTestRequest(BaseModel):
    """A key and region to try; no key means "the stored settings"."""

    model_config = ConfigDict(extra="forbid")

    api_key: str = ""
    region: str = "eu"


class ITGlueOrgRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    id: Union[int, str] = ""


class ITGlueImportRequest(BaseModel):
    """IT Glue organisations to create as customers. Empty keeps its message."""

    model_config = ConfigDict(extra="forbid")

    organizations: list[ITGlueOrgRef] = []


class ITGlueUploadRequest(BaseModel):
    """Whose data to upload, and the organisation to upload it into.

    A missing organisation keeps its message. The customer is required: the
    upload carries that customer's audit or credentials, and it was "the
    active customer's", which another tab of the same account could change.
    """

    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(min_length=1)
    org_id: _OrgId = None


class ITGlueReportUpload(ITGlueUploadRequest):
    """…and which of the selected audit's report files to send."""

    files: list[str] = []


# ── Request bodies: ALSO Cloud Marketplace ───────────────────────────────────


class AlsoTestRequest(BaseModel):
    """An ALSO login to try; the mask means "the stored password"."""

    model_config = ConfigDict(extra="forbid")

    username: str = ""
    password: str = ""
    country: str = "no"


class AlsoScanBatch(BaseModel):
    """How much of a renewal or price scan to do per call.

    Optional; the handlers clamp both values (a batch ceiling, a minimum
    delay) and their defaults differ per scan, so ``None`` means "use the
    route's default".
    """

    model_config = ConfigDict(extra="forbid")

    batch_size: int | None = None
    delay: float | None = None


class AlsoRenewalHandled(BaseModel):
    """Mark a renewal handled (1) or not (0), with an optional note."""

    model_config = ConfigDict(extra="forbid")

    handled: int = 1
    notes: str = ""


class AlsoLinkPair(BaseModel):
    """A local customer and the ALSO account it is. ALSO account ids may be numbers."""

    model_config = ConfigDict(extra="forbid")

    toolkit_id: str | None = None
    also_id: Union[int, str, None] = None


class AlsoLinkMatched(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matches: list[AlsoLinkPair] = []


class AlsoImportCompany(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    domain: str = ""
    also_id: str = ""


class AlsoSyncCustomers(BaseModel):
    """ALSO companies to create as customers. Empty keeps the handler's message."""

    model_config = ConfigDict(extra="forbid")

    customers: list[AlsoImportCompany] = []


# ── Request bodies: Uniweb ───────────────────────────────────────────────────


class UniwebMatchRequest(BaseModel):
    """Bind a Uniweb account to a customer; an empty customer id unbinds it."""

    model_config = ConfigDict(extra="forbid")

    uniweb_account_id: str = ""
    customer_id: str = ""


class UniwebImportRequest(BaseModel):
    """Unmatched Uniweb accounts to create as customers."""

    model_config = ConfigDict(extra="forbid")

    account_ids: list[str] = []


class UniwebSettingsRequest(BaseModel):
    """Uniweb credentials; the mask as password keeps the stored one."""

    model_config = ConfigDict(extra="forbid")

    email: str = ""
    password: str = ""


# ── Request bodies: PSA connection tests ─────────────────────────────────────


class AutotaskTestRequest(BaseModel):
    """Unsaved Autotask credentials to try. All three, or the stored ones are used.

    The body is optional: the settings card saves first and posts ``{}``.
    """

    model_config = ConfigDict(extra="forbid")

    integration_code: str | None = None
    username: str | None = None
    secret: str | None = None


class MyITProcessTestRequest(BaseModel):
    """An unsaved myITprocess key to try; without one the stored key is used."""

    model_config = ConfigDict(extra="forbid")

    api_key: str | None = None
    base_url: str = ""
