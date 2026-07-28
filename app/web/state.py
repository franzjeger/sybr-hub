"""Shared mutable state for the MSP Toolkit web server.

This module centralises the global variables that were previously scattered
across server.py.  Route modules import from here instead of keeping their
own copies.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

# ── Audit state ─────────────────────────────────────────────────────────
audit_running: bool = False
audit_cancel_requested: bool = False
audit_results: list = []
audit_out_dir: Optional[Path] = None
setup_running: bool = False
bulk_audit_running: bool = False
audit_lock = asyncio.Lock()

# ── Audit progress tracking (for REST polling) ───────────────────────
# Keyed by customer_id (or "active" for single-customer audits).
# Value: {"progress": 0-100, "current_section": "...", "total_sections": N, "completed": N}
audit_progress: dict[str, dict] = {}
