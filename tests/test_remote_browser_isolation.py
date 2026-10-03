"""The remote browser must not inherit the hub's identity, secrets or files.

Chromium runs as the hub's service account and is driven over VNC by a
technician, so whatever they type into the omnibox bypasses
``_validate_browser_target``. Three things leaked before:

* ``browser_start`` copied ``os.environ`` into Chromium, Xvfb and x11vnc, so
  the browser held GUACAMOLE_PASS, the master-key variables and the systemd
  credentials directory;
* ``browser_navigate`` restarted Chromium with the hub's environment and no
  ``--user-data-dir``, so it fell back to the service account's persistent
  default profile and shared cookies and saved logins between sessions;
* nothing stopped the browser reading the hub's data, config or key backups.

These tests run the real routes with ``subprocess.Popen`` replaced by a
recorder and assert what would have been launched. The sandbox checks replay
the bubblewrap argv as a mount table, so they test what the browser could
read rather than which flags happen to be present.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.exceptions import IntegrationError
from app.models.remote import BrowserTarget
from app.models.user import Role, User
from app.web.routes import proxy

CHROMIUM = "/usr/lib/chromium/chromium"
BWRAP = "/usr/bin/bwrap"

INHERITED_SECRETS = {
    "GUACAMOLE_PASS": "guac-admin-password",
    "AWS_SECRET_ACCESS_KEY": "aws-secret-value",
    "MSP_GUACAMOLE_HOSTS": "guac.internal.example",
    "SYBR_HUB_SSL_KEY": "/etc/ssl/private/sybr-hub.key",
    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/990/bus",
    "SSH_AUTH_SOCK": "/run/user/990/ssh-agent.sock",
    "XAUTHORITY": "/var/lib/sybr-hub/home/.Xauthority",
}
ALLOWED_ENV = {"DISPLAY", "HOME", "TMPDIR", "PATH", "LANG", "LC_ALL", "TZ"}


class _Proc:
    def __init__(self, argv, env, exit_code=None):
        self.argv = list(argv)
        self.env = dict(env or {})
        self.pid = 4242
        self.returncode = exit_code
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def _user(uid: str = "tech-1") -> User:
    return User(
        id=uid,
        username=uid,
        display_name=uid,
        role=Role.technician,
        created_at=datetime.now(UTC),
        is_active=True,
        can_write=True,
    )


def _json_request(body: dict) -> BrowserTarget:
    """The body the route's model would parse from this JSON."""
    return BrowserTarget.model_validate(body)


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    """Run the browser routes with every external process and service faked."""
    for key, value in INHERITED_SECRETS.items():
        monkeypatch.setenv(key, value)
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials))

    state = {"bwrap": None, "chromium_exit": None}
    launched: list[_Proc] = []

    def _popen(argv, stdout=None, stderr=None, env=None):
        is_chromium = any(str(a).startswith("--user-data-dir=") for a in argv)
        proc = _Proc(argv, env, exit_code=state["chromium_exit"] if is_chromium else None)
        launched.append(proc)
        return proc

    async def _no_sleep(_delay):
        return None

    async def _guac_token():
        return "guac-backend-token"

    async def _no_pending():
        return 0

    async def _vnc_connection(*_a, **_k):
        return {"identifier": "42"}

    async def _deleted(*_a, **_k):
        return True

    tools = {"Xvfb": "/usr/bin/Xvfb", "x11vnc": "/usr/bin/x11vnc"}
    monkeypatch.setattr(
        proxy.shutil,
        "which",
        lambda name, *a, **k: state["bwrap"] if name == "bwrap" else tools.get(name),
    )
    monkeypatch.setattr(proxy, "_chromium_binary", lambda: CHROMIUM)
    monkeypatch.setattr(proxy.subprocess, "Popen", _popen)
    monkeypatch.setattr(proxy.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(proxy, "_docker_host_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(proxy, "_guac_login", _guac_token)
    monkeypatch.setattr(proxy, "_retry_pending_guacamole_cleanup", _no_pending)
    monkeypatch.setattr(proxy, "_guac_create_vnc_connection", _vnc_connection)
    monkeypatch.setattr(proxy, "_guac_delete_with_fresh_token", _deleted)
    monkeypatch.setattr(proxy, "_browser_session", {})

    class Launcher:
        procs = launched

        @staticmethod
        def sandbox(available: bool) -> None:
            state["bwrap"] = BWRAP if available else None

        @staticmethod
        def chromium_exits_with(code) -> None:
            state["chromium_exit"] = code

        @staticmethod
        def chromium() -> list[_Proc]:
            return [p for p in launched if any(a.startswith("--user-data-dir=") for a in p.argv)]

    yield Launcher
    # Never leave a session directory behind, whatever the test did.
    session_dir = proxy._browser_session.get("session_dir")
    if session_dir:
        proxy._stop_browser_session()


def _profile_dir(proc: _Proc) -> Path:
    flag = next(a for a in proc.argv if a.startswith("--user-data-dir="))
    return Path(flag.split("=", 1)[1])


# ── Mount-table replay for the bubblewrap argv ───────────────────────────────

_TWO_ARGS = {"--ro-bind", "--ro-bind-try", "--bind", "--bind-try", "--symlink", "--setenv"}
_ONE_ARG = {"--tmpfs", "--proc", "--dev", "--chdir", "--dir", "--remount-ro"}


def _mounts(argv: list[str]) -> list[tuple[str, str | None, str]]:
    """(kind, source, destination) for each mount, in the order bwrap applies them."""
    ops: list[tuple[str, str | None, str]] = []
    i = 1
    while i < len(argv) and argv[i].startswith("--"):
        opt = argv[i]
        if opt in _TWO_ARGS:
            if opt != "--setenv":
                kind = "link" if opt == "--symlink" else "bind"
                ops.append((kind, argv[i + 1], argv[i + 2]))
            i += 3
        elif opt in _ONE_ARG:
            if opt in {"--tmpfs", "--proc", "--dev"}:
                ops.append(("fresh", None, argv[i + 1]))
            i += 2
        else:
            i += 1
    return ops


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _readable_inside(argv: list[str], host_path: str) -> bool:
    """Whether the host file or directory at *host_path* is reachable in the sandbox."""
    ops = _mounts(argv)
    for index, (kind, source, dest) in enumerate(ops):
        if kind != "bind" or not _within(host_path, source):
            continue
        inside = dest + host_path[len(source) :]
        if not any(_within(inside, later) for _, _, later in ops[index + 1 :]):
            return True
    return False


# ── Environment ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sandboxed", [False, True])
async def test_no_process_of_the_session_inherits_the_hub_environment(launcher, sandboxed):
    launcher.sandbox(sandboxed)

    await proxy.browser_start(_json_request({"url": "http://intranet.local/"}), user=_user())

    assert len(launcher.procs) == 3, "expected Xvfb, Chromium and x11vnc"
    session_dir = proxy._browser_session["session_dir"]
    for proc in launcher.procs:
        assert set(proc.env) <= ALLOWED_ENV, f"{proc.argv[0]} got {set(proc.env) - ALLOWED_ENV}"
        for value in (*INHERITED_SECRETS.values(), os.environ["CREDENTIALS_DIRECTORY"]):
            assert value not in proc.env.values()
        assert proc.env["PATH"] == proxy._BROWSER_PATH
        assert proc.env["HOME"].startswith(session_dir + "/")
        assert proc.env["TMPDIR"].startswith(session_dir + "/")


def test_master_key_variables_never_reach_the_browser_environment(monkeypatch, tmp_path):
    for key in ("SYBR_MASTER_KEY", "SYBR_KEY_WRAP_SECRET", "SYBR_MASTER_KEY_FILE", "MSP_DATA_DIR"):
        monkeypatch.setenv(key, f"value-of-{key}")

    env = proxy._browser_env(":55", tmp_path)

    assert set(env) <= ALLOWED_ENV
    assert not any(value.startswith("value-of-") for value in env.values())


# ── Profiles ─────────────────────────────────────────────────────────────────


async def test_every_session_gets_a_fresh_profile_and_stop_deletes_it(launcher):
    user = _user()
    await proxy.browser_start(_json_request({}), user=user)
    first = _profile_dir(launcher.chromium()[-1])
    assert first.is_dir()
    assert first.parent == Path(proxy._browser_session["session_dir"])

    await proxy.browser_stop(user=user)
    assert not first.parent.exists(), "the session directory outlived the session"

    await proxy.browser_start(_json_request({}), user=user)
    second = _profile_dir(launcher.chromium()[-1])
    assert second != first and second.is_dir()


@pytest.mark.parametrize("sandboxed", [False, True])
async def test_navigate_restarts_chromium_in_the_session_profile(launcher, sandboxed):
    launcher.sandbox(sandboxed)
    user = _user()
    await proxy.browser_start(_json_request({"url": "http://a.local/"}), user=user)
    started = launcher.chromium()[-1]

    await proxy.browser_navigate(_json_request({"url": "http://b.local/"}), user=user)

    restarted = launcher.chromium()[-1]
    assert restarted is not started and started.terminated
    assert _profile_dir(restarted) == _profile_dir(started)
    assert restarted.argv[-1] == "http://b.local/"
    assert set(restarted.env) <= ALLOWED_ENV
    assert (restarted.argv[0] == BWRAP) is sandboxed


async def test_navigate_clears_the_profile_lock_left_by_the_killed_browser(launcher):
    user = _user()
    await proxy.browser_start(_json_request({}), user=user)
    profile = _profile_dir(launcher.chromium()[-1])
    (profile / "SingletonLock").symlink_to("host-2")
    (profile / "SingletonSocket").write_text("")

    await proxy.browser_navigate(_json_request({"url": "http://b.local/"}), user=user)

    assert not list(profile.glob("Singleton*"))


async def test_a_crashed_session_is_cleared_before_the_next_one_starts(launcher, monkeypatch):
    monkeypatch.setattr(proxy, "_guac_pending_cleanup", {})
    user = _user()
    await proxy.browser_start(_json_request({}), user=user)
    crashed_dir = Path(proxy._browser_session["session_dir"])
    proxy._browser_session["xvfb"].returncode = 1  # the display died; nobody pressed stop

    await proxy.browser_start(_json_request({}), user=user)

    assert not crashed_dir.exists(), "the crashed session's profile survived"
    assert Path(proxy._browser_session["session_dir"]) != crashed_dir
    assert proxy._guac_pending_cleanup == {"42": "guac-backend-token"}


async def test_a_failed_start_removes_its_session_directory(launcher, monkeypatch):
    # Keep the cleanup away from real X lock files on the machine running this.
    monkeypatch.setattr(proxy.os, "remove", lambda _path: None)
    launcher.chromium_exits_with(1)

    with pytest.raises(IntegrationError):
        await proxy.browser_start(_json_request({}), user=_user())

    profile = _profile_dir(launcher.chromium()[-1])
    assert not profile.parent.exists()
    assert proxy._browser_session == {}


# ── Sandbox ──────────────────────────────────────────────────────────────────


async def test_without_bwrap_the_browser_starts_unconfined_and_says_so(launcher, caplog):
    launcher.sandbox(False)
    user = _user()

    with caplog.at_level(logging.WARNING, logger=proxy.logger.name):
        started = await proxy.browser_start(_json_request({}), user=user)

    assert started["sandboxed"] is False
    assert launcher.chromium()[-1].argv[0] == CHROMIUM
    assert any("bwrap" in record.getMessage() for record in caplog.records)
    assert (await proxy.browser_status(user=user))["sandboxed"] is False


async def test_with_bwrap_chromium_runs_inside_it(launcher):
    launcher.sandbox(True)
    user = _user()

    started = await proxy.browser_start(_json_request({"url": "http://a.local/"}), user=user)

    argv = launcher.chromium()[-1].argv
    assert started["sandboxed"] is True
    assert argv[0] == BWRAP
    for flag in ("--die-with-parent", "--new-session", "--unshare-pid"):
        assert flag in argv
    # The browser exists to reach internal sites; the network stays shared.
    assert "--unshare-net" not in argv
    chromium_at = argv.index(CHROMIUM)
    assert argv[chromium_at:][-1] == "http://a.local/"
    assert (await proxy.browser_status(user=user))["sandboxed"] is True


async def test_sandbox_exposes_the_session_but_none_of_the_hubs_files(launcher):
    from app.core.config import CONFIG_DIR, DATA_DIR
    from app.core.encryption import _backup_locations

    launcher.sandbox(True)
    await proxy.browser_start(_json_request({}), user=_user())
    argv = launcher.chromium()[-1].argv
    session_dir = proxy._browser_session["session_dir"]

    hidden = [
        str(DATA_DIR),
        str(CONFIG_DIR),
        *(str(p) for p in _backup_locations()),
        os.environ["CREDENTIALS_DIRECTORY"],
        f"/proc/{os.getpid()}/environ",
        f"/proc/{os.getpid()}/root",
        *proxy._protected_paths(),
    ]
    # A path that does not exist on this machine has nothing to read.
    for path in filter(os.path.lexists, hidden):
        assert not _readable_inside(argv, os.path.realpath(path)), f"{path} is visible"
    # Not vacuous: the session and the system libraries are there.
    assert _readable_inside(argv, session_dir + "/profile")
    assert _readable_inside(argv, "/usr/lib")


def test_protected_paths_inside_system_directories_are_masked(monkeypatch, tmp_path):
    sysroot = tmp_path / "sysroot"
    (sysroot / "sybr-hub" / "nested").mkdir(parents=True)
    (sysroot / "sybr-hub" / "settings.json").write_text("{}")
    (sysroot / "fonts").mkdir()
    (sysroot / ".master_key_backup").write_text("wrapped-key")
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(proxy, "_SANDBOX_RO_DIRS", (*proxy._SANDBOX_RO_DIRS, str(sysroot)))
    monkeypatch.setattr(
        proxy,
        "_protected_paths",
        lambda: [
            str(sysroot / "sybr-hub"),
            str(sysroot / "sybr-hub" / "nested"),
            str(sysroot / ".master_key_backup"),
            str(sysroot / "not-there"),
            str(outside),
        ],
    )
    session = tmp_path / "session"
    session.mkdir()

    argv = proxy._sandbox_prefix(BWRAP, CHROMIUM, session, ":60")

    assert _readable_inside(argv, str(sysroot / "fonts"))
    assert not _readable_inside(argv, str(sysroot / "sybr-hub" / "settings.json"))
    assert not _readable_inside(argv, str(sysroot / ".master_key_backup"))
    assert not _readable_inside(argv, str(outside))
    # A missing path cannot be a mount point; bwrap would refuse to start.
    assert str(sysroot / "not-there") not in argv


def test_protected_paths_cover_hub_state_and_credentials(monkeypatch, tmp_path):
    import app.core.config as config
    from app.core.encryption import _backup_locations

    audit, certs = tmp_path / "audits", tmp_path / "certs"
    monkeypatch.setattr(config, "get_audit_dir", lambda: audit)
    monkeypatch.setattr(config, "get_cert_dir", lambda: certs)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path / "creds"))
    monkeypatch.setenv("SYBR_KEY_WRAP_SECRET_FILE", str(tmp_path / "creds" / "key-wrap.secret"))
    monkeypatch.setenv("SYBR_MASTER_KEY_FILE", str(tmp_path / "master.key"))
    monkeypatch.setenv("SYBR_HUB_SSL_KEY", str(tmp_path / "tls.key"))

    protected = set(proxy._protected_paths())

    expected = {
        str(config.DATA_DIR),
        str(config.CONFIG_DIR),
        str(audit),
        str(certs),
        *(str(p) for p in _backup_locations()),
        str(tmp_path / "creds"),
        str(tmp_path / "creds" / "key-wrap.secret"),
        str(tmp_path / "master.key"),
        str(tmp_path / "tls.key"),
        "/etc/sybr-hub-secrets",
    }
    assert expected <= protected, expected - protected
