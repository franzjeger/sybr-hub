"""Parsers for Exchange Online and the mail domains' DNS records."""

from __future__ import annotations

import re

from app.reports.parsers.common import _policy_names, _record_count, _sidecar


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


def _spf_dmarc_records(file_contents: dict[str, str]) -> list[dict]:
    """Per mail domain, its SPF, DMARC, DKIM and MTA-STS findings.

    From 26_email_dns_spf_dmarc.json, in the shape _parse_spf_dmarc reads the
    text into, so every consumer of the list reads either the same way: the
    statuses as the collector wrote them, a record only where one was looked
    up ("" for DMARC when none is published), and the two DKIM summaries in
    the text's "selector: status | ..." form. A run without the sidecar is
    read from the text. A status is a code in a new run and an English phrase
    in an old one; every reader takes it through the *_status functions
    below, which read either.
    """
    data = _sidecar(file_contents, "26_email_dns_spf_dmarc.txt")
    if data is None:
        return _parse_spf_dmarc(file_contents.get("26_email_dns_spf_dmarc.txt", ""))
    records = []
    for d in data.get("domains") or []:
        if not isinstance(d, dict):
            continue
        record = {"domain": str(d.get("domain") or "").strip()}
        record["spf"] = str(d.get("spf_status") or "").strip()
        if isinstance(d.get("spf_record"), str) and d["spf_record"]:
            record["spf_record"] = d["spf_record"].strip()
        record["dmarc"] = str(d.get("dmarc_status") or "").strip()
        if isinstance(d.get("dmarc_record"), str):
            record["dmarc_record"] = d["dmarc_record"].strip()
        dkim = d.get("dkim") if isinstance(d.get("dkim"), dict) else {}
        m365 = ("selector1", "selector2")
        record["dkim1"] = " | ".join(f"{s}: {dkim.get(s, 'missing')}" for s in m365)
        record["dkim2"] = " | ".join(f"{s}: {v}" for s, v in dkim.items() if s not in m365)
        found = d.get("dkim_found") if isinstance(d.get("dkim_found"), list) else []
        record["dkim_found"] = ", ".join(str(s) for s in found) or "(none)"
        record["mta_sts"] = str(d.get("mta_sts") or "").strip()
        records.append(record)
    return records


# ── The DNS collector's statuses ──────────────────────────────────────────────
#
# dns.py writes each status as a code (dns.SPF_STATUSES, dns.DMARC_STATUSES;
# a DKIM selector "cname -> <target>", "txt" or "missing"; MTA-STS the record
# or "missing"), or "error (<what failed>)" for a lookup that went unanswered.
# It wrote English phrases before ("WEAK (~all softfail)", "TXT present",
# "ERROR (...)"), which an old run still holds; those are read to the same
# codes. Each reader gets (code, detail): the detail is an error's message,
# a CNAME's target or MTA-STS's record. A value neither form names comes back
# as ("", value), for the report to show as it was stored.

SPF_STATUSES = ("hardfail", "softfail", "neutral", "pass_all", "no_all", "missing", "error")
DMARC_STATUSES = ("reject", "quarantine", "none", "unknown_policy", "missing", "error")

_LEGACY_SPF = {
    "OK (-all hardfail)": "hardfail",
    "WEAK (~all softfail)": "softfail",
    "WEAK (?all neutral)": "neutral",
    "CRITICAL (+all — allows anyone)": "pass_all",
    "PRESENT (no 'all' mechanism)": "no_all",
    "MISSING": "missing",
}
_LEGACY_DMARC = {
    "OK (p=reject)": "reject",
    "WARN (p=quarantine)": "quarantine",
    "WEAK (p=none)": "none",
    "PRESENT (unknown policy)": "unknown_policy",
    "MISSING": "missing",
}
_ERROR_STATUS = re.compile(r"error \((.*)\)", re.IGNORECASE | re.DOTALL)


