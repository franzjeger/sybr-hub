"""Helpers every domain parser shares.

Row and banner counting for the fixed-width section files, the lookup of
per-subscription Azure files and their JSON sidecars, the first line of a
"(not available)" block, and recognising a file that holds an error.
"""

from __future__ import annotations

import json
import logging
import re

log = logging.getLogger(__name__)


def _first_prose_line(text: str) -> str:
    """The first sentence under a "(not available)" banner.

    The collector writes the cause there — which permission, or which licence
    — so the report can say it instead of offering the reader a guess between
    two possibilities the audit had already told apart.
    """
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or set(stripped) == {"="}:
            continue
        if "(not available)" in stripped.lower():
            continue
        if stripped.lower().startswith(("error details", "graph said")):
            continue
        return stripped
    return ""


def _find_azure_files(file_contents: dict[str, str], prefix: str) -> list[tuple[str, str, str]]:
    """Find all Azure files matching a prefix, with or without subscription suffix.

    Returns list of (filename, content, subscription_name).
    Matches both '30_azure_vms.txt' and '30_azure_vms_Corp-Backend-01.txt'.
    """
    base = prefix.replace(".txt", "")
    matches = []
    for fname, content in file_contents.items():
        if not fname.startswith(base):
            continue
        rest = fname[len(base) :]
        if rest == ".txt":
            matches.append((fname, content, ""))
        elif rest.startswith("_") and rest.endswith(".txt"):
            sub_name = rest[1:-4]  # strip leading _ and .txt
            matches.append((fname, content, sub_name))
    return matches


def _sidecar(file_contents: dict[str, str], text_filename: str) -> dict | None:
    """The JSON sidecar beside a text evidence file, parsed, or None.

    "15_sharepoint_settings.txt" has its sidecar in "15_sharepoint_settings.json"
    (see BaseSection._save_sidecar). None when the run predates the sidecar, or
    when it is empty or not a JSON object: the caller then reads the text, as it
    did before. A run whose collector failed writes only the text error, so a
    missing sidecar is never evidence of an empty result.
    """
    if not text_filename.endswith(".txt"):
        raise ValueError(f"a sidecar sits beside a .txt file, not {text_filename!r}")
    raw = file_contents.get(text_filename[:-4] + ".json")
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        log.warning("Unreadable sidecar beside %s", text_filename)
        return None
    return data if isinstance(data, dict) else None


def _find_azure_json(file_contents: dict[str, str], prefix: str) -> list[tuple[str, str, str]]:
    """Like _find_azure_files, for the .json sidecars some collectors write."""
    matches = []
    for fname, content in file_contents.items():
        if not fname.startswith(prefix):
            continue
        rest = fname[len(prefix) :]
        if rest == ".json":
            matches.append((fname, content, ""))
        elif rest.startswith("_") and rest.endswith(".json"):
            matches.append((fname, content, rest[1:-5]))
    return matches


# Permissive about what surrounds the count: banners in the wild include
# "(5 total)", "(0 entries)" and "(last 14 days — 0 events)". Requiring the
# digits to follow the parenthesis directly missed the third and counted it as
# an audit-log event.
_HEADER_TOTAL_RE = re.compile(r"^[A-Z][^\(]*\(.*\b\d+\s+[A-Za-z][A-Za-z-]*\b.*\)\s*$")


# Banner counts: pull the parenthesised part, then take the first number that
# is attached to a word meaning "how many". The vocabulary is deliberate —
# position alone cannot decide it, as two real banners show:
#
#   "(26 total: 26 permanent, 0 time-bound/activated)"  -> 26, the first number
#   "(last 14 days — 0 events)"                         -> 0, the last one
#
# Neither first-wins nor last-wins is right; "total" and "events" are the
# count words and "days" is not. An unrecognised banner yields None and the
# caller counts rows, which is the safe direction.
_BANNER_PARENS_RE = re.compile(r"\(([^)]*)\)")


_BANNER_COUNT_RE = re.compile(
    r"\b(\d+)\s+(?:total|entries|found|unresolved|events?|mailboxes|results?|"
    r"assignments?|policies|devices)\b",
    re.IGNORECASE,
)


_EMPTY_PLACEHOLDER_RE = re.compile(r"^\(?\s*(none|ingen|n/?a|empty|tom)\s*\)?\.?$", re.IGNORECASE)


