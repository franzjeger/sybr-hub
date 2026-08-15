"""Describe whether this process may run raw-socket network scans.

nmap's SYN (``-sS``), FIN/stealth (``-sF``) and OS-detection modes need raw
sockets — root or ``CAP_NET_RAW``. The production service runs with
``NoNewPrivileges=yes`` and no such capability, so those modes cannot work.
As with VPN (see ``app.services.vpn_privileges``), ``sudo`` is not a fallback:
under ``NoNewPrivileges`` it can never succeed and only turns a deliberate
boundary into confusing failures. Callers use this module to decide, before
building an nmap command line, whether a raw scan is possible — and if not, to
fall back to an unprivileged TCP connect scan or refuse a raw-only mode with a
clear reason, never to attempt elevation.
"""

from __future__ import annotations

import os

from app.services.vpn_privileges import _linux_status_value, no_new_privileges_enabled

# CAP_NET_RAW — the capability nmap needs to build raw packets for -sS/-sF/-O.
_CAP_NET_RAW = 13


def _status_cap_set(field: str, bit: int) -> bool:
    """Return whether *bit* is set in a /proc/self/status capability *field*."""
    value = _linux_status_value(field)
    if value is None:
        return False
    try:
        return bool(int(value, 16) & (1 << bit))
    except ValueError:
        return False


def has_effective_cap_net_raw() -> bool:
    """Return whether CAP_NET_RAW is effective in THIS process."""
    if os.name != "posix":
        return False
    return _status_cap_set("CapEff", _CAP_NET_RAW)


def has_ambient_cap_net_raw() -> bool:
    """Return whether CAP_NET_RAW is in the ambient set.

    A non-root binary exec'd without file capabilities inherits only the
    *ambient* set — not the parent's effective caps — so this, not CapEff, is
    what predicts whether the spawned nmap child can raw-scan.
    """
    if os.name != "posix":
        return False
    return _status_cap_set("CapAmb", _CAP_NET_RAW)


def _cap_permitted_has_net_raw(blob: bytes) -> bool:
    """Parse a ``security.capability`` xattr and test its permitted CAP_NET_RAW.

    struct vfs_cap_data is little-endian: ``__le32 magic_etc`` then
    ``permitted_lo`` at byte offset 4 (same for v2 and v3). CAP_NET_RAW (13) is
    in the low 32-bit word.
    """
    import struct
    if len(blob) < 8:
        return False
    permitted_lo = struct.unpack_from("<I", blob, 4)[0]
    return bool(permitted_lo & (1 << _CAP_NET_RAW))


def _nmap_binary_grants_net_raw() -> bool:
    """True if the nmap binary itself would give its child CAP_NET_RAW on exec.

    Only valid when NoNewPrivileges is NOT enforced — under NNP the kernel
    suppresses both file capabilities and setuid, so this must not be consulted
    there. A file capability (``setcap cap_net_raw+ep nmap``) or a setuid-root
    nmap is the documented way to grant a non-root user raw scans, and the child
    obtains the capability regardless of the parent's ambient set.
    """
    import shutil
    import stat
    path = shutil.which("nmap")
    if not path:
        return False
    try:
        st = os.stat(path)
        if (st.st_mode & stat.S_ISUID) and st.st_uid == 0:
            return True
    except OSError:
        return False
    try:
        blob = os.getxattr(path, "security.capability")   # Linux only
    except (OSError, AttributeError):
        return False
    return _cap_permitted_has_net_raw(blob)


def raw_scan_available() -> bool:
    """True when a spawned nmap could actually run a raw-socket scan.

    Root is NOT taken as proof: a container/pod that runs the service as root
    but drops NET_RAW (``--cap-drop=NET_RAW``) has euid 0 yet cannot raw-scan,
    so for root we require the capability to still be effective. A non-root
    child inherits the ambient set on exec, so there we require CAP_NET_RAW to
    be ambient — merely effective in the web process would not reach the child.
    When NoNewPrivileges is not enforced, a privileged nmap *binary* (file cap
    or setuid-root) also reaches the child, so we honour that too (SR-006 review).
    """
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    if is_root:
        return has_effective_cap_net_raw()
    if has_ambient_cap_net_raw():
        return True
    if not no_new_privileges_enabled():
        return _nmap_binary_grants_net_raw()
    return False


def scan_capability() -> dict[str, object]:
    """Return a JSON-safe decision on what scan modes this process can run.

    ``mode`` is ``"raw"`` when SYN/stealth/OS scans are possible, else
    ``"connect"`` — the unprivileged TCP connect scan the web process falls
    back to. ``reason`` is a user-facing explanation for the ``connect`` case.
    """
    available = raw_scan_available()
    if available:
        reason = "Prosessen har CAP_NET_RAW og kan kjøre SYN-, stealth- og OS-skann."
    else:
        reason = (
            "Denne installasjonen kjører uten CAP_NET_RAW/root, så SYN-, stealth- "
            "og OS-skann er avslått. Sybr HUB bruker TCP connect-skann i stedet og "
            "forsøker aldri sudo. For raw-skann: gi tjenesten CAP_NET_RAW bevisst "
            "(AmbientCapabilities=CAP_NET_RAW) eller kjør skannet utenfor webprosessen."
        )
    return {
        "available": available,
        "mode": "raw" if available else "connect",
        "requirement": "CAP_NET_RAW",
        "reason": reason,
        "no_new_privileges": no_new_privileges_enabled(),
    }


def raw_only_unavailable_reason() -> str | None:
    """Return a refusal for a raw-only scan mode, or None when raw is available."""
    capability = scan_capability()
    return None if capability["available"] else str(capability["reason"])
