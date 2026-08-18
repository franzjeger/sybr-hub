"""Audit-related API endpoints — extracted from server.py."""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.user import Role, User
from app.web import state
from app.web.i18n import ui_t
from app.web.middleware.auth import get_current_user, require_customer_access, require_role

logger = logging.getLogger(__name__)

router = APIRouter()

_BUILTIN_PRESETS = {
    "Full Audit": None,  # None means all sections — resolved at request time
    "Quick Scan": [
        "MFA Methods",
        "Conditional Access",
        "Admin Roles",
        "Secure Score",
        "DNS / Email Security",
    ],
    "Identity Only": [
        "Users",
        "MFA Methods",
        "Conditional Access",
        "Admin Roles",
        "Groups",
        "Privileged Identity Management",
    ],
}


class _ProgressTracker:
    """Counts audit sections towards a total the run may turn out to exceed.

    The denominator is an estimate: it is fixed before the run from the
    selected section names, while the numerator comes from whatever the
    collector actually reports. The two disagreed and the bar read "21 / 18".

    Two rules keep the ratio honest. Sections are counted by name, so a
    section that reaches a terminal state more than once — the Azure sections
    run once per subscription under a single name — is still one section. And
    if the count exceeds the estimate anyway, the estimate is what was wrong,
    so it widens.
    """

    def __init__(self, sections_filter: set[str] | None = None):
        from app.modules.m365_audit.collector import AuditCollector

        all_sections = AuditCollector.GRAPH_SECTION_NAMES + AuditCollector.AZURE_SECTION_NAMES
        if sections_filter:
            self.total = sum(1 for s in all_sections if s in sections_filter)
        else:
            self.total = len(all_sections)
        self._done: set[str] = set()
        self._current = ""

    def record(self, name: str, status) -> dict:
        from app.modules.base import SectionStatus

        if status in (SectionStatus.DONE, SectionStatus.SKIPPED, SectionStatus.FAILED):
            self._done.add(name)
        self._current = name
        if len(self._done) > self.total:
            logger.warning(
                "Audit progress: %d sections completed but %d were expected; last section '%s'",
                len(self._done),
                self.total,
                name,
            )
            self.total = len(self._done)
        return self.snapshot()

    def snapshot(self) -> dict:
        completed = len(self._done)
        pct = round((completed / self.total) * 100) if self.total > 0 else 0
        return {
            "progress": min(pct, 100),
            "current_section": self._current,
            "total_sections": self.total,
            "completed": completed,
        }


# ── API: Setup SSE stream ──────────────────────────────────────────────────────


async def _run_setup_job(setup_run: state.SetupRunContext) -> None:
    """Run first-run setup to completion and persist config + secrets, whether
    or not the browser that started it is still connected.

    ``FirstRunSetup`` writes the cert and — on the PowerShell ``[RESULT]`` —
    saves the config and secrets. Run inside the SSE stream (as it used to be), a
    client disconnect mid-sign-in tore it down before that write, and the
    credentials were lost. Here it is a server-owned task; the stream only
    subscribes. Publishes log / device_code / done events and resets
    ``setup_running`` in its own ``finally``.
    """
    from app.modules.m365_audit.setup import FirstRunSetup

    def on_device_code(code: str, url: str) -> None:
        setup_run.publish({"type": "device_code", "code": code, "url": url})

    try:
        setup = FirstRunSetup(on_device_code=on_device_code)
        async for event in setup.run():
            setup_run.publish(
                {
                    "type": "log",
                    "step": event.get("step", ""),
                    "status": event.get("status", "ok"),
                    "msg": event.get("msg", ""),
                }
            )
            if event.get("status") == "error":
                setup_run.publish({"type": "done", "success": False})
                return
        setup_run.publish({"type": "done", "success": True})
    except Exception as e:
        logger.warning("Setup job failed: %s", e)
        setup_run.publish({"type": "error", "msg": str(e)})
        setup_run.publish({"type": "done", "success": False})
    finally:
        setup_run.running = False
        state.setup_running = False


