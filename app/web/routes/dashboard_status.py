"""Dashboard status, files, and customer action endpoints.

Split from dashboard.py for maintainability.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request

from app.core import credentials as credential_store
from app.core import job_state as state
from app.core.activity_log import log_activity
from app.core.customer import CustomerManager
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.rbac import check_customer_access, filter_customers, get_accessible_customer_ids
from app.models.customer import CredentialResetTarget
from app.models.user import Role, User
from app.web.i18n import ui_t
from app.web.middleware.auth import get_current_user, require_role

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


# ── Files ─────────────────────────────────────────────────────────────────────


@router.get("/files")
async def get_files():
    """List customer files: cert, config, reports, raw audit data."""

    from app.core.config import AUDIT_DIR

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

    active_id = CustomerManager.get_active_id()
    audit_run = state.get_user_audit(user.id, active_id) if active_id else None

    if not config_exists():
        # No M365 config yet, but the customer still exists: the header names
        # it either way, instead of claiming that no customer is selected.
        active = CustomerManager.get_customer(active_id) if active_id else None
        return {
            "has_config": False,
            "customer": None
            if active is None
            else {
                "name": active.get("CustomerName", ""),
                "domain": active.get("PrimaryDomain", ""),
                "also_account_id": active.get("AlsoAccountId", ""),
            },
            "active_id": active_id or "",
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
            "also_account_id": cfg.get("AlsoAccountId", ""),
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


async def _clear_customer_credentials(
    request: Request, body: CredentialResetTarget | None, user: User, action: str
) -> dict:
    """Delete the stored M365 credentials of one customer the caller may access.

    The customer is the one named in the body, else the caller's active
    customer. These endpoints used to delete the secrets of whatever tenant
    the process-wide setup staging file named, which is simply the last setup
    anybody ran: renewing customer A wiped customer B's credentials, whether
    or not the caller could see B.

    Secrets are keyed by tenant, so every registration on the same tenant
    shares them, and the caller needs access to each of those as well.
    Registration, certificate and history stay; setup issues fresh
    credentials and re-registers over them.
    """
    # The browser sends no body; then the active customer applies.
    requested = body.customer_id if body else None
    customer_id = requested or CustomerManager.get_active_id()
    if not customer_id:
        raise ValidationError(ui_t("err_no_active_customer", request))
    if not await check_customer_access(user, customer_id):
        raise ForbiddenError(ui_t("err_customer_access_denied", request))
    customer = CustomerManager.get_customer(customer_id)
    if customer is None:
        raise NotFoundError(ui_t("err_customer_not_found", request))

    tenant_id = customer.get("TenantId", "")
    if tenant_id:
        for other in CustomerManager.list_customers():
            if other.get("TenantId") == tenant_id and not await check_customer_access(
                user, other["_id"]
            ):
                raise ForbiddenError(ui_t("err_credentials_shared_with_other_customer", request))
        credential_store.delete_all_secrets(tenant_id)
    credential_store.clear_secret_cache()

    log_activity(action, customer=customer.get("CustomerName", customer_id), user=user.username)
    return {"ok": True, "customer_id": customer_id}


@router.post("/customer/wipe")
async def customer_wipe(
    request: Request,
    body: CredentialResetTarget | None = None,
    user: User = Depends(require_role(Role.technician)),
):
    # Technician floor: a viewer has no business deleting credentials.
    return await _clear_customer_credentials(request, body, user, "customer_credentials_wiped")


@router.post("/customer/renew")
async def customer_renew(
    request: Request,
    body: CredentialResetTarget | None = None,
    user: User = Depends(require_role(Role.technician)),
):
    # The first half of renewal; the browser runs setup straight after.
    return await _clear_customer_credentials(request, body, user, "customer_credentials_renewed")


# ── Expiry check ──────────────────────────────────────────────────────────────


@router.get("/expiry/check")
async def check_expiry(user=Depends(get_current_user)):
    """Check ALL customers' credential expiry dates and return categorised results."""
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
