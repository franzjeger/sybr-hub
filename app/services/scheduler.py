"""Task scheduler — periodic background jobs for Uniweb sync, FortiGate backup,
ALSO price refresh, and more.

Uses pure asyncio (no external dependencies).  Each task runs in its own
coroutine and sleeps until its next scheduled time.  Task configs are stored
in app settings under the ``"task_scheduler"`` key.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

# ── Defaults ───────────────────────────────────────────────────────────────

DEFAULT_TASKS: dict[str, dict[str, Any]] = {
    "uniweb_sync": {
        "enabled": True,
        "type": "daily",
        "time": "02:00",
        "label_no": "Uniweb-synkronisering",
        "label_en": "Uniweb sync",
    },
    "fortigate_backup": {
        "enabled": True,
        "type": "weekly",
        "day": "sunday",
        "time": "03:00",
        "label_no": "FortiGate-backup",
        "label_en": "FortiGate backup",
    },
    "also_price_refresh": {
        "enabled": True,
        "type": "daily",
        "time": "04:00",
        "label_no": "ALSO prisoppdatering",
        "label_en": "ALSO price refresh",
    },
    "alert_check": {
        "enabled": True,
        "type": "interval",
        "interval_hours": 6,
        "label_no": "Varselsjekk",
        "label_en": "Alert check",
    },
    "scheduled_reports": {
        "enabled": False,
        "type": "weekly",
        "day": "monday",
        "time": "07:00",
        "label_no": "Ukentlig rapport",
        "label_en": "Weekly report",
    },
    "health_snapshot": {
        "enabled": True,
        "type": "weekly",
        "day": "sunday",
        "time": "23:00",
        "label_no": "Helsescore-snapshot",
        "label_en": "Health score snapshot",
    },
    "db_cleanup": {
        "enabled": True,
        "type": "daily",
        "time": "01:00",
        "label_no": "Database-opprydding",
        "label_en": "Database cleanup",
    },
    "app_backup": {
        "enabled": False,  # Operator opts in; enable in Settings
        "type": "weekly",
        "day": "saturday",
        "time": "02:30",
        "label_no": "Automatisk backup",
        "label_en": "Automatic backup",
    },
    "cert_expiry_check": {
        "enabled": True,
        "type": "daily",
        "time": "06:00",
        "label_no": "Sertifikatutløp-sjekk",
        "label_en": "TLS certificate expiry check",
    },
}

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# ── Runtime state ──────────────────────────────────────────────────────────

_task_status: dict[str, dict] = {}
_running_tasks: dict[str, asyncio.Task] = {}
_MAX_CONSECUTIVE_FAILURES = 5
_BACKOFF_BASE_SECONDS = 60  # 1min, 2min, 4min, 8min, 16min


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _persist_task_status() -> None:
    """Save task status to app settings so it survives restarts."""
    try:
        from app.core.config import update_app_settings
        persist = {}
        for tid, st in _task_status.items():
            persist[tid] = {
                "last_run": st.get("last_run"),
                "last_result": st.get("last_result"),
                "last_error": st.get("last_error"),
                "consecutive_failures": st.get("consecutive_failures", 0),
            }
        update_app_settings(lambda s: s.__setitem__("task_scheduler_status", persist))
    except Exception as e:
        log.warning("Failed to persist task status: %s", e)


def _load_task_status() -> None:
    """Restore task status from app settings after restart."""
    try:
        from app.core.config import load_app_settings
        settings = load_app_settings()
        saved = settings.get("task_scheduler_status", {})
        for tid, st in saved.items():
            _task_status.setdefault(tid, {}).update(st)
    except Exception as e:
        log.warning("Failed to load task status: %s", e)


def _seconds_until(target_time: time, weekday: Optional[int] = None) -> float:
    """Return seconds from now until the next occurrence of *target_time*.

    If *weekday* is given (0=Mon … 6=Sun), find the next matching weekday.
    """
    now = _now()
    candidate = now.replace(
        hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0,
    )
    if weekday is not None:
        days_ahead = (weekday - now.weekday()) % 7
        candidate += timedelta(days=days_ahead)
        if candidate <= now:
            candidate += timedelta(days=7)
    else:
        if candidate <= now:
            candidate += timedelta(days=1)
    return (candidate - now).total_seconds()


# ── Config helpers ─────────────────────────────���───────────────────────────

def get_task_scheduler_config() -> dict[str, dict]:
    """Return merged task scheduler config (defaults + user overrides)."""
    from app.core.config import load_app_settings
    settings = load_app_settings()
    saved = settings.get("task_scheduler", {})
    merged: dict[str, dict] = {}
    for key, defaults in DEFAULT_TASKS.items():
        merged[key] = {**defaults}
        if key in saved:
            merged[key].update(saved[key])
    return merged


def save_task_scheduler_config(cfg: dict) -> None:
    from app.core.config import update_app_settings
    update_app_settings(lambda s: s.__setitem__("task_scheduler", cfg))


# ── Task implementations ──���───────────────────────────────────────────────

async def _do_uniweb_sync() -> str:
    """Run Uniweb sync (same logic as POST /api/uniweb/sync)."""
    from app.web.routes.uniweb import _get_uniweb_config, _run_sync
    cfg = _get_uniweb_config()
    if not cfg["email"] or not cfg["password"]:
        return "skipped — not configured"
    await _run_sync(cfg["email"], cfg["password"])
    return "ok"


async def _do_fortigate_backup() -> str:
    """Backup config for all customers with FortiGate configured."""
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager
    from app.services.fortigate_api import backup_config

    customers = CustomerManager.list_customers()
    backed_up = 0
    errors = 0
    for cust in customers:
        cid = cust.get("_id", "")
        host = cust.get("FortiGateHost", "")
        if not host or not cid:
            continue
        token = get_secret(cid, "fortigate_api_token")
        if not token:
            continue
        try:
            result = await backup_config(cust, token, cid)
            if result.get("ok"):
                backed_up += 1
            else:
                errors += 1
                log.warning("FortiGate backup failed for %s: %s", cust.get("CustomerName", cid), result.get("error"))
        except Exception as e:
            errors += 1
            log.warning("FortiGate backup exception for %s: %s", cust.get("CustomerName", cid), e)
    return f"{backed_up} backed up, {errors} errors"


async def _do_also_price_refresh() -> str:
    """Trigger ALSO price scan + renewal cache (same as scheduler._scan_also_renewals)."""
    from app.core.config import load_app_settings
    settings = load_app_settings()
    if not settings.get("also_password"):
        return "skipped — not configured"

    from app.core.customer import CustomerManager
    from app.core.database import get_db
    from app.integrations.also_cloud import AlsoCloudClient

    customers = CustomerManager.list_customers()
    linked = [c for c in customers if c.get("AlsoAccountId")]
    if not linked:
        return "skipped — no linked customers"

    client = AlsoCloudClient(
        settings.get("also_username", ""),
        settings.get("also_password", ""),
        settings.get("also_country", "no"),
    )

    scanned = 0
    for c in linked[:25]:
        account_id = str(c["AlsoAccountId"])
        try:
            subs = await client.get_subscriptions(account_id)
            if subs:
                from app.web.routes.also import _cache_renewals
                await _cache_renewals(account_id, subs)
            scanned += 1
        except Exception as e:
            log.warning("ALSO refresh failed for %s: %s", c.get("CustomerName"), e)
            if "403" in str(e) or "429" in str(e):
                break
        await asyncio.sleep(1.5)

    return f"{scanned}/{len(linked)} customers scanned"


async def _do_alert_check() -> str:
    """Run alert engine check + credential expiry webhook alerts."""
    # Use alert_engine if available
    try:
        from app.services.alert_engine import run_alert_check
        result = await run_alert_check()
        alerts_found = result.get("alerts_sent", 0) if isinstance(result, dict) else 0
    except ImportError:
        alerts_found = 0
    except Exception as e:
        log.warning("Alert engine check failed: %s", e)
        alerts_found = 0

    # Also run credential expiry check via audit scheduler
    try:
        from app.core.scheduler import scheduler as audit_scheduler
        await audit_scheduler._check_credential_expiry()
    except Exception as e:
        log.warning("Credential expiry check failed: %s", e)

    return f"ok — {alerts_found} alerts sent"


async def _do_scheduled_reports() -> str:
    """Generate and email reports for all customers with recent audit data."""
    from pathlib import Path

    from app.core.config import load_app_settings
    from app.core.credentials import load_config, save_config
    from app.core.customer import CustomerManager

    settings = load_app_settings()
    recipient = settings.get("email_default_recipient", "")
    smtp_server = settings.get("smtp_server", "")
    if not recipient or not smtp_server:
        return "skipped — email not configured"

    customers = CustomerManager.list_customers()
    sent = 0
    errors = 0

    for cust in customers:
        cid = cust.get("_id", "")
        name = cust.get("CustomerName", "Unknown")
        cust_dir = CustomerManager.get_customer_dir(cid)
        if not cust_dir.exists():
            continue

        # Find latest audit output directory
        audit_base = Path(settings.get("audit_dir", "audit_data"))
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        customer_audit_dirs = sorted(audit_base.glob(f"{safe_name}_*"), reverse=True)
        if not customer_audit_dirs:
            continue

        latest_dir = customer_audit_dirs[0]
        # Find PDF in the latest audit dir
        pdfs = list(latest_dir.glob("*.pdf")) + list(latest_dir.glob("*.pdf.enc"))
        if not pdfs:
            continue

        try:
            from app.core.email_sender import send_report_email

            subject = f"Sikkerhetsrapport — {name}"
            body = f"""<html><body style="font-family:sans-serif;">
            <h2>Ukentlig sikkerhetsrapport</h2>
            <p>Vedlagt finner du den siste sikkerhetsrapporten for <strong>{name}</strong>.</p>
            <p style="color:#666;font-size:12px;">Denne rapporten ble generert automatisk av SYBR MSP Toolkit.</p>
            </body></html>"""

            send_report_email(
                to=recipient,
                subject=subject,
                body_html=body,
                attachment_path=pdfs[0],
            )
            sent += 1
        except Exception as e:
            log.warning("Scheduled report email failed for %s: %s", name, e)
            errors += 1

    # Send Teams notification summary
    if sent > 0:
        try:
            from app.core.scheduler import scheduler
            webhook_url = settings.get("webhook_url") or (
                load_app_settings().get("scheduler", {}).get("webhook_url", "")
            )
            if webhook_url:
                import httpx
                card = {
                    "type": "message",
                    "attachments": [{
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": {
                            "type": "AdaptiveCard",
                            "version": "1.4",
                            "body": [{
                                "type": "TextBlock",
                                "text": f"📊 Ukentlig rapport sendt til {sent} kunder",
                                "weight": "Bolder",
                                "size": "Medium",
                            }, {
                                "type": "TextBlock",
                                "text": f"Mottaker: {recipient}" + (f" ({errors} feil)" if errors else ""),
                                "size": "Small",
                                "color": "Default" if not errors else "Attention",
                            }],
                        },
                    }],
                }
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(webhook_url, json=card)
        except Exception as e:
            log.warning("Report webhook notification failed: %s", e)

    return f"{sent} reports sent, {errors} errors"


async def _do_health_snapshot() -> str:
    """Snapshot current health scores for all customers into SQLite for trend charts."""
    from datetime import datetime, timezone

    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager
    from app.core.database import get_db
    from app.core.encryption import encrypted_read_json

    customers = CustomerManager.list_customers()
    audit_dir = get_audit_dir()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    saved = 0

    async with get_db() as db:
        for c in customers:
            cid = c.get("_id", "")
            name = c.get("CustomerName", "Unknown")
            safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
            customer_dir = audit_dir / safe_name
            if not customer_dir.exists():
                continue

            # Find latest metrics
            runs = sorted([d for d in customer_dir.iterdir() if d.is_dir()], reverse=True)
            for run_dir in runs:
                metrics_path = run_dir / "_audit_metrics.json"
                if metrics_path.exists():
                    try:
                        m = encrypted_read_json(metrics_path)
                        # Avoid duplicate snapshots for same day
                        existing = await db.execute(
                            "SELECT id FROM health_snapshots WHERE customer_id = ? AND snapshot_date = ?",
                            (cid, today),
                        )
                        if await existing.fetchone():
                            break
                        await db.execute(
                            """INSERT INTO health_snapshots
                               (customer_id, snapshot_date, risk_score, risk_grade,
                                mfa_pct, secure_score_pct, health_score, health_grade,
                                total_users, total_warns)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (cid, today,
                             m.get("risk_score"), m.get("risk_grade"),
                             m.get("mfa_coverage_pct"), m.get("secure_score_pct"),
                             None, None,  # health_score/grade computed separately
                             m.get("total_users", 0), m.get("total_warns", 0)),
                        )
                        saved += 1
                    except Exception as e:
                        log.warning("Health snapshot failed for %s: %s", name, e)
                    break
        await db.commit()

    return f"{saved} snapshots saved"