def _status(value, codes: tuple[str, ...], legacy: dict[str, str]) -> tuple[str, str]:
    text = str(value or "").strip()
    if text in codes:
        return text, ""
    if text in legacy:
        return legacy[text], ""
    m = _ERROR_STATUS.fullmatch(text)
    if m:
        return "error", m.group(1)
    return "", text


def spf_status(record: dict) -> tuple[str, str]:
    """The domain's SPF status: (one of SPF_STATUSES, an error's message)."""
    return _status(record.get("spf"), SPF_STATUSES, _LEGACY_SPF)


def dmarc_status(record: dict) -> tuple[str, str]:
    """The domain's DMARC status: (one of DMARC_STATUSES, an error's message)."""
    return _status(record.get("dmarc"), DMARC_STATUSES, _LEGACY_DMARC)


def mta_sts_status(record: dict) -> tuple[str, str]:
    """("present", the record), ("missing", ""), or ("error", its message)."""
    text = str(record.get("mta_sts") or "").strip()
    if text.lower().startswith("v=stsv1"):
        return "present", text
    return _status(text, ("missing",), {"MISSING": "missing"})


def dkim_status(value: str) -> tuple[str, str]:
    """A DKIM selector's status: "cname" (with its target), "txt", "missing" or "error"."""
    text = str(value or "").strip()
    head, sep, target = text.partition("->")
    if sep and head.strip().lower() == "cname":
        return "cname", target.strip()
    if text.lower() in ("txt", "txt present"):
        return "txt", ""
    return _status(text, ("missing",), {"MISSING": "missing"})


# The report's word for each status: the tag in the technical report's email
# table, and the sentence CIS 5.2.1 and 5.2.2 give as their detail. The tag's
# colour is the class _severity used to read off the English.
_SPF_TAGS = {
    "hardfail": ("ok", "ok"),
    "softfail": ("weak_label", "warning"),
    "neutral": ("weak_label", "warning"),
    "pass_all": ("critical", "critical"),
    "no_all": ("dns_present", "ok"),
    "missing": ("missing_label", "critical"),
    "error": ("error_status", "warning"),
}
_DMARC_TAGS = {
    "reject": ("ok", "ok"),
    "quarantine": ("warning", "warning"),
    "none": ("weak_label", "warning"),
    "unknown_policy": ("dns_present", "ok"),
    "missing": ("missing_label", "critical"),
    "error": ("error_status", "warning"),
}
_MTA_STS_TAGS = {
    "present": ("dns_present", "ok"),
    "missing": ("missing_label", "critical"),
    "error": ("error_status", "warning"),
}


def dns_tag(record: dict, field: str, t) -> dict:
    """{"word", "severity"} for a record's "spf", "dmarc" or "mta_sts" cell.

    A status the report cannot name is shown as stored, coloured as _severity
    reads its words.
    """
    reader, tags = {
        "spf": (spf_status, _SPF_TAGS),
        "dmarc": (dmarc_status, _DMARC_TAGS),
        "mta_sts": (mta_sts_status, _MTA_STS_TAGS),
    }[field]
    code, _ = reader(record)
    if code in tags:
        key, severity = tags[code]
        return {"word": str(getattr(t, key)), "severity": severity}
    raw = str(record.get(field) or "")
    word = raw.split("(")[0].strip() if "(" in raw else raw[:20]
    return {"word": word, "severity": _severity(raw)}


# The customer report's pill for each status: (class, word).
_SPF_PILLS = {
    "hardfail": ("ok", "ok"),
    "no_all": ("ok", "ok"),
    "softfail": ("warning", "weak_label"),
    "neutral": ("warning", "weak_label"),
    "pass_all": ("critical", "critical"),
    "missing": ("critical", "missing_label"),
    "error": ("unknown", "data_unavailable"),
}
_DMARC_PILLS = {
    "reject": ("ok", "ok"),
    "quarantine": ("ok", "ok"),
    "unknown_policy": ("ok", "ok"),
    "none": ("warning", "weak_label"),
    "missing": ("critical", "missing_label"),
    "error": ("unknown", "data_unavailable"),
}
_MTA_STS_PILLS = {
    "present": ("ok", "ok"),
    "missing": ("warning", "missing_label"),
    "error": ("unknown", "data_unavailable"),
}


