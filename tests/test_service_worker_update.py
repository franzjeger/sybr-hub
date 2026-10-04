"""A deploy does not reload the operator's open tabs on its own.

Every deploy that changes a static file changes sw.js, because its cache
version is a digest of the assets. The worker called skipWaiting() on
install, so it took over at once and every open tab reloaded, ending any
terminal or RDP session in it. Now it waits for the operator to accept the
update, and only the tab that accepted reloads.
"""

from __future__ import annotations

import pathlib
import re

STATIC = pathlib.Path(__file__).resolve().parent.parent / "app/web/static"


def _listener(source: str, event: str) -> str:
    start = source.index(f"self.addEventListener('{event}'")
    return source[start : source.index("\n});", start)]


def test_a_new_worker_does_not_take_over_on_install():
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    assert "skipWaiting" not in _listener(sw, "install")
    # It still can, when the page asks on the operator's behalf.
    assert "skipWaiting" in _listener(sw, "message")


def test_only_the_tab_that_accepted_reloads():
    chrome = (STATIC / "app-chrome.js").read_text(encoding="utf-8")
    handler = chrome[chrome.index("addEventListener('controllerchange'") :]
    handler = handler[: handler.index("\n  });")]
    assert re.search(r"if \(_swUpdateAccepted\) \{ location\.reload\(\); return; \}", handler)


def test_notification_permission_is_not_asked_on_page_load():
    chrome = (STATIC / "app-chrome.js").read_text(encoding="utf-8")
    top_level = [ln for ln in chrome.splitlines() if ln.startswith("if (") and "Notification" in ln]
    assert not top_level
    audit = (STATIC / "app-audit.js").read_text(encoding="utf-8")
    start = audit[audit.index("async function startAudit(") :][:600]
    assert "requestAuditNotifications()" in start


def test_the_worker_keeps_every_file_the_offline_page_loads():
    """Offline, the worker answers a page load with offline.html from its cache.

    The page's stylesheet and script are fetched under their bare URLs, so the
    worker has them only if it stored them at install. A file added to the
    offline page and not to PRECACHE would be missing exactly when it is
    needed.
    """
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    offline_page = re.search(r"const OFFLINE_PAGE = '([^']+)'", sw).group(1)
    precache = re.search(r"const PRECACHE = \[([^\]]*)\]", sw).group(1)
    stored = set(re.findall(r"'(/static/[^']+)'", precache))
    if "OFFLINE_PAGE" in precache:
        stored.add(offline_page)
    page = (STATIC / "offline.html").read_text(encoding="utf-8")
    loads = set(re.findall(r'(?:href|src)="(/static/[^"]+)"', page))
    assert offline_page == "/static/offline.html"
    assert stored == loads | {offline_page}
