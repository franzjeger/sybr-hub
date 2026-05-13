"""UniFi firmware version database for audit comparison.

Maps board/model names to latest known stable firmware.
Updated manually — run `update_from_ui_com()` to fetch latest from ui.com.
"""

from __future__ import annotations

import logging
from datetime import date

log = logging.getLogger(__name__)

# Last updated date
LAST_UPDATED = "2026-03-30"

# Model → latest stable firmware mapping
# Source: https://community.ui.com/releases + ui.com/download
FIRMWARE_DB: dict[str, dict] = {
    # ── Access Points ─────────────────────────────────────────────
    # U6 / U7 series
    "U6-Pro":       {"latest": "6.6.77", "eol": False},
    "U6-Lite":      {"latest": "6.6.77", "eol": False},
    "U6-LR":        {"latest": "6.6.77", "eol": False},
    "U6-Mesh":      {"latest": "6.6.77", "eol": False},
    "U6-Enterprise":{"latest": "6.6.77", "eol": False},
    "U6-IW":        {"latest": "6.6.77", "eol": False},
    "U7-Pro":       {"latest": "7.0.97", "eol": False},
    "U7-Pro-Max":   {"latest": "7.0.97", "eol": False},
    "U7-Outdoor":   {"latest": "7.0.97", "eol": False},
    # UAP classic
    "UAP":          {"latest": "6.6.77", "eol": True},
    "UAP-AC-Pro":   {"latest": "6.6.77", "eol": False},
    "UAP-AC-Lite":  {"latest": "6.6.77", "eol": False},
    "UAP-AC-LR":    {"latest": "6.6.77", "eol": False},
    "UAP-AC-Mesh":  {"latest": "6.6.77", "eol": False},
    "UAP-AC-EDU":   {"latest": "6.6.77", "eol": False},
    "UAP-AC-HD":    {"latest": "6.6.77", "eol": False},
    "UAP-AC-SHD":   {"latest": "6.6.77", "eol": False},
    "UAP-AC-IW":    {"latest": "6.6.77", "eol": False},
    "UAP-AC-IW-Pro":{"latest": "6.6.77", "eol": False},
    "UAP-nanoHD":   {"latest": "6.6.77", "eol": False},
    "UAP-FlexHD":   {"latest": "6.6.77", "eol": False},
    "UAP-BeaconHD": {"latest": "6.6.77", "eol": False},
    # UAP legacy (EOL)
    "UAP-LR":       {"latest": "4.3.28", "eol": True},
    "UAP-Pro":      {"latest": "4.3.28", "eol": True},
    "UAP-Outdoor":  {"latest": "4.3.28", "eol": True},
    "UAP-Outdoor+": {"latest": "4.3.28", "eol": True},
    "UAP-v2":       {"latest": "6.6.77", "eol": True},

    # ── Switches ──────────────────────────────────────────────────
    "USW-Flex":         {"latest": "6.6.77", "eol": False},
    "USW-Flex-Mini":    {"latest": "2.8.4",  "eol": False},
    "USW-Lite-8-PoE":   {"latest": "6.6.77", "eol": False},
    "USW-Lite-16-PoE":  {"latest": "6.6.77", "eol": False},
    "USW-24":           {"latest": "6.6.77", "eol": False},
    "USW-24-PoE":       {"latest": "6.6.77", "eol": False},
    "USW-48":           {"latest": "6.6.77", "eol": False},
    "USW-48-PoE":       {"latest": "6.6.77", "eol": False},
    "USW-Pro-24":       {"latest": "6.6.77", "eol": False},
    "USW-Pro-24-PoE":   {"latest": "6.6.77", "eol": False},
    "USW-Pro-48":       {"latest": "6.6.77", "eol": False},
    "USW-Pro-48-PoE":   {"latest": "6.6.77", "eol": False},
    "USW-Enterprise-8-PoE":  {"latest": "6.6.77", "eol": False},
    "USW-Enterprise-24-PoE": {"latest": "6.6.77", "eol": False},
    "USW-Enterprise-48-PoE": {"latest": "6.6.77", "eol": False},
    "USW-Pro-Max-24-PoE":    {"latest": "6.6.77", "eol": False},
    "USW-Pro-Max-48-PoE":    {"latest": "6.6.77", "eol": False},
    # Legacy switches
    "US-8":         {"latest": "6.6.77", "eol": False},
    "US-8-60W":     {"latest": "6.6.77", "eol": False},
    "US-8-150W":    {"latest": "6.6.77", "eol": False},
    "US-16-150W":   {"latest": "6.6.77", "eol": False},
    "US-24":        {"latest": "6.6.77", "eol": False},
    "US-24-250W":   {"latest": "6.6.77", "eol": False},
    "US-48":        {"latest": "6.6.77", "eol": False},
    "US-48-500W":   {"latest": "6.6.77", "eol": False},
    "US-48-750W":   {"latest": "6.6.77", "eol": False},

    # ── Gateways ──────────────────────────────────────────────────
    "UDM":           {"latest": "4.0.21", "eol": False},
    "UDM-Pro":       {"latest": "4.0.21", "eol": False},
    "UDM-SE":        {"latest": "4.0.21", "eol": False},
    "UDM-Pro-Max":   {"latest": "4.0.21", "eol": False},
    "UDR":           {"latest": "4.0.21", "eol": False},
    "UXG-Pro":       {"latest": "4.0.21", "eol": False},
    "UXG-Max":       {"latest": "4.0.21", "eol": False},
    "UXG-Lite":      {"latest": "4.0.21", "eol": False},
    "USG":           {"latest": "4.4.57", "eol": True},
    "USG-Pro-4":     {"latest": "4.4.57", "eol": True},
    "USG-XG-8":      {"latest": "4.4.57", "eol": True},
}