@router.get("/setup/stream")
async def setup_stream(request: Request, user: User = Depends(get_current_user)):
    """Start first-run setup, or re-attach to the one already running.

    The setup is a server-owned job (``_run_setup_job``): the PowerShell
    device-code sign-in and the cert/credential write run to completion and
    persist regardless of this stream. A reconnecting client re-attaches and is
    replayed the current device-code prompt (so it can still finish signing in)
    and the outcome. ``?attach=1`` forces attach-only so a reconnect can never
    start a second setup.
    """
    attach_only = request.query_params.get("attach") == "1"

    attach = False
    attach_ended = False
    setup_run: state.SetupRunContext | None = None
    async with state.setup_lock:
        existing = state.get_setup_run()
        if existing is not None and existing.running:
            setup_run = existing
            attach = True
        elif attach_only:
            setup_run = existing
            attach_ended = True
        elif state.setup_running:
            raise ConflictError(ui_t("err_setup_running"))
        else:
            state.setup_running = True
            setup_run = state.begin_setup()

    # Launch the job outside the stream so it runs and persists even if the
    # client never consumes this response (disconnects immediately).
    if setup_run is not None and not attach and not attach_ended:
        setup_run.task = asyncio.create_task(_run_setup_job(setup_run))

    async def generate() -> AsyncGenerator[str, None]:
        if attach_ended:
            terminal = setup_run.terminal if setup_run is not None else None
            yield f"data: {json.dumps(terminal if terminal is not None else {'type': 'ended'})}\n\n"
            return

        q = setup_run.subscribe()
        try:
            if attach:
                # Replay the current sign-in prompt so a reconnecting operator can
                # still complete it, and the outcome if it already finished.
                if setup_run.device_code is not None:
                    yield f"data: {json.dumps(setup_run.device_code)}\n\n"
                if setup_run.terminal is not None:
                    yield f"data: {json.dumps(setup_run.terminal)}\n\n"
                    return
            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    break
        finally:
            setup_run.unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── API: Permission validation ────────────────────────────────────────────────


@router.post("/audit/validate-permissions")
async def validate_permissions(user: User = Depends(get_current_user)):
    """Check that the service principal has the required Graph API permissions."""
    try:
        from app.core.credentials import load_config
        from app.modules.m365_audit.auth import AuthManager
        from app.modules.m365_audit.graph_client import GraphClient

        cfg = load_config()
        if cfg and cfg.get("AuthMode") == "gdap":
            auth = AuthManager.from_gdap(cfg["TenantId"])
        else:
            auth = AuthManager.from_config()
        async with auth, GraphClient(auth.credential) as graph:
            if cfg and cfg.get("AuthMode") == "gdap":
                result = await graph.validate_gdap_access()
            else:
                result = await graph.validate_permissions()
            return result
    except Exception as e:
        logger.warning("Permission validation failed: %s", e)
        return JSONResponse(
            {"ok": False, "error": str(e), "granted": [], "missing": [], "warnings": [str(e)]},
            status_code=200,  # Return 200 so the UI can display the error message
        )


# ── API: Audit section listing & scope persistence ────────────────────────────


@router.get("/audit/sections")
async def list_audit_sections(user: User = Depends(get_current_user)):
    """Return all available audit sections with default enabled status."""
    from app.core.credentials import load_config
    from app.modules.m365_audit.collector import AuditCollector

    sections = AuditCollector.get_all_sections()

    # Check if Azure subscription is configured
    cfg = load_config()
    has_azure = bool(cfg.get("SubscriptionId", "")) if cfg else False

    if not has_azure:
        for s in sections:
            if s["category"] == "Azure":
                s["enabled"] = False

    return {"sections": sections, "has_azure": has_azure}


@router.get("/audit/scope")
async def get_audit_scope(user: User = Depends(get_current_user)):
    """Get saved audit scope for the active customer."""
    from app.core.customer import CustomerManager

    active_id = CustomerManager.get_active_id()
    if not active_id:
        return {"scope": None}
    scope_path = CustomerManager.get_customer_dir(active_id) / "audit_scope.json"
    if scope_path.exists():
        from app.core.encryption import encrypted_read_json

        return {"scope": encrypted_read_json(scope_path)}
    return {"scope": None}


