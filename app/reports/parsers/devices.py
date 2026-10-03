"""Parsers for the Intune and Entra ID device registers."""

from __future__ import annotations

from app.reports.evidence import _evidence_unavailable
from app.reports.parsers.common import _first_prose_line


def _parse_entra_devices(count_text: str, detail_text: str, sidecar: dict | None = None) -> dict:
    """The directory's own device register, beside the Intune one.

    Its whole purpose is the gap between the two counts: devices the tenant
    has, minus devices Intune manages, is the unmanaged-endpoint finding. With
    only the Intune figure, a tenant with forty joined machines and no
    enrolment read as "no devices found".

    ``sidecar`` is 15_entra_devices.json when the run wrote one; its counts are
    read instead of the text. A refused read writes no sidecar.
    """
    result = {
        "total": 0,
        "managed": 0,
        "unmanaged": 0,
        "enabled": 0,
        "has_data": False,
        "unavailable": False,
        "unavailable_reason": "",
    }
    if sidecar is not None:
        for key in ("total", "managed", "unmanaged", "enabled"):
            result[key] = int(sidecar.get(key) or 0)
        result["has_data"] = True
        return result
    if _evidence_unavailable(count_text) and _evidence_unavailable(detail_text):
        if (count_text or detail_text or "").strip():
            result["unavailable"] = True
            result["unavailable_reason"] = _first_prose_line(detail_text) or _first_prose_line(
                count_text
            )
        return result

    for line in (count_text or "").splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower()
        try:
            v = int(val.strip())
        except ValueError:
            continue
        if key in ("total", "managed", "unmanaged", "enabled"):
            result[key] = v
            result["has_data"] = True
    if not result["has_data"] and "ENTRA REGISTERED DEVICES" in (detail_text or ""):
        result["has_data"] = True
    return result


