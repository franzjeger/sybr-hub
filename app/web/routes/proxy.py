"""Remote-session routes — remote browser and remote RDP.

The remote browser is Chromium on Xvfb, exposed over Guacamole VNC; the
remote-RDP endpoints front Apache Guacamole. Both reach customer-internal
destinations on purpose, which is why ``_validate_browser_target`` restricts
the *scheme* rather than the address.

The server-side web proxy that used to live here (``/api/proxy/fetch`` and
``/api/proxy/raw``) is gone. No caller ever reached it, its HTML rewriter
injected a ``<script>`` the application CSP refuses, and its SSRF policy
rejected every private address — so the one thing its docstring promised,
browsing an internal site, was the one thing it could not do.
"""

from __future__ import annotations

import asyncio
import atexit
import base64
import glob
import logging
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.remote import BrowserTarget, RdpClipboard, RdpStartRequest
from app.models.user import Role, User
from app.services.guacamole_client import (
    _GUAC_BOOT_PREFIX,
    _get_guac_config,
    _guac_base,
    _guac_delete_with_fresh_token,
    _guac_login,
    cleanup_stale_guacamole_connections,
)
from app.web.i18n import keyed, refusal
from app.web.middleware.auth import require_feature, require_module, require_role

logger = logging.getLogger(__name__)
# The whole module is the 'remote' feature (app/core/features.py); per-route
# floors below only ever raise it.
router = APIRouter(
    dependencies=[Depends(require_module("remote")), Depends(require_feature("remote"))]
)

# ── Remote browser session state ──────────────────────────────────────────────

_browser_session: dict = {}  # keys: xvfb, chromium, x11vnc, vnc_port, url, display, guac_token, guac_conn_id
_browser_lock = asyncio.Lock()

# The only schemes a remote-browser session may be pointed at. Kept here rather
# than inline so the two validators below cannot drift apart.
_ALLOWED_SCHEMES = {"http", "https"}


def _validate_browser_target(url: str) -> None:
    """Allow browser navigation only to ordinary HTTP(S) pages.

    Internal destinations are intentional for this feature, but local files,
    browser settings and executable schemes are not.
    """
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        raise refusal(ValidationError, "err_proxy_url_scheme")
    if parsed.username is not None or parsed.password is not None:
        raise refusal(ValidationError, "err_proxy_url_userinfo")


def _require_browser_owner(user: User) -> None:
    owner_id = _browser_session.get("owner_user_id")
    if owner_id and owner_id != str(user.id):
        raise refusal(ForbiddenError, "err_proxy_session_other_user")


# ── Browser process isolation ─────────────────────────────────────────────────
#
# Chromium runs as the hub's service account, and the technician drives it over
# VNC: whatever they type into the omnibox is never seen by
# _validate_browser_target. So the process itself must not be able to reach
# the hub's secrets. Three layers: a fresh profile per session (no cookies or
# saved logins shared between technicians and customers), an environment built
# from scratch instead of copied from the hub, and, when bubblewrap is
# installed, a filesystem namespace with read-only system directories, a
# private /tmp and /proc, and none of the hub's data, config or credentials.

# Fixed rather than inherited, so the hub's virtualenv is not on it.
_BROWSER_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
# Locale and timezone are the only inherited variables; neither is secret.
_BROWSER_INHERITED_ENV = ("LC_ALL", "TZ")

# Read-only system directories. On merged-/usr systems /bin, /lib and friends
# are symlinks into /usr and are recreated as symlinks.
_SANDBOX_RO_DIRS = ("/usr", "/etc")
_SANDBOX_RO_LINKS_OR_DIRS = ("/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32")
_SANDBOX_RO_OPTIONAL = ("/var/cache/fontconfig",)

# Environment variables naming files or directories that hold secrets.
_SECRET_FILE_ENV = ("SYBR_MASTER_KEY_FILE", "SYBR_KEY_WRAP_SECRET_FILE", "SYBR_HUB_SSL_KEY")
_SECRET_DIR_ENV = ("CREDENTIALS_DIRECTORY",)
# Source directory for the systemd LoadCredential= in scripts/sybr-hub.service.
_KEY_WRAP_SECRET_DIR = "/etc/sybr-hub-secrets"


def _new_session_dir() -> Path:
    """Create the private directory one browser session lives in.

    It holds the Chromium profile, HOME and TMPDIR, and is deleted when the
    session stops, so nothing the browser stored outlives it.
    """
    root = Path(tempfile.mkdtemp(prefix="msp-browser-"))
    for name in ("profile", "home", "tmp"):
        (root / name).mkdir(mode=0o700)
    return root


