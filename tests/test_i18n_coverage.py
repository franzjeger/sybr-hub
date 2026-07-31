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

import collections
import html as htmlmod
import importlib.util
import pathlib
import json
import re

import pytest

ROOT = pathlib.Path(".")
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
    "&times;", "&bull;",   # a close glyph and a bullet
    "0 : diff", "0 && synced",   # expressions the position regex reads as markup
    # Protocols, file extensions and product names from the infra views.
    "PPPoE", "VLANs", "IDS/IPS", "SD-WAN", "WireGuard", "OpenVPN",
    "FortiGate IPsec (IKEv2)", "Azure P2S VPN", "PSK:", "S/N:", "Model:",
    ".conf", ".ovpn", ".xml", "both", "localhost:2023", "&#x26F6;",
    "Installer: npm install -g @anthropic-ai/claude-code",   # a shell command
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


def norwegian_literals_in_js(script: str = "app.js") -> list[tuple[int, str]]:
    """Norwegian text in the scripts that never passes through t().

    Two things are deliberately not counted. A fallback — t("key", "Verktøy")
    — is a safety net for a missing key, not hard-coded UI; the key resolves
    normally. And comments are not user-facing. Counting both put the figure at
    56 when the real number was 9, which made the budget below meaningless.

    English literals are invisible to this, since there is no letter that gives
    them away. It is a floor on the problem, not a measure of it.

    This catches what the markup detector cannot: a string handed to showToast
    or confirm never sits between > and <, so seventeen of them sat in the two
    smaller scripts while both files measured clean.
    """
    js = (STATIC / script).read_text()
    lines = js.split("\n")
    found = []
    for m in re.finditer(r"""(['"])((?:[^'"\\\n]|\\.)*[ÆØÅæøå][^'"\\\n]*)\1""", js):
        line_no = js[:m.start()].count("\n")
        stripped = lines[line_no].strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        before = js[max(0, m.start() - 200):m.start()]
        if re.search(r"\bt\(\s*['\"][A-Za-z0-9_.]+['\"]\s*,\s*$", before):
            continue                              # fallback argument
        if re.search(r"\bt\(\s*$", before):
            continue                              # goes through t()
        found.append((line_no + 1, m.group(2)))
    return found


def text_shown_to_a_person(script: str) -> list[tuple[int, str]]:
    """String literals handed to showToast, confirm or alert.

    Those three functions exist to put words in front of someone, so a literal
    argument to any of them is user-facing by construction — no heuristic
    needed. This is the gap the other two detectors could not see: such a
    string never sits between > and < and need not contain a Norwegian letter,
    so thirty-four of them, in both languages, survived every file measuring
    clean. Fourteen were English, which the Norwegian detector is blind to by
    design.
    """
    js = (STATIC / script).read_text()
    found = []
    for m in re.finditer(
        r"""\b(showToast|confirm|alert)\(\s*(['"])((?:[^'"\\\n]|\\.)*)\2""", js
    ):
        text = htmlmod.unescape(m.group(3)).strip()
        if len(text) < 2 or text in _NOT_TEXT or _NOT_TEXT_RE.match(text) or _is_code(text):
            continue
        found.append((js[: m.start()].count("\n") + 1, m.group(3)))
    return found


_IDENT_END = re.compile(r"[A-Za-z0-9_$\)\]]$")


