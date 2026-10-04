"""The server must not try to open a browser for the operator.

/api/open-private ran subprocess.Popen on the server, walking a list of
browser paths and launching the first it found with --private-window. The
server is headless and the technician is on another machine, so it opened a
window nobody could see and then reported which browser it had used —
"Firefox (privat)" being the browser the *server* had installed.

It was also remote process execution reachable by any authenticated user,
for a feature that never worked. Opening a tab belongs in the page.

The page's replacement went with the device-code sign-in it served: setup
signs in with PKCE now, where the operator copies the link into a private
window of their own, so no button claims to open one.
"""

from __future__ import annotations

import pathlib
import re

ROUTES = pathlib.Path("app/web/routes")
STATIC = pathlib.Path("app/web/static")


def test_no_route_launches_a_browser_process():
    for py in ROUTES.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        for browser in ("--private-window", "--incognito", "--inprivate"):
            assert browser not in src, f"{py.name} launches a browser with {browser}"


def test_the_open_private_endpoint_is_gone():
    src = "\n".join(p.read_text(encoding="utf-8") for p in ROUTES.rglob("*.py"))
    assert "/open-private" not in src, "the server-side launcher is still routed"
    js = "\n".join(p.read_text(encoding="utf-8") for p in STATIC.glob("app*.js"))
    # A comment may name the endpoint it replaced; a fetch may not.
    called = re.findall(r"""(?:apiFetch|fetch)\(\s*['"][^'"]*open-private""", js)
    assert not called, "the page still calls the removed endpoint"
