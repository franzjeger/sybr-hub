"""A Norwegian report reads Norwegian, outside what the tenant itself wrote.

The mirror of test_english_reports. The engine was written in Norwegian, but
English crept in where nobody looked: the tech report's cover said "M365 +
Azure Full Security Audit", a WLAN whose encryption the controller did not
report read "Unknown", the priority of a licence suggestion printed as HIGH
or MEDIUM, every CIS control was titled in English, and a template asked for
two keys that did not exist and printed their names.

Same method: both templates are rendered in Norwegian from the audit
fixtures and every text node is scanned for English words. What the tenant
said in the run's files is data and stays as written: a node that is a piece
of a file is left out, and so is a value the report took from a file and set
into a sentence of its own (a line or a cell of a collector's table, the
value after a "Key : " label, a JSON string). What the collector wrote there
in its own words is not data (tests/collector_words.py reads those words out
of the collectors' source, and lists what they wrote before they stored
codes): "Admins and Guest Inviters" and "Policy 12: allow-all" passed as the
tenant's words until the collectors stored codes and the report worded them
(TODO C15). A whole file shown as itself, the raw-data appendix's, stays data.
"""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path

import pytest

from app.reports.compliance import _ISO_NAMES, _NIST_NAMES
from app.reports.generator import _jinja_env, build_report_context
from app.reports.i18n import _SECTION_NAMES, TRANSLATIONS, T
from tests.collector_words import written_by_a_collector
from tests.test_english_reports import FIXTURES, TEMPLATES, _is_data, _text_nodes

_TEMPLATE_DIR = Path("app/reports/templates")

# Words that are English and not Norwegian. Norwegian IT language borrows a
# lot ("policy", "tenant", "admin", "status", "audit", "score", "full"), so a
# borrowed word is not here: only words a Norwegian sentence would not use.
_ENGLISH = re.compile(
    r"\b(?:the|and|of|with|without|from|this|that|these|is|are|was|were|has|have|not|"
    r"none|yes|unknown|enabled|disabled|missing|found|users?|devices?|settings|policies|"
    r"high|medium|low|critical|warnings?|errors?|failed|passed|partial|recommended|"
    r"recommendations?|actions?|summary|report|overview|security|compliance|compliant|"
    r"guests?|licen[cs]es?|mailbox(?:es)?|forwarding|available|unavailable|could|cannot|"
    r"should|must|will|which|when|only|days|total|active|inactive|never|expired|expires|"
    r"sign-ins?|risky|alerts?|rules?|groups?|members?|owners?|sharing|external|internal|"
    r"configured|assigned|unassigned|eligible|assignments?|registrations?|subscriptions?|"
    r"online|offline|open|insecure|priority|effort|details|roles?|access|ensure|"
    r"measured|points|credentials|enrolled|"
    # Words the collectors used in their own phrases (tests/collector_words.py),
    # so one of those printed as it stood is seen.
    r"restrictive|potential|candidate|allows|allow(?!-all)|traffic|inbound|weak|present|"
    r"mechanism|warn|dynamic|distribution|phone|call|key|email|certificate|password|"
    r"standalone|timeout|unattached|primary|general|reports|information|network|"
    r"governance)\b",
    re.IGNORECASE,
)

# Names a Norwegian report keeps in English, as Microsoft's own Norwegian
# pages do: products and features, and the built-in role names an operator
# looks for in the admin centre. "end-of-life" is the industry's term.
_TERMS = (
    "Microsoft Secure Score",
    "Secure Score",
    "Conditional Access",
    "Security Defaults",
    "Exchange Online",
    "SharePoint Online",
    "Defender for Office 365",
    "Defender for Endpoint",
    "Safe Links",
    "Safe Attachments",
    "Global Administrator",
    "Exchange Administrator",
    "Security Administrator",
    "end-of-life",
)

# A NIST CSF 2.0 subcategory or an ISO 27001:2022 Annex A control is cited by
# its id and the framework's own published name. Neither framework has a
# Norwegian edition of those names, so a translation would be ours, not theirs.
_FRAMEWORK_CITATIONS = {
    f"{k}: {v}" for names in (_NIST_NAMES, _ISO_NAMES) for k, v in names.items()
}

# An identifier is not a word: a Graph permission (User.Read.All), a domain,
# a file name, a property and its value (AuditDisabled=False).
_IDENTIFIER = re.compile(r"\b\w+(?:[.=@]\w+)+\b")


