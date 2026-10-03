"""A FortiGate config backup is a configuration, or it is a failure.

backup_config used to call the HTTP client directly, check no status but 405,
and store whatever came back. A 500, a rejected token's error envelope or a
login page was written to disk as a "backup" and reported as a success, which
is a restore point that restores nothing, discovered on the day it is needed.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.encryption import encrypted_read_text
from app.modules.fortigate_audit.client import FortiGateClient
from app.services import fortigate_api

CONFIG = (
    "#config-version=FGT60F-7.4.3-FW-build2573-240201:opmode=0:vdom=0:user=msp_api_admin\n"
    "#conf_file_ver=1234567890\n"
    "#buildno=2573\n"
    "config system global\n"
    '    set hostname "FGT-ACME"\n'
    "end\n"
)


@pytest.fixture()
def backup_dir(tmp_path, monkeypatch):
    # get_audit_dir falls back to the operator's Documents folder.
    monkeypatch.setattr(fortigate_api, "get_audit_dir", lambda: tmp_path)
    return tmp_path / "acme" / "fortigate_backups"


@pytest.fixture()
def firewall(monkeypatch):
    """Route the client's requests to *handler*; returns the request log."""
    seen: list[str] = []
    state: dict = {}

    def _build(config, token):
        client = FortiGateClient("fg.test", token, port=8443, verify_ssl=False)

        def _handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.method)
            return state["handler"](request)

        client._client = httpx.AsyncClient(
            base_url="https://fg.test:8443", transport=httpx.MockTransport(_handler)
        )
        return client

    async def _no_wait(_seconds):
        return None

    monkeypatch.setattr(fortigate_api, "_build_client", _build)
    monkeypatch.setattr("app.integrations.http_retry.asyncio.sleep", _no_wait)

    def _set(handler):
        state["handler"] = handler
        return seen

    return _set


async def _backup():
    return await fortigate_api.backup_config({"FortiGateHost": "fg.test"}, "token", "acme")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="Internal Server Error"),
        httpx.Response(403, json={"http_status": 403, "status": "error"}),
        httpx.Response(200, json={"http_status": 403, "status": "error", "results": {}}),
        httpx.Response(200, html="<html><body><form action='/logincheck'></form></body></html>"),
        httpx.Response(200, text=""),
    ],
)
async def test_anything_but_a_configuration_is_a_failure(firewall, backup_dir, response):
    firewall(lambda _req: response)
    result = await _backup()
    assert result["ok"] is False, result
    assert not backup_dir.exists() or not any(backup_dir.iterdir()), "a non-config was stored"


async def test_an_unreachable_firewall_is_a_failure(firewall, backup_dir):
    def _refuse(request):
        raise httpx.ConnectError("refused", request=request)

    firewall(_refuse)
    result = await _backup()
    assert result["ok"] is False
    assert not backup_dir.exists() or not any(backup_dir.iterdir())


async def test_a_configuration_is_stored_and_reported(firewall, backup_dir):
    firewall(lambda _req: httpx.Response(200, text=CONFIG))
    result = await _backup()
    assert result["ok"] is True, result
    assert encrypted_read_text(backup_dir / result["filename"]) == CONFIG


async def test_older_firmware_falls_back_to_get(firewall, backup_dir):
    seen = firewall(
        lambda req: (
            httpx.Response(405) if req.method == "POST" else httpx.Response(200, text=CONFIG)
        )
    )
    result = await _backup()
    assert result["ok"] is True, result
    assert seen == ["POST", "GET"]


async def test_a_json_wrapped_configuration_is_accepted(firewall, backup_dir):
    firewall(lambda _req: httpx.Response(200, json={"results": CONFIG}))
    result = await _backup()
    assert result["ok"] is True, result
    assert encrypted_read_text(backup_dir / result["filename"]) == CONFIG
