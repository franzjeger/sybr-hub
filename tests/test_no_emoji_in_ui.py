"""Emoji stay out of user-visible text.

A previous pass removed 84 and left 171, because it searched for the ones
somebody had noticed. Most of the survivors were written as HTML numeric
escapes — ``&#128203;`` is a clipboard, and no literal search will ever see it.

This checks Unicode ranges instead, in both spellings, so the next one cannot
hide the same way.

Monochrome affordances are not decoration and stay: ✕ closes, ☰ opens a menu,
▶ starts, ★/☆ is a toggle, the arrows say which way a column is sorted. The
rule is whether the glyph is a control or an ornament, and the allowlist below
is the whole of it.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "app/web/static", ROOT / "app/reports/templates"]
# Vendored bundles are not ours to edit, and xterm draws terminal box
# characters that are the whole point of a terminal.
SKIP_SUFFIX = ".min.js"
SUFFIXES = {".js", ".html", ".j2"}
COMMENT = re.compile(r"^\s*(//|/\*|\*|#|\{#)")
ESCAPE = re.compile(r"&#(\d+);|&#x([0-9a-fA-F]+);")

# Controls, not ornaments.
ALLOWED = {
    0x2715, 0x2716, 0x2717, 0x2718,   # ✕ ✖ close / fail
    0x2630,                            # ☰ menu
    0x25B6, 0x25C0,                    # ▶ ◀ start
    0x2190, 0x2191, 0x2192, 0x2193,    # ← ↑ → ↓
    0x2B06, 0x2B07,                    # ⬆ ⬇ sort
    0x2196, 0x2197, 0x2198, 0x2199,    # ↗ external link
    0x21BA, 0x21BB, 0x27F3,            # ↻ refresh
    0x21C4, 0x21C6, 0x2944,            # ⇄ compare
    0x21A9, 0x21AA,                    # ↩ return
    0x290A, 0x290B, 0x2913,            # ⤓ collapse
    0x21C8, 0x21CA,                    # ⇈ ⇊
    0x2733,                            # ✳
    0x2713, 0x2714,                    # ✓
    0x2605, 0x2606,                    # ★ ☆ favourite
    0x2318, 0x2325, 0x2303, 0x21E7,    # ⌘ ⌥ ⌃ ⇧ — keys on the reader's keyboard
    0x2022, 0x00D7, 0x2014, 0x2013, 0x00B7, 0x2265, 0x2264,
}
PICTOGRAPHIC = [
    (0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF),
    (0x2190, 0x21FF), (0x2300, 0x23FF), (0x20E3, 0x20E3), (0xFE0F, 0xFE0F),
]


def _is_ornament(cp: int) -> bool:
    if cp in ALLOWED:
        return False
    return any(lo <= cp <= hi for lo, hi in PICTOGRAPHIC)


def _files() -> list[Path]:
    out: list[Path] = []
    for root in SOURCES:
        out += [
            p for p in sorted(root.rglob("*"))
            if p.is_file() and p.suffix in SUFFIXES and not p.name.endswith(SKIP_SUFFIX)
        ]
    return out


def _offences(path: Path) -> list[str]:
    found: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if COMMENT.match(line):
            continue  # a comment recording what was removed is not a rendering
        for ch in line:
            if _is_ornament(ord(ch)):
                found.append(f"{path.name}:{lineno} {ch!r}")
        for m in ESCAPE.finditer(line):
            cp = int(m.group(1)) if m.group(1) else int(m.group(2), 16)
            if cp > 0x2000 and _is_ornament(cp):
                try:
                    name = unicodedata.name(chr(cp))
                except ValueError:
                    name = "?"
                found.append(f"{path.name}:{lineno} {m.group(0)} ({name})")
    return found


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name)
def test_no_emoji_in_user_visible_text(path):
    offences = _offences(path)
    assert not offences, (
        f"{len(offences)} emoji left in {path.name}:\n  " + "\n  ".join(offences[:20])
    )


def test_the_escaped_spelling_is_actually_checked():
    # The hole the last sweep fell through. If this stops detecting, the whole
    # file goes quiet without failing.
    assert _is_ornament(0x1F4CB), "&#128203; is a clipboard and must be caught"
    assert not _is_ornament(0x2713), "✓ is not an ornament"


def test_the_allowlist_is_not_a_backdoor():
    # Anything genuinely pictographic must not be sitting in ALLOWED.
    for cp in ALLOWED:
        assert not (0x1F300 <= cp <= 0x1FAFF), f"U+{cp:04X} is an emoji, not a control"


def test_a_control_that_lost_its_glyph_got_a_label():
    # Emptying a button is not removing an emoji, it is removing the button.
    js = (ROOT / "app/web/static/app.js").read_text(encoding="utf-8")
    for dead in ('title="${t(\'btn_delete\')}"></button>',
                 'title="${t(\'btn_copy_to_clipboard\')}"></button>'):
        assert dead not in js, "a button was left with no label at all"
