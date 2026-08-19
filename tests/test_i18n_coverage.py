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
reached zero on both counts and stayed there.

The scripts read zero for a while too, and that zero was an artefact. The
detector looked at three of the seven files index.html loads, required an æ, ø
or å before it would call a string Norwegian, and — through a character class
that excluded both quote characters — skipped any string containing the quote
it was not delimited by. Since these scripts build markup, and markup carries
style="…", that last one hid most of them: two whole files measured clean while
"Feil ved tilkobling" sat in the toolbar. All seven are measured now, a word
list stands beside the letters, and the budgets below are what is actually
there. English literals remain invisible to the Norwegian detector by
construction; text_shown_to_a_person is what catches those.
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
    "SYBR", "Sybr HUB", "MSP Toolkit", "ESC", "IT Glue", "M365",
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
    # Customer tag vocabulary. TAG_COLORS is keyed by the tag string as it is
    # stored against the customer, so these are lookup keys, not labels —
    # translating one would return the fallback colour for every customer
    # already carrying it. The map holds both languages for the same reason.
    "Ny kunde", "New customer", "Prioritert", "Priority", "Proveperiode",
}
_NOT_TEXT_RE = re.compile(r"^(?:[\W\d_]+|Ctrl\+\S+|⌘\S*|v?\d+[\d.]*|[A-Z]{2,5})$")

# "prov", "ma" and "na" were here as ASCII-folded prøv/må/nå and were dropped:
# every one of them carries æøå in real Norwegian, so the letter branch already
# has them, while the folded spellings collided with identifiers — "prov" alone
# matched a dozen prov-* element ids in the provisioning form.
#
# What makes a string Norwegian: one of the three letters, or a word that
# exists in Norwegian and not in English. Words shared with English are kept
# out on purpose — see norwegian_literals_in_js for why the shape of this list
# matters more than its length.
_NORWEGIAN_RE = re.compile(
    r"[æøåÆØÅ]|\b(?:ikke|lagre|slett|sletter|slettet|kunde|kunder|velg|valgt|feil|"
    r"lukk|avbryt|bruker|brukere|brukernavn|passord|ingen|finnes|kjorer|kjort|hent|"
    r"henter|hentet|oppdater|oppdatert|endre|endret|sok|soker|vis|skjul|varsel|"
    r"varsler|rapport|rapporter|siste|antall|dager|mangler|manglende|ukjent|krever|"
    r"angi|apne|apnet|ferdig|startet|fullfort|mislyktes|igjen|tilbake|neste|"
    r"forrige|enheter|enhet|eller|med|som|har|kan|til|fra|av|og|er|den|det|denne|"
    r"dette|nar|hvis|alle|legg|lagt|laster|lastet|kobler|koblet|tilkoblet|"
    r"frakoblet|aktiver|aktivert|deaktiver|deaktivert|opprett|opprettet|kopier|"
    r"kopiert|navn|dato|konfigurert|handling|se)\b",
    re.IGNORECASE,
)

# snake_case with no spaces is an i18n key being passed around, not its text.
_T_CALL = re.compile(
    r"""\bt\(\s*(['"])[A-Za-z0-9_.]+\1\s*(?:,\s*(['"])(?:\\.|(?!\2).)*\2\s*)?\)"""
)

# A run of letters that could be a sentence. Excludes selectors, colours, paths
# and anything starting with punctuation or a digit.
_WORDLIKE = re.compile(r"^[A-Za-zÆØÅæøå][A-Za-zÆØÅæøå0-9 '\u2019\-\u2014:,.!?()/%\u2026]*$")

_KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")

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
    # The markup scan looks for text between > and <, which in a script also
    # matches across the halves of a comparison: "d.days_remaining >= 0 && d"
    # is read as the text "= 0 && d". A logical operator is never prose.
    if "&&" in text or "||" in text:
        return True
    # A \uXXXX escape read as source text. The detector sees the six
    # characters, not the glyph they stand for, so the "u" makes it look like
    # a word.
    if re.fullmatch(r"(?:\\u[0-9a-fA-F]{4}|\s)+", text):
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

    It used to require an æ, ø or å in the string, which is a narrow floor
    indeed: "Feil ved tilkobling", "Vis alle" and "Dager igjen" carry none, so
    the budget read zero while that text sat in the toolbar. A word list now
    stands beside the letters. Every word on it is Norwegian and nothing else —
    "for", "type", "status", "total" and "her" are all English too and are
    deliberately absent, because a false positive here means wrapping English
    in t() and inventing a key for it.
    """
    js = (STATIC / script).read_text()
    lines = js.split("\n")
    found = []
    # (?!\1) rather than [^'"]: a single-quoted string may hold double quotes
    # and almost every one here does, because these scripts build markup and
    # markup carries style="…". Excluding both quote characters meant every
    # such string was skipped, which is why two whole files measured zero.
    for m in re.finditer(r"""(['"])((?:(?!\1)[^\\\n]|\\.)*)\1""", js):
        text = m.group(2).strip()
        if len(text) < 3 or not _NORWEGIAN_RE.search(text):
            continue
        if text in _NOT_TEXT or _NOT_TEXT_RE.match(text) or _is_code(text):
            continue
        if _KEY_RE.match(text):                   # an i18n key, not its text
            continue
        # These scripts build markup, so a quote inside an HTML attribute ends
        # a "string" the tokenizer thought it was in, and the next one starts
        # mid-concatenation: title="' + t('tip_x','Klikk …') + ' captures a
        # t() call as though it were a literal. If a t() call is inside it,
        # the text did go through translation.
        if re.search(r"\bt\(\s*['\"]", text):
            continue
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



# Words that are the same in both languages because they are not really words:
# device classes, threat categories and product names as they appear in the
# vendors' own consoles. Translating "Access Point" or "Botnet" would make the
# interface harder to match against FortiGate's or UniFi's, not easier. Listed
# by value rather than matched by pattern, so the exemption cannot quietly
# widen.
_TECHNICAL_VOCABULARY = frozenset({
    "Access Point", "Gateway", "Gateway/FW", "Switch", "Client", "Server",
    "IPS", "Antivirus", "Botnet", "Web Filter", "Firewall", "VPN", "DNS",
    "WireGuard", "OpenVPN", "FortiGate", "FortiGate IPsec", "FortiGate SSL",
    "UniFi", "Tailscale", "Guacamole", "Autotask", "IT Glue", "Uniweb",
    "Microsoft", "Azure", "Azure P2S", "Azure P2S VPN", "M365", "Intune",
    "SSH hosts", "Set-Inform", "Auto-discover",
})

_DOM_TEXT_SINK = re.compile(
    r"""\.(textContent|innerText|placeholder)\s*=\s*(['"])((?:\\.|(?!\2).)*)\2"""
)


def literals_assigned_to_the_page(script: str) -> list[tuple[int, str]]:
    """String literals written straight into an element's text.

    User-facing by construction, exactly as the showToast detector is: you do
    not assign to ``textContent`` for any reason other than putting words in
    front of someone. No heuristic, and so no judgement call about whether a
    given string is prose.

    This is the third gap. The first two detectors read markup and Norwegian
    literals; the showToast one reads three named functions. A button whose
    label is set in JavaScript passes all three — ``btn.textContent =
    'Synkroniserer...'`` sits in no markup, is not an argument to anything, and
    was Norwegian in an English interface for as long as it existed.
    """
    js = (STATIC / script).read_text()
    masked = _T_CALL.sub(lambda m: " " * len(m.group(0)), js)
    found = []
    for m in _DOM_TEXT_SINK.finditer(masked):
        text = htmlmod.unescape(m.group(3)).strip()
        if (
            len(text) < 3
            or text in _NOT_TEXT
            or text in _TECHNICAL_VOCABULARY
            or _NOT_TEXT_RE.match(text)
            or _is_code(text)
            or not _WORDLIKE.match(text)
        ):
            continue
        found.append((masked[: m.start()].count("\n") + 1, text))
    return found


_LABEL_TABLE = re.compile(
    r"""\b(?:const|let|var)\s+(\w*(?:[Ll]abel|[Tt]ext|[Tt]itle|[Mm]essage|[Mm]sg|"""
    r"""[Cc]aption|[Hh]eading)s?)\s*=\s*\{"""
)


def literals_in_a_table_of_labels(script: str) -> list[tuple[int, str]]:
    """Bare strings inside an object whose name says it holds display text.

    The shape that hid the last one: a lookup table from an enum to a word,
    read later into the page. The literal is not near a DOM call, not inside
    markup, and not an argument — it is a value in an object literal, which
    every other detector walks straight past.

    ``const labels = {open:'Open', in_progress:'In Progress', ...}`` sat four
    lines below an identical table built correctly out of t() calls, and shipped
    English into a Norwegian interface. Naming is the signal here rather than
    construction, which is weaker — so the exemption list beside it is by value,
    not by pattern.
    """
    js = (STATIC / script).read_text()
    masked = _T_CALL.sub(lambda m: " " * len(m.group(0)), js)
    found = []
    for m in _LABEL_TABLE.finditer(masked):
        start = masked.index("{", m.end() - 1)
        depth = 0
        end = start
        for i in range(start, min(start + 2000, len(masked))):
            depth += (masked[i] == "{") - (masked[i] == "}")
            end = i
            if depth == 0:
                break
        line = masked[:start].count("\n") + 1
        for value in re.finditer(r"""[:,]\s*(['"])((?:\\.|(?!\1).)*)\1""", masked[start : end + 1]):
            text = htmlmod.unescape(value.group(2)).strip()
            if (
                len(text) < 3
                or text in _NOT_TEXT
                or text in _TECHNICAL_VOCABULARY
                or _NOT_TEXT_RE.match(text)
                or _is_code(text)
                or not _WORDLIKE.match(text)
            ):
                continue
            found.append((line, f"{m.group(1)}: {text}"))
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
# Per script, because they come down one file at a time. The single 0 that
# stood here was true only of what the detector could see: it required an æ, ø
# or å and refused any string containing the other quote character, so files
# built entirely out of markup measured clean. These are the numbers once it
# can see them. Only ever down.
BUDGET_JS_NORWEGIAN = {
    "app.js": 0,
    "app-assessments.js": 0,
    "app-also.js": 0,
    "app-dashboard.js": 0,
    "app-infra.js": 0,
    "app-integrations.js": 0,
    "app-policy-deploy.js": 0,
    "app-tailscale.js": 0,
    "app-tls.js": 0,
}

# Strings handed straight to showToast/confirm/alert. Norwegian and English
# alike — the mirror of the problem above is an English literal that a
# Norwegian UI shows in English.
BUDGET_JS_PERSON = {
    "app.js": 0,
    "app-assessments.js": 0,
    "app-also.js": 0,
    "app-dashboard.js": 0,
    "app-infra.js": 0,
    "app-integrations.js": 0,
    "app-policy-deploy.js": 0,
    "app-tailscale.js": 0,
    "app-tls.js": 0,
}



# Literals written straight into the page, and literals sitting in a table of
# labels. Both start at zero: the fifteen and thirteen that existed were fixed
# in the same change that added the detectors, which is the only honest moment
# to set a budget to zero.
BUDGET_JS_DOM_TEXT = {
    "app.js": 0,
    "app-assessments.js": 0,
    "app-also.js": 0,
    "app-dashboard.js": 0,
    "app-infra.js": 0,
    "app-integrations.js": 0,
    "app-policy-deploy.js": 0,
    "app-tailscale.js": 0,
    "app-tls.js": 0,
}

BUDGET_JS_LABEL_TABLES = {
    "app.js": 0,
    "app-assessments.js": 0,
    "app-also.js": 0,
    "app-dashboard.js": 0,
    "app-infra.js": 0,
    "app-integrations.js": 0,
    "app-policy-deploy.js": 0,
    "app-tailscale.js": 0,
    "app-tls.js": 0,
}

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
    """The whole front end at once. Called with no argument this measured
    app.js alone, so a literal added to any of the other six was not counted
    here at all."""
    total = sum(len(norwegian_literals_in_js(s)) for s in _SCRIPTS)
    ceiling = sum(BUDGET_JS_NORWEGIAN.values())
    assert total <= ceiling, (
        f"{total} Norwegian literals outside t() across the scripts, "
        f"budget {ceiling}"
    )


def test_the_budgets_are_not_stale():
    """A budget well above the real count stops ratcheting anything.

    If a batch lands without the ceiling coming down with it, this says so
    rather than letting the slack hide the next regression.
    """
    checks = [
        ("text nodes", BUDGET_TEXT_NODES, len(untranslated_text_nodes())),
        ("attributes", BUDGET_ATTRIBUTES, len(untranslated_attributes())),
    ]
    for script in _SCRIPTS:
        checks += [
            (f"js literals {script}", BUDGET_JS_NORWEGIAN[script],
             len(norwegian_literals_in_js(script))),
            (f"js prose {script}", BUDGET_JS_PROSE[script],
             len(prose_in_generated_markup(script))),
            (f"js shown {script}", BUDGET_JS_PERSON[script],
             len(text_shown_to_a_person(script))),
        ]
    for name, budget, count in checks:
        slack = budget - count
        assert slack <= 10, (
            f"{name}: budget {budget} but only {count} remain — "
            f"lower it to {count} in the commit that fixed them"
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
# Every script index.html loads. It was three, and the four it left out
# were not measured by any check in this file.
_SCRIPTS = (
    "app.js",
    "app-also.js",
    "app-assessments.js",
    "app-dashboard.js",
    "app-infra.js",
    "app-integrations.js",
    "app-tailscale.js",
    "app-tls.js",
)


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
BUDGET_JS_PROSE = {           # ceilings per script; only ever down
    "app.js": 0,
    "app-assessments.js": 0,
    "app-also.js": 0,
    "app-dashboard.js": 0,
    "app-infra.js": 0,
    "app-integrations.js": 0,
    "app-policy-deploy.js": 0,
    "app-tailscale.js": 0,
    "app-tls.js": 0,
}


@pytest.mark.parametrize("script", _SCRIPTS)
def test_no_new_prose_hard_coded_into_generated_markup(script):
    found = prose_in_generated_markup(script)
    assert len(found) <= BUDGET_JS_PROSE[script], (
        f"{len(found)} strings baked into markup {script} builds, budget "
        f"{BUDGET_JS_PROSE[script]}. Route them through t():\n{_report(found)}"
    )


@pytest.mark.parametrize("script", _SCRIPTS)
def test_no_text_reaches_a_person_without_going_through_t(script: str) -> None:
    found = text_shown_to_a_person(script)
    budget = BUDGET_JS_PERSON[script]
    assert len(found) <= budget, (
        f"{len(found)} hard-coded strings shown to the user in {script}, "
        f"budget {budget}:\n{_report(found)}"
    )


@pytest.mark.parametrize("script", _SCRIPTS)
def test_no_norwegian_literal_outside_t(script: str) -> None:
    found = norwegian_literals_in_js(script)
    budget = BUDGET_JS_NORWEGIAN[script]
    assert len(found) <= budget, (
        f"{len(found)} Norwegian literals in {script}, budget "
        f"{budget}:\n{_report(found)}"
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


def test_every_key_a_script_asks_for_exists_in_both_languages():
    """A fallback is a safety net, not a translation.

    The Python side has the same check above, and there it is easy: ui_t
    renders the key itself when it cannot resolve it, so a missing key shows
    up as "log_history_deleted" in the interface and somebody reports it.

    The JS side hides it. `t('status_watch', 'Følg med')` renders the fallback
    when the key is absent — so the Norwegian UI looks perfect, the English UI
    quietly says "Følg med", and every detector in this file passes because
    the string *is* routed through t(). Forty-five keys had accumulated that
    way: ten showing Norwegian to an English reader, thirty-five showing
    English to a Norwegian one.

    The budget tests measure whether a string goes through t(). This measures
    whether that accomplished anything.
    """
    import json

    strings = json.loads(
        (STATIC / "ui_i18n.json").read_text(encoding="utf-8")
    )

    # The literal must be the whole argument: t('activity_' + key) builds its
    # key at runtime, and the prefix is not one to look up.
    call = re.compile(r"""\bt\(\s*(['"])([A-Za-z0-9_.]+)\1\s*(?=[,)])""")

    missing: list[tuple[str, str]] = []
    for js in sorted(STATIC.glob("*.js")):
        src = js.read_text(encoding="utf-8")
        for m in call.finditer(src):
            key = m.group(2)
            absent = [lang for lang in ("no", "en") if key not in strings[lang]]
            if absent:
                line = src[: m.start()].count("\n") + 1
                missing.append((f"{js.name}:{line}", f"{key} (missing in {'+'.join(absent)})"))

    assert not missing, (
        f"{len(missing)} t() calls name a key that does not exist:\n{_report(missing)}"
    )


def test_every_reason_code_the_backend_emits_is_translated_in_both_tables():
    """The baseline card showed Norwegian titles beside English detail lines.

    Both came from code I wrote: the titles from the baseline JSON, which was
    Norwegian-only, and the detail from the evaluator, which formatted English
    sentences. Neither passed through a translation table, so neither could be
    translated, and every detector in this file was blind to both — they read
    JavaScript, and this was a JSON document and a Python f-string.

    The fix was to stop emitting prose from the core: a check returns a
    reason_code and the values behind it, and the report template and the
    browser each build the sentence. This holds the other half of that — a
    code with no translation renders as nothing at all, which is worse than
    the wrong language.
    """
    import json

    from app.core.baseline import REASON_CODES as BASELINE_CODES
    from app.core.policy_drift import REASON_CODES as DRIFT_CODES
    from app.reports.i18n import TRANSLATIONS

    ui = json.loads((STATIC / "ui_i18n.json").read_text(encoding="utf-8"))

    missing: list[tuple[str, str]] = []
    for prefix, codes in (("bl_", BASELINE_CODES), ("drift_", DRIFT_CODES)):
        for code in codes:
            key = prefix + code
            for lang in ("no", "en"):
                if not str(ui.get(lang, {}).get(key, "")).strip():
                    missing.append(("ui_i18n.json", f"{key} ({lang})"))
                if not str(TRANSLATIONS.get(key, {}).get(lang, "")).strip():
                    missing.append(("reports/i18n.py", f"{key} ({lang})"))

    assert not missing, f"{len(missing)} reason codes render as nothing:\n{_report(missing)}"


def test_the_reason_code_tuples_have_not_drifted_from_the_source():
    """A tuple nobody updates is a guard that stops guarding."""
    declared = set()
    emitted = set()
    for module, name in (
        ("app/core/baseline.py", "REASON_CODES"),
        ("app/core/policy_drift.py", "REASON_CODES"),
    ):
        src = pathlib.Path(module).read_text(encoding="utf-8")
        block = re.search(rf"{name} = \(([^)]*)\)", src, re.S).group(1)
        declared |= set(re.findall(r'"([a-z_]+)"', block))
        body = src[src.index(")", src.index(name)) :]
        emitted |= set(re.findall(r'reason_code"?\]?\s*[:=]\s*"([a-z_]+)"', body))
        emitted |= set(re.findall(r'unmeasured\(\s*"([a-z_]+)"', body))

    emitted.discard("")
    undeclared = sorted(emitted - declared)
    assert not undeclared, (
        f"these reason codes are emitted but not declared, so nothing checks "
        f"that they are translated: {undeclared}"
    )


@pytest.mark.parametrize("script", sorted(BUDGET_JS_DOM_TEXT))
def test_no_new_literals_written_straight_into_the_page(script):
    """A button label set in JavaScript is in no markup and no function call.

    It passed every other detector here, and stayed Norwegian in an English
    interface for as long as it existed.
    """
    hits = literals_assigned_to_the_page(script)
    assert len(hits) <= BUDGET_JS_DOM_TEXT[script], (
        f"{script}: {len(hits)} literals assigned to the page "
        f"(budget {BUDGET_JS_DOM_TEXT[script]}):\n{_report(hits)}"
    )


@pytest.mark.parametrize("script", sorted(BUDGET_JS_LABEL_TABLES))
def test_no_new_label_tables_built_from_bare_strings(script):
    """The shape that hid the last one — an enum-to-word lookup.

    It sat four lines below an identical table built correctly out of t()
    calls, and shipped English into a Norwegian interface.
    """
    hits = literals_in_a_table_of_labels(script)
    assert len(hits) <= BUDGET_JS_LABEL_TABLES[script], (
        f"{script}: {len(hits)} bare strings in a table of labels "
        f"(budget {BUDGET_JS_LABEL_TABLES[script]}):\n{_report(hits)}"
    )