def dns_pill(record: dict, field: str, t) -> dict:
    """{"pill", "word"} for the customer report's "spf", "dmarc" or "mta_sts" cell.

    A lookup that failed is unknown: it showed as a green OK. A status no
    collector wrote is read by its words, as before.
    """
    reader, pills = {
        "spf": (spf_status, _SPF_PILLS),
        "dmarc": (dmarc_status, _DMARC_PILLS),
        "mta_sts": (mta_sts_status, _MTA_STS_PILLS),
    }[field]
    code, _ = reader(record)
    if code in pills:
        pill, key = pills[code]
    else:
        raw = str(record.get(field) or "")
        missing = "MISSING" in raw or (field == "spf" and "CRITICAL" in raw)
        weak = "WEAK" in raw or (field == "dmarc" and "none" in raw)
        if missing:
            pill, key = ("warning" if field == "mta_sts" else "critical"), "missing_label"
        elif weak and field != "mta_sts":
            pill, key = "warning", "weak_label"
        else:
            pill, key = "ok", "ok"
    return {"pill": pill, "word": str(getattr(t, key))}


# What a status says, for CIS 5.2.1 and 5.2.2 to give as their detail.
_SPF_WORDS = {
    "hardfail": "dns_spf_hardfail",
    "softfail": "dns_spf_softfail",
    "neutral": "dns_spf_neutral",
    "pass_all": "dns_spf_pass_all",
    "no_all": "dns_spf_no_all",
    "missing": "missing_label",
}
_DMARC_WORDS = {
    "reject": "dns_dmarc_reject",
    "quarantine": "dns_dmarc_quarantine",
    "none": "dns_dmarc_none",
    "unknown_policy": "dns_dmarc_unknown_policy",
    "missing": "missing_label",
}


def spf_words(record: dict, t) -> str:
    """What the domain's SPF status says, worded; one the report cannot name, as stored."""
    code, _ = spf_status(record)
    key = _SPF_WORDS.get(code)
    return str(getattr(t, key)) if key else str(record.get("spf") or "")


def dmarc_words(record: dict, t) -> str:
    """What the domain's DMARC status says, worded; one the report cannot name, as stored."""
    code, _ = dmarc_status(record)
    key = _DMARC_WORDS.get(code)
    return str(getattr(t, key)) if key else str(record.get("dmarc") or "")


def dkim_summary(record: dict, field: str, t) -> str:
    """The technical report's DKIM cell: "dkim1" (Exchange's two selectors) or
    "dkim2" (the others, only those with a key or an error), worded."""
    words = []
    for part in str(record.get(field) or "").split("|"):
        name, sep, value = part.partition(":")
        if not sep or not name.strip():
            continue
        code, _ = dkim_status(value)
        if field == "dkim2" and code == "missing":
            continue
        word = {
            "cname": "CNAME",
            "txt": "TXT",
            "missing": str(t.missing_label).lower(),
            "error": str(t.dns_lookup_failed).lower(),
        }.get(code, value.strip())
        words.append(f"{name.strip()}: {word}")
    return " | ".join(words)


# ── DKIM: who signs a domain's mail ───────────────────────────────────────────

_EXCHANGE_DKIM = "25_exchange_dkim.txt"
# The table's domain column, cut to this width.
_DKIM_DOMAIN_WIDTH = 45


