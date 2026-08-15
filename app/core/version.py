"""Version helper — resolves version from git tags with fallback.

Version is read live from git so it updates after ``git pull`` without
requiring a server restart.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone


def _resolve_static_version() -> str:
    """The version for when git cannot answer.

    The git tag is the single release source. setuptools-scm writes the
    resolved value into ``app/core/_version.py`` at build time, and an
    installed distribution carries the same value in its metadata. A plain
    source checkout — which is how the service is deployed — has neither, and
    ``get_build_info`` reads ``git describe`` there, so this last resort only
    has to be well-formed rather than accurate.

    The imported MSP-Toolkit audit layer had its own 10.x lineage; using that
    value here made the API, reports and package metadata disagree about which
    product was running.
    """
    try:
        from app.core._version import version  # written by setuptools-scm

        return version
    except Exception:
        pass
    try:
        from importlib.metadata import version as _distribution_version

        return _distribution_version("sybr-hub")
    except Exception:
        pass
    return "0.0.0"


__version__ = _resolve_static_version()

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

    # Full describe (e.g. "1.1.1-3-g4f5c3da"): the clean tag `version` above is
    # what customer reports show, but a deployment several commits PAST the last
    # tag reads as stuck at that tag in the admin version card — which looks like
    # the self-updater did nothing. `describe` exposes the commits-ahead so the
    # card can say "1.1.1-3-g4f5c3da" and currency is obvious. Equals `version`
    # exactly when HEAD sits on the tag.
    try:
        desc = subprocess.check_output(
            ["git", "describe", "--tags"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if desc.startswith("v"):
            desc = desc[1:]
        info["describe"] = desc or info["version"]
    except Exception:
        info["describe"] = info["version"]

    _build_info_cache = info
    _build_info_ts = now
    return info
