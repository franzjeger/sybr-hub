"""Customer CRUD, notes, and tags endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.rbac import filter_customers, get_accessible_customer_ids
from app.models.customer import CustomerNotes, CustomerRef, CustomerTags, ManualCustomerCreate
from app.models.user import Role, User
from app.web.i18n import refusal, ui_t
from app.web.middleware.auth import get_current_user, require_customer_access, require_role

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Customer management ──────────────────────────────────────────────────────


@router.get("/customers")
async def list_customers(user: User = Depends(get_current_user)):
    from app.core.customer import CustomerManager

    CustomerManager.migrate_legacy()  # auto-migrate on first access
    all_customers = CustomerManager.list_customers()
    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(all_customers, allowed)
    # Batch-annotate notes/tags (avoid N+1 file I/O)
    cids = [c.get("_id", "") for c in customers]
    tags_cache = {cid: CustomerManager.get_tags(cid) for cid in cids}
    for c in customers:
        cid = c.get("_id", "")
        c["_has_notes"] = (CustomerManager.get_customer_dir(cid) / "notes.md").exists()
        c["_tags"] = tags_cache.get(cid, [])
    # No "active_id": the server keeps no current customer for a user. Which
    # customer a tab is working on is that tab's business (app.js).
    return {"customers": customers}


@router.post("/customers/delete")
async def delete_customer(
    body: CustomerRef, request: Request, user: User = Depends(require_role(Role.admin))
):
    from app.core.customer import CustomerManager

    customer_id = body.customer_id
    if not customer_id:
        raise ValidationError(ui_t("err_missing_customer_id", request))
    customer = CustomerManager.get_customer(customer_id)
    customer_name = customer.get("CustomerName", customer_id) if customer else customer_id
    # Archive conflicts must not destroy the still-active customer's credentials.
    CustomerManager.delete_customer(customer_id)
    if customer and customer.get("TenantId"):
        from app.core.credentials import delete_all_secrets

        delete_all_secrets(customer["TenantId"])

    from app.core.activity_log import log_activity

    log_activity(
        "customer_archived",
        detail="Registration retired; historical data retained",
        customer=customer_name,
        user=user.username,
    )

    return {
        "ok": True,
        "archived": True,
        "retained": ["audits", "reports", "certificates", "database_history", "backups"],
        "purge_runbook": "docs/RETENTION.md",
    }


@router.post("/customers/add-manual")
async def add_manual_customer(
    body: ManualCustomerCreate,
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Create a customer manually without M365 setup."""
    from app.core.customer import CustomerManager

    name = (body.name or "").strip()
    if not name:
        raise ValidationError(ui_t("err_name_required", request))

    # Check for duplicate name
    existing = CustomerManager.list_customers()
    existing_names = {c.get("CustomerName", "").lower() for c in existing}
    if name.lower() in existing_names:
        raise ConflictError(ui_t("err_customer_exists", request))

    config = {
        "CustomerName": name,
        "PrimaryDomain": (body.primary_domain or "").strip(),
        "ContactEmail": (body.contact_email or "").strip(),
        "ContactPhone": (body.contact_phone or "").strip(),
        "OrgNumber": (body.org_number or "").strip(),
        "TenantId": "",
        "ClientId": "",
        "InitialDomain": "",
        "AppObjectId": "",
        "SubscriptionId": "",
        "SetupDate": datetime.now(UTC).isoformat(),
        "SecretExpiry": "",
        "CertExpiry": "",
        "Source": "manual",
    }
    cust_id = CustomerManager.save_customer(config, create=True)

    # Save notes if provided
    notes = (body.notes or "").strip()
    if notes:
        from app.core.encryption import encrypted_write_text

        notes_path = CustomerManager.get_customer_dir(cust_id) / "notes.md"
        encrypted_write_text(notes_path, notes)

    from app.core.activity_log import log_activity

    log_activity(
        "customer_added",
        detail=f"Manuelt opprettet kunde: {name}",
        customer=name,
        user=user.username,
    )

    return {"ok": True, "customer_id": cust_id}


@router.post("/customers/register")
async def register_customer(user: User = Depends(require_role(Role.technician))):
    """Register the current config as a customer in the multi-tenant registry."""
    from app.core.credentials import global_cert_path, load_global_config
    from app.core.customer import CustomerManager

    # Setup writes to the process-wide staging slot.  Never resolve this read
    # through the caller's currently selected customer: doing so would
    # re-register that customer instead of the one setup just created.
    cfg = load_global_config()
    if not cfg:
        raise refusal(ValidationError, "err_no_config_to_register")
    cid = CustomerManager.save_customer(cfg)
    # Copy cert
    cp = global_cert_path()
    if cp.exists():
        import shutil

        shutil.copy2(str(cp), str(CustomerManager.get_cert_path(cid)))

    from app.core.activity_log import log_activity

    log_activity("customer_added", customer=cfg.get("CustomerName", ""), user=user.username)

    return {"ok": True, "customer_id": cid}


# ── Customer notes ────────────────────────────────────────────────────────────


def _notes_path(customer_id: str):
    from app.core.customer import CustomerManager

    return CustomerManager.get_customer_dir(customer_id) / "notes.md"


def _saved_at(path) -> str:
    import os

    return datetime.fromtimestamp(os.path.getmtime(path), tz=UTC).isoformat()


@router.get("/customer/{customer_id}/notes")
async def get_customer_notes(
    customer_id: str, user: User = Depends(require_customer_access(Role.viewer))
):
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_read_text

    if CustomerManager.get_customer(customer_id) is None:
        raise refusal(NotFoundError, "err_customer_not_found")
    notes_path = _notes_path(customer_id)
    if not notes_path.exists():
        return {"customer_id": customer_id, "notes": "", "last_saved": ""}
    return {
        "customer_id": customer_id,
        "notes": encrypted_read_text(notes_path),
        "last_saved": _saved_at(notes_path),
    }


@router.post("/customer/{customer_id}/notes")
async def save_customer_notes(
    customer_id: str,
    body: CustomerNotes,
    user: User = Depends(require_customer_access(Role.technician)),
):
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_write_text

    if CustomerManager.get_customer(customer_id) is None:
        raise refusal(NotFoundError, "err_customer_not_found")
    notes_path = _notes_path(customer_id)
    encrypted_write_text(notes_path, body.notes)
    return {"ok": True, "customer_id": customer_id, "last_saved": _saved_at(notes_path)}


# ── Customer tags ─────────────────────────────────────────────────────────────


@router.get("/customer/{customer_id}/tags")
async def get_customer_tags(
    customer_id: str, user: User = Depends(require_customer_access(Role.viewer))
):
    from app.core.customer import CustomerManager

    return {"customer_id": customer_id, "tags": CustomerManager.get_tags(customer_id)}


@router.post("/customer/{customer_id}/tags")
async def set_customer_tags(
    customer_id: str,
    body: CustomerTags,
    user: User = Depends(require_customer_access(Role.technician)),
):
    from app.core.customer import CustomerManager

    if CustomerManager.get_customer(customer_id) is None:
        raise refusal(NotFoundError, "err_customer_not_found")
    CustomerManager.set_tags(customer_id, body.tags)
    return {"ok": True, "tags": CustomerManager.get_tags(customer_id)}
