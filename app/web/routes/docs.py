"""Serve the documents a person using the app reads to the in-app Docs view.

The frontend Docs view fetches:
  GET /api/docs/list           -> the documents on offer
  GET /api/docs/file?path=...  -> raw markdown for one of them

On offer: the user guide when the build has one, and the changelog. The
view used to list every file under docs/, so a technician opening
"Dokumentasjon" met ARCHITECTURE, TODO and CRITICAL REVIEW CHECKLIST: the
repository's working notes, written for whoever changes the code. Those stay
in the repository, where that reader already is.

A request names a document from the list; anything else is not found.
Before that lookup the path is still refused when it is empty, escapes the
docs/ root or is not a .md file, so a malformed request keeps its message.

Auth: any authenticated user. Docs aren't sensitive but they describe
the system to a degree we don't want to expose unauthenticated.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.core.exceptions import NotFoundError, ValidationError
from app.models.user import User
from app.web.i18n import refusal
from app.web.middleware.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

# Repo layout: app/web/routes/docs.py -> app/web/routes -> app/web -> app -> repo
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DOCS_ROOT = _REPO_ROOT / "docs"

# The documents the view offers, by the name the interface asks for, with
# the key it translates the title from. Listed in this order when present.
_USER_DOCUMENTS: dict[str, tuple[str, Path]] = {
    "USER_GUIDE.md": ("guide", _DOCS_ROOT / "USER_GUIDE.md"),
    "CHANGELOG.md": ("changelog", _REPO_ROOT / "CHANGELOG.md"),
}

# Image assets served via /docs/asset. Executable or ambiguous types are
# intentionally excluded — this endpoint is for diagrams and illustrations
# referenced from markdown, not a generic static-file server.
_ASSET_EXTENSIONS: dict[str, str] = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _safe_path(rel: str) -> Path:
    """Resolve `rel` under _DOCS_ROOT, refusing escapes and non-.md files."""
    if not rel:
        raise refusal(ValidationError, "err_docs_path_required")
    candidate = (_DOCS_ROOT / rel).resolve()
    try:
        candidate.relative_to(_DOCS_ROOT.resolve())
    except ValueError as exc:
        raise refusal(ValidationError, "err_docs_path_escapes") from exc
    if candidate.suffix.lower() != ".md":
        raise refusal(ValidationError, "err_docs_only_markdown")
    return candidate


def _safe_asset_path(rel: str) -> Path:
    """Resolve `rel` under _DOCS_ROOT, refusing escapes and non-image types."""
    if not rel:
        raise refusal(ValidationError, "err_docs_path_required")
    candidate = (_DOCS_ROOT / rel).resolve()
    try:
        candidate.relative_to(_DOCS_ROOT.resolve())
    except ValueError as exc:
        raise refusal(ValidationError, "err_docs_path_escapes") from exc
    if candidate.suffix.lower() not in _ASSET_EXTENSIONS:
        raise refusal(
            ValidationError, "err_docs_asset_type", allowed=", ".join(sorted(_ASSET_EXTENSIONS))
        )
    return candidate


@router.get("/docs/list")
async def docs_list(user: User = Depends(get_current_user)):
    """Return the documents on offer, as a one-level tree.

    The documents live in the repository, not in package data, so a wheel
    install may carry none. An empty list rendered as an empty Docs view,
    which reads as "there are no documents" — so the absence is reported
    rather than drawn.
    """
    children = [
        {"type": "file", "name": name, "path": name, "key": key}
        for name, (key, path) in _USER_DOCUMENTS.items()
        if path.is_file()
    ]
    root = {"type": "dir", "name": "docs", "path": "", "children": children}
    if not children:
        # 200, not 503: the SPA's generic handler turns any 5xx into a retry
        # toast and two more requests, which is the wrong answer for a state
        # that will never change without a redeploy. The flag is what the Docs
        # view reads to say so in one line.
        return {"root": root, "available": False, "reason": "not_packaged"}
    return {"root": root, "available": True}


@router.get("/docs/file")
async def docs_file(
    path: str = Query(..., description="Path relative to docs/ root"),
    user: User = Depends(get_current_user),
):
    """Return the raw markdown of one document the list offers."""
    _safe_path(path)
    entry = _USER_DOCUMENTS.get(path)
    p = entry[1] if entry else None
    if p is None or not p.is_file():
        raise refusal(NotFoundError, "err_docs_not_found", path=path)
    return {
        "path": path,
        "name": p.name,
        "content": p.read_text(encoding="utf-8"),
        "size": p.stat().st_size,
    }


@router.get("/docs/asset")
async def docs_asset(
    path: str = Query(..., description="Path relative to docs/ root"),
    user: User = Depends(get_current_user),
):
    """Stream a raw image asset (svg/png/jpg/webp/gif) from docs/.

    Auth is required like the rest of the docs routes; the AuthMiddleware
    accepts the ``access_token`` cookie set on login, so browsers can use
    this URL directly as ``<img src=...>`` without extra headers.
    """
    p = _safe_asset_path(path)
    if not p.exists() or not p.is_file():
        raise refusal(NotFoundError, "err_docs_asset_not_found", path=path)
    media_type = _ASSET_EXTENSIONS[p.suffix.lower()]
    return FileResponse(p, media_type=media_type, filename=p.name)
