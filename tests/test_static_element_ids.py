"""JavaScript must not dereference an element id that nothing ever creates.

``document.getElementById('x').value`` throws ``Cannot read properties of null``
when the markup no longer has ``x``, and it throws on the *first* such line —
taking down every branch below it. That is how a valid UniFi Site Manager API
key came to fail with a null-property error: the handler read two account
fields that had been dropped from the card before it reached the key.

Two shapes are checked. The blunt one — ``getElementById('x').y`` on a single
line. And the one that hid behind the first version of this file: assigning to a
variable and dereferencing it further down, which crashes just as hard. That was
left out as needing "more than a regex"; it needed one more regex, and four real
cases were sitting in it, two of them crashes reachable from a Back button.

A lookup guarded by ``if (el)`` passes either way. A guarded lookup of an id
nothing creates is not a crash — but it is a feature that silently never runs,
so those are reported separately rather than ignored.
"""

from __future__ import annotations

import pathlib
import re

STATIC = pathlib.Path(__file__).resolve().parents[1] / "app/web/static"
VENDORED = {"guacamole.min.js"}

# Known-crashing lookups, kept as an explicit list so the set may shrink and
# never grow — the same ratchet scripts/lint_budget.py applies to lint debt.
# Empty, and the second test below keeps it that way by failing on a stale
# entry. Adding one is a deliberate act that has to be argued for in review.
KNOWN_BROKEN: set[str] = set()


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


def _assigned_then_dereferenced() -> dict[str, str]:
    """Ids bound to a variable and dereferenced later, with no guard between.

    ``var el = getElementById('x'); ... el.innerHTML = …`` crashes exactly as
    ``getElementById('x').innerHTML`` does. Telling it apart from a guarded use
    only takes looking for ``if (el)`` in the lines that follow.
    """
    found: dict[str, str] = {}
    for path in sorted(STATIC.glob("*.js")):
        if path.name in VENDORED:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            m = re.search(
                r"""(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*"""
                r"""document\.getElementById\(\s*['"]([^'"]+)['"]\s*\)\s*;""",
                line,
            )
            if not m:
                continue
            var, element_id = m.group(1), m.group(2)
            if re.search(rf"if\s*\(\s*!?\s*{re.escape(var)}\b", "\n".join(lines[i + 1:i + 4])):
                continue
            if re.search(rf"\b{re.escape(var)}\s*\.", "\n".join(lines[i + 1:i + 40])):
                found.setdefault(element_id, f"{path.name}:{i + 1}")
    return found


def test_no_javascript_dereferences_a_variable_holding_a_missing_element():
    created = _created_ids()
    crashing = {
        name: where
        for name, where in _assigned_then_dereferenced().items()
        if name not in created and name not in KNOWN_BROKEN
    }
    assert not crashing, (
        "JavaScript binds an element id nothing creates and dereferences it, "
        "which throws at runtime: "
        + ", ".join(f"{n} ({w})" for n, w in sorted(crashing.items()))
    )
