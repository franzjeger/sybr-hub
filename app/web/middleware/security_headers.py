"""Browser security headers shared by every HTTP response."""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply the browser security baseline to every HTTP response.

    The legacy UI still has inline event and style *attributes*, but executable
    ``<script>`` blocks and ``<style>`` elements are no longer allowed. Keeping
    those two exceptions in their CSP3 ``*-src-attr`` directives prevents them
    from silently authorising injected script/style elements as well.

    The OpenAPI viewer is the only path allowed to load a pinned bundle from
    jsDelivr. Its route sets a response-specific nonce for the bootstrap; the
    fallback below stays strict for authentication errors on that path.
    """

    _APP_CSP = (
        "default-src 'self'; base-uri 'none'; object-src 'none'; "
        "frame-ancestors 'self'; form-action 'self'; "
        "script-src 'self'; script-src-elem 'self'; "
        "script-src-attr 'unsafe-inline'; "
        "style-src 'self'; style-src-elem 'self'; "
        "style-src-attr 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; "
        "connect-src 'self' ws: wss:; frame-src 'self'; "
        "worker-src 'self' blob:; manifest-src 'self'; media-src 'self' blob:"
    )
    _OPENAPI_CSP = (
        "default-src 'self'; base-uri 'none'; object-src 'none'; "
        "frame-ancestors 'self'; form-action 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "font-src 'self' data:; connect-src 'self'; frame-src 'none'"
    )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), geolocation=(), microphone=(), payment=(), "
            "usb=(), clipboard-read=(self), clipboard-write=(self)",
        )
        csp = self._OPENAPI_CSP if request.url.path == "/docs" else self._APP_CSP
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        if request.url.path.startswith("/api/auth/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response
