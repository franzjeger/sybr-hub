"""Backup of the Microsoft 365 data: what 34_m365_backup says, per workload.

The collector (sections/m365_backup.py) reads two sources: Microsoft 365
Backup, Microsoft's own service, and the service principals of known backup
vendors. This module turns them into one verdict per workload:

* ``native``: an active Microsoft 365 Backup policy protects it;
* ``third_party``: a backup vendor's app holds access to it. That is evidence
  the product is installed and allowed to read the data, not proof that its
  backups run, and every sentence built here says so;
* ``none``: both sources were read and neither shows anything;
* ``unknown``: a source that could have answered was not read. A refusal is
  not a zero, so this is never reported as "no backup".

Teams is shown beside the three because customers ask about it, but it is not
judged: Microsoft 365 Backup has no Teams policy (its files live in
SharePoint), so without a vendor app holding chat access the row says where
the files are rather than raising a finding.

The sidecar is read first; the text, which carries the same facts in fixed
labelled lines, is the fallback when the sidecar is missing.
"""

from __future__ import annotations

import re

from app.reports.i18n import T
from app.reports.parsers.common import _sidecar

OUTPUT_FILE = "34_m365_backup.txt"

# The workloads a finding is raised for, and Teams, which is shown only.
CORE_WORKLOADS = ("exchange", "onedrive", "sharepoint")
WORKLOADS = (*CORE_WORKLOADS, "teams")

_SERVICE_PERMISSION = "BackupRestore-Control.Read.All"
_POLICY_PERMISSION = "BackupRestore-Configuration.Read.All"

# Policy statuses under which some units are, or are about to be, protected.
_ACTIVE_POLICY = {"active", "activewitherrors", "updating"}
_LOCKED = {"protectionchangelocked", "restorelocked"}


# ── Reading the file ──────────────────────────────────────────────────────────


def _blank_source() -> dict:
    return {
        "native": {
            "service": {"read": False, "status": "", "error_kind": "", "error": ""},
            "policies": {"read": False, "error_kind": "", "error": "", "items": []},
        },
        "third_party": {"read": False, "error_kind": "", "error": "", "scanned": 0, "apps": []},
    }


_UNREADABLE = re.compile(r"^unreadable \((\w*)\)")
_COUNTS = re.compile(
    r"protected=(\d+)\s+in_progress=(\d+)\s+failed=(\d+)\s+total=(\d+)",
)


def _permission_list(text: str) -> list[dict]:
    if text.strip() == "(none)":
        return []
    out = []
    for part in text.split(", "):
        resource, _, value = part.strip().rpartition("/")
        if value:
            out.append({"value": value, "resource": resource})
    return out


def _from_text(text: str) -> dict | None:
    """The sidecar's shape, rebuilt from the text file's labelled lines.

    None when the text is not this collector's output at all.
    """
    if "MICROSOFT 365 BACKUP" not in text:
        return None
    data = _blank_source()
    service = data["native"]["service"]
    policies = data["native"]["policies"]
    third = data["third_party"]
    block = ""
    app: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("NATIVE:"):
            block = "native"
            continue
        if line.startswith("THIRD-PARTY BACKUP APPS"):
            block = "third"
            continue
        label, sep, value = line.partition(":")
        label, value = label.strip(), value.strip()
        unreadable = _UNREADABLE.match(value) if sep else None
        if block == "native" and label == "Service status":
            if unreadable:
                service["error_kind"] = unreadable.group(1)
            else:
                service.update(read=True, status="" if value == "unknown" else value)
        elif block == "native" and label == "Service detail":
            service["error"] = value
        elif block == "native" and label == "Disable reason":
            service["disable_reason"] = value
        elif block == "native" and label == "Controlled by":
            service["consumer"] = "" if value == "unknown" else value
        elif block == "native" and label == "Policies":
            if unreadable:
                policies["error_kind"] = unreadable.group(1)
            else:
                policies["read"] = True
        elif block == "native" and label == "Policies detail":
            policies["error"] = value
        elif block == "native" and raw.startswith("    ") and line.count(" | ") >= 4:
            workload, status, mode, counts, name = line.split(" | ", 4)
            found = _COUNTS.search(counts)
            units: dict = {"read": bool(found), "source": "", "error_kind": ""}
            if found:
                protected, in_progress, failed, total = (int(g) for g in found.groups())
                units.update(protected=protected, in_progress=in_progress)
                units.update(failed=failed, total=total)
            policies["items"].append(
                {
                    "name": name,
                    "workload": "" if workload == "unknown" else workload,
                    "status": "" if status == "unknown" else status,
                    "mode": "" if mode == "standard" else mode,
                    "units": units,
                }
            )
        elif block == "third" and label == "Apps found":
            if unreadable:
                third["error_kind"] = unreadable.group(1)
            else:
                third["read"] = True
                scanned = re.search(r"of (\d+) service principals", value)
                third["scanned"] = int(scanned.group(1)) if scanned else 0
        elif block == "third" and label == "Apps detail":
            third["error"] = value
        elif block == "third" and raw.startswith("    ") and not raw.startswith("      "):
            fields = line.split(" | ")
            if len(fields) < 6:
                continue
            product, display, enabled, match, workloads = fields[:5]
            match = match.removeprefix("match=")
            workloads = workloads.removeprefix("workloads=")
            app = {
                "product": None if match == "generic" else product,
                "display_name": display,
                "app_id": fields[5].removeprefix("app_id="),
                "enabled": enabled == "enabled",
                "match": match,
                "permissions_read": workloads != "unknown",
                "permissions_error": "",
                "application_permissions": [],
                "delegated_scopes": [],
                "workloads": [] if workloads in ("none", "unknown") else workloads.split(","),
            }
            third["apps"].append(app)
        elif block == "third" and app is not None and label == "permissions":
            app["permissions_read"] = False
            app["permissions_error"] = value
        elif block == "third" and app is not None and label == "application":
            app["application_permissions"] = _permission_list(value)
        elif block == "third" and app is not None and label == "delegated":
            app["delegated_scopes"] = _permission_list(value)
    return data