# "[1]" — the per-record index a multi-line section writes before its fields.
_RECORD_INDEX_RE = re.compile(r"^\[\d+\]$")


# "Name: Scanner spam-bypass" — a field line inside such a record. The field
# name may be lower-case: 22_exchange_connectors.txt writes "outbound:" and
# "inbound:", and requiring a capital meant its one record was not recognised
# as multi-line at all. Row counting then reported the tenant's single
# connector as three, on the customer-facing report as well as the technical
# one. Only a file that already carries "[n]" index lines can reach the
# multi-line branch, so relaxing this cannot pull a plain table into it.
_RECORD_FIELD_RE = re.compile(r"^[A-Za-z][A-Za-z ]{0,30}:\s")


def _looks_like_column_header(line: str, *, near_rule: bool = True) -> bool:
    """True for a table header row or a bare section title.

    Two shapes, both of which were being counted as data:

    "Policy Name  Platform  Created" — columns split on runs of whitespace, at
    least two of them, every token starting with a capital and none carrying
    the characters that mark real data (digits, @, /, :).

    "USER INVENTORY" — a single all-caps title with no banner count after it.
    That one made every bannerless section read one too high.

    The column shape alone is not enough, because real rows land on it. Two
    that did: an OAuth grant reading "AvePoint Fly | Microsoft Graph |
    User.Read", and a PIM assignment whose principal name was truncated to
    exactly the column width, closing the gap that would have exposed the
    lower-case "servicePrinc" beside it. Eleven consent grants and one
    privileged assignment were being dropped from their counts.

    So position decides. Every header these collectors emit is written against
    a "---" or "===" rule, and across a full audit that held without exception:
    67 of 67 headers sat next to one, and all 12 lines matching the column
    shape away from a rule were data. near_rule carries that context in; the
    all-caps title needs no such help, since a lone capitalised word is not a
    record in any of these files.

    Mistaking a data row for a header undercounts, which is the same class of
    error this exists to prevent.
    """
    stripped = line.strip()
    cols = [c for c in re.split(r"\s{2,}", stripped) if c]

    if len(cols) == 1:
        return (
            stripped == stripped.upper()
            and any(ch.isalpha() for ch in stripped)
            and not any(ch.isdigit() or ch in "@/:" for ch in stripped)
        )

    if not near_rule:
        return False

    return all(c[:1].isupper() and not any(ch.isdigit() or ch in "@/:" for ch in c) for c in cols)


def _parse_banner_count(text: str) -> int | None:
    """Pull the authoritative count from a collector banner.

    Many audit files write `SECTION NAME  (N total)` as their header. That's
    the number the collector intended; trying to re-count by scanning data
    rows is error-prone because column headers and continuation lines look
    like data.

    Returns None when there is no banner *or* when the file carries more than
    one. 32_pim_roles.txt is the reason for the second case: it holds two
    sub-sections, "ELIGIBLE ... (0 total)" followed by "ACTIVE ASSIGNMENTS
    (26 total: ...)". Taking the first banner as the file's count reported zero
    privileged assignments for a tenant with twenty-six permanent ones, two of
    them Global Administrator. No single number describes such a file, so the
    caller falls back to counting rows.
    """
    counts: list[int] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for inside in _BANNER_PARENS_RE.findall(stripped):
            found = _BANNER_COUNT_RE.findall(inside)
            if found:
                counts.append(int(found[0]))
                break

    if len(counts) != 1:
        return None
    return counts[0]


def _is_furniture(stripped: str, *, near_rule: bool = True) -> bool:
    """True for a line that is never data, whichever branch is counting.

    Separators, NOTE prose, "(none)" placeholders, column headers and the
    section banner itself. Counting any of these is how a tenant with no Intune
    compliance policies came to be reported as having one, and how two empty
    Purview sections passed their CIS controls.

    near_rule says whether this line sits against a "---" or "===" rule, which
    is what separates a column header from a data row that happens to share its
    shape. It defaults to True so a caller judging a line in isolation keeps
    the older, more aggressive reading.
    """
    if not stripped:
        return True
    if stripped.startswith(("=", "-", "#")):
        return True
    if stripped.upper().startswith("NOTE") or stripped.upper().startswith("NO "):
        return True
    if _EMPTY_PLACEHOLDER_RE.match(stripped):
        return True
    if _looks_like_column_header(stripped, near_rule=near_rule):
        return True
    return bool(_HEADER_TOTAL_RE.match(stripped))


