"""Web proxy routes — browse internal sites through the server's network.

Also provides remote-browser endpoints (Guacamole VNC + Chromium on Xvfb)
and remote-RDP endpoints (Apache Guacamole).
"""

from __future__ import annotations

import asyncio
import atexit
import base64
import logging
import os
import re
import shutil
import socket
import subprocess
from urllib.parse import quote, urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.user import Role, User
from app.web.middleware.auth import require_role

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Remote browser session state ──────────────────────────────────────────────

_browser_session: dict = {}  # keys: xvfb, chromium, x11vnc, vnc_port, url, display, guac_token, guac_conn_id
_browser_lock = asyncio.Lock()

_TIMEOUT = 10.0
_MAX_BODY = 10 * 1024 * 1024  # 10 MB
_ALLOWED_SCHEMES = {"http", "https"}
_VERIFY_SSL = os.environ.get("MSP_PROXY_VERIFY_SSL", "0") == "1"

# Shared httpx client with connection pooling (reused across requests)
_http_client = httpx.AsyncClient(
    timeout=_TIMEOUT,
    follow_redirects=True,
    verify=_VERIFY_SSL,
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    headers={"User-Agent": "MSP-Toolkit-Proxy/1.0"},
)


import ipaddress

# Private/internal IP ranges that must never be proxied
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local + cloud metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),          # IPv6 private
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]

_BLOCKED_HOSTNAMES = {
    "metadata.google.internal",
    "metadata.internal",
}


def _is_private_host(hostname: str) -> bool:
    """Check if a hostname resolves to a private/internal IP."""
    if hostname in _BLOCKED_HOSTNAMES:
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return any(addr in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        pass
    # Resolve DNS to check actual IP
    try:
        for info in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM):
            addr = ipaddress.ip_address(info[4][0])
            if any(addr in net for net in _BLOCKED_NETWORKS):
                return True
    except (socket.gaierror, OSError):
        pass
    return False


