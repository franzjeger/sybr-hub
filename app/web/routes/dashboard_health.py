"""Dashboard health scores and alerts endpoints.

Split from dashboard.py for maintainability.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.core.rbac import filter_customers, get_accessible_customer_ids
from app.web.middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Alerts aggregation ───────────────────────────────────────────────────────

@router.get("/dashboard/alerts")
async def dashboard_alerts(user=Depends(get_current_user)):
    """Aggregate all items needing attention across the MSP."""
    from app.core.customer import CustomerManager
    from app.core.database import get_db

    now = datetime.now(timezone.utc)
    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)

    # ── Credential expiry (same logic as /expiry/check) ──
    credential_items: list[dict] = []
    for c in customers:
        customer_name = c.get("CustomerName", "Unknown")
        cid = c.get("_id", "")
        for cred_type, key in [("secret", "SecretExpiry"), ("cert", "CertExpiry")]:
            iso_val = c.get(key, "")
            if not iso_val:
                continue
            try:
                dt = datetime.fromisoformat(iso_val.replace("Z", "+00:00"))
                days = (dt - now).days
            except ValueError:
                continue
            if days >= 30:
                continue  # only alert-worthy items
            if days < 0:
                category = "critical"
            elif days < 7:
                category = "critical"
            elif days < 30:
                category = "warning"
            else:
                category = "info"
            credential_items.append({
                "customer_name": customer_name,
                "customer_id": cid,
                "type": cred_type,
                "expiry_date": iso_val[:10],
                "days_remaining": days,
                "category": category,
            })
    credential_items.sort(key=lambda x: x["days_remaining"])

    # ── ALSO renewal expiry ──
    renewal_items: list[dict] = []
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id, customer_name, subscription_id, service_name, "
                "contract_end, account_state, handled FROM also_renewals"
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
        for r in rows:
            raw = r.get("contract_end", "")
            if not raw:
                continue
            try:
                end = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
                days = (end - now).days
            except (ValueError, TypeError):
                continue
            if days >= 30:
                continue
            if days < 0:
                category = "critical"
            elif days < 7:
                category = "critical"
            elif days < 30:
                category = "warning"
            else:
                category = "info"
            renewal_items.append({
                "customer_name": r.get("customer_name", ""),
                "customer_id": r.get("customer_id", ""),
                "subscription_id": r.get("subscription_id", ""),
                "service_name": r.get("service_name", ""),
                "contract_end": raw[:10] if raw else "",
                "days_remaining": days,
                "category": category,
                "handled": bool(r.get("handled")),
            })
        renewal_items.sort(key=lambda x: x["days_remaining"])
    except Exception as exc:
        logger.warning("Failed to read also_renewals for alerts: %s", exc)

    all_items = credential_items + renewal_items
    critical = sum(1 for i in all_items if i["category"] == "critical")
    warning = sum(1 for i in all_items if i["category"] == "warning")
    info = sum(1 for i in all_items if i["category"] == "info")

    return {
        "credential_expiry": credential_items,
        "renewals": renewal_items,
        "total_alerts": len(all_items),
        "categories": {"critical": critical, "warning": warning, "info": info},
    }


# ── Per-customer health score ────────────────────────────────────────────────

@router.get("/dashboard/health")
async def dashboard_health(user=Depends(get_current_user)):
    """Per-customer health score (0-100) with grade and issues list."""
    from app.core.customer import CustomerManager
    from app.core.database import get_db

    now = datetime.now(timezone.utc)
    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)

    # Pre-fetch ALSO renewals grouped by customer
    also_by_customer: dict[str, list[dict]] = {}
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id, contract_end, account_state, handled "
                "FROM also_renewals"
            ) as cur:
                for r in await cur.fetchall():
                    row = dict(r)
                    cid = row["customer_id"]
                    also_by_customer.setdefault(cid, []).append(row)
    except Exception as exc:
        logger.warning("Failed to read also_renewals for health: %s", exc)

    # Pre-fetch latest audit_metrics per customer
    metrics_by_customer: dict[str, dict] = {}
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id, risk_grade, risk_score, secure_score_pct, "
                "mfa_coverage_pct, audit_date "
                "FROM audit_metrics "
                "ORDER BY audit_date DESC"
            ) as cur:
                for r in await cur.fetchall():
                    row = dict(r)
                    cid = row["customer_id"]
                    if cid not in metrics_by_customer:
                        # Add staleness info
                        audit_date_str = row.get("audit_date", "")
                        if audit_date_str:
                            try:
                                ad = datetime.fromisoformat(audit_date_str[:10]).replace(tzinfo=timezone.utc)
                                row["audit_age_days"] = (datetime.now(timezone.utc) - ad).days
                                row["is_stale"] = row["audit_age_days"] > 30
                            except (ValueError, TypeError):
                                row["audit_age_days"] = None
                                row["is_stale"] = True
                        else:
                            row["audit_age_days"] = None
                            row["is_stale"] = True
                        metrics_by_customer[cid] = row
    except Exception as exc:
        logger.warning("Failed to read audit_metrics for health: %s", exc)

    results: list[dict] = []

    for c in customers:
        cid = c.get("_id", "")
        name = c.get("CustomerName", "Unknown")
        score = 100
        issues: list[str] = []

        # ── M365 configured? ──
        has_m365 = bool(c.get("TenantId") and c.get("ClientId"))
        if not has_m365:
            score -= 10
            issues.append("M365 not configured")

        # ── Secret/cert expiry ──
        for cred_type, key in [("Secret", "SecretExpiry"), ("Certificate", "CertExpiry")]:
            iso_val = c.get(key, "")
            if not iso_val:
                continue
            try:
                dt = datetime.fromisoformat(iso_val.replace("Z", "+00:00"))
                days = (dt - now).days
            except ValueError:
                continue
            if days < 0:
                score -= 30
                issues.append(f"{cred_type} expired ({abs(days)}d ago)")
            elif days < 30:
                score -= 15
                issues.append(f"{cred_type} expires in {days}d")
            elif days < 60:
                score -= 5
                issues.append(f"{cred_type} expires in {days}d")

        # ── ALSO renewals ──
        also_rows = also_by_customer.get(cid, [])
        also_penalty = 0
        for r in also_rows:
            raw = r.get("contract_end", "")
            if not raw:
                continue
            try:
                end = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
                days = (end - now).days
            except (ValueError, TypeError):
                continue
            if days < 0:
                also_penalty += 20
                issues.append(f"ALSO sub expired ({abs(days)}d ago)")
            elif days < 30:
                also_penalty += 5
                issues.append(f"ALSO sub expires in {days}d")
        also_penalty = min(also_penalty, 30)
        score -= also_penalty

        # ── Audit metrics (latest) ──
        am = metrics_by_customer.get(cid)
        if am:
            grade = (am.get("risk_grade") or "").upper()
            if grade in ("D", "F"):
                score -= 20
                issues.append(f"Risk grade {grade}")
            elif grade == "C":
                score -= 10
                issues.append(f"Risk grade {grade}")

        score = max(score, 0)

        if score >= 90:
            letter = "A"
        elif score >= 75:
            letter = "B"
        elif score >= 60:
            letter = "C"
        elif score >= 40:
            letter = "D"
        else:
            letter = "F"

        results.append({
            "customer_id": cid,
            "customer_name": name,
            "score": score,
            "grade": letter,
            "issues": issues,
        })

    results.sort(key=lambda x: x["score"])

    total = len(results)
    avg_score = round(sum(r["score"] for r in results) / total, 1) if total else 0
    critical_count = sum(1 for r in results if r["grade"] in ("D", "F"))
    warning_count = sum(1 for r in results if r["grade"] == "C")
    healthy_count = sum(1 for r in results if r["grade"] in ("A", "B"))

    return {
        "customers": results,
        "summary": {
            "avg_score": avg_score,
            "critical": critical_count,
            "warning": warning_count,
            "healthy": healthy_count,
        },
    }


# ── Helper: ALSO days left ───────────────────────────────────────────────────

def _also_days_left(row: dict, now: datetime) -> int | None:
    """Helper: days until ALSO contract_end."""
    raw = row.get("contract_end", "")
    if not raw:
        return None
    try:
        end = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return (end - now).days
    except (ValueError, TypeError):
        return None


# ── Unified Customer Health Scores ─────────────────────────────────────────

@router.get("/dashboard/health-scores")
async def dashboard_health_scores(user=Depends(get_current_user)):
    """Unified 0-100 health score per customer combining all integrations.

    Categories:
      - Security audit (30 pts) — latest risk grade
      - License compliance (20 pts) — ALSO subscription status
      - Domain health (20 pts) — Uniweb domains / SSL
      - Infrastructure (15 pts) — FortiGate / UniFi configured
      - MFA status (15 pts) — from audit data
    """
    import json as _json

    from app.core.customer import CustomerManager
    from app.core.database import get_db

    now = datetime.now(timezone.utc)
    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)

    # ── Pre-fetch: audit metrics (latest per customer) ──
    metrics_by_customer: dict[str, dict] = {}
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id, risk_grade, risk_score, secure_score_pct, "
                "mfa_coverage_pct, total_users, users_no_mfa, audit_date "
                "FROM audit_metrics ORDER BY audit_date DESC"
            ) as cur:
                for r in await cur.fetchall():
                    row = dict(r)
                    cid = row["customer_id"]
                    if cid not in metrics_by_customer:
                        # Add staleness info
                        audit_date_str = row.get("audit_date", "")
                        if audit_date_str:
                            try:
                                ad = datetime.fromisoformat(audit_date_str[:10]).replace(tzinfo=timezone.utc)
                                row["audit_age_days"] = (datetime.now(timezone.utc) - ad).days
                                row["is_stale"] = row["audit_age_days"] > 30
                            except (ValueError, TypeError):
                                row["audit_age_days"] = None
                                row["is_stale"] = True
                        else:
                            row["audit_age_days"] = None
                            row["is_stale"] = True
                        metrics_by_customer[cid] = row
    except Exception as exc:
        logger.warning("health-scores: failed to read audit_metrics: %s", exc)

    # ── Pre-fetch: ALSO renewals grouped by customer ──
    also_by_cust: dict[str, list[dict]] = {}
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id, contract_end, account_state "
                "FROM also_renewals"
            ) as cur:
                for r in await cur.fetchall():
                    row = dict(r)
                    cid = row["customer_id"]
                    also_by_cust.setdefault(cid, []).append(row)
    except Exception as exc:
        logger.warning("health-scores: failed to read also_renewals: %s", exc)

    # ── Pre-fetch: Uniweb data grouped by customer ──
    uniweb_by_cust: dict[str, dict] = {}
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id, data_json FROM uniweb_accounts "
                "WHERE customer_id IS NOT NULL"
            ) as cur:
                for r in await cur.fetchall():
                    cid = r["customer_id"]
                    if cid and r["data_json"]:
                        try:
                            uniweb_by_cust[cid] = _json.loads(r["data_json"])
                        except _json.JSONDecodeError:
                            pass
    except Exception as exc:
        logger.warning("health-scores: failed to read uniweb_accounts: %s", exc)

    # ── Score each customer ──
    results: list[dict] = []
    grade_dist: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0, "?": 0}

    for c in customers:
        cid = c.get("_id", "")
        name = c.get("CustomerName", "Unknown")

        # ── 1. Security Audit (30 pts) ──
        audit_data = metrics_by_customer.get(cid)
        audit_score = 0
        audit_detail = "Ingen data"
        if audit_data:
            grade = (audit_data.get("risk_grade") or "").upper()
            grade_map = {"A": 30, "B": 24, "C": 18, "D": 12, "F": 6}
            audit_score = grade_map.get(grade, 0)
            audit_detail = f"Karakter {grade}" if grade else "Ingen karakter"

        # ── 2. License Compliance (20 pts) ──
        also_rows = also_by_cust.get(cid, [])
        license_score = 0
        license_detail = "Ingen data"
        if also_rows:
            has_expired = False
            has_expiring_soon = False
            for r in also_rows:
                days = _also_days_left(r, now)
                if days is not None and days < 0:
                    has_expired = True
                elif days is not None and days < 30:
                    has_expiring_soon = True

            if has_expired:
                license_score = 0
                license_detail = "Utlopte abonnement"
            elif has_expiring_soon:
                license_score = 10
                exp_count = sum(
                    1 for r in also_rows
                    if (_d := _also_days_left(r, now)) is not None and 0 <= _d < 30
                )
                license_detail = f"{exp_count} utloper snart"
            else:
                license_score = 20
                license_detail = "Alle aktive"

        # ── 3. Domain Health (20 pts) ──
        uw_data = uniweb_by_cust.get(cid)
        domain_score = 0
        domain_detail = "Ingen data"
        if uw_data:
            domains = uw_data.get("domains", [])
            ssl_certs = uw_data.get("ssl", [])
            has_expired_ssl = False
            has_expiring_ssl = False
            has_domain_issues = False

            for cert in ssl_certs:
                expiry_str = (cert.get("expiry") or "").strip()
                if not expiry_str or len(expiry_str) < 10:
                    continue
                try:
                    exp_date = datetime.fromisoformat(expiry_str[:10])
                    exp_date = exp_date.replace(tzinfo=timezone.utc)
                    ssl_days = (exp_date - now).days
                except (ValueError, TypeError):
                    continue
                if ssl_days < 0:
                    has_expired_ssl = True
                elif ssl_days < 30:
                    has_expiring_ssl = True

            for dom in domains:
                expiry_str = (dom.get("expiry") or "").strip()
                if not expiry_str or len(expiry_str) < 10:
                    continue
                try:
                    exp_date = datetime.fromisoformat(expiry_str[:10])
                    exp_date = exp_date.replace(tzinfo=timezone.utc)
                    dom_days = (exp_date - now).days
                except (ValueError, TypeError):
                    continue
                if dom_days < 30:
                    has_domain_issues = True

            if has_expired_ssl:
                domain_score = 0
                domain_detail = "Utlopt SSL"
            elif has_expiring_ssl or has_domain_issues:
                domain_score = 10
                parts = []
                if has_expiring_ssl:
                    parts.append("SSL utloper snart")
                if has_domain_issues:
                    parts.append("Domeneproblemer")
                domain_detail = ", ".join(parts)
            else:
                domain_score = 20
                domain_detail = (
                    f"{len(domains)} domener OK" if domains else "Ingen domener"
                )

        # ── 4. Infrastructure (15 pts) ──
        has_fortigate = bool(c.get("FortiGateHost"))
        has_unifi = bool(c.get("UniFiHost"))
        infra_score = 0
        infra_detail = "Ingen data"
        if has_fortigate and has_unifi:
            infra_score = 15
            infra_detail = "FortiGate + UniFi"
        elif has_fortigate or has_unifi:
            infra_score = 8
            infra_detail = "FortiGate" if has_fortigate else "UniFi"

        # ── 5. MFA Status (15 pts) ──
        mfa_score = 0
        mfa_detail = "Ingen data"
        if audit_data and audit_data.get("mfa_coverage_pct") is not None:
            mfa_pct = audit_data["mfa_coverage_pct"]
            if mfa_pct >= 100:
                mfa_score = 15
                mfa_detail = "100% MFA"
            elif mfa_pct > 80:
                mfa_score = 10
                mfa_detail = f"{mfa_pct:.0f}% MFA"
            elif mfa_pct > 50:
                mfa_score = 5
                mfa_detail = f"{mfa_pct:.0f}% MFA"
            else:
                mfa_score = 0
                mfa_detail = f"{mfa_pct:.0f}% MFA"

        # ── Total — exclude missing categories from max ──
        total_score = (
            audit_score + license_score + domain_score + infra_score + mfa_score
        )
        max_possible = 100
        if not audit_data:
            max_possible -= 30
        if not also_rows:
            max_possible -= 20
        if not uw_data:
            max_possible -= 20
        if not (has_fortigate or has_unifi):
            max_possible -= 15
        if not (audit_data and audit_data.get("mfa_coverage_pct") is not None):
            max_possible -= 15

        # Scale score to percentage of available data
        if max_possible > 0:
            pct_score = round(total_score / max_possible * 100)
        else:
            pct_score = None  # No data at all

        if pct_score is None:
            letter = "?"
        elif pct_score >= 90:
            letter = "A"
        elif pct_score >= 75:
            letter = "B"
        elif pct_score >= 60:
            letter = "C"
        elif pct_score >= 40:
            letter = "D"
        else:
            letter = "F"
        grade_dist[letter] += 1

        results.append({
            "customer_id": cid,
            "customer_name": name,
            "total_score": pct_score if pct_score is not None else 0,
            "max_possible": max_possible,
            "grade": letter,
            "breakdown": {
                "security_audit": {
                    "score": audit_score, "max": 30, "detail": audit_detail,
                },
                "license_compliance": {
                    "score": license_score, "max": 20, "detail": license_detail,
                },
                "domain_health": {
                    "score": domain_score, "max": 20, "detail": domain_detail,
                },
                "infrastructure": {
                    "score": infra_score, "max": 15, "detail": infra_detail,
                },
                "mfa_status": {
                    "score": mfa_score, "max": 15, "detail": mfa_detail,
                },
            },
        })

    results.sort(key=lambda x: x["total_score"])

    n = len(results)
    avg = round(sum(r["total_score"] for r in results) / n, 1) if n else 0

    return {
        "scores": results,
        "average_score": avg,
        "grade_distribution": grade_dist,
    }
