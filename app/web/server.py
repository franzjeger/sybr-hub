"""Sybr HUB FastAPI app.

An application factory and nothing else: middleware, the error handler, and
the router table. Every endpoint lives in ``app.web.routes`` — including the
SPA shell and static assets (``routes.frontend``) and the Guacamole reverse
proxy (``routes.guacamole``), so this file stays readable as the map of what
the app exposes.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.database import close_pool, run_migrations
from app.core.encryption import verify_master_key_available
from app.core.exceptions import ToolkitError
from app.core.redact import redact
from app.core.version import get_version
from app.web.middleware.auth import AuthMiddleware, get_current_user
from app.web.middleware.rate_limit import RateLimitMiddleware
from app.web.middleware.security_headers import SecurityHeadersMiddleware
from app.web.middleware.write_guard import WriteGuardMiddleware
from app.web.routes import (
    also,
    audit,
    auth,
    autotask,
    backup,
    baselines,
    claude,
    customers,
    dashboard,
    dashboard_ws,
    docs,
    fortigate,
    frontend,
    gdap,
    guacamole,
    history,
    hub,
    itglue,
    myitprocess,
    pentest,
    policy_backup,
    policy_deploy,
    provisioning,
    proxy,
    reports,
    settings,
    ssh,
    system,
    tailscale,
    terminal,
    tls,
    unifi,
    uniweb,
    vpn,
    workshop,
)

log = logging.getLogger(__name__)

OPENAPI_DOCS_URL = "/docs"
_SWAGGER_UI_VERSION = "5.32.12"

# Mounted under /api, in the order the operator meets them: authentication,
# then the customer/audit core, then integrations and connectivity.
_API_ROUTERS = (
    ("auth", auth),
    ("settings", settings),
    ("system", system),
    ("vpn", vpn),
    ("hub", hub),
    ("customers", customers),
    ("dashboard", dashboard),
    ("dashboard_ws", dashboard_ws),
    ("audit", audit),
    ("reports", reports),
    ("history", history),
    ("autotask", autotask),
    ("baselines", baselines),
    ("docs", docs),
    ("policy_backup", policy_backup),
    ("policy_deploy", policy_deploy),
    ("workshop", workshop),
    ("backup", backup),
    # Connectivity — the toolkit reaches customer-internal devices over these.
    ("fortigate", fortigate),
    ("unifi", unifi),
    ("ssh", ssh),
    ("terminal", terminal),
    ("proxy", proxy),
    ("tailscale", tailscale),
    # Integrations and analysis.
    ("itglue", itglue),
    ("myitprocess", myitprocess),
    ("also", also),
    ("gdap", gdap),
    ("uniweb", uniweb),
    ("tls", tls),
    ("pentest", pentest),
    ("provisioning", provisioning),
    ("claude", claude),
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App startup/shutdown hooks."""
    log.info("Sybr HUB starting — version %s", get_version())
    # Attach the /api/logs ring buffer before anything interesting is logged.
    frontend.install_log_capture()
    # Resolve the master key before serving anything. The key is otherwise
    # resolved lazily on first use, so a host that can no longer unwrap its own
    # key backups would serve traffic and then fail somewhere deep in a
    # request. Fail fast instead: MasterKeyUnavailableError carries the
    # remediation, and stopping here is what stops a new key being minted over
    # recoverable data.
    verify_master_key_available()
    await run_migrations()
    try:
        await proxy.startup_proxy_resources()
    except Exception as exc:
        # Guacamole is optional and may be offline while the rest of the hub is
        # healthy. Keep serving, but leave a visible cleanup warning.
        log.warning("Stale Guacamole cleanup could not run at startup: %s", exc)

    # Start the background schedulers here, not from a settings save. Enabled
    # jobs used to begin only when their config was next written, so a restart
    # silently stopped everything until an operator reopened Settings (SR-004).
    # This process owns the schedule: main.py runs a single uvicorn worker;
    # running several would double every job, and a leader/lease would be
    # needed before multi-worker is supported.
    try:
        from app.core.scheduler import scheduler as _audit_scheduler
        _audit_scheduler.start()
    except Exception as exc:
        log.warning("Audit scheduler did not start: %s", exc)
    try:
        from app.services import scheduler as _task_scheduler
        _task_scheduler.start_all()
    except Exception as exc:
        log.warning("Task scheduler did not start: %s", exc)

    yield

    # Await cancellation so the loops are actually gone before the DB pool and
    # proxy resources they use are torn down.
    try:
        from app.core.scheduler import scheduler as _audit_scheduler
        await _audit_scheduler.stop()
    except Exception as exc:
        log.warning("Audit scheduler did not stop cleanly: %s", exc)
    try:
        from app.services import scheduler as _task_scheduler
        await _task_scheduler.stop_all()
    except Exception as exc:
        log.warning("Task scheduler did not stop cleanly: %s", exc)

    try:
        await proxy.shutdown_proxy_resources()
    finally:
        # Dispose pooled connections explicitly. aiosqlite runs a non-daemon
        # thread per connection, so leaving them open holds the process open.
        await close_pool()
    log.info("Sybr HUB shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sybr HUB",
        description=(
            "Audit, documentation and remote access for MSP technicians. "
            "Collects Microsoft 365, Azure, FortiGate and UniFi state into "
            "one view, turns findings into reports and tickets, and reaches "
            "customer-internal devices over managed VPN and SSH."
        ),
        version=get_version(),
        lifespan=_lifespan,
        docs_url=None,
        redoc_url=None,
    )

    @app.get(OPENAPI_DOCS_URL, include_in_schema=False)
    async def openapi_docs(_user=Depends(get_current_user)):
        """Serve the authenticated API viewer with immutable asset URLs.

        FastAPI's default uses the mutable ``swagger-ui-dist@5`` major tag.
        Pin the exact reviewed release and keep its necessary inline bootstrap
        exception scoped to this path.
        """
        base = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{_SWAGGER_UI_VERSION}"
        generated = get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            swagger_js_url=f"{base}/swagger-ui-bundle.js",
            swagger_css_url=f"{base}/swagger-ui.css",
            swagger_favicon_url="/static/icons/icon-192.png",
        )
        nonce = secrets.token_urlsafe(24)
        body = generated.body.decode("utf-8").replace(
            "<script>", f'<script nonce="{nonce}">', 1
        )
        response = HTMLResponse(body)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'self'; form-action 'self'; "
            f"script-src 'self' https://cdn.jsdelivr.net 'nonce-{nonce}'; "
            "style-src 'self' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; font-src 'self' data:; "
            "connect-src 'self'; frame-src 'none'"
        )
        return response

    # Middleware order matters: Starlette runs the *last* registered
    # middleware outermost. Rate limiting has to sit outside authentication
    # so a flood of unauthenticated requests is rejected before it costs us
    # a database round-trip per request.
    #
    # The write guard is registered first so it runs innermost — it needs the
    # account AuthMiddleware attaches, and asking "may this account change
    # anything" before knowing which account it is would answer the wrong
    # question. Security headers wrap every layer so even rate-limit and auth
    # failures receive the browser baseline. Final order: security headers,
    # rate limit, authenticate, then the write guard.
    app.add_middleware(WriteGuardMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.exception_handler(ToolkitError)
    async def _toolkit_error_handler(
        request: Request, exc: ToolkitError
    ) -> JSONResponse:
        """Map ToolkitError subclasses to their declared status codes.

        Without this, every ``raise ValidationError(...)`` in a route
        surfaced as a 500 with a stack trace instead of a 400.
        """
        if exc.status_code >= 500:
            log.exception("%s %s — %s", request.method, request.url.path, exc.message)
        else:
            log.info(
                "%s %s — %s: %s",
                request.method, request.url.path, exc.error_type, exc.message,
            )
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(exc.to_dict(), status_code=exc.status_code, headers=headers)

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Everything the handler above does not claim.

        Without this, only ``ToolkitError`` had a shape. Anything else — an
        ``AttributeError`` from a request body that was a list where a dict was
        expected, a driver error, an ``httpx`` failure escaping an integration
        — reached Starlette's default handler, which is a bare 500 whose body
        depends on how the server was started. That is the wrong answer twice:
        the client gets nothing it can act on, and in a debug configuration it
        gets a traceback that may quote a credential out of the failing call.

        So the response carries an id and nothing else, and the id is in the
        log line next to the traceback. An operator reading a support screenshot
        can find the exact event without the screenshot having to contain it.

        Starlette's ``ServerErrorMiddleware`` re-raises after this returns, so
        a test running with the default ``raise_server_exceptions=True`` still
        sees the original exception rather than a tidy 500 hiding it. That is
        the behaviour we want in both places and it is not something this
        handler has to arrange.
        """
        error_id = secrets.token_hex(6)
        log.exception(
            "500 unhandled [%s]: %s %s — %s",
            error_id, request.method, request.url.path, redact(str(exc)),
        )
        return JSONResponse(
            {
                "ok": False,
                "error": "Det oppstod en uventet feil. Oppgi feil-ID ved support.",
                "error_type": "internal_error",
                "error_id": error_id,
            },
            status_code=500,
        )

    # Auth is declared by each router (on its APIRouter, or per route), not
    # here: FastAPI >= 0.140 keeps include_router's `dependencies=` on an
    # internal wrapper rather than on the route objects, so a guard added at
    # this layer is invisible to the route audit in tests/test_web_auth.py.
    for tag, module in _API_ROUTERS:
        app.include_router(module.router, prefix="/api", tags=[tag])

    # Browser-facing paths carry no /api prefix: the SPA shell and its assets,
    # and the Guacamole tunnel the remote-access screens open directly.
    app.include_router(guacamole.router, tags=["guacamole"])
    app.include_router(frontend.router, tags=["frontend"])

    @app.get("/api/health")
    async def health() -> JSONResponse:
        """Unauthenticated liveness *and* readiness probe.

        Reports ok only when the database answers. A health check that returns
        ok while the thing the app exists to read is unreachable tells a
        monitor nothing — and the front-end's connection badge reads ``db_ok``
        to decide between "Live" and "Degradert", so leaving the field out made
        it read degraded permanently on a perfectly healthy install.

        Non-200 on failure so an external monitor can alert without parsing the
        body.
        """
        from app.core.database import get_db

        db_ok = False
        try:
            async with get_db() as conn, conn.execute("SELECT 1") as cur:
                db_ok = (await cur.fetchone())[0] == 1
        except Exception as e:
            log.warning("Health check: database unreachable — %s", e)

        return JSONResponse(
            {
                "status": "ok" if db_ok else "degraded",
                "version": get_version(),
                "db_ok": db_ok,
            },
            status_code=200 if db_ok else 503,
        )

    return app


app = create_app()
