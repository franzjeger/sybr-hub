"""Dashboard overview, search, and unified customer endpoints.

Split from dashboard.py for maintainability.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request

from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
)
from app.core.rbac import check_customer_access, filter_customers, get_accessible_customer_ids
from app.models.responses import UnifiedCustomerResponse
from app.models.user import Role
from app.reports.recommendations import relocalise_recommendations
from app.web.i18n import get_ui_lang, refusal
from app.web.middleware.auth import get_current_user, require_customer_access

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("/dashboard")
async def get_dashboard(request: Request):
    """Return dashboard metrics from the latest audit run."""
    from app.core.config import get_audit_dir
    from app.core.credentials import load_config

    cfg = load_config()
    if not cfg:
        return {"has_data": False}

    customer_name = cfg.get("CustomerName", "Unknown")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in customer_name)
    audit_dir = get_audit_dir()
    customer_dir = audit_dir / safe_name

    if not customer_dir.exists():
        return {"has_data": False}

    runs = sorted([d for d in customer_dir.iterdir() if d.is_dir()], reverse=True)
    for run_dir in runs:
        metrics_path = run_dir / "_audit_metrics.json"
        if metrics_path.exists():
            from app.core.encryption import encrypted_read_json

            metrics = encrypted_read_json(metrics_path)

            prev_metrics = None
            for prev_dir in runs:
                if prev_dir.name < run_dir.name:
                    prev_path = prev_dir / "_audit_metrics.json"
                    if prev_path.exists():
                        prev_metrics = encrypted_read_json(prev_path)
                        break

            return {
                "has_data": True,
                "customer": customer_name,
                "run_date": run_dir.name,
                "metrics": relocalise_recommendations(metrics, get_ui_lang(request)),
                "previous": prev_metrics,
            }

    return {"has_data": False}


@router.get("/dashboard/overview")
async def get_dashboard_overview(user=Depends(get_current_user)):
    """Return all customers with their latest audit metrics for the multi-customer dashboard."""
    from app.core.config import get_audit_dir
    from app.core.credentials import m365_ready
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_read_json

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    active_id = CustomerManager.get_active_id()
    audit_dir = get_audit_dir()

    results = []
    for c in customers:
        name = c.get("CustomerName", "Unknown")
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
        customer_dir = audit_dir / safe_name

        cid = c.get("_id", "")
        entry = {
            "customer_id": cid,
            "customer_name": name,
            "primary_domain": c.get("PrimaryDomain", ""),
            "also_account_id": c.get("AlsoAccountId", ""),
            "is_active": cid == active_id,
            "has_metrics": False,
            "metrics": None,
            "last_audit": None,
            "tags": CustomerManager.get_tags(cid),
            "prev_metrics": None,
            "has_m365": m365_ready(c),
            "has_fortigate": bool(c.get("FortiGateHost")),
            "has_unifi": bool(c.get("UniFiHost") or c.get("UniFiSiteId")),
        }

        if customer_dir.exists():
            runs = sorted([d for d in customer_dir.iterdir() if d.is_dir()], reverse=True)
            metrics_found = 0
            for run_dir in runs:
                metrics_path = run_dir / "_audit_metrics.json"
                if metrics_path.exists():
                    try:
                        m = encrypted_read_json(metrics_path)
                        if metrics_found == 0:
                            entry["has_metrics"] = True
                            entry["metrics"] = m
                            entry["last_audit"] = run_dir.name
                        elif metrics_found == 1:
                            entry["prev_metrics"] = m
                        metrics_found += 1
                    except Exception as e:
                        logger.warning(
                            "Failed to read metrics for %s/%s: %s", name, run_dir.name, e
                        )
                if metrics_found >= 2:
                    break

        results.append(entry)

    # Oversikt leads with who needs attention, worst open finding first: the
    # newest run's findings less those someone has closed, per severity.
    from app.services.remediation import open_finding_counts

    open_counts = await open_finding_counts(
        {
            e["customer_id"]: (e["metrics"] or {}).get("recommendations") or []
            for e in results
            if e["has_metrics"]
        }
    )
    for e in results:
        e["open_findings"] = open_counts.get(e["customer_id"])

    results.sort(
        key=lambda x: (
            0 if x["has_metrics"] else 1,
            x["metrics"].get("risk_score", 0) if x["has_metrics"] else 999,
        )
    )

    return {"customers": results, "active_id": active_id}


# ── Trend Data ────────────────────────────────────────────────────────────────


@router.get("/dashboard/trends")
async def dashboard_trends(user=Depends(get_current_user)):
    """Return historical health score snapshots for sparkline charts."""

    # Every other dashboard endpoint filters on the caller's grants; this one
    # selected the whole health_snapshots table, so the sparklines carried
    # every customer's risk and MFA history to anyone logged in.
    allowed = await get_accessible_customer_ids(user)

    trends: dict[str, list[dict]] = {}
    try:
        from sqlmodel import select

        from app.core.orm import get_session
        from app.models.audit import HealthSnapshot

        async with get_session() as session:
            stmt = select(HealthSnapshot).order_by(HealthSnapshot.snapshot_date.asc())
            result = await session.execute(stmt)
            for row in result.scalars().all():
                cid = row.customer_id
                if allowed is not None and cid not in allowed:
                    continue
                if cid not in trends:
                    trends[cid] = []
                trends[cid].append(
                    {
                        "date": row.snapshot_date,
                        "score": row.risk_score,
                        "mfa": row.mfa_pct,
                        "ss": row.secure_score_pct,
                    }
                )
    except Exception as e:
        logger.warning("Failed to load health trends: %s", e)

    return {"trends": trends}


# ── Search ────────────────────────────────────────────────────────────────────


@router.get("/search/customers")
async def search_customers(
    query: str = Query("", description="Free text search on name/domain"),
    risk_grade: str = Query("", description="Filter by risk grade (A/B/C/D/F)"),
    mfa_below: float = Query(0, description="Filter customers with MFA% below this threshold"),
    secure_score_below: float = Query(
        0, description="Filter customers with Secure Score% below this threshold"
    ),
    user=Depends(get_current_user),
):
    """Server-side search/filter across all customers with their latest metrics."""
    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_read_json

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    active_id = CustomerManager.get_active_id()
    audit_dir = get_audit_dir()

    results = []
    q_lower = query.strip().lower()
    grade_filter = (
        [g.strip().upper() for g in risk_grade.split(",") if g.strip()] if risk_grade else []
    )

    for c in customers:
        name = c.get("CustomerName", "Unknown")
        domain = c.get("PrimaryDomain", "")

        if q_lower and q_lower not in name.lower() and q_lower not in domain.lower():
            continue

        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
        customer_dir = audit_dir / safe_name

        entry = {
            "customer_id": c.get("_id", ""),
            "customer_name": name,
            "primary_domain": domain,
            "is_active": c.get("_id", "") == active_id,
            "has_metrics": False,
            "metrics": None,
            "last_audit": None,
        }

        if customer_dir.exists():
            runs = sorted([d for d in customer_dir.iterdir() if d.is_dir()], reverse=True)
            for run_dir in runs:
                metrics_path = run_dir / "_audit_metrics.json"
                if metrics_path.exists():
                    try:
                        metrics = encrypted_read_json(metrics_path)
                        entry["has_metrics"] = True
                        entry["metrics"] = metrics
                        entry["last_audit"] = run_dir.name
                    except Exception as e:
                        logger.warning(
                            "Failed to read metrics for %s/%s: %s", name, run_dir.name, e
                        )
                    break

        m = entry["metrics"] or {}

        if grade_filter and (
            not entry["has_metrics"] or m.get("risk_grade", "") not in grade_filter
        ):
            continue

        if mfa_below > 0:
            if not entry["has_metrics"] or m.get("mfa_coverage_pct") is None:
                continue
            if m["mfa_coverage_pct"] >= mfa_below:
                continue

        if secure_score_below > 0:
            if not entry["has_metrics"] or m.get("secure_score_pct") is None:
                continue
            if m["secure_score_pct"] >= secure_score_below:
                continue

        results.append(entry)

    results.sort(
        key=lambda x: (
            0 if x["has_metrics"] else 1,
            x["metrics"].get("risk_score", 0) if x["has_metrics"] else 999,
        )
    )

    return {"customers": results, "active_id": active_id, "total": len(results)}


# ── Unified Customer Dashboard ──────────────────────────────────────────────


async def _read_block(
    name: str,
    read,
    unavailable: dict[str, str],
    customer_id: str,
):
    """Run one block's read, recording a failure rather than absorbing it.

    This view used to do::

        except Exception:
            result["audit"] = None

    which is the defect the audit pipeline was rebuilt to remove, still living
    in the customer view. The consequence was not cosmetic. The front end reads
    ``if ((a.users_no_mfa || 0) > 0)`` to build the "Krever handling" band, so a
    failed metrics read did not show an error — it showed a customer with
    nothing wrong. A database hiccup made a tenant look clean.

    A failure now leaves the value null *and* names the block in
    ``unavailable``, so a caller can tell "nothing configured" from "we could
    not look". Returning null for both and letting the reader guess is what
    this is here to stop.

    Still per-block rather than letting the exception out: one unreadable
    table should degrade one card, not take the whole customer page down.
    """
    try:
        return await read()
    except Exception as e:
        logger.warning("Customer view: %s read failed for %s: %s", name, customer_id, e)
        unavailable[name] = str(e)[:200]
        return None


@router.get(
    "/customer/{customer_id}/unified",
    response_model=UnifiedCustomerResponse,
    tags=["Dashboard"],
    summary="Get unified customer data",
    description="Returns aggregated configuration and state for a single customer across all integrations. Perfect for rendering the unified customer card.",
)
async def customer_unified(customer_id: str, user=Depends(require_customer_access(Role.viewer))):
    """Aggregated view of a single customer across all integrations.

    All data comes from local cache/config — zero external API calls.
    """
    from app.core.customer import CustomerManager
    from app.core.database import get_db

    if not await check_customer_access(user, customer_id):
        raise refusal(ForbiddenError, "err_customer_no_access")
    cust = CustomerManager.get_customer(customer_id)
    if not cust:
        raise refusal(NotFoundError, "err_customer_not_found")

    name = cust.get("CustomerName", "Unknown")
    also_id = cust.get("AlsoAccountId", "")

    result: dict = {
        "customer_id": customer_id,
        "customer_name": name,
        "domain": cust.get("PrimaryDomain", ""),
        "source": cust.get("Source", ""),
        "tags": cust.get("Tags", []),
        "also_account_id": also_id,
    }

    # ── M365 config ──
    m365 = {}
    for k in ("TenantId", "ClientId", "SecretExpiry", "CertExpiry", "PrimaryDomain"):
        if cust.get(k):
            m365[k] = cust[k]
    # Credential expiry status
    for key, label in [("SecretExpiry", "secret"), ("CertExpiry", "cert")]:
        iso_val = cust.get(key, "")
        if iso_val:
            try:
                dt = datetime.fromisoformat(iso_val.replace("Z", "+00:00"))
                days = (dt - datetime.now(UTC)).days
                m365[f"{label}_days_left"] = days
                m365[f"{label}_status"] = (
                    "expired"
                    if days < 0
                    else "critical"
                    if days < 7
                    else "warning"
                    if days < 30
                    else "ok"
                )
            except ValueError:
                pass
    result["m365"] = m365 if m365 else None

    # ── FortiGate config ──
    fg = {}
    for k in ("FortiGateHost", "FortiGatePort", "FortiGateVdom"):
        if cust.get(k):
            fg[k] = cust[k]
    result["fortigate"] = fg if fg else None

    # ── UniFi config ──
    uf = {}
    for k in ("UniFiHost", "UniFiMode", "UniFiSite", "UniFiIsUniFiOS"):
        if cust.get(k):
            uf[k] = cust[k]
    result["unifi"] = uf if uf else None

    # Blocks whose read failed, named with the reason. A key present here means
    # the null beside it is "we could not look", not "there is none" — see the
    # comment on _read_block.
    unavailable: dict[str, str] = {}

    # ── ALSO renewals (from DB cache) ──
    async def _read_also():
        if not also_id:
            return None
        from sqlmodel import select

        from app.core.orm import get_session
        from app.models.integrations import AlsoRenewal, AlsoSubscriptionDetail

        async with get_session() as session:
            stmt = (
                select(
                    AlsoRenewal,
                    AlsoSubscriptionDetail.quantity,
                    AlsoSubscriptionDetail.unit_price,
                    AlsoSubscriptionDetail.monthly_cost,
                    AlsoSubscriptionDetail.currency,
                )
                .join(
                    AlsoSubscriptionDetail,
                    AlsoRenewal.subscription_id == AlsoSubscriptionDetail.subscription_id,
                    isouter=True,
                )
                .where(AlsoRenewal.customer_id == customer_id)
                .order_by(AlsoRenewal.contract_end.asc())
            )
            res = await session.execute(stmt)
            renewals = []
            for row in res.mappings().all():
                # SQLModel mappings include the model object and other columns
                r_dict = (
                    dict(row["AlsoRenewal"])
                    if hasattr(row["AlsoRenewal"], "model_dump")
                    else {
                        k: getattr(row["AlsoRenewal"], k)
                        for k in row["AlsoRenewal"].__table__.columns
                    }
                )
                r_dict.update(
                    {
                        "quantity": row["quantity"],
                        "unit_price": row["unit_price"],
                        "monthly_cost": row["monthly_cost"],
                        "currency": row["currency"],
                    }
                )
                r_dict["product_name"] = (
                    r_dict.get("service_display") or r_dict.get("service_name") or ""
                )
                renewals.append(r_dict)
        now = datetime.now(UTC)
        for r in renewals:
            try:
                raw = r.get("contract_end", "")
                if raw:
                    end = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=UTC)
                    r["days_left"] = (end - now).days
                else:
                    r["days_left"] = None
            except (ValueError, TypeError):
                r["days_left"] = None
        expiring = [
            r for r in renewals if r.get("days_left") is not None and 0 <= r["days_left"] <= 90
        ]
        expired = [r for r in renewals if r.get("days_left") is not None and r["days_left"] < 0]
        return {
            "total_subscriptions": len(renewals),
            "expiring_90d": len(expiring),
            "expired": len(expired),
            "renewals": renewals,
            "mrr": round(sum(r.get("monthly_cost") or 0 for r in renewals), 2),
            "currency": next((r.get("currency") for r in renewals if r.get("currency")), ""),
        }

    result["also"] = await _read_block("also", _read_also, unavailable, customer_id)

    # ── SSH hosts ──
    async def _read_ssh_hosts():
        async with (
            get_db() as db,
            db.execute("SELECT * FROM ssh_hosts WHERE customer_id = ?", (customer_id,)) as cur,
        ):
            hosts = [dict(r) for r in await cur.fetchall()]
        return hosts if hosts else None

    result["ssh_hosts"] = await _read_block("ssh_hosts", _read_ssh_hosts, unavailable, customer_id)

    # ── Tailscale (match by customer name in device tags or hostname) ──
    # Not directly linked per-customer yet — set to None
    result["tailscale"] = None

    # ── Latest audit metrics ──
    async def _read_audit():
        from sqlmodel import select

        from app.core.orm import get_session
        from app.models.audit import AuditMetric

        async with get_session() as session:
            stmt = (
                select(AuditMetric)
                .where(AuditMetric.customer_id == customer_id)
                .order_by(AuditMetric.audit_date.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            m = result.scalars().first()
        if not m:
            return None
        return {
            "risk_grade": m.risk_grade,
            "risk_score": m.risk_score,
            "secure_score_pct": m.secure_score_pct,
            "mfa_coverage_pct": m.mfa_coverage_pct,
            "total_users": m.total_users,
            "users_no_mfa": m.users_no_mfa,
            "admin_roles_ga_count": m.admin_roles_ga_count,
            "audit_date": m.audit_date,
        }

    result["audit"] = await _read_block("audit", _read_audit, unavailable, customer_id)

    result["unavailable"] = unavailable
    return result
