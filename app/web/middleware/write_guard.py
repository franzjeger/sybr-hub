"""Read is what an account can do. Changing anything is a grant somebody made.

Enforced here rather than on each route, and that is the whole design. There
are 163 mutating endpoints; a decorator on each is 163 chances to forget one,
and the one forgotten is the one that matters. A request that changes something
is denied unless the account holds ``can_write`` — not because a rule was
attached to that route, but because nothing exempted it.

So the interesting content of this module is the exemption table, and it is
meant to be *read*. One list, one line of reasoning each, rather than a
decorator scattered across forty files. When in doubt an endpoint is left out
of it: a read-only user meeting a wall is recoverable in a way that a read-only
user reconfiguring somebody's firewall is not.

Two capabilities, because saving a note and pushing a Conditional Access policy
into a customer's production tenant are different risks:

* ``can_write`` — change Sybr HUB itself.
* ``tenant_write`` — change a customer's Microsoft tenant. Checked separately
  by ``require_tenant_write``, and it now requires ``can_write`` too.

Refusals are logged with the account and the path, because "who tried" is the
question nobody asks until they need the answer.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# ── Signing in, and looking after your own account ──────────────────────────
# None of these can be gated on a capability the account may not have, and the
# last one is how somebody with no rights at all still rotates their password.
SESSION = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/refresh",
    "/api/auth/setup",
    "/api/auth/change-password",
}

# ── Changing what you are looking at, not what is ───────────────────────────
# switch is how the whole interface navigates between customers. Gating it
# would leave a read-only account able to read exactly one tenant.
NAVIGATION = {
    "/api/customers/switch",
    "/api/history/load",
    "/api/settings/language",
}

# ── Questions that happen to be POSTs ───────────────────────────────────────
# A lookup with a body too large for a query string. Each reaches out and
# reports back; none of them leaves anything behind.
LOOKUPS = {
    "/api/dns/check",
    "/api/dns/check-bulk",
    "/api/tls/check",
    "/api/tls/scan",
    "/api/proxy/fetch",
    "/api/audit/validate-permissions",
    "/api/also/test",
    "/api/autotask/test",
    "/api/itglue/test",
    "/api/itglue/organizations",
    "/api/fortigate/test",
    "/api/unifi/test",
    "/api/unifi/test-device",
    "/api/tailscale/test",
    "/api/email/test",
    "/api/ssh/hosts/health",
}

# ── Producing something to read ─────────────────────────────────────────────
# These write a file, so they are not literally free of side effects — but what
# they produce is a document for the person who asked, and refusing to let a
# read-only account read is a strange reading of read-only. Deleting and
# cleaning up the archive is *not* here.
DOCUMENTS = {
    "/api/report/csv",
    "/api/report/generate",
    "/api/reports/batch-summary",
    "/api/export/excel",
    "/api/pentest/report",
}

ALLOWED_WITHOUT_WRITE = SESSION | NAVIGATION | LOOKUPS | DOCUMENTS

_DENIED = (
    "Denne handlingen endrer noe og krever skrivetilgang. "
    "Kontoen din har lesetilgang."
)


def _is_exempt(path: str) -> bool:
    """Exact match only.

    A prefix rule would quietly cover endpoints added underneath one of these
    later — which is how an exemption list stops describing what it exempts.
    """
    return path.rstrip("/") in ALLOWED_WITHOUT_WRITE


class WriteGuardMiddleware(BaseHTTPMiddleware):
    """Deny anything that changes state unless the account may change state."""

    async def dispatch(self, request, call_next):
        if request.method in READ_METHODS or _is_exempt(request.url.path):
            return await call_next(request)

        user = getattr(request.state, "user", None)
        if user is None:
            # Unauthenticated. AuthMiddleware owns that answer, including for
            # the routes that are deliberately open; second-guessing it here
            # would turn a 401 into a confusing 403.
            return await call_next(request)

        if not getattr(user, "can_write", False):
            logger.warning(
                "403 write-denied: user=%s role=%s %s %s",
                user.username, getattr(user.role, "value", user.role),
                request.method, request.url.path,
            )
            return JSONResponse({"error": _DENIED}, status_code=403)

        return await call_next(request)