def _browser_env(display: str, session_dir: Path) -> dict[str, str]:
    """The environment for Xvfb, Chromium and x11vnc, built from nothing.

    Copying os.environ handed the browser everything the hub runs with:
    GUACAMOLE_PASS, SYBR_MASTER_KEY, the key-wrap secret, the MSP_* paths and
    the systemd CREDENTIALS_DIRECTORY.
    """
    env = {
        "DISPLAY": display,
        "HOME": str(session_dir / "home"),
        "TMPDIR": str(session_dir / "tmp"),
        "PATH": _BROWSER_PATH,
        "LANG": os.environ.get("LANG") or "C.UTF-8",
    }
    for key in _BROWSER_INHERITED_ENV:
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def _chromium_binary() -> str:
    """The Chromium executable to run.

    Snap Chromium cannot start from a systemd service cgroup through its
    wrapper, so the real binary inside the snap mount is used when present.
    That also bypasses snap confinement, which is one more reason the browser
    runs inside bubblewrap when it can.
    """
    snap_chrome = glob.glob("/snap/chromium/*/usr/lib/chromium-browser/chrome")
    if snap_chrome:
        return sorted(snap_chrome)[-1]  # Latest revision
    return shutil.which("chromium") or "/snap/bin/chromium"


def _bwrap_binary() -> str | None:
    return shutil.which("bwrap")


def _under(path: str, roots: list[str]) -> bool:
    return any(path == root or path.startswith(root.rstrip("/") + "/") for root in roots)


def _protected_paths() -> list[str]:
    """Locations the browser must not see, even read-only."""
    import app
    from app.core.config import CONFIG_DIR, DATA_DIR, get_audit_dir, get_cert_dir
    from app.core.encryption import _backup_locations
    from app.services.vpn_backends.fortigate_ipsec import CONF_DIR as SWANCTL_CONF_DIR

    paths = [
        DATA_DIR,
        CONFIG_DIR,
        *_backup_locations(),
        Path.home(),
        Path(app.__file__).resolve().parent.parent,
        Path(_KEY_WRAP_SECRET_DIR),
        SWANCTL_CONF_DIR,
    ]
    for resolve in (get_audit_dir, get_cert_dir):
        try:
            paths.append(resolve())
        except Exception:
            logger.debug("Could not resolve %s for the browser sandbox", resolve.__name__)
    for key in (*_SECRET_FILE_ENV, *_SECRET_DIR_ENV):
        if os.environ.get(key):
            paths.append(Path(os.environ[key]))
    return [str(p) for p in paths]


def _mask_args(visible_roots: list[str]) -> list[str]:
    """Hide every protected path that a read-only bind would otherwise expose.

    Only paths under a bound root need it; the rest do not exist in the
    sandbox at all. Directories get an empty tmpfs, files /dev/null.
    """
    args: list[str] = []
    masked: list[str] = []
    for path in sorted({os.path.realpath(p) for p in _protected_paths()}, key=len):
        if not os.path.lexists(path) or not _under(path, visible_roots) or _under(path, masked):
            continue
        if os.path.isdir(path):
            args += ["--tmpfs", path]
            masked.append(path)
        else:
            args += ["--ro-bind", "/dev/null", path]
    return args


