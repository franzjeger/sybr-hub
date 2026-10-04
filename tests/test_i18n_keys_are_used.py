"""Every key in ui_i18n.json is one something asks for.

Redesigns removed screens and left their strings: the active-customer bar's
"hdr_active_customer", M365-status's menu text, the device-code card's
instructions. Nothing failed, because a key nobody asks for is invisible. It
still costs whoever translates or rewords the file the time to find out it is
dead, and it reads as if the screen were still there.

A key is used when it is written as a string somewhere the interface or the
server reads it from:

* a quoted literal in a script (``t('key')``, a table of keys, a ternary);
* an attribute value in index.html (``data-i18n="key"`` and its kin);
* a quoted literal in the server's code, data or templates, which send keys
  to the page (``error_key``) or translate with ``ui_t``, whose fallback is
  this file.

Keys built at runtime are covered by the prefix they are built from. Every
literal that ends in an underscore, or that ends in one and is joined to
something (``'sev_' + sev``, ``f"activity_{kind}"``, a template literal,
``_reason('drift_', code)``), is collected as a prefix, and a key starting
with one counts as used. ``_DYNAMIC`` below names the prefixes that are
built in a way the collector cannot see.

The translation tables themselves (app/web/i18n.py, app/core/messages.py,
app/reports/i18n.py) are not references: a key defined in two tables and
asked for by neither is still dead.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

STATIC = Path("app/web/static")
STRINGS = STATIC / "ui_i18n.json"
TABLES = {
    Path("app/web/i18n.py"),
    Path("app/core/messages.py"),
    Path("app/reports/i18n.py"),
}

# Prefixes built where the collector cannot see the literal, with the place.
_DYNAMIC: dict[str, str] = {}

_LITERAL = re.compile(r"""(['"`])([A-Za-z0-9_.]+)\1""")
_ATTRIBUTE = re.compile(r"""=\s*"([A-Za-z0-9_.]+)\"""")
# 'sev_' + x, "activity_" + key, f"fw_reason_{code}", `docs_title_${n}`
_PREFIX = re.compile(r"""([A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*_)(?:['"`]\s*\+|\$?\{)""")


def _sources() -> list[tuple[Path, str]]:
    found: list[Path] = sorted(p for p in STATIC.glob("*.js") if p.name != "guacamole.min.js")
    found.append(STATIC / "index.html")
    for suffix in ("*.py", "*.json", "*.html", "*.j2"):
        found += sorted(Path("app").rglob(suffix))
    return [
        (p, p.read_text(encoding="utf-8"))
        for p in found
        if p != STRINGS and p not in TABLES and "vendor" not in p.parts
    ]


def words_in(text: str) -> set[str]:
    return {m.group(2) for m in _LITERAL.finditer(text)}


def _references() -> tuple[set[str], set[str]]:
    words: set[str] = set()
    prefixes: set[str] = set(_DYNAMIC)
    for path, text in _sources():
        words |= words_in(text)
        if path.suffix == ".html":
            words |= set(_ATTRIBUTE.findall(text))
        prefixes |= set(_PREFIX.findall(text))
        # A literal that is nothing but a prefix: _reason('drift_', code).
        prefixes |= {w for w in words_in(text) if w.endswith("_") and len(w) > 2}
    return words, prefixes


def unused_keys() -> list[str]:
    keys = json.loads(STRINGS.read_text(encoding="utf-8"))["no"]
    words, prefixes = _references()
    return sorted(k for k in keys if k not in words and not any(k.startswith(p) for p in prefixes))


def test_every_key_is_asked_for_somewhere():
    unused = unused_keys()
    assert not unused, (
        f"{len(unused)} keys in ui_i18n.json that nothing asks for (remove them from "
        f"both languages, or name the runtime prefix in _DYNAMIC):\n  " + "\n  ".join(unused)
    )


def test_the_prefix_collector_sees_the_ways_keys_are_built():
    """The prefixes the scripts build keys from today. If one of these stops
    being found, keys built from it would be reported as unused, or worse, a
    rewrite moved the building somewhere the collector cannot see."""
    _, prefixes = _references()
    for prefix in ("sev_", "activity_", "module_", "lbl_action_", "docs_title_", "bl_"):
        assert prefix in prefixes, prefix