async def _do_db_cleanup() -> str:
    """Clean up expired sessions, old health snapshots, and stale audit metrics."""
    from app.core.auth import cleanup_expired_sessions
    from app.core.database import get_db

    # 1. Expired sessions
    expired = await cleanup_expired_sessions()

    # 2. Old health snapshots (keep last 365 days)
    trimmed = 0
    try:
        async with get_db() as db:
            cur = await db.execute(
                "DELETE FROM health_snapshots WHERE snapshot_date < date('now', '-365 days')"
            )
            trimmed = cur.rowcount
            await db.commit()
    except Exception as e:
        log.warning("Health snapshot cleanup failed: %s", e)

    # 3. Expired token-blacklist entries — they're irrelevant once the
    # token's exp timestamp has passed (the JWT is naturally invalid).
    bl_purged = 0
    try:
        from datetime import datetime, timezone
        async with get_db() as db:
            cur = await db.execute(
                "DELETE FROM token_blacklist WHERE expires_at < ?",
                (datetime.now(timezone.utc).isoformat(),),
            )
            bl_purged = cur.rowcount
            await db.commit()
    except Exception as e:
        log.warning("Token blacklist cleanup failed: %s", e)

    parts = []
    if expired:
        parts.append(f"{expired} expired sessions")
    if trimmed:
        parts.append(f"{trimmed} old snapshots")
    if bl_purged:
        parts.append(f"{bl_purged} expired blacklist entries")
    return f"cleaned: {', '.join(parts)}" if parts else "nothing to clean"