@router.post("/audit/scope")
async def save_audit_scope(request: Request, user: User = Depends(get_current_user)):
    """Save audit scope for the active customer."""
    from app.core.customer import CustomerManager

    active_id = CustomerManager.get_active_id()
    if not active_id:
        raise ValidationError(ui_t("err_no_active_customer", request))
    body = await request.json()
    scope_path = CustomerManager.get_customer_dir(active_id) / "audit_scope.json"
    from app.core.encryption import encrypted_write_json

    encrypted_write_json(scope_path, body)
    return {"ok": True}


# ── API: Audit presets ─────────────────────────────────────────────────────────


@router.get("/audit/presets")
async def list_audit_presets(user: User = Depends(get_current_user)):
    """Return built-in + custom presets."""
    from app.core.config import load_app_settings
    from app.modules.m365_audit.collector import AuditCollector

    all_names = [s["name"] for s in AuditCollector.get_all_sections()]

    presets = []
    for name, sections in _BUILTIN_PRESETS.items():
        presets.append(
            {
                "name": name,
                "sections": sections if sections is not None else all_names,
                "builtin": True,
            }
        )

    settings = load_app_settings()
    for name, sections in settings.get("audit_presets", {}).items():
        presets.append({"name": name, "sections": sections, "builtin": False})

    return {"presets": presets}


@router.post("/audit/presets")
async def save_audit_preset(request: Request, user: User = Depends(get_current_user)):
    """Save a custom preset."""
    from app.core.config import update_app_settings

    body = await request.json()
    name = (body.get("name") or "").strip()
    sections = body.get("sections", [])
    if not name:
        raise ValidationError(ui_t("err_missing_title", request))
    if name in _BUILTIN_PRESETS:
        raise ValidationError(ui_t("err_preset_builtin", request))

    def _add(s: dict) -> None:
        custom = s.get("audit_presets", {})
        custom[name] = sections
        s["audit_presets"] = custom

    update_app_settings(_add)
    return {"ok": True}


@router.delete("/audit/presets/{name}")
async def delete_audit_preset(name: str, user: User = Depends(get_current_user)):
    """Delete a custom preset."""
    from app.core.config import update_app_settings

    if name in _BUILTIN_PRESETS:
        raise ValidationError(ui_t("err_preset_builtin"))

    def _remove(s: dict) -> None:
        custom = s.get("audit_presets", {})
        if name not in custom:
            raise NotFoundError(ui_t("err_preset_not_found"))
        del custom[name]
        s["audit_presets"] = custom

    update_app_settings(_remove)
    return {"ok": True}


# ── API: Audit SSE stream ──────────────────────────────────────────────────────


def _prepare_audit(request: Request) -> tuple[str | None, dict | None]:
    """Preflight a *new* audit: verify credentials and build the output dir.

    Returns ``(error_message, spec)``. On error the spec is None and nothing has
    been committed — no run is marked running — so the caller can refuse without
    stranding the global lock. The spec carries what the background job needs.
    """
    from app.core.credentials import config_exists, get_secret, load_config
    from app.modules.m365_audit.collector import make_output_dir

    if not config_exists():
        return ui_t("err_no_customer_config", request), None
    cfg = load_config() or {}
    tenant_id = cfg.get("TenantId", "")
    client_id = cfg.get("ClientId", "")
    if not tenant_id or not client_id:
        return ui_t("err_missing_m365_setup", request), None
    if not get_secret(tenant_id, "client_secret"):
        return ui_t("err_missing_m365_secret", request), None
    customer_name = cfg.get("CustomerName", "Ukjent")
    return None, {
        "cfg": cfg,
        "customer_name": customer_name,
        "out_dir": make_output_dir(customer_name),
    }


