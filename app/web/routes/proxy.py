"""Web proxy routes — browse internal sites through the server's network.

Also provides remote-browser endpoints (Guacamole VNC + Chromium on Xvfb)
and remote-RDP endpoints (Apache Guacamole).
"""

from __future__ import annotations

import asyncio
import atexit
import base64
import ipaddress
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
from contextlib import suppress
from urllib.parse import quote, urljoin, urlparse

import httpx
import nh3
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from app.core.exceptions import (
    ForbiddenError,
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
_VERIFY_SSL = os.environ.get("MSP_PROXY_VERIFY_SSL", "1") != "0"

# Shared httpx client with connection pooling (reused across requests)
_http_client = httpx.AsyncClient(
    timeout=_TIMEOUT,
    # Redirects are handled below so every hop is checked against the SSRF
    # policy. Letting httpx follow them would allow a public URL to bounce to
    # localhost, a private network or a cloud metadata endpoint.
    follow_redirects=False,
    verify=_VERIFY_SSL,
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    headers={"User-Agent": "MSP-Toolkit-Proxy/1.0"},
)

# Private/internal IP ranges that must never be proxied
_BLOCKED_HOSTNAMES = {
    "metadata.google.internal",
    "metadata.internal",
}

_REDIRECT_CODES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 5


class _ResponseTooLarge(Exception):
    pass


def _is_disallowed_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Reject every address that is not globally routable.

    ``is_private`` alone misses categories such as multicast, unspecified and
    documentation/reserved ranges on some Python versions. A server-side web
    proxy has no legitimate reason to connect to any of those ranges.
    """
    return not addr.is_global


def _is_private_host(hostname: str) -> bool:
    """Check if a hostname resolves to a non-public address, failing closed."""
    hostname = hostname.rstrip(".").lower()
    if hostname in _BLOCKED_HOSTNAMES:
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return _is_disallowed_ip(addr)
    except ValueError:
        pass
    # Resolve DNS to check actual IP
    try:
        for info in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM):
            addr = ipaddress.ip_address(info[4][0])
            if _is_disallowed_ip(addr):
                return True
    except (socket.gaierror, OSError):
        # An unresolvable host fails closed.
        return True
    return False


def _resolve_public_address(hostname: str) -> str:
    """Resolve and return a public address, refusing mixed/private answers."""
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_disallowed_ip(literal):
            raise ValidationError("Tilgang til interne/private adresser er blokkert")
        return str(literal)

    try:
        addresses = {
            ipaddress.ip_address(info[4][0])
            for info in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        }
    except (socket.gaierror, OSError) as exc:
        raise ValidationError("Vertsnavnet kunne ikke slås opp") from exc
    if not addresses or any(_is_disallowed_ip(address) for address in addresses):
        raise ValidationError("Tilgang til interne/private adresser er blokkert")
    return str(sorted(addresses, key=lambda address: (address.version, int(address)))[0])


def _validate_url(url: str) -> str | None:
    """Return an error message if the URL is not allowed, else None."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return f"Ugyldig skjema: {parsed.scheme!r} — kun http/https er tillatt"
    if not parsed.hostname:
        return "Mangler vertsnavn i URL"
    if parsed.username is not None or parsed.password is not None:
        return "Brukerinformasjon i URL er ikke tillatt"
    if _is_private_host(parsed.hostname):
        return "Tilgang til interne/private adresser er blokkert"
    return None


async def _safe_fetch(url: str) -> httpx.Response:
    """Fetch a bounded response while validating and pinning every DNS hop."""
    current_url = url
    for redirect_count in range(_MAX_REDIRECTS + 1):
        err = _validate_url(current_url)
        if err:
            raise ValidationError(err)

        # Resolve once, validate every answer, then connect to that exact IP.
        # Keeping the original Host header and TLS SNI preserves virtual hosts
        # and certificate validation while removing the DNS-rebinding window
        # between policy validation and httpx's connection.
        logical_url = httpx.URL(current_url)
        resolved_ip = _resolve_public_address(logical_url.host)
        pinned_url = logical_url.copy_with(host=resolved_ip)
        request = _http_client.build_request(
            "GET", pinned_url, headers={"Host": logical_url.netloc.decode("ascii")}
        )
        request.extensions["sni_hostname"] = logical_url.host
        response = await _http_client.send(request, stream=True)

        if response.status_code in _REDIRECT_CODES and response.headers.get("location"):
            location = response.headers["location"]
            await response.aclose()
            if redirect_count == _MAX_REDIRECTS:
                raise ValidationError("For mange videresendinger")
            current_url = urljoin(current_url, location)
            continue

        chunks: list[bytes] = []
        size = 0
        try:
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > _MAX_BODY:
                    raise _ResponseTooLarge
                chunks.append(chunk)
        finally:
            await response.aclose()

        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=b"".join(chunks),
            request=httpx.Request("GET", current_url),
        )

    raise ValidationError("For mange videresendinger")


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
        'window.parent.postMessage({type:"proxy-navigate",url:a.dataset.proxyUrl},window.location.origin);'
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