def _is_underlined(stripped_lines: list[str], i: int) -> bool:
    """True when line i is immediately underlined by a "---" rule.

    Underlined, not merely near a rule: the first data row of every table sits
    directly below the rule that underlines the header, so "next to a rule"
    catches it too, and eleven OAuth consent grants stayed missing.

    A dashed rule specifically. "===" frames titles and closes the file, so
    accepting it would eat the last row of a table instead — which is a real
    row, and the first version of this did exactly that. Across a full audit
    all 39 column headers were underlined by "---" and none by "===".
    """
    nxt = stripped_lines[i + 1] if i + 1 < len(stripped_lines) else ""
    return nxt.startswith("---")


def _is_multiline_record_format(text: str) -> bool:
    """True when a section renders one record across several lines.

    Transport rules are the case that matters: each rule is an "[n]" index
    followed by indented "Key: value" lines and a free-text Description that
    wraps. Row counting cannot work on that shape at all — one rule with a
    four-line description reads as nine rows.
    """
    indexed_records = 0
    keyed_lines = 0
    for line in text.splitlines():
        stripped = line.strip()
        if _RECORD_INDEX_RE.match(stripped):
            indexed_records += 1
        elif _RECORD_FIELD_RE.match(stripped):
            keyed_lines += 1
    return indexed_records > 0 and keyed_lines > indexed_records


def _count_table_rows(stripped_lines: list[str]) -> int:
    """Count the rows inside a section's tables, not every line in the file.

    These files carry more than their table. A summary block follows the rows
    in PIM and in mailbox delegations; a severity tally precedes them in the
    Defender alerts; the compliance score holds two tables under one banner.
    Counting the whole file made all four disagree with their own headers —
    one privileged-assignment file read thirty-one where twenty-six were
    listed, because four summary lines and a heading were counted as records.

    A table is what a "---" rule underlines: the header sits on the rule, and
    the rows run until a blank line, a "===" frame, or the next header. Files
    with no such structure fall back to counting the whole thing, which is what
    every count file and free-text section needs.
    """

    def underlined(i: int) -> bool:
        s = stripped_lines[i]
        return bool(s) and not s.startswith(("---", "===")) and _is_underlined(stripped_lines, i)

    if not any(underlined(i) for i in range(len(stripped_lines))):
        return sum(1 for s in stripped_lines if not _is_furniture(s))

    # One pass, because the regions overlap otherwise. A sub-section banner is
    # underlined by the same kind of rule as the column header beneath it, so
    # treating every underlined line as the start of its own table counted the
    # PIM assignments twice and its column headers as records — thirty-one
    # became fifty-four. Walking once, a header simply opens the table and the
    # next header closes it.
    rows = 0
    in_table = False
    for i, s in enumerate(stripped_lines):
        if underlined(i):
            in_table = True  # a heading or a column header; never a row
            continue
        if not in_table:
            continue
        if not s or s.startswith("==="):
            in_table = False  # blank line or frame ends the table
            continue
        if s.startswith("---"):
            continue  # the rule under a header, or a divider
        if not _is_furniture(s, near_rule=False):
            rows += 1
    return rows


