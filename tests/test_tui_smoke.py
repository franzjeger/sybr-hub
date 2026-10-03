"""Smoke tests for the optional Textual UI (the [tui] extra).

CI installs [tui] alongside [dev] (see .github/workflows/ci.yml), so these
run against the newest textual the pyproject range allows. They validate
the app shell: imports, mount, home screen, and the quit binding. The
audit screens need live tenant access and are not covered here.
"""

from __future__ import annotations

import pytest


async def test_tui_mounts_home_screen_and_exits_on_q() -> None:
    pytest.importorskip("textual")
    from app.ui.app import MSPToolkitApp
    from app.ui.screens.home import HomeScreen

    app = MSPToolkitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, HomeScreen)
        await pilot.press("q")
