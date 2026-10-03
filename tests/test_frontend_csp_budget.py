"""No inline event handlers; inline style attributes are a shrinking budget."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path("app/web/static")
SOURCES = [*STATIC.glob("*.html"), *STATIC.glob("*.js")]
SCRIPTS = sorted(p for p in STATIC.glob("*.js") if p.name != "guacamole.min.js")

# The inherited single-page UI generates substantial markup in JavaScript.
# CSP distinguishes attributes from executable elements. Event-handler
# attributes are gone (script-src-attr 'none'); the style budget below keeps
# the remaining exception from becoming permanent growth.
# Lowered from 4631 when the ticket panel was built: it was written with inline
# styles first, hit this ceiling, and was rebuilt on classes in app.css. A
# budget that is not lowered when the number falls stops being a ratchet and
# becomes headroom for the next person.
# Lowered to 4532 after the CSP pass moved hover handlers into CSS.
# Lowered to 4278 when the Wiki and Helse tabs went and the customer page,
# Kunder list and Docs view moved to classes.
# Lowered to 4215 when the settings modal and Integrasjoner became the
# Administrasjon page, built on classes; to 4185 when the top bar became
# Oversikt, Kunder and Verktøy and Nettverk's tabs took the shared tab style;
# to 4168 when the active-customer bar went; to 3976 when M365-status went
# and the customer page got tabs built on classes; to 3694 when the shell
# (palette, sign-in, report viewer, footer) moved to classes on the token
# scale and every view took the one tab bar (.tabs / .tab); to 3655 with Oversikt
# and Varsler; to 2894 with the customer page and Kunder.
INLINE_STYLE_ATTRIBUTE_BUDGET = 2894

_REGISTRATION = re.compile(r"^registerUiHandlers\(\{\n(.*?)\n\}\);", re.S | re.M)
_REGISTERED_NAME = re.compile(r"^  ([A-Za-z0-9_$]+): function\b", re.M)
_HANDLER_ATTRIBUTE = re.compile(r"""data-([a-z]+)-handler=\\?["']([A-Za-z0-9_$]+)""")
# An on*= attribute in markup: preceded by whitespace, a quote or a slash and
# followed by a quote (escaped, inside a JavaScript string, or not). Property
# assignments in code (`xhr.onload = fn`) are preceded by a dot.
_INLINE_HANDLER = re.compile(r"""(?:^|[\s"'\\/])on[a-z]+\s*=\s*\\?["']""", re.I)
_JAVASCRIPT_URL = re.compile(r"""(?:href|src|action)\s*=\s*\\?["']?\s*javascript:""", re.I)


def _count(pattern: str) -> int:
    return sum(
        len(re.findall(pattern, path.read_text(encoding="utf-8"), flags=re.IGNORECASE))
        for path in SOURCES
    )


def _registered() -> dict[str, str]:
    names: dict[str, str] = {}
    for path in SCRIPTS:
        for block in _REGISTRATION.findall(path.read_text(encoding="utf-8")):
            for name in _REGISTERED_NAME.findall(block):
                assert name not in names, f"{name} registered in {names[name]} and {path.name}"
                names[name] = path.name
    return names


def _used() -> set[str]:
    used: set[str] = set()
    for path in [*STATIC.glob("*.html"), *SCRIPTS]:
        used |= {name for _, name in _HANDLER_ATTRIBUTE.findall(path.read_text(encoding="utf-8"))}
    return used


def test_static_shells_have_no_inline_script_or_style_elements():
    for path in STATIC.glob("*.html"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\bsrc\s*=)[^>]*>", source, re.I), path
        assert not re.search(r"<style(?:\s|>)", source, re.I), path


def test_no_inline_event_handlers_in_markup_or_scripts():
    """The CSP runs none of them: a control with onclick="..." does nothing.
    Name a registered handler instead (data-click-handler, see app-handlers.js)."""
    offenders = []
    for path in [*STATIC.glob("*.html"), *SCRIPTS]:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _INLINE_HANDLER.search(line) or _JAVASCRIPT_URL.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()[:120]}")
    assert not offenders, "inline event handlers or javascript: URLs:\n" + "\n".join(offenders)


def test_the_inline_handler_pattern_still_finds_them():
    """A pattern that matches nothing passes for the wrong reason."""
    samples = (
        r"""<b onclick="x()">""",
        r"""'<b onclick=\'x()\'>'""",
        r"""html += "<select onchange=\"go()\">";""",
        r"""<a href="javascript:void(0)">""",
    )
    for sample in samples:
        assert _INLINE_HANDLER.search(sample) or _JAVASCRIPT_URL.search(sample), sample
    for sample in ("xhr.onload = function() {}", "el.onclick = handler;", "var online = 1;"):
        assert not _INLINE_HANDLER.search(sample), sample


def test_inline_style_attribute_debt_cannot_grow():
    count = _count(r"\bstyle\s*=")
    assert count <= INLINE_STYLE_ATTRIBUTE_BUDGET, (
        f"inline style debt grew: {count} > {INLINE_STYLE_ATTRIBUTE_BUDGET}"
    )


def test_no_tag_carries_two_class_attributes():
    """Moving an inline style to classes merges them into the class the tag
    already has. A second class attribute would be dropped by the browser,
    and the element would silently lose either its component or its layout."""
    offenders = []
    for path in [*STATIC.glob("*.html"), *SCRIPTS]:
        source = path.read_text(encoding="utf-8")
        for m in re.finditer(r"<[a-zA-Z][^<>]*>", source):
            if len(re.findall(r"""(?:^|[\s"'])class\s*=""", m.group(0))) > 1:
                line = source[: m.start()].count("\n") + 1
                offenders.append(f"{path.name}:{line}: {m.group(0)[:120]}")
    assert not offenders, "tags with two class attributes:\n" + "\n".join(offenders)


def test_the_two_class_pattern_still_finds_them():
    tag = re.compile(r"""(?:^|[\s"'])class\s*=""")
    assert len(tag.findall('<div class="a" style="" class="b">')) == 2
    assert len(tag.findall("""'<span class="a"' + (x ? ' class="b"' : '') + '>'""")) == 2
    assert len(tag.findall('<div class="a" data-subclass="b">')) == 1


def test_index_html_has_no_inline_event_handlers():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    found = re.findall(r"<[a-zA-Z][^>]*?\s(on[a-z]+)\s*=", html)
    assert not found, f"inline handlers in index.html: {sorted(set(found))}"


def test_ui_handlers_are_an_explicit_registered_map():
    """Markup names a handler; only names registered as function literals in a
    registerUiHandlers({...}) map can be called. Nothing evaluates an attribute
    or looks a name up on window."""
    javascript = (STATIC / "app-handlers.js").read_text(encoding="utf-8")
    dispatcher = javascript[javascript.index("function _dispatchUiEvent") :]
    dispatcher = dispatcher[: dispatcher.index("\n}\n")]
    assert "_uiHandlers[name]" in dispatcher
    for forbidden in ("eval(", "window[", "Function(", "globalThis"):
        assert forbidden not in dispatcher
    assert "Object.freeze(_uiHandlers)" in javascript

    registered = _registered()
    used = _used()
    assert len(used) > 100
    assert used <= set(registered), f"used but never registered: {sorted(used - set(registered))}"
    assert set(registered) <= used, f"registered but unused: {sorted(set(registered) - used)}"
    for path in SCRIPTS:
        source = path.read_text(encoding="utf-8")
        for block in _REGISTRATION.findall(source):
            assert "eval(" not in block and "window[" not in block, path.name
