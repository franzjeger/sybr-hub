"""The words the collectors write themselves, as templates a report can be checked against.

A run's files hold two kinds of text. What the tenant and its vendors said (a
group's name, a policy's display name, Graph's own "enabled") is data, and a
report shows it as it is. What the collector wrote around it (a banner, a
label for a code, a note, a warning) is the collector's own English, and a
Norwegian report must word it itself. tests/test_norwegian_reports.py used to
treat every file as data, so "Admins and Guest Inviters" and "Policy 12:
allow-all" read as the tenant's words and passed (TODO C15).

The collectors' words are read from their source: every string literal and
f-string they could write, an f-string's placeholders standing for any text.
A string a collector only compares a value with, looks up, splits on or logs
is left out: it reads data, it does not write it. Runs written before the
collectors stored codes hold words the source no longer has; LEGACY lists
those, so a report regenerated from an old run is checked against them too.
"""

from __future__ import annotations

import ast
import re
from functools import cache
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent

# The code that writes a run's files, or the JSON a run keeps of a network audit.
COLLECTORS = (
    *sorted((ROOT / "app/modules/m365_audit/sections").glob("*.py")),
    ROOT / "app/modules/m365_audit/collector.py",
    ROOT / "app/modules/m365_audit/auth.py",
    *sorted((ROOT / "app/modules/unifi_audit").glob("*.py")),
    *sorted((ROOT / "app/modules/fortigate_audit").glob("*.py")),
    ROOT / "app/services/fortigate_api.py",
    ROOT / "app/services/network_audit.py",
    ROOT / "app/services/unifi_api.py",
)

# What the collectors wrote before they stored codes, as old runs on disk
# still hold it. "{}" stands for a value. The report words each of these when
# it reads an old run; one shown as it is fails the check.
LEGACY = (
    # dns.py: a mail domain's statuses.
    "MISSING",
    "OK (-all hardfail)",
    "WEAK (~all softfail)",
    "WEAK (?all neutral)",
    "CRITICAL (+all — allows anyone)",
    "PRESENT (no 'all' mechanism)",
    "OK (p=reject)",
    "WARN (p=quarantine)",
    "WEAK (p=none)",
    "PRESENT (unknown policy)",
    "ERROR ({})",
    "TXT present",
    "CNAME -> {}",
    # groups_roles.py: a group's kind, and a role without a name.
    "Dynamic",
    "Security",
    "Distribution",
    "Other",
    "Unknown Role",
    # users_mfa.py: a registered method.
    "Phone (SMS/Call)",
    "Authenticator App",
    "FIDO2 Key",
    "Windows Hello",
    "Email OTP",
    "Temp Access Pass",
    "OATH TOTP",
    "Certificate",
    "Password",
    # intune.py: why a collection was not available.
    "Graph refused this collection with {}, reporting a licence gap. Verify the required "
    "licence for this endpoint; the response does not identify a specific missing Intune SKU.",
    "The Intune service refused this collection ({}). Check {} and admin consent, an active "
    "Intune licence and tenant service provisioning. The response alone does not establish "
    "which prerequisite failed.",
    "Graph refused this collection with {}. Check {} and admin consent, token validity and an "
    "active Intune licence. The response alone does not establish the cause.",
    "Graph refused this collection with {}: the app registration is missing {} or its admin "
    "consent.",
    "The collection failed before it could be read: {}",
    # azure_network.py: a risky NSG rule; auth.py and collector.py: a subscription.
    "NSG '{}' rule '{}' (priority {}): allows inbound from {} to port(s) {}",
    "SubscriptionState.{}",
    "Primary",
    # fortigate_api.py: the HA mode; network_audit.py and the UniFi client: why a
    # device could not be read; m365_backup.py: an app it left unread.
    "Standalone",
    "SSH timeout",
    "Connection failed",
    "sshpass not installed — run: brew install hudochenkov/sshpass/sshpass",
    "not read: more than {} matching apps",
    # teams_policies.py: who may invite guests, and the guest role.
    "Everyone (most open)",
    "Admins and Guest Inviters",
    "Admins, Guest Inviters, and Members",
    "No one (most restrictive)",
    "Same as member users",
    "Limited access (default)",
    "Restricted access (most restrictive)",
    # identity_security.py: the break-glass notes.
    "No MFA — potential break-glass",
    "Excluded from CA — confirmed break-glass candidate",
    "Excluded from CA but signed in {}d ago — an actively-used admin bypassing MFA, "
    "NOT a break-glass account",
    "CA policies not collected — cannot confirm exclusion",
    # fortigate_api.py: a firewall policy's finding.
    "Policy {}: allow-all (src=all, dst=all, svc=ALL)",
    "Policy {}: logging disabled",
)

