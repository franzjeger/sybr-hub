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

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse, JSONResponse, Response

from app.models.user import Role, User
from app.web.middleware.auth import require_audit_path_access, require_role
from app.web.middleware.security_headers import ARTEFACT_CSP

log = logging.getLogger(__name__)
router = APIRouter()

_STATIC_DIR = Path(__file__).parent.parent / "static"
_BRANDING_DIR = _STATIC_DIR / "branding"


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


# Each /static/ reference in the shell gets ?v=<hash of that file's bytes> when
# the shell is served. Hand-bumped numbers drifted: a file changed without its
# number, browsers kept serving their cached copy, and a deploy reached nobody
# until a hard reload.
# json before js, and a word boundary: "ui_i18n.json" must not match as ".js".
_SHELL_ASSET = re.compile(r"(/static/[A-Za-z0-9_./-]+\.(?:json|css|js)\b)(?:\?v=[A-Za-z0-9._-]*)?")
_file_digests: dict[tuple, str] = {}


def _file_digest(path: Path) -> str | None:
    import hashlib

    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    if (hit := _file_digests.get(key)) is not None:
        return hit
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    _file_digests[key] = digest
    return digest


# ── ES modules ───────────────────────────────────────────────────────────────
# The shell loads one module, main.js; every other module is reached through
# an import in another. A browser resolves import './app-ui.js' against the
# importing module's URL without its query, so the ?v= on main.js would not
# reach the modules it imports, and after a deploy the browser (or the service
# worker, which serves a versioned /static/ URL cache-first) would hand the new
# main.js the modules it already held.
#
# So the server versions the imports too. Every module in the graph is served
# with each relative import specifier rewritten to './x.js?v=<D>', and the
# shell's main.js carries the same ?v=<D>, where D is one digest over the
# bytes of every module in the graph. Change any module and every module URL
# changes; change none and every URL can be cached for good.
#
# One digest for the graph rather than one per file: a module's served bytes
# hold its imports' versions, so its own version would have to cover theirs,
# and theirs their imports', through a graph that has cycles. A deploy that
# touches one module re-downloads all of them (a few hundred kB), as the
# service worker's cache version already makes it do.
#
# The rewrite only has to understand the imports scripts/js-modules.cjs
# allows: static `import {a, b} from './x.js'` and `import './x.js'` at the
# start of a line, with './name.js' specifiers. Anything else fails that check.
_MODULE_TAG = re.compile(r'<script\b[^>]*\btype="module"[^>]*\bsrc="/static/([^"?]+\.js)"')
_MODULE_IMPORT = re.compile(
    r"""^(\s*import\s*(?:\{[^}]*\}\s*from\s*)?)(['"])\./([A-Za-z0-9_-]+\.js)(?:\?v=[^'"]*)?\2""",
    re.M,
)
_module_graph_cache: dict[str, tuple[list[Path], tuple, str]] = {}


def _module_imports(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [m.group(3) for m in _MODULE_IMPORT.finditer(source)]


def _stamp(paths: list[Path]) -> tuple:
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)


def _module_graph() -> tuple[frozenset[Path], str]:
    """Every module the shell's entry reaches, and one digest over all of them.

    The offline page's offline.js is a module too, but imports nothing and is
    served like any other file. Memoised against each module's and the
    shell's (mtime_ns, size): a deploy changes them, and a new module only
    joins the graph through an import in one that changed.
    """
    import hashlib

    shells = [s for s in [_STATIC_DIR / "index.html"] if s.is_file()]
    cached = _module_graph_cache.get(str(_STATIC_DIR))
    if cached is not None:
        paths, stamp, digest = cached
        try:
            if stamp == _stamp(shells + paths):
                return frozenset(paths), digest
        except OSError:
            pass

    queue: list[str] = []
    for shell in shells:
        queue.extend(_MODULE_TAG.findall(shell.read_text(encoding="utf-8")))
    found: list[Path] = []
    seen: set[Path] = set()
    while queue:
        path = _safe_child(_STATIC_DIR, queue.pop(0))
        if path is None or path in seen or not path.is_file():
            continue
        seen.add(path)
        found.append(path)
        queue.extend(_module_imports(path))
    paths = sorted(found)
    root = _STATIC_DIR.resolve()
    h = hashlib.sha256()
    for path in paths:
        h.update(path.relative_to(root).as_posix().encode() + b"\0")
        h.update(path.read_bytes() + b"\0")
    digest = h.hexdigest()[:12]
    _module_graph_cache.clear()
    _module_graph_cache[str(_STATIC_DIR)] = (paths, _stamp(shells + paths), digest)
    return frozenset(paths), digest


def _versioned_module(source: str, digest: str) -> str:
    """The module's source with every relative import carrying ?v=<digest>."""
    return _MODULE_IMPORT.sub(
        lambda m: f"{m.group(1)}{m.group(2)}./{m.group(3)}?v={digest}{m.group(2)}", source
    )


def _versioned(match: re.Match) -> str:
    ref = match.group(1)
    path = _safe_child(_STATIC_DIR, ref[len("/static/") :])
    if path is None or not path.is_file():
        return match.group(0)
    modules, graph_digest = _module_graph()
    digest = graph_digest if path in modules else _file_digest(path)
    return f"{ref}?v={digest}" if digest else match.group(0)