def _exchange_dkim_configs(file_contents: dict[str, str]) -> list[dict] | None:
    """Exchange Online's DKIM signing configs: {"domain", "enabled", "cut"} each.

    From 25_exchange_dkim.json, or the text's table read by column. "cut" says
    the domain is the table's 45-character cut of a longer one. None when the
    run did not collect the configs (the helper failed, or the file is an
    error stub, which the report blanks): unknown, not "signing nowhere".
    """
    data = _sidecar(file_contents, _EXCHANGE_DKIM)
    if data is not None:
        return [
            {
                "domain": str(c.get("domain") or "").strip().lower(),
                "enabled": c.get("enabled") is True,
                "cut": False,
            }
            for c in data.get("configs") or []
            if isinstance(c, dict)
        ]
    text = file_contents.get(_EXCHANGE_DKIM, "")
    if not text.strip() or "DKIM SIGNING CONFIGS" not in text:
        return None
    configs: list[dict] = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Domain") and "Enabled" in stripped:
            in_table = True
            continue
        if not in_table or not stripped or stripped.startswith(("-", "=")):
            continue
        # "  {domain:<45} {enabled:>8} {status:<20} {selector}"
        domain = line[2 : 2 + _DKIM_DOMAIN_WIDTH].strip().lower()
        enabled = line[2 + _DKIM_DOMAIN_WIDTH : 2 + _DKIM_DOMAIN_WIDTH + 9].strip()
        if domain:
            configs.append(
                {
                    "domain": domain,
                    "enabled": enabled == "Yes",
                    "cut": len(domain) == _DKIM_DOMAIN_WIDTH,
                }
            )
    return configs


def _exchange_signs(configs: list[dict] | None, domain: str) -> bool | None:
    """Whether Exchange Online signs the domain's mail with DKIM; None when unknown.

    A domain without a config of its own is not signed with its own name:
    Exchange then signs with the onmicrosoft.com domain, which does not align
    with the sender for DMARC.
    """
    if configs is None:
        return None
    name = domain.strip().lower()
    return any(
        c["enabled"] and (c["domain"] == name or (c["cut"] and name.startswith(c["domain"])))
        for c in configs
    )


def _dkim_selectors(record: dict) -> dict[str, str]:
    """{selector: status} from a mail-domain record's two DKIM summaries."""
    selectors: dict[str, str] = {}
    for summary in (record.get("dkim1"), record.get("dkim2")):
        for part in str(summary or "").split("|"):
            name, sep, status = part.partition(":")
            if sep and name.strip():
                selectors[name.strip().lower()] = status.strip()
    return selectors


def _key_published(status: str) -> bool:
    """A selector the DNS lookup found a key (or a CNAME to one) at."""
    code, _ = dkim_status(status)
    if code:
        return code in ("cname", "txt")
    return str(status).upper().startswith(("CNAME", "TXT"))


_EXCHANGE_SPF = "spf.protection.outlook.com"
# Senders the data can name: the SPF include that says one sends a domain's
# mail, and the DKIM selectors it signs with, among those the DNS collector
# looks up. "default" and "dkim" are anybody's, so a key there names no sender.
_THIRD_PARTY_SENDERS = (
    ("Google Workspace", ("_spf.google.com",), ("google",)),
    ("Mailchimp", ("servers.mcsv.net", "spf.mandrillapp.com"), ("k1", "k2")),
)


def _spf_senders(record: dict) -> set[str] | None:
    """Who the domain's SPF record lets send its mail, as far as the data can name them.

    "exchange", a third-party sender's name, and "none" for a record that
    lets nobody send (v=spf1 -all). None without a published SPF record.
    """
    spf = record.get("spf_record")
    if not isinstance(spf, str) or not spf.lower().startswith("v=spf1"):
        return None
    mechanisms = spf.lower().split()[1:]
    if mechanisms == ["-all"]:
        return {"none"}
    targets: set[str] = set()
    for term in mechanisms:
        term = term.lstrip("+-~?")
        for prefix in ("include:", "redirect="):
            if term.startswith(prefix):
                targets.add(term[len(prefix) :])
    senders = {"exchange"} if _EXCHANGE_SPF in targets else set()
    for name, includes, _selectors in _THIRD_PARTY_SENDERS:
        if targets & set(includes):
            senders.add(name)
    return senders


def _third_party_dkim(record: dict) -> list[tuple[str, str]]:
    """(sender, selector) for each nameable sender whose DKIM key is published."""
    selectors = _dkim_selectors(record)
    return [
        (name, selector)
        for name, _includes, keys in _THIRD_PARTY_SENDERS
        for selector in keys
        if _key_published(selectors.get(selector, ""))
    ]


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


