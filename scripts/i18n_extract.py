#!/usr/bin/env python3
"""Move hard-coded UI text out of index.html and into ui_i18n.json.

The Norwegian never passes through a human's hands. It is read out of the file,
written to the language file byte for byte, and the element is tagged in place.
Every attempt at retyping it from a terminal listing has silently truncated a
clause, guessed the wrong HTML entity, or dropped a space that only shows up on
screen in a language nobody is testing in.

    scripts/i18n_extract.py list 1800 2000        # what is there
    scripts/i18n_extract.py plan 1800 2000 > b.tsv # key<TAB>Norwegian
    # add an English column to b.tsv, then:
    scripts/i18n_extract.py apply b.tsv

apply refuses to touch anything whose Norwegian no longer matches the file.
"""

from __future__ import annotations

import html as htmlmod
import json
import pathlib
import re
import sys

STATIC = pathlib.Path("app/web/static")
HTML = STATIC / "index.html"
I18N = STATIC / "ui_i18n.json"

# Elements whose whole content is one run of text can be tagged directly.
_SIMPLE = re.compile(
    r"<(label|option|button|p|div|span|h1|h2|h3|h4|strong|summary|td|th|li)"
    r"\b(?![^>]*data-i18n)([^>]*)>([^<>]*[A-Za-zÆØÅæøå][^<>]*)</\1>"
)


def _slug(text: str) -> str:
    words = re.findall(r"[a-zæøå]+", htmlmod.unescape(text).lower())
    return "_".join(words[:5])[:44] or "text"


def _translatable(text: str) -> bool:
    """The same definition the coverage test uses, imported rather than
    restated — two notions of "translatable" drift, and the one in the test is
    the one that decides whether the work counts."""
    sys.path.insert(0, ".")
    from tests.test_i18n_coverage import _NOT_TEXT, _NOT_TEXT_RE, _is_code

    plain = htmlmod.unescape(text).strip()
    if len(plain) < 2 or plain in _NOT_TEXT or _NOT_TEXT_RE.match(plain):
        return False
    return not _is_code(plain)


def _candidates(lo: int, hi: int):
    lines = HTML.read_text().split("\n")
    for n in range(lo, min(hi, len(lines)) + 1):
        for m in _SIMPLE.finditer(lines[n - 1]):
            raw = m.group(3)
            if raw.strip() and _translatable(raw):
                yield n, m.group(1), raw


def cmd_list(lo: int, hi: int) -> None:
    for n, tag, raw in _candidates(lo, hi):
        print(f"{n:5}  <{tag:<8}> {htmlmod.unescape(raw)[:70]}")


def cmd_plan(lo: int, hi: int) -> None:
    d = json.loads(I18N.read_text())
    seen: set[str] = set()
    for n, tag, raw in _candidates(lo, hi):
        key = _slug(raw)
        base, i = key, 2
        while key in d["no"] or key in seen:
            key = f"{base}_{i}"; i += 1
        seen.add(key)
        # Tab-separated so the Norwegian keeps every character it has.
        print(f"{key}\t{raw}\t")


def cmd_apply(path: str) -> None:
    rows = []
    for line in pathlib.Path(path).read_text().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3 or not parts[2].strip():
            print(f"skipping (no English): {parts[0] if parts else line[:40]}")
            continue
        rows.append((parts[0], parts[1], parts[2]))

    html = HTML.read_text()
    d = json.loads(I18N.read_text())
    applied = 0
    for key, no, en in rows:
        # Tag the element holding exactly this text, and only if it is still
        # there — a stale plan file must fail loudly rather than half-apply.
        pat = re.compile(
            r"(<(label|option|button|p|div|span|h1|h2|h3|h4|strong|summary|td|th|li)"
            r"\b(?![^>]*data-i18n)[^>]*?)(>)" + re.escape(no) + r"(</\2>)"
        )
        html, count = pat.subn(
            lambda m: f'{m.group(1)} data-i18n="{key}"{m.group(3)}{no}{m.group(4)}',
            html, count=1,
        )
        if not count:
            print(f"NOT FOUND, skipped: {key}  {no[:50]}")
            continue
        d["no"][key] = htmlmod.unescape(no).strip()
        d["en"][key] = en.strip()
        applied += 1

    # A space inside a translated span is erased by textContent replacement.
    html = re.sub(r'(<span data-i18n="[^"]+">)([^<]*?)(\s+)(</span>)', r"\1\2\4\3", html)
    html = re.sub(r'(<span data-i18n="[^"]+">)(\s+)([^<]*?)(</span>)', r"\2\1\3\4", html)

    HTML.write_text(html)
    I18N.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    print(f"applied {applied} of {len(rows)}")


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:]
    if cmd == "list":
        cmd_list(int(rest[0]), int(rest[1]))
    elif cmd == "plan":
        cmd_plan(int(rest[0]), int(rest[1]))
    elif cmd == "apply":
        cmd_apply(rest[0])
    else:
        sys.exit(__doc__)
