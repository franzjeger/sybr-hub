"""The Azure device-code status carries an Entra access token: owner only.

Any signed-in user who knew a device code could poll it and read the token.
"""

from __future__ import annotations

import pytest

from app.core.auth import get_user_by_username
from app.web.routes import vpn as vpn_routes
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    _reset_middleware_state,
    _scope_env,
    client,
    login,
)


@pytest.fixture()
def token_ready(monkeypatch):
    monkeypatch.setattr(
        "app.services.vpn_backends.azure.get_device_code_status",
        lambda code: {"status": "complete", "token": "entra-token", "error": None},
    )
    vpn_routes._device_code_owner.clear()
    yield
    vpn_routes._device_code_owner.clear()


async def test_only_the_user_who_started_the_flow_reads_the_token(client, token_ready):
    owner = await login("owner", all_customers=True)
    other = await login("other", all_customers=True)
    vpn_routes._device_code_owner["dc-1"] = str((await get_user_by_username("owner")).id)

    refused = client.get("/api/vpn/azure/device-code/status?device_code=dc-1", headers=other)
    assert refused.status_code == 404
    assert "entra-token" not in refused.text

    ok = client.get("/api/vpn/azure/device-code/status?device_code=dc-1", headers=owner)
    assert ok.status_code == 200 and ok.json()["token"] == "entra-token"
    # Finished flows are forgotten, so the token cannot be read twice.
    again = client.get("/api/vpn/azure/device-code/status?device_code=dc-1", headers=owner)
    assert again.status_code == 404
