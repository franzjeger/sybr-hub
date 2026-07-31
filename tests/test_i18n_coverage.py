"""No user-facing text may be hard-coded in the markup or the scripts.

Every string a person reads belongs in ui_i18n.json, in both languages. A
literal in index.html or app.js is stuck in whichever language whoever typed it
happened to think in, which is how the app came to show "Customer Overview"
beside "Oppdatert 16:15" and "Alle tags".

There are several hundred of them, accumulated over a long time and added to by
every redesign. Fixing them in one pass would be a huge unreviewable change, so
this test works as a ratchet: it counts what is left and fails if the number
grows. Bring a batch into ui_i18n.json, lower the budget in the same commit,
and the ground you took cannot be given back.

The budgets are ceilings, not targets. They only ever go down. index.html
reached zero on both counts; app.js still has its own literals, and English
ones are invisible to a detector that keys on æøå.
"""

from __future__ import annotations

import html as htmlmod
import pathlib
import re

STATIC = pathlib.Path("app/web/static")

# Not translatable: product and vendor names, keyboard hints, bare numbers and
# acronyms. Listed rather than pattern-matched where a pattern would be too
# eager, so adding a new brand is a deliberate edit.
_NOT_TEXT = {
    "SYBR", "MSP Toolkit", "SYBR — MSP Toolkit", "ESC", "IT Glue", "M365",
    "GDAP", "UniFi", "FortiGate", "Tailscale", "ALSO Cloud", "Uniweb", "MRR",
    "CSV", "PDF", "HTML", "API", "SSH", "RDP", "VPN", "DNS", "TLS", "AI",
    "Swagger ↗", "Claude AI",
    # Operating systems and firewall platforms, named as products.
    "Windows", "Linux", "macOS", "pfSense", "OpenWrt", "OPNsense",
    # Placeholder examples: a host, a key prefix, a UUID shape, a colour. They
    # show the form of a value, and that form is the same in any language.
    "smtp.office365.com", "587 (TLS) / 465 (SSL)", "root", "sk-ant-...",
    "tskey-api-...", "your-org.github", "example.com", "#4d9fb5",
    "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "https://outlook.office.com/webhook/...", "Sybrt",
    # Framework names and modifier keys, printed as-is in every language.
    "CIS + NIST + ISO", "CIS + NIST CSF", "CIS + ISO 27001", "CIS only",
    "Ctrl", "Shift", "Alt", "Cmd", "Esc", "Tab", "Excel", "Live", "Tailnet",
    'VPN\xa0·',   # the VPN chip prefix, non-breaking spaces and all
    "claude", "ALSO Cloud Marketplace", "Organization API key",
    # Menu paths inside other vendors' interfaces: the reader retypes them
    # there, so translating them would send someone looking for a menu that
    # does not exist.
    "System → Administrators → Create New → REST API Admin",
    "unifi.ui.com → Settings → API", "console.anthropic.com",
    "docs/msp-toolkit-architecture.svg",
    # Log-level filters and grade letters: symbols the UI reads back verbatim.
    "INFO+", "WARNING+", "ERROR+", "DEBUG+", "A+", "A-", "B+", "B-", "C+", "C-",
}
_NOT_TEXT_RE = re.compile(r"^(?:[\W\d_]+|Ctrl\+\S+|⌘\S*|v?\d+[\d.]*|[A-Z]{2,5})$")

# Code, not language. The API reference panel lists sixty-odd endpoint
# signatures — "GET /audit/stream (SSE) · POST /audit/cancel" — which are
# identifiers a reader matches against the server, not prose. Counting them put
# the largest cluster in the file at 74 strings when 8 were translatable, and
# "fixing" them would have meant sixty keys whose two languages are the same
# URLs.
_CODE_RE = re.compile(
    r"^(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|WS)\s|"      # a request line
    r"^/[a-z0-9{}/_.-]+$|"                                     # a bare path
    r"^https?://|"                                             # a URL
    r"^[a-z_]+\([^)]*\)$|"                                     # a function signature
    r"^\(/api/[a-z_]+(?:/\*)?\)$|"                                  # a path left beside a translated word
    r"^[—–-]\s*v?\d+[\d.]*$"                                   # a version fragment, likewise
)


