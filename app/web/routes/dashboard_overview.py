"""Dashboard overview, trends and customer search endpoints.

Split from dashboard.py for maintainability.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request

from app.core.rbac import filter_customers, get_accessible_customer_ids
from app.reports.recommendations import relocalise_recommendations
from app.web.i18n import get_ui_lang
from app.web.middleware.auth import get_current_user

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