def _count_data_lines(text: str) -> int:
    """How many records a section file holds.

    Three branches, in priority order. They are named and separate on purpose:
    this used to be decided implicitly by which regex happened to match first,
    and the answer came out wrong in both directions.

    1. Banner declares zero. Settled, whatever the vocabulary — entries, total,
       found, unresolved, events, mailboxes. No row counting runs, because the
       rows in an empty section are furniture and counting them is precisely
       the bug: "(0 entries)" over a "(none)" placeholder was read as one
       policy, and passed a CIS control on it.

    2. Banner declares N > 0 and the file uses a multi-line record format.
       The banner wins; see _is_multiline_record_format.

    3. Anything else — a plain table, one record per line. Rows win and the
       banner is only a sanity check. A file listing one row is one row even if
       its header claims twelve; a disagreement means the output was truncated,
       so the smaller honest number is used and the mismatch is logged.
    """
    declared = _parse_banner_count(text)

    # Branch 1 — declared empty.
    if declared == 0:
        return 0

    # Branch 2 — declared non-empty, records span lines.
    if declared is not None and _is_multiline_record_format(text):
        return declared

    # Branch 3 — tabular, or no banner at all.
    stripped_lines = [line.strip() for line in text.splitlines()]
    rows = _count_table_rows(stripped_lines)
    if declared is not None and declared != rows:
        # The two directions mean different things and the message used to
        # assert truncation for both. Fewer rows than declared is consistent
        # with truncated output. More rows than declared is not — the section
        # cannot hold records the collector never wrote — so it means extra
        # lines are being counted, typically a summary or a second table under
        # one banner. Naming which one is observed keeps the log from claiming
        # a cause it has no evidence for.
        cause = "output may be truncated" if rows < declared else "non-record lines may be counted"
        log.warning(
            "Section banner declares %d record(s) but %d row(s) are present — "
            "using the row count; %s",
            declared,
            rows,
            cause,
        )
    return rows


def _extract_policy_names(text: str) -> list[str]:
    """One name per policy from a ``_section_block`` dump.

    The block format numbers each policy ``[i]`` and follows it with
    ``Key: Value`` field lines; an empty section is written as ``(none)``. The
    previous reader treated every non-header line as a policy name, so it
    counted the ``(none)`` placeholder as one policy and each of a policy's
    field lines as a separate policy — a single six-field anti-phish policy read
    as "7". Count the ``[i]`` blocks and take each block's Name/Identity field
    (only the first, so a policy carrying both Name and Identity is not doubled).
    """
    names: list[str] = []
    have_block = False
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^\[\d+\]$", stripped):
            if have_block:
                names.append(current or f"Policy {len(names) + 1}")
            have_block = True
            current = None
            continue
        if have_block and current is None and ":" in stripped:
            key, val = stripped.split(":", 1)
            if key.strip().lower() in ("name", "identity", "policyname", "policy"):
                v = val.strip()
                if v:
                    current = v
    if have_block:
        names.append(current or f"Policy {len(names) + 1}")
    return names


def _record_count(file_contents: dict[str, str], text_filename: str) -> int:
    """How many records a section holds: its sidecar's "count", or the text's.

    The text is counted by _count_data_lines, which trusts the banner. A value
    that itself reads like a banner count, say a rule described as "(2
    policies merged)", leaves two banners in the file and the count falls back
    to counting lines. The sidecar's number is the collector's own.
    """
    data = _sidecar(file_contents, text_filename)
    count = data.get("count") if data else None
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    return _count_data_lines(file_contents.get(text_filename, ""))


def _policy_names(file_contents: dict[str, str], text_filename: str) -> list[str]:
    """One name per policy: from the sidecar's "policies", or the text's blocks.

    The names follow _extract_policy_names: the first of Name, Identity,
    PolicyName or Policy, else "Policy n".
    """
    data = _sidecar(file_contents, text_filename)
    policies = data.get("policies") if data else None
    if not isinstance(policies, list):
        return _extract_policy_names(file_contents.get(text_filename, ""))
    names: list[str] = []
    for policy in policies:
        if not isinstance(policy, dict):
            continue
        name = next(
            (
                str(policy[k]).strip()
                for k in ("Name", "Identity", "PolicyName", "Policy")
                if policy.get(k) not in (None, "")
            ),
            "",
        )
        names.append(name or f"Policy {len(names) + 1}")
    return names


def _is_error_payload(text: str) -> bool:
    """True if a section file holds a collector's error instead of its data.

    A section that fails writes the exception into the file it would otherwise
    have filled, so the file exists, is non-empty, and looks parseable. Every
    parser here then treats it as content.

    Matched on the first few lines only, and on the shapes the collectors
    actually emit. Files like 05b_signin_failures.txt and 18_risky_users.txt
    contain the word "error" in their *data* — they open with a header rule,
    and must not be blanked.
    """
    head = "\n".join(text.strip().splitlines()[:3]).lower()
    if not head:
        return False
    return (
        head.startswith("error:")
        or "client error '4" in head
        or "server error '5" in head
        or "query failed" in head
        or "fetch failed" in head
        or "collection failed" in head
    )