# "FortiGate (/api/fortigate/*)" — a vendor name and a path, neither of which
# translates. "Kunder (/api/customers/*)" does, so the name is checked against
# the brand list rather than the shape being trusted on its own.
_HEADING_RE = re.compile(r"^(.+?)\s*\(/api/[a-z_]+/\*\)$")


def _is_code(text: str) -> bool:
    if _CODE_RE.match(text):
        return True
    heading = _HEADING_RE.match(text)
    if heading and (heading.group(1) in _NOT_TEXT or _NOT_TEXT_RE.match(heading.group(1))):
        return True
    # A line of endpoints joined by the separator this panel uses.
    parts = [p.strip() for p in text.split("·") if p.strip()]
    return len(parts) > 1 and all(_CODE_RE.match(p) for p in parts)


def _markup_without_scripts() -> str:
    """Blank out scripts and styles, keeping every newline.

    Deleting them shifted every line number after the first <script>, so the
    failure message pointed at the wrong place — which is most of the value of
    the message. Replacing each block with its own newlines keeps offsets true.
    """
    src = (STATIC / "index.html").read_text()
    return re.sub(
        r"<script\b.*?</script>|<style\b.*?</style>|<title\b.*?</title>",
        lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S,
    )


def untranslated_text_nodes() -> list[tuple[int, str]]:
    """Text a reader sees, on an element that declares no key for it."""
    clean = _markup_without_scripts()
    found = []
    for m in re.finditer(r">([^<>]*[A-Za-zÆØÅæøå][^<>]*)<", clean):
        text = htmlmod.unescape(m.group(1)).strip()
        if not text or len(text) < 2 or text in _NOT_TEXT or _NOT_TEXT_RE.match(text):
            continue
        if _is_code(text):
            continue
        tag = clean[clean.rfind("<", 0, m.start()):m.start() + 1]
        if "data-i18n" in tag:
            continue
        found.append((clean[:m.start()].count("\n") + 1, text[:60]))
    return found


def untranslated_attributes() -> list[tuple[int, str, str]]:
    """title, placeholder, aria-label and alt carry text too."""
    clean = _markup_without_scripts()
    found = []
    for attr in ("title", "placeholder", "aria-label", "alt"):
        for m in re.finditer(rf'{attr}="([^"]*[A-Za-zÆØÅæøå][^"]*)"', clean):
            end = clean.find(">", m.start())
            tag = clean[clean.rfind("<", 0, m.start()):end + 1]
            if f"data-i18n-{attr}" in tag:
                continue
            value = m.group(1).strip()
            if value in _NOT_TEXT or _NOT_TEXT_RE.match(value):
                continue
            found.append((clean[:m.start()].count("\n") + 1, attr, value[:40]))
    return found


def norwegian_literals_in_js() -> list[tuple[int, str]]:
    """Norwegian text in the scripts that never passes through t().

    Two things are deliberately not counted. A fallback — t("key", "Verktøy")
    — is a safety net for a missing key, not hard-coded UI; the key resolves
    normally. And comments are not user-facing. Counting both put the figure at
    56 when the real number was 9, which made the budget below meaningless.

    English literals are invisible to this, since there is no letter that gives
    them away. It is a floor on the problem, not a measure of it.
    """
    js = (STATIC / "app.js").read_text()
    lines = js.split("\n")
    found = []
    for m in re.finditer(r"""(['"])((?:[^'"\\]|\\.)*[ÆØÅæøå][^'"\\]*)\1""", js):
        line_no = js[:m.start()].count("\n")
        stripped = lines[line_no].strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        before = js[max(0, m.start() - 200):m.start()]
        if re.search(r"\bt\(\s*['\"][A-Za-z0-9_.]+['\"]\s*,\s*$", before):
            continue                              # fallback argument
        if re.search(r"\bt\(\s*$", before):
            continue                              # goes through t()
        found.append((line_no + 1, m.group(2)[:60]))
    return found


