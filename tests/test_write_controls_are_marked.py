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

_FUNCTION = re.compile(r"^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", re.M)
_MUTATING_CALL = re.compile(
    r"""(?:apiFetch|fetch)\(\s*['"`]([^'"`]+)['"`][^)]*?method\s*:\s*['"](\w+)['"]""", re.S
)
_HANDLER = re.compile(
    r"""<(\w+)((?:[^>"]|"[^"]*")*?)on(?:click|change|submit)\s*=\s*"([^"]*)"((?:[^>"]|"[^"]*")*?)>"""
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
                (name for (start, name), (end, _) in zip(bounds, bounds[1:])
                 if start <= call.start() < end),
                None,
            )
            if owner:
                found.setdefault(owner, set()).add(call.group(1).split("?")[0])
    return {fn for fn, paths in found.items() if not all(_is_exempt(p) for p in paths)}


def unmarked_controls() -> list[tuple[int, str]]:
    writers = write_functions()
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    out = []
    for m in _HANDLER.finditer(html):
        attrs = m.group(2) + m.group(4)
        called = set(re.findall(r"([A-Za-z_$][\w$]*)\s*\(", m.group(3)))
        if called & writers and "data-write" not in attrs:
            out.append((html[: m.start()].count("\n") + 1, sorted(called & writers)[0]))
    return out


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
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")

    assignments = re.findall(r"_writeExempt\s*=\s*([^;\n]+)", app_js)

    assert assignments, "_writeExempt is never assigned — the gate cannot work"
    for value in assignments:
        assert value.strip() in ("[]", "_me.write_exempt"), (
            f"_writeExempt assigned {value.strip()!r} — the list must come from "
            f"/auth/me, not from a literal the server never sees"
        )


def test_the_server_sends_the_list_it_enforces():
    """The same object, not a parallel one."""
    source = pathlib.Path("app/web/routes/auth.py").read_text(encoding="utf-8")

    assert "ALLOWED_WITHOUT_WRITE" in source, (
        "/auth/me should serve the middleware's own set"
    )
