"""/rdp/launch starts a client process on the hub with a stored password.

Three ways that went wrong: a newline in the username or domain injected keys
into a Remmina profile (including the commands Remmina runs around a
connection), the profile sat at a predictable path in /tmp, and the password
rode on xfreerdp's command line where /proc shows it to every local account.
"""

from __future__ import annotations

import subprocess
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.database import run_migrations
from app.core.rbac import grant_access, set_can_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app


@pytest.fixture(autouse=True)
def _reset_state():
    import app.web.middleware.rate_limit as rl

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _init_db(tmp_path, monkeypatch):
    import app.core.database as db_mod
    from app.services import ssh_manager

    db_mod.DB_PATH = tmp_path / "test.db"
    monkeypatch.setattr(ssh_manager, "SSH_KEYS_DIR", tmp_path / "ssh_keys")
    await run_migrations()
    yield


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


class _FakeStdin:
    def __init__(self):
        self.data = b""
        self.closed = False

    def write(self, data: bytes) -> int:
        self.data += data
        return len(data)

    def close(self) -> None:
        self.closed = True


class _FakePopen:
    launched: ClassVar[list[_FakePopen]] = []

    def __init__(self, args, **kwargs):
        self.args = list(args)
        self.kwargs = kwargs
        self.stdin = _FakeStdin() if kwargs.get("stdin") is subprocess.PIPE else None
        _FakePopen.launched.append(self)


@pytest.fixture()
def installed(monkeypatch):
    """Pretend exactly the named clients are on PATH, and record launches."""
    _FakePopen.launched = []
    clients: set[str] = set()
    monkeypatch.setattr(
        "app.web.routes.ssh.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in clients else None,
    )
    monkeypatch.setattr("app.web.routes.ssh.subprocess.Popen", _FakePopen)
    monkeypatch.setattr("app.web.routes.ssh.sys.platform", "linux")
    return clients


async def _setup(client) -> tuple[dict, str]:
    user = await create_user("tech", "Test1234!xyz", "Tech", role=Role.technician)
    await grant_access(user.id, "acme")
    await set_can_write(user.id, True)
    hdr = {"Authorization": f"Bearer {await create_access_token(await get_user_by_id(user.id))}"}
    resp = client.post(
        "/api/ssh/hosts",
        headers=hdr,
        json={
            "label": "TS01",
            "hostname": "10.20.1.30",
            "username": "Administrator",
            "auth_method": "password",
            "password": "rdp-secret",
            "device_type": "windows",
            "customer_id": "acme",
        },
    )
    assert resp.status_code == 200, resp.text
    return hdr, resp.json()["host"]["id"]


async def test_the_password_goes_to_stdin_not_argv(client, installed):
    installed.add("xfreerdp3")
    hdr, host_id = await _setup(client)

    resp = client.post("/api/rdp/launch", headers=hdr, json={"host_id": host_id})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "client": "xfreerdp3"}

    [proc] = _FakePopen.launched
    assert not any("rdp-secret" in arg for arg in proc.args), proc.args
    assert not any(arg.startswith("/p:") for arg in proc.args)
    assert "/from-stdin:force" in proc.args
    assert proc.stdin.data == b"rdp-secret\n"
    assert proc.stdin.closed


async def test_the_older_xfreerdp_gets_the_same_treatment(client, installed):
    installed.add("xfreerdp")
    hdr, host_id = await _setup(client)

    resp = client.post("/api/rdp/launch", headers=hdr, json={"host_id": host_id})
    assert resp.json()["client"] == "xfreerdp"
    [proc] = _FakePopen.launched
    assert not any("rdp-secret" in arg for arg in proc.args)
    assert proc.stdin.data == b"rdp-secret\n"