# Aliases: common board names that map to the canonical name above
MODEL_ALIASES: dict[str, str] = {
    "BZ.qca956x": "UAP-AC-Pro",
    "BZ.ar7240":  "UAP",
    "BZ.ipq8074": "U6-Pro",
    "BZ.mt7621":  "UAP-FlexHD",
    "BZ.ipq5018": "U6-Lite",
    "BZ.ipq6018": "U6-LR",
    "U6Pro":      "U6-Pro",
    "U6Lite":     "U6-Lite",
    "U6LR":       "U6-LR",
    "U7Pro":      "U7-Pro",
    "UAPG2":      "UAP-v2",
    "UP1":        "U6-Mesh",
    "UP6":        "U6-Enterprise",
    "U2S48":      "USW-Pro-48",
    "U2S24":      "USW-Pro-24",
    "UDM-Pro":    "UDM-Pro",
    "UDMPRO":     "UDM-Pro",
    "UDMSE":      "UDM-SE",
}


def normalize_model(raw_model: str) -> str:
    """Try to normalize a raw model/board string to a canonical name."""
    if not raw_model:
        return ""
    raw = raw_model.strip()
    # Direct match
    if raw in FIRMWARE_DB:
        return raw
    # Alias match
    if raw in MODEL_ALIASES:
        return MODEL_ALIASES[raw]
    # Prefix match (e.g., "UAP-AC-Pro-Gen2" → "UAP-AC-Pro")
    for canonical in FIRMWARE_DB:
        if raw.startswith(canonical):
            return canonical
    # Firmware string prefix (e.g., "BZ.qca956x.v6.2.91...")
    if "." in raw:
        prefix = raw.split(".")[0] + "." + raw.split(".")[1] if len(raw.split(".")) > 1 else ""
        if prefix in MODEL_ALIASES:
            return MODEL_ALIASES[prefix]
    return raw


def check_firmware(model: str, current_firmware: str) -> dict:
    """Check if firmware is up to date.

    Returns:
        {
            "model": normalized model name,
            "current": current firmware version,
            "latest": latest known version (or None),
            "up_to_date": True/False/None,
            "eol": True/False,
            "severity": "ok" / "warning" / "critical" / "unknown",
        }
    """
    normalized = normalize_model(model)
    result: dict = {
        "model": normalized or model,
        "current": current_firmware,
        "latest": None,
        "up_to_date": None,
        "eol": False,
        "severity": "unknown",
    }

    db_entry = FIRMWARE_DB.get(normalized)
    if not db_entry:
        return result

    result["latest"] = db_entry["latest"]
    result["eol"] = db_entry.get("eol", False)

    if result["eol"]:
        result["severity"] = "critical"
        result["up_to_date"] = False
        return result

    # Extract version numbers for comparison
    cur_ver = _extract_version(current_firmware)
    lat_ver = _extract_version(db_entry["latest"])

    if not cur_ver or not lat_ver:
        result["severity"] = "unknown"
        return result

    if cur_ver >= lat_ver:
        result["up_to_date"] = True
        result["severity"] = "ok"
    else:
        result["up_to_date"] = False
        # Check how far behind
        if cur_ver[0] < lat_ver[0]:  # Major version behind
            result["severity"] = "critical"
        else:
            result["severity"] = "warning"

    return result


def _extract_version(fw_string: str) -> tuple | None:
    """Extract numeric version tuple from firmware string.

    Handles formats like:
        "6.6.77"
        "BZ.qca956x.v6.2.91.13247.220325.0116"
        "v4.4.57"
    """
    import re
    if not fw_string:
        return None
    # Try to find version-like pattern
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", fw_string)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None
