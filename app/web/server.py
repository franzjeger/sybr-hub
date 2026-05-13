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

from fastapi import FastAPI

from app.core.database import run_migrations
from app.core.version import get_version
from app.web.routes import fortigate, hub, unifi, vpn

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App startup/shutdown hooks."""
    log.info("Sybr HUB starting — version %s", get_version())
    await run_migrations()
    yield
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
