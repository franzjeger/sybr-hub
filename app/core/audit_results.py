"""Small transport-independent contracts shared by collectors and consumers."""

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

_EXPIRY_SUMMARY = re.compile(r"^\s*(\d+) expired,\s*(\d+) expiring within \d+ days\.", re.M)


def credential_expiry_counts(warning: str) -> tuple[int, int] | None:
    """Parse the collector's summary, never app names or the generic heading."""
    match = _EXPIRY_SUMMARY.search(warning)
    return (int(match[1]), int(match[2])) if match else None


def new_run_directory(root: Path) -> Path:
    """Sort chronologically and never reuse another run's directory."""
    name = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S_%f") + "_" + uuid4().hex[:12]
    directory = root / name
    directory.mkdir(parents=True, exist_ok=False)
    return directory