def _source(file_contents: dict[str, str]) -> dict | None:
    data = _sidecar(file_contents, OUTPUT_FILE)
    if data is not None and isinstance(data.get("native"), dict):
        merged = _blank_source()
        native = data["native"]
        merged["native"]["service"].update(native.get("service") or {})
        merged["native"]["policies"].update(native.get("policies") or {})
        merged["third_party"].update(data.get("third_party") or {})
        return merged
    return _from_text(file_contents.get(OUTPUT_FILE, ""))


# ── Wording ───────────────────────────────────────────────────────────────────


def _join(items: list[str], t: T) -> str:
    """ "a, b og c" / "a, b and c"."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {t.m365_backup_and} {items[-1]}"


_UNREAD_KINDS = ("permission", "licence", "not_found")


def _unread_reason(kind: str, permission: str, t: T) -> str:
    """The whole sentence: why it was not read, and what to grant."""
    kind = kind if kind in _UNREAD_KINDS else "error"
    return t(f"m365_backup_unread_{kind}", permission=permission)


def _unread_short(kind: str, t: T) -> str:
    """The same in a few words, for a table cell; the sentence sits below the table."""
    kind = kind if kind in _UNREAD_KINDS else "error"
    return getattr(t, f"m365_backup_unread_short_{kind}")


# ── Per workload ──────────────────────────────────────────────────────────────


def _native_state(native: dict, workload: str, total: int | None, t: T) -> dict:
    """What Microsoft 365 Backup says about one workload.

    state is "covered", "none" or "unknown"; text says it in the reader's
    language. ``total`` is what the audit counted elsewhere (mailboxes,
    sites), for "x of y"; None when there is nothing comparable.
    """
    service, policies = native["service"], native["policies"]
    status = str(service.get("status") or "").lower()
    out: dict = {"state": "unknown", "text": "", "warning": False, "policies": []}
    if workload == "teams":
        out.update(state="not_supported", text=t.m365_backup_native_teams)
        return out
    if service.get("read") and status == "disabled":
        out.update(state="none", text=t.m365_backup_native_disabled)
        return out
    if service.get("read") and status in _LOCKED:
        out.update(state="none", text=t("m365_backup_native_locked", status=service["status"]))
        return out
    if not policies.get("read"):
        failed_read, permission = (
            (policies, _POLICY_PERMISSION)
            if service.get("read")
            else (service, _SERVICE_PERMISSION)
        )
        kind = failed_read.get("error_kind", "")
        out.update(text=_unread_short(kind, t), reason=_unread_reason(kind, permission, t))
        return out

    mine = [p for p in policies.get("items") or [] if p.get("workload") == workload]
    out["policies"] = mine
    if not mine:
        out.update(state="none", text=t.m365_backup_native_no_policy)
        return out
    active = [p for p in mine if str(p.get("status") or "").lower() in _ACTIVE_POLICY]
    if not active:
        out.update(state="none", text=t.m365_backup_native_inactive)
        return out

    full_service = any(str(p.get("mode") or "") == "fullServiceBackup" for p in active)
    counted = [p["units"] for p in active if (p.get("units") or {}).get("read")]
    protected = sum(int(u.get("protected") or 0) for u in counted)
    in_progress = sum(int(u.get("in_progress") or 0) for u in counted)
    failed = sum(int(u.get("failed") or 0) for u in counted)
    errors = any(str(p.get("status") or "").lower() == "activewitherrors" for p in active)
    out["warning"] = errors or failed > 0
    out.update(protected=protected, in_progress=in_progress, failed=failed)

    if full_service:
        parts = [t.m365_backup_native_full_service]
    elif not counted:
        out.update(
            state="covered", text=f"Microsoft 365 Backup: {t.m365_backup_native_units_unknown}"
        )
        return out
    elif protected == 0 and in_progress == 0:
        out.update(state="none", text=t.m365_backup_native_no_units)
        return out
    elif protected == 0:
        # Units asked for and not protected yet: being set up, not done.
        out["warning"] = True
        parts = []
    elif total is not None and total >= protected:
        parts = [t("m365_backup_native_covered_of", count=protected, total=total)]
    else:
        parts = [t("m365_backup_native_covered", count=protected)]
    if in_progress:
        parts.append(t("m365_backup_native_in_progress", count=in_progress))
    if failed:
        parts.append(t("m365_backup_native_failed", count=failed))
    out.update(state="covered", text=f"Microsoft 365 Backup: {', '.join(parts)}")
    return out


def _app_name(app: dict) -> str:
    return str(app.get("product") or app.get("display_name") or "?")


def _third_state(third: dict, workload: str, t: T) -> dict:
    """What the vendor apps say about one workload: "found", "none" or "unknown"."""
    if not third.get("read"):
        return {
            "state": "unknown",
            "apps": [],
            "text": t.m365_backup_app_unread_short,
            "reason": t.m365_backup_app_unread,
        }
    apps = [a for a in third.get("apps") or [] if a.get("enabled", True)]
    found = sorted(
        {_app_name(a) for a in apps if a.get("permissions_read") and workload in a["workloads"]}
    )
    if found:
        return {
            "state": "found",
            "apps": found,
            "text": t("m365_backup_app_found", apps=_join(found, t)),
        }
    unread = sorted({_app_name(a) for a in apps if not a.get("permissions_read")})
    if unread:
        text = t("m365_backup_app_permissions_unread", app=_join(unread, t))
        return {"state": "unknown", "apps": [], "text": text, "reason": text}
    # Teams is judged on chat access only; its files are SharePoint's row.
    none = t.m365_backup_app_none_teams if workload == "teams" else t.m365_backup_app_none
    return {"state": "none", "apps": [], "text": none}


_LEVEL = {
    "native": "ok",
    "third_party": "ok",
    "none": "critical",
    "unknown": "unknown",
    "files_only": "unknown",
}


def _workload(native: dict, third: dict, workload: str, total: int | None, t: T) -> dict:
    nat = _native_state(native, workload, total, t)
    tp = _third_state(third, workload, t)
    if nat["state"] == "covered":
        verdict = "native"
    elif tp["state"] == "found":
        verdict = "third_party"
    elif workload == "teams":
        verdict = "unknown" if tp["state"] == "unknown" else "files_only"
    elif nat["state"] == "none" and tp["state"] == "none":
        verdict = "none"
    else:
        verdict = "unknown"
    level = _LEVEL[verdict]
    if verdict == "native" and nat["warning"]:
        level = "warning"
    return {
        "key": workload,
        "label": getattr(t, f"m365_backup_wl_{workload}"),
        "verdict": verdict,
        "level": level,
        "verdict_label": getattr(t, f"m365_backup_verdict_{verdict}"),
        "native_state": nat["state"],
        "native_text": nat["text"],
        "third_state": tp["state"],
        "third_text": tp["text"],
        # The whole sentence behind an "unknown": the source that could have
        # answered and did not. Microsoft 365 Backup first, as it decides more.
        "reason": nat.get("reason") if nat["state"] == "unknown" else tp.get("reason", ""),
        "apps": tp["apps"],
    }


# ── The parsed reading ────────────────────────────────────────────────────────


def _empty() -> dict:
    return {
        "has_data": False,
        "assessed": False,
        "workloads_without_backup": 0,
        "gaps": [],
        "unknown": [],
        "third_party_only": [],
        "workloads": [],
        "service": {},
        "policies": [],
        "apps": [],
        "native_read": False,
        "third_party_read": False,
        "unread_notes": [],
    }


def _parse_m365_backup(
    file_contents: dict[str, str],
    lang: str = "no",
    totals: dict[str, int | None] | None = None,
) -> dict:
    """The backup verdict per workload, and what the technical report lists.

    ``totals`` maps a workload to what the audit counted for it elsewhere
    (mailboxes from Exchange, sites from SharePoint), shown as "x of y".

    ``assessed`` is true when the reading can be judged: every core workload
    has a definite verdict, or at least one has a definite gap.
    ``workloads_without_backup`` counts the core workloads with no sign of
    backup from either source; it is what a baseline compares.
    """
    source = _source(file_contents)
    result = _empty()
    if source is None:
        return result
    t = T(lang)
    totals = totals or {}
    native, third = source["native"], source["third_party"]

    workloads = [_workload(native, third, w, totals.get(w), t) for w in WORKLOADS]
    core = [w for w in workloads if w["key"] in CORE_WORKLOADS]
    gaps = [w["key"] for w in core if w["verdict"] == "none"]
    unknown = [w["key"] for w in core if w["verdict"] == "unknown"]

    notes: list[str] = []
    service, policies = native["service"], native["policies"]
    if not service.get("read"):
        notes.append(_unread_reason(service.get("error_kind", ""), _SERVICE_PERMISSION, t))
    if not policies.get("read"):
        notes.append(_unread_reason(policies.get("error_kind", ""), _POLICY_PERMISSION, t))
    if not third.get("read"):
        notes.append(t.m365_backup_app_unread)

    result.update(
        has_data=True,
        assessed=not unknown or bool(gaps),
        workloads_without_backup=len(gaps),
        gaps=gaps,
        unknown=unknown,
        third_party_only=[w["key"] for w in core if w["verdict"] == "third_party"],
        workloads=workloads,
        service=service,
        policies=[
            {
                **p,
                "workload_label": (
                    getattr(t, f"m365_backup_wl_{p['workload']}") if p.get("workload") else "?"
                ),
                "total": totals.get(p.get("workload") or ""),
            }
            for p in policies.get("items") or []
        ],
        policies_read=bool(policies.get("read")),
        policies_error=str(policies.get("error") or ""),
        apps=[
            {
                **app,
                "name": _app_name(app),
                "access": _join(
                    [getattr(t, f"m365_backup_access_{w}") for w in app.get("workloads") or []], t
                ),
            }
            for app in third.get("apps") or []
        ],
        native_read=bool(service.get("read") or policies.get("read")),
        third_party_read=bool(third.get("read")),
        third_party_error=str(third.get("error") or ""),
        scanned=int(third.get("scanned") or 0),
        unread_notes=notes,
    )
    return result


def m365_backup_control(audit) -> tuple[str, str]:
    """The compliance verdict for "Ensure Microsoft 365 data is backed up".

    ``audit`` is compliance._Audit; only its file contents and translator are
    read. "pass" needs Microsoft 365 Backup on all three core workloads, the
    one reading the tenant itself can confirm. A vendor app with access is
    evidence, not confirmation, so a workload covered only that way leaves the
    control "info" with the app named. Any workload with no sign of backup
    fails it, and a source that was not read leaves it "info".
    """
    t: T = audit.t
    reading = _parse_m365_backup(audit.fc, lang=t.lang)
    if not reading["has_data"]:
        return "info", t.cis_m365_backup_not_run
    labels = {w["key"]: w["label"] for w in reading["workloads"]}
    if reading["gaps"]:
        return "fail", t(
            "cis_m365_backup_fail", workloads=_join([labels[k] for k in reading["gaps"]], t)
        )
    if reading["unknown"]:
        first = next(w for w in reading["workloads"] if w["key"] in reading["unknown"])
        return "info", t("cis_m365_backup_unknown", reason=first["reason"])
    if reading["third_party_only"]:
        apps = sorted({a for w in reading["workloads"] for a in w["apps"]})
        return "info", t("cis_m365_backup_third_party", apps=_join(apps, t))
    return "pass", t.cis_m365_backup_pass