async def _do_app_backup() -> str:
    """Create an encrypted ZIP backup of the MSP Toolkit data + audit tree.

    Uses the same path resolution and manifest format as the UI-triggered
    ``/api/backup/create`` endpoint. Runs in an executor since the underlying
    routine is synchronous file I/O.
    """
    from app.web.routes.backup import create_backup_sync

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: create_backup_sync())
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "backup failed"))
    path = result.get("path", "")
    size_mb = 0.0
    try:
        from pathlib import Path as _P
        if path:
            size_mb = round(_P(path).stat().st_size / 1048576, 1)
    except Exception:
        pass
    return f"ok — {path} ({size_mb} MB)"


async def _do_cert_expiry_check() -> str:
    """Warn when Tailscale TLS certs are close to expiry or have expired.

    Logs WARNING at 30/7/1 days remaining and ERROR after expiry so operators
    see it in Settings → Aktivitetslogg and the rotating log file. Does not
    page externally — wire a webhook here if alerting is wanted.
    """
    from datetime import datetime as _dt
    from datetime import timezone as _tz
    from pathlib import Path as _P

    cert_path = _P("/etc/ssl/tailscale.crt")
    if not cert_path.exists():
        return "skipped — no Tailscale cert"

    try:
        from cryptography import x509
        raw = cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(raw)
        not_after = cert.not_valid_after_utc
        now = _dt.now(_tz.utc)
        remaining = (not_after - now).total_seconds() / 86400
    except Exception as e:
        log.warning("Could not parse %s: %s", cert_path, e)
        return f"error — {e}"

    if remaining < 0:
        log.error(
            "TLS certificate EXPIRED %.1f days ago (%s) — run `tailscale cert`",
            -remaining, not_after.isoformat(),
        )
        return f"expired {abs(int(remaining))} days ago"
    if remaining < 1:
        log.warning("TLS certificate expires in <1 day (%s)", not_after.isoformat())
    elif remaining < 7:
        log.warning("TLS certificate expires in %.0f days (%s)", remaining, not_after.isoformat())
    elif remaining < 30:
        log.info("TLS certificate expires in %.0f days (%s)", remaining, not_after.isoformat())
    return f"{int(remaining)} days remaining"


