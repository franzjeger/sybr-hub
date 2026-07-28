"""Audit orchestrator — coordinates M365, FortiGate, and UniFi audit modules.

Determines which modules to run based on customer configuration,
creates a shared output directory, and merges all results.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.modules.base import ProgressCallback, SectionResult, SectionStatus

log = logging.getLogger(__name__)


def get_enabled_modules(config: dict) -> list[str]:
    """Return list of module names that are configured for a customer.

    Checks which credentials/hosts are present in the customer config.
    """
    modules = []
    if config.get("TenantId") and config.get("ClientId"):
        modules.append("m365")
    if config.get("FortiGateHost"):
        modules.append("fortigate")
    if config.get("UniFiHost") or config.get("UniFiDirectDevices"):
        modules.append("unifi")
    return modules


def get_all_section_names() -> dict[str, list[dict]]:
    """Return all available sections grouped by module, for scope selector UI."""
    return {
        "m365": [
            # Existing M365 sections — populated dynamically by AuditCollector
        ],
        "fortigate": [
            {"name": "FortiGate System Info", "category": "FortiGate"},
            {"name": "FortiGate Admin Security", "category": "FortiGate"},
            {"name": "FortiGate Interfaces & Zones", "category": "FortiGate"},
            {"name": "FortiGate Firewall Policies", "category": "FortiGate"},
            {"name": "FortiGate VPN", "category": "FortiGate"},
            {"name": "FortiGate Security Profiles", "category": "FortiGate"},
            {"name": "FortiGate Logging", "category": "FortiGate"},
            {"name": "FortiGate High Availability", "category": "FortiGate"},
            {"name": "FortiGate Network Services", "category": "FortiGate"},
        ],
        "unifi": [
            {"name": "UniFi Sites Overview", "category": "UniFi"},
            {"name": "UniFi Devices & Firmware", "category": "UniFi"},
            {"name": "UniFi Wireless Security", "category": "UniFi"},
            {"name": "UniFi Networks & VLANs", "category": "UniFi"},
            {"name": "UniFi Firewall Rules", "category": "UniFi"},
            {"name": "UniFi Threat Management", "category": "UniFi"},
            {"name": "UniFi Clients & Traffic", "category": "UniFi"},
            {"name": "UniFi Admin & Settings", "category": "UniFi"},
        ],
    }
