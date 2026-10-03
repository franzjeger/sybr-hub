"""MSP Toolkit — Textual application root."""

from __future__ import annotations

from typing import ClassVar

from textual.app import App
from textual.binding import Binding

from app.ui.screens.home import HomeScreen


class MSPToolkitApp(App):
    """Main application."""

    TITLE = "MSP Toolkit"
    CSS_PATH = None  # Inline CSS only

    CSS = """
    Screen {
        background: #0d1117;
    }
    """

    BINDINGS: ClassVar[list] = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False),
    ]

    SCREENS: ClassVar[dict] = {
        "home": HomeScreen,
    }

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())
