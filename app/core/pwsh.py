"""PowerShell 7 discovery.

The Microsoft 365 audit shells out to PowerShell 7 for the two things the
Graph API can't do on its own — Exchange Online collection and first-run app
registration. Both go through ``find_pwsh()``.

Deliberately detect-only: ``ensure_pwsh()`` reports what is missing and how
to install it rather than invoking a package manager itself. Installing
system packages from a web request would need root, would differ per distro,
and would be a surprising side effect of clicking "run setup" — the operator
should make that call.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path

log = logging.getLogger(__name__)

# Well-known install locations checked when `pwsh` isn't on PATH.
_CANDIDATES: dict[str, tuple[str, ...]] = {
    "Windows": (
        r"C:\Program Files\PowerShell\7\pwsh.exe",
        r"C:\Program Files (x86)\PowerShell\7\pwsh.exe",
    ),
    "Darwin": (
        "/usr/local/bin/pwsh",
        "/opt/homebrew/bin/pwsh",
    ),
    "Linux": (
        "/usr/bin/pwsh",
        "/usr/local/bin/pwsh",
        "/snap/bin/pwsh",
        "/opt/microsoft/powershell/7/pwsh",
    ),
}

INSTALL_HINT = (
    "PowerShell 7 is required for Exchange Online collection and first-run "
    "setup. Install it from https://aka.ms/install-powershell "
    "(Debian/Ubuntu: `sudo apt install powershell`, "
    "macOS: `brew install --cask powershell`, "
    "Arch: `yay -S powershell-bin`)."
)


def find_pwsh() -> str | None:
    """Return the path to the PowerShell 7 executable, or None.

    Checks ``$PWSH_PATH`` first so an operator can point at a non-standard
    install, then PATH, then the usual per-platform locations.
    """
    override = os.environ.get("PWSH_PATH")
    if override:
        if Path(override).is_file() and os.access(override, os.X_OK):
            return override
        log.warning("PWSH_PATH is set to %r but that is not an executable file", override)

    found = shutil.which("pwsh")
    if found:
        return found

    for candidate in _CANDIDATES.get(platform.system(), ()):
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate

    return None


def pwsh_available() -> bool:
    """True if PowerShell 7 can be located."""
    return find_pwsh() is not None


async def ensure_pwsh() -> AsyncGenerator[dict, None]:
    """Yield setup events describing PowerShell 7 availability.

    Yields a single ``ok`` event when pwsh is present, or a single ``error``
    event carrying install instructions when it isn't. The caller stops on
    the first ``error``.
    """
    exe = find_pwsh()
    if exe:
        yield {
            "step": "PwshInstall",
            "status": "ok",
            "msg": f"PowerShell 7 found at {exe}",
        }
        return

    log.warning("PowerShell 7 not found on this host")
    yield {
        "step": "PwshInstall",
        "status": "error",
        "msg": INSTALL_HINT,
    }
