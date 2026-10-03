"""Serve the repo's docs/ markdown files to the in-app Docs viewer.

The frontend Docs tab fetches:
  GET /api/docs/list           -> tree of available *.md files
  GET /api/docs/file?path=...  -> raw markdown for a specific file

Path traversal is prevented by:
  * resolving the requested path relative to the docs/ root
  * rejecting anything that escapes the docs/ root
  * rejecting anything that isn't a .md file

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


def _node(path: Path) -> dict:
    """Recursive directory tree node. Files only — empty dirs collapsed out."""
    if path.is_file():
        return {
            "type": "file",
            "name": path.name,
            "path": str(path.relative_to(_DOCS_ROOT)),
        }
    children: list[dict] = []
    md_files = sorted(p for p in path.iterdir() if p.is_file() and p.suffix == ".md")
    sub_dirs = sorted(p for p in path.iterdir() if p.is_dir() and not p.name.startswith("."))
    # README first, then other md files, then sub-directories.
    md_files.sort(key=lambda p: (p.name.lower() != "readme.md", p.name.lower()))
    for f in md_files:
        children.append(_node(f))
    for d in sub_dirs:
        sub = _node(d)
        if sub.get("children"):
            children.append(sub)
    return {
        "type": "dir",
        "name": path.name,
        "path": str(path.relative_to(_DOCS_ROOT)) if path != _DOCS_ROOT else "",
        "children": children,
    }


@router.get("/docs/list")
async def docs_list(user: User = Depends(get_current_user)):
    """Return the tree of *.md files under docs/.

    ``docs/`` lives at the repository root and is not package data, so a wheel
    or container install does not carry it. An empty tree rendered as an empty
    Docs tab, which is indistinguishable from "this build ships no
    documentation" — so the absence is reported rather than drawn.
    """
    empty = {"type": "dir", "name": "docs", "path": "", "children": []}
    if not _DOCS_ROOT.exists():
        # 200, not 503: the SPA's generic handler turns any 5xx into a retry
        # toast and two more requests, which is the wrong answer for a state
        # that will never change without a redeploy. The flag is what the Docs
        # tab reads to say so in one line.
        return {"root": empty, "available": False, "reason": "not_packaged"}
    try:
        return {"root": _node(_DOCS_ROOT), "available": True}
    except Exception as e:
        logger.warning("Failed to build docs tree: %s", e)
        return {"root": empty, "available": False, "reason": "unreadable"}


@router.get("/docs/file")
async def docs_file(
    path: str = Query(..., description="Path relative to docs/ root"),
    user: User = Depends(get_current_user),
):
    """Return the raw markdown of one doc file."""
    p = _safe_path(path)
    if not p.exists() or not p.is_file():
        raise refusal(NotFoundError, "err_docs_not_found", path=path)
    return {
        "path": str(p.relative_to(_DOCS_ROOT)),
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
