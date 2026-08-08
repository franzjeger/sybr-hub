"""Make the remaining CSP attribute exceptions a shrinking migration budget."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path("app/web/static")
SOURCES = [*STATIC.glob("*.html"), *STATIC.glob("*.js")]

# The inherited single-page UI generates substantial markup in JavaScript.
# CSP now distinguishes attributes from executable elements, and these budgets
# prevent the temporary attribute exceptions from becoming permanent growth.
INLINE_EVENT_HANDLER_BUDGET = 834
INLINE_STYLE_ATTRIBUTE_BUDGET = 4631


def _count(pattern: str) -> int:
    return sum(
        len(re.findall(pattern, path.read_text(encoding="utf-8"), flags=re.IGNORECASE))
        for path in SOURCES
    )


def test_static_shells_have_no_inline_script_or_style_elements():
    for path in STATIC.glob("*.html"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\bsrc\s*=)[^>]*>", source, re.I), path
        assert not re.search(r"<style(?:\s|>)", source, re.I), path


def test_inline_event_handler_debt_cannot_grow():
    count = _count(r"\bon[a-z]+\s*=")
    assert count <= INLINE_EVENT_HANDLER_BUDGET, (
        f"inline event-handler debt grew: {count} > {INLINE_EVENT_HANDLER_BUDGET}"
    )


def test_inline_style_attribute_debt_cannot_grow():
    count = _count(r"\bstyle\s*=")
    assert count <= INLINE_STYLE_ATTRIBUTE_BUDGET, (
        f"inline style debt grew: {count} > {INLINE_STYLE_ATTRIBUTE_BUDGET}"
    )
