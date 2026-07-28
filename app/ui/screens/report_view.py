"""Report view screen — shown after audit, before/after report generation."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static


class ReportViewScreen(Screen):
    """Post-audit: shows warning summary and report export options."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
    ]

    DEFAULT_CSS = """
    ReportViewScreen { background: #0d1117; }

    #title       { color: #58a6ff; text-style: bold; padding: 1 3; background: #161b22; border-bottom: solid #21262d; }
    #warn-box    { margin: 1 3; border: solid #9e6a03; background: #161b22; padding: 1 2; }
    #warn-title  { color: #f0883e; text-style: bold; }
    #buttons     { padding: 1 3; }
    Button       { margin: 0 1; min-width: 22; }
    Button.primary { background: #1f6feb; color: white; }
    Button.success { background: #196127; color: white; }
    Button.default { background: #21262d; color: #c9d1d9; }
    """

    def __init__(self, out_dir: Path, warn_files: list[str]):
        super().__init__()
        self._out_dir    = out_dir
        self._warn_files = warn_files

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Static(f"  Audit complete — {self._out_dir.name}", id="title"),
            self._build_warn_box(),
            Horizontal(
                Button("📄  HTML Report",  id="btn-html",  classes="success"),
                Button("📑  PDF Report",   id="btn-pdf",   classes="success"),
                Button("📂  Open Folder",  id="btn-folder",classes="default"),
                Button("✕  Close",         id="btn-back",  classes="default"),
                id="buttons",
            ),
            id="container",
        )
        yield Footer()

    def _build_warn_box(self) -> Static:
        if not self._warn_files:
            return Static("  ✓ No warnings detected.", id="warn-box")
        lines = [f"  ⚠ {len(self._warn_files)} warning file(s) detected:"]
        for wf in self._warn_files:
            lines.append(f"    → {wf}")
        return Static("\n".join(lines), id="warn-box")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if   bid == "btn-html":   self._export("html")
        elif bid == "btn-pdf":    self._export("pdf")
        elif bid == "btn-folder": self._open_folder()
        elif bid == "btn-back":   self.action_go_back()

    def _export(self, fmt: str) -> None:
        # Delegate back to app — results are held in AuditRunScreen
        self.app.pop_screen()

    def _open_folder(self) -> None:
        import subprocess
        import sys
        folder = str(self._out_dir)
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", folder])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            pass

    def action_go_back(self) -> None:
        self.app.pop_screen()
