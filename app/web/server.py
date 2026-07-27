"""Sybr HUB FastAPI app — minimal scaffold.

This is intentionally small. The toolkit's value is in the audit
collectors, report generator, and the integration writes — not in
custom auth or middleware. We use FastAPI's standard dependency-
injection auth and add routes incrementally.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.database import close_pool, run_migrations
from app.core.exceptions import ToolkitError
from app.core.version import get_version
from app.web.middleware.auth import AuthMiddleware
from app.web.middleware.rate_limit import RateLimitMiddleware
from app.web.routes import auth, fortigate, hub, unifi, vpn

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App startup/shutdown hooks."""
    log.info("Sybr HUB starting — version %s", get_version())
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
            "Read-mostly aggregator for MSP technicians. Pulls audit "
            "results, contract data and device status into one view; "
            "lets the operator turn findings into Autotask tickets or "
            "myITprocess recommendations with a single click."
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

    app.include_router(auth.router, prefix="/api", tags=["auth"])
    app.include_router(hub.router, prefix="/api", tags=["hub"])
    # VPN management — required so the toolkit can reach customer-internal
    # devices (FortiGate / UniFi management interfaces live on the LAN,
    # not on the internet). Routes are operator-gated.
    app.include_router(vpn.router, prefix="/api", tags=["vpn"])
    app.include_router(fortigate.router, prefix="/api", tags=["fortigate"])
    app.include_router(unifi.router, prefix="/api", tags=["unifi"])

    @app.get("/api/health")
    async def health() -> dict[str, str | bool]:
        return {"status": "ok", "version": get_version()}

    return app


app = create_app()