async def _post_audit_side_effects(
    cfg: dict, results: list[dict], out_dir, customer_name: str
) -> dict | None:
    """Completion work that must run whether or not a browser is watching: save
    the dashboard metrics, auto-send the report, fire the webhook.

    Moved out of the SSE loop so it runs in the job. Each step is best-effort and
    logged rather than fatal. Returns an email status to surface, or None.
    """
    from app.modules.base import SectionResult, SectionStatus

    result_objs = [
        SectionResult(
            name=r["name"],
            status=SectionStatus[r["status"].upper()],
            warns=r.get("warns", []),
            warn_levels=r.get("warn_levels", []),
            files=r.get("files", []),
            error=r.get("error"),
        )
        for r in results
    ]

    # Build the report context once: it saves the metrics JSON the dashboard
    # grade/score reads, and doubles as the webhook payload.
    ctx = None
    try:
        from app.reports.generator import build_report_context

        ctx = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: build_report_context(
                customer_name=customer_name,
                org_domain=cfg.get("PrimaryDomain", ""),
                out_dir=out_dir,
                results=result_objs,
                lang="no",
            ),
        )
    except Exception as exc:
        logger.warning("Failed to build report context / save audit metrics: %s", exc)

    email_status: dict | None = None
    try:
        from app.core.email_sender import auto_send_after_audit

        email_err = await asyncio.get_event_loop().run_in_executor(
            None, lambda: auto_send_after_audit(out_dir)
        )
        if email_err:
            email_status = {"ok": False, "msg": email_err}
        elif email_err is None:
            from app.core.config import load_app_settings

            _s = load_app_settings()
            if _s.get("email_auto_send"):
                email_status = {
                    "ok": True,
                    "msg": "Rapport sendt til " + _s.get("email_default_recipient", ""),
                }
    except Exception as exc:
        logger.warning("Auto-send email after audit failed: %s", exc)
        email_status = {"ok": False, "msg": str(exc)}

    try:
        from app.core.scheduler import scheduler as _sched

        if ctx is not None:
            await _sched._check_and_alert(ctx, customer_name)
            await _sched._notify_audit_completed(customer_name, ctx=ctx)
        else:
            await _sched._notify_audit_completed(customer_name)
    except Exception as exc:
        logger.error("Webhook notification failed: %s", exc, exc_info=True)

    return email_status


async def _run_audit_job(
    audit_run: state.AuditRunContext,
    spec: dict,
    sections_filter: set | None,
    username: str,
) -> None:
    """Run the collector to completion and persist everything, independent of any
    connected stream.

    Publishes progress and a terminal (done/error/cancelled) event to the run's
    subscribers, and resets the running flags in its own ``finally`` — so a
    dropped view never ends the run, and results are saved even when nobody is
    watching at the finish. This is the whole point of the server-owned job.
    """
    from app.core.activity_log import log_activity
    from app.modules.m365_audit.auth import AuthManager
    from app.modules.m365_audit.collector import AuditCollector

    cfg = spec["cfg"]
    out_dir = spec["out_dir"]
    customer_name = spec["customer_name"]

    tracker = _ProgressTracker(sections_filter)
    audit_run.progress = tracker.snapshot()

    def progress_cb(name, status, detail=None) -> None:
        audit_run.progress = tracker.record(name, status)
        audit_run.publish(
            {"type": "progress", "name": name, "status": status.name.lower(), "detail": detail or ""}
        )

    try:
        if cfg.get("AuthMode") == "gdap":
            auth = AuthManager.from_gdap(cfg["TenantId"])
        else:
            auth = AuthManager.from_config()
        collector = AuditCollector(
            auth=auth, out_dir=out_dir, progress_cb=progress_cb, sections_filter=sections_filter
        )
        results = await collector.run()
        audit_run.results = [
            {
                "name": r.name,
                "status": r.status.name.lower(),
                "warns": r.warns,
                "warn_levels": r.warn_levels,
                "files": r.files,
                "error": r.error,
            }
            for r in results
        ]
        log_activity("audit_completed", customer=customer_name, user=username)

        done_event: dict = {"type": "done", "results": audit_run.results}
        email_status = await _post_audit_side_effects(
            cfg, audit_run.results, out_dir, customer_name
        )
        if email_status is not None:
            done_event["email_status"] = email_status
        audit_run.publish(done_event)
    except asyncio.CancelledError:
        # Operator-initiated cancel (/audit/cancel cancels this task). Fully
        # handled here: announce it, then let the finally reset the flags.
        audit_run.publish({"type": "cancelled", "msg": ui_t("msg_audit_cancelled")})
    except Exception as exc:
        logger.error("Audit failed:\n%s", traceback.format_exc())
        audit_run.publish({"type": "error", "msg": str(exc)})
    finally:
        audit_run.running = False
        state.audit_running = False


