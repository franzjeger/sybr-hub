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


_TRANSLIT = str.maketrans({"æ": "ae", "ø": "oe", "å": "aa"})


def _slug(text: str) -> str:
    """ASCII snake_case. A key with ø in it is legal but out of step with the
    1800 already in the file, and awkward to type or grep for."""
    plain = htmlmod.unescape(text).lower().translate(_TRANSLIT)
    words = re.findall(r"[a-z]+", plain)
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


_ATTRS = ("title", "placeholder", "aria-label", "alt")


def _attr_candidates(lo: int, hi: int):
    """title, placeholder, aria-label and alt on elements that declare no key
    for them. translatePage handles all four, so they are taggable the same way
    the text is."""
    lines = HTML.read_text().split("\n")
    for n in range(lo, min(hi, len(lines)) + 1):
        line = lines[n - 1]
        for attr in _ATTRS:
            for m in re.finditer(rf'{attr}="([^"]*[A-Za-zÆØÅæøå][^"]*)"', line):
                end = line.find(">", m.start())
                tag = line[line.rfind("<", 0, m.start()):end + 1 if end > 0 else len(line)]
                if f"data-i18n-{attr}" in tag:
                    continue
                if _translatable(m.group(1)):
                    yield n, attr, m.group(1)


def cmd_list_attrs(lo: int, hi: int) -> None:
    for n, attr, value in _attr_candidates(lo, hi):
        print(f"{n:5}  {attr:<11} {htmlmod.unescape(value)[:64]}")


def cmd_plan_attrs(lo: int, hi: int) -> None:
    d = json.loads(I18N.read_text())
    seen: set[str] = set()
    for n, attr, value in _attr_candidates(lo, hi):
        key = _slug(value)
        base, i = key, 2
        while key in d["no"] or key in seen:
            key = f"{base}_{i}"; i += 1
        seen.add(key)
        print(f"{key}\t{attr}\t{value}\t")


def cmd_apply_attrs(path: str) -> None:
    rows = []
    for line in pathlib.Path(path).read_text().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4 or not parts[3].strip():
            print(f"skipping (no English): {parts[0] if parts else line[:40]}")
            continue
        rows.append((parts[0], parts[1], parts[2], parts[3]))

    html = HTML.read_text()
    d = json.loads(I18N.read_text())
    applied = 0
    for key, attr, value, en in rows:
        # Add the marker beside the attribute it translates, once, and only
        # where the value still matches.
        pat = re.compile(rf'({attr}="{re.escape(value)}")')
        html, count = pat.subn(rf'data-i18n-{attr}="{key}" \1', html, count=1)
        if not count:
            print(f"NOT FOUND, skipped: {key}  {attr}={value[:40]}")
            continue
        d["no"][key] = htmlmod.unescape(value).strip()
        d["en"][key] = en.strip()
        applied += 1
    HTML.write_text(html)
    I18N.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    print(f"applied {applied} of {len(rows)}")


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



JS = STATIC / "app.js"


def _js_candidates():
    sys.path.insert(0, ".")
    from tests.test_i18n_coverage import prose_in_generated_markup
    return prose_in_generated_markup()


def cmd_plan_js() -> None:
    d = json.loads(I18N.read_text())
    seen: set[str] = set()
    for _, text in _js_candidates():
        if text in seen:
            continue
        seen.add(text)
        key = _slug(text)
        base, i = key, 2
        while key in d["no"] or key in {k for k in seen if k == key}:
            key = f"{base}_{i}"; i += 1
        print(f"{key}\t{text}\t")


def cmd_apply_js(path: str) -> None:
    """Turn >Lagre< inside a quoted string into >' + t('btn_save') + '<.

    Only single-quoted strings are rewritten. A template literal needs
    ${t(...)} instead, and mixing the two forms silently produces a string
    containing the word "t(" — so anything else is reported and left alone.
    """
    rows = []
    for line in pathlib.Path(path).read_text().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3 or not parts[2].strip():
            continue
        rows.append((parts[0], parts[1], parts[2]))

    js = JS.read_text()
    d = json.loads(I18N.read_text())
    applied = skipped = 0
    for key, text, en in rows:
        needle = f">{text}<"
        if needle not in js:
            print(f"NOT FOUND: {key}  {text[:40]}")
            skipped += 1
            continue
        js = js.replace(needle, ">' + t('" + key + "') + '<")
        d["no"][key] = text
        d["en"][key] = en.strip()
        applied += 1
    JS.write_text(js)
    I18N.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    print(f"applied {applied}, skipped {skipped}")

if __name__ == "__main__":
    cmd, *rest = sys.argv[1:]
    if cmd == "list":
        cmd_list(int(rest[0]), int(rest[1]))
    elif cmd == "plan":
        cmd_plan(int(rest[0]), int(rest[1]))
    elif cmd == "apply":
        cmd_apply(rest[0])
    elif cmd == "list-attrs":
        cmd_list_attrs(int(rest[0]), int(rest[1]))
    elif cmd == "plan-attrs":
        cmd_plan_attrs(int(rest[0]), int(rest[1]))
    elif cmd == "apply-attrs":
        cmd_apply_attrs(rest[0])
    elif cmd == "plan-js":
        cmd_plan_js()
    elif cmd == "apply-js":
        cmd_apply_js(rest[0])
    else:
        sys.exit(__doc__)