async def test_remmina_is_never_launched(client, installed, tmp_path, monkeypatch):
    installed.add("remmina")
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    hdr, host_id = await _setup(client)

    resp = client.post("/api/rdp/launch", headers=hdr, json={"host_id": host_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is False
    assert _FakePopen.launched == []
    assert not (tmp_path / "msp-rdp").exists(), "a Remmina profile was written"


@pytest.mark.parametrize(
    "over",
    [
        {"username": "x\npostcommand=touch /tmp/pwned"},
        {"username": "a=b"},
        {"domain": "CORP\nprecommand=id"},
        {"domain": "corp domain"},
    ],
)
async def test_username_and_domain_cannot_carry_control_characters(client, installed, over):
    installed.add("xfreerdp3")
    hdr, host_id = await _setup(client)

    resp = client.post("/api/rdp/launch", headers=hdr, json={"host_id": host_id, **over})
    assert resp.status_code == 400, resp.text
    assert _FakePopen.launched == []


async def test_another_username_does_not_get_the_stored_password(client, installed):
    """The stored password was entered for the stored account."""
    installed.add("xfreerdp3")
    hdr, host_id = await _setup(client)

    resp = client.post(
        "/api/rdp/launch", headers=hdr, json={"host_id": host_id, "username": "backup.admin"}
    )
    assert resp.status_code == 200, resp.text
    [proc] = _FakePopen.launched
    assert "/u:backup.admin" in proc.args
    assert "/from-stdin:force" not in proc.args
    assert proc.stdin is None


# ── The request body ─────────────────────────────────────────────────────────


async def test_a_caller_supplied_host_is_accepted_and_never_used(client, installed):
    """The old client sent ``host``; the address must still be the registered one."""
    installed.add("xfreerdp3")
    hdr, host_id = await _setup(client)

    resp = client.post(
        "/api/rdp/launch",
        headers=hdr,
        json={"host": "evil.example", "host_id": host_id, "username": "", "port": 3389},
    )

    assert resp.status_code == 200, resp.text
    [proc] = _FakePopen.launched
    assert "/v:10.20.1.30:3389" in proc.args


@pytest.mark.parametrize(
    "over",
    [{"port": "rdp"}, {"port": [3389]}, {"username": 7}, {"password": ["x"]}, {"hots_id": "x"}],
)
async def test_a_wrong_type_or_unknown_key_is_a_422_not_a_500(client, installed, over):
    installed.add("xfreerdp3")
    hdr, host_id = await _setup(client)

    resp = client.post("/api/rdp/launch", headers=hdr, json={"host_id": host_id, **over})

    assert resp.status_code == 422, resp.text
    assert resp.json()["error_type"] == "validation_error"
    assert _FakePopen.launched == []


async def test_an_out_of_range_port_keeps_its_own_message(client, installed):
    installed.add("xfreerdp3")
    hdr, host_id = await _setup(client)

    resp = client.post("/api/rdp/launch", headers=hdr, json={"host_id": host_id, "port": 70000})

    assert resp.status_code == 400
    assert resp.json()["error"] == "Ugyldig RDP-port"


async def test_a_missing_host_id_keeps_its_own_message(client, installed):
    hdr, _host_id = await _setup(client)

    resp = client.post("/api/rdp/launch", headers=hdr, json={"host_id": None})

    assert resp.status_code == 400
    assert resp.json()["error"] == "Velg en registrert host"


# ── Health check and SSH config: which hosts ─────────────────────────────────


@pytest.mark.parametrize(
    "path,marker", [("/api/ssh/hosts/health", "id"), ("/api/ssh/config/generate", "10.20.1.30")]
)
async def test_an_empty_selection_still_means_the_callers_hosts(client, path, marker, monkeypatch):
    from app.services import ssh_manager

    async def _no_connections(host_ids):
        return [{"host_id": h, "reachable": True} for h in host_ids]

    monkeypatch.setattr(ssh_manager, "health_check", _no_connections)
    hdr, host_id = await _setup(client)

    resp = client.post(path, headers=hdr, json={})

    assert resp.status_code == 200, resp.text
    assert (host_id if marker == "id" else marker) in resp.text


@pytest.mark.parametrize("path", ["/api/ssh/hosts/health", "/api/ssh/config/generate"])
@pytest.mark.parametrize("body", [{"host_ids": "h1"}, {"host_ids": [1]}, {"hosts": []}, [1]])
async def test_a_bad_host_selection_is_a_422(client, path, body):
    hdr, _host_id = await _setup(client)

    resp = client.post(path, headers=hdr, json=body)

    assert resp.status_code == 422, resp.text