# Calls whose string arguments read data rather than write it.
_READERS = frozenset(
    {
        "get",
        "startswith",
        "endswith",
        "split",
        "rsplit",
        "partition",
        "rpartition",
        "replace",
        "strip",
        "lstrip",
        "rstrip",
        "count",
        "find",
        "index",
        "match",
        "search",
        "fullmatch",
        "findall",
        "finditer",
        "sub",
        "compile",
        "debug",
        "info",
        "warning",
        "error",
        "exception",
        "critical",
        "getattr",
        "hasattr",
        "isinstance",
        "setdefault",
        "pop",
    }
)

_WORD = re.compile(r"[A-Za-z]{3,}")
_CODE = re.compile(r"[a-z][A-Za-z0-9_]*")
# A collector's own words are a line, not a file: a longer text is not tried,
# so a whole file shown as an exhibit stays what it is, the file.
_LONGEST = 400


class _Template(NamedTuple):
    """Constant pieces with a value between each: "Policy {}: logging disabled".

    ``head`` and ``tail`` say whether a value comes before the first piece or
    after the last. Whitespace is collapsed, as a report collapses it.
    """

    pieces: tuple[str, ...]
    head: bool
    tail: bool

    def matches(self, text: str) -> bool:
        pieces = self.pieces
        if not self.head and not text.startswith(pieces[0]):
            return False
        if not self.tail and not text.endswith(pieces[-1]):
            return False
        if len(pieces) == 1 and not self.head and not self.tail:
            return text == pieces[0]
        # Leftmost first, each value at least one character: exact for a
        # template whose values may be any text.
        pos = 0
        for i, piece in enumerate(pieces):
            if i == 0 and not self.head:
                pos = len(piece)
                continue
            if i == len(pieces) - 1 and not self.tail:
                return len(text) - len(piece) >= pos + 1
            found = text.find(piece, pos + 1)
            if found < 0:
                return False
            pos = found + len(piece)
        return len(text) >= pos + 1


def _template(parts: list[str | None]) -> _Template | None:
    """The template for text built from these parts; None stands for a value.

    None when the constant parts hold no word: a layout string such as
    f"  {label:<45} {value}" would match anything; and when they hold one
    word beside a value (f"{n} Methods"), which would match too much. None
    too for a lone lowercase token ("none", "enabled", "online"): that is a
    code, the same kind of value Graph writes, and a report that shows one
    shows a value.
    """
    words = _WORD.findall(" ".join(p for p in parts if p))
    if not words or (len(words) == 1 and None in parts):
        return None
    if len(parts) == 1 and _CODE.fullmatch(parts[0] or ""):
        return None
    pieces: list[str] = []
    values: list[bool] = []  # whether a value comes before each piece
    pending = False
    for part in parts:
        if part is None or not part.split():
            pending = pending or part is None
            continue
        pieces.append(" ".join(part.split()))
        values.append(pending)
        pending = False
    return _Template(tuple(pieces), head=values[0], tail=pending)


def _reading_context(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    # A value in a tuple or set is read as the container is: ("Default", "default")
    # in a comparison names values to recognise, not words to write.
    while isinstance(parent, ast.Tuple | ast.List | ast.Set):
        node, parent = parent, parents.get(parent)
    if isinstance(parent, ast.Expr):  # a docstring or a bare string
        return True
    if isinstance(parent, ast.Compare | ast.Subscript | ast.JoinedStr | ast.FormattedValue):
        return True
    if isinstance(parent, ast.Dict) and node in parent.keys:
        return True
    if isinstance(parent, ast.keyword):
        parent = parents.get(parent)
    if isinstance(parent, ast.Call):
        func = parent.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        return name in _READERS
    return False


def _part(value: ast.AST) -> str | None:
    """An f-string's part as text, or None for a value.

    A literal placed through a format spec (f"{'Notes':<12}") is text.
    """
    if isinstance(value, ast.FormattedValue):
        value = value.value
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _python_templates(path: Path) -> set[_Template]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    templates: set[_Template] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = [_part(v) for v in node.values]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            parts = [node.value]
        else:
            continue
        if _reading_context(node, parents):
            continue
        template = _template(parts)
        if template:
            templates.add(template)
    return templates


def _legacy_templates() -> set[_Template]:
    out = set()
    for text in LEGACY:
        parts: list[str | None] = []
        for i, piece in enumerate(text.split("{}")):
            parts += [None, piece] if i else [piece]
        template = _template(parts)
        if template:
            out.add(template)
    return out


@cache
def _templates_by_word() -> dict[str, list[_Template]]:
    """Each template under its longest word, which a text must hold to be tried."""
    templates = set().union(*(_python_templates(p) for p in COLLECTORS)) | _legacy_templates()
    by_word: dict[str, list[_Template]] = {}
    for template in sorted(templates):
        word = max(_WORD.findall(" ".join(template.pieces)), key=len).lower()
        by_word.setdefault(word, []).append(template)
    return by_word


def written_by_a_collector(text: str) -> bool:
    """Whether this text, whole, is something a collector writes itself."""
    text = " ".join(text.split())
    if not text or len(text) > _LONGEST:
        return False
    by_word = _templates_by_word()
    return any(
        template.matches(text)
        for word in {w.lower() for w in _WORD.findall(text)}
        for template in by_word.get(word, ())
    )
