"""FortiOS release branches and when Fortinet stops supporting them.

A **manually maintained** table, like the UniFi one in
``app/modules/unifi_audit/firmware_db.py``, with the same shelf life and the
same rule: a verdict the table cannot vouch for is "unknown", never "current".

Two questions are answered here, from two sources:

* **End of life** comes from this table. A branch whose End of Support date has
  passed is EOL for every device on it, whatever patch it runs. Fortinet has
  extended support dates before (7.4 and 7.6, in March 2026), so a date that
  passed *after* the table was last updated is not trusted from a stale table:
  it may have moved since.
* **Outdated** comes from the device. FortiGuard tells a FortiGate which
  releases it can move to (``/api/v2/monitor/system/firmware``, ``available``).
  A newer patch on the branch the device runs means it is behind. A device that
  reports no list at all cannot be confirmed current: an unlicensed unit, or
  one that cannot reach FortiGuard, answers with the same empty list a unit on
  the newest release does. That reads as "unknown".

Update process: refresh the dates from Fortinet's product life cycle page
(support.fortinet.com, Product Life Cycle, FortiOS) and set ``LAST_UPDATED``.
"""

from __future__ import annotations

import re
from datetime import date

LAST_UPDATED = "2026-10-03"
FRESHNESS_DAYS = 180
SOURCE = "fortios-lifecycle (manuell tabell)"

# Branch -> End of Support. Fortinet's dates as published on its life cycle
# page; 7.4 and 7.6 carry the March 2026 extension.
END_OF_SUPPORT: dict[tuple[int, int], str] = {
    (6, 0): "2022-09-29",
    (6, 2): "2023-09-28",
    (6, 4): "2024-09-30",
    (7, 0): "2025-09-30",
    (7, 2): "2026-09-30",
    (7, 4): "2028-11-11",
    (7, 6): "2030-01-25",
    (8, 0): "2030-10-21",
}

_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    """(major, minor, patch) from "v7.2.8", "7.2.8 build1639" and the like."""
    m = _VERSION.search(text or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _age_days(today: date) -> int | None:
    try:
        return (today - date.fromisoformat(LAST_UPDATED)).days
    except ValueError:
        return None


def is_stale(today: date | None = None) -> bool:
    """Past the freshness window, unparseable, or dated after today."""
    age = _age_days(today or date.today())
    return age is None or age < 0 or age > FRESHNESS_DAYS


def _available_versions(available: list | None) -> list[tuple[int, int, int]] | None:
    """The versions FortiGuard offers, or None when the list was not read."""
    if available is None:
        return None
    out = []
    for entry in available:
        if isinstance(entry, dict):
            v = parse_version(str(entry.get("version", "")))
            if v is None and all(isinstance(entry.get(k), int) for k in ("major", "minor")):
                v = (entry["major"], entry["minor"], int(entry.get("patch") or 0))
        else:
            v = parse_version(str(entry))
        if v:
            out.append(v)
    return out


def check_fortios(
    version: str | None,
    available: list | None = None,
    today: date | None = None,
) -> dict:
    """Classify a FortiGate's firmware.

    Returns ``{"status", "latest", "reason", "end_of_support", "source"}``:

    * status: "eol", "outdated", "current" or "unknown";
    * latest: the newest patch on the device's branch FortiGuard offers, or "";
    * reason: why the answer is "unknown" (a key the interface translates):
      ``version_unparsed``, ``no_firmware_list``, ``table_stale``.
    """
    today = today or date.today()
    out: dict = {
        "status": "unknown",
        "latest": "",
        "reason": "",
        "end_of_support": "",
        "source": f"{SOURCE} {LAST_UPDATED}",
    }
    current = parse_version(version)
    if current is None:
        out["reason"] = "version_unparsed"
        return out

    branch = current[:2]
    eos = END_OF_SUPPORT.get(branch)
    known = sorted(END_OF_SUPPORT)
    if eos is None and branch < known[0]:
        # Older than anything the table lists: long past its support.
        out["status"] = "eol"
        return out
    if eos:
        out["end_of_support"] = eos
        eos_date = date.fromisoformat(eos)
        if today > eos_date:
            # A date that had already passed when the table was written is
            # durable. One that passed since may have been extended meanwhile,
            # which only a fresh table can rule out.
            if eos_date <= date.fromisoformat(LAST_UPDATED) or not is_stale(today):
                out["status"] = "eol"
                return out
            out["reason"] = "table_stale"
            return out

    offered = _available_versions(available)
    newer_patch = sorted(v for v in (offered or []) if v[:2] == branch and v > current)
    if newer_patch:
        newest = newer_patch[-1]
        out["status"] = "outdated"
        out["latest"] = f"{newest[0]}.{newest[1]}.{newest[2]}"
        return out
    if not offered:
        out["reason"] = "no_firmware_list"
        return out
    out["status"] = "current"
    return out