def _english(text: str) -> bool:
    if text in _FRAMEWORK_CITATIONS:
        return False
    text = _IDENTIFIER.sub(" ", text)
    for term in _TERMS:
        text = re.sub(re.escape(term), " ", text, flags=re.IGNORECASE)
    return bool(_ENGLISH.search(text))


def _json_strings(value) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return {s for v in value.values() for s in _json_strings(v)}
    if isinstance(value, list):
        return {s for v in value for s in _json_strings(v)}
    return set()


def _data_values(files: dict[str, str]) -> set[str]:
    """What the tenant said in a file: its lines, table cells, labelled values
    and JSON strings, less what the collector wrote there itself."""
    values: set[str] = set()
    for name, text in files.items():
        # The raw-data appendix titles each file by its name.
        values.add(name.rsplit(".", 1)[0].replace("_", " ").title())
        with contextlib.suppress(ValueError):  # not every file is JSON
            values |= _json_strings(json.loads(text))
        for line in text.splitlines():
            values.add(line)
            values.update(re.split(r"\s{2,}|\t|\s*:\s+|;\s*", line))
    values = {" ".join(v.split()) for v in values}
    return {v for v in values if len(v) >= 3 and not written_by_a_collector(v)}


def _without_data(node: str, values: set[str]) -> str:
    """The node with the files' values taken out.

    A value of several words is taken out wherever it stands. A single word
    only where it stands alone between brackets, commas or colons: "high" in
    "(risikonivå: high)" is the tenant's reading, "medium" in "høy/medium
    risiko" is the report's own word that happens to be in a file too.
    """
    words = {v for v in values if v.isalpha()}
    for value in sorted(values - words, key=len, reverse=True):
        if value in node:
            node = re.sub(r"(?<!\w)" + re.escape(value) + r"(?!\w)", " ", node)
    parts = re.split(r"([(),:;])", node)
    return "".join(" " if p.strip() in words else p for p in parts)


def _is_tenant_data(node: str, files: dict[str, str]) -> bool:
    """A piece of a file that is not the collector's own words, or a whole
    file shown as itself: the evidence, as it was collected."""
    if not _is_data(node, files):
        return False
    whole = any(node == " ".join(text.split()) for text in files.values())
    return whole or not written_by_a_collector(node)


def _english_nodes(page: str, files: dict[str, str]) -> set[str]:
    values = _data_values(files)
    return {
        n
        for n in _text_nodes(page)
        if _english(n) and not _is_tenant_data(n, files) and _english(_without_data(n, values))
    }


def _render(tmp_path: Path, files: dict[str, str]) -> dict[str, str]:
    run = tmp_path / "Acme_AS" / "2026-01-01_0900"
    run.mkdir(parents=True)
    for name, content in files.items():
        (run / name).write_text(content, encoding="utf-8")
    ctx = build_report_context("Acme AS", "acme.example", run, [], lang="no", persist_metrics=False)
    ctx["t"], ctx["lang"], ctx["theme"] = T("no"), "no", "light"
    env = _jinja_env()
    return {name: env.get_template(name).render(**ctx) for name in TEMPLATES}


@pytest.mark.parametrize("fixture", FIXTURES, ids=list(FIXTURES))
def test_a_norwegian_report_has_no_english_outside_the_tenants_data(tmp_path, fixture):
    files = FIXTURES[fixture]
    english = sorted(
        f"{template}: {node}"
        for template, page in _render(tmp_path, files).items()
        for node in _english_nodes(page, files)
    )
    assert not english, f"({fixture}) shows English:\n" + "\n".join(english)


def test_the_scan_finds_english_when_there_is_some(tmp_path):
    """The scan above would pass on anything if it could not see English."""
    page = _render(tmp_path, {})["report_tech.html.j2"]
    page = page.replace("</body>", "<p>Full Security Audit</p></body>")
    assert _english_nodes(page, {}) == {"Full Security Audit"}


def test_a_value_from_a_file_is_data_but_the_words_around_it_are_not():
    files = {
        "08_conditional_access.txt": "  Policy Name       : Block external guests\n",
        "18_risky_users.json": json.dumps({"users": [{"level": "medium"}]}),
    }
    page = (
        "<p>Policy: Block external guests</p>"
        "<p>u@acme.example (risikonivå: medium)</p>"
        "<p>2 brukere med høy/medium risiko</p>"
        "<p>Invites from: everyone</p>"
    )
    assert _english_nodes(page, files) == {
        "2 brukere med høy/medium risiko",
        "Invites from: everyone",
    }


