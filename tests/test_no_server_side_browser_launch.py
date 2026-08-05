"""The server must not try to open a browser for the operator.

/api/open-private ran subprocess.Popen on the server, walking a list of
browser paths and launching the first it found with --private-window. The
server is headless and the technician is on another machine, so it opened a
window nobody could see and then reported which browser it had used —
"Firefox (privat)" being the browser the *server* had installed.

It was also remote process execution reachable by any authenticated user,
for a feature that never worked. Opening a tab belongs in the page.
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
    js = "\n".join(
        p.read_text(encoding="utf-8") for p in STATIC.glob("app*.js")
    )
    # A comment may name the endpoint it replaced; a fetch may not.
    called = re.findall(r"""(?:apiFetch|fetch)\(\s*['"][^'"]*open-private""", js)
    assert not called, "the page still calls the removed endpoint"


def test_the_page_opens_the_tab_itself():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    body = re.search(r"function openPrivateBrowser\(\)\s*\{.*?\n\}", js, re.S)
    assert body, "openPrivateBrowser is gone"
    assert "window.open(" in body.group(0), (
        "the sign-in URL is not opened in the operator's own browser"
    )


def test_the_ui_does_not_promise_a_private_window():
    """A page cannot open one, so the button must not say it does."""
    import json

    d = json.loads((STATIC / "ui_i18n.json").read_text(encoding="utf-8"))
    for lang in ("no", "en"):
        label = d[lang].get("btn_open_private_window_label", "")
        assert "privat" not in label.lower() and "private" not in label.lower(), (
            f"{lang} button label still claims a private window: {label!r}"
        )
        assert d[lang].get("setup_private_hint"), (
            f"{lang} has no hint telling the reader to open a private window themselves"
        )
