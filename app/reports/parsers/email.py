"""Parsers for Exchange Online and the mail domains' DNS records."""

from __future__ import annotations

from app.reports.parsers.common import (
    _count_data_lines,
    _policy_names,
    _record_count,
    _sidecar,
)


def _parse_spf_dmarc(text: str) -> list[dict]:
    domains = []
    current: dict = {}
    prev_key = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Domain :"):
            if current:
                domains.append(current)
            current = {"domain": stripped.split(":", 1)[1].strip()}
            prev_key = ""
        elif stripped.startswith("SPF") and ":" in stripped and current:
            current["spf"] = stripped.split(":", 1)[1].strip()
            prev_key = "spf"
        elif stripped.startswith("DMARC") and ":" in stripped and current:
            current["dmarc"] = stripped.split(":", 1)[1].strip()
            prev_key = "dmarc"
        elif prev_key == "spf" and stripped.startswith("v=spf1") and current:
            current["spf_record"] = stripped
            prev_key = ""
        elif (
            prev_key == "dmarc"
            and (stripped.startswith("v=DMARC1") or stripped == "(none)")
            and current
        ):
            current["dmarc_record"] = stripped if stripped != "(none)" else ""
            prev_key = ""
        elif stripped.startswith("DKIM") and ":" in stripped and current:
            val = stripped.split(":", 1)[1].strip()
            low = stripped.lower()
            if "sel1" in low or "(m365)" in low or "dkim1" not in current:
                current["dkim1"] = val
            elif "sel2" in low or "dkim2" not in current:
                current["dkim2"] = val
            if "found" in low:
                current["dkim_found"] = val
            prev_key = ""
        elif stripped.startswith("MTA-STS") and current:
            current["mta_sts"] = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
            prev_key = ""
        else:
            prev_key = ""
    if current:
        domains.append(current)
    return domains


# Domains to exclude from SPF/DMARC compliance checks — these are either
# Microsoft infrastructure domains or third-party service domains where
# the customer has no control over DNS records.
_IGNORED_DOMAIN_SUFFIXES = (
    ".onmicrosoft.com",
    ".mail.onmicrosoft.com",
    ".sharepoint.com",
    # Anti-spam / anti-phishing gateway domains (no customer DNS control)
    ".inkyphishfence.com",
    ".mimecast.com",
    ".pphosted.com",  # Proofpoint
    ".barracudanetworks.com",
)


def _is_audit_relevant_domain(domain: str) -> bool:
    """Return True if a domain should be included in SPF/DMARC compliance checks."""
    d = domain.lower()
    return not any(d.endswith(suffix) for suffix in _IGNORED_DOMAIN_SUFFIXES)


def _mailbox_counts(file_contents: dict[str, str]) -> dict[str, int]:
    """Total, user and shared mailboxes: the count file's sidecar, or its text."""
    data = _sidecar(file_contents, "20_exchange_mailboxes_count.txt")
    if data is not None:
        return {
            key: data[key]
            for key in ("total", "user", "shared")
            if isinstance(data.get(key), int) and not isinstance(data.get(key), bool)
        }
    counts: dict[str, int] = {}
    # Mailbox counts — flexible key matching (same pattern as Intune parser)
    count_text = file_contents.get("20_exchange_mailboxes_count.txt", "")
    for line in count_text.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower().replace("-", "").replace(" ", "")
        try:
            v = int(val.strip())
        except ValueError:
            continue
        if "total" in key:
            counts["total"] = v
        elif key in ("user", "usermailbox", "usermailboxes"):
            counts["user"] = v
        elif key in ("shared", "sharedmailbox", "sharedmailboxes"):
            counts["shared"] = v
    return counts


