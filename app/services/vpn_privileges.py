"""Describe whether this process may create host VPN interfaces.

The production service deliberately runs with ``NoNewPrivileges=yes`` and no
network-administration capability.  In that mode, trying ``sudo`` is not a
fallback: it can never succeed and only turns a deliberate security boundary
into confusing runtime failures.  Callers use this module to fail closed
before handling profile secrets or launching a VPN client.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.models.vpn import VpnProtocol

_CAP_NET_ADMIN = 12


def _linux_status_value(name: str) -> str | None:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator and key == name:
                return value.strip()
    except OSError:
        return None
    return None


def no_new_privileges_enabled() -> bool:
    """Return the kernel's no-new-privileges state for this process."""
    return _linux_status_value("NoNewPrivs") == "1"


def has_effective_cap_net_admin() -> bool:
    """Return whether CAP_NET_ADMIN is currently effective, not merely allowed."""
    if os.name != "posix":
        return False
    value = _linux_status_value("CapEff")
    if value is None:
        return False
    try:
        return bool(int(value, 16) & (1 << _CAP_NET_ADMIN))
    except ValueError:
        return False


def protocol_capability(protocol: VpnProtocol | str) -> dict[str, object]:
    """Return a JSON-safe capability decision for one VPN backend."""
    value = protocol.value if isinstance(protocol, VpnProtocol) else str(protocol)
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    net_admin = is_root or has_effective_cap_net_admin()

    if value == VpnProtocol.fortigate_ipsec.value:
        available = is_root
        requirement = "root"
    else:
        available = net_admin
        requirement = "CAP_NET_ADMIN"

    if available:
        reason = "Prosessen har nødvendige vertsrettigheter."
    else:
        reason = (
            "VPN styres eksternt på denne installasjonen. Sybr HUB mangler "
            f"{requirement} og vil ikke forsøke sudo. Etabler tunnelen utenfor webprosessen."
        )

    return {
        "available": available,
        "mode": "direct" if available else "external",
        "requirement": requirement,
        "reason": reason,
    }


def vpn_capabilities() -> dict[str, object]:
    """Return host-wide and per-protocol VPN control capabilities."""
    protocols = {
        protocol.value: protocol_capability(protocol)
        for protocol in (
            VpnProtocol.wireguard,
            VpnProtocol.openvpn,
            VpnProtocol.fortigate_ipsec,
            VpnProtocol.azure,
        )
    }
    return {
        "no_new_privileges": no_new_privileges_enabled(),
        "cap_net_admin": has_effective_cap_net_admin(),
        "protocols": protocols,
    }


def unavailable_reason(protocol: VpnProtocol | str) -> str | None:
    """Return a user-facing refusal, or None when direct control is available."""
    capability = protocol_capability(protocol)
    return None if capability["available"] else str(capability["reason"])
