"""Technician-only areas refuse a viewer at the server, not just in the menu.

The feature table drove the interface, but only one route module asked it:
a viewer who skipped the hidden menu could read VPN profiles, the SSH host
list, Tailscale inventory and the AI console. Each module whose every route
belongs to one technician feature now carries that feature on its router.
"""

from __future__ import annotations

import pytest

from app.models.user import Role
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    _reset_middleware_state,
    _scope_env,
    client,
    login,
)

GATED = [
    "/api/ssh/hosts",
    "/api/browser/status",
    "/api/rdp/status",
    "/api/tailscale/status",
    "/api/pentest/capabilities",
    "/api/claude/status",
    "/api/tls/auto-discover",
    "/api/vpn/profiles",
    "/api/vpn/status",
]
FEATURE_REFUSAL = "Kontoen din har ikke tilgang til denne delen av verktøyet."


@pytest.mark.parametrize("path", GATED)
async def test_a_viewer_is_refused(client, path):
    r = client.get(path, headers=await login("viewer", role=Role.viewer, all_customers=True))
    assert r.status_code == 403, r.text
    assert FEATURE_REFUSAL in r.text


@pytest.mark.parametrize("path", GATED)
async def test_a_technician_passes_the_gate(client, path):
    r = client.get(path, headers=await login("tech", all_customers=True))
    assert FEATURE_REFUSAL not in r.text, (path, r.status_code)