@router.get("/audit/stream")
async def audit_stream(request: Request, user: User = Depends(get_current_user)):
    """Start an audit, or re-attach to this user's already-running one.

    The run is owned by the server (``_run_audit_job``), not by this stream. A
    dropped connection is a lost *view*, not a lost run: the job keeps collecting
    and saves its results regardless, and a reconnecting client re-attaches here
    and is replayed the current progress (and the outcome, if it already
    finished). The stream never resets the running flags — only the job does.

    ``?attach=1`` asks to *only* re-attach: if the run is no longer active it
    replays the stored outcome (or says it ended) rather than starting a fresh
    audit, so a reconnect loop can never launch a duplicate collection.
    """
    from app.core.customer import CustomerManager

    active_id = CustomerManager.get_active_id()
    if not active_id:
        raise ValidationError(ui_t("err_no_active_customer", request))

    sections_param = request.query_params.get("sections", "")
    sections_filter: set | None = None
    if sections_param:
        sections_filter = set(s.strip() for s in sections_param.split(",") if s.strip())
    attach_only = request.query_params.get("attach") == "1"

    # Decide attach-or-start under the lock so two tabs cannot both start one.
    prep_error: str | None = None
    spec: dict | None = None
    attach = False
    attach_ended = False
    audit_run: state.AuditRunContext | None = None
    async with state.audit_lock:
        existing = state.get_user_audit(user.id, active_id)
        if existing is not None and existing.running:
            audit_run = existing
            attach = True
        elif attach_only:
            # Asked to re-attach, but the run is no longer active. Do NOT start a
            # new one; replay the outcome if we still have it, else say it ended.
            audit_run = existing
            attach_ended = True
        elif state.audit_running:
            raise ConflictError(ui_t("err_audit_running", request))
        else:
            prep_error, spec = _prepare_audit(request)
            if prep_error is None and spec is not None:
                state.audit_running = True
                audit_run = state.begin_user_audit(user.id, active_id)
                audit_run.customer_name = spec["customer_name"]
                audit_run.out_dir = spec["out_dir"]

    # Launch the job *outside* the stream, so it runs to completion and saves
    # even if the client never consumes this response (disconnects immediately).
    # If it were created inside generate(), a client gone before the first yield
    # would leave it un-launched — and the global lock stranded True forever.
    if audit_run is not None and not attach and not attach_ended and prep_error is None:
        from app.core.activity_log import log_activity

        log_activity("audit_started", customer=spec["customer_name"], user=user.username)
        audit_run.task = asyncio.create_task(
            _run_audit_job(audit_run, spec, sections_filter, user.username)
        )

    async def generate() -> AsyncGenerator[str, None]:
        if prep_error is not None:
            yield f"data: {json.dumps({'type': 'error', 'msg': prep_error})}\n\n"
            return
        if attach_ended:
            terminal = audit_run.terminal if audit_run is not None else None
            if terminal is not None:
                yield f"data: {json.dumps({'type': 'started', 'customer': audit_run.customer_name, 'reattached': True})}\n\n"
                yield f"data: {json.dumps(terminal)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'ended'})}\n\n"
            return

        # Subscribe before inspecting terminal so a finish during setup is not
        # missed: the event lands on the queue and is streamed below.
        q = audit_run.subscribe()
        try:
            if attach:
                yield f"data: {json.dumps({'type': 'started', 'customer': audit_run.customer_name, 'reattached': True})}\n\n"
                yield f"data: {json.dumps({'type': 'snapshot', **audit_run.progress})}\n\n"
                if audit_run.terminal is not None:
                    yield f"data: {json.dumps(audit_run.terminal)}\n\n"
                    return
            else:
                # The job was already launched above; just announce the start.
                yield f"data: {json.dumps({'type': 'started', 'customer': spec['customer_name']})}\n\n"

            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error", "cancelled"):
                    break
        finally:
            # A lost view must never end the run: unsubscribe only. The job owns
            # the running flags and resets them when it actually finishes.
            audit_run.unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── API: Audit progress polling ──────────────────────────────────────────────

