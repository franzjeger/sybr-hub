"""Customer setup screen — first-run and returning customer handling."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Log, Static


class CustomerSetupScreen(Screen):
    """
    Handles:
    - Returning customer detection (config found)
    - First-run setup flow
    - Credential renewal
    - Navigation to audit run
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
    ]

    DEFAULT_CSS = """
    CustomerSetupScreen {
        background: #0d1117;
    }

    #header-box {
        background: #161b22;
        border-bottom: solid #21262d;
        padding: 1 3;
        color: #c9d1d9;
    }

    #customer-info {
        color: #58a6ff;
        text-style: bold;
    }

    #expiry-warn {
        color: #f0883e;
    }

    #action-buttons {
        padding: 2 3;
        height: auto;
    }

    Button {
        margin: 0 1 1 0;
        min-width: 30;
    }

    Button.primary  { background: #1f6feb; color: white; }
    Button.danger   { background: #da3633; color: white; }
    Button.warning  { background: #9e6a03; color: white; }
    Button.default  { background: #21262d; color: #c9d1d9; }

    #setup-log {
        border: solid #21262d;
        background: #161b22;
        margin: 1 3;
        height: 1fr;
    }

    #device-code-box {
        background: #161b22;
        border: solid #3b82f6;
        padding: 1 3;
        margin: 1 3;
        display: none;
    }

    #device-code-box.visible {
        display: block;
    }

    #code-label {
        color: #f0f6fc;
        text-style: bold;
    }

    #url-label {
        color: #58a6ff;
    }

    Footer {
        background: #161b22;
    }
    """

    def __init__(self):
        super().__init__()
        self._config: Optional[dict] = None
        self._mode: str = "unknown"   # "returning" | "first_run"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Static("", id="header-box"),
            Static("", id="device-code-box"),
            Vertical(id="action-buttons"),
            Log(id="setup-log", auto_scroll=True),
            id="main-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._load_state()

    def _load_state(self) -> None:
        from app.core.credentials import config_exists, load_config
        header_box  = self.query_one("#header-box",     Static)
        action_area = self.query_one("#action-buttons", Vertical)

        if config_exists():
            cfg = load_config()
            self._config = cfg
            self._mode   = "returning"

            name   = cfg.get("CustomerName", "Unknown")
            domain = cfg.get("PrimaryDomain", "")
            setup  = cfg.get("SetupDate", "")[:10]

            # Expiry checks
            warns = []
            secret_exp = cfg.get("SecretExpiry", "")
            cert_exp   = cfg.get("CertExpiry",   "")

            def days_left(iso: str) -> Optional[int]:
                if not iso:
                    return None
                try:
                    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                    return (dt - datetime.now(timezone.utc)).days
                except ValueError:
                    return None

            sd = days_left(secret_exp)
            cd = days_left(cert_exp)
            if sd is not None and sd < 30:
                warns.append(f"⚠  Client secret expires in {sd} days!")
            if cd is not None and cd < 30:
                warns.append(f"⚠  Certificate expires in {cd} days!")

            warn_text = "\n".join(warns) if warns else ""

            header_box.update(
                f"  Saved configuration found:\n"
                f"  Customer : [bold cyan]{name}[/bold cyan]  ({domain})\n"
                f"  Set up   : {setup}\n"
                + (f"\n  [bold yellow]{warn_text}[/bold yellow]" if warn_text else "")
            )

            action_area.mount(
                Button("▶  Run Audit",              id="btn-run",    classes="primary"),
                Button("🔄  New Customer",           id="btn-new",    classes="default"),
                Button("🔑  Renew Credentials",      id="btn-renew",  classes="warning"),
                Button("✕  Back",                   id="btn-back",   classes="default"),
            )

        else:
            self._mode = "first_run"
            header_box.update(
                "  No saved configuration found.\n"
                "  First-run setup will:\n"
                "    1. Authenticate as Global Admin (browser / device code)\n"
                "    2. Create an App Registration + API permissions\n"
                "    3. Generate a certificate for Exchange Online\n"
                "    4. Assign Azure Reader role\n"
                "    5. Save credentials securely"
            )
            action_area.mount(
                Button("▶  Start Setup", id="btn-setup", classes="primary"),
                Button("✕  Back",        id="btn-back",  classes="default"),
            )

    # ── Button handlers ───────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if   bid == "btn-run":   self._launch_audit()
        elif bid == "btn-new":   self._confirm_new_customer()
        elif bid == "btn-renew": self._renew_credentials()
        elif bid == "btn-setup": self.run_worker(self._run_setup(), exclusive=True)
        elif bid == "btn-back":  self.action_go_back()

    def _launch_audit(self) -> None:
        from app.ui.screens.audit_run import AuditRunScreen
        self.app.push_screen(AuditRunScreen())

    def _confirm_new_customer(self) -> None:
        from app.core.credentials import load_config, wipe_customer
        cfg = load_config()
        if cfg:
            wipe_customer(cfg.get("TenantId", ""))
        self._refresh_screen()

    def _renew_credentials(self) -> None:
        from app.core.credentials import delete_cert, delete_config, load_config
        cfg = load_config()
        if cfg:
            from app.core.credentials import delete_all_secrets
            delete_all_secrets(cfg.get("TenantId", ""))
        delete_config()
        delete_cert()
        self._refresh_screen()

    def _refresh_screen(self) -> None:
        # Re-mount the screen fresh
        self.app.pop_screen()
        self.app.push_screen(CustomerSetupScreen())

    def action_go_back(self) -> None:
        self.app.pop_screen()

    # ── First-run setup flow ──────────────────────────────────────────────────

    async def _run_setup(self) -> None:
        from app.modules.m365_audit.setup import FirstRunSetup

        log = self.query_one("#setup-log", Log)
        log.write_line("Starting first-run setup...\n")

        # Disable buttons during setup
        for btn in self.query("Button"):
            btn.disabled = True

        def on_device_code(user_code: str, url: str) -> None:
            box = self.query_one("#device-code-box", Static)
            box.update(
                f"\n  [bold]Browser login required[/bold]\n\n"
                f"  1. Open:  [bold cyan]{url}[/bold cyan]\n"
                f"  2. Enter code:  [bold yellow]{user_code}[/bold yellow]\n"
                f"  3. Sign in as [bold]Global Admin[/bold]\n\n"
                f"  Waiting for authentication..."
            )
            box.add_class("visible")
            # Open URL in private/incognito browser window
            import shutil
            import subprocess
            import sys
            try:
                if sys.platform == "darwin":
                    for app_path in ["/Applications/Google Chrome.app", "/Applications/Microsoft Edge.app"]:
                        if Path(app_path).exists():
                            flag = "--incognito" if "Chrome" in app_path else "--inprivate"
                            subprocess.Popen(["open", "-na", app_path, "--args", flag, url])
                            break
                    else:
                        subprocess.Popen(["open", url])
                elif sys.platform == "win32":
                    edge = shutil.which("msedge") or r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
                    if Path(edge).exists():
                        subprocess.Popen([edge, "--inprivate", url])
                    else:
                        import webbrowser
                        webbrowser.open(url)
                else:
                    chrome = shutil.which("google-chrome") or shutil.which("chromium-browser")
                    if chrome:
                        subprocess.Popen([chrome, "--incognito", url])
                    else:
                        subprocess.Popen(["xdg-open", url])
            except Exception:
                pass  # Fallback: user opens manually

        setup = FirstRunSetup(on_device_code=on_device_code)

        success = True
        async for event in setup.run():
            step   = event["step"]
            status = event["status"]
            msg    = event["msg"]

            icon = {"ok": "✓", "warn": "⚠", "error": "✗"}.get(status, "•")
            log.write_line(f"  {icon}  [{step}] {msg}")

            if status == "error":
                success = False
                log.write_line("\n  ✗ Setup failed. Check the error above and try again.")
                break

        # Hide device code box
        box = self.query_one("#device-code-box", Static)
        box.remove_class("visible")

        if success:
            log.write_line("\n  ✓ Setup complete! You can now run the audit.")
            await asyncio.sleep(1.5)
            self._refresh_screen()
        else:
            # Re-enable buttons on failure
            for btn in self.query("Button"):
                btn.disabled = False
