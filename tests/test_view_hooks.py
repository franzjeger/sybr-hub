"""showView is one function; views hook in instead of wrapping it.

Two scripts replaced the global showView with a wrapper that called the one
before it. Wrappers stack in load order, and a throw in one cuts off every
wrapper after it. A script that owns a view registers its loader with
onViewShown(name, fn) instead.
"""

from __future__ import annotations

import pathlib
import re

STATIC = pathlib.Path(__file__).resolve().parent.parent / "app/web/static"


def test_no_script_reassigns_show_view():
    offenders = [
        f"{path.name}:{n}"
        for path in sorted(STATIC.glob("*.js"))
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"(?<![\w.])showView\s*=(?!=)", line)
    ]
    assert not offenders, f"showView reassigned at {offenders}; use onViewShown(name, fn)"


def test_the_integrations_views_still_load_when_opened():
    source = (STATIC / "app-integrations.js").read_text(encoding="utf-8")
    for view in ("hosts", "vpn", "tailscale", "pentest", "docs"):
        assert f"onViewShown('{view}'" in source, view


def test_tls_monitor_loads_as_a_tab_of_nettverk():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "if (tabId === 'net-tls') tlsLoadView();" in source


def test_administrasjon_loads_when_opened():
    """The settings modal and the Integrasjoner view became one page."""
    source = (STATIC / "app-settings.js").read_text(encoding="utf-8")
    assert "onViewShown('admin'" in source
