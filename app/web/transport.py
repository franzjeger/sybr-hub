"""Is this connection safe to put a password on?

The README has always said plain HTTP is for a loopback quick-start and that
anything reaching this app from another machine belongs behind TLS. Nothing
enforced it. ``_cookie_secure`` in the auth routes decided a *cookie flag* and
was mistaken for the rule itself — but ``/api/auth/login`` returns the access
and refresh tokens in the response body too, so a client that ignores cookies
authenticated over cleartext HTTP from anywhere on the network and nothing
objected.

Two predicates, deliberately not one, because they answer different questions:

``is_secure_transport``
    Did this request actually arrive over TLS? Only the scheme and a
    forwarded-proto header can answer that.

``is_local_quickstart``
    Is this the documented "open localhost:8099 and look around" case? That
    needs *both* ends local: a request from 127.0.0.1 carrying a public Host
    header is a local reverse proxy, not a quick-start, and it is exactly the
    shipped deployment — ``tailscale serve`` terminates TLS and forwards to
    loopback.

Which is why the enforcement below keys off the client address alone and the
cookie flag keys off both. A local proxy that terminated TLS is trusted; a
laptop on the same LAN talking cleartext to port 8099 is not.

``X-Forwarded-Proto`` is honoured without qualification, which is a real
assumption: a client that can reach this port directly can also claim
``https``. It holds because the deployments that set it — the systemd unit
binds loopback, and ``tailscale serve`` is the only thing in front of it — are
ones where nothing untrusted can reach the port at all. An install that binds a
routable interface and trusts the header has already lost, and the startup
check in ``main.py`` refuses that combination.
"""

from __future__ import annotations

import ipaddress
import logging
import os

from fastapi import Request

logger = logging.getLogger(__name__)

# The escape hatch, for a TLS terminator we cannot see from inside the process
# — one that strips X-Forwarded-Proto, or a tunnel that presents as plain HTTP
# on a socket we have no way to inspect. Named for what it permits rather than
# what it disables, so nobody sets it without reading it.
ENV_ALLOW_INSECURE = "SYBR_ALLOW_INSECURE_AUTH"

# Additional trusted proxies *behind* the one terminating at this process. The
# shipped deployment has none, hence a default of 0 — see client_ip().
ENV_TRUSTED_PROXY_HOPS = "SYBR_TRUSTED_PROXY_HOPS"


def insecure_auth_allowed() -> bool:
    """Whether the operator has explicitly accepted cleartext credentials."""
    return os.environ.get(ENV_ALLOW_INSECURE) == "1"


def is_loopback_address(value: str) -> bool:
    """Whether *value* names this host.

    ``testclient`` is Starlette's synthetic client address. Treating it as
    loopback keeps the test suite on the quick-start path rather than making
    every existing test negotiate TLS it has no way to provide.
    """
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return value.lower() in {"localhost", "testclient"}


def client_is_loopback(request: Request) -> bool:
    """Whether the request came from this host."""
    return bool(request.client and is_loopback_address(request.client.host))


def is_secure_transport(request: Request) -> bool:
    """Whether this request arrived over TLS, directly or via a terminator."""
    if request.url.scheme == "https":
        return True
    forwarded = request.headers.get("x-forwarded-proto", "")
    return forwarded.split(",", 1)[0].strip().lower() == "https"


def is_local_quickstart(request: Request) -> bool:
    """Whether this is the documented loopback-only HTTP quick-start."""
    return client_is_loopback(request) and is_loopback_address(request.url.hostname or "")


def credentials_may_cross(request: Request) -> bool:
    """Whether it is acceptable for a secret to travel on this connection.

    A password, an access token or a refresh token. Loopback is fine because
    the bytes never reach a network interface; TLS is fine because that is the
    whole point; anything else is refused unless the operator opted in.
    """
    return is_secure_transport(request) or client_is_loopback(request) or insecure_auth_allowed()


def client_ip(request: Request) -> str:
    """Return the address to attribute this request to.

    ``X-Forwarded-For`` is a list a *client* can start and each proxy appends
    to, so only the entries a trusted proxy wrote can be believed. Counting
    from the right is therefore the whole game, and the count has to be right:
    a reverse proxy appends *the address it received the request from*, not
    its own, so one terminator in front means the rightmost entry is the
    client and there is nothing to skip.

    ``SYBR_TRUSTED_PROXY_HOPS`` is the number of *additional* proxies behind
    the one that terminates here — 0 for the shipped deployment, where
    ``tailscale serve`` forwards straight to loopback. An earlier version
    defaulted to 1 and returned ``parts[-2]``, which on that exact deployment
    handed back the attacker-supplied leading entry: a rotating header value
    then bought a fresh rate-limit bucket per request, and the login log
    recorded whatever the caller wrote.

    Anything left of the trusted entries is caller-controlled and ignored. The
    header is only consulted at all when the direct peer is loopback; a
    request that reaches the port from elsewhere is attributed to where it
    actually came from.
    """
    direct_ip = request.client.host if request.client else ""
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded or not is_loopback_address(direct_ip):
        return direct_ip

    parts = [p.strip() for p in forwarded.split(",") if p.strip()]
    if not parts:
        return direct_ip

    try:
        hops = max(0, int(os.environ.get(ENV_TRUSTED_PROXY_HOPS, "0")))
    except ValueError:
        logger.warning(
            "%s is not an integer; treating it as 0 (one terminator, none behind it)",
            ENV_TRUSTED_PROXY_HOPS,
        )
        hops = 0

    # parts[-1] is what the terminator wrote. Each extra trusted hop moves one
    # further left; a header shorter than the configured chain means the chain
    # is mis-configured, so fall back to the leftmost entry it did write rather
    # than indexing past the front.
    if hops >= len(parts):
        return parts[0]
    return parts[-(hops + 1)]
