"""Front-end asset serving plus the small system endpoints the admin panel reads.

Kept out of ``app.web.server`` so the application factory stays a factory.
The paths here are the ones the browser asks for directly — the SPA shell,
its static assets, branding images, generated audit reports — together with
``/api/version``, ``/api/system-info``, ``/api/logs`` and ``/api/changelog``.

Log capture is opt-in: :func:`install_log_capture` attaches the in-memory
ring buffer and the rotating file handler. It is called from the server's
lifespan rather than at import, so importing this module has no side effect
on the root logger (which would otherwise fire during test collection).
"""

from __future__ import annotations

import html as _html
import logging
import logging.handlers
import mimetypes
import os
import platform
import re
import sys
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, JSONResponse, Response

from app.models.user import User
from app.web.middleware.auth import get_current_user, require_audit_path_access

log = logging.getLogger(__name__)
router = APIRouter()

_STATIC_DIR = Path(__file__).parent.parent / "static"
_BRANDING_DIR = Path(__file__).parent.parent.parent.parent / "Logo-Branding"


# ── Log capture ──────────────────────────────────────────────────────────────

_LOG_BUFFER: deque[dict] = deque(maxlen=500)
_capture_installed = False


class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        _LOG_BUFFER.append(
            {
                "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": self.format(record),
            }
        )


def install_log_capture() -> None:
    """Attach the ring buffer and the rotating file log to the root logger.

    Idempotent — the server calls this once at startup, but a re-entry (an
    app factory invoked twice in a test session) must not stack handlers.
    """
    global _capture_installed
    if _capture_installed:
        return

    from app.core.config import DATA_DIR

    buf_handler = _BufferHandler()
    buf_handler.setFormatter(logging.Formatter("%(message)s"))
    buf_handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    root.addHandler(buf_handler)

    log_file = DATA_DIR / "msp_toolkit.log"
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_file), maxBytes=100 * 1024 * 1024, backupCount=20, encoding="utf-8"
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root.addHandler(file_handler)
    except OSError as e:
        # A read-only or missing data dir must not stop the app from serving;
        # the in-memory buffer still backs /api/logs.
        log.warning("File logging unavailable (%s) — using the in-memory buffer only", e)

    _capture_installed = True


# ── Static assets ────────────────────────────────────────────────────────────


def _safe_child(root: Path, relative: str) -> Path | None:
    """Resolve ``relative`` under ``root``, or None if it escapes.

    Containment is checked on the resolved path *before* the caller touches
    the filesystem, so a traversal attempt never reaches a stat() call.
    """
    try:
        candidate = (root / relative).resolve()
        candidate.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return candidate


@router.get("/")
async def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@router.get("/favicon.ico")
async def favicon() -> Response:
    ico = _STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(ico)
    # 204 rather than falling through to the auth layer's 401 — otherwise the
    # browser re-asks on every navigation and floods the auth log.
    return Response(status_code=204)


_SW_VERSION = re.compile(r"const CACHE_VERSION = '[^']*'")

# Assets the online and offline shells pull in themselves, so the set cannot
# drift from what the pages actually load. It used to be a hand-written four — app.js, app.css,
# index.html, ui_i18n.json — which left the other six front-end bundles out of
# the digest entirely. A release touching only one of those (Build 7a rewrote
# app-dashboard.js) produced an unchanged CACHE_VERSION, so the worker kept
# serving the copy it already had. Build 7a only escaped that because it
# happened to also touch app.css and ui_i18n.json.
# json before js: the alternation is ordered, and "js" would otherwise match
# inside manifest.json and hand back a manifest.js that does not exist.
_ASSET_REF = re.compile(r"/static/([A-Za-z0-9_./-]+\.(?:json|css|js))")

# Hashing bytes is not free and sw.js is fetched on every navigation, so the
# result is memoised against each file's (mtime_ns, size). A deploy changes
# both, which is the same signal the digest is there to catch.
_digest_cache: dict[tuple, str] = {}


def _digest_inputs() -> list[Path]:
    shells = [_STATIC_DIR / "index.html", _STATIC_DIR / "offline.html"]
    shells = [path for path in shells if path.exists()]
    if not shells:
        return []
    paths = list(shells)
    seen = set(shells)
    for shell in shells:
        source = shell.read_text(encoding="utf-8", errors="replace")
        for ref in _ASSET_REF.findall(source):
            path = _safe_child(_STATIC_DIR, ref)
            if path is not None and path.is_file() and path not in seen:
                seen.add(path)
                paths.append(path)
    # ui_i18n.json is fetched by app.js rather than referenced in the markup,
    # so the scan above cannot see it.
    extra = _STATIC_DIR / "ui_i18n.json"
    if extra.is_file() and extra not in seen:
        paths.append(extra)
    return sorted(paths)


def _static_digest() -> str:
    import hashlib

    paths = _digest_inputs()
    try:
        stamp = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    except OSError:
        stamp = ()
    if stamp and (hit := _digest_cache.get(stamp)) is not None:
        return hit

    h = hashlib.sha256()
    for path in paths:
        try:
            h.update(path.read_bytes())
        except OSError:
            continue
    digest = h.hexdigest()[:12]
    if stamp:
        _digest_cache.clear()  # only the current deploy's entry is of any use
        _digest_cache[stamp] = digest
    return digest