# Ceilings. Lower them as batches land; never raise them.
#
# text nodes went 251 -> 158, but only 11 of that were strings brought into
# ui_i18n.json. The other 82 were never translatable: the API reference lists
# sixty-odd endpoint signatures, and its section headings are vendor names
# beside a path. Counting them made the largest cluster in the file look like
# 74 strings when 8 were real, and "fixing" them would have produced sixty keys
# whose two languages are identical URLs.
#
# js literals went 56 -> 1 in one commit, but only 9 of those 56 were ever
# real: the detector was counting t("key", "fallback") arguments and comments.
# The one that remains is a multi-line string the regex mis-reads, kept rather
# than special-cased so the next reader sees the limit of the measurement.
BUDGET_TEXT_NODES = 0
BUDGET_ATTRIBUTES = 0
BUDGET_JS_NORWEGIAN = 1


def _report(items) -> str:
    return "\n".join("  " + " ".join(str(p) for p in i) for i in items[:15])


def test_no_new_hardcoded_text_in_the_markup():
    found = untranslated_text_nodes()
    assert len(found) <= BUDGET_TEXT_NODES, (
        f"{len(found)} hard-coded strings, budget {BUDGET_TEXT_NODES}. "
        f"New user-facing text belongs in ui_i18n.json:\n{_report(found)}"
    )


def test_no_new_hardcoded_attributes():
    found = untranslated_attributes()
    assert len(found) <= BUDGET_ATTRIBUTES, (
        f"{len(found)} untranslated attributes, budget {BUDGET_ATTRIBUTES}:\n{_report(found)}"
    )


def test_no_new_norwegian_literals_in_the_scripts():
    found = norwegian_literals_in_js()
    assert len(found) <= BUDGET_JS_NORWEGIAN, (
        f"{len(found)} Norwegian literals outside t(), budget {BUDGET_JS_NORWEGIAN}:\n{_report(found)}"
    )


def test_the_budgets_are_not_stale():
    """A budget well above the real count stops ratcheting anything.

    If a batch lands without the ceiling coming down with it, this says so
    rather than letting the slack hide the next regression.
    """
    for name, budget, found in (
        ("text nodes", BUDGET_TEXT_NODES, untranslated_text_nodes()),
        ("attributes", BUDGET_ATTRIBUTES, untranslated_attributes()),
        ("js literals", BUDGET_JS_NORWEGIAN, norwegian_literals_in_js()),
    ):
        slack = budget - len(found)
        assert slack <= 10, (
            f"{name}: budget {budget} but only {len(found)} remain — "
            f"lower it to {len(found)} in the commit that fixed them"
        )


def test_every_text_bearing_attribute_can_actually_be_translated():
    """aria-label and alt were not handled, so marking them up did nothing."""
    js = (STATIC / "app.js").read_text()
    for attr in ("title", "placeholder", "aria-label", "alt"):
        assert f"'{attr}'" in js.split("_I18N_ATTRS")[1][:200], (
            f"{attr} is not in the translated attribute list"
        )


# The letter-based detector above cannot see Norwegian spelled without æøå —
# "Konfigurert", "Se audit", "Krever handling" look like any other string. A
# mutation putting one of them back passed the whole file, which means the
# batch that removed them was unprotected. These name the keys instead.

_KEYS_THAT_REPLACED_LITERALS = (
    "st_not_configured", "st_configured", "st_secret_expired",
    "st_secret_days_left", "st_expired", "st_none", "time_now",
    "find_users_no_mfa", "find_secret_expiring", "find_subs_expired",
    "find_subs_expiring", "lbl_see_audit", "lbl_see_subscriptions",
    "hdr_needs_action", "msg_none_expiring_soon", "lbl_others_over_90d",
    "src_m365_audit", "nav_m365_status",
)