_TASK_RUNNERS = {
    "uniweb_sync": _do_uniweb_sync,
    "fortigate_backup": _do_fortigate_backup,
    "also_price_refresh": _do_also_price_refresh,
    "alert_check": _do_alert_check,
    "scheduled_reports": _do_scheduled_reports,
    "health_snapshot": _do_health_snapshot,
    "db_cleanup": _do_db_cleanup,
    "app_backup": _do_app_backup,
    "cert_expiry_check": _do_cert_expiry_check,
}


# ── Task loop ────��───────────────────────────��────────────────────────────

def _compute_next_run(task_cfg: dict) -> datetime:
    """Compute the next run time for a task and return it as a UTC datetime."""
    now = _now()
    task_type = task_cfg.get("type", "daily")

    if task_type == "interval":
        hours = task_cfg.get("interval_hours", 6)
        return now + timedelta(hours=hours)

    # Parse target time
    time_str = task_cfg.get("time", "02:00")
    parts = time_str.split(":")
    target = time(int(parts[0]), int(parts[1]))

    if task_type == "weekly":
        day_name = task_cfg.get("day", "sunday").lower()
        weekday = _WEEKDAYS.get(day_name, 6)
        secs = _seconds_until(target, weekday)
    else:  # daily
        secs = _seconds_until(target)

    return now + timedelta(seconds=secs)