def test_a_collectors_own_words_in_a_file_are_not_the_tenants_data():
    """The words a collector wrote are found wherever they stand: set into a
    sentence, alone in a cell, or as an old run holds them (TODO C15)."""
    files = {
        "30b_teams_guest_access.txt": "  Allow Invites From       : Admins and Guest Inviters\n",
        "60_fortigate_audit.txt": json.dumps({"policy_warnings": ["Policy 19: logging disabled"]}),
        "07c_emergency_access_check.json": json.dumps(
            {"admins": [{"notes": ["No MFA — potential break-glass"]}]}
        ),
        "26_email_dns_spf_dmarc.txt": "    SPF            : MISSING\n",
    }
    page = (
        "<p>Invitasjoner: Admins and Guest Inviters</p>"
        "<li>Policy 19: logging disabled</li>"
        "<td>No MFA — potential break-glass</td>"
        "<td>MISSING</td>"
        # The tenant's own words, and the file shown whole, stay data.
        "<td>Block external guests</td>"
        f"<div>{files['30b_teams_guest_access.txt']}</div>"
    )
    files["08_conditional_access.txt"] = "  Block external guests\n"
    assert _english_nodes(page, files) == {
        "Invitasjoner: Admins and Guest Inviters",
        "Policy 19: logging disabled",
        "No MFA — potential break-glass",
        "MISSING",
    }


# Old phrases that read the same in a Norwegian report: names, the industry's
# terms and codes. Every other old phrase must be one the scan sees as English,
# or a report that printed it as it stood would pass.
_SAME_IN_NORWEGIAN = {
    "OK (-all hardfail)",
    "OK (p=reject)",
    "CNAME -> {}",
    "Other",
    "Authenticator App",
    "Windows Hello",
    "OATH TOTP",
    "SubscriptionState.{}",
    "Policy {}: allow-all (src=all, dst=all, svc=ALL)",
}


def test_an_old_collector_phrase_printed_as_it_stood_would_be_seen():
    from tests.collector_words import LEGACY

    unseen = [
        phrase
        for phrase in LEGACY
        if phrase not in _SAME_IN_NORWEGIAN and not _english(phrase.replace("{}", "12"))
    ]
    assert not unseen, unseen


def test_the_collectors_words_are_read_from_their_source():
    """What collector_words reads is what the collectors write today, not a list
    kept by hand: a phrase a collector writes is found, the tenant's is not."""
    assert written_by_a_collector(
        "Guest invitation policy is set to 'Everyone' — any user can invite guests"
    )
    assert written_by_a_collector("Storage 'acmestorage': public blob access is enabled")
    assert not written_by_a_collector("Block external guests")
    assert not written_by_a_collector("enabled"), "a lone code is a value, as Graph's own are"


def test_the_terms_kept_in_english_do_not_hide_a_sentence():
    assert not _english("Conditional Access-policyer: 3 aktive")
    assert _english("Conditional Access policies are missing")
    assert not _english("PR.DS-01: Data-at-rest is protected")
    assert _english("PR.DS-01: Data is not protected")
    assert not _english("Verifiser at appen har User.Read.All")


# ── Every string, not only the ones a fixture reaches ─────────────────────────


def test_every_norwegian_report_string_is_norwegian():
    """The Norwegian side of the report's translation table, all of it."""
    english = []
    for key, langs in TRANSLATIONS.items():
        text = re.sub(r"\{[^}]*\}", " ", langs["no"])  # placeholders are values
        if _english(text):
            english.append(f"{key}: {langs['no']}")
    assert not english, "\n".join(english)


def test_every_section_is_named_in_norwegian():
    """A section's Norwegian name is in the report's sentences (section_name)."""
    english = [
        f"{name}: {names['no']}" for name, names in _SECTION_NAMES.items() if _english(names["no"])
    ]
    assert not english, "\n".join(english)


def test_every_key_a_template_names_exists():
    """A missing key renders as its own name: "subscription", "type".

    A key built from a prefix and a value ('drift_' ~ code) is held by the
    reason-code test in test_i18n_coverage.
    """
    missing = []
    for template in TEMPLATES:
        source = (_TEMPLATE_DIR / template).read_text(encoding="utf-8")
        keys = set(re.findall(r"\bt\.([a-z0-9_]+)\b", source))
        keys |= set(re.findall(r"\bt\(\s*'([a-z0-9_]+)'", source))
        keys = {k for k in keys if not k.endswith("_")}
        missing += [f"{template}: {k}" for k in sorted(keys) if k not in TRANSLATIONS]
    assert not missing, "\n".join(missing)
