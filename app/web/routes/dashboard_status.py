"""Dashboard status, files, and customer action endpoints.

Split from dashboard.py for maintainability.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.core.rbac import filter_customers, get_accessible_customer_ids
from app.models.user import User
from app.web import state
from app.web.middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


# ── Files ─────────────────────────────────────────────────────────────────────


@router.get("/files")
async def get_files():
    """List customer files: cert, config, reports, raw audit data."""

    from app.core.config import AUDIT_DIR
    from app.core.customer import CustomerManager

    active = CustomerManager.get_active()
    if not active:
        return {"has_customer": False}

    customer_name = active.get("CustomerName", "unknown")
    customer_id = active.get("_id", "")

    credentials = {
        "customer_name": customer_name,
        "tenant_id": active.get("TenantId", ""),
        "client_id": active.get("ClientId", ""),
        "domain": active.get("PrimaryDomain", ""),
        "setup_date": active.get("SetupDate", "")[:10] if active.get("SetupDate") else "",
        "secret_expiry": active.get("SecretExpiry", "")[:10] if active.get("SecretExpiry") else "",
    }

    cert_path = CustomerManager.get_cert_path(customer_id)
    certificate = {
        "exists": cert_path.exists(),
        "path": str(cert_path),
        "expiry": active.get("CertExpiry", "")[:10] if active.get("CertExpiry") else "",
        "encrypted": True,
    }

    sanitized_name = "".join(
        c if c.isalnum() or c in "-_ " else "_" for c in customer_name
    ).replace(" ", "_")
    audit_base = AUDIT_DIR / sanitized_name
    reports: list[dict] = []
    if audit_base.exists():
        for run_dir in sorted(audit_base.iterdir(), reverse=True):
            if run_dir.is_dir():
                for f in sorted(run_dir.iterdir()):
                    if f.suffix in (".html", ".pdf"):
                        size_kb = f.stat().st_size / 1024
                        size_str = (
                            f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
                        )
                        reports.append(
                            {
                                "name": f"{run_dir.name}/{f.name}",
                                "size": size_str,
                            }
                        )

    runs = 0
    latest = ""
    total_bytes = 0
    if audit_base.exists():
        run_dirs = sorted([d for d in audit_base.iterdir() if d.is_dir()], reverse=True)
        runs = len(run_dirs)
        if run_dirs:
            latest = run_dirs[0].name
        for rd in run_dirs:
            for f in rd.rglob("*"):
                if f.is_file():
                    total_bytes += f.stat().st_size
    total_size = (
        f"{total_bytes / 1024:.0f} KB"
        if total_bytes < 1048576
        else f"{total_bytes / 1048576:.1f} MB"
    )

    return {
        "has_customer": True,
        "credentials": credentials,
        "certificate": certificate,
        "reports": reports[:50],
        "raw_data": {
            "runs": runs,
            "latest": latest,
            "total_size": total_size,
            "path": str(audit_base),
        },
    }


# ── Status ────────────────────────────────────────────────────────────────────


@router.get("/status")
async def get_status(user: User = Depends(get_current_user)):
    from app.core.credentials import config_exists, load_config
    from app.core.customer import CustomerManager

    active_id = CustomerManager.get_active_id()
    audit_run = state.get_user_audit(user.id, active_id) if active_id else None

    if not config_exists():
        return {
            "has_config": False,
            "audit_running": bool(audit_run and audit_run.running),
            "setup_running": state.setup_running,
        }

    cfg = load_config()
    warns: list[str] = []
    for key, label in [("SecretExpiry", "Client secret"), ("CertExpiry", "Certificate")]:
        val = cfg.get(key, "")
        if val:
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                days = (dt - datetime.now(UTC)).days
                if days < 30:
                    warns.append(f"{label} expires in {days} days!")
            except ValueError:
                pass

    tags = CustomerManager.get_tags(active_id) if active_id else []

    has_credentials = False
    tenant_id = cfg.get("TenantId", "")
    if tenant_id and cfg.get("ClientId"):
        from app.core.credentials import get_secret

        has_credentials = bool(get_secret(tenant_id, "client_secret"))

    return {
        "has_config": True,
        "has_credentials": has_credentials,
        "customer": {
            "name": cfg.get("CustomerName", "Unknown"),
            "domain": cfg.get("PrimaryDomain", ""),
            "setup_date": cfg.get("SetupDate", "")[:10],
            "warns": warns,
            "tags": tags,
            "tenant_id": tenant_id,
        },
        "active_id": active_id or "",
        "audit_running": bool(audit_run and audit_run.running),
        "setup_running": state.setup_running,
    }


# ── Latest report ────────────────────────────────────────────────────────────


@router.get("/latest-report")
async def get_latest_report():
    """Return URL to the latest HTML report for the active customer."""
    from app.core.config import AUDIT_DIR, get_audit_dir
    from app.core.credentials import load_config

    cfg = load_config()
    if not cfg:
        return {"has_report": False}

    customer_name = cfg.get("CustomerName", "Unknown")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in customer_name)
    customer_dir = get_audit_dir() / safe_name

    if not customer_dir.exists():
        return {"has_report": False}

    for run_dir in sorted(customer_dir.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        for f in run_dir.iterdir():
            if f.suffix == ".html" and "report" in f.name.lower():
                rel = f.relative_to(AUDIT_DIR)
                return {
                    "has_report": True,
                    "url": f"/audit_data/{rel}",
                    "filename": f.name,
                    "run": run_dir.name,
                }

    return {"has_report": False}


# ── Customer actions ──────────────────────────────────────────────────────────


@router.post("/customer/wipe")
async def customer_wipe():
    from app.core.credentials import load_global_config, wipe_customer

    # This endpoint resets setup staging.  The authenticated user's active
    # customer is durable registry data and must not be treated as staging.
    cfg = load_global_config()
    if cfg:
        wipe_customer(cfg.get("TenantId", ""))
    return {"ok": True}


@router.post("/customer/renew")
async def customer_renew():
    from app.core.credentials import (
        clear_secret_cache,
        delete_all_secrets,
        delete_cert,
        delete_config,
        load_global_config,
    )

    cfg = load_global_config()
    if cfg:
        delete_all_secrets(cfg.get("TenantId", ""))
    delete_config()
    delete_cert()
    clear_secret_cache()
    return {"ok": True}


# ── Expiry check ──────────────────────────────────────────────────────────────


@router.get("/expiry/check")
async def check_expiry(user=Depends(get_current_user)):
    """Check ALL customers' credential expiry dates and return categorised results."""
    from app.core.customer import CustomerManager

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    items: list[dict] = []

    for c in customers:
        customer_name = c.get("CustomerName", "Unknown")
        for cred_type, key in [("secret", "SecretExpiry"), ("cert", "CertExpiry")]:
            iso_val = c.get(key, "")
            if not iso_val:
                continue
            try:
                dt = datetime.fromisoformat(iso_val.replace("Z", "+00:00"))
                days = (dt - datetime.now(UTC)).days
            except ValueError:
                continue

            if days < 0:
                category = "expired"
            elif days < 7:
                category = "critical"
            elif days < 30:
                category = "warning"
            elif days < 60:
                category = "notice"
            else:
                category = "ok"

            items.append(
                {
                    "customer_name": customer_name,
                    "customer_id": c.get("_id", ""),
                    "type": cred_type,
                    "expiry_date": iso_val[:10],
                    "days_remaining": days,
                    "category": category,
                }
            )

    order = {"expired": 0, "critical": 1, "warning": 2, "notice": 3, "ok": 4}
    items.sort(key=lambda x: (order.get(x["category"], 9), x["days_remaining"]))

    summary = {
        "expired": len([i for i in items if i["category"] == "expired"]),
        "critical": len([i for i in items if i["category"] == "critical"]),
        "warning": len([i for i in items if i["category"] == "warning"]),
        "notice": len([i for i in items if i["category"] == "notice"]),
        "ok": len([i for i in items if i["category"] == "ok"]),
        "total": len(items),
    }

    return {"items": items, "summary": summary}
