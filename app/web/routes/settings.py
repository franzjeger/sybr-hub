"""Settings, scheduler, encryption, and activity-log endpoints."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.settings import (
    LanguageChoice,
    SchedulerConfig,
    TaskSchedule,
    WebhookTest,
)
from app.models.user import Role, User
from app.web.i18n import ui_t
from app.web.middleware.auth import get_current_user, require_role

_auth = Depends(get_current_user)
_admin = Depends(require_role(Role.admin))

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_fortigate_configured() -> bool:
    """Check if any customer has a FortiGate host configured."""
    try:
        from app.core.customer import CustomerManager
        for c in CustomerManager.list_customers():
            if c.get("FortiGateHost"):
                return True
    except Exception as e:
        logger.debug("Failed to check FortiGate configuration: %s", e)
    return False


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(user: User = _auth):
    from app.core.config import (
        _DEFAULT_AUDIT_DIR,
        CERTS_DIR,
        get_audit_dir,
        get_branding,
        get_cert_dir,
        load_app_settings,
    )
    settings = load_app_settings()
    return {
        "audit_dir":         str(get_audit_dir()),
        "audit_dir_default": str(_DEFAULT_AUDIT_DIR),
        "audit_dir_custom":  settings.get("audit_dir", ""),
        "cert_dir":          str(get_cert_dir()),
        "cert_dir_default":  str(CERTS_DIR),
        "cert_dir_custom":   settings.get("cert_dir", ""),
        "branding":          get_branding(),
        "itglue_api_key":    "••••••" if settings.get("itglue_api_key") else "",
        "itglue_api_key_set": bool(settings.get("itglue_api_key")),
        "itglue_region":     settings.get("itglue_region", "eu"),
        "smtp_server":       settings.get("smtp_server", ""),
        "smtp_port":         settings.get("smtp_port", 587),
        "smtp_user":         settings.get("smtp_user", ""),
        "smtp_password":     "••••••" if settings.get("smtp_password") else "",
        "smtp_password_set": bool(settings.get("smtp_password")),
        "smtp_from":         settings.get("smtp_from", ""),
        "email_auto_send":   settings.get("email_auto_send", False),
        "email_default_recipient": settings.get("email_default_recipient", ""),
        "unifi_site_manager_api_key": "••••••" if settings.get("unifi_site_manager_api_key") else "",
        "unifi_site_manager_api_key_set": bool(settings.get("unifi_site_manager_api_key")),
        "fortigate_configured": _check_fortigate_configured(),
        "also_username": settings.get("also_username", ""),
        "also_password": "••••••" if settings.get("also_password") else "",
        "also_password_set": bool(settings.get("also_password")),
        "also_country": settings.get("also_country", "no"),
        "autotask_integration_code": "••••••" if settings.get("autotask_integration_code") else "",
        "autotask_integration_code_set": bool(settings.get("autotask_integration_code")),
        "autotask_username": settings.get("autotask_username", ""),
        "autotask_secret": "••••••" if settings.get("autotask_secret") else "",
        "autotask_secret_set": bool(settings.get("autotask_secret")),
        "autotask_zone_url": settings.get("autotask_zone_url", ""),
        # Ticket defaults. Not secrets — these are picklist numbers the
        # operator has to be able to see to know what a new ticket will get.
        "autotask_default_queue_id": settings.get("autotask_default_queue_id"),
        "autotask_default_priority": settings.get("autotask_default_priority", 2),
        "autotask_default_status": settings.get("autotask_default_status", 1),
        "tailscale_api_key": "••••••" if settings.get("tailscale_api_key") else "",
        "tailscale_api_key_set": bool(settings.get("tailscale_api_key")),
        "tailscale_tailnet": settings.get("tailscale_tailnet", "-"),
        "uniweb_email": settings.get("uniweb_email", ""),
        "uniweb_password": "••••••" if settings.get("uniweb_password") else "",
        "uniweb_password_set": bool(settings.get("uniweb_password")),
        # GDAP / Partner Center
        **_gdap_settings(),
    }


def _gdap_settings() -> dict:
    """Return GDAP-related settings for the settings endpoint."""
    from app.core.credentials import gdap_configured, get_secret, load_gdap_config
    gdap_cfg = load_gdap_config() or {}
    return {
        # "configured" means the credentials are present, which is the right
        # precondition for the API routes. It is not the same claim as "these
        # credentials work", and the card used to paint the first as if it
        # were the second.
        "gdap_configured": gdap_configured(),
        # True, False, or null — and null is not False. A config written
        # before this field existed says nothing about whether the credentials
        # work, and painting it as broken would be the same overclaim in the
        # other direction.
        "gdap_validated": gdap_cfg.get("validated"),
        "gdap_validated_at": gdap_cfg.get("validated_at", ""),
        "gdap_validation_error": gdap_cfg.get("validation_error", ""),
        "gdap_partner_tenant_id": gdap_cfg.get("partner_tenant_id", ""),
        "gdap_client_id": gdap_cfg.get("client_id", ""),
        "gdap_client_secret_set": bool(get_secret("gdap", "partner_client_secret")),
        "gdap_app_display_name": gdap_cfg.get("app_display_name", ""),
        "gdap_setup_date": gdap_cfg.get("setup_date", ""),
        "gdap_last_customer_sync": gdap_cfg.get("last_customer_sync", ""),
        "gdap_customer_count": gdap_cfg.get("customer_count", 0),
    }


@router.post("/settings")
async def save_settings(request: Request, user: User = _admin):
    from app.core.config import DATA_DIR, get_audit_dir, load_app_settings, save_app_settings
    body = await request.json()
    settings = load_app_settings()

    # Path traversal protection — only allow dirs under home or DATA_DIR
    _allowed_parents = (Path.home(), DATA_DIR)

    def _is_safe_path(p: Path) -> bool:
        resolved = p.resolve()
        return any(resolved == ap or ap in resolved.parents for ap in _allowed_parents)

    new_dir = body.get("audit_dir", "").strip()
    if new_dir:
        p = Path(new_dir)
        if not _is_safe_path(p):
            raise ValidationError("Directory must be under home or data directory")
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("Cannot create audit dir %s: %s", new_dir, e)
            raise ValidationError(ui_t('err_cannot_create_dir', request))
        settings["audit_dir"] = str(p)
    else:
        settings.pop("audit_dir", None)  # reset to default

    new_cert_dir = body.get("cert_dir", "").strip()
    if new_cert_dir:
        cp = Path(new_cert_dir)
        if not _is_safe_path(cp):
            raise ValidationError("Directory must be under home or data directory")
        try:
            cp.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("Cannot create cert dir %s: %s", new_cert_dir, e)
            raise ValidationError(ui_t('err_cannot_create_cert_dir', request))
        settings["cert_dir"] = str(cp)
    else:
        settings.pop("cert_dir", None)  # reset to default

    branding = body.get("branding")
    if branding and isinstance(branding, dict):
        settings["branding"] = branding

    # IT Glue settings — skip masked placeholder
    itglue_key = body.get("itglue_api_key", "").strip()
    if itglue_key and itglue_key != "••••••":
        settings["itglue_api_key"] = itglue_key
    itglue_region = body.get("itglue_region", "").strip()
    if itglue_region:
        settings["itglue_region"] = itglue_region

    # UniFi Site Manager API key — skip masked placeholder
    unifi_sm_key = body.get("unifi_site_manager_api_key", "").strip()
    if unifi_sm_key and unifi_sm_key != "••••••":
        settings["unifi_site_manager_api_key"] = unifi_sm_key

    # UniFi Controller direct access
    for key in ("unifi_controller_host", "unifi_controller_username", "unifi_controller_password"):
        val = body.get(key, "")
        if isinstance(val, str):
            val = val.strip()
        if val:
            settings[key] = val

    # ALSO Cloud Marketplace
    for key in ("also_username", "also_password", "also_country"):
        val = body.get(key, "")
        if isinstance(val, str):
            val = val.strip()
        if key == "also_password" and val == "••••••":
            continue
        if val:
            settings[key] = val

    # Autotask PSA — the two secrets keep their masked placeholder out of
    # storage, the same way ALSO's password does above.
    for key in (
        "autotask_integration_code", "autotask_username",
        "autotask_secret", "autotask_zone_url",
    ):
        val = body.get(key, "")
        if isinstance(val, str):
            val = val.strip()
        if key in ("autotask_integration_code", "autotask_secret") and val == "••••••":
            continue
        if val:
            settings[key] = val

    # Autotask ticket defaults. Status and priority are picklists, so a
    # customised instance numbers them differently and the write side must not
    # assume the stock values. Stored as ints and validated here rather than
    # discovered as a 400 from Autotask at the moment a technician clicks.
    for key, low, high in (
        ("autotask_default_queue_id", 1, 2_147_483_647),
        ("autotask_default_priority", 1, 4),
        ("autotask_default_status", 1, 255),
    ):
        if key not in body:
            continue
        raw = body[key]
        if raw in (None, ""):
            settings.pop(key, None)
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{key} må være et tall") from exc
        if not low <= value <= high:
            raise ValidationError(f"{key} må være mellom {low} og {high}")
        settings[key] = value

    # Tailscale
    ts_key = body.get("tailscale_api_key", "").strip()
    if ts_key and ts_key != "••••••":
        settings["tailscale_api_key"] = ts_key
    ts_tailnet = body.get("tailscale_tailnet", "").strip()
    if ts_tailnet:
        settings["tailscale_tailnet"] = ts_tailnet

    # Uniweb hosting provider
    for key in ("uniweb_email", "uniweb_password"):
        val = body.get(key, "")
        if isinstance(val, str):
            val = val.strip()
        if key == "uniweb_password" and val == "••••••":
            continue
        if val:
            settings[key] = val

    # Email / SMTP settings — skip masked placeholder for password
    for key in ("smtp_server", "smtp_user", "smtp_password", "smtp_from", "email_default_recipient"):
        val = body.get(key, "")
        if isinstance(val, str):
            val = val.strip()
        if key == "smtp_password" and val == "••••••":
            continue  # Keep existing password
        if val:
            settings[key] = val
        else:
            settings.pop(key, None)
    if "smtp_port" in body:
        settings["smtp_port"] = int(body["smtp_port"])
    settings["email_auto_send"] = bool(body.get("email_auto_send", False))

    save_app_settings(settings)

    from app.core.activity_log import log_activity as _log_act
    _log_act("settings_changed")

    from app.core.config import get_cert_dir
    return {"ok": True, "audit_dir": str(get_audit_dir()), "cert_dir": str(get_cert_dir())}


# ── Logo upload ───────────────────────────────────────────────────────────────

@router.post("/settings/logo")
async def upload_logo(file: UploadFile = File(...), user: User = _admin):
    """Accept a logo image upload and store it in CONFIG_DIR/branding/logo.png."""
    from app.core.config import BRANDING_DIR, LOGO_PATH
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    allowed = (".png", ".jpg", ".jpeg", ".svg")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed:
        raise ValidationError(ui_t("err_invalid_file_type"))
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise ValidationError(ui_t("err_file_too_large"))
    LOGO_PATH.write_bytes(data)
    return {"ok": True}


@router.get("/settings/logo")
async def get_logo():
    """Serve the current custom logo, or 404 if none.

    Public — the logo is shown on the login screen before any session
    exists. The middleware already allows /api/settings/logo; this route
    previously re-required auth via ``user: User = _auth``, causing a
    401 loop on the unauthenticated login page.
    """
    from app.core.config import LOGO_PATH
    if LOGO_PATH.exists():
        return FileResponse(LOGO_PATH, media_type="image/png")
    raise NotFoundError(ui_t("err_no_logo"))


# ── Language settings ─────────────────────────────────────────────────────────

@router.get("/settings/language")
async def get_language(user: User = _auth):
    from app.core.config import load_app_settings
    settings = load_app_settings()
    return {"language": settings.get("ui_language", "no")}


@router.post("/settings/language")
async def set_language(body: LanguageChoice, user: User = _admin):
    from app.core.config import load_app_settings, save_app_settings
    lang = body.language
    settings = load_app_settings()
    settings["ui_language"] = lang
    save_app_settings(settings)
    return {"ok": True, "language": lang}


# ── Scheduler ─────────────────────────────────────────────────────────────────

@router.get("/scheduler")
async def get_scheduler(user: User = _auth):
    from app.core.config import get_scheduler_config
    return get_scheduler_config()


@router.post("/scheduler")
async def update_scheduler(body: SchedulerConfig, user: User = _admin):
    """Replace the scheduler block.

    Takes a model rather than the raw body. This used to be
    ``settings["scheduler"] = await request.json()`` — a JSON list made
    ``body.get("enabled")`` raise and answered 500, and any object at all was
    persisted under a key the scheduler reads on every tick.
    """
    from app.core.config import load_app_settings, save_app_settings
    settings = load_app_settings()
    settings["scheduler"] = body.model_dump()
    save_app_settings(settings)

    # Restart scheduler with new config
    from app.core.scheduler import scheduler
    scheduler.stop()
    if body.enabled:
        scheduler.start()

    from app.core.activity_log import log_activity
    log_activity(
        "scheduler_updated",
        detail=f"Scheduler {'aktivert' if body.enabled else 'deaktivert'}",
    )

    return {"ok": True}


@router.post("/scheduler/test-webhook")
async def test_webhook(body: WebhookTest, request: Request, user: User = _admin):
    url = body.webhook_url

    from app.core.scheduler import AuditScheduler
    s = AuditScheduler()
    # Temporarily override webhook URL for test
    from app.core.config import load_app_settings, save_app_settings
    settings = load_app_settings()
    old = settings.get("scheduler", {}).get("webhook_url", "")
    settings.setdefault("scheduler", {})["webhook_url"] = url
    save_app_settings(settings)

    try:
        await s._send_webhook("\U0001f9ea Testmelding fra SYBR MSP Toolkit — webhook fungerer!")
        return {"ok": True}
    except Exception as e:
        logger.warning("Webhook test failed: %s", e)
        raise IntegrationError("Webhook-test feilet")
    finally:
        settings["scheduler"]["webhook_url"] = old
        save_app_settings(settings)


# ── Task Scheduler ────────────────────────────────────────────────────────────

@router.get("/scheduler/tasks")
async def get_task_scheduler_status(user: User = _auth):
    """List all scheduled tasks with next run, last run, status."""
    from app.services.scheduler import get_status
    return {"tasks": get_status()}


@router.post("/scheduler/tasks/config")
async def update_task_scheduler_config(request: Request, user: User = _admin):
    """Update schedule settings for one or more tasks."""
    from app.services.scheduler import (
        get_task_scheduler_config,
        restart_task,
        save_task_scheduler_config,
    )
    body = await request.json()
    if not isinstance(body, dict):
        raise ValidationError("Forventet et objekt med oppgave-ID som nøkkel")
    cfg = get_task_scheduler_config()

    # Body is {"task_id": {"enabled": bool, "time": "HH:MM", ...}}. Each value
    # is validated rather than copied: `time` reaches a scheduler that parses
    # it, and an unparseable one used to be accepted here and fail later where
    # nothing connected it back to this request.
    for task_id, updates in body.items():
        if task_id not in cfg:
            continue
        if not isinstance(updates, dict):
            continue
        try:
            schedule = TaskSchedule.model_validate(updates)
        except PydanticValidationError as exc:
            raise ValidationError(
                f"Ugyldig oppsett for oppgaven {task_id!r}"
            ) from exc
        for key, value in schedule.model_dump(exclude_none=True).items():
            cfg[task_id][key] = value
        save_task_scheduler_config(cfg)
        restart_task(task_id)

    from app.core.activity_log import log_activity as _log_act
    _log_act("task_scheduler_updated", detail="Task scheduler config updated", user="admin")

    return {"ok": True}


@router.post("/scheduler/tasks/{task_id}/run")
async def run_task_now(task_id: str, user: User = _admin):
    """Execute a scheduled task immediately."""
    from app.services.scheduler import run_now
    result = await run_now(task_id)
    return result


# ── Encryption ────────────────────────────────────────────────────────────────

@router.post("/encrypt/migrate")
async def migrate_encryption(user: User = _admin):
    """Encrypt all existing plaintext customer data."""
    from app.core.config import AUDIT_DIR
    from app.core.customer import CustomerManager
    from app.core.encryption import migrate_encrypt_directory
    count = 0
    # Encrypt customer configs
    customers_dir = Path(CustomerManager.get_customer_dir("")).parent
    if customers_dir.exists():
        count += migrate_encrypt_directory(customers_dir)
    # Encrypt audit data
    count += migrate_encrypt_directory(AUDIT_DIR)
    return {"ok": True, "files_encrypted": count}


@router.get("/encryption/key-backup")
async def backup_encryption_key(user: User = _admin):
    """Return the master encryption key for backup purposes."""
    from app.core.encryption import export_master_key
    try:
        key = export_master_key()
        from app.core.activity_log import log_activity
        log_activity("encryption_key_exported", detail="Master encryption key exported for backup")
        return {"ok": True, "key": key}
    except Exception as e:
        logger.error("Encryption key backup failed: %s", e)
        raise IntegrationError("Kunne ikke eksportere krypteringsnøkkel")


@router.post("/encryption/key-restore")
async def restore_encryption_key(request: Request, user: User = _admin):
    """Restore a master encryption key from backup."""
    from app.core.encryption import import_master_key
    body = await request.json()
    b64_key = body.get("key", "").strip()
    if not b64_key:
        raise ValidationError(ui_t("err_no_key_provided", request))
    if import_master_key(b64_key):
        from app.core.activity_log import log_activity
        log_activity("encryption_key_restored", detail="Master encryption key restored from backup")
        return {"ok": True}
    raise ValidationError(ui_t("err_invalid_key", request))


# ── Activity log ──────────────────────────────────────────────────────────────

@router.get("/activity-log")
async def get_activity_log_endpoint(user: User = _auth, limit: int = 50, offset: int = 0, customer: str = ""):
    from app.core.activity_log import get_activity_log as _get_log
    entries = _get_log(limit=limit, offset=offset, customer=customer)
    return {"entries": entries}


# ── Automatic alerts ─────────────────────────────────────────────────────────

@router.get("/alerts/config")
async def get_alerts_config(user: User = _auth):
    from app.services.alert_engine import get_alert_config
    return get_alert_config()


@router.post("/alerts/config")
async def save_alerts_config(request: Request, user: User = _admin):
    from app.services.alert_engine import get_alert_config, save_alert_config
    body = await request.json()
    # Merge incoming with defaults to preserve structure
    config = get_alert_config()
    for key in ("enabled", "notify_teams", "notify_email", "email_recipient"):
        if key in body:
            config[key] = body[key]
    if "rules" in body and isinstance(body["rules"], dict):
        for rk, rv in body["rules"].items():
            if rk in config["rules"] and isinstance(rv, dict):
                config["rules"][rk].update(rv)
    save_alert_config(config)

    from app.core.activity_log import log_activity
    log_activity("alert_config_changed", detail=f"Alerts {'enabled' if config.get('enabled') else 'disabled'}")

    return {"ok": True}


@router.post("/alerts/check-now")
async def alerts_check_now(user: User = _admin):
    from app.services.alert_engine import run_alert_check
    result = await run_alert_check()
    return result


@router.get("/alerts/history")
async def alerts_history(user: User = _auth, limit: int = Query(default=100, le=500)):
    from app.services.alert_engine import get_alert_history
    entries = get_alert_history(limit=limit)
    return {"entries": entries, "total": len(entries)}
