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


@router.get("/setup/stream")
async def setup_stream(user: User = Depends(get_current_user)):
    if state.setup_running:
        raise ConflictError(ui_t("err_setup_running"))

    async def generate() -> AsyncGenerator[str, None]:
        state.setup_running = True
        device_code_pending: dict | None = None

        try:
            from app.modules.m365_audit.setup import FirstRunSetup

            def on_device_code(code: str, url: str) -> None:
                nonlocal device_code_pending
                device_code_pending = {"type": "device_code", "code": code, "url": url}

            setup = FirstRunSetup(on_device_code=on_device_code)

            async for event in setup.run():
                # Flush pending device_code event before next log line
                if device_code_pending:
                    yield f"data: {json.dumps(device_code_pending)}\n\n"
                    device_code_pending = None

                payload = {
                    "type": "log",
                    "step": event.get("step", ""),
                    "status": event.get("status", "ok"),
                    "msg": event.get("msg", ""),
                }
                yield f"data: {json.dumps(payload)}\n\n"

                if event.get("status") == "error":
                    yield f"data: {json.dumps({'type': 'done', 'success': False})}\n\n"
                    return

            yield f"data: {json.dumps({'type': 'done', 'success': True})}\n\n"

        except Exception as e:
            logger.warning("Setup stream failed: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'msg': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'success': False})}\n\n"
        finally:
            state.setup_running = False

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
    from app.core.config import load_app_settings, save_app_settings

    body = await request.json()
    name = (body.get("name") or "").strip()
    sections = body.get("sections", [])
    if not name:
        raise ValidationError(ui_t("err_missing_title", request))
    if name in _BUILTIN_PRESETS:
        raise ValidationError(ui_t("err_preset_builtin", request))

    settings = load_app_settings()
    custom = settings.get("audit_presets", {})
    custom[name] = sections
    settings["audit_presets"] = custom
    save_app_settings(settings)
    return {"ok": True}


@router.delete("/audit/presets/{name}")
async def delete_audit_preset(name: str, user: User = Depends(get_current_user)):
    """Delete a custom preset."""
    from app.core.config import load_app_settings, save_app_settings

    if name in _BUILTIN_PRESETS:
        raise ValidationError(ui_t("err_preset_builtin"))

    settings = load_app_settings()
    custom = settings.get("audit_presets", {})
    if name not in custom:
        raise NotFoundError(ui_t("err_preset_not_found"))
    del custom[name]
    settings["audit_presets"] = custom
    save_app_settings(settings)
    return {"ok": True}


# ── API: Audit SSE stream ──────────────────────────────────────────────────────


@router.get("/audit/stream")
async def audit_stream(request: Request, user: User = Depends(get_current_user)):
    from app.core.customer import CustomerManager

    active_id = CustomerManager.get_active_id()
    if not active_id:
        raise ValidationError(ui_t("err_no_active_customer", request))

    async with state.audit_lock:
        if state.audit_running:
            raise ConflictError(ui_t("err_audit_running", request))
        state.audit_running = True
        audit_run = state.begin_user_audit(user.id, active_id)

    # Parse optional sections filter from query string
    sections_param = request.query_params.get("sections", "")
    sections_filter: set | None = None
    if sections_param:
        sections_filter = set(s.strip() for s in sections_param.split(",") if s.strip())

    async def generate() -> AsyncGenerator[str, None]:
        try:
            from app.core.credentials import config_exists, get_secret, load_config
            from app.modules.base import SectionStatus
            from app.modules.m365_audit.auth import AuthManager
            from app.modules.m365_audit.collector import AuditCollector, make_output_dir

            # Pre-flight check: does this customer have credentials?
            if not config_exists():
                yield f"data: {json.dumps({'type': 'error', 'msg': ui_t('err_no_customer_config', request)})}\n\n"
                return

            cfg = load_config()
            tenant_id = cfg.get("TenantId", "") if cfg else ""
            client_id = cfg.get("ClientId", "") if cfg else ""

            if not tenant_id or not client_id:
                yield f"data: {json.dumps({'type': 'error', 'msg': ui_t('err_missing_m365_setup', request)})}\n\n"
                return

            # Check for client secret in keyring
            secret = get_secret(tenant_id, "client_secret")
            if not secret:
                yield f"data: {json.dumps({'type': 'error', 'msg': ui_t('err_missing_m365_secret', request)})}\n\n"
                return

            queue: asyncio.Queue = asyncio.Queue()

            tracker = _ProgressTracker(sections_filter)

            audit_run.progress = tracker.snapshot()

            def progress_cb(name: str, status: SectionStatus, detail: str | None) -> None:
                audit_run.progress = tracker.record(name, status)
                queue.put_nowait(
                    {
                        "type": "progress",
                        "name": name,
                        "status": status.name.lower(),
                        "detail": detail or "",
                    }
                )

            cfg = load_config()
            customer_name = cfg.get("CustomerName", "Ukjent") if cfg else "Ukjent"
            out_dir = make_output_dir(customer_name)
            audit_run.out_dir = out_dir

            yield f"data: {json.dumps({'type': 'started', 'customer': customer_name})}\n\n"

            from app.core.activity_log import log_activity

            log_activity("audit_started", customer=customer_name, user=user.username)

            async def run_audit() -> None:
                try:
                    if cfg.get("AuthMode") == "gdap":
                        auth = AuthManager.from_gdap(cfg["TenantId"])
                    else:
                        auth = AuthManager.from_config()
                    collector = AuditCollector(
                        auth=auth,
                        out_dir=out_dir,
                        progress_cb=progress_cb,
                        sections_filter=sections_filter,
                    )
                    results = await collector.run()
                    queue.put_nowait(
                        {
                            "type": "done",
                            "results": [
                                {
                                    "name": r.name,
                                    "status": r.status.name.lower(),
                                    "warns": r.warns,
                                    "warn_levels": r.warn_levels,
                                    "files": r.files,
                                    "error": r.error,
                                }
                                for r in results
                            ],
                        }
                    )
                except Exception as e:
                    tb = traceback.format_exc()
                    logger.error("Audit failed:\n%s", tb)
                    queue.put_nowait({"type": "error", "msg": str(e)})

            task = asyncio.create_task(run_audit())

            while True:
                if audit_run.cancel_requested:
                    task.cancel()
                    yield f"data: {json.dumps({'type': 'cancelled', 'msg': ui_t('msg_audit_cancelled', request)})}\n\n"
                    break
                item = await queue.get()
                if item["type"] == "done":
                    audit_run.results = item.get("results", [])
                    log_activity("audit_completed", customer=customer_name, user=user.username)

                    # Always save metrics for dashboard grade/score
                    try:
                        from app.core.credentials import load_config as _lc2
                        from app.modules.base import SectionResult as _SR2
                        from app.modules.base import SectionStatus as _SS2
                        from app.reports.generator import build_report_context as _brc

                        _cfg2 = _lc2() or {}
                        _ro2 = [
                            _SR2(
                                name=r["name"],
                                status=_SS2[r["status"].upper()],
                                warns=r.get("warns", []),
                                warn_levels=r.get("warn_levels", []),
                                files=r.get("files", []),
                                error=r.get("error"),
                            )
                            for r in audit_run.results
                        ]
                        await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda cfg=_cfg2, results=_ro2: _brc(
                                customer_name=customer_name,
                                org_domain=cfg.get("PrimaryDomain", ""),
                                out_dir=out_dir,
                                results=results,
                                lang="no",
                            ),
                        )
                    except Exception as _metrics_exc:
                        logger.warning("Failed to save audit metrics: %s", _metrics_exc)

                    # Auto-send email if enabled
                    try:
                        from app.core.email_sender import auto_send_after_audit

                        email_err = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: auto_send_after_audit(audit_run.out_dir)
                        )
                        if email_err:
                            item["email_status"] = {"ok": False, "msg": email_err}
                        elif email_err is None:
                            from app.core.config import load_app_settings as _las

                            _s = _las()
                            if _s.get("email_auto_send"):
                                item["email_status"] = {
                                    "ok": True,
                                    "msg": "Rapport sendt til "
                                    + _s.get("email_default_recipient", ""),
                                }
                    except Exception as email_exc:
                        logger.warning("Auto-send email after audit failed: %s", email_exc)
                        item["email_status"] = {"ok": False, "msg": str(email_exc)}
                    # Webhook notification after manual audit
                    try:
                        from app.core.credentials import load_config as _lc
                        from app.core.scheduler import scheduler as _sched
                        from app.modules.base import SectionResult
                        from app.modules.base import SectionStatus as _SS
                        from app.reports.generator import build_report_context

                        _cfg = _lc() or {}
                        _results_objs = [
                            SectionResult(
                                name=r["name"],
                                status=_SS[r["status"].upper()],
                                warns=r.get("warns", []),
                                warn_levels=r.get("warn_levels", []),
                                files=r.get("files", []),
                                error=r.get("error"),
                            )
                            for r in audit_run.results
                        ]
                        _ctx = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda cfg=_cfg, results=_results_objs: build_report_context(
                                customer_name=customer_name,
                                org_domain=cfg.get("PrimaryDomain", ""),
                                out_dir=out_dir,
                                results=results,
                                lang="no",
                            ),
                        )
                        await _sched._check_and_alert(_ctx, customer_name)
                        await _sched._notify_audit_completed(customer_name, ctx=_ctx)
                    except Exception as _wh_exc:
                        logger.error("Webhook ctx build failed: %s", _wh_exc, exc_info=True)
                        # Fallback — send basic notification rather than nothing
                        try:
                            await _sched._notify_audit_completed(customer_name)
                        except Exception as e3:
                            logger.warning(
                                "Fallback webhook notification failed for %s: %s", customer_name, e3
                            )
                    yield f"data: {json.dumps(item)}\n\n"
                    break
                yield f"data: {json.dumps(item)}\n\n"
                if item["type"] == "error":
                    break

            await task

        except Exception as e:
            logger.error("Audit stream failed: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'msg': str(e)})}\n\n"
        finally:
            audit_run.running = False
            state.audit_running = False

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
    return {"ok": True, "msg": ui_t("msg_audit_cancelled")}


# ── API: Bulk audit SSE stream ────────────────────────────────────────────────


@router.get("/audit/bulk")
async def bulk_audit_stream(request: Request, user: User = Depends(require_role(Role.admin))):
    """Run audit for configured customers in parallel, streaming progress via SSE.

    Uses asyncio.Semaphore to limit concurrency (default 3) so Microsoft
    Graph API rate limits are respected while still running much faster
    than sequential execution.
    """
    if state.bulk_audit_running:
        raise ConflictError(ui_t("err_bulk_running"))
    if state.audit_running:
        raise ConflictError(ui_t("err_audit_running"))

    MAX_CONCURRENT = 3  # parallel audits at once

    async def generate() -> AsyncGenerator[str, None]:
        state.bulk_audit_running = True
        state.audit_running = True

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
