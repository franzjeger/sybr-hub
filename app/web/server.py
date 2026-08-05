"""Sybr HUB FastAPI app.

An application factory and nothing else: middleware, the error handler, and
the router table. Every endpoint lives in ``app.web.routes`` — including the
SPA shell and static assets (``routes.frontend``) and the Guacamole reverse
proxy (``routes.guacamole``), so this file stays readable as the map of what
the app exposes.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.database import close_pool, run_migrations
from app.core.encryption import verify_master_key_available
from app.core.exceptions import ToolkitError
from app.core.version import get_version
from app.web.middleware.auth import AuthMiddleware
from app.web.middleware.rate_limit import RateLimitMiddleware
from app.web.routes import (
    also,
    audit,
    auth,
    backup,
    claude,
    customers,
    dashboard,
    dashboard_ws,
    autotask,
    docs,
    fortigate,
    frontend,
    gdap,
    guacamole,
    history,
    hub,
    itglue,
    pentest,
    provisioning,
    proxy,
    reports,
    settings,
    ssh,
    tailscale,
    terminal,
    tls,
    unifi,
    uniweb,
    vpn,
    workshop,
)

log = logging.getLogger(__name__)

# Mounted under /api, in the order the operator meets them: authentication,
# then the customer/audit core, then integrations and connectivity.
_API_ROUTERS = (
    ("auth", auth),
    ("settings", settings),
    ("vpn", vpn),
    ("hub", hub),
    ("customers", customers),
    ("dashboard", dashboard),
    ("dashboard_ws", dashboard_ws),
    ("audit", audit),
    ("reports", reports),
    ("history", history),
    ("autotask", autotask),
    ("docs", docs),
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
    yield
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
    )

    # Middleware order matters: Starlette runs the *last* registered
    # middleware outermost. Rate limiting has to sit outside authentication
    # so a flood of unauthenticated requests is rejected before it costs us
    # a database round-trip per request.
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)

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