def broken_t_calls(js: str) -> list[tuple[int, str]]:
    """t() sequences that a browser paints as characters instead of calling.

    i18n_extract emits >' + t('key') + '< : close the string, call t(), reopen.
    That only closes anything when the surrounding string is single-quoted.
    Inside a template literal the quotes are ordinary characters, so the whole
    sequence stays in the string and the page shows ' + t('audit_2') + '.

    Six of those shipped while every test was green, because every detector
    here looked for text that was *missing* a t() and none looked for one that
    had been put somewhere it could not run.
    """
    out: list[tuple[int, str]] = []
    stack: list[str] = []           # ' " ` or { for a ${ } hole
    i, n = 0, len(js)
    while i < n:
        c = js[i]
        cur = stack[-1] if stack else None
        if cur in ("'", '"', "`"):
            if c == "\\":
                i += 2; continue
            if c == cur:
                stack.pop(); i += 1; continue
            if cur == "`" and c == "$" and js[i + 1:i + 2] == "{":
                stack.append("{"); i += 2; continue
            m = re.compile(r"""['"]\s*\+\s*t\(\s*['"]([a-z0-9_]+)['"]""").match(js, i)
            if m:
                out.append((js[:i].count("\n") + 1, m.group(1)))
            i += 1; continue
        # code
        if js.startswith("//", i):
            j = js.find("\n", i); i = n if j < 0 else j; continue
        if js.startswith("/*", i):
            j = js.find("*/", i); i = n if j < 0 else j + 2; continue
        if c == "/":
            # Regex literal or division, told apart by what precedes it.
            before = js[:i].rstrip()
            if before and not _IDENT_END.search(before):
                j = i + 1
                while j < n:
                    if js[j] == "\\": j += 2; continue
                    if js[j] == "[":
                        while j < n and js[j] != "]":
                            j += 2 if js[j] == "\\" else 1
                    if js[j] == "/": break
                    if js[j] == "\n": break
                    j += 1
                i = j + 1; continue
            i += 1; continue
        if c in ("'", '"', "`"):
            stack.append(c); i += 1; continue
        if c == "{" and stack and stack[-1] == "{":
            stack.append("{"); i += 1; continue
        if c == "}" and stack and stack[-1] == "{":
            stack.pop(); i += 1; continue
        i += 1
    return out


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
# The last one was a phantom too — the pattern spanned a newline and matched a
# quote on one line against a comment two lines down. A quoted JS string cannot
# hold a raw newline, so the pattern no longer does either, and the budget is
# a real zero rather than a carried exception nobody could interpret.
BUDGET_TEXT_NODES = 0
BUDGET_ATTRIBUTES = 0
BUDGET_JS_NORWEGIAN = 0


def _report(items) -> str:
    """Truncate for display only. Doing it in the detector made long strings
    unmatchable against the source they came from."""
    return "\n".join(
        "  " + " ".join(str(p)[:60] for p in i) for i in items[:15]
    )


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


# Every script that builds markup. app.js was measured first and cleared; the
# other two were never looked at, and app-infra.js turned out to hold more than
# app.js did.
_SCRIPTS = ("app.js", "app-integrations.js", "app-infra.js")


def prose_in_generated_markup(script: str = "app.js") -> list[tuple[int, str]]:
    """Text that lands between tags in markup a script builds.

    The Norwegian-letter detector above cannot see "Save" or "In Progress", and
    those are just as stuck in one language. This keys on position instead of
    spelling: anything sitting between > and < in a generated string is read by
    a person, whatever language it happens to be in.
    """
    js = (STATIC / script).read_text()
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
        found.append((line_no + 1, text))
    return found


# Ceilings, per script. Same rule as the others: only ever down.
BUDGET_JS_PROSE = {
    "app.js": 0,
    "app-integrations.js": 0,
    "app-infra.js": 0,
}


@pytest.mark.parametrize("script", _SCRIPTS)
def test_no_new_prose_hard_coded_into_generated_markup(script):
    found = prose_in_generated_markup(script)
    assert len(found) <= BUDGET_JS_PROSE[script], (
        f"{len(found)} strings baked into markup {script} builds, budget "
        f"{BUDGET_JS_PROSE[script]}. Route them through t():\n{_report(found)}"
    )


def test_the_workshop_section_titles_resolve() -> None:
    """These are looked up through a variable, so no static check sees them.

    They used to carry a Norwegian fallback beside the key, which is a second
    copy of the string in the source. Dropping it is only safe while the keys
    are known to be there."""
    d = json.loads((STATIC / "ui_i18n.json").read_text())
    js = (STATIC / "app-integrations.js").read_text()
    keys = re.findall(r"i18n: '(workshop_section_\d)'", js)
    assert len(keys) == 4, f"expected four sections, found {keys}"
    for key in keys:
        assert key in d["no"] and key in d["en"], f"{key} has no translation"