_IDLE_PROGRESS = {"progress": 0, "current_section": "", "total_sections": 0, "completed": 0}


def _with_running(run: state.AuditRunContext | None) -> dict:
    """Progress, plus whether an audit is actually running.

    Without this the client cannot tell "no audit" from "an audit that has not
    reported a section yet" — both are zeros. It guessed, kept a local flag,
    and the flag outlived the run: the badge stayed lit and the reconnect loop
    kept calling the *start* endpoint, which started a fresh audit every time.
    The server knows; let it say so.
    """
    if run is None:
        return {**_IDLE_PROGRESS, "running": False}
    return {**run.progress, "running": run.running, "run_id": run.run_id}


@router.get("/audit/progress/{customer_id}")
async def get_audit_progress(
    customer_id: str, user: User = Depends(require_customer_access(Role.viewer))
):
    """Return current audit progress for the given customer (or 'active')."""
    return _with_running(state.get_user_audit(user.id, customer_id))


@router.get("/audit/progress")
async def get_audit_progress_active(user: User = Depends(get_current_user)):
    """Return current audit progress for the active customer."""
    from app.core.customer import CustomerManager

    active_id = CustomerManager.get_active_id()
    return _with_running(state.get_user_audit(user.id, active_id) if active_id else None)


# ── API: Audit cancel ─────────────────────────────────────────────────────────


@router.post("/audit/cancel")
async def cancel_audit(user: User = Depends(get_current_user)):
    """Request cancellation of a running audit."""
    # Cancellation follows ownership, not the currently selected customer. A
    # user may switch views while their stream is running; that must not strand
    # an un-cancellable collector, and it still can never target another user.
    run = state.get_user_audit(user.id)
    if run is None or not run.running:
        raise ConflictError(ui_t("err_no_audit_running"))
    run.cancel_requested = True
    # The run is a server-owned task now, not a loop in the stream, so cancel it
    # directly. It raises CancelledError inside _run_audit_job, which announces
    # 'cancelled' and resets the running flags in its finally.
    if run.task is not None:
        run.task.cancel()
    return {"ok": True, "msg": ui_t("msg_audit_cancelled")}


# ── API: Bulk audit SSE stream ────────────────────────────────────────────────