@router.get("/")
async def index() -> Response:
    source = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return Response(
        _SHELL_ASSET.sub(_versioned, source),
        media_type="text/html; charset=utf-8",
        # The shell names the asset versions, so it must never come from cache.
        headers={"Cache-Control": "no-cache"},
    )


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
    # ui_i18n.json is fetched by app-i18n.js rather than referenced in the
    # markup, so the scan above cannot see it; nor the modules main.js
    # imports, which no shell names.
    modules, _ = _module_graph()
    for extra in [_STATIC_DIR / "ui_i18n.json", *sorted(modules)]:
        if extra.is_file() and extra not in seen:
            seen.add(extra)
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

    The worker served everything under /static/ cache-first and only evicted
    when CACHE_VERSION changed. Left as a literal in the file it went stale —
    it still read v10.6.0 at app version 10.10.12 — so it was changed to derive
    from the app version instead.

    That was not enough. A release bumps the version; a deploy usually does
    not. A dozen front-end fixes shipped in one day under app version 10.10.12
    all landed on browsers that went on serving the app.js they already had —
    confirmed by asking a live page whether a function it should have had was
    there, and finding the old one. So the version is no longer the whole
    signal: the digest of what is actually being served is.

    It now keeps only versioned responses this server marks immutable, which
    cannot go stale under their URL. The digest still decides three things: a
    changed asset makes a new worker the browser offers as a new version, its
    activation drops what earlier deploys left in the cache, and its install
    stores the offline page as it is now.
    """
    from app.core.version import get_version

    source = (_STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    source = _SW_VERSION.sub(
        f"const CACHE_VERSION = 'msptoolkit-{get_version()}-{_static_digest()}'",
        source,
        count=1,
    )
    return Response(
        source,
        media_type="application/javascript",
        headers={
            # The worker script itself must never come from cache, or a
            # browser holding the old one never learns the version changed.
            "Cache-Control": "no-cache",
            # It lives under /static/ but has to control the interface at /.
            # A worker's scope may not reach above its own directory unless
            # its response allows it; registered with the default scope
            # (/static/) it controlled no page at all.
            "Service-Worker-Allowed": "/",
        },
    )


@router.get("/static/{filename:path}")
async def static_file(
    filename: str, v: str = "", if_none_match: str | None = Header(default=None)
) -> Response:
    if filename == "index.html":
        return JSONResponse({"error": "Not found"}, status_code=404)
    path = _safe_child(_STATIC_DIR, filename)
    if path is None:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    if not path.is_file():
        return JSONResponse({"error": "Not found"}, status_code=404)
    modules, graph_digest = _module_graph()
    if path in modules:
        return _module_response(path, v, graph_digest, if_none_match)
    # A URL carrying this file's own content hash can be kept forever: new
    # bytes get a new URL. Anything else revalidates on every load.
    immutable = bool(v) and v == _file_digest(path)
    return FileResponse(
        path,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache"
        },
    )


def _module_response(path: Path, v: str, graph_digest: str, if_none_match: str | None) -> Response:
    """A module of the interface, its imports versioned (see _module_graph).

    Under the graph's own ?v= it is immutable. Under any other URL (a bare
    one, or an old ?v= after a deploy) it is the current module, revalidated
    on every load: the ETag answers a repeat request with 304.
    """
    etag = f'"{graph_digest}-{_file_digest(path)}"'
    immutable = v == graph_digest
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache",
        "ETag": etag,
    }
    if if_none_match and etag in [tag.strip() for tag in if_none_match.split(",")]:
        return Response(status_code=304, headers=headers)
    source = _versioned_module(path.read_text(encoding="utf-8"), graph_digest)
    return Response(source, media_type="text/javascript; charset=utf-8", headers=headers)


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
    headers: dict[str, str] = {}
    if content_type == "text/html":
        headers["Content-Security-Policy"] = ARTEFACT_CSP
    return Response(content=data, media_type=content_type, headers=headers)


# ── System endpoints ─────────────────────────────────────────────────────────


@router.get("/api/version")
async def version_info() -> JSONResponse:
    from app.core.version import get_build_info

    return JSONResponse(get_build_info())


@router.get("/api/system-info")
async def system_info(_user: User = Depends(require_role(Role.admin))) -> dict:
    """Environment summary for whoever runs the server.

    Admin-only: it names the host's paths, Python, platform and PID, which a
    technician has no use for. The settings screen no longer shows it.
    """
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


# The buffer is a root-logger DEBUG capture across every subsystem and
# customer, unredacted — cross-customer names, hosts, integration diagnostics,
# and anything debug-logged that shape-based redaction missed. It is operator
# diagnostics, not viewer data, so both reading it and wiping it (anti-forensics
# on the diagnostic trail) are admin-only, matching /ssh/audit-log and /system/*.
@router.get("/api/logs")
async def get_logs(
    level: str = Query("DEBUG"),
    limit: int = Query(200),
    _user: User = Depends(require_role(Role.admin)),
) -> JSONResponse:
    levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    min_level = levels.get(level.upper(), 10)
    entries = [e for e in _LOG_BUFFER if logging.getLevelName(e["level"]) >= min_level]
    return JSONResponse({"logs": entries[-limit:]})


@router.post("/api/logs/clear")
async def clear_logs(_user: User = Depends(require_role(Role.admin))) -> dict:
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
        # CHANGELOG.md sits at the repository root and is not package data, so
        # it is simply absent from a wheel or container install. Saying so is
        # the point: an empty string rendered as a blank panel that looked
        # like "no releases yet" rather than "this build does not carry the
        # file", and nobody reported it because nothing looked broken.
        #
        # 200 rather than 503 — a 5xx here would make the SPA's generic error
        # handler retry twice and raise a toast, for a state a redeploy is the
        # only thing that changes.
        return JSONResponse(
            {
                "content": "",
                "html": "",
                "latest_html": "",
                "available": False,
                "reason": "not_packaged",
            }
        )

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
            "available": True,
        }
    )