@pytest.mark.parametrize("script", _SCRIPTS)
def test_no_text_reaches_a_person_without_going_through_t(script: str) -> None:
    found = text_shown_to_a_person(script)
    assert not found, (
        f"{len(found)} hard-coded strings shown to the user in {script}:\n"
        f"{_report(found)}"
    )


@pytest.mark.parametrize("script", _SCRIPTS)
def test_no_norwegian_literal_outside_t(script: str) -> None:
    found = norwegian_literals_in_js(script)
    assert len(found) <= BUDGET_JS_NORWEGIAN, (
        f"{len(found)} Norwegian literals in {script}, budget "
        f"{BUDGET_JS_NORWEGIAN}:\n{_report(found)}"
    )


@pytest.mark.parametrize("script", _SCRIPTS)
def test_no_t_call_is_stranded_inside_a_string(script: str) -> None:
    """The counterpart to every other check here.

    Those look for text that never reached t(). This looks for a t() put
    somewhere it cannot run — and six of those shipped to the browser with the
    whole suite green, painting ' + t('audit_2') + ' on the customer list.
    """
    found = broken_t_calls((STATIC / script).read_text())
    assert not found, (
        f"{len(found)} t() calls rendered as text in {script}:\n{_report(found)}"
    )


def test_the_applier_knows_which_string_it_is_editing() -> None:
    """i18n_extract picks the replacement form from the surrounding quote.

    Getting this wrong is not a near miss — it puts characters on the customer
    list. The regex-literal case is here because a /'/ in the source desynced
    an earlier version of this scanner and made everything after it wrong.
    """
    spec = importlib.util.spec_from_file_location(
        "i18n_extract", ROOT / "scripts" / "i18n_extract.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    enclosing = module._enclosing_quote

    cases = [
        ("var a = 'x>HER<y';", "'"),
        ("var a = `x>HER<y`;", "`"),
        ('var a = "x>HER<y";', '"'),
        ("var a = `${b}x>HER<y`;", "`"),
        ("var a = 'q' + `x>HER<y`;", "`"),
        ("var a = 1; // >HER<", None),
        ("var a = 'it\\'s' + `x>HER<y`;", "`"),
        ("var a = x.replace(/'/g,'') + `>HER<`;", "`"),
    ]
    for js, want in cases:
        assert enclosing(js, js.index(">HER<")) == want, js


def test_no_element_carries_the_same_marker_twice() -> None:
    """Running apply-attrs twice used to stack a second marker on the same
    element instead of recognising the first.

    A duplicate attribute is not a style problem: the browser keeps the first
    and drops the rest, so the extra keys are dead and the markup is invalid.
    One img had three data-i18n-alt attributes.
    """
    html = (STATIC / "index.html").read_text()
    offenders = []
    for m in re.finditer(r"<[a-zA-Z][^>]*>", html):
        names = re.findall(r"\b(data-i18n(?:-[a-z-]+)?)\s*=", m.group(0))
        for name, count in collections.Counter(names).items():
            if count > 1:
                offenders.append((html[: m.start()].count("\n") + 1, f"{name} x{count}"))
    assert not offenders, f"duplicate markers:\n{_report(offenders)}"


def test_every_key_the_routes_ask_for_resolves() -> None:
    """ui_t returns the key itself when it cannot translate it.

    That is not a silent degradation: it puts "log_history_deleted" in the
    activity log where a sentence belongs, which is what the home view showed.
    Two tables exist for one application, so a key can be added to one and
    missed in the other without anything failing.
    """
    from app.web.i18n import ui_t

    called: dict[str, str] = {}
    for path in pathlib.Path("app").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"""ui_t\(\s*["']([a-z0-9_]+)["']""", src):
            called[m.group(1)] = f"{path}:{src[: m.start()].count(chr(10)) + 1}"

    assert called, "found no ui_t calls at all — has the helper been renamed?"
    unresolved = [(where, key) for key, where in sorted(called.items()) if ui_t(key) == key]
    assert not unresolved, (
        f"{len(unresolved)} keys render as their own name:\n{_report(unresolved)}"
    )