@router.get("/audit/bulk")
async def bulk_audit_stream(request: Request, user: User = Depends(require_role(Role.admin))):
    """Run audit for configured customers in parallel, streaming progress via SSE.

    Uses asyncio.Semaphore to limit concurrency (default 3) so Microsoft
    Graph API rate limits are respected while still running much faster
    than sequential execution.
    """
    # Claim both flags atomically, before the response starts streaming. The
    # check and the set must be one critical section: set inside the generator
    # (as this used to be) left a window where two concurrent requests both
    # passed the check before either set the flag, and both audits ran.
    async with state.audit_lock:
        if state.bulk_audit_running:
            raise ConflictError(ui_t("err_bulk_running"))
        if state.audit_running:
            raise ConflictError(ui_t("err_audit_running"))
        state.bulk_audit_running = True
        state.audit_running = True

    MAX_CONCURRENT = 3  # parallel audits at once

    async def generate() -> AsyncGenerator[str, None]:
        try:
            from app.core.customer import CustomerManager
            from app.modules.base import SectionResult, SectionStatus
            from app.modules.m365_audit.collector import AuditCollector, make_output_dir
            from app.reports.generator import build_report_context, generate_reports

            all_customers = CustomerManager.list_customers()
            if not all_customers:
                yield f"data: {json.dumps({'type': 'error', 'msg': ui_t('err_no_customers')})}\n\n"
                return

            # Filter to only configured customers (have TenantId + ClientId)
            customers = [c for c in all_customers if c.get("TenantId") and c.get("ClientId")]
            skipped_count = len(all_customers) - len(customers)

            if not customers:
                yield f"data: {json.dumps({'type': 'error', 'msg': ui_t('err_no_customers_audit', request)})}\n\n"
                return

            total = len(customers)
            summary: list[dict] = []
            progress_queue: asyncio.Queue = asyncio.Queue()
            sem = asyncio.Semaphore(MAX_CONCURRENT)

            yield f"data: {json.dumps({'type': 'bulk_started', 'total_customers': total, 'skipped_unconfigured': skipped_count, 'parallel': MAX_CONCURRENT, 'customers': [c.get('CustomerName', c.get('customer_id', '?')) for c in customers]})}\n\n"

            # ── Per-customer audit coroutine ──
            async def audit_one(idx: int, cust: dict) -> dict:
                cust_id = cust.get("customer_id", cust.get("_id", ""))
                cust_name = cust.get("CustomerName", cust_id)

                async with sem:
                    # Build auth from customer data directly — no global state
                    try:
                        full_cust = CustomerManager.get_customer(cust_id)
                        if not full_cust:
                            progress_queue.put_nowait(
                                {
                                    "type": "customer_skip",
                                    "index": idx,
                                    "total": total,
                                    "customer": cust_name,
                                    "reason": ui_t("err_customer_not_found"),
                                }
                            )
                            return {
                                "customer": cust_name,
                                "status": "skipped",
                                "error": ui_t("err_customer_not_found"),
                            }

                        cust_cert = CustomerManager.get_cert_path(cust_id)
                        from app.modules.m365_audit.auth import get_auth_for_customer

                        auth = get_auth_for_customer(full_cust, cust_cert)
                    except Exception as e:
                        logger.warning("Auth setup failed for customer %s: %s", cust_name, e)
                        progress_queue.put_nowait(
                            {
                                "type": "customer_error",
                                "index": idx,
                                "total": total,
                                "customer": cust_name,
                                "error": str(e),
                            }
                        )
                        return {"customer": cust_name, "status": "error", "error": str(e)}

                    progress_queue.put_nowait(
                        {
                            "type": "customer_start",
                            "index": idx,
                            "total": total,
                            "customer": cust_name,
                        }
                    )

                    try:

                        def progress_cb(
                            name: str,
                            status: SectionStatus,
                            detail: str | None,
                            _ci=idx,
                            _ct=total,
                            _cn=cust_name,
                        ) -> None:
                            progress_queue.put_nowait(
                                {
                                    "type": "progress",
                                    "index": _ci,
                                    "total": _ct,
                                    "customer": _cn,
                                    "name": name,
                                    "status": status.name.lower(),
                                    "detail": detail or "",
                                }
                            )

                        out_dir = make_output_dir(cust_name)
                        collector = AuditCollector(
                            auth=auth, out_dir=out_dir, progress_cb=progress_cb
                        )
                        audit_results_raw = await collector.run()

                        # Generate reports
                        results_objs = [
                            SectionResult(
                                name=r.name,
                                status=r.status,
                                warns=r.warns,
                                warn_levels=r.warn_levels,
                                files=r.files,
                                error=r.error,
                            )
                            for r in audit_results_raw
                        ]
                        org_domain = full_cust.get("PrimaryDomain", "")
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            None,
                            lambda _cn=cust_name, _od=org_domain, _odir=out_dir, _ro=results_objs: (
                                generate_reports(
                                    customer_name=_cn,
                                    org_domain=_od,
                                    out_dir=_odir,
                                    results=_ro,
                                    formats=["html"],
                                    report_type="tech",
                                    lang="no",
                                )
                            ),
                        )

                        ctx = await loop.run_in_executor(
                            None,
                            lambda _cn=cust_name, _od=org_domain, _odir=out_dir, _ro=results_objs: (
                                build_report_context(_cn, _od, _odir, _ro, lang="no")
                            ),
                        )

                        done_count = sum(
                            1 for r in audit_results_raw if r.status == SectionStatus.DONE
                        )
                        fail_count = sum(
                            1 for r in audit_results_raw if r.status == SectionStatus.FAILED
                        )

                        cust_summary = {
                            "customer": cust_name,
                            "status": "done",
                            "grade": ctx.get("risk_grade", "-"),
                            "risk_score": ctx.get("risk_score", 0),
                            "sections_done": done_count,
                            "sections_failed": fail_count,
                            "sections_total": len(audit_results_raw),
                        }
                        progress_queue.put_nowait(
                            {"type": "customer_done", "index": idx, "total": total, **cust_summary}
                        )

                        # Webhooks
                        try:
                            from app.core.scheduler import scheduler as _sched

                            await _sched._check_and_alert(ctx, cust_name)
                            await _sched._notify_audit_completed(cust_name, ctx=ctx)
                        except Exception as e:
                            logger.warning("Webhook notification failed for %s: %s", cust_name, e)

                        return cust_summary

                    except Exception as e:
                        logger.error("Audit failed for %s:\n%s", cust_name, traceback.format_exc())
                        progress_queue.put_nowait(
                            {
                                "type": "customer_error",
                                "index": idx,
                                "total": total,
                                "customer": cust_name,
                                "error": str(e),
                            }
                        )
                        try:
                            from app.core.scheduler import scheduler as _sched

                            await _sched._send_webhook(f"⚠️ Audit feilet for **{cust_name}**: {e}")
                        except Exception as e2:
                            logger.warning(
                                "Webhook error notification failed for %s: %s", cust_name, e2
                            )
                        return {"customer": cust_name, "status": "error", "error": str(e)}

            # ── Launch all audits and stream progress ──
            tasks = [asyncio.create_task(audit_one(i, c)) for i, c in enumerate(customers)]

            # Drain progress queue while tasks run
            finished = 0
            while finished < len(tasks):
                try:
                    item = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                    yield f"data: {json.dumps(item)}\n\n"
                    if item.get("type") in ("customer_done", "customer_error", "customer_skip"):
                        finished += 1
                except TimeoutError:
                    # Check for crashed tasks
                    for t in tasks:
                        if t.done() and t.exception():
                            finished += 1
                    continue

            # Gather all results
            summary = [t.result() for t in tasks if t.done() and not t.exception()]

            # Send bulk summary webhook
            try:
                from app.core.scheduler import scheduler as _sched

                done_custs = [s for s in summary if s.get("status") == "done"]
                fail_custs = [s for s in summary if s.get("status") == "error"]
                skip_custs = [s for s in summary if s.get("status") == "skipped"]
                lines = [
                    f"📋 **Bulk-audit fullført: {len(done_custs)}/{total} OK** ({MAX_CONCURRENT} parallelle)"
                ]
                for s in done_custs:
                    lines.append(
                        f"✅ {s['customer']} — Karakter {s.get('grade', '-')} (score {s.get('risk_score', 0)})"
                    )
                for s in fail_custs:
                    lines.append(f"❌ {s['customer']} — {s.get('error', 'Ukjent feil')}")
                for s in skip_custs:
                    lines.append(f"⏭ {s['customer']} — Hoppet over")
                await _sched._send_webhook("\n".join(lines))
            except Exception as e:
                logger.warning("Bulk summary webhook failed: %s", e)

            yield f"data: {json.dumps({'type': 'bulk_done', 'summary': summary})}\n\n"

        except Exception as e:
            logger.error("Bulk audit failed:\n%s", traceback.format_exc())
            yield f"data: {json.dumps({'type': 'error', 'msg': str(e)})}\n\n"
        finally:
            state.bulk_audit_running = False
            state.audit_running = False

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
