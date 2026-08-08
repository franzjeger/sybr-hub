"""Customer CRUD, notes, and tags endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.rbac import check_customer_access, filter_customers, get_accessible_customer_ids
from app.models.user import Role, User
from app.web.i18n import ui_t
from app.web.middleware.auth import get_current_user, require_role

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
    active_id = CustomerManager.get_active_id()
    # Batch-annotate notes/tags (avoid N+1 file I/O)
    cids = [c.get("_id", "") for c in customers]
    tags_cache = {cid: CustomerManager.get_tags(cid) for cid in cids}
    for c in customers:
        cid = c.get("_id", "")
        c["is_active"] = cid == active_id
        c["_has_notes"] = (CustomerManager.get_customer_dir(cid) / "notes.md").exists()
        c["_tags"] = tags_cache.get(cid, [])
    return {"customers": customers, "active_id": active_id}


@router.post("/customers/switch")
async def switch_customer(request: Request, user: User = Depends(get_current_user)):
    from app.core.customer import CustomerManager
    body = await request.json()
    customer_id = body.get("customer_id", "")
    customer = CustomerManager.get_customer(customer_id)
    if not customer:
        raise NotFoundError(ui_t("err_customer_not_found", request))
    if not await check_customer_access(user, customer_id):
        raise ForbiddenError("Ingen tilgang til denne kunden")
    CustomerManager.set_active(customer_id)

    from app.core.activity_log import log_activity
    log_activity("customer_switched", customer=customer.get("CustomerName", ""), user=user.username)

    return {"ok": True, "customer": customer}


@router.post("/customers/delete")
async def delete_customer(request: Request, user: User = Depends(require_role(Role.admin))):
    from app.core.customer import CustomerManager
    body = await request.json()
    customer_id = body.get("customer_id", "")
    if not customer_id:
        raise ValidationError(ui_t("err_missing_customer_id", request))
    # Delete secrets from keyring
    customer = CustomerManager.get_customer(customer_id)
    if customer:
        from app.core.credentials import delete_all_secrets
        delete_all_secrets(customer.get("TenantId", ""))
    customer_name = customer.get("CustomerName", customer_id) if customer else customer_id
    CustomerManager.delete_customer(customer_id)

    from app.core.activity_log import log_activity
    log_activity("customer_deleted", detail=f"Kunde {customer_name} slettet", customer=customer_name, user=user.username)

    return {"ok": True}


@router.post("/customers/add-manual")
async def add_manual_customer(request: Request, user: User = Depends(get_current_user)):
    """Create a customer manually without M365 setup."""
    from app.core.customer import CustomerManager

    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise ValidationError(ui_t("err_name_required", request))

    # Check for duplicate name
    existing = CustomerManager.list_customers()
    existing_names = {c.get("CustomerName", "").lower() for c in existing}
    if name.lower() in existing_names:
        raise ConflictError(ui_t("err_customer_exists", request))

    config = {
        "CustomerName": name,
        "PrimaryDomain": (body.get("primary_domain") or "").strip(),
        "ContactEmail": (body.get("contact_email") or "").strip(),
        "ContactPhone": (body.get("contact_phone") or "").strip(),
        "OrgNumber": (body.get("org_number") or "").strip(),
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
    cust_id = CustomerManager.save_customer(config)

    # Save notes if provided
    notes = (body.get("notes") or "").strip()
    if notes:
        from app.core.encryption import encrypted_write_text
        notes_path = CustomerManager.get_customer_dir(cust_id) / "notes.md"
        encrypted_write_text(notes_path, notes)

    from app.core.activity_log import log_activity
    log_activity("customer_added", detail=f"Manuelt opprettet kunde: {name}", customer=name, user=user.username)

    return {"ok": True, "customer_id": cust_id}


@router.post("/customers/register")
async def register_customer(user: User = Depends(get_current_user)):
    """Register the current config as a customer in the multi-tenant registry."""
    from app.core.credentials import global_cert_path, load_global_config
    from app.core.customer import CustomerManager
    # Setup writes to the process-wide staging slot.  Never resolve this read
    # through the caller's currently selected customer: doing so would
    # re-register that customer instead of the one setup just created.
    cfg = load_global_config()
    if not cfg:
        raise ValidationError(ui_t("err_no_config_to_register"))
    cid = CustomerManager.save_customer(cfg)
    # Copy cert
    cp = global_cert_path()
    if cp.exists():
        import shutil
        shutil.copy2(str(cp), str(CustomerManager.get_cert_path(cid)))
    CustomerManager.set_active(cid)

    from app.core.activity_log import log_activity
    log_activity("customer_added", customer=cfg.get("CustomerName", ""), user=user.username)

    return {"ok": True, "customer_id": cid}


# ── Customer notes ────────────────────────────────────────────────────────────

@router.get("/customer/notes")
async def get_customer_notes(user: User = Depends(get_current_user)):
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_read_text
    active_id = CustomerManager.get_active_id()
    if not active_id:
        raise ValidationError(ui_t("err_no_active_customer"))
    notes_path = CustomerManager.get_customer_dir(active_id) / "notes.md"
    notes = ""
    last_saved = ""
    if notes_path.exists():
        notes = encrypted_read_text(notes_path)
        import os
        mtime = os.path.getmtime(notes_path)
        last_saved = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
    return {"notes": notes, "last_saved": last_saved}


@router.post("/customer/notes")
async def save_customer_notes(request: Request, user: User = Depends(get_current_user)):
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_write_text
    active_id = CustomerManager.get_active_id()
    if not active_id:
        raise ValidationError(ui_t("err_no_active_customer", request))
    body = await request.json()
    notes = body.get("notes", "")
    notes_path = CustomerManager.get_customer_dir(active_id) / "notes.md"
    encrypted_write_text(notes_path, notes)
    import os
    mtime = os.path.getmtime(notes_path)
    last_saved = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
    return {"ok": True, "last_saved": last_saved}


# ── Customer tags ─────────────────────────────────────────────────────────────

@router.get("/customer/tags")
async def get_customer_tags(user: User = Depends(get_current_user)):
    from app.core.customer import CustomerManager
    active_id = CustomerManager.get_active_id()
    if not active_id:
        raise ValidationError(ui_t("err_no_active_customer"))
    tags = CustomerManager.get_tags(active_id)
    return {"customer_id": active_id, "tags": tags}


@router.post("/customer/tags")
async def set_customer_tags(request: Request, user: User = Depends(get_current_user)):
    from app.core.customer import CustomerManager
    body = await request.json()
    customer_id = body.get("customer_id")
    if not customer_id:
        customer_id = CustomerManager.get_active_id()
    if not customer_id:
        raise ValidationError(ui_t("err_no_active_customer", request))
    if not await check_customer_access(user, customer_id):
        raise ForbiddenError("Ingen tilgang til denne kunden")
    tags = body.get("tags", [])
    if not isinstance(tags, list):
        raise ValidationError("tags må være en liste")
    CustomerManager.set_tags(customer_id, tags)
    return {"ok": True, "tags": CustomerManager.get_tags(customer_id)}
