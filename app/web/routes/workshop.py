"""Shared workshop notes — wishlist, per-section discussion notes, follow-ups.

Backs the in-app Workshop view so attendees can capture input live during a
session and have it survive page reload. Stored as a single JSON file under
DATA_DIR; every authenticated user can read and write (this is a collab
scratchpad, not audit material).

Persistence is atomic: write to a sibling ``.tmp`` then ``replace`` so an
interrupted write never leaves a half-written file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.config import DATA_DIR
from app.models.user import Role, User
from app.web.middleware.auth import get_current_user, require_role

logger = logging.getLogger(__name__)
router = APIRouter()

_NOTES_PATH = Path(DATA_DIR) / "workshop_notes.json"
_DEFAULT: dict[str, Any] = {
    "wishlist": [],
    "discussion_notes": {},
    "followups": [],
}


def _load() -> dict[str, Any]:
    if not _NOTES_PATH.exists():
        return {"wishlist": [], "discussion_notes": {}, "followups": []}
    try:
        data = json.loads(_NOTES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("workshop_notes.json unreadable (%s); returning defaults", e)
        return {"wishlist": [], "discussion_notes": {}, "followups": []}
    if not isinstance(data, dict):
        return {"wishlist": [], "discussion_notes": {}, "followups": []}
    data.setdefault("wishlist", [])
    data.setdefault("discussion_notes", {})
    data.setdefault("followups", [])
    return data


def _save(data: dict[str, Any]) -> None:
    _NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _NOTES_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(_NOTES_PATH)


def _clean_followup(f: Any) -> dict[str, Any] | None:
    if not isinstance(f, dict):
        return None
    text = str(f.get("text", "")).strip()
    if not text:
        return None
    return {
        "id": int(f.get("id") or 0),
        "text": text,
        "owner": str(f.get("owner", "")).strip(),
        "due": str(f.get("due", "")).strip(),
        "done": bool(f.get("done", False)),
    }


@router.get("/workshop/notes")
async def get_workshop_notes(user: User = Depends(get_current_user)):
    """Return the current shared workshop notes."""
    return _load()


@router.post("/workshop/notes")
async def set_workshop_notes(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Upsert workshop notes. Body: {wishlist?, discussion_notes?, followups?}."""
    body = await request.json()
    data = _load()

    if isinstance(body.get("wishlist"), list):
        data["wishlist"] = [str(x).strip() for x in body["wishlist"] if str(x).strip()]

    if isinstance(body.get("discussion_notes"), dict):
        data["discussion_notes"] = {
            str(k): str(v) for k, v in body["discussion_notes"].items()
        }

    if isinstance(body.get("followups"), list):
        cleaned = [c for c in (_clean_followup(f) for f in body["followups"]) if c]
        # Assign monotonically increasing ids to new items (id=0).
        next_id = max((f["id"] for f in cleaned if f["id"] > 0), default=0) + 1
        for f in cleaned:
            if f["id"] <= 0:
                f["id"] = next_id
                next_id += 1
        data["followups"] = cleaned

    _save(data)
    logger.info(
        "workshop notes saved by user=%s (wishlist=%d, notes=%d, followups=%d)",
        user.username,
        len(data["wishlist"]),
        len(data["discussion_notes"]),
        len(data["followups"]),
    )
    return {"ok": True, "data": data}
