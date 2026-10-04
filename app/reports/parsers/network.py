"""Parser for the saved FortiGate and UniFi quick-audit results."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# The saved quick-audit files, in the order they are read: an unreadable file
# is reported in this order, and recommendations.py names each by its file.
NETWORK_AUDIT_FILES = (("60_fortigate_audit.txt", "fortigate"), ("61_unifi_audit.txt", "unifi"))


def _parse_network_audit(file_contents: dict) -> dict:
    """Parse network audit data from saved quick-audit JSON files.

    A file that is present but will not parse is *not* the same as no network
    audit. Both used to produce has_data=False, and the caller reads that to
    decide whether to run _network_penalty at all — so a malformed file
    dropped the firewall findings and their risk penalty, and the customer
    scored better for it. Unreadable is now recorded and reported as itself.
    """
    import json as _json

    result: dict = {
        "fortigate": None,
        "unifi": None,
        "has_data": False,
        # Files that had content and could not be read. Empty is the good case;
        # non-empty means the report is missing findings it should have had.
        "unreadable": [],
    }
    for name, key in NETWORK_AUDIT_FILES:
        raw = file_contents.get(name, "")
        if not raw.strip():
            continue
        try:
            result[key] = _json.loads(raw)
            result["has_data"] = True
        except Exception as exc:
            result["unreadable"].append(name)
            log.warning(
                "Network audit file %s is present but could not be parsed (%s). "
                "Its findings and their risk penalty are missing from this report.",
                name,
                exc,
            )
    return result
