"""The devices the Hub knows for a customer, for the RMM deep-link.

The Hub has no device inventory of its own. What it has is the newest finished
audit run: Intune's managed devices (``10_intune_devices.json``, with the Wi-Fi
MAC address on runs from October 2026) and the devices registered in Entra ID
(``15_entra_devices.json``). Those two lists are the hub devices the RMM page
matches; a device the audit never saw is not on it.

The two lists overlap, since an Intune-managed device is also registered in
Entra. They are merged by whole name, compared without regard to case: one row
per host name, its sources named, Intune's spelling and operating system kept
where both have it. That merge is the Hub's own list, not a match against the
RMM; the RMM still has to agree on exactly one device for the name.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.integrations.rmm import HubDevice, normalise_mac, on_agent_platform

logger = logging.getLogger(__name__)

_SOURCES = (("intune", "10_intune_devices.json"), ("entra", "15_entra_devices.json"))


def latest_finished_run(customer: dict[str, Any]) -> Path | None:
    """The customer's newest run that finished (it holds its metrics)."""
    from app.core.config import get_audit_dir
    from app.core.customer import customer_dir_name

    root = get_audit_dir() / customer_dir_name(customer.get("CustomerName", ""))
    if not root.is_dir():
        return None
    for run in sorted((d for d in root.iterdir() if d.is_dir()), reverse=True):
        if (run / "_audit_metrics.json").exists():
            return run
    return None


def _read(run: Path, filename: str) -> list[dict[str, Any]] | None:
    """The sidecar's device list, or None when the run has no readable one."""
    path = run / filename
    if not path.is_file():
        return None
    try:
        from app.core.encryption import encrypted_read_json

        data = encrypted_read_json(path)
    except Exception:
        logger.warning("Could not read %s in %s", filename, run.name)
        return None
    devices = data.get("devices") if isinstance(data, dict) else None
    return [d for d in devices if isinstance(d, dict)] if isinstance(devices, list) else None


def hub_devices(run: Path) -> list[HubDevice] | None:
    """The run's devices an RMM agent could be on, merged by name.

    None when the run carries neither device list (the sections failed, or the
    run predates the sidecars): no list is not an empty list.
    """
    merged: dict[str, dict[str, Any]] = {}
    read_any = False
    for source, filename in _SOURCES:
        listed = _read(run, filename)
        if listed is None:
            continue
        read_any = True
        for raw in listed:
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            row = merged.setdefault(
                name.casefold(), {"name": name, "os": "", "sources": [], "macs": []}
            )
            if not row["os"]:
                row["os"] = str(raw.get("os") or "")
            if source not in row["sources"]:
                row["sources"].append(source)
            mac = normalise_mac(str(raw.get("wifi_mac") or ""))
            if mac and mac not in row["macs"]:
                row["macs"].append(mac)
    if not read_any:
        return None
    return [
        HubDevice(
            name=row["name"],
            os=row["os"],
            sources=tuple(row["sources"]),
            macs=tuple(row["macs"]),
        )
        for row in sorted(merged.values(), key=lambda r: str(r["name"]).casefold())
        if on_agent_platform(row["os"])
    ]
