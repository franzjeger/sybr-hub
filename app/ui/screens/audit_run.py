"""Audit run screen — live progress table + completion actions."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    ProgressBar,
    Static,
)

from app.modules.base import SectionResult, SectionStatus


# Posted by worker thread to update progress table
class SectionUpdate:
    def __init__(self, name: str, status: SectionStatus, detail: Optional[str] = None):
        self.name   = name
        self.status = status
        self.detail = detail or ""


class AuditRunScreen(Screen):
    """Shows live audit progress and provides post-audit actions."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=False),
    ]

    DEFAULT_CSS = """
    AuditRunScreen {
        background: #0d1117;
    }

    #title-bar {
        background: #161b22;
        border-bottom: solid #21262d;
        padding: 1 3;
        color: #58a6ff;
        text-style: bold;
    }

    #progress-area {
        padding: 1 3 0 3;
        height: auto;
    }

    #overall-label {
        color: #8b949e;
        padding: 0 0 1 0;
    }

    ProgressBar {
        width: 100%;
    }

    DataTable {
        margin: 1 3;
        border: solid #21262d;
        background: #161b22;
        height: 1fr;
    }

    #action-row {
        padding: 1 3;
        height: auto;
    }

    Button {
        margin: 0 1;
        min-width: 25;
    }

    Button.primary { background: #1f6feb; color: white; }
    Button.success { background: #196127; color: white; }
    Button.default { background: #21262d; color: #c9d1d9; }

    #status-footer {
        background: #161b22;
        padding: 0 3;
        color: #8b949e;
        height: 1;
    }

    Footer { background: #161b22; }
    """

    def __init__(self):
        super().__init__()
        self._results:        list[SectionResult] = []
        self._out_dir:        Optional[Path]       = None
        self._audit_running:  bool                  = False
        self._total_sections  = 20   # approximate
        self._done_count      = 0
        self._row_keys:       dict[str, str]        = {}   # name -> row_key

    def _on_mount(self, event) -> None:
        # Textual 8.x + Python 3.14: screen_layout_refresh_signal.subscribe
        # raises SignalError if is_running is False (interactive mode timing).
        # AuditRunScreen doesn't use tooltips so missing this subscription is safe.
        if self.is_running:
            super()._on_mount(event)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Static("", id="title-bar"),
            Vertical(
                Label("", id="overall-label"),
                ProgressBar(total=self._total_sections, id="progress-bar", show_eta=False),
                id="progress-area",
            ),
            DataTable(id="section-table", cursor_type="none"),
            Horizontal(
                Button("📄  HTML Report",  id="btn-html",  classes="success",  disabled=True),
                Button("📑  PDF Report",   id="btn-pdf",   classes="success",  disabled=True),
                Button("📂  Open Folder",  id="btn-folder",classes="default",  disabled=True),
                Button("✕  Back",          id="btn-back",  classes="default"),
                id="action-row",
            ),
            Static("", id="status-footer"),
            id="main-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._setup_table()
        self._setup_title()
        self.run_worker(self._run_audit(), exclusive=True)

    def _setup_title(self) -> None:
        from app.core.credentials import load_config
        cfg  = load_config() or {}
        name = cfg.get("CustomerName", "Unknown Customer")
        ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self.query_one("#title-bar", Static).update(
            f"  🔍  M365 + Azure Audit  •  {name}  •  {ts}"
        )

    def _setup_table(self) -> None:
        table = self.query_one("#section-table", DataTable)
        table.add_columns("", "Section", "Status", "Files", "Notes")
        table.zebra_stripes = True

    # ── Audit worker ──────────────────────────────────────────────────────────

    async def _run_audit(self) -> None:
        from app.core.credentials import load_config
        from app.modules.m365_audit.auth import AuthError, AuthManager
        from app.modules.m365_audit.collector import AuditCollector, make_output_dir

        self._audit_running = True
        self._set_status("Connecting...")

        try:
            auth     = AuthManager.from_config()
            cfg      = load_config()
            out_dir  = make_output_dir(cfg.get("CustomerName", "Unknown"))
            self._out_dir = out_dir

            collector = AuditCollector(
                auth        = auth,
                out_dir     = out_dir,
                progress_cb = self._on_section_progress,
            )

            self._set_status("Audit running...")
            results = await collector.run()
            self._results = results

            self._on_audit_complete()

        except Exception as e:
            self._set_status(f"Error: {e}")
            self._add_row("ERROR", "Audit failed", SectionStatus.FAILED, [], str(e))

        finally:
            self._audit_running = False

    # ── Progress callback (called from collector, may be threaded) ────────────

    def _on_section_progress(
        self,
        name:   str,
        status: SectionStatus,
        detail: Optional[str],
    ) -> None:
        """Called by audit sections to report progress. Thread-safe via call_from_thread."""
        self.call_from_thread(self._update_section_row, name, status, detail or "")

    def _update_section_row(self, name: str, status: SectionStatus, detail: str) -> None:
        table  = self.query_one("#section-table", DataTable)
        icon   = {
            SectionStatus.PENDING:  "⏳",
            SectionStatus.RUNNING:  "⚡",
            SectionStatus.DONE:     "✓",
            SectionStatus.SKIPPED:  "→",
            SectionStatus.FAILED:   "✗",
        }[status]

        status_text = {
            SectionStatus.PENDING:  "Pending",
            SectionStatus.RUNNING:  "Running...",
            SectionStatus.DONE:     "Done",
            SectionStatus.SKIPPED:  "Skipped",
            SectionStatus.FAILED:   "Failed",
        }[status]

        if name in self._row_keys:
            rk = self._row_keys[name]
            table.update_cell(rk, "")          # icon col
            table.update_cell(rk, status_text)
        else:
            rk = table.add_row(icon, name, status_text, "-", detail[:60] if detail else "")
            self._row_keys[name] = rk

        if status in (SectionStatus.DONE, SectionStatus.SKIPPED, SectionStatus.FAILED):
            self._done_count += 1
            pb = self.query_one("#progress-bar", ProgressBar)
            pb.advance(1)
            self.query_one("#overall-label", Label).update(
                f"  Progress: {self._done_count} / {self._total_sections} sections"
            )

    def _add_row(self, icon: str, name: str, status: SectionStatus, files: list, detail: str) -> None:
        table = self.query_one("#section-table", DataTable)
        table.add_row(icon, name, status.name, str(len(files)), detail[:60])

    # ── Completion ────────────────────────────────────────────────────────────

    def _on_audit_complete(self) -> None:
        warns  = sum(1 for r in self._results if r.has_warnings)
        failed = sum(1 for r in self._results if r.status == SectionStatus.FAILED)

        self._set_status(
            f"✓ Audit complete — "
            f"{len(self._results)} sections, "
            f"{warns} with warnings, "
            f"{failed} failed"
        )

        # Enable action buttons
        self.query_one("#btn-html",   Button).disabled = False
        self.query_one("#btn-pdf",    Button).disabled = False
        self.query_one("#btn-folder", Button).disabled = False

    def _set_status(self, msg: str) -> None:
        self.query_one("#status-footer", Static).update(f"  {msg}")

    # ── Button handlers ───────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if   bid == "btn-html":   self.run_worker(self._gen_report(["html"]))
        elif bid == "btn-pdf":    self.run_worker(self._gen_report(["html", "pdf"]))
        elif bid == "btn-folder": self._open_folder()
        elif bid == "btn-back":   self.action_go_back()

    async def _gen_report(self, formats: list[str]) -> None:
        if not self._out_dir:
            return
        self._set_status("Generating report...")

        from app.core.credentials import load_config
        from app.reports.generator import generate_reports

        cfg = load_config() or {}
        try:
            output = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: generate_reports(
                    customer_name = cfg.get("CustomerName", "Unknown"),
                    org_domain    = cfg.get("PrimaryDomain", ""),
                    out_dir       = self._out_dir,
                    results       = self._results,
                    formats       = formats,
                )
            )
            paths = ", ".join(str(p.name) for p in output.values())
            self._set_status(f"✓ Report saved: {paths}")
        except Exception as e:
            self._set_status(f"✗ Report error: {e}")

    def _open_folder(self) -> None:
        import subprocess
        import sys
        if not self._out_dir:
            return
        folder = str(self._out_dir)
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", folder])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            self._set_status(f"Folder: {folder}")

    def action_go_back(self) -> None:
        if not self._audit_running:
            self.app.pop_screen()
