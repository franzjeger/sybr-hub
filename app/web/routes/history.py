"""History & audit-comparison routes."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    AuthError,
    ConflictError,
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.user import Role, User
from app.web import state
from app.web.i18n import ui_t
from app.web.middleware.auth import get_current_user, require_customer_access

logger = logging.getLogger(__name__)

router = APIRouter()

_auth = Depends(get_current_user)


@router.get("/trends/{customer_id}")
async def get_customer_trends(
    customer_id: str,
    user: User = Depends(require_customer_access(Role.viewer)),
    limit: int = 20,
):
    """Return historical audit metrics for a customer, newest first."""
    from app.core.database import get_db

    async with (
        get_db() as conn,
        conn.execute(
            """SELECT audit_date, risk_grade, risk_score, mfa_coverage_pct,
                      secure_score_pct, total_users, users_no_mfa,
                      ca_policies_enabled, intune_compliance_pct
               FROM audit_metrics
               WHERE customer_id = ? OR customer_name = ?
               ORDER BY audit_date DESC LIMIT ?""",
            (customer_id, customer_id, limit),
        ) as cur,
    ):
        rows = await cur.fetchall()
    # Return oldest-first for chart rendering
    entries = [
        {
            "date": r[0],
            "risk_grade": r[1],
            "risk_score": r[2],
            "mfa_pct": r[3],
            "secure_score_pct": r[4],
            "total_users": r[5],
            "users_no_mfa": r[6],
            "ca_policies": r[7],
            "intune_pct": r[8],
        }
        for r in reversed(rows)
    ]
    return {"customer_id": customer_id, "entries": entries}


@router.get("/trends")
async def get_all_trends(user: User = _auth, limit: int = 50):
    """Return latest metrics per customer for dashboard sparklines."""
    from app.core.database import get_db
    from app.core.rbac import get_accessible_customer_ids

    allowed = await get_accessible_customer_ids(user)
    params: tuple[object, ...]
    if allowed is None:
        where = ""
        params = (limit,)
    elif not allowed:
        return {"entries": []}
    else:
        placeholders = ", ".join("?" for _ in allowed)
        where = f"WHERE customer_id IN ({placeholders})"
        params = (*sorted(allowed), limit)

    async with (
        get_db() as conn,
        conn.execute(
            f"""SELECT customer_id, customer_name, audit_date, risk_grade, risk_score,
                       mfa_coverage_pct, secure_score_pct
                FROM audit_metrics
                {where}
                ORDER BY audit_date DESC LIMIT ?""",
            params,
        ) as cur,
    ):
        rows = await cur.fetchall()
    entries = [
        {
            "customer_id": r[0],
            "customer_name": r[1],
            "date": r[2],
            "risk_grade": r[3],
            "risk_score": r[4],
            "mfa_pct": r[5],
            "secure_score_pct": r[6],
        }
        for r in rows
    ]
    return {"entries": entries}


# ── API: Audit history ─────────────────────────────────────────────────────────


@router.get("/history")
async def list_history(user: User = _auth):
    """List all previous audit runs grouped by customer."""
    from app.core.config import get_audit_dir

    audit_dir = get_audit_dir()
    history: list[dict] = []

    if not audit_dir.exists():
        return {"history": history}

    # This listing is what hands out the paths /audit_data serves, so it has
    # to be scoped too — otherwise it stays a directory of every customer's
    # runs, and the guard downstream just turns enumeration into 403s.
    from app.core.rbac import check_audit_path_access

    for customer_dir in sorted(audit_dir.iterdir()):
        if not customer_dir.is_dir():
            continue
        if not await check_audit_path_access(user, customer_dir.name):
            continue
        customer_name = customer_dir.name.replace("_", " ")
        for run_dir in sorted(customer_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            txt_files = list(run_dir.glob("*.txt"))
            if not txt_files:
                continue
            has_metrics = (run_dir / "_audit_metrics.json").exists()
            metrics_summary = None
            if has_metrics:
                try:
                    from app.core.encryption import encrypted_read_json

                    m = encrypted_read_json(run_dir / "_audit_metrics.json")
                    metrics_summary = {
                        "risk_grade": m.get("risk_grade", ""),
                        "risk_score": m.get("risk_score", 0),
                        "mfa_coverage_pct": m.get("mfa_coverage_pct"),
                    }
                except Exception as e:
                    logger.debug("Failed to read audit metrics: %s", e)
            history.append(
                {
                    "customer": customer_name,
                    "timestamp": run_dir.name,
                    "path": str(run_dir),
                    "file_count": len(txt_files),
                    "has_metrics": has_metrics,
                    "metrics": metrics_summary,
                }
            )

    return {"history": history}


@router.post("/history/load")
async def load_history(request: Request, user: User = _auth):
    """Load a previous audit run into memory for report generation."""
    existing = state.get_user_audit(user.id)
    if existing is not None and existing.running:
        raise ConflictError(ui_t("err_audit_running", request))

    body = await request.json()
    run_path = Path(body.get("path", ""))

    if not run_path.exists() or not run_path.is_dir():
        raise NotFoundError(ui_t("err_invalid_path", request))

    from app.core.config import get_audit_dir

    try:
        run_path.resolve().relative_to(get_audit_dir().resolve())
    except ValueError:
        raise AuthError(ui_t("err_invalid_path", request)) from None

    from app.core.rbac import check_audit_path_access

    if not await check_audit_path_access(user, str(run_path)):
        raise ForbiddenError("Ingen tilgang til denne auditkjøringen")

    txt_files = sorted(run_path.glob("*.txt"))
    if not txt_files:
        raise ValidationError(ui_t("err_no_data_files", request))

    # Reconstruct results from files on disk
    # Group files by section number prefix (e.g. 01_, 02_, ...)
    section_map: dict[str, list[str]] = {}
    for f in txt_files:
        # Extract section prefix: "01_tenant.txt" -> "01"
        parts = f.name.split("_", 1)
        prefix = (
            parts[0]
            if parts[0].isdigit() or (len(parts[0]) >= 2 and parts[0][:2].isdigit())
            else "99"
        )
        # Normalize: 07b -> 07, 19c -> 19, etc.
        num = ""
        for ch in prefix:
            if ch.isdigit():
                num += ch
            else:
                break
        num = num or "99"
        section_map.setdefault(num, []).append(f.name)

    # Map section numbers to friendly names
    section_names = {
        "01": "Tenant Info",
        "02": "Licenses",
        "03": "Users",
        "04": "MFA Methods",
        "05": "Sign-in Activity",
        "06": "Groups",
        "07": "Admin Roles & PIM",
        "08": "Conditional Access",
        "09": "Secure Score & Auth",
        "10": "Intune Devices",
        "11": "Intune Compliance",
        "13": "Intune Apps",
        "14": "Intune Autopilot",
        "15": "SharePoint",
        "16": "Teams",
        "17": "Apps & OAuth",
        "18": "Identity Security",
        "19": "Defender & Purview",
        "20": "Exchange Mailboxes",
        "21": "Exchange Transport Rules",
        "22": "Exchange Connectors",
        "23": "Exchange Anti-Phish",
        "24": "Exchange Anti-Spam",
        "25": "Exchange DKIM",
        "26": "Email DNS (SPF/DMARC)",
        "27": "Exchange Defender Policies",
        "28": "Mailbox Forwarding",
        "29": "Inbox Rules",
    }

    results = []
    for num in sorted(section_map.keys()):
        files = section_map[num]
        name = section_names.get(num, f"Section {num}")
        warns = [f for f in files if "WARN" in f.upper()]
        results.append(
            {
                "name": name,
                "status": "done",
                "warns": warns,
                "files": files,
                "error": None,
            }
        )

    from app.core.customer import CustomerManager, customers_for_dir_name

    matches = customers_for_dir_name(run_path.parent.name)
    active_id = CustomerManager.get_active_id()
    active_match = next(
        (c.get("_id", "") for c in matches if c.get("_id", "") == active_id),
        "",
    )
    if active_match:
        customer_id = active_match
    elif len(matches) == 1:
        customer_id = matches[0].get("_id", "")
    else:
        raise ValidationError("Auditmappen kan ikke knyttes entydig til aktiv kunde")
    state.select_user_audit(
        user.id,
        customer_id,
        out_dir=run_path,
        results=results,
    )

    # Derive customer name from parent dir
    customer_name = run_path.parent.name.replace("_", " ")

    return {
        "ok": True,
        "customer": customer_name,
        "timestamp": run_path.name,
        "sections": len(results),
        "files": len(txt_files),
    }


# ── API: Delete audit runs ─────────────────────────────────────────────────────


@router.post("/history/delete")
async def delete_history_runs(request: Request, user: User = _auth):
    """Delete one or more audit runs by path."""
    import shutil

    from app.core.config import get_audit_dir

    body = await request.json()
    paths = body.get("paths", [])
    if not paths:
        raise ValidationError(ui_t("err_invalid_path", request))

    audit_dir = get_audit_dir()
    deleted = []
    errors = []

    from app.core.rbac import check_audit_path_access

    for p_str in paths:
        p = Path(p_str)
        # Security: ensure path is inside audit_dir
        try:
            rel = p.resolve().relative_to(audit_dir.resolve())
        except ValueError:
            errors.append(f"{p_str}: ugyldig sti")
            continue
        # Containment is not ownership. The equivalent archive route is
        # admin-only; this one deleted any customer's audit history for any
        # authenticated caller.
        if not await check_audit_path_access(user, str(rel)):
            errors.append(f"{p_str}: ingen tilgang")
            continue
        if not p.exists() or not p.is_dir():
            errors.append(f"{p_str}: finnes ikke")
            continue
        try:
            shutil.rmtree(str(p))
            deleted.append(p_str)
        except Exception as e:
            errors.append(f"{p_str}: {e}")

    # Log activity
    try:
        from app.core.activity_log import log_activity

        _user = getattr(getattr(request.state, "user", None), "username", "")
        log_activity(
            "history_deleted",
            detail=ui_t("log_history_deleted", request).format(count=len(deleted)),
            user=_user,
        )
    except Exception as e:
        logger.debug("Failed to log history deletion activity: %s", e)

    return {"ok": True, "deleted": len(deleted), "errors": errors}


@router.post("/history/delete-customer")
async def delete_customer_history(request: Request, user: User = _auth):
    """Delete ALL audit runs for a customer."""
    import shutil

    from app.core.config import get_audit_dir

    body = await request.json()
    customer_dir_name = body.get("customer_dir", "")
    if not customer_dir_name:
        raise ValidationError(ui_t("err_missing_customer_id", request))

    audit_dir = get_audit_dir()
    target = audit_dir / customer_dir_name

    # Security: ensure target is inside audit_dir
    try:
        target.resolve().relative_to(audit_dir.resolve())
    except ValueError:
        raise AuthError(ui_t("err_invalid_path", request)) from None

    from app.core.rbac import check_audit_path_access

    if not await check_audit_path_access(user, customer_dir_name):
        raise ForbiddenError("Du har ikke tilgang til denne kunden")

    if not target.exists() or not target.is_dir():
        raise NotFoundError(ui_t("err_customer_not_found", request))

    run_count = sum(1 for d in target.iterdir() if d.is_dir())

    try:
        shutil.rmtree(str(target))
    except Exception as e:
        logger.error("Failed to delete history for %s: %s", customer_dir_name, e)
        raise IntegrationError(ui_t("err_history_delete_failed", request)) from e

    try:
        from app.core.activity_log import log_activity

        _user = getattr(getattr(request.state, "user", None), "username", "")
        log_activity(
            "history_deleted",
            detail=ui_t("log_history_deleted_customer", request).format(
                count=run_count, customer=customer_dir_name.replace("_", " ")
            ),
            user=_user,
        )
    except Exception as e:
        logger.debug("Failed to log customer history deletion activity: %s", e)

    return {"ok": True, "deleted": run_count, "customer": customer_dir_name.replace("_", " ")}


# ── API: Audit comparison ──────────────────────────────────────────────────────


@router.get("/audit/compare")
async def compare_audits(run1: str, run2: str, user: User = _auth):
    """Compare metrics from two audit runs side-by-side."""
    from app.core.config import AUDIT_DIR
    from app.core.encryption import encrypted_read_json

    path1, path2 = Path(run1), Path(run2)

    from app.core.rbac import check_audit_path_access

    for p, label in [(path1, "run1"), (path2, "run2")]:
        if not p.exists() or not p.is_dir():
            raise NotFoundError(f"{label}: mappen finnes ikke")
        if not (p / "_audit_metrics.json").exists():
            raise ValidationError(f"{label}: ingen metrikk-data funnet")
        try:
            p.resolve().relative_to(AUDIT_DIR.resolve())
        except ValueError:
            raise AuthError(f"{label}: {ui_t('err_invalid_path')}") from None
        # Every other audit-tree route in this file calls this; compare_audits
        # was the lone exception, so any logged-in user could read any
        # customer's metrics by supplying the path.
        if not await check_audit_path_access(user, str(p)):
            raise ForbiddenError(f"{label}: Ingen tilgang til denne auditkjøringen")

    metrics1 = encrypted_read_json(path1 / "_audit_metrics.json")
    metrics2 = encrypted_read_json(path2 / "_audit_metrics.json")

    higher_is_better = {
        "mfa_coverage_pct",
        "secure_score_pct",
        "ca_policies_enabled",
        "intune_compliance_pct",
        "risk_score",
    }
    lower_is_better = {"users_no_mfa", "admin_roles_ga_count", "total_warns"}

    compare_keys = [
        "risk_score",
        "risk_grade",
        "mfa_coverage_pct",
        "secure_score_pct",
        "total_users",
        "users_no_mfa",
        "ca_policies_enabled",
        "intune_compliance_pct",
        "admin_roles_ga_count",
        "total_warns",
    ]

    deltas = []
    for key in compare_keys:
        v1 = metrics1.get(key)
        v2 = metrics2.get(key)
        entry = {"key": key, "run1": v1, "run2": v2}

        if key == "risk_grade":
            grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1, "F": 0}
            g1 = grade_order.get(str(v1).upper(), -1)
            g2 = grade_order.get(str(v2).upper(), -1)
            if g2 > g1:
                entry["direction"] = "improved"
            elif g2 < g1:
                entry["direction"] = "worsened"
            else:
                entry["direction"] = "unchanged"
            entry["delta"] = None
        elif isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            delta = v2 - v1
            entry["delta"] = round(delta, 2)
            if delta == 0:
                entry["direction"] = "unchanged"
            elif key in higher_is_better:
                entry["direction"] = "improved" if delta > 0 else "worsened"
            elif key in lower_is_better:
                entry["direction"] = "improved" if delta < 0 else "worsened"
            else:
                entry["direction"] = "changed"
        else:
            entry["delta"] = None
            entry["direction"] = "unchanged" if v1 == v2 else "changed"

        deltas.append(entry)

    return {
        "run1": {
            "path": str(path1),
            "timestamp": path1.name,
            "metrics": metrics1,
        },
        "run2": {
            "path": str(path2),
            "timestamp": path2.name,
            "metrics": metrics2,
        },
        "deltas": deltas,
    }
