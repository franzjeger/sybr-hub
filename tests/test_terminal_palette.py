"""The web terminal's colours are readable on its background, in both themes.

The light palette was modelled on GitHub's and never measured: its bright
blue, magenta, cyan and white came to 3.0 to 3.6:1 on white. The dark theme
defined no bright variants at all, so xterm drew its own, and its bright
black, the grey a shell draws suggestions in, came to 2.6:1. Each --term-*
colour in app.css is measured here, as WCAG 2 contrast against --term-bg, so
a later palette change cannot bring that back.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS = Path("app/web/static/app.css")
INFRA = Path("app/web/static/app-infra.js")

THEMES = {"dark": ':root, [data-theme="dark"]', "light": '[data-theme="light"]'}
ANSI = (
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    *(
        f"bright-{name}"
        for name in ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")
    ),
)
# WCAG 2.x AA for normal text: the terminal's text is 13 to 18 px, never large.
AA = 4.5
# Below AA on purpose, each with the reason app.css gives beside it.
EXEMPT = {
    ("dark", "black"): "the background's own colour on a dark screen",
}


def _palette(theme: str) -> dict[str, str]:
    """The --term-* tokens of one theme's block, as written."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    selector = re.escape(THEMES[theme])
    block = re.search(r"(?:^|[}\s])" + selector + r"\s*\{([^{}]*)\}", css)
    assert block, f"no {THEMES[theme]} block in {CSS}"
    return dict(re.findall(r"--term-([a-z-]+)\s*:\s*([^;]+);", block.group(1)))


def _luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    assert re.fullmatch(r"[0-9a-fA-F]{6}", value), hex_colour

    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    light, dark = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_the_contrast_formula_matches_wcag():
    """A formula that returned the wrong scale would pass everything below."""
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#ffffff", "#ffffff") == pytest.approx(1.0)
    # WCAG's own boundary case: #767676 is the lightest grey that passes on white.
    assert contrast("#767676", "#ffffff") >= AA > contrast("#777777", "#ffffff")


@pytest.mark.parametrize("theme", THEMES)
def test_every_colour_is_defined_as_a_plain_hex(theme):
    """A colour a theme leaves out is drawn in xterm's own, which nothing here
    measures; a var() or color-mix() reaches xterm unresolved (app-infra.js
    reads the token as written)."""
    palette = _palette(theme)
    for name in ("bg", "fg", "selection", *ANSI):
        assert name in palette, f"{theme} theme has no --term-{name}"
        assert re.fullmatch(r"#[0-9a-fA-F]{6}", palette[name].strip()), (
            f"--term-{name} in the {theme} theme is {palette[name]!r}, not a #rrggbb colour"
        )


@pytest.mark.parametrize("theme", THEMES)
def test_every_foreground_reads_on_the_terminal_background(theme):
    palette = _palette(theme)
    background = palette["bg"].strip()
    below = []
    # A colour left out is the test above's failure, not this one's.
    for name in (n for n in ("fg", *ANSI) if n in palette):
        ratio = contrast(palette[name].strip(), background)
        if ratio < AA and (theme, name) not in EXEMPT:
            below.append(f"--term-{name} {palette[name].strip()}: {ratio:.2f}:1")
    listed = "\n  ".join(below)
    assert not below, f"{theme} terminal colours under {AA}:1 on {background}:\n  {listed}"


def test_an_exemption_is_still_needed():
    """An exempt colour that has since been raised should lose its exemption,
    or the list grows into a place to put anything that fails."""
    for theme, name in EXEMPT:
        palette = _palette(theme)
        assert contrast(palette[name].strip(), palette["bg"].strip()) < AA, (theme, name)


@pytest.mark.parametrize("theme", THEMES)
def test_selected_text_stays_readable(theme):
    palette = _palette(theme)
    assert contrast(palette["fg"].strip(), palette["selection"].strip()) >= AA


def test_the_terminal_reads_every_measured_colour():
    """What is measured here is what app-infra.js hands xterm: a token this
    test checks and the script never reads would prove nothing."""
    source = INFRA.read_text(encoding="utf-8")
    table = re.search(r"var _TERM_COLOURS = \{(.*?)\};", source, re.S)
    assert table, "_TERM_COLOURS not found in app-infra.js"
    read = set(re.findall(r":\s*'([a-z-]+)'", table.group(1)))
    assert {"bg", "fg", "selection", *ANSI} <= read
