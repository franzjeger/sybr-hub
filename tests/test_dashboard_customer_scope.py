"""Cross-customer dashboards must only aggregate rows the caller may see.

Several dashboard routes computed the caller's accessible customers and then
used that set only to look up names, while iterating every ALSO, Uniweb, SSH
or VPN row in the database. A viewer scoped to one customer read every other
customer's monthly revenue (/dashboard/costs), domains (/dashboard/domains,
/dashboard/assets), mail-hosting overlaps (/dashboard/domain-email-chain) and
expiring renewals (/dashboard/alerts). Rows with no owning customer (an
unlinked Uniweb account, an unassigned SSH host) are MSP-wide and are only for
unrestricted callers.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.core.orm import get_session
from app.models.audit import AuditMetric, HealthSnapshot
from app.models.integrations import AlsoRenewal, AlsoSubscriptionDetail, UniwebAccount
from app.models.ssh import SshHost
from app.models.user import Role
from app.models.vpn import VpnProfile, VpnProtocol
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    BETA,
    _reset_middleware_state,
    _scope_env,
    assert_no_foreign,
    client,
    login,
)


def _uniweb_data(domain: str, price: str) -> str:
    """A synced Uniweb account: one Exchange-routed domain also hosted for mail."""
    return json.dumps(
        {
            "domains": [
                {
                    "domain": domain,
                    "dns": [
                        {
                            "type": "MX",
                            "hostname": "@",
                            "value": f"{domain.replace('.', '-')}.mail.protection.outlook.com",
                        }
                    ],
                }
            ],
            "email": [{"domain": domain}],
            "subscriptions": [{"Price per month": price}],
        }
    )


@pytest.fixture(autouse=True)
async def _seed():
    now = datetime.now(UTC)
    stamp = now.isoformat()
    async with get_session() as s:
        for cid, name, sub, cost in (
            (ACME, "Acme AS", "subA", 100.0),
            (BETA, "Beta AS", "subB", 999.0),
        ):
            # Expired, so it is alert-worthy on /dashboard/alerts.
            s.add(
                AlsoRenewal(
                    customer_id=cid,
                    customer_name=name,
                    subscription_id=sub,
                    service_name="M365",
                    service_display="Microsoft 365 Business Premium",
                    vendor="Microsoft",
                    contract_end="2020-01-01T00:00:00Z",
                    scanned_at=stamp,
                )
            )
            s.add(
                AlsoSubscriptionDetail(
                    subscription_id=sub,
                    customer_id=cid,
                    quantity=1,
                    monthly_cost=cost,
                    currency="NOK",
                    cached_at=stamp,
                )
            )
            s.add(
                AuditMetric(
                    customer_id=cid,
                    customer_name=name,
                    audit_date=stamp[:10],
                    risk_grade="C",
                    risk_score=50,
                    mfa_coverage_pct=80,
                    metrics_json=json.dumps({"compliance": {"pass": 1, "total": 2, "pct": 50}}),
                    created_at=stamp,
                )
            )
            s.add(HealthSnapshot(customer_id=cid, snapshot_date=stamp[:10], risk_score=50))
        s.add(
            UniwebAccount(
                id="uw-acme",
                name="Acme Web",
                customer_id=ACME,
                data_json=_uniweb_data("acme-web.example", "50"),
            )
        )
        s.add(
            UniwebAccount(
                id="uw-beta",
                name="Beta Web",
                customer_id=BETA,
                data_json=_uniweb_data("beta-web.example", "777"),
            )
        )
        s.add(
            UniwebAccount(
                id="uw-orphan",
                name="Orphan Web",
                customer_id=None,
                data_json=_uniweb_data("orphan-web.example", "5"),
            )
        )
        for hid, cid in (("h-acme", ACME), ("h-beta", BETA), ("h-none", None)):
            s.add(
                SshHost(
                    id=hid,
                    label=hid,
                    hostname=f"{hid}.example",
                    username="root",
                    customer_id=cid,
                    created_at=now,
                    updated_at=now,
                )
            )
        for vid, cid in (("v-acme", ACME), ("v-beta", BETA), ("v-none", None)):
            s.add(
                VpnProfile(
                    id=vid,
                    name=vid,
                    protocol=VpnProtocol.wireguard,
                    config={},
                    customer_id=cid,
                    created_at=now,
                    updated_at=now,
                )
            )
        await s.commit()
    yield


@pytest.fixture(autouse=True)
def probed(monkeypatch) -> list[str]:
    """Stub the live TLS/DNS probes and record which hosts were asked about."""
    seen: list[str] = []

    async def _tls(host, port=443, timeout=4.0):
        seen.append(host)
        return {"valid": False, "error": "not probed in tests"}

    def _dns(domain, records=None):
        seen.append(domain)
        return None

    async def _no_fortigates():
        return []

    monkeypatch.setattr("app.services.tls_monitor.check_endpoint_tls", _tls)
    monkeypatch.setattr("app.services.dns_checker.check_domain", _dns)
    monkeypatch.setattr("app.services.fortigate_api.poll_all_fortigates", _no_fortigates)
    return seen


async def _scoped():
    return await login("viewer-acme", role=Role.viewer, customers=(ACME,), write=False)


# ── /dashboard/costs ─────────────────────────────────────────────────────────


async def test_costs_only_total_the_callers_customers(client):
    r = client.get("/api/dashboard/costs", headers=await _scoped())
    assert r.status_code == 200, r.text
    body = r.json()
    assert {c["customer_id"] for c in body["customers"]} == {ACME}
    assert body["totals"]["also_mrr"] == 100.0
    assert body["totals"]["uniweb_monthly"] == 50.0
    assert_no_foreign(r.text)


async def test_costs_for_an_admin_cover_every_customer(client):
    headers = await login("boss", role=Role.admin)
    body = client.get("/api/dashboard/costs", headers=headers).json()
    assert {c["customer_id"] for c in body["customers"]} == {ACME, BETA}


# ── /dashboard/domains ───────────────────────────────────────────────────────


async def test_domains_list_only_the_callers_domains(client, probed):
    r = client.get("/api/dashboard/domains", headers=await _scoped())
    assert r.status_code == 200, r.text
    domains = {d["domain"] for d in r.json()["domains"]}
    assert domains == {"acme-web.example", "acme.example"}
    assert_no_foreign(r.text)
    # Nor does the hub probe a domain on the caller's behalf that it then hides.
    assert not [h for h in probed if "beta" in h or "orphan" in h]


async def test_unlinked_uniweb_domains_are_for_unrestricted_callers(client):
    headers = await login("wide", all_customers=True)
    domains = {
        d["domain"] for d in client.get("/api/dashboard/domains", headers=headers).json()["domains"]
    }
    assert {"acme-web.example", "beta-web.example", "orphan-web.example"} <= domains


# ── /dashboard/domain-email-chain ────────────────────────────────────────────


async def test_domain_email_chain_only_reports_the_callers_domains(client):
    r = client.get("/api/dashboard/domain-email-chain", headers=await _scoped())
    assert r.status_code == 200, r.text
    assert {i["customer_id"] for i in r.json()["items"]} == {ACME}
    assert_no_foreign(r.text)


async def test_domain_email_chain_for_an_admin_reports_both(client):
    headers = await login("boss", role=Role.admin)
    items = client.get("/api/dashboard/domain-email-chain", headers=headers).json()["items"]
    assert {i["customer_id"] for i in items} == {ACME, BETA}


# ── /dashboard/assets ────────────────────────────────────────────────────────


async def test_assets_hide_foreign_and_unassigned_rows_from_a_scoped_caller(client):
    r = client.get("/api/dashboard/assets", headers=await _scoped())
    assert r.status_code == 200, r.text
    assets = r.json()["assets"]
    assert {h["id"] for h in assets["ssh_hosts"]} == {"h-acme"}
    assert {p["id"] for p in assets["vpn_profiles"]} == {"v-acme"}
    assert {d["domain"] for d in assets["domains"]} == {"acme-web.example"}
    assert {s["customer_id"] for s in assets["subscriptions"]} == {ACME}
    assert_no_foreign(r.text)


async def test_assets_show_unassigned_rows_to_an_admin(client):
    headers = await login("boss", role=Role.admin)
    assets = client.get("/api/dashboard/assets", headers=headers).json()["assets"]
    assert {h["id"] for h in assets["ssh_hosts"]} == {"h-acme", "h-beta", "h-none"}
    assert {p["id"] for p in assets["vpn_profiles"]} == {"v-acme", "v-beta", "v-none"}


# ── /dashboard/alerts ────────────────────────────────────────────────────────


async def test_alerts_only_list_the_callers_renewals(client):
    r = client.get("/api/dashboard/alerts", headers=await _scoped())
    assert r.status_code == 200, r.text
    assert {i["customer_id"] for i in r.json()["renewals"]} == {ACME}
    assert_no_foreign(r.text)


async def test_alerts_for_an_admin_list_every_renewal(client):
    headers = await login("boss", role=Role.admin)
    renewals = client.get("/api/dashboard/alerts", headers=headers).json()["renewals"]
    assert {i["customer_id"] for i in renewals} == {ACME, BETA}


# ── Per-customer views that were already filtered stay filtered ─────────────

ALREADY_SCOPED = [
    "/api/dashboard/health",
    "/api/dashboard/health-scores",
    "/api/dashboard/compliance",
    "/api/dashboard/overview",
    "/api/dashboard/trends",
    "/api/search/customers",
    "/api/dashboard/network-inventory",
]


@pytest.mark.parametrize("path", ALREADY_SCOPED)
async def test_per_customer_views_never_mention_a_foreign_customer(client, path):
    r = client.get(path, headers=await _scoped())
    assert r.status_code == 200, r.text
    assert_no_foreign(r.text)
