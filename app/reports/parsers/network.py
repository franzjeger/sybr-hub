"""Parser for the saved FortiGate and UniFi quick-audit results."""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# What quick_audit_fortigate notes about a firewall policy (its "kind").
FORTIGATE_POLICY_FINDINGS = ("allow_all", "no_logging")

# A run from before the quick audit stored kinds holds its English sentences
# in "policy_warnings": "Policy 12: allow-all (src=all, dst=all, svc=ALL)",
# "Policy 19: logging disabled". The kind is read the way the report always
# counted them, by "allow-all" and "logging"; the policy by the leading
# "Policy <id>", with a quoted name if one follows.
_LEGACY_KIND_WORDS = (("allow_all", "allow-all"), ("no_logging", "logging"))
_LEGACY_POLICY = re.compile(r'Policy (?P<id>[^\s:"]+)(?: "(?P<name>[^"]*)")?(?=[:\s]|$)')

# FortiOS's HA modes, and the report's word for each.
_HA_MODE_WORDS = {
    "standalone": "net_ha_standalone",
    "a-p": "net_ha_active_passive",
    "a-a": "net_ha_active_active",
}


def _legacy_policy_findings(warnings: list) -> list[dict]:
    """The findings an old run's English warnings name, each keeping its text.

    A warning that names both kinds is both, as the report counted it. One
    that names neither has no kind and is shown as it was stored.
    """
    findings = []
    for warning in warnings:
        text = str(warning)
        kinds = [kind for kind, word in _LEGACY_KIND_WORDS if word in text.lower()]
        m = _LEGACY_POLICY.match(text)
        for kind in kinds or [None]:
            findings.append(
                {
                    "kind": kind,
                    "policy_id": m["id"] if m and kind else None,
                    "name": (m["name"] or "") if m else "",
                    "text": text,
                }
            )
    return findings


def policy_finding_text(finding: dict, t) -> str:
    """A FortiGate policy finding in the report's language, or as stored."""
    kind, policy = finding.get("kind"), finding.get("policy_id")
    if kind in FORTIGATE_POLICY_FINDINGS and policy:
        name = finding.get("name")
        return str(t(f"fg_finding_{kind}", policy=f"{policy} ({name})" if name else policy))
    return str(finding.get("text") or "")


def ha_mode_text(mode, t) -> str:
    """FortiOS's HA mode in the report's language; one it does not name, as stored."""
    if not mode:
        return ""
    key = _HA_MODE_WORDS.get(str(mode).lower())
    return str(t(key)) if key else str(mode)


def policy_findings(fortigate: dict) -> list[dict]:
    """A saved FortiGate audit's policy findings, whatever its age.

    Each is {"kind", "policy_id", "name"}, and "text" for one read from an old
    run's "policy_warnings". Every reader takes them from here, so a run from
    before the codes is counted and shown the same way as a new one.
    """
    if "policy_findings" in fortigate:
        return [f for f in fortigate.get("policy_findings") or [] if isinstance(f, dict)]
    return _legacy_policy_findings(fortigate.get("policy_warnings") or [])


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
