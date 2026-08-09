"""Every URL the frontend calls resolves to a route the backend registers.

A typo here is invisible until someone clicks. `/api/remediation/update` never
existed — the route is `/api/remediation` and takes exactly the body the caller
was sending — so saving a remediation status did nothing but raise a toast.
`/api/customers/active` never existed either.

The parsing has to read the *whole* concatenated expression. A first attempt
truncated at the first `+`, which turned `/api/baselines/default/evaluate/' +
id + '/latest` into a two-segment path that matched nothing, and produced nine
false positives against two real bugs. A check that cries wolf gets muted.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app/web/static"
ROUTES = ROOT / "app/web/routes"
VENDORED = {"guacamole.min.js"}

# The router is mounted under /api, but frontend.py registers its own paths
# with the prefix already on them. Both spellings are accepted.
_PARAM = re.compile(r"\{[^}]+\}")


def _registered() -> set[str]:
    routes: set[str] = set()
    for path in sorted(ROUTES.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for _verb, route in re.findall(
            r"""@router\.(get|post|put|patch|delete|websocket)\(\s*["']([^"']+)""", text
        ):
            route = _PARAM.sub("*", route).rstrip("/")
            routes.add(route)
            routes.add(route[4:] if route.startswith("/api/") else "/api" + route)
    return routes


def _called() -> dict[str, str]:
    """URL literals passed to apiFetch, with interpolated parts as ``*``."""
    calls: dict[str, str] = {}
    for path in sorted(STATIC.glob("*.js")):
        if path.name in VENDORED:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in re.finditer(r"apiFetch\(", line):
                # Read the first argument whole, to the comma or closing paren
                # that ends it, so a concatenation is not mistaken for the end.
                rest, depth, arg = line[m.end():], 0, []
                for ch in rest:
                    if ch in "([{":
                        depth += 1
                    elif ch in ")]}":
                        if depth == 0:
                            break
                        depth -= 1
                    elif ch == "," and depth == 0:
                        break
                    arg.append(ch)
                expr = "".join(arg)
                if "/api/" not in expr:
                    continue
                # Quoted runs are literal; every gap between or after them is
                # a value. Treating only the gaps *between* them as wildcards
                # loses the segment on `'/api/x/' + id`, which is most of them.
                pieces, last, saw = [], 0, False
                for q in re.finditer(r"""['"]([^'"]*)['"]""", expr):
                    if saw and expr[last:q.start()].strip():
                        pieces.append("*")
                    pieces.append(q.group(1))
                    last, saw = q.end(), True
                if not saw:
                    continue
                if expr[last:].strip():
                    pieces.append("*")
                url = "".join(pieces)
                url = url.split("?")[0].split("#")[0]
                if not url.startswith("/api/"):
                    continue
                url = re.sub(r"\*+", "*", url).rstrip("/")
                url = re.sub(r"/\*(?=/|$)", "/*", url)
                calls.setdefault(url, f"{path.name}:{lineno}")
    return calls


def _matches(call: str, registered: set[str]) -> bool:
    if call in registered:
        return True
    parts = call.split("/")
    for route in registered:
        rparts = route.split("/")
        if len(rparts) != len(parts):
            continue
        if all(r == "*" or c == "*" or r == c for r, c in zip(rparts, parts, strict=True)):
            return True
    return False


def test_every_apifetch_url_has_a_route():
    registered = _registered()
    missing = {
        call: where
        for call, where in _called().items()
        if not _matches(call, registered)
    }
    assert not missing, (
        "the frontend calls URLs no route serves: "
        + ", ".join(f"{c} ({w})" for c, w in sorted(missing.items()))
    )


def test_the_parser_keeps_the_tail_after_an_interpolation():
    # The failure that made the first version of this useless: everything after
    # the first `+` was dropped, so a real four-segment path looked like two.
    calls = _called()
    assert any(c.endswith("/latest") or "/evaluate/" in c for c in calls), (
        "no interpolated URL kept its trailing segments — the parser truncated"
    )
