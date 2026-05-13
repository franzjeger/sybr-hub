"""Sybr HUB entry point.

Run with:
    python main.py                  # uses defaults (https://0.0.0.0:8099)
    SYBR_HUB_HOST=127.0.0.1 python main.py
    SYBR_HUB_PORT=9000 python main.py
"""

from __future__ import annotations

import logging
import os
import sys


def run() -> None:
    logging.basicConfig(
        level=os.environ.get("SYBR_HUB_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    )

    import uvicorn

    host = os.environ.get("SYBR_HUB_HOST", "0.0.0.0")
    port = int(os.environ.get("SYBR_HUB_PORT", "8099"))

    # TLS — optional. If both env vars are set we serve HTTPS; otherwise
    # plain HTTP (only safe behind a reverse proxy / on a trusted LAN).
    ssl_cert = os.environ.get("SYBR_HUB_SSL_CERT")
    ssl_key = os.environ.get("SYBR_HUB_SSL_KEY")

    print(f"  Sybr HUB — http{'s' if ssl_cert else ''}://{host}:{port}", file=sys.stderr)

    uvicorn.run(
        "app.web.server:app",
        host=host,
        port=port,
        ssl_certfile=ssl_cert,
        ssl_keyfile=ssl_key,
        log_level="info",
    )


if __name__ == "__main__":
    run()