def _validate_browser_target(url: str) -> None:
    """Allow browser navigation only to ordinary HTTP(S) pages.

    Internal destinations are intentional for this feature, but local files,
    browser settings and executable schemes are not.
    """
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        raise ValidationError("Nettleseren tillater bare fullstendige http/https-URL-er")
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError("Brukerinformasjon i URL er ikke tillatt")


def _require_browser_owner(user: User) -> None:
    owner_id = _browser_session.get("owner_user_id")
    if owner_id and owner_id != str(user.id):
        raise ForbiddenError("Nettleserøkten tilhører en annen bruker")


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
        resp = await _safe_fetch(url)

        content_type = resp.headers.get("content-type", "")
        final_url = str(resp.url)

        # For HTML content, rewrite URLs and return as JSON
        if "text/html" in content_type:
            # The fetched document is attacker-controlled but is rendered from
            # our origin. Strip executable markup before URL rewriting; the
            # proxy's own small navigation helper is added afterwards.
            html = nh3.clean(resp.text, link_rel=None)
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

    except _ResponseTooLarge:
        return JSONResponse({"error": "Svaret er for stort"}, status_code=413)
    except ValidationError:
        raise
    except httpx.TimeoutException:
        raise IntegrationError(f"Tidsavbrudd etter {_TIMEOUT}s") from None
    except httpx.ConnectError as e:
        raise IntegrationError(f"Kunne ikke koble til: {e}") from e
    except Exception as e:
        logger.warning("Proxy fetch failed for %s: %s", url, e)
        raise IntegrationError(f"Feil ved henting: {e}") from e


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
        resp = await _safe_fetch(url)

        content_type = resp.headers.get("content-type", "application/octet-stream")
        final_url = str(resp.url)

        unsafe_types = (
            "text/html",
            "text/javascript",
            "application/javascript",
            "application/ecmascript",
            "image/svg+xml",
            "application/xml",
            "text/xml",
        )
        if any(content_type.lower().startswith(t) for t in unsafe_types):
            return JSONResponse(
                {"error": "Kjørbart eller aktivt innhold kan ikke hentes via råproxyen"},
                status_code=415,
            )

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

    except _ResponseTooLarge:
        return JSONResponse({"error": "Svaret er for stort"}, status_code=413)
    except ValidationError:
        raise
    except httpx.TimeoutException:
        raise IntegrationError("Tidsavbrudd") from None
    except httpx.ConnectError as e:
        raise IntegrationError(f"Kunne ikke koble til: {e}") from e
    except Exception as e:
        logger.warning("Proxy raw failed for %s: %s", url, e)
        raise IntegrationError(str(e)) from e


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
            _require_browser_owner(user)
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
        _validate_browser_target(target_url)

        display = _find_free_display(50, 74)
        display_num = int(display.lstrip(":"))
        vnc_port = 5900 + display_num

        xvfb_bin = shutil.which("Xvfb") or "/usr/bin/Xvfb"
        chromium_bin = shutil.which("chromium") or "/snap/bin/chromium"
        x11vnc_bin = shutil.which("x11vnc") or "/usr/bin/x11vnc"

        env = os.environ.copy()
        devnull = subprocess.DEVNULL
        xvfb_proc = None
        chromium_proc = None
        x11vnc_proc = None
        chrome_profile = None
        vnc_password_path = None

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
            if chrome_profile:
                shutil.rmtree(chrome_profile, ignore_errors=True)
            _stop_browser_session()

        try:
            # 1. Start Xvfb — clean up stale locks first
            display_num_str = display.lstrip(":")
            for f in [f"/tmp/.X{display_num_str}-lock", f"/tmp/.X11-unix/X{display_num_str}"]:
                with suppress(OSError):
                    os.remove(f)
            xvfb_proc = subprocess.Popen(
                [xvfb_bin, display, "-screen", "0", "1920x1080x24"],
                stdout=devnull, stderr=devnull, env=env,
            )
            await asyncio.sleep(0.5)
            if xvfb_proc.poll() is not None:
                raise IntegrationError(f"Xvfb startet ikke (exit code {xvfb_proc.returncode})")

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
                # Keep Chromium's user-namespace sandbox. Only disable the
                # legacy setuid helper, which is commonly unavailable inside
                # the hardened systemd service.
                "--disable-setuid-sandbox",
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

            with tempfile.TemporaryFile(mode="w+") as chrome_log:
                chromium_proc = subprocess.Popen(
                    chrome_args,
                    stdout=chrome_log, stderr=chrome_log, env=chrome_env,
                )
                await asyncio.sleep(3)
                if chromium_proc.poll() is not None:
                    chrome_log.seek(0)
                    chrome_output = chrome_log.read()[-500:]
                    _kill_proc(xvfb_proc, "xvfb")
                    logger.error("Chromium exited immediately: %s", chrome_output)
                    raise IntegrationError(
                        f"Chromium krasjet ved oppstart: {chrome_output[:200]}"
                    )

            # 3. Expose VNC only on the Docker-facing host address and protect
            # it with a high-entropy per-session password.
            docker_host = _docker_host_ip()
            vnc_password = secrets.token_urlsafe(32)
            with tempfile.NamedTemporaryFile(
                mode="w", prefix="sybr-vnc-", delete=False,
            ) as password_file:
                password_file.write(vnc_password + "\n")
                vnc_password_path = password_file.name
            os.chmod(vnc_password_path, 0o600)
            x11vnc_proc = subprocess.Popen(
                [
                    x11vnc_bin,
                    "-display", display,
                    # Do not expose the password in the process command line.
                    "-passwdfile", vnc_password_path,
                    "-listen", docker_host,
                    "-xkb",
                    "-forever",
                    "-shared",
                    "-noxdamage",
                    "-rfbport", str(vnc_port),
                ],
                stdout=devnull, stderr=devnull, env=env,
            )
            await asyncio.sleep(1.0)
            if x11vnc_proc.poll() is not None:
                _kill_proc(chromium_proc, "chromium")
                _kill_proc(xvfb_proc, "xvfb")
                raise IntegrationError("x11vnc startet ikke")
            with suppress(OSError):
                os.unlink(vnc_password_path)
            vnc_password_path = None

            # 4. Create Guacamole VNC connection (Guacamole is in Docker)
            token = await _guac_login()
            if not token:
                _kill_proc(x11vnc_proc, "x11vnc")
                _kill_proc(chromium_proc, "chromium")
                _kill_proc(xvfb_proc, "xvfb")
                raise IntegrationError("Kunne ikke logge inn på Guacamole")

            conn = await _guac_create_vnc_connection(
                token, docker_host, vnc_port, vnc_password,
            )
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
                "chromium_bin": real_chrome,
                "owner_user_id": str(user.id),
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
            _cleanup_failed_start()
            raise IntegrationError(f"Binar ikke funnet: {exc.filename}") from exc
        except Exception as exc:
            _cleanup_failed_start()
            logger.exception("Failed to start remote browser")
            raise IntegrationError(str(exc)) from exc


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
        _require_browser_owner(user)

        body = await request.json()
        target_url = (body.get("url") or "").strip()
        if not target_url:
            raise ValidationError("URL er påkrevd")
        _validate_browser_target(target_url)

        # Kill old Chromium
        _kill_proc(_browser_session.get("chromium"), "chromium")

        # Start new Chromium with the new URL
        display = _browser_session["display"]
        chromium_bin = _browser_session.get("chromium_bin") or shutil.which("chromium") or "/snap/bin/chromium"
        chrome_env = {**os.environ.copy(), "DISPLAY": display}

        chromium_proc = subprocess.Popen(
            [
                chromium_bin,
                "--disable-setuid-sandbox",
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
        _require_browser_owner(user)
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
        if running and _browser_session.get("owner_user_id") != str(user.id):
            return {"running": False}
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
    token: str, host: str, port: int, password: str,
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


async def _get_authorized_rdp_host(user: User, host_id: str):
    """Resolve an RDP target from inventory and enforce its customer scope."""
    from app.core.rbac import check_customer_access, get_accessible_customer_ids
    from app.services.ssh_manager import get_host

    if not host_id:
        raise ValidationError("Velg en registrert host")
    host = await get_host(host_id)
    if host is None:
        raise NotFoundError("Host finnes ikke")

    if host.customer_id:
        allowed = await check_customer_access(user, host.customer_id)
    else:
        allowed = await get_accessible_customer_ids(user) is None
    if not allowed:
        logger.info(
            "403 RDP host-access: user=%s host=%s customer=%s",
            user.username, host_id, host.customer_id,
        )
        raise ForbiddenError("Du har ikke tilgang til denne hosten")
    return host


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
        host_record = await _get_authorized_rdp_host(
            user, (body.get("host_id") or "").strip(),
        )
        host = host_record.hostname
        try:
            port = int(body.get("port") or 3389)
        except (TypeError, ValueError):
            raise ValidationError("Ugyldig RDP-port") from None
        if not 1 <= port <= 65535:
            raise ValidationError("Ugyldig RDP-port")
        username = (body.get("username") or host_record.username or "").strip()
        password = body.get("password") or ""
        if not password:
            from app.services.ssh_manager import _load_host_password
            password = _load_host_password(host_record.id) or ""

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