def _parse_exchange_overview(file_contents: dict[str, str]) -> dict:
    """Parse Exchange data files into a structured overview."""
    result = {
        "mailbox_total": 0,
        "mailbox_user": 0,
        "mailbox_shared": 0,
        "transport_rules": 0,
        "connectors": 0,
        "antiphish_policies": [],
        "antispam_policies": [],
        "forwarding_count": 0,
        "external_forwarding": False,
        "inbox_rules_external": 0,
        "has_data": False,
    }

    counts = _mailbox_counts(file_contents)
    result["mailbox_total"] = counts.get("total", 0)
    result["mailbox_user"] = counts.get("user", 0)
    result["mailbox_shared"] = counts.get("shared", 0)

    # Transport rules and connectors: the sidecar's count, or the text's records
    result["transport_rules"] = _record_count(file_contents, "21_exchange_transport_rules.txt")
    result["connectors"] = _record_count(file_contents, "22_exchange_connectors.txt")

    # Anti-phish and anti-spam policies — one name per policy
    result["antiphish_policies"] = _policy_names(file_contents, "23_exchange_antiphish.txt")
    result["antispam_policies"] = _policy_names(file_contents, "24_exchange_antispam.txt")

    # Mailbox forwarding count
    fwd_text = file_contents.get("28_exchange_mailbox_forwarding.txt", "")
    result["forwarding_count"] = _count_data_lines(fwd_text)

    # External forwarding warning flag
    ext_fwd_text = file_contents.get("28b_exchange_external_forwarding_WARN.txt", "")
    result["external_forwarding"] = bool(ext_fwd_text and ext_fwd_text.strip())

    # Inbox rules with external forwarding.
    #
    # The collector signals the finding by renaming the file, not by writing
    # anything inside it: rules found go to 29_..._WARN.txt, and the plain name
    # is the all-clear. Reading only the plain name meant this count was zero
    # precisely when it should not have been, and that number is printed on the
    # customer-facing report — while CIS 4.4 on the same report flagged the
    # forwarding correctly, because it reads the WARN file. The report
    # contradicted itself, and the reassuring half was the wrong half.
    #
    # Same trap 4.4 itself fell into once; see the note on that check.
    inbox_rules_text = file_contents.get(
        "29_exchange_inbox_rules_external_fwd_WARN.txt", ""
    ) or file_contents.get("29_exchange_inbox_rules_external_fwd.txt", "")
    result["inbox_rules_external"] = _count_data_lines(inbox_rules_text)

    result["has_data"] = (
        result["mailbox_total"] > 0
        or result["transport_rules"] > 0
        or len(result["antiphish_policies"]) > 0
        or result["forwarding_count"] > 0
    )
    return result


def _count_defender_policy_state(text: str) -> tuple[int, int]:
    """Walk the 27_exchange_defender_policies.txt file and return
    (safe_links_enabled, safe_attachments_enabled) counts.

    The Exchange collector writes each policy as a small block of
    `Key: Value` lines separated by blank lines. A previous version of
    the compliance check just matched the substring "safe links" /
    "safe attach" anywhere in the file, which counted a disabled policy
    as enabled. This helper parses the blocks and only counts entries
    whose PolicyType is SafeLinks* / SafeAttachments* AND Enabled is True.
    """
    safe_links = safe_attach = 0
    block: dict[str, str] = {}

    def _flush() -> None:
        nonlocal safe_links, safe_attach
        if not block:
            return
        ptype = block.get("policytype", "").lower()
        enabled = block.get("enabled", "").strip().lower() in ("true", "yes", "1")
        if not enabled:
            block.clear()
            return
        if "safelinks" in ptype.replace(" ", "") or "safe link" in ptype:
            safe_links += 1
        if "safeattach" in ptype.replace(" ", "") or "safe attach" in ptype:
            safe_attach += 1
        block.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("-"):
            _flush()
            continue
        if ":" in stripped:
            key, val = stripped.split(":", 1)
            block[key.strip().lower()] = val.strip()
    _flush()
    return safe_links, safe_attach


# (sidecar key, the two spellings the text reader looks for)
_DEFENDER_KINDS = {
    "safe_links": ("safelinks", "safe links"),
    "safe_attachments": ("safeattach", "safe attach"),
}


def _defender_policies(file_contents: dict[str, str]) -> dict[str, dict]:
    """Safe Links and Safe Attachments: how many policies are enabled, and whether any exist.

    {"safe_links": {"enabled": n, "present": bool}, "safe_attachments": {...}},
    from 27_exchange_defender_policies.json, or from the text: the enabled
    count from its policy blocks, and "present" when the policy type is named
    anywhere in it. That last test also matched a policy of the other type
    whose name said "Safe Links".
    """
    data = _sidecar(file_contents, "27_exchange_defender_policies.txt")
    if data is not None:
        state = {}
        for kind in _DEFENDER_KINDS:
            counts = data.get(kind) if isinstance(data.get(kind), dict) else {}
            enabled, total = counts.get("enabled"), counts.get("total")
            state[kind] = {
                "enabled": enabled if isinstance(enabled, int) else 0,
                "present": isinstance(total, int) and total > 0,
            }
        return state
    text = file_contents.get("27_exchange_defender_policies.txt", "")
    links, attachments = _count_defender_policy_state(text)
    low = text.lower()
    return {
        kind: {"enabled": enabled, "present": any(name in low for name in names)}
        for (kind, names), enabled in zip(
            _DEFENDER_KINDS.items(), (links, attachments), strict=True
        )
    }


def _severity(status: str) -> str:
    s = status.upper()
    if s.startswith("ERROR") or "QUERY FAILED" in s:
        return "warning"  # transport error — an unanswered lookup is not a clean pass
    if "MISSING" in s or "CRITICAL" in s:
        return "critical"
    if "WEAK" in s or "WARN" in s or "QUARANTINE" in s or "NONE" in s:
        return "warning"
    return "ok"
