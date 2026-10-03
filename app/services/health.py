"""Component readiness without exposing customer or integration payloads."""

import logging

from app.core.database import get_db

log = logging.getLogger(__name__)


async def component_health() -> dict:
    from app.core.config import get_scheduler_config
    from app.services import schedule_owner
    from app.services import scheduler as tasks
    from app.services.audit_scheduler import scheduler as audit

    components = {}
    try:
        async with get_db() as db, db.execute("SELECT 1") as cur:
            components["database"] = {"ready": (await cur.fetchone())[0] == 1}
    except Exception:
        log.warning("Database health probe failed", exc_info=True)
        components["database"] = {"ready": False}
    try:
        here = schedule_owner.owns()
        enabled = bool(get_scheduler_config().get("enabled"))
        statuses = tasks.get_status()
        if here:
            schedule = {"owner": "this", "ready": True}
        elif schedule_owner.owned_elsewhere():
            # Another process runs the jobs; its heartbeat is the evidence.
            age = schedule_owner.heartbeat_age()
            schedule = {
                "owner": "external",
                "ready": age is not None and age < schedule_owner.HEARTBEAT_STALE_SECONDS,
                "heartbeat_age_seconds": None if age is None else round(age),
            }
        else:
            # Nothing holds the lock: no process runs scheduled jobs. That only
            # matters if something is scheduled.
            nothing_scheduled = not enabled and not any(t["enabled"] for t in statuses)
            schedule = {"owner": None, "ready": nothing_scheduled}
        components["schedule"] = schedule
        components["audit_scheduler"] = {
            "enabled": enabled,
            "ready": not enabled or not here or audit.is_alive(),
        }
        for task in statuses:
            # Loop handles exist only in the owning process; elsewhere the
            # schedule component above stands in for them.
            handle = tasks._running_tasks.get(task["id"])
            alive = not here or bool(handle and not handle.done())
            ready = not task["enabled"] or (alive and not task["consecutive_failures"])
            components[task["id"]] = {
                "enabled": task["enabled"],
                "ready": ready,
                "last_run": task["last_run"],
                "last_success": task.get("last_success"),
                "next_run": task["next_run"],
                "consecutive_failures": task["consecutive_failures"],
            }
    except Exception:
        log.warning("Scheduler health probe failed", exc_info=True)
        components["schedule"] = {"ready": False}
    return {"ready": all(c["ready"] for c in components.values()), "components": components}
