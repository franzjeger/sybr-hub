from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UnifiedM365(BaseModel):
    TenantId: str | None = None
    ClientId: str | None = None
    PrimaryDomain: str | None = None
    secret_days_left: int | None = None
    secret_status: str | None = None
    cert_days_left: int | None = None
    cert_status: str | None = None


class UnifiedFortiGate(BaseModel):
    FortiGateHost: str | None = None
    FortiGatePort: int | None = None
    FortiGateVdom: str | None = None


class UnifiedUniFi(BaseModel):
    UniFiHost: str | None = None
    UniFiMode: str | None = None
    UniFiSite: str | None = None
    UniFiIsUniFiOS: bool | None = None


class UnifiedAlsoSubscription(BaseModel):
    subscription_id: str
    product_name: str
    quantity: int | None = None
    monthly_cost: float | None = None
    currency: str | None = None
    days_left: int | None = None
    contract_end: str | None = None


class UnifiedAlso(BaseModel):
    total_subscriptions: int
    expiring_90d: int
    expired: int
    mrr: float
    currency: str
    renewals: list[UnifiedAlsoSubscription]


class UnifiedAudit(BaseModel):
    risk_grade: str | None = None
    risk_score: float | None = None
    secure_score_pct: float | None = None
    mfa_coverage_pct: float | None = None
    total_users: int | None = None
    users_no_mfa: int | None = None
    admin_roles_ga_count: int | None = None
    audit_date: datetime | None = None


class UnifiedCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    customer_name: str
    domain: str
    source: str
    tags: list[str]
    also_account_id: str | None = None

    m365: UnifiedM365 | None = None
    fortigate: UnifiedFortiGate | None = None
    unifi: UnifiedUniFi | None = None
    also: UnifiedAlso | None = None
    ssh_hosts: list[dict] | None = None
    tailscale: dict | None = None
    audit: UnifiedAudit | None = None
    unavailable: dict[str, str]