def _parse_intune_devices(count_text: str, detail_text: str, sidecar: dict | None = None) -> dict:
    """The Intune register. ``sidecar`` is 10_intune_devices.json when the run
    wrote one, read instead of the two text files; a refused read writes none."""
    result = {
        "total": 0,
        "windows": 0,
        "ios": 0,
        "android": 0,
        "macos": 0,
        "compliant": 0,
        "noncompliant": 0,
        "unknown": 0,
        "compliance_pct": 0.0,
        "devices": [],
        "unavailable": False,
        "unavailable_reason": "",
    }

    if sidecar is not None:
        for key in ("total", "windows", "ios", "android", "macos"):
            result[key] = int(sidecar.get(key) or 0)
        for key in ("compliant", "noncompliant", "unknown"):
            result[key] = int(sidecar.get(key) or 0)
        result["compliance_pct"] = float(sidecar.get("compliance_pct") or 0.0)
        result["devices"] = [
            {
                "name": d.get("name") or "",
                "os": d.get("os") or "",
                "user": d.get("owner") or "",
                "compliance": d.get("compliance") or "",
                "enrolled": d.get("last_sync") or "",
            }
            for d in sidecar.get("devices") or []
        ]
        result["noncompliant_devices"] = _noncompliant(result["devices"])
        result["has_data"] = True
        return result

    # Track whether the audit produced a parseable report at all — even a
    # zero-device tenant gets the "INTUNE DEVICE COUNT SUMMARY" banner from
    # the collector. Without this signal, a small M365-only tenant with no
    # Intune-enrolled devices would be reported as "Intune-data utilgjengelig"
    # in data_quality_issues, when in fact the audit completed fine and
    # measured zero devices.
    # A refusal is not a zero. The collector writes this marker when Graph
    # would not answer, and names the cause on the line below it; without
    # reading it back, "403 Forbidden" and "this tenant enrols nothing" are
    # the same empty file, and the report printed the same sentence for both.
    if _evidence_unavailable(detail_text) and _evidence_unavailable(count_text):
        result["unavailable"] = True
        result["unavailable_reason"] = _first_prose_line(detail_text) or _first_prose_line(
            count_text
        )
        result["has_data"] = False
        return result

    audit_succeeded = False
    if "INTUNE DEVICE COUNT" in count_text or "INTUNE MANAGED DEVICES" in detail_text:
        audit_succeeded = True

    # Parse count summary — flexible key matching
    for line in count_text.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower().replace("-", "").replace(" ", "")
        try:
            v = int(val.strip())
        except ValueError:
            continue
        # Any recognised count field also proves the audit ran.
        audit_succeeded = True
        if "total" in key:
            result["total"] = v
        elif key == "windows":
            result["windows"] = v
        elif key in ("ios", "ipadios"):
            result["ios"] = v
        elif key == "android":
            result["android"] = v
        elif key in ("macos", "mac"):
            result["macos"] = v
        elif key == "compliant":
            result["compliant"] = v
        elif key.startswith("non"):
            result["noncompliant"] = v
        elif "unknown" in key or "other" in key:
            result["unknown"] = v

    if result["total"] > 0:
        result["compliance_pct"] = round(result["compliant"] / result["total"] * 100, 1)

    # Parse device detail — supports both pipe-delimited AND columnar formats
    # Try pipe-delimited first
    pipe_parsed = False
    for line in detail_text.splitlines():
        if "|" not in line:
            continue
        parts = {}
        for seg in line.split("|"):
            seg = seg.strip()
            if ":" in seg:
                k, v = seg.split(":", 1)
                parts[k.strip().lower()] = v.strip()
        if parts:
            result["devices"].append(
                {
                    "name": parts.get("name", parts.get("devicename", "")),
                    "os": parts.get("os", ""),
                    "user": parts.get("user", parts.get("userprincipalname", "")),
                    "compliance": parts.get("compliance", parts.get("compliancestate", "")),
                    "enrolled": parts.get("enrolled", parts.get("enrolleddatetime", "")),
                }
            )
            pipe_parsed = True

    # Fallback: parse space-aligned columnar format using header positions
    if not pipe_parsed:
        lines = detail_text.splitlines()
        header_idx = -1
        for i, line in enumerate(lines):
            low = line.lower()
            if "device name" in low and "compliance" in low:
                header_idx = i
                break

        if header_idx >= 0:
            header = lines[header_idx]
            hlow = header.lower()
            # Find column start positions from header keywords
            col_os = hlow.find("os ")
            col_owner = hlow.find("owner")
            col_compl = hlow.find("complian")
            col_sync = hlow.find("last sync") if "last sync" in hlow else hlow.find("lastsync")

            for line in lines[header_idx + 1 :]:
                if not line.strip() or line.strip().startswith("=") or line.strip().startswith("-"):
                    continue
                if len(line) < col_compl + 5:
                    continue
                dev_name = line[2:col_os].strip() if col_os > 0 else line[:36].strip()
                os_name = line[col_os:col_owner].strip() if col_owner > col_os else ""
                compliance = (
                    line[col_compl:col_sync].strip()
                    if col_sync > col_compl
                    else line[col_compl:].strip()
                )
                enrolled = line[col_sync:].strip() if col_sync > 0 else ""
                owner = line[col_owner:col_compl].strip() if col_compl > col_owner else ""

                if dev_name and dev_name != "Device Name":
                    result["devices"].append(
                        {
                            "name": dev_name,
                            "os": os_name.split()[0] if os_name else "",
                            "user": owner,
                            "compliance": compliance,
                            "enrolled": enrolled,
                        }
                    )
    # The collector's count file has never had a per-platform line, so the
    # split stayed at zero for every tenant. The table's OS column has it.
    if not any(result[key] for key in _PLATFORMS):
        for device in result["devices"]:
            bucket = _platform(device["os"])
            if bucket:
                result[bucket] += 1
    result["noncompliant_devices"] = _noncompliant(result["devices"])
    # has_data means "audit produced a parseable report" — NOT "≥1 device
    # exists". A small M365-only tenant with no Intune-enrolled devices
    # legitimately reports 0; that's a measurement, not a gap.
    result["has_data"] = audit_succeeded or result["total"] > 0 or len(result["devices"]) > 0
    return result


def _noncompliant(devices: list[dict]) -> list[dict]:
    return [d for d in devices if d.get("compliance", "").lower() not in ("compliant", "")]


_PLATFORMS = ("windows", "ios", "android", "macos")


def _platform(operating_system: str) -> str:
    """The report's platform for an Intune operatingSystem value, or "".

    The same buckets the collector counts into its sidecar.
    """
    name = operating_system.lower()
    if name.startswith("windows"):
        return "windows"
    if name in ("ios", "ipados"):
        return "ios"
    if name.startswith("android"):
        return "android"
    if name.startswith("mac"):
        return "macos"
    return ""
