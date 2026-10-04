"""Colours in app.css come from the tokens at its top.

A hex value in a component rule is a colour each theme does not get to
redefine. The older rules carried dozens: toasts in Material reds and blues
beside the token palette, an error alert whose light-theme override was a
second set of literals, a warning button no token knew about, a sign-in card
that stayed navy on the light theme. They read the tokens now; this keeps new
literals out.

A literal is allowed where a custom property is defined (that is what the
token blocks are), inside @media print (paper is white in either theme), and
in the few rules listed below, each with the reason.
"""

from __future__ import annotations

import re
from pathlib import Path

CSS = Path("app/web/static/app.css")
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")

ALLOWED_SELECTORS = {
    # Vendors' own brand colours on their logo tiles.
    re.compile(r"^\.integ-logo--[a-z]+$"): "a vendor's brand colour",
    # A report is a white page in either theme.
    re.compile(r"^\.report-viewer-frame$"): "a report is a white page",
}


def _declarations(css: str):
    """(enclosing preludes, selector, property, value) for every declaration."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    stack: list[str] = []
    buf = ""
    for ch in css:
        if ch == "{":
            stack.append(buf.strip())
            buf = ""
        elif ch == "}":
            if buf.strip():
                yield from _split(stack, buf)
            buf = ""
            if stack:
                stack.pop()
        elif ch == ";" and stack and not stack[-1].startswith("@"):
            yield from _split(stack, buf + ";")
            buf = ""
        else:
            buf += ch


def _split(stack, text):
    for decl in text.split(";"):
        if ":" in decl:
            prop, value = decl.split(":", 1)
            yield stack[:-1], stack[-1] if stack else "", prop.strip(), value.strip()


def _allowed(preludes, selector, prop) -> bool:
    if prop.startswith("--"):
        return True
    if any(p.startswith("@media print") for p in preludes):
        return True
    selectors = [s.strip() for s in selector.split(",")]
    return all(any(rx.match(s) for rx in ALLOWED_SELECTORS) for s in selectors)


def test_component_rules_use_the_colour_tokens():
    offenders = [
        f"{selector} {{ {prop}: {value} }}"
        for preludes, selector, prop, value in _declarations(CSS.read_text(encoding="utf-8"))
        if HEX.search(value) and not _allowed(preludes, selector, prop)
    ]
    assert not offenders, "hex colours outside the tokens:\n  " + "\n  ".join(offenders)


def test_the_checker_sees_a_literal():
    """A parser that found nothing would pass the test above forever."""
    sample = ":root { --x: #fff; } .a { color: #123456; } @media print { .b { color: #000; } }"
    found = [
        (s, p)
        for pre, s, p, v in _declarations(sample)
        if HEX.search(v) and not _allowed(pre, s, p)
    ]
    assert found == [(".a", "color")]


def test_buttons_take_the_button_sizes():
    """A component that sets a button's padding makes a fourth button size.
    .btn-sm, .btn and .btn-lg are the three (app.css, Buttons)."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    offenders = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector, body = m.group(1).strip(), m.group(2)
        pads_a_button = re.search(r"\.btn\b(?![-\w])", selector) and re.search(
            r"(?<![-\w])padding\s*:", body
        )
        if pads_a_button and not re.fullmatch(r"\s*\.btn(-sm|-lg)?\s*", selector):
            offenders.append(selector)
    assert not offenders, "rules that pad a .btn of their own:\n  " + "\n  ".join(offenders)
