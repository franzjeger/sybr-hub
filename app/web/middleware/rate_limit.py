"""Simple in-memory rate limiting middleware.

Tracks request counts per IP using a module-level dict with per-minute
sliding windows.  No external dependencies — just dicts and timestamps.

Limits:
    - General:  120 requests/minute per IP
    - Sensitive: 10 requests/minute for VPN and audit endpoints
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────────────

GENERAL_LIMIT = 600       # requests per minute. Dashboard bursts 15-20
                          # endpoints on load; with tab refresh + navigation
                          # 200/min was easy to hit from a single user.
SENSITIVE_LIMIT = 60      # requests per minute (VPN auth uses multiple calls)
WINDOW = 60               # seconds

# Prefixes that get the stricter limit.
_SENSITIVE_PREFIXES: tuple[str, ...] = (
    "/api/vpn/",
    "/api/audit/stream",
    "/api/audit/bulk",
    "/api/setup/stream",
)
# Audit read-only endpoints (progress, sections, presets, scope) use the general limit.

# ── Storage ─────────────────────────────────────────────────────────────────
# { ip: [ (timestamp, bucket_key), ... ] }
# bucket_key is "general" or "sensitive" so one dict handles both.
_hits: dict[str, list[float]] = defaultdict(list)
_sensitive_hits: dict[str, list[float]] = defaultdict(list)
_last_cleanup: float = time.monotonic()


def _cleanup() -> None:
    """Remove entries older than the window.  Runs at most once per WINDOW."""
    global _last_cleanup
    now = time.monotonic()
    if now - _last_cleanup < WINDOW:
        return
    _last_cleanup = now
    cutoff = now - WINDOW
    for store in (_hits, _sensitive_hits):
        dead_keys = []
        for ip, timestamps in store.items():
            store[ip] = [t for t in timestamps if t > cutoff]
            if not store[ip]:
                dead_keys.append(ip)
        for ip in dead_keys:
            del store[ip]


def _is_sensitive(path: str) -> bool:
    return any(path.startswith(p) for p in _SENSITIVE_PREFIXES)


def _client_ip(request: Request) -> str:
    """Best-effort real IP — trust X-Forwarded-For only from localhost."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and request.client and request.client.host in ("127.0.0.1", "::1"):
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Middleware ──────────────────────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Return 429 when a client exceeds the per-minute request budget."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        _cleanup()

        now = time.monotonic()
        cutoff = now - WINDOW
        ip = _client_ip(request)
        path = request.url.path

        # --- sensitive-endpoint check ---
        if _is_sensitive(path):
            bucket = _sensitive_hits[ip]
            bucket[:] = [t for t in bucket if t > cutoff]
            if len(bucket) >= SENSITIVE_LIMIT:
                logger.warning("Rate limit (sensitive) hit: %s on %s", ip, path)
                return JSONResponse(
                    {"error": "Too many requests — try again in a minute"},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            bucket.append(now)

        # --- general check (always) ---
        bucket = _hits[ip]
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= GENERAL_LIMIT:
            logger.warning("Rate limit (general) hit: %s on %s", ip, path)
            return JSONResponse(
                {"error": "Too many requests — try again in a minute"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        bucket.append(now)

        return await call_next(request)
