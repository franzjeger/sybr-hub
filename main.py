"""Sybr HUB entry point.

Run with:
    python main.py                  # loopback only (http://127.0.0.1:8099)
    SYBR_HUB_HOST=0.0.0.0 python main.py   # needs TLS, see below
    SYBR_HUB_PORT=9000 python main.py

The default bind is loopback. It used to be 0.0.0.0, which meant the
documented quick-start — "run this, open localhost:8099" — also published a
cleartext login form to every machine on the network, without the person
running it choosing that or being told. Exposure is now something you ask for.

Asking for it requires TLS. The application refuses cleartext credentials from
a non-loopback client (see app/web/transport.py), so binding a routable
interface without a certificate produces an app nobody can log into — better to
say so here than to let it start and fail one request later.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import sys


def _is_loopback_bind(host: str) -> bool:
    """Whether this bind address reaches only the local machine.

    An empty host and 0.0.0.0/:: mean "every interface" and are not loopback.
    A name we cannot parse is treated as routable: guessing generously about
    an address we do not understand is the wrong direction to be wrong in.
    """
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_exposure(host: str, ssl_cert: str | None) -> str | None:
    """Return an error message if this bind would publish cleartext auth."""
    from app.web.transport import ENV_ALLOW_INSECURE, insecure_auth_allowed

    if _is_loopback_bind(host) or ssl_cert or insecure_auth_allowed():
        return None
    return (
        f"Refusing to start: SYBR_HUB_HOST={host!r} publishes Sybr HUB on a "
        "routable interface with no TLS, so passwords and tokens would cross "
        "the network in cleartext.\n\n"
        "  Pick one:\n"
        "    - leave SYBR_HUB_HOST unset to listen on loopback only\n"
        "    - set SYBR_HUB_SSL_CERT and SYBR_HUB_SSL_KEY to serve HTTPS\n"
        "    - put a TLS terminator in front of a loopback bind "
        "(`tailscale serve` does this)\n"
        f"    - set {ENV_ALLOW_INSECURE}=1 if a terminator this process "
        "cannot see is already handling it"
    )


def run() -> None:
    logging.basicConfig(
        level=os.environ.get("SYBR_HUB_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    )

    import uvicorn

    host = os.environ.get("SYBR_HUB_HOST", "127.0.0.1")
    port = int(os.environ.get("SYBR_HUB_PORT", "8099"))

    # TLS — optional. If both env vars are set we serve HTTPS; otherwise plain
    # HTTP, which the check below confines to loopback.
    ssl_cert = os.environ.get("SYBR_HUB_SSL_CERT")
    ssl_key = os.environ.get("SYBR_HUB_SSL_KEY")

    problem = _check_exposure(host, ssl_cert)
    if problem:
        print(f"\n{problem}\n", file=sys.stderr)
        raise SystemExit(2)

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