def _sandbox_prefix(bwrap: str, chromium_bin: str, session_dir: Path, display: str) -> list[str]:
    """bubblewrap arguments that confine Chromium to what it needs.

    The network namespace is shared on purpose: the browser exists to reach
    internal sites. The PID namespace is not: with the host /proc, the browser
    could read the hub's /proc/<pid>/environ and walk /proc/<pid>/root.
    """
    # Order matters: bwrap applies mounts in sequence, so the fresh /proc, /dev
    # and /tmp come first, the read-only binds on top, then the masks that hide
    # protected paths inside them, and the session directory last.
    args = [
        bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-cgroup-try",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]
    roots: list[str] = []
    for path in _SANDBOX_RO_DIRS:
        if os.path.isdir(path):
            args += ["--ro-bind", path, path]
            roots.append(path)
    for path in _SANDBOX_RO_LINKS_OR_DIRS:
        if os.path.islink(path):
            args += ["--symlink", os.readlink(path), path]
        elif os.path.isdir(path):
            args += ["--ro-bind", path, path]
            roots.append(path)
    real_chrome = os.path.realpath(chromium_bin)
    install_root = "/snap" if real_chrome.startswith("/snap/") else os.path.dirname(real_chrome)
    if not _under(install_root, roots):
        args += ["--ro-bind", install_root, install_root]
        roots.append(install_root)
    # systemd-resolved makes /etc/resolv.conf a symlink into /run.
    resolv = os.path.realpath("/etc/resolv.conf")
    if not _under(resolv, roots) and os.path.isfile(resolv):
        args += ["--ro-bind", resolv, resolv]
    for path in _SANDBOX_RO_OPTIONAL:
        args += ["--ro-bind-try", path, path]
    args += _mask_args(roots)
    display_socket = f"/tmp/.X11-unix/X{display.lstrip(':')}"
    args += [
        "--bind",
        str(session_dir),
        str(session_dir),
        "--ro-bind-try",
        display_socket,
        display_socket,
        "--chdir",
        str(session_dir / "home"),
    ]
    return args


def _chromium_command(
    chromium_bin: str, bwrap: str | None, session_dir: Path, display: str, url: str
) -> list[str]:
    """Full argv for one Chromium launch; start and navigate share it."""
    chrome_args = [
        chromium_bin,
        # Keep Chromium's user-namespace sandbox. Only disable the legacy
        # setuid helper, which is commonly unavailable inside the hardened
        # systemd service.
        "--disable-setuid-sandbox",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080",
        "--window-position=0,0",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-sync",
        # Saved passwords stay in the session profile, never a desktop keyring.
        "--password-store=basic",
        f"--user-data-dir={session_dir / 'profile'}",
    ]
    if url:
        chrome_args.append(url)
    if bwrap is None:
        return chrome_args
    return _sandbox_prefix(bwrap, chromium_bin, session_dir, display) + chrome_args


def _spawn_chromium(
    chromium_bin: str,
    bwrap: str | None,
    session_dir: Path,
    display: str,
    url: str,
    log=subprocess.DEVNULL,
) -> subprocess.Popen:
    return subprocess.Popen(
        _chromium_command(chromium_bin, bwrap, session_dir, display, url),
        stdout=log,
        stderr=log,
        env=_browser_env(display, session_dir),
    )


def _clear_profile_locks(session_dir: Path) -> None:
    """Remove Chromium's single-instance lock left by a killed browser.

    The lock names a host and PID. In a fresh PID namespace the next browser
    can be handed that same PID and mistake the stale lock for a live one.
    """
    for lock in (session_dir / "profile").glob("Singleton*"):
        with suppress(OSError):
            lock.unlink()


# ═══════════════════════════════════════════════════════════════════════════════
# REMOTE BROWSER — Guacamole VNC + Chromium on Xvfb
# ═══════════════════════════════════════════════════════════════════════════════


def _kill_proc(proc: subprocess.Popen | None, name: str) -> None:
    """Terminate a subprocess gracefully, then kill if needed."""
    if proc is None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        logger.info("Stopped %s (pid %d)", name, proc.pid)
    except Exception as exc:
        logger.debug("Could not stop %s: %s", name, exc)


def _find_free_display(start=50, end=99) -> str:
    """Find an unused X display number."""
    import random

    candidates = list(range(start, end + 1))
    random.shuffle(candidates)
    for n in candidates:
        lock = f"/tmp/.X{n}-lock"
        if not os.path.exists(lock):
            return f":{n}"
    # Force-clean the first candidate
    n = candidates[0]
    with suppress(OSError):
        os.remove(f"/tmp/.X{n}-lock")
    with suppress(OSError):
        os.remove(f"/tmp/.X11-unix/X{n}")
    return f":{n}"


def _docker_host_ip() -> str:
    """Return the IP address the Docker host is reachable at from containers.

    Tries the default Docker bridge gateway (172.17.0.1), then falls back
    to the first routable IP on the host.
    """
    # Check default Docker bridge gateway
    candidate = "172.17.0.1"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.bind((candidate, 0))
        return candidate
    except OSError:
        pass

    # Fallback: find the host IP on any interface
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception as e:
        logger.debug("Could not determine Docker host IP: %s", e)
        return "172.17.0.1"


def _stop_browser_session() -> dict:
    """Kill every process in the current session and reset state."""
    global _browser_session
    if not _browser_session:
        # Still clean up stale lock files
        for f in ["/tmp/.X99-lock", "/tmp/.X11-unix/X99"]:
            with suppress(OSError):
                os.remove(f)
        return {"ok": True, "msg": "No session running"}

    display = _browser_session.get("display", ":99")
    for key in ("x11vnc", "chromium", "xvfb"):
        _kill_proc(_browser_session.get(key), key)

    # Clean up X lock files
    display_num = display.lstrip(":")
    for f in [f"/tmp/.X{display_num}-lock", f"/tmp/.X11-unix/X{display_num}"]:
        with suppress(OSError):
            os.remove(f)

    # The profile, HOME and TMPDIR go with the session.
    session_dir = _browser_session.get("session_dir")
    if session_dir:
        shutil.rmtree(session_dir, ignore_errors=True)

    _browser_session = {}
    return {"ok": True}


# Clean up on interpreter exit
atexit.register(_stop_browser_session)


@router.post("/browser/start")
async def browser_start(
    body: BrowserTarget | None = None,
    user: User = Depends(require_role(Role.technician)),
):
    """Start a remote Chromium browser session accessible via Guacamole VNC."""
    global _browser_session

    async with _browser_lock:
        # If already running, return current session info
        if _browser_session.get("xvfb") and _browser_session["xvfb"].poll() is None:
            _require_browser_owner(user)
            guac_url = None
            token = _browser_session.get("guac_token")
            client_token = _browser_session.get("guac_client_token")
            conn_id = _browser_session.get("guac_conn_id")
            if client_token and conn_id:
                guac_url = _guac_client_url(conn_id, client_token)
            return {
                "ok": True,
                "guac_url": guac_url,
                "guac_token": client_token,
                "guac_connection_id": conn_id,
                "url": _browser_session.get("url", ""),
                "sandboxed": bool(_browser_session.get("bwrap")),
                "already_running": True,
            }

        if _browser_session:
            # A session whose display died was never stopped; its profile and
            # Guacamole connection must not outlive it.
            stale_token = _browser_session.get("guac_token")
            stale_conn = _browser_session.get("guac_conn_id")
            if stale_token and stale_conn:
                _guac_pending_cleanup[stale_conn] = stale_token
            _stop_browser_session()

        # The body, and the URL in it, are optional.
        target_url = ((body.url if body else None) or "").strip()
        _validate_browser_target(target_url)

        display = _find_free_display(50, 74)
        display_num = int(display.lstrip(":"))
        vnc_port = 5900 + display_num

        xvfb_bin = shutil.which("Xvfb") or "/usr/bin/Xvfb"
        x11vnc_bin = shutil.which("x11vnc") or "/usr/bin/x11vnc"
        chromium_bin = _chromium_binary()
        bwrap_bin = _bwrap_binary()
        if bwrap_bin is None:
            logger.warning(
                "bubblewrap (bwrap) is not installed: the remote browser runs without "
                "filesystem isolation, with the hub service account's file access"
            )

        session_dir = _new_session_dir()
        env = _browser_env(display, session_dir)
        devnull = subprocess.DEVNULL
        xvfb_proc = None
        chromium_proc = None
        x11vnc_proc = None
        vnc_password_path = None
        guac_token = None
        guac_connection_id = None

        def _cleanup_failed_start() -> None:
            if vnc_password_path:
                with suppress(OSError):
                    os.unlink(vnc_password_path)
            for proc, name in (
                (x11vnc_proc, "x11vnc"),
                (chromium_proc, "chromium"),
                (xvfb_proc, "xvfb"),
            ):
                _kill_proc(proc, name)
            shutil.rmtree(session_dir, ignore_errors=True)
            _stop_browser_session()

        try:
            # 1. Start Xvfb — clean up stale locks first
            display_num_str = display.lstrip(":")
            for f in [f"/tmp/.X{display_num_str}-lock", f"/tmp/.X11-unix/X{display_num_str}"]:
                with suppress(OSError):
                    os.remove(f)
            xvfb_proc = subprocess.Popen(
                [xvfb_bin, display, "-screen", "0", "1920x1080x24"],
                stdout=devnull,
                stderr=devnull,
                env=env,
            )
            await asyncio.sleep(0.5)
            if xvfb_proc.poll() is not None:
                raise refusal(IntegrationError, "err_proxy_xvfb_failed", code=xvfb_proc.returncode)

            # 2. Start Chromium in this session's own profile.
            with tempfile.TemporaryFile(mode="w+") as chrome_log:
                chromium_proc = _spawn_chromium(
                    chromium_bin, bwrap_bin, session_dir, display, target_url, log=chrome_log
                )
                await asyncio.sleep(3)
                if chromium_proc.poll() is not None:
                    chrome_log.seek(0)
                    chrome_output = chrome_log.read()[-500:]
                    _kill_proc(xvfb_proc, "xvfb")
                    logger.error("Chromium exited immediately: %s", chrome_output)
                    raise refusal(
                        IntegrationError, "err_proxy_chromium_crashed", output=chrome_output[:200]
                    )

            # 3. Expose VNC only on the Docker-facing host address and protect
            # it with a high-entropy per-session password.
            docker_host = _docker_host_ip()
            vnc_password = secrets.token_urlsafe(32)
            with tempfile.NamedTemporaryFile(
                mode="w",
                prefix="sybr-vnc-",
                delete=False,
            ) as password_file:
                password_file.write(vnc_password + "\n")
                vnc_password_path = password_file.name
            os.chmod(vnc_password_path, 0o600)
            x11vnc_proc = subprocess.Popen(
                [
                    x11vnc_bin,
                    "-display",
                    display,
                    # Do not expose the password in the process command line.
                    "-passwdfile",
                    vnc_password_path,
                    "-listen",
                    docker_host,
                    "-xkb",
                    "-forever",
                    "-shared",
                    "-noxdamage",
                    "-rfbport",
                    str(vnc_port),
                ],
                stdout=devnull,
                stderr=devnull,
                env=env,
            )
            await asyncio.sleep(1.0)
            if x11vnc_proc.poll() is not None:
                _kill_proc(chromium_proc, "chromium")
                _kill_proc(xvfb_proc, "xvfb")
                raise refusal(IntegrationError, "err_proxy_x11vnc_failed")
            with suppress(OSError):
                os.unlink(vnc_password_path)
            vnc_password_path = None

            # 4. Create Guacamole VNC connection (Guacamole is in Docker)
            token = await _guac_login()
            if not token:
                _kill_proc(x11vnc_proc, "x11vnc")
                _kill_proc(chromium_proc, "chromium")
                _kill_proc(xvfb_proc, "xvfb")
                raise refusal(IntegrationError, "err_guacamole_login_failed")
            guac_token = token
            await _retry_pending_guacamole_cleanup()

            conn = await _guac_create_vnc_connection(
                token,
                docker_host,
                vnc_port,
                vnc_password,
            )
            if not conn or "identifier" not in conn:
                _kill_proc(x11vnc_proc, "x11vnc")
                _kill_proc(chromium_proc, "chromium")
                _kill_proc(xvfb_proc, "xvfb")
                raise refusal(IntegrationError, "err_guacamole_vnc_failed")

            connection_id = conn["identifier"]
            guac_connection_id = connection_id
            client_token = secrets.token_urlsafe(32)
            guac_url = _guac_client_url(connection_id, client_token)

            _browser_session = {
                "xvfb": xvfb_proc,
                "chromium": chromium_proc,
                "x11vnc": x11vnc_proc,
                "vnc_port": vnc_port,
                "display": display,
                "url": target_url,
                "guac_token": token,
                "guac_client_token": client_token,
                "guac_conn_id": connection_id,
                "session_dir": str(session_dir),
                "chromium_bin": chromium_bin,
                "bwrap": bwrap_bin,
                "owner_user_id": str(user.id),
            }

            logger.info(
                "Remote browser started: display=%s vnc=%d guac_conn=%s sandboxed=%s url=%s",
                display,
                vnc_port,
                connection_id,
                bwrap_bin is not None,
                target_url or "(blank)",
            )

            return {
                "ok": True,
                "guac_url": guac_url,
                "guac_token": client_token,
                "guac_connection_id": connection_id,
                "url": target_url,
                "sandboxed": bwrap_bin is not None,
            }

        except FileNotFoundError as exc:
            if guac_token and guac_connection_id:
                try:
                    deleted = await _guac_delete_with_fresh_token(
                        guac_token,
                        guac_connection_id,
                    )
                except Exception as cleanup_exc:
                    logger.warning("Failed to clean up browser connection: %s", cleanup_exc)
                    deleted = False
                if not deleted:
                    _guac_pending_cleanup[guac_connection_id] = guac_token
            _cleanup_failed_start()
            raise refusal(
                IntegrationError, "err_proxy_binary_missing", binary=exc.filename
            ) from exc
        except Exception as exc:
            if guac_token and guac_connection_id:
                try:
                    deleted = await _guac_delete_with_fresh_token(
                        guac_token,
                        guac_connection_id,
                    )
                except Exception as cleanup_exc:
                    logger.warning(
                        "Failed to clean up browser connection after start error: %s", cleanup_exc
                    )
                    deleted = False
                if not deleted:
                    _guac_pending_cleanup[guac_connection_id] = guac_token
            _cleanup_failed_start()
            logger.exception("Failed to start remote browser")
            raise IntegrationError(str(exc)) from exc


@router.post("/browser/navigate")
async def browser_navigate(
    body: BrowserTarget,
    user: User = Depends(require_role(Role.technician)),
):
    """Navigate the remote browser to a new URL (restarts Chromium)."""
    global _browser_session

    async with _browser_lock:
        if not _browser_session.get("xvfb") or _browser_session["xvfb"].poll() is not None:
            raise refusal(ValidationError, "err_proxy_no_session")
        _require_browser_owner(user)

        target_url = (body.url or "").strip()
        if not target_url:
            raise refusal(ValidationError, "err_url_required")
        _validate_browser_target(target_url)

        # Restart Chromium in the same session profile, sandbox and environment
        # it started with. Without --user-data-dir it would fall back to the
        # service account's persistent default profile.
        _kill_proc(_browser_session.get("chromium"), "chromium")
        session_dir = Path(_browser_session["session_dir"])
        _clear_profile_locks(session_dir)
        chromium_proc = _spawn_chromium(
            _browser_session["chromium_bin"],
            _browser_session.get("bwrap"),
            session_dir,
            _browser_session["display"],
            target_url,
        )

        _browser_session["chromium"] = chromium_proc
        _browser_session["url"] = target_url

    return {"ok": True, "url": target_url}


@router.post("/browser/stop")
async def browser_stop(
    user: User = Depends(require_role(Role.technician)),
):
    """Stop the remote browser session, delete Guacamole connection, kill processes."""
    async with _browser_lock:
        _require_browser_owner(user)
        # Delete Guacamole VNC connection first
        token = _browser_session.get("guac_token")
        conn_id = _browser_session.get("guac_conn_id")
        deleted = True
        if token and conn_id:
            try:
                deleted = await _guac_delete_with_fresh_token(token, conn_id)
            except Exception as exc:
                logger.warning("Failed to delete browser Guacamole connection: %s", exc)
                deleted = False
            if not deleted:
                _guac_pending_cleanup[conn_id] = token

        result = _stop_browser_session()
        if not deleted:
            raise refusal(IntegrationError, "err_proxy_stopped_cleanup_pending")
    return result


@router.get("/browser/status")
async def browser_status(
    user: User = Depends(require_role(Role.technician)),
):
    """Return whether a remote browser session is running.

    ``sandboxed`` says whether the browser is (or, with no session running,
    would be) confined by bubblewrap, so the UI can warn when it is not.
    """
    async with _browser_lock:
        running = bool(_browser_session.get("xvfb") and _browser_session["xvfb"].poll() is None)
        available = _bwrap_binary() is not None
        if running and _browser_session.get("owner_user_id") != str(user.id):
            return {"running": False, "sandboxed": available}
        guac_url = None
        client_token = None
        conn_id = None
        if running:
            client_token = _browser_session.get("guac_client_token")
            conn_id = _browser_session.get("guac_conn_id")
            if client_token and conn_id:
                guac_url = _guac_client_url(conn_id, client_token)
        return {
            "running": running,
            "guac_url": guac_url,
            "guac_token": client_token,
            "guac_connection_id": conn_id,
            "url": _browser_session.get("url", "") if running else "",
            "sandboxed": bool(_browser_session.get("bwrap")) if running else available,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# REMOTE RDP — Apache Guacamole
# ═══════════════════════════════════════════════════════════════════════════════


def _warn_guac_config() -> None:
    """Log a warning if Guacamole credentials are empty or missing."""
    cfg = _get_guac_config()
    missing = [k for k in ("url", "user", "pass") if not cfg[k]]
    if missing:
        logger.warning(
            "Guacamole config incomplete — missing: %s. "
            "Set guacamole_url/guacamole_user/guacamole_pass in app settings "
            "or GUACAMOLE_URL/GUACAMOLE_USER/GUACAMOLE_PASS env vars.",
            ", ".join(missing),
        )


# Guacamole config warning is now checked at startup via server.py lifespan,
# not at import time (which breaks test collection).

# Track per-user Guacamole sessions: {user_id: {token, connection_id}}
_guac_sessions: dict[str, dict] = {}
_guac_lock = asyncio.Lock()
_guac_pending_cleanup: dict[str, str] = {}  # connection_id -> last usable token


def _guac_connection_name(kind: str) -> str:
    """Return a collision-resistant name owned by this process boot."""
    return f"{_GUAC_BOOT_PREFIX}{kind}-{secrets.token_hex(8)}"


def resolve_guacamole_tunnel(
    user: User,
    client_token: str,
    connection_id: str,
) -> str | None:
    """Exchange a user-bound opaque token for the backend Guacamole token.

    The browser must never receive the Guacamole admin token. State reads are
    intentionally synchronous and atomic within the event loop; route writers
    replace whole token/id values while holding their respective locks.
    """
    user_key = str(user.id)
    session = _guac_sessions.get(user_key)
    if session:
        expected = str(session.get("client_token") or "")
        if (
            expected
            and secrets.compare_digest(client_token, expected)
            and secrets.compare_digest(connection_id, str(session.get("connection_id") or ""))
        ):
            return str(session["token"])

    if _browser_session.get("owner_user_id") == user_key:
        expected = str(_browser_session.get("guac_client_token") or "")
        if (
            expected
            and secrets.compare_digest(client_token, expected)
            and secrets.compare_digest(
                connection_id, str(_browser_session.get("guac_conn_id") or "")
            )
        ):
            return str(_browser_session["guac_token"])
    return None


async def _guac_create_connection(
    token: str,
    host: str,
    port: int,
    username: str,
    password: str,
) -> dict | None:
    """Create an RDP connection in Guacamole. Returns the connection dict or None."""
    payload = {
        "parentIdentifier": "ROOT",
        "name": _guac_connection_name("RDP"),
        "protocol": "rdp",
        "parameters": {
            "hostname": host,
            "port": str(port),
            "username": username,
            "password": password,
            "security": "any",
            "ignore-cert": "true",
            "resize-method": "display-update",
            "enable-wallpaper": "false",
            "enable-font-smoothing": "true",
            "enable-drive": "false",
            "disable-audio": "true",
            "clipboard-encoding": "UTF-8",
            "color-depth": "32",
        },
        "attributes": {
            "max-connections": "1",
            "max-connections-per-user": "1",
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{_guac_base()}/api/session/data/mysql/connections",
            params={"token": token},
            json=payload,
        )
        if resp.status_code in (200, 201):
            return resp.json()

        logger.warning(
            "Guacamole create connection failed: %d %s", resp.status_code, resp.text[:200]
        )
    return None


async def _retry_pending_guacamole_cleanup() -> int:
    """Retry deletions that failed without losing their identifiers."""
    deleted = 0
    for connection_id, token in list(_guac_pending_cleanup.items()):
        try:
            if await _guac_delete_with_fresh_token(token, connection_id):
                _guac_pending_cleanup.pop(connection_id, None)
                deleted += 1
        except Exception as exc:
            logger.warning("Pending Guacamole cleanup still failed for %s: %s", connection_id, exc)
    return deleted


async def _guac_connection_exists(token: str, connection_id: str) -> bool:
    """Check whether a Guacamole connection still exists."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{_guac_base()}/api/session/data/mysql/connections/{connection_id}",
            params={"token": token},
        )
        return resp.status_code == 200


def _guac_client_url(connection_id: str, token: str) -> str:
    """Build the Guacamole client URL for embedding in an iframe.

    Guacamole encodes the connection identifier as:
        base64( connection_id + "\\0" + "c" + "\\0" + "mysql" )
    """
    raw = f"{connection_id}\0c\0mysql"
    encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return f"/guacamole/#/client/{encoded}?token={token}"


async def _guac_create_vnc_connection(
    token: str,
    host: str,
    port: int,
    password: str,
) -> dict | None:
    """Create a VNC connection in Guacamole for the remote browser.

    Returns the connection dict or None.
    """
    payload = {
        "parentIdentifier": "ROOT",
        "name": _guac_connection_name("Browser"),
        "protocol": "vnc",
        "parameters": {
            "hostname": host,
            "port": str(port),
            "password": password,
            "clipboard-encoding": "UTF-8",
            "resize-method": "reconnect",
            "color-depth": "32",
        },
        "attributes": {
            "max-connections": "1",
            "max-connections-per-user": "1",
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{_guac_base()}/api/session/data/mysql/connections",
            params={"token": token},
            json=payload,
        )
        if resp.status_code in (200, 201):
            return resp.json()

        logger.warning("Guacamole VNC create failed: %d %s", resp.status_code, resp.text[:200])
    return None


async def _get_authorized_rdp_host(user: User, host_id: str):
    """Resolve an RDP target from inventory and enforce its customer scope."""
    from app.core.rbac import check_customer_access, get_accessible_customer_ids
    from app.services.ssh_manager import get_host

    if not host_id:
        raise refusal(ValidationError, "err_host_choose_registered")
    host = await get_host(host_id)
    if host is None:
        raise refusal(NotFoundError, "err_proxy_host_missing")

    if host.customer_id:
        allowed = await check_customer_access(user, host.customer_id)
    else:
        allowed = await get_accessible_customer_ids(user) is None
    if not allowed:
        logger.info(
            "403 RDP host-access: user=%s host=%s customer=%s",
            user.username,
            host_id,
            host.customer_id,
        )
        raise refusal(ForbiddenError, "err_host_forbidden")
    return host


@router.post("/rdp/start")
async def rdp_start(
    body: RdpStartRequest,
    user: User = Depends(require_role(Role.technician)),
):
    """Start a remote RDP session via Apache Guacamole."""
    user_key = str(user.id)

    async with _guac_lock:
        # If already running, return existing session
        existing = _guac_sessions.get(user_key)
        if existing:
            try:
                alive = await _guac_connection_exists(
                    existing["token"],
                    existing["connection_id"],
                )
            except Exception as e:
                logger.warning("Failed to check Guacamole connection: %s", e)
                alive = False
            if alive:
                return {
                    "ok": True,
                    "guac_url": _guac_client_url(
                        existing["connection_id"],
                        existing["client_token"],
                    ),
                    "guac_token": existing["client_token"],
                    "guac_connection_id": existing["connection_id"],
                    "already_running": True,
                }
            else:
                # Stale/expired token does not mean the JDBC connection is
                # gone. Delete with a fresh admin token before forgetting its
                # identifier or creating another credential-bearing row.
                try:
                    deleted = await _guac_delete_with_fresh_token(
                        existing["token"],
                        existing["connection_id"],
                    )
                except Exception as exc:
                    logger.warning("Failed to delete stale Guacamole connection: %s", exc)
                    deleted = False
                if not deleted:
                    raise refusal(IntegrationError, "err_guacamole_stale_connection")
                _guac_sessions.pop(user_key, None)

        host_record = await _get_authorized_rdp_host(user, (body.host_id or "").strip())
        host = host_record.hostname
        port = body.port or 3389
        if not 1 <= port <= 65535:
            raise refusal(ValidationError, "err_rdp_invalid_port")
        username = (body.username or host_record.username or "").strip()
        password = body.password or ""
        # The stored password belongs to the stored account; it is not handed
        # to whatever username the caller types instead.
        if not password and username.lower() == (host_record.username or "").strip().lower():
            from app.services.ssh_manager import _load_host_password

            password = _load_host_password(host_record.id) or ""

        # 1. Login to Guacamole
        token = await _guac_login()
        if not token:
            raise refusal(IntegrationError, "err_guacamole_login_failed")
        await _retry_pending_guacamole_cleanup()

        # 2. Create RDP connection
        conn = await _guac_create_connection(token, host, port, username, password)
        if not conn or "identifier" not in conn:
            raise refusal(IntegrationError, "err_guacamole_rdp_failed")

        connection_id = conn["identifier"]
        client_token = secrets.token_urlsafe(32)
        guac_url = _guac_client_url(connection_id, client_token)

        _guac_sessions[user_key] = {
            "token": token,
            "client_token": client_token,
            "connection_id": connection_id,
        }

    logger.info(
        "Guacamole RDP connection created: host=%s:%d connection_id=%s user=%s",
        host,
        port,
        connection_id,
        user_key,
    )

    return {
        "ok": True,
        "guac_url": guac_url,
        "guac_token": client_token,
        "guac_connection_id": connection_id,
    }


@router.post("/rdp/stop")
async def rdp_stop(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Stop the remote RDP session by deleting the Guacamole connection."""
    user_key = str(user.id)
    async with _guac_lock:
        session = _guac_sessions.get(user_key)
        if not session:
            return {"ok": True, "msg": "No RDP session running"}

        try:
            deleted = await _guac_delete_with_fresh_token(
                session["token"],
                session["connection_id"],
            )
        except Exception as exc:
            logger.warning("Failed to delete Guacamole connection: %s", exc)
            deleted = False
        if not deleted:
            # Keep the identifier so stop/status/shutdown can retry. Returning
            # success here used to make the credential residue unreachable.
            raise refusal(IntegrationError, "err_guacamole_cleanup_pending")
        _guac_sessions.pop(user_key, None)

    return {"ok": True}


@router.get("/rdp/status")
async def rdp_status(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Return whether a Guacamole RDP session is active for this user."""
    user_key = str(user.id)
    async with _guac_lock:
        session = _guac_sessions.get(user_key)
        if not session:
            return {"running": False}

        try:
            alive = await _guac_connection_exists(
                session["token"],
                session["connection_id"],
            )
        except Exception as e:
            logger.warning("Failed to check Guacamole connection: %s", e)
            alive = False

        if not alive:
            try:
                deleted = await _guac_delete_with_fresh_token(
                    session["token"],
                    session["connection_id"],
                )
            except Exception as exc:
                logger.warning("Failed to clean stale Guacamole status entry: %s", exc)
                deleted = False
            if deleted:
                _guac_sessions.pop(user_key, None)

        return {
            "running": alive,
            "guac_url": _guac_client_url(
                session["connection_id"],
                session["client_token"],
            )
            if alive
            else None,
            "guac_token": session["client_token"] if alive else None,
            "guac_connection_id": session["connection_id"] if alive else None,
        }


@router.post("/rdp/clipboard")
async def rdp_clipboard(
    body: RdpClipboard,
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Send clipboard text to the active RDP session via Guacamole API."""
    user_key = str(user.id)
    async with _guac_lock:
        session = _guac_sessions.get(user_key)
    if not session:
        return {"ok": False, **keyed("error", "err_rdp_no_session", request)}

    text = body.text
    if not text:
        return {"ok": False, **keyed("error", "err_rdp_clipboard_empty", request)}

    # Use Guacamole's active connection tunnel to send clipboard
    # The Guacamole API doesn't have a direct clipboard endpoint,
    # so we use xdotool on the server as fallback for RDP via guacd
    try:
        proc = await asyncio.create_subprocess_exec(
            "xdotool",
            "set-clipboard",
            "--",
            text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except Exception as e:
        logger.warning("Clipboard set via xdotool failed: %s", e)

    return {"ok": True}


async def shutdown_proxy_resources() -> None:
    """Best-effort cleanup for application shutdown.

    IDs are retained until a confirmed delete, and the next startup also
    sweeps instance-owned rows. Together those two paths cover orderly stops,
    expired Guacamole tokens and abrupt process termination.
    """
    async with _guac_lock:
        for user_key, session in list(_guac_sessions.items()):
            try:
                deleted = await _guac_delete_with_fresh_token(
                    session["token"],
                    session["connection_id"],
                )
            except Exception as exc:
                logger.warning("RDP shutdown cleanup failed for %s: %s", user_key, exc)
                deleted = False
            if deleted:
                _guac_sessions.pop(user_key, None)

    async with _browser_lock:
        token = _browser_session.get("guac_token")
        connection_id = _browser_session.get("guac_conn_id")
        if token and connection_id:
            try:
                deleted = await _guac_delete_with_fresh_token(token, connection_id)
            except Exception as exc:
                logger.warning("Browser shutdown cleanup failed: %s", exc)
                deleted = False
            if not deleted:
                _guac_pending_cleanup[connection_id] = token
        _stop_browser_session()

    await _retry_pending_guacamole_cleanup()


async def startup_proxy_resources() -> None:
    """Initialize pooled resources and sweep crash-left Guacamole rows."""
    _warn_guac_config()
    await cleanup_stale_guacamole_connections()
