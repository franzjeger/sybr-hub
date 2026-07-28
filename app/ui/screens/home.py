"""Home screen — module selector."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static

_BANNER = """\
 ███╗   ███╗███████╗██████╗     ████████╗ ██████╗  ██████╗ ██╗      ██╗  ██╗██╗████████╗
 ████╗ ████║██╔════╝██╔══██╗    ╚══██╔══╝██╔═══██╗██╔═══██╗██║      ██║ ██╔╝██║╚══██╔══╝
 ██╔████╔██║███████╗██████╔╝       ██║   ██║   ██║██║   ██║██║      █████╔╝ ██║   ██║
 ██║╚██╔╝██║╚════██║██╔═══╝        ██║   ██║   ██║██║   ██║██║      ██╔═██╗ ██║   ██║
 ██║ ╚═╝ ██║███████║██║            ██║   ╚██████╔╝╚██████╔╝███████╗ ██║  ██╗██║   ██║
 ╚═╝     ╚═╝╚══════╝╚═╝            ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝ ╚═╝  ╚═╝╚═╝   ╚═╝"""

_SUBTITLE = "Professional IT Management Platform  •  v0.1.0"


class ModuleCard(Static):
    """Clickable module card."""

    DEFAULT_CSS = """
    ModuleCard {
        border: solid #2d3748;
        padding: 1 3;
        margin: 0 0 1 0;
        background: #161b22;
        color: #c9d1d9;
    }
    ModuleCard:hover {
        border: solid #3b82f6;
        background: #1c2435;
        color: white;
    }

    ModuleCard.unavailable {
        color: #4a5568;
    }
    ModuleCard .module-icon  { color: #3b82f6; }
    ModuleCard .module-title { text-style: bold; }
    ModuleCard .module-badge { color: #4a5568; text-style: italic; }
    """

    def __init__(self, key: str, icon: str, title: str, description: str, available: bool = True):
        super().__init__()
        self.key         = key
        self.icon        = icon
        self.title_text  = title
        self.description = description
        self.is_available = available
        if not available:
            self.add_class("unavailable")
        else:
            self.add_class("available")

    def compose(self) -> ComposeResult:
        badge = "" if self.is_available else "  [coming soon]"
        yield Label(f"  {self.icon}  [{self.key}]  {self.title_text}{badge}")
        yield Label(f"       {self.description}", classes="module-desc")

    def on_click(self) -> None:
        if self.is_available:
            self.app.post_message(ModuleSelected(self.key))


class ModuleSelected(Message):
    """Posted when a module is selected."""
    def __init__(self, key: str):
        super().__init__()
        self.key = key


class HomeScreen(Screen):
    """Main menu screen."""

    BINDINGS = [
        Binding("1", "select_m365",       "M365 Audit",     show=False),
        Binding("2", "select_fortigate",  "FortiGate",      show=False),
        Binding("3", "select_unifi",      "UniFi",          show=False),
        Binding("q", "quit_app",          "Quit",           show=True),
        Binding("ctrl+c", "quit_app",     "Quit",           show=False),
    ]

    DEFAULT_CSS = """
    HomeScreen {
        background: #0d1117;
        align: center middle;
    }

    #banner {
        color: #3b82f6;
        text-align: center;
        padding: 2 0 0 0;
    }

    #subtitle {
        color: #8b949e;
        text-align: center;
        padding: 0 0 2 0;
    }

    #modules-container {
        width: 80;
        padding: 1 2;
    }

    #modules-label {
        color: #58a6ff;
        text-style: bold;
        padding: 1 0;
    }

    #divider {
        color: #21262d;
        padding: 0 0 1 0;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Static(_BANNER,    id="banner"),
            Static(_SUBTITLE,  id="subtitle"),
            Vertical(
                Label("  Select a module:", id="modules-label"),
                Label("  " + "─" * 60, id="divider"),
                ModuleCard("1", "🔍", "M365 + Azure Full Audit",
                           "Audit tenant, Exchange, Intune, SharePoint, Azure"),
                ModuleCard("2", "🔥", "Fortigate Configuration",
                           "Audit and configure Fortigate firewalls via REST API"),
                ModuleCard("3", "📡", "Unifi AP Setup",
                           "Configure Unifi access points via SSH + best-practice templates"),
                Label("  " + "─" * 60),
                Label("  [Q] Quit", id="quit-label"),
                id="modules-container",
            ),
            id="home-container",
        )
        yield Footer()

    def action_select_m365(self) -> None:
        from app.ui.screens.customer_setup import CustomerSetupScreen
        self.app.push_screen(CustomerSetupScreen())

    def _open_web_module(self, tab: str) -> None:
        """Open a module in the web UI browser."""
        import webbrowser

        from app.core.config import load_app_settings
        settings = load_app_settings()
        port = settings.get("web_port", 8000)
        webbrowser.open(f"http://localhost:{port}/#{tab}")

    def action_select_fortigate(self) -> None:
        self._open_web_module("infra")

    def action_select_unifi(self) -> None:
        self._open_web_module("infra")

    def action_quit_app(self) -> None:
        self.app.exit()

    def on_module_selected(self, event: ModuleSelected) -> None:
        if event.key == "1":
            self.action_select_m365()
        elif event.key == "2":
            self.action_select_fortigate()
        elif event.key == "3":
            self.action_select_unifi()