# Registered before the catch-all below, which would otherwise serve sw.js
# verbatim — FastAPI matches routes in registration order.
@router.get("/static/sw.js")
async def service_worker() -> Response:
    """Serve the worker with CACHE_VERSION pinned to the served assets.

    Everything under /static/ is cached cache-first, and the worker only evicts
    when CACHE_VERSION changes. Left as a literal in the file it went stale —
    it still read v10.6.0 at app version 10.10.12 — so it was changed to derive
    from the app version instead.

    That was not enough. A release bumps the version; a deploy usually does
    not. A dozen front-end fixes shipped in one day under app version 10.10.12
    all landed on browsers that went on serving the app.js they already had —
    confirmed by asking a live page whether a function it should have had was
    there, and finding the old one. So the version is no longer the whole
    signal: the digest of what is actually being served is.
    """
    from app.core.version import get_version

    source = (_STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    source = _SW_VERSION.sub(
        f"const CACHE_VERSION = 'msptoolkit-{get_version()}-{_static_digest()}'",
        source, count=1,
    )
    return Response(
        source,
        media_type="application/javascript",
        # The worker script itself must never come from cache, or a browser
        # holding the old one never learns the version changed.
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/static/{filename:path}")
async def static_file(filename: str) -> Response:
    if filename == "index.html":
        return JSONResponse({"error": "Not found"}, status_code=404)
    path = _safe_child(_STATIC_DIR, filename)
    if path is None:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    if not path.is_file():
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(path)


@router.get("/branding/{filename}")
async def branding(filename: str) -> Response:
    path = _safe_child(_BRANDING_DIR, filename)
    if path is None:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    if not path.is_file():
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(path)


@router.get("/audit_data/{path:path}")
async def serve_audit_data(
    path: str, user: User = Depends(require_audit_path_access())
) -> Response:
    """Serve a generated audit artefact, decrypting it on the way out.

    Two separate guards, because they answer different questions.
    ``_safe_child`` stops the path escaping the audit root; it says nothing
    about *whose* data is inside it. The first path segment is the customer's
    directory, so without ``require_audit_path_access`` any authenticated
    account could read every customer's decrypted reports and raw tenant dumps
    — and /api/history and /api/reports/archive hand out the exact paths.

    Resolved through get_audit_dir() rather than the AUDIT_DIR constant: that
    constant is bound at import, so after an operator changes the audit
    directory in Settings this kept serving the old tree until a restart.
    """
    from app.core.config import get_audit_dir
    from app.core.encryption import encrypted_read_bytes

    file_path = _safe_child(get_audit_dir(), path)
    if file_path is None:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    if not file_path.is_file():
        return JSONResponse({"error": "Not found"}, status_code=404)

    data = encrypted_read_bytes(file_path)
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return Response(content=data, media_type=content_type)


# ── System endpoints ─────────────────────────────────────────────────────────


@router.get("/api/version")
async def version_info() -> JSONResponse:
    from app.core.version import get_build_info

    return JSONResponse(get_build_info())


@router.get("/api/system-info")
async def system_info(_user: User = Depends(get_current_user)) -> dict:
    """Environment summary for the admin panel."""
    from app.core.config import DATA_DIR, get_audit_dir
    from app.core.database import DB_PATH

    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0

    audit_dir = get_audit_dir()
    audit_files = audit_size = 0
    if audit_dir.exists():
        for f in audit_dir.rglob("*"):
            if f.is_file():
                audit_files += 1
                audit_size += f.stat().st_size

    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "data_dir": str(DATA_DIR),
        "audit_dir": str(audit_dir),
        "db_size_mb": round(db_size / 1048576, 2),
        "audit_files": audit_files,
        "audit_size_mb": round(audit_size / 1048576, 1),
        "pid": os.getpid(),
    }


@router.get("/api/logs")
async def get_logs(
    level: str = Query("DEBUG"),
    limit: int = Query(200),
    _user: User = Depends(get_current_user),
) -> JSONResponse:
    levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    min_level = levels.get(level.upper(), 10)
    entries = [e for e in _LOG_BUFFER if logging.getLevelName(e["level"]) >= min_level]
    return JSONResponse({"logs": entries[-limit:]})


@router.post("/api/logs/clear")
async def clear_logs(_user: User = Depends(get_current_user)) -> dict:
    _LOG_BUFFER.clear()
    return {"ok": True}


# ── Changelog ────────────────────────────────────────────────────────────────

_CHANGELOG = Path(__file__).parent.parent.parent.parent / "CHANGELOG.md"


def _md_to_html(text: str) -> str:
    """Render the small Markdown subset the changelog uses.

    Deliberately dependency-free: headings, bullet lists, inline code and
    paragraphs. Everything is HTML-escaped first, so the changelog cannot
    inject markup into the admin panel.
    """
    out: list[str] = []
    in_list = False
    for line in text.split("\n"):
        stripped = line.strip()
        safe = _html.escape(stripped).replace("**", "")
        safe = re.sub(r"`([^`]+)`", r"<code>\1</code>", safe)

        if stripped.startswith("## ") or stripped.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            tag, cut = ("h2", 3) if stripped.startswith("## ") else ("h3", 4)
            out.append(f"<{tag}>{safe[cut:]}</{tag}>")
        elif stripped.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{safe.lstrip('- ').lstrip()}</li>")
        elif stripped == "" or stripped.startswith("---"):
            if in_list and stripped == "":
                out.append("</ul>")
                in_list = False
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{safe}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


@router.get("/api/changelog")
async def changelog() -> JSONResponse:
    if not _CHANGELOG.exists():
        return JSONResponse({"content": "", "html": "", "latest_html": ""})

    md = _CHANGELOG.read_text(encoding="utf-8")

    # The panel shows the three most recent versions inline and keeps the
    # rest behind "show all".
    latest_lines: list[str] = []
    seen = 0
    for line in md.split("\n"):
        if line.startswith("## v"):
            seen += 1
            if seen > 3:
                break
        latest_lines.append(line)

    return JSONResponse(
        {
            "content": md,
            "html": _md_to_html(md),
            "latest_html": _md_to_html("\n".join(latest_lines)),
        }
    )
