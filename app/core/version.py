"""Version helper — resolves version from git tags with fallback.

Version is read live from git so it updates after ``git pull`` without
requiring a server restart.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone

# Sybr HUB's product version. The imported MSP-Toolkit audit layer had its own
# 10.x lineage; using that value here made the API, reports and package metadata
# disagree about which product was running. pyproject.toml reads this attribute
# dynamically, making this the single release-version source.
__version__ = "0.1.0"

# ── Cached build info with TTL ────────────────────────────────────────────
_build_info_cache: dict | None = None
_build_info_ts: float = 0
_BUILD_INFO_TTL = 300  # refresh every 5 minutes


def get_version() -> str:
    """Return the live version — re-reads from git describe if available."""
    info = get_build_info()
    return info.get("version", __version__)


def get_build_info() -> dict:
    """Return version, commit hash, commit date and branch from git.

    Results are cached for 5 minutes so repeated API calls are fast,
    but a ``git pull`` is picked up without a restart.
    """
    global _build_info_cache, _build_info_ts

    now = time.monotonic()
    if _build_info_cache is not None and (now - _build_info_ts) < _BUILD_INFO_TTL:
        return _build_info_cache

    info: dict = {"version": __version__, "commit_hash": None, "commit_date": None, "branch": None}
    try:
        info["commit_hash"] = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip() or None
    except Exception:
        pass
    try:
        raw = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if raw:
            info["commit_date"] = raw
    except Exception:
        pass
    try:
        info["branch"] = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip() or None
    except Exception:
        pass

    # Try to read version from latest git tag (e.g. v9.3.0 → 9.3.0)
    try:
        tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if tag.startswith("v"):
            tag = tag[1:]
        if tag:
            info["version"] = tag
    except Exception:
        pass  # fall back to __version__

    _build_info_cache = info
    _build_info_ts = now
    return info
