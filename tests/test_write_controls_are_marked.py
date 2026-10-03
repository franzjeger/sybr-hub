"""A read-only account should not be offered what the server will refuse.

Two halves, and the split is the point.

`apiFetch` refuses a mutating call the account cannot make and says why. That
half cannot be forgotten, because every request in the interface goes through
it — which matters because most controls are built at runtime out of innerHTML
and there is no list of them to mark.

`data-write` hides the controls that live in the markup, so the interface does
not show a button whose only outcome is a toast. That half *can* be forgotten,
which is what this file is for: a control in index.html whose handler reaches a
write endpoint has to carry the attribute, and adding one without it fails
here rather than in front of a customer.
"""

from __future__ import annotations

import pathlib
import re

from app.web.middleware.write_guard import ALLOWED_WITHOUT_WRITE

STATIC = pathlib.Path("app/web/static")
SKIP = {"guacamole.min.js", "sw.js"}

_FUNCTION = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", re.M)
_MUTATING_CALL = re.compile(
    r"""(?:apiFetch|fetch)\(\s*['"`]([^'"`]+)['"`][^)]*?method\s*:\s*['"](\w+)['"]""", re.S
)
_HANDLER = re.compile(
    r"""<(\w+)((?:[^>"]|"[^"]*")*?)data-(?:click|change|submit)-handler\s*=\s*"([^"]*)"((?:[^>"]|"[^"]*")*?)>"""
)
# registerUiHandlers({ name: function(el, event) { ... }, ... }) in the scripts:
# what each named handler calls.
_REGISTRATION = re.compile(r"^registerUiHandlers\(\{\n(.*?)\n\}\);", re.S | re.M)
_ENTRY = re.compile(
    r"^  ([A-Za-z0-9_$]+): (function\b.*?)(?=^  [A-Za-z0-9_$]+: function\b|\Z)", re.S | re.M
)


def _is_exempt(path: str) -> bool:
    """Strip a concatenated id off the end before comparing."""
    return re.sub(r"'\s*\+.*$", "", path).rstrip("/") in ALLOWED_WITHOUT_WRITE


def write_functions() -> set[str]:
    """JS functions that issue a request the write guard would stop."""
    found: dict[str, set[str]] = {}
    for js in sorted(p for p in STATIC.glob("*.js") if p.name not in SKIP):
        src = js.read_text(encoding="utf-8")
        bounds = [(m.start(), m.group(1)) for m in _FUNCTION.finditer(src)] + [(len(src), None)]
        for call in _MUTATING_CALL.finditer(src):
            if call.group(2).upper() in {"GET", "HEAD"}:
                continue
            owner = next(
                (
                    name
                    for (start, name), (end, _) in zip(bounds, bounds[1:])
                    if start <= call.start() < end
                ),
                None,
            )
            if owner:
                found.setdefault(owner, set()).add(call.group(1).split("?")[0])
    return {fn for fn, paths in found.items() if not all(_is_exempt(p) for p in paths)}


def handler_bodies() -> dict[str, str]:
    """The source of every registered UI handler, by name."""
    bodies: dict[str, str] = {}
    for js in sorted(p for p in STATIC.glob("*.js") if p.name not in SKIP):
        for block in _REGISTRATION.findall(js.read_text(encoding="utf-8")):
            for name, body in _ENTRY.findall(block + "\n"):
                bodies[name] = body
    return bodies


def static_controls() -> list[tuple[int, str, set[str]]]:
    """(line, attributes, functions its handler calls) for each control in index.html."""
    bodies = handler_bodies()
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    out = []
    for m in _HANDLER.finditer(html):
        attrs = m.group(2) + m.group(4)
        called = set(re.findall(r"([A-Za-z_$][\w$]*)\s*\(", bodies.get(m.group(3), "")))
        out.append((html[: m.start()].count("\n") + 1, attrs, called))
    return out


def unmarked_controls() -> list[tuple[int, str]]:
    writers = write_functions()
    out = []
    for line, attrs, called in static_controls():
        if called & writers and "data-write" not in attrs:
            out.append((line, sorted(called & writers)[0]))
    return out


def test_the_controls_and_their_handlers_are_found():
    """If the markup or the handler map changes shape, the check below must not
    quietly start checking nothing."""
    writers = write_functions()
    controls = static_controls()
    assert len(controls) > 150
    assert sum(1 for _, _, called in controls if called & writers) > 40


def test_the_detector_finds_functions_that_write():
    """If this ever returns nothing the test below passes for the wrong reason."""
    assert len(write_functions()) > 50


def test_every_static_control_that_writes_is_marked():
    unmarked = unmarked_controls()

    assert not unmarked, (
        f"{len(unmarked)} controls in index.html call a write endpoint without "
        f"data-write, so a read-only account is offered them:\n"
        + "\n".join(f"  line {line}: {fn}()" for line, fn in unmarked)
    )


def test_the_marking_actually_hides_something():
    """The attribute is inert without the rule that acts on it."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "app.css").read_text(encoding="utf-8")

    assert "body.is-readonly [data-write]" in css
    assert html.count("data-write") > 40


def test_the_client_does_not_keep_its_own_copy_of_the_exemptions():
    """It is sent by /auth/me.

    A second copy goes stale in the direction of offering something the server
    refuses. Checked by where the variable is *assigned* rather than by looking
    for the paths themselves — those appear all over app.js as call sites,
    which is what an earlier version of this test could not tell apart.
    """
    # Any script may assign it; app-state.js is the one that does.
    app_js = "\n".join(path.read_text(encoding="utf-8") for path in sorted(STATIC.glob("app*.js")))

    assignments = re.findall(r"_writeExempt\s*=\s*([^;\n]+)", app_js)

    assert assignments, "_writeExempt is never assigned — the gate cannot work"
    for value in assignments:
        assert value.strip() in ("[]", "me.write_exempt"), (
            f"_writeExempt assigned {value.strip()!r} — the list must come from "
            f"/auth/me, not from a literal the server never sees"
        )


def test_the_server_sends_the_list_it_enforces():
    """The same object, not a parallel one."""
    source = pathlib.Path("app/web/routes/auth.py").read_text(encoding="utf-8")

    assert "ALLOWED_WITHOUT_WRITE" in source, "/auth/me should serve the middleware's own set"
