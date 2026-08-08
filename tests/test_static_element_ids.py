"""JavaScript must not dereference an element id that nothing ever creates.

``document.getElementById('x').value`` throws ``Cannot read properties of null``
when the markup no longer has ``x``, and it throws on the *first* such line —
taking down every branch below it. That is how a valid UniFi Site Manager API
key came to fail with a null-property error: the handler read two account
fields that had been dropped from the card before it reached the key.

A lookup kept behind ``if (el)`` is fine and not counted. Only an immediate
dereference is, because only that one crashes.
"""

from __future__ import annotations

import pathlib
import re

STATIC = pathlib.Path(__file__).resolve().parents[1] / "app/web/static"
VENDORED = {"guacamole.min.js"}

# Known-crashing lookups, kept as an explicit list so the set may shrink and
# never grow — the same ratchet scripts/lint_budget.py applies to lint debt.
# These three are the Sybrt AI card: its customer picker and reply pane are
# read but never rendered, so those handlers throw the moment they run.
KNOWN_BROKEN = {
    "ai-customer-list",
    "ai-customer-search",
    "ai-reply-text",
}


def _created_ids() -> set[str]:
    """Every id assigned in markup or built by a JS template string."""
    created: set[str] = set()
    for path in list(STATIC.glob("*.html")) + list(STATIC.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        created.update(re.findall(r"""id\s*=\s*\\?['"]([A-Za-z0-9_:-]+)""", text))
        # An id assembled by concatenation, e.g. id="row-' + i + '"
        created.update(re.findall(r"""id\s*=\s*\\?['"]([A-Za-z0-9_:-]+)['"]?\s*\+""", text))
    return created


def _immediately_dereferenced() -> dict[str, str]:
    """Ids whose lookup is dereferenced on the spot, mapped to where."""
    found: dict[str, str] = {}
    for path in sorted(STATIC.glob("*.js")):
        if path.name in VENDORED:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for name in re.findall(
                r"""getElementById\(\s*['"]([^'"]+)['"]\s*\)\s*\.""", line
            ):
                found.setdefault(name, f"{path.name}:{lineno}")
    return found


def test_no_new_javascript_reads_a_nonexistent_element():
    created = _created_ids()
    crashing = {
        name: where
        for name, where in _immediately_dereferenced().items()
        if name not in created
    }
    new = {n: w for n, w in crashing.items() if n not in KNOWN_BROKEN}
    assert not new, (
        "JavaScript dereferences element ids that nothing creates, which throws "
        "at runtime: " + ", ".join(f"{n} ({w})" for n, w in sorted(new.items()))
    )


def test_the_known_broken_list_does_not_go_stale():
    """A fixed entry must leave the list, or it stops meaning anything."""
    created = _created_ids()
    crashing = set(_immediately_dereferenced()) - created
    fixed = KNOWN_BROKEN - crashing
    assert not fixed, (
        "These no longer crash and should be removed from KNOWN_BROKEN: "
        + ", ".join(sorted(fixed))
    )