async def _task_loop(task_id: str) -> None:
    """Sleep-loop for a single scheduled task."""
    while True:
        cfg = get_task_scheduler_config()
        task_cfg = cfg.get(task_id, {})
        if not task_cfg.get("enabled", False):
            log.info("Task %s disabled — stopping loop", task_id)
            _task_status.setdefault(task_id, {})["running"] = False
            return

        next_run = _compute_next_run(task_cfg)
        _task_status.setdefault(task_id, {})["next_run"] = next_run.isoformat()
        _task_status[task_id]["running"] = True

        sleep_secs = max((next_run - _now()).total_seconds(), 5)
        log.info("Task %s sleeping %.0fs until %s", task_id, sleep_secs, next_run.isoformat())

        try:
            await asyncio.sleep(sleep_secs)
        except asyncio.CancelledError:
            _task_status[task_id]["running"] = False
            return

        # Execute
        runner = _TASK_RUNNERS.get(task_id)
        if not runner:
            log.warning("No runner for task %s", task_id)
            continue

        start = _now()
        _task_status[task_id]["last_start"] = start.isoformat()
        try:
            result = await runner()
            _task_status[task_id]["last_run"] = start.isoformat()
            _task_status[task_id]["last_result"] = result
            _task_status[task_id]["last_error"] = None
            _task_status[task_id]["consecutive_failures"] = 0
            log.info("Task %s completed: %s", task_id, result)
            _persist_task_status()

            try:
                from app.core.activity_log import log_activity
                log_activity(
                    action=f"task_{task_id}",
                    detail=f"Scheduled task completed: {result}",
                    user="task_scheduler",
                )
            except Exception as e:
                log.debug("Activity log write failed: %s", e)

        except asyncio.CancelledError:
            _task_status[task_id]["running"] = False
            return
        except Exception as e:
            failures = _task_status[task_id].get("consecutive_failures", 0) + 1
            _task_status[task_id]["last_run"] = start.isoformat()
            _task_status[task_id]["last_result"] = None
            _task_status[task_id]["last_error"] = str(e)
            _task_status[task_id]["consecutive_failures"] = failures
            log.error("Task %s failed (%d/%d): %s", task_id, failures, _MAX_CONSECUTIVE_FAILURES, e)
            _persist_task_status()

            if failures >= _MAX_CONSECUTIVE_FAILURES:
                log.error("Task %s disabled after %d consecutive failures", task_id, failures)
                _task_status[task_id]["running"] = False
                try:
                    from app.core.activity_log import log_activity
                    log_activity(
                        action=f"task_{task_id}_disabled",
                        detail=f"Auto-disabled after {failures} consecutive failures: {e}",
                        user="task_scheduler",
                    )
                except Exception as e2:
                    log.debug("Activity log write failed: %s", e2)
                # Page the operator via the configured webhook so a silent
                # task death doesn't go unnoticed.
                await _notify_task_failure(task_id, failures, str(e))
                return

            # Exponential backoff before next attempt
            backoff = min(_BACKOFF_BASE_SECONDS * (2 ** (failures - 1)), 3600)
            log.info("Task %s backing off %ds before next attempt", task_id, backoff)
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                _task_status[task_id]["running"] = False
                return


async def _notify_task_failure(task_id: str, failures: int, error: str) -> None:
    """Post a Teams-style adaptive card to the configured webhook so the
    operator sees that a scheduled task has been auto-disabled.

    Best-effort — webhook unavailability never propagates back into the
    scheduler. The card uses the same MessageCard format as
    _do_scheduled_reports above so existing receivers don't need new code.
    """
    try:
        from app.core.config import load_app_settings
        settings = load_app_settings()
        webhook_url = (
            settings.get("webhook_url")
            or settings.get("scheduler", {}).get("webhook_url", "")
        )
        if not webhook_url:
            return

        cfg = get_task_scheduler_config().get(task_id, {})
        label = cfg.get("label_no") or cfg.get("label_en") or task_id

        import httpx
        card = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {"type": "TextBlock", "text": "\u26A0 MSP Toolkit \u2014 task auto-disabled",
                         "weight": "Bolder", "size": "Medium", "color": "Attention"},
                        {"type": "TextBlock", "text": f"{label} ({task_id})",
                         "weight": "Bolder"},
                        {"type": "TextBlock", "text": f"Failed {failures}\u00d7 in a row.",
                         "wrap": True, "size": "Small"},
                        {"type": "TextBlock", "text": f"Last error: {error[:300]}",
                         "wrap": True, "size": "Small", "color": "Default"},
                        {"type": "TextBlock",
                         "text": "Re-enable in Settings \u2192 Scheduler when fixed.",
                         "wrap": True, "size": "Small", "color": "Accent"},
                    ],
                },
            }],
        }
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(webhook_url, json=card)
        log.info("Failure webhook posted for task %s", task_id)
    except Exception as e:
        log.warning("Failure webhook failed for task %s: %s", task_id, e)