def _external_forwarding_items(file_contents: dict[str, str]) -> list[str] | None:
    """ "mailbox → target" for each mailbox forwarding outside the tenant.

    From 28b_exchange_external_forwarding_WARN.json, in the form the text's
    "  mailbox  →  smtp:target" lines are read into: the target without its
    smtp: prefix. None for a run without the sidecar, whose text the caller
    reads as it did before.
    """
    data = _sidecar(file_contents, "28b_exchange_external_forwarding_WARN.txt")
    if data is None:
        return None
    items = []
    for row in data.get("forwarding") or []:
        if not isinstance(row, dict):
            continue
        mailbox = str(row.get("mailbox") or "?").strip()
        target = str(row.get("forward_to") or "?").strip()
        items.append(f"{mailbox} → {target.replace('smtp:', '').replace('SMTP:', '')}")
    return items


_FORWARDING = "28_exchange_mailbox_forwarding.txt"


def _unverified_forwarding_count(file_contents: dict[str, str]) -> int:
    """Mailboxes forwarding to a recipient the run could not place inside or outside.

    From 28_exchange_mailbox_forwarding.json, or the text's External column,
    which reads "Unverified" for them. Runs from before called every one of
    them external, so they have none.
    """
    data = _sidecar(file_contents, _FORWARDING)
    if data is not None:
        return int(data.get("unverified_count") or 0)
    return sum(
        1
        for line in file_contents.get(_FORWARDING, "").splitlines()
        if line.rstrip().endswith(" Unverified")
    )


_INBOX_RULES = "29_exchange_inbox_rules_external_fwd.txt"
_INBOX_RULES_WARN = "29_exchange_inbox_rules_external_fwd_WARN.txt"
_UNVERIFIED_RULE = re.compile(r"^\s*Scope:\s*Unverified\s*$", re.MULTILINE | re.IGNORECASE)


def _inbox_rule_counts(file_contents: dict[str, str]) -> dict[str, int]:
    """Forwarding inbox rules that leave the tenant, and those the run could not place.

    {"external": n, "unverified": m}. The collector writes every forwarding
    rule to the plain 29 file with where it goes, and only the external ones to
    the WARN file, so the external count is the WARN file's. Runs from before
    that wrote every forwarding rule to the WARN file, internal ones included;
    their count is read as it was written, and they have no unverified rules.
    """
    plain = _sidecar(file_contents, _INBOX_RULES)
    if plain is not None and "external_count" in plain:
        return {
            "external": int(plain.get("external_count") or 0),
            "unverified": int(plain.get("unverified_count") or 0),
        }
    has_warn = bool(file_contents.get(_INBOX_RULES_WARN)) or (
        _sidecar(file_contents, _INBOX_RULES_WARN) is not None
    )
    return {
        "external": _record_count(file_contents, _INBOX_RULES_WARN) if has_warn else 0,
        "unverified": len(_UNVERIFIED_RULE.findall(file_contents.get(_INBOX_RULES, ""))),
    }


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
        "forwarding_unverified": 0,
        "external_forwarding": False,
        "inbox_rules_external": 0,
        "inbox_rules_unverified": 0,
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
    result["forwarding_count"] = _record_count(file_contents, _FORWARDING)
    result["forwarding_unverified"] = _unverified_forwarding_count(file_contents)

    # External forwarding warning flag
    ext_fwd_text = file_contents.get("28b_exchange_external_forwarding_WARN.txt", "")
    ext_fwd_items = _external_forwarding_items(file_contents)
    if ext_fwd_items is not None:
        result["external_forwarding"] = bool(ext_fwd_items)
    else:
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
    # Same trap 4.4 itself fell into once; see the note on that check. The
    # plain file now lists every forwarding rule, internal ones too, so it is
    # never the count (_inbox_rule_counts).
    rule_counts = _inbox_rule_counts(file_contents)
    result["inbox_rules_external"] = rule_counts["external"]
    result["inbox_rules_unverified"] = rule_counts["unverified"]

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