def test_the_keys_that_replaced_literals_are_still_used():
    """Otherwise a revert reintroduces the literal and nothing notices."""
    js = (STATIC / "app.js").read_text()
    unused = [k for k in _KEYS_THAT_REPLACED_LITERALS if f"'{k}'" not in js]
    assert not unused, (
        f"keys no longer referenced — a literal has probably come back: {unused}"
    )


def test_those_keys_exist_in_both_languages():
    import json

    d = json.loads((STATIC / "ui_i18n.json").read_text())
    for key in _KEYS_THAT_REPLACED_LITERALS:
        assert key in d["no"], f"{key} missing from Norwegian"
        assert key in d["en"], f"{key} missing from English"


def test_the_languages_have_the_same_keys():
    """A key present in one language only shows a raw key name to the other."""
    import json

    d = json.loads((STATIC / "ui_i18n.json").read_text())
    only_no = set(d["no"]) - set(d["en"])
    only_en = set(d["en"]) - set(d["no"])
    assert not only_no and not only_en, f"no-only: {sorted(only_no)[:5]}, en-only: {sorted(only_en)[:5]}"


def test_every_key_used_in_the_markup_exists():
    """translatePage calls t(key) with no fallback, and t returns the key when
    it finds nothing — so a missing entry puts "btn_export" on screen as text.

    Three were doing exactly that, on the integrations panel and the renewals
    placeholder.
    """
    import json

    d = json.loads((STATIC / "ui_i18n.json").read_text())
    html = (STATIC / "index.html").read_text()
    used = set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', html))
    missing = sorted(k for k in used if k not in d["no"])
    assert not missing, f"markup references keys that do not exist: {missing}"


def test_a_translated_span_does_not_hold_the_spacing_around_it():
    """textContent replacement drops whatever whitespace the span held.

    A sentence split around an inline <strong> or <code> keeps its prose in
    spans. If the trailing space lives inside the span, translating the page
    removes it and the words run into the brand: "fraconsole.anthropic.com".
    The space belongs in the markup between the elements.
    """
    html = (STATIC / "index.html").read_text()
    bad = re.findall(r'<span data-i18n="([^"]+)">(?:\s[^<]*|[^<]*\s)</span>', html)
    assert not bad, f"spans holding their own padding: {bad[:8]}"


def prose_in_generated_markup() -> list[tuple[int, str]]:
    """Text that lands between tags in markup app.js builds.

    The Norwegian-letter detector above cannot see "Save" or "In Progress", and
    those are just as stuck in one language. This keys on position instead of
    spelling: anything sitting between > and < in a generated string is read by
    a person, whatever language it happens to be in.
    """
    js = (STATIC / "app.js").read_text()
    lines = js.split("\n")
    found = []
    for m in re.finditer(r">([^<>{}$'\"\n]{2,70})<", js):
        text = m.group(1).strip()
        if not text or not re.search(r"[A-Za-zÆØÅæøå]", text):
            continue
        if text in _NOT_TEXT or _NOT_TEXT_RE.match(text) or _is_code(text):
            continue
        line_no = js[:m.start()].count("\n")
        src = lines[line_no].strip()
        if src.startswith("//") or src.startswith("*"):
            continue
        found.append((line_no + 1, text[:60]))
    return found


# Ceiling for the above. Same rule as the others: only ever down.
BUDGET_JS_PROSE = 69


def test_no_new_prose_hard_coded_into_generated_markup():
    found = prose_in_generated_markup()
    assert len(found) <= BUDGET_JS_PROSE, (
        f"{len(found)} strings baked into markup app.js builds, budget "
        f"{BUDGET_JS_PROSE}. Route them through t():\n{_report(found)}"
    )