# Public API

def start_all() -> None:
    """Start loops for all enabled tasks.  Idempotent — skips already-running."""
    _load_task_status()
    cfg = get_task_scheduler_config()
    for task_id, task_cfg in cfg.items():
        if not task_cfg.get("enabled", False):
            continue
        if task_id in _running_tasks and not _running_tasks[task_id].done():
            continue
        _running_tasks[task_id] = asyncio.create_task(_task_loop(task_id))
        _task_status.setdefault(task_id, {})["running"] = True
        log.info("Scheduled task started: %s", task_id)


def stop_all() -> None:
    """Cancel all running task loops."""
    for task_id, task in list(_running_tasks.items()):
        if not task.done():
            task.cancel()
        _task_status.setdefault(task_id, {})["running"] = False
    _running_tasks.clear()


def restart_task(task_id: str) -> None:
    """Restart a single task loop (e.g. after config change)."""
    if task_id in _running_tasks:
        t = _running_tasks[task_id]
        if not t.done():
            t.cancel()
    cfg = get_task_scheduler_config()
    task_cfg = cfg.get(task_id, {})
    if task_cfg.get("enabled", False):
        _running_tasks[task_id] = asyncio.create_task(_task_loop(task_id))
        _task_status.setdefault(task_id, {})["running"] = True


async def run_now(task_id: str) -> dict:
    """Execute a task immediately (on-demand).  Returns result dict."""
    runner = _TASK_RUNNERS.get(task_id)
    if not runner:
        return {"ok": False, "error": f"Unknown task: {task_id}"}
    start = _now()
    _task_status.setdefault(task_id, {})["last_start"] = start.isoformat()
    try:
        result = await runner()
        _task_status[task_id]["last_run"] = start.isoformat()
        _task_status[task_id]["last_result"] = result
        _task_status[task_id]["last_error"] = None
        try:
            from app.core.activity_log import log_activity
            log_activity(
                action=f"task_{task_id}_manual",
                detail=f"Manual run: {result}",
                user="task_scheduler",
            )
        except Exception as e:
            log.debug("Activity log write failed: %s", e)
        return {"ok": True, "result": result}
    except Exception as e:
        _task_status[task_id]["last_run"] = start.isoformat()
        _task_status[task_id]["last_result"] = None
        _task_status[task_id]["last_error"] = str(e)
        return {"ok": False, "error": str(e)}


def get_status() -> list[dict]:
    """Return status for all tasks, suitable for the API response."""
    cfg = get_task_scheduler_config()
    out: list[dict] = []
    for task_id, task_cfg in cfg.items():
        st = _task_status.get(task_id, {})

        # Build human-readable schedule string
        task_type = task_cfg.get("type", "daily")
        if task_type == "interval":
            schedule = f"every {task_cfg.get('interval_hours', 6)}h"
        elif task_type == "weekly":
            schedule = f"{task_cfg.get('day', 'sunday')} {task_cfg.get('time', '03:00')}"
        else:
            schedule = f"daily {task_cfg.get('time', '02:00')}"

        out.append({
            "id": task_id,
            "label_no": task_cfg.get("label_no", task_id),
            "label_en": task_cfg.get("label_en", task_id),
            "enabled": task_cfg.get("enabled", False),
            "schedule": schedule,
            "type": task_type,
            "time": task_cfg.get("time", ""),
            "day": task_cfg.get("day", ""),
            "interval_hours": task_cfg.get("interval_hours", 0),
            "last_run": st.get("last_run"),
            "next_run": st.get("next_run"),
            "last_result": st.get("last_result"),
            "last_error": st.get("last_error"),
            "running": st.get("running", False),
            "consecutive_failures": st.get("consecutive_failures", 0),
        })
    return out
