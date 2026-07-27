"""Append-only encrypted activity log.

Each entry is one JSON line in DATA_DIR/activity_log.jsonl, encrypted at rest.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import DATA_DIR

log = logging.getLogger(__name__)

_log_lock = threading.Lock()
_MAX_LOG_ENTRIES = 10000

_LOG_PATH = DATA_DIR / "activity_log.jsonl"

# Informational: the set of actions the UI knows how to label. Not enforced —
# an unrecognised action is still recorded, since dropping an audit entry is
# worse than showing an unfamiliar label.
VALID_ACTIONS = {
    "audit_started",
    "audit_completed",
    "report_generated",
    "customer_added",
    "customer_switched",
    "itglue_uploaded",
    "settings_changed",
    "email_sent",
    "remediation_updated",
    "also_sync",
    "ssh_key_push",
    "ssh_key_revoke",
    "fortigate_bootstrapped",
    "fortigate_credentials_viewed",
}


def log_activity(action: str, detail: str = "", customer: str = "", user: str = "") -> None:
    """Append one activity entry to the encrypted JSONL log.

    Uses per-line encryption so each append is O(1) — no full-file
    read-decrypt-append-encrypt-write cycle.
    """
    import base64

    from app.core.encryption import encrypt_text

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "detail": detail,
        "customer": customer,
        "user": user,
    }
    json_line = json.dumps(entry, ensure_ascii=False)
    # Encrypt this single entry and base64 encode so it's one safe line
    encrypted = base64.b64encode(encrypt_text(json_line)).decode("ascii")

    with _log_lock:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Rotate if too large (check line count periodically). Use binary
        # I/O throughout — legacy entries on disk may not be valid UTF-8
        # (older versions wrote plaintext JSON with a system-default encoding
        # on Windows) and decode errors would otherwise spam the log on
        # every single call.
        try:
            if _LOG_PATH.exists() and _LOG_PATH.stat().st_size > 0:
                with open(_LOG_PATH, "rb") as f:
                    line_count = sum(1 for _ in f)
                if line_count >= _MAX_LOG_ENTRIES:
                    with open(_LOG_PATH, "rb") as f:
                        all_lines = f.readlines()
                    with open(_LOG_PATH, "wb") as f:
                        f.writelines(all_lines[-(line_count // 2):])
        except Exception as e:
            log.warning("Log rotation check failed: %s", e)

        # Append single encrypted line — O(1) operation. Content is
        # base64-encoded ASCII so text mode is safe.
        with open(_LOG_PATH, "a", encoding="ascii") as f:
            f.write(encrypted + "\n")


def get_activity_log(limit: int = 50, offset: int = 0, customer: str = "") -> list[dict]:
    """Read the last *limit* entries from the activity log, with optional offset for pagination."""
    import base64

    from app.core.encryption import decrypt_text, is_encrypted

    if not _LOG_PATH.exists():
        return []

    try:
        raw = _LOG_PATH.read_bytes()
    except Exception as e:
        log.warning("Failed to read activity log: %s", e)
        return []

    # Support both legacy (full-file encrypted) and new (per-line encrypted) formats
    if is_encrypted(raw):
        # Legacy format: entire file is one encrypted blob
        try:
            text = decrypt_text(raw)
            raw_lines = [l for l in text.strip().split("\n") if l.strip()]
        except Exception:
            return []
    else:
        raw_lines = [l for l in raw.decode("utf-8", errors="replace").strip().split("\n") if l.strip()]

    # Decrypt per-line entries (base64-encoded encrypted JSON)
    json_lines: list[str] = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        # Try as plain JSON first (legacy unencrypted or migrated)
        if line.startswith("{"):
            json_lines.append(line)
            continue
        # Per-line encrypted format: base64 → decrypt → JSON
        try:
            encrypted_bytes = base64.b64decode(line)
            decrypted = decrypt_text(encrypted_bytes)
            json_lines.append(decrypted)
        except Exception:
            continue

    # Most recent last in file, reverse so newest first
    json_lines.reverse()

    # Parse and filter *before* paginating. Slicing first meant a customer
    # filter was applied only to the current page, so filtered queries
    # returned short or empty pages while matching entries sat further down.
    entries: list[dict] = []
    wanted = customer.lower() if customer else ""
    for line in json_lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if wanted and entry.get("customer", "").lower() != wanted:
            continue
        entries.append(entry)

    start = max(0, offset)
    return entries[start:start + limit]