def _validate_url(url: str) -> str | None:
    """Return an error message if the URL is not allowed, else None."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return f"Ugyldig skjema: {parsed.scheme!r} — kun http/https er tillatt"
    if not parsed.hostname:
        return "Mangler vertsnavn i URL"
    if _is_private_host(parsed.hostname):
        return "Tilgang til interne/private adresser er blokkert"
    return None


def _rewrite_html(html: str, base_url: str) -> str:
    """Rewrite URLs in HTML so assets and links go through the proxy."""
    # Rewrite src="..." and href="..." attributes
    # For src= attributes, use /api/proxy/raw so images/CSS/JS load directly
    # For href= attributes, keep them as data attributes for JS-based navigation

    def _rewrite_attr(match: re.Match) -> str:
        attr = match.group(1)       # src or href
        quote_char = match.group(2)  # ' or "
        raw_url = match.group(3)

        # Skip anchors, javascript:, data:, and empty
        if not raw_url or raw_url.startswith(("#", "javascript:", "data:", "mailto:")):
            return match.group(0)

        # Resolve relative URLs against the base
        absolute = urljoin(base_url, raw_url)

        # Validate scheme of resolved URL
        parsed = urlparse(absolute)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return match.group(0)

        if attr.lower() == "src":
            proxy_url = "/api/proxy/raw?url=" + quote(absolute, safe="")
            return f'{attr}={quote_char}{proxy_url}{quote_char}'
        else:
            # href — rewrite to proxy fetch (JS will intercept clicks)
            proxy_url = "/api/proxy/raw?url=" + quote(absolute, safe="")
            return (
                f'href={quote_char}javascript:void(0){quote_char} '
                f'data-proxy-url={quote_char}{absolute}{quote_char}'
            )

    # Match src="..." href='...' (both quote styles)
    html = re.sub(
        r"""(src|href)\s*=\s*(["'])(.*?)\2""",
        _rewrite_attr,
        html,
        flags=re.IGNORECASE,
    )

    # Rewrite url(...) in inline styles (for background images etc.)
    def _rewrite_css_url(match: re.Match) -> str:
        raw_url = match.group(1).strip("'\"")
        if not raw_url or raw_url.startswith(("data:", "#")):
            return match.group(0)
        absolute = urljoin(base_url, raw_url)
        parsed = urlparse(absolute)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return match.group(0)
        return f'url("/api/proxy/raw?url={quote(absolute, safe="")}")'

    html = re.sub(r'url\(([^)]+)\)', _rewrite_css_url, html)

    # Inject a <base> so any remaining relative URLs resolve correctly
    # Also inject a click interceptor for proxied navigation
    inject = (
        '<script>'
        'document.addEventListener("click",function(e){'
        'var a=e.target.closest("[data-proxy-url]");'
        'if(a){'
        'e.preventDefault();'
        'window.parent.postMessage({type:"proxy-navigate",url:a.dataset.proxyUrl},"*");'
        '}'
        '});'
        '</script>'
    )
    # Insert after <head> if present, otherwise prepend
    if re.search(r'<head[^>]*>', html, re.IGNORECASE):
        html = re.sub(r'(<head[^>]*>)', r'\1' + inject, html, count=1, flags=re.IGNORECASE)
    else:
        html = inject + html

    return html


def _rewrite_css(css: str, base_url: str) -> str:
    """Rewrite url() references in CSS files."""
    def _rewrite(match: re.Match) -> str:
        raw_url = match.group(1).strip("'\"")
        if not raw_url or raw_url.startswith(("data:", "#")):
            return match.group(0)
        absolute = urljoin(base_url, raw_url)
        parsed = urlparse(absolute)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return match.group(0)
        return f'url("/api/proxy/raw?url={quote(absolute, safe="")}")'

    return re.sub(r'url\(([^)]+)\)', _rewrite, css)


# ── POST /api/proxy/fetch ───────────────────────────────────────────────────


@router.post("/proxy/fetch")
async def proxy_fetch(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Fetch a URL from the server's network and return the content."""
    body = await request.json()
    url = (body.get("url") or "").strip()
    if not url:
        raise ValidationError("URL er påkrevd")

    err = _validate_url(url)
    if err:
        raise ValidationError(err)

    try:
        resp = await _http_client.get(url)

        content_type = resp.headers.get("content-type", "")
        final_url = str(resp.url)

        if len(resp.content) > _MAX_BODY:
            return JSONResponse(
                {"error": f"Svaret er for stort ({len(resp.content)} bytes, maks {_MAX_BODY})"},
                status_code=413,
            )

        # For HTML content, rewrite URLs and return as JSON
        if "text/html" in content_type:
            html = resp.text
            html = _rewrite_html(html, final_url)
            return {
                "ok": True,
                "html": html,
                "content_type": content_type,
                "status_code": resp.status_code,
                "final_url": final_url,
            }

        # For non-HTML, return metadata (client should use /api/proxy/raw)
        return {
            "ok": True,
            "html": None,
            "content_type": content_type,
            "status_code": resp.status_code,
            "final_url": final_url,
        }

    except httpx.TimeoutException:
        raise IntegrationError(f"Tidsavbrudd etter {_TIMEOUT}s")
    except httpx.ConnectError as e:
        raise IntegrationError(f"Kunne ikke koble til: {e}")
    except Exception as e:
        logger.warning("Proxy fetch failed for %s: %s", url, e)
        raise IntegrationError(f"Feil ved henting: {e}")


# ── GET /api/proxy/raw ──────────────────────────────────────────────────────


@router.get("/proxy/raw")
async def proxy_raw(
    url: str = Query(..., description="URL to fetch raw content from"),
    user: User = Depends(require_role(Role.technician)),
):
    """Fetch raw content (images, CSS, JS) and return with proper content-type.

    Used by src= attributes in proxied HTML.
    """
    url = url.strip()
    if not url:
        raise ValidationError("URL er påkrevd")

    err = _validate_url(url)
    if err:
        raise ValidationError(err)

    try:
        resp = await _http_client.get(url)

        if len(resp.content) > _MAX_BODY:
            return JSONResponse({"error": "Svaret er for stort"}, status_code=413)

        content_type = resp.headers.get("content-type", "application/octet-stream")
        final_url = str(resp.url)

        # Rewrite CSS url() references
        if "text/css" in content_type:
            css = resp.text
            css = _rewrite_css(css, final_url)
            return Response(
                content=css.encode("utf-8"),
                media_type="text/css",
                headers={"Cache-Control": "public, max-age=300"},
            )

        return Response(
            content=resp.content,
            media_type=content_type.split(";")[0].strip(),
            headers={"Cache-Control": "public, max-age=300"},
        )

    except httpx.TimeoutException:
        raise IntegrationError("Tidsavbrudd")
    except httpx.ConnectError as e:
        raise IntegrationError(f"Kunne ikke koble til: {e}")
    except Exception as e:
        logger.warning("Proxy raw failed for %s: %s", url, e)
        raise IntegrationError(str(e))


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
    try:
        os.remove(f"/tmp/.X{n}-lock")
    except OSError:
        pass
    try:
        os.remove(f"/tmp/.X11-unix/X{n}")
    except OSError:
        pass
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
            try:
                os.remove(f)
            except OSError:
                pass
        return {"ok": True, "msg": "No session running"}

    display = _browser_session.get("display", ":99")
    for key in ("x11vnc", "chromium", "xvfb"):
        _kill_proc(_browser_session.get(key), key)

    # Clean up X lock files
    display_num = display.lstrip(":")
    for f in [f"/tmp/.X{display_num}-lock", f"/tmp/.X11-unix/X{display_num}"]:
        try:
            os.remove(f)
        except OSError:
            pass

    # Clean up temp Chrome profile
    chrome_profile = _browser_session.get("chrome_profile")
    if chrome_profile:
        try:
            shutil.rmtree(chrome_profile, ignore_errors=True)
        except Exception as e:
            logger.debug("Chrome profile cleanup failed: %s", e)

    _browser_session = {}
    return {"ok": True}


# Clean up on interpreter exit
atexit.register(_stop_browser_session)


@router.post("/browser/start")
async def browser_start(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Start a remote Chromium browser session accessible via Guacamole VNC."""
    global _browser_session

    async with _browser_lock:
        # If already running, return current session info
        if _browser_session.get("xvfb") and _browser_session["xvfb"].poll() is None:
            guac_url = None
            token = _browser_session.get("guac_token")
            conn_id = _browser_session.get("guac_conn_id")
            if token and conn_id:
                guac_url = _guac_client_url(conn_id, token)
            return {
                "ok": True,
                "guac_url": guac_url,
                "guac_token": token,
                "guac_connection_id": conn_id,
                "url": _browser_session.get("url", ""),
                "already_running": True,
            }

        # Parse optional URL from request body
        try:
            body = await request.json()
        except Exception as e:
            logger.debug("Could not parse request body as JSON: %s", e)
            body = {}
        target_url = (body.get("url") or "").strip()

        display = _find_free_display(50, 74)
        display_num = int(display.lstrip(":"))
        vnc_port = 5900 + display_num

        xvfb_bin = shutil.which("Xvfb") or "/usr/bin/Xvfb"
        chromium_bin = shutil.which("chromium") or "/snap/bin/chromium"
        x11vnc_bin = shutil.which("x11vnc") or "/usr/bin/x11vnc"

        env = os.environ.copy()
        devnull = subprocess.DEVNULL

        try:
            # 1. Start Xvfb — clean up stale locks first
            display_num_str = display.lstrip(":")
            for f in [f"/tmp/.X{display_num_str}-lock", f"/tmp/.X11-unix/X{display_num_str}"]:
                try:
                    os.remove(f)
                except OSError:
                    pass
            xvfb_proc = subprocess.Popen(
                [xvfb_bin, display, "-screen", "0", "1920x1080x24"],
                stdout=devnull, stderr=devnull, env=env,
            )
            await asyncio.sleep(0.5)
            if xvfb_proc.poll() is not None:
                raise IntegrationError("Xvfb startet ikke (exit code {})".format(xvfb_proc.returncode))

            # 2. Start Chromium with isolated profile
            # Snap Chromium can't start from a systemd service cgroup.
            # Use the actual binary inside the snap mount instead of the wrapper.
            import glob
            import tempfile
            chrome_profile = tempfile.mkdtemp(prefix="msp-browser-")
            chrome_env = {**env, "DISPLAY": display}

            # Find the real Chromium binary inside the snap
            snap_chrome = glob.glob("/snap/chromium/*/usr/lib/chromium-browser/chrome")
            if snap_chrome:
                real_chrome = sorted(snap_chrome)[-1]  # Latest revision
            else:
                real_chrome = chromium_bin  # Fallback to wrapper

            chrome_args = [
                real_chrome,
                "--no-sandbox",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-dev-shm-usage",
                "--window-size=1920,1080",
                "--window-position=0,0",
                "--no-first-run",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-sync",
                f"--user-data-dir={chrome_profile}",
            ]
            if target_url:
                chrome_args.append(target_url)

            chrome_log = open("/tmp/msp_chrome_start.log", "w")
            chromium_proc = subprocess.Popen(
                chrome_args,
                stdout=chrome_log, stderr=chrome_log, env=chrome_env,
            )
            await asyncio.sleep(3)
            if chromium_proc.poll() is not None:
                chrome_log.close()
                chrome_output = open("/tmp/msp_chrome_start.log").read()[-500:]
                _kill_proc(xvfb_proc, "xvfb")
                logger.error("Chromium exited immediately: %s", chrome_output)
                raise IntegrationError(f"Chromium krasjet ved oppstart: {chrome_output[:200]}")

            # 3. Start x11vnc (bind to 0.0.0.0 so Guacamole in Docker can reach it)
            vnc_log = open("/tmp/x11vnc_browser.log", "w")
            x11vnc_proc = subprocess.Popen(
                [
                    x11vnc_bin,
                    "-display", display,
                    "-nopw",
                    "-listen", "0.0.0.0",
                    "-xkb",
                    "-forever",
                    "-shared",
                    "-noxdamage",
                    "-rfbport", str(vnc_port),
                ],
                stdout=vnc_log, stderr=vnc_log, env=env,
            )
            await asyncio.sleep(1.0)
            if x11vnc_proc.poll() is not None:
                _kill_proc(chromium_proc, "chromium")
                _kill_proc(xvfb_proc, "xvfb")
                raise IntegrationError("x11vnc startet ikke")

            # 4. Create Guacamole VNC connection (Guacamole is in Docker)
            token = await _guac_login()
            if not token:
                _kill_proc(x11vnc_proc, "x11vnc")
                _kill_proc(chromium_proc, "chromium")
                _kill_proc(xvfb_proc, "xvfb")
                raise IntegrationError("Kunne ikke logge inn på Guacamole")

            docker_host = _docker_host_ip()
            conn = await _guac_create_vnc_connection(token, docker_host, vnc_port)
            if not conn or "identifier" not in conn:
                _kill_proc(x11vnc_proc, "x11vnc")
                _kill_proc(chromium_proc, "chromium")
                _kill_proc(xvfb_proc, "xvfb")
                raise IntegrationError("Kunne ikke opprette VNC-tilkobling i Guacamole")

            connection_id = conn["identifier"]
            guac_url = _guac_client_url(connection_id, token)

            _browser_session = {
                "xvfb": xvfb_proc,
                "chromium": chromium_proc,
                "x11vnc": x11vnc_proc,
                "vnc_port": vnc_port,
                "display": display,
                "url": target_url,
                "guac_token": token,
                "guac_conn_id": connection_id,
                "chrome_profile": chrome_profile,
            }

            logger.info(
                "Remote browser started: display=%s vnc=%d guac_conn=%s url=%s",
                display, vnc_port, connection_id, target_url or "(blank)",
            )

            return {
                "ok": True,
                "guac_url": guac_url,
                "guac_token": token,
                "guac_connection_id": connection_id,
                "url": target_url,
            }

        except FileNotFoundError as exc:
            _stop_browser_session()
            raise IntegrationError(f"Binar ikke funnet: {exc.filename}")
        except Exception as exc:
            _stop_browser_session()
            logger.exception("Failed to start remote browser")
            raise IntegrationError(str(exc))


@router.post("/browser/navigate")
async def browser_navigate(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Navigate the remote browser to a new URL (restarts Chromium)."""
    global _browser_session

    async with _browser_lock:
        if not _browser_session.get("xvfb") or _browser_session["xvfb"].poll() is not None:
            raise ValidationError("Ingen nettleser-sesjon kjører")

        body = await request.json()
        target_url = (body.get("url") or "").strip()
        if not target_url:
            raise ValidationError("URL er påkrevd")

        # Kill old Chromium
        _kill_proc(_browser_session.get("chromium"), "chromium")

        # Start new Chromium with the new URL
        display = _browser_session["display"]
        chromium_bin = shutil.which("chromium") or "/snap/bin/chromium"
        chrome_env = {**os.environ.copy(), "DISPLAY": display}

        chromium_proc = subprocess.Popen(
            [
                chromium_bin,
                "--no-sandbox",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-dev-shm-usage",
                "--start-maximized",
                "--no-first-run",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-sync",
                target_url,
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=chrome_env,
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
        # Delete Guacamole VNC connection first
        token = _browser_session.get("guac_token")
        conn_id = _browser_session.get("guac_conn_id")
        if token and conn_id:
            try:
                await _guac_delete_connection(token, conn_id)
            except Exception as exc:
                logger.warning("Failed to delete browser Guacamole connection: %s", exc)

        result = _stop_browser_session()
    return result


@router.get("/browser/status")
async def browser_status(
    user: User = Depends(require_role(Role.technician)),
):
    """Return whether a remote browser session is running."""
    async with _browser_lock:
        running = bool(
            _browser_session.get("xvfb")
            and _browser_session["xvfb"].poll() is None
        )
        guac_url = None
        token = None
        conn_id = None
        if running:
            token = _browser_session.get("guac_token")
            conn_id = _browser_session.get("guac_conn_id")
            if token and conn_id:
                guac_url = _guac_client_url(conn_id, token)
        return {
            "running": running,
            "guac_url": guac_url,
            "guac_token": token,
            "guac_connection_id": conn_id,
            "url": _browser_session.get("url", "") if running else "",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# REMOTE RDP — Apache Guacamole
# ═══════════════════════════════════════════════════════════════════════════════

def _get_guac_config() -> dict:
    """Load Guacamole config from encrypted app settings with env var fallback."""
    from app.core.config import load_app_settings
    settings = load_app_settings()
    return {
        "url": settings.get("guacamole_url") or os.environ.get("GUACAMOLE_URL", ""),
        "user": settings.get("guacamole_user") or os.environ.get("GUACAMOLE_USER", ""),
        "pass": settings.get("guacamole_pass") or os.environ.get("GUACAMOLE_PASS", ""),
    }


# Hosts permitted as Guacamole backend. Default to loopback only — the
# Docker compose stack the app installs runs Guacamole on localhost:8888.
# Operators that legitimately need a remote Guacamole can opt in via the
# MSP_GUACAMOLE_HOSTS env var (comma-separated). This stops a compromised
# settings.json from redirecting RDP/VNC sessions through an attacker-
# controlled Guacamole that captures credentials in transit.
_GUAC_DEFAULT_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}
_GUAC_EXTRA_HOSTS = {
    h.strip().lower()
    for h in os.environ.get("MSP_GUACAMOLE_HOSTS", "").split(",")
    if h.strip()
}
_GUAC_ALLOWED_HOSTS = _GUAC_DEFAULT_ALLOWED_HOSTS | _GUAC_EXTRA_HOSTS


def _validate_guac_url(url: str) -> str | None:
    """Return an error message if the configured Guacamole URL isn't safe.

    Rules: only http/https schemes, only allowlisted hosts. Empty URL is
    fine (the feature is just disabled).
    """
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Guacamole URL scheme must be http or https, got {parsed.scheme!r}"
    host = (parsed.hostname or "").lower()
    if host not in _GUAC_ALLOWED_HOSTS:
        return (
            f"Guacamole host {host!r} is not in the allowlist. "
            f"Allowed: {sorted(_GUAC_ALLOWED_HOSTS)}. "
            f"Add to MSP_GUACAMOLE_HOSTS env var if intentional."
        )
    return None


def _guac_base() -> str:
    """Return the Guacamole base URL from config, validated against allowlist.

    Returns "" if the configured URL is unsafe — callers already handle
    empty URL as "Guacamole not configured" so RDP/VNC stays disabled
    rather than reaching out to an attacker host.
    """
    url = _get_guac_config()["url"]
    err = _validate_guac_url(url)
    if err:
        logger.error("Guacamole URL rejected: %s", err)
        return ""
    return url


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


async def _guac_login() -> str | None:
    """Authenticate with Guacamole and return an auth token, or None."""
    cfg = _get_guac_config()
    if not cfg["url"] or not cfg["user"]:
        logger.warning("Guacamole login skipped — URL or user not configured")
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{cfg['url']}/api/tokens",
            data={"username": cfg["user"], "password": cfg["pass"]},
        )
        if resp.status_code == 200:
            return resp.json().get("authToken")
    return None


async def _guac_create_connection(
    token: str, host: str, port: int, username: str, password: str,
) -> dict | None:
    """Create an RDP connection in Guacamole. Returns the connection dict or None."""
    payload = {
        "parentIdentifier": "ROOT",
        "name": f"MSP-RDP-{host}-{port}",
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

        # If duplicate name, find existing and reuse it
        if resp.status_code in (400, 409):
            logger.info("Guacamole create failed (%d), looking for existing connection", resp.status_code)
            list_resp = await client.get(
                f"{_guac_base()}/api/session/data/mysql/connections",
                params={"token": token},
            )
            if list_resp.status_code == 200:
                for cid, conn in list_resp.json().items():
                    if conn.get("name") == payload["name"]:
                        # Update credentials on existing connection
                        await client.put(
                            f"{_guac_base()}/api/session/data/mysql/connections/{cid}",
                            params={"token": token},
                            json={**payload, "identifier": cid},
                        )
                        return {"identifier": cid, "name": conn["name"], "reused": True}

        logger.warning("Guacamole create connection failed: %d %s", resp.status_code, resp.text[:200])
    return None


async def _guac_delete_connection(token: str, connection_id: str) -> bool:
    """Delete a Guacamole connection. Returns True on success."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.delete(
            f"{_guac_base()}/api/session/data/mysql/connections/{connection_id}",
            params={"token": token},
        )
        return resp.status_code in (200, 204)


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
    token: str, host: str, port: int,
) -> dict | None:
    """Create a VNC connection in Guacamole for the remote browser.

    Returns the connection dict or None.
    """
    conn_name = "MSP-Browser"
    payload = {
        "parentIdentifier": "ROOT",
        "name": conn_name,
        "protocol": "vnc",
        "parameters": {
            "hostname": host,
            "port": str(port),
            "clipboard-encoding": "UTF-8",
            "resize-method": "reconnect",
            "color-depth": "32",
        },
        "attributes": {
            "max-connections": "2",
            "max-connections-per-user": "2",
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

        # If duplicate name, find existing and reuse it
        if resp.status_code in (400, 409):
            logger.info("Guacamole VNC create failed (%d), looking for existing", resp.status_code)
            list_resp = await client.get(
                f"{_guac_base()}/api/session/data/mysql/connections",
                params={"token": token},
            )
            if list_resp.status_code == 200:
                for cid, conn in list_resp.json().items():
                    if conn.get("name") == conn_name:
                        # Update parameters on existing connection
                        await client.put(
                            f"{_guac_base()}/api/session/data/mysql/connections/{cid}",
                            params={"token": token},
                            json={**payload, "identifier": cid},
                        )
                        return {"identifier": cid, "name": conn_name, "reused": True}

        logger.warning("Guacamole VNC create failed: %d %s", resp.status_code, resp.text[:200])
    return None


@router.post("/rdp/start")
async def rdp_start(
    request: Request,
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
                    existing["token"], existing["connection_id"],
                )
            except Exception as e:
                logger.warning("Failed to check Guacamole connection: %s", e)
                alive = False
            if alive:
                return {
                    "ok": True,
                    "guac_url": _guac_client_url(
                        existing["connection_id"], existing["token"],
                    ),
                    "guac_token": existing["token"],
                    "guac_connection_id": existing["connection_id"],
                    "already_running": True,
                }
            else:
                # Stale session — clean up
                _guac_sessions.pop(user_key, None)

        body = await request.json()
        host = (body.get("host") or "").strip()
        if not host:
            raise ValidationError("Vertsnavn er påkrevd")

        port = int(body.get("port") or 3389)
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""

        # 1. Login to Guacamole
        token = await _guac_login()
        if not token:
            raise IntegrationError("Kunne ikke logge inn på Guacamole")

        # 2. Create RDP connection
        conn = await _guac_create_connection(token, host, port, username, password)
        if not conn or "identifier" not in conn:
            raise IntegrationError("Kunne ikke opprette RDP-tilkobling i Guacamole")

        connection_id = conn["identifier"]
        guac_url = _guac_client_url(connection_id, token)

        _guac_sessions[user_key] = {
            "token": token,
            "connection_id": connection_id,
        }

    logger.info(
        "Guacamole RDP connection created: host=%s:%d connection_id=%s user=%s",
        host, port, connection_id, user_key,
    )

    return {
        "ok": True,
        "guac_url": guac_url,
        "guac_token": token,
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
        session = _guac_sessions.pop(user_key, None)
    if not session:
        return {"ok": True, "msg": "No RDP session running"}

    try:
        await _guac_delete_connection(session["token"], session["connection_id"])
    except Exception as exc:
        logger.warning("Failed to delete Guacamole connection: %s", exc)

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
                session["token"], session["connection_id"],
            )
        except Exception as e:
            logger.warning("Failed to check Guacamole connection: %s", e)
            alive = False

        if not alive:
            _guac_sessions.pop(user_key, None)

        return {
            "running": alive,
            "guac_url": _guac_client_url(
                session["connection_id"], session["token"],
            ) if alive else None,
            "guac_token": session["token"] if alive else None,
            "guac_connection_id": session["connection_id"] if alive else None,
        }


@router.post("/rdp/clipboard")
async def rdp_clipboard(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Send clipboard text to the active RDP session via Guacamole API."""
    user_key = str(user.id)
    async with _guac_lock:
        session = _guac_sessions.get(user_key)
    if not session:
        return {"ok": False, "error": "Ingen aktiv RDP-sesjon"}

    body = await request.json()
    text = body.get("text", "")
    if not text:
        return {"ok": False, "error": "Ingen tekst"}

    # Use Guacamole's active connection tunnel to send clipboard
    # The Guacamole API doesn't have a direct clipboard endpoint,
    # so we use xdotool on the server as fallback for RDP via guacd
    try:
        proc = await asyncio.create_subprocess_exec(
            "xdotool", "set-clipboard", "--", text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except Exception as e:
        logger.warning("Clipboard set via xdotool failed: %s", e)

    return {"ok": True}
