"""Parsers for SharePoint and OneDrive, Teams access, apps and their grants, and Purview."""

from __future__ import annotations

import re

from app.reports.evidence import _labelled_int, _labelled_value
from app.reports.i18n import T
from app.reports.parsers.common import _count_data_lines, _extract_policy_names, _sidecar
from app.reports.parsers.common import _count_data_lines, _policy_names, _sidecar


def _site_table_rows(sites_text: str) -> int | None:
    """Rows of the collector's site table, or None for a file without one.

    Every line between the "---" rule under the column header and the closing
    "===" frame is a site, whatever its first word. The shared row counter
    decides by that word, and files a site called "Notes" as a NOTE line and
    one called "No Code Lab" as a "No ..." placeholder.
    """
    lines = [line.strip() for line in sites_text.splitlines()]
    rule = next((i for i, line in enumerate(lines) if line.startswith("---")), None)
    if rule is None:
        return None
    rows = 0
    for line in lines[rule + 1 :]:
        if line.startswith("==="):
            break
        if line:
            rows += 1
    return rows


def _flag(value) -> str:
    """A sidecar's true/false/None as the text writes it: "true", "false" or ""."""
    return "" if value is None else str(value).lower()


def _parse_sharepoint_settings(
    settings_text: str,
    sites_text: str,
    lang: str = "no",
    settings_json: dict | None = None,
    sites_json: dict | None = None,
) -> dict:
    """SharePoint sharing posture and site counts.

    From the 15b_sharepoint_settings.json and 15_sharepoint_sites.json sidecars
    where the run has them, each independently, and from the text otherwise.
    """
    t = T(lang)
    settings: dict[str, str] = {}
    for line in settings_text.splitlines():
        if ":" in line and not line.strip().startswith("==="):
            k, v = line.split(":", 1)
            settings[k.strip().lower()] = v.strip()
    if settings_json is not None:
        # The sidecar, put in the vocabulary of the text it stands beside.
        settings = {
            "sharing capability": settings_json.get("sharing_capability") or "",
            "legacy auth": _flag(settings_json.get("legacy_auth")),
            "unmanaged devices": _flag(settings_json.get("unmanaged_devices")),
        }

    sharing_raw = settings.get("sharing capability", "")
    sharing_map = {
        "disabled": ("ok", t.sp_sharing_disabled),
        "existingexternalusersharingonly": ("ok", t.sp_sharing_existing_guests),
        "externalusersharingonly": ("warning", t.sp_sharing_guests_only),
        "externaluserandguestsharing": ("warning", t.sp_sharing_guests_anon),
    }
    sharing_key = sharing_raw.lower().replace(" ", "")
    # An absent "Sharing Capability" used to fall through to ("warning", …),
    # which every consumer reads as a finding. It is not one: has_data on this
    # parser is true as soon as the *sites* file parsed, so a tenant whose
    # admin-settings call failed while the site list succeeded got a
    # "SharePoint external sharing is at its most permissive level"
    # recommendation, an amber CIS 7.2.1, and a red panel — all from a field
    # nobody read. An unrecognised value is likewise unknown, not permissive.
    if not sharing_key:
        sharing_level, sharing_label = "unknown", t.sp_sharing_unknown
    else:
        sharing_level, sharing_label = sharing_map.get(
            sharing_key, ("unknown", sharing_raw or t.sp_sharing_unknown)
        )

    # Three states, not two. The collector did not write this line at all until
    # recently, and reading its absence as "false" meant the control that
    # grades it passed on every tenant ever audited, whatever the setting was.
    legacy_raw = settings.get("legacy auth", "").strip().lower()
    legacy_auth = legacy_raw == "true"
    legacy_known = legacy_raw in ("true", "false")

    # Counted through the shared helper rather than a local loop. The loop here
    # skipped only "===" lines, so the banner, the column header and the "---"
    # rule were each counted as a site: a tenant with 105 sites was reported as
    # having 108. The collector's own table is counted row by row, though: the
    # shared counter drops a site whose name starts like table furniture.
    site_count = _site_table_rows(sites_text)
    if site_count is None:
        site_count = _count_data_lines(sites_text)
    if sites_json is not None and "count" in sites_json:
        site_count = int(sites_json["count"])

    # A personal site is identified by its host, not by the word "personal"
    # appearing anywhere on the line. This tenant has an ordinary team site
    # named "Personal FF HF" at /sites/pers, which the substring match filed as
    # a OneDrive — the one "personal" site in a report where there are none.
    personal_sites = sum(
        1
        for line in sites_text.splitlines()
        if "-my.sharepoint.com" in line.lower() or "/personal/" in line.lower()
    )
    if sites_json is not None and "personal_count" in sites_json:
        personal_sites = int(sites_json["personal_count"])

    return {
        "sharing": sharing_raw,
        "sharing_level": sharing_level,
        "sharing_label": sharing_label,
        # Same tri-state as legacy_auth_known: a baseline check on the sharing
        # posture must be able to tell "read, and permissive" from "the
        # admin-settings call failed while the site list succeeded". Without
        # this guard, sharing_level == "unknown" reads as a finding — the exact
        # mistake the sharing_map comment above rejected one field over.
        "sharing_known": sharing_level != "unknown",
        "legacy_auth": legacy_auth,
        "legacy_auth_known": legacy_known,
        "unmanaged_devices": settings.get("unmanaged devices", "").lower() == "true",
        "site_count": site_count,
        "personal_sites": personal_sites,
        "team_sites": max(0, site_count - personal_sites),
        "has_data": bool(settings) or site_count > 0,
    }


def _onedrive_scan(file_contents: dict[str, str]) -> dict:
    """What the OneDrive sharing scan found and how far it got.

    {"anyone": int | None, "scanned", "refused", "discovery", "folders": int,
    "scope": "complete" | "partial" | ""}. From 25_onedrive_sharing.json where
    the run has it, and from the labelled lines of the text otherwise. "anyone"
    is None when there is no reading at all.
    """
    data = _sidecar(file_contents, "25_onedrive_sharing.txt")
    if data is not None and "anyone_link_count" in data:
        return {
            "anyone": int(data["anyone_link_count"]),
            "scanned": int(data.get("drives_scanned") or 0),
            "refused": int(data.get("drives_refused") or 0),
            "discovery": len(data.get("discovery_failures") or []),
            "folders": len(data.get("folder_failures") or []),
            "scope": "complete" if data.get("complete") else "partial",
        }
    text = file_contents.get("25_onedrive_sharing.txt", "")
    return {
        "anyone": _labelled_int(text, "'Anyone' links"),
        "scanned": _labelled_int(text, "Drives scanned") or 0,
        "refused": _labelled_int(text, "Drives refused") or 0,
        "discovery": _labelled_int(text, "Discovery failures") or 0,
        "folders": _labelled_int(text, "Folder failures") or 0,
        "scope": _labelled_value(text, "Scan scope"),
    }


def _teams_cross_tenant(file_contents: dict[str, str]) -> dict | None:
    """The default inbound access types CIS 8.1.1 grades, or None if unread.

    {"collab": str, "direct": str, "partners": str | None}: an access type is
    "" where nothing was read, and "partners" is the text the partner-only
    fallback searches for "blocked" and the like, or None when there are no
    partner configurations. From 16c_teams_external_access.json where the run
    has it, and from the labelled lines of the text otherwise.
    """
    data = _sidecar(file_contents, "16c_teams_external_access.txt")
    if data is not None:
        partners = data.get("partners") or []
        return {
            "collab": data.get("b2b_collaboration_inbound") or "",
            "direct": data.get("b2b_direct_connect_inbound") or "",
            "partners": " ".join(str(p.get("b2b_collaboration_inbound") or "N/A") for p in partners)
            if partners
            else None,
        }
    text = file_contents.get("16c_teams_external_access.txt", "")
    if not text.strip():
        return None
    return {
        "collab": _labelled_value(text, "B2B Collaboration"),
        "direct": _labelled_value(text, "B2B Direct Connect"),
        "partners": text if "Partner Configurations (" in text else None,
    }


def _teams_guest_settings(file_contents: dict[str, str]) -> tuple[str, str]:
    """(who may invite guests, the guest role), as the readable names, "" if unread.

    From 30b_teams_guest_access.json where the run has it, and from the
    labelled lines of the text otherwise.
    """
    data = _sidecar(file_contents, "30b_teams_guest_access.txt")
    if data is not None:
        return data.get("allow_invites_from_label") or "", data.get("guest_user_role") or ""
    text = file_contents.get("30b_teams_guest_access.txt", "")
    return _labelled_value(text, "Allow Invites From"), _labelled_value(text, "Guest User Role")


def _app_credential_counts(file_contents: dict[str, str]) -> tuple[int, int] | None:
    """(expired, expiring within 30 days) app credentials, or None to read the text.

    From the 17c_app_credential_expiry.json sidecar. It is written whenever
    there are app registrations to check, so its zeros are a reading, where the
    WARN file's absence was only one if the registrations had been read. None
    for a run from before it; the caller then reads the WARN file's summary.
    """
    data = _sidecar(file_contents, "17c_app_credential_expiry.txt")
    if data is None or "expired" not in data or "critical" not in data:
        return None
    return int(data["expired"]), int(data["critical"])


def _parse_oauth_grants(
    text: str,
    app_reg_text: str = "",
    grants_json: dict | None = None,
    apps_json: dict | None = None,
) -> dict:
    """Tenant-wide consent grants and the app registration count.

    From the 17b_oauth_consent_grants.json and 17_app_registrations.json
    sidecars where the run has them, each independently, and from the text
    otherwise. The sidecar carries each grant's names whole.
    """
    admin_consent: list[dict] = []
    grant_rows = (grants_json or {}).get("grants")
    if isinstance(grant_rows, list):
        admin_consent = [
            {
                "app": g.get("client_name") or g.get("client_id") or "",
                "scopes": list(g.get("scopes") or []),
            }
            for g in grant_rows
        ]
    app_permissions: list[dict] = []
    high_priv_keywords = {
        "fullcontrol",
        "readwrite.all",
        "accessasuser.all",
        "manage",
        "rolemanagement.readwrite",
    }

    _UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    section = ""
    fixed_width = False

    # Nothing to read off the text when the sidecar gave the grants.
    for line in [] if isinstance(grant_rows, list) else text.splitlines():
        stripped = line.strip()
        if "ADMIN CONSENT" in stripped or "CONSENT GRANTS" in stripped or "TENANT-WIDE" in stripped:
            section = "admin"
            continue
        elif "APPLICATION PERMISSIONS" in stripped:
            section = "app"
            continue
        elif not stripped or stripped.startswith("===") or stripped.startswith("-"):
            continue

        # The current collector's table, read by column offset. It writes
        #   f"  {client:<40} {resource:<40} {scopes}"
        # with each name trimmed to its column. A 40-character name fills the
        # column and leaves one space before the next, so the split on runs of
        # spaces below merged two columns and dropped the grant; so did an empty
        # scope. A doubled space inside a name cut the name short, and "App:" in
        # one sent the row down the pipe format's branch with no scopes. Every
        # one of those hid a grant, high-privilege ones included.
        if line.startswith("  Client App") and line[43:51] == "Resource":
            fixed_width = True
            continue
        if fixed_width:
            scopes = [s.strip() for s in line[84:].split(",") if s.strip()]
            admin_consent.append({"app": line[2:42].strip(), "scopes": scopes})
            continue

        # Format 1: Pipe-delimited with "App:" prefix
        if "App:" in stripped:
            parts = stripped.split("|")
            app_name = parts[0].replace("App:", "").strip()
            if app_name.startswith("["):
                idx = app_name.find("]")
                if idx > 0:
                    app_name = app_name[idx + 1 :].strip()
            if section == "admin":
                scopes_str = ""
                for p in parts[1:]:
                    if "Scopes:" in p:
                        scopes_str = p.replace("Scopes:", "").strip()
                scopes = scopes_str.split() if scopes_str else []
                admin_consent.append({"app": app_name, "scopes": scopes})
            elif section == "app":
                role = resource = ""
                for p in parts[1:]:
                    p = p.strip()
                    if p.startswith("Role:"):
                        role = p.replace("Role:", "").strip()
                    elif p.startswith("Resource:"):
                        resource = p.replace("Resource:", "").strip()
                app_permissions.append({"app": app_name, "role": role, "resource": resource})
            continue

        # Format 2: Columnar with GUIDs — "ClientID  ResourceID  Scopes"
        # Also: "Client (SP ID)    Resource ID    Scopes" header
        if "Client" in stripped and "Resource" in stripped and "Scope" in stripped:
            continue

        cols = re.split(r"\s{2,}", stripped)
        if len(cols) >= 2:
            # Check if first column looks like a GUID
            first = cols[0].strip()
            if _UUID.match(first) or (len(cols) >= 3 and not first.startswith("[")):
                client_id = first
                scopes_str = cols[-1] if len(cols) >= 3 else cols[1]
                scopes = [s.strip() for s in scopes_str.split(",") if s.strip()]
                admin_consent.append({"app": client_id, "scopes": scopes})

    # Count app registrations from separate file
    app_reg_count = 0
    if app_reg_text:
        m = re.search(r"\((\d+) total\)", app_reg_text)
        if m:
            app_reg_count = int(m.group(1))
    if apps_json is not None and "count" in apps_json:
        app_reg_count = int(apps_json["count"])

    all_apps = set()
    high_priv_apps = set()
    for g in admin_consent:
        all_apps.add(g["app"])
        for s in g["scopes"]:
            if any(kw in s.lower() for kw in high_priv_keywords):
                high_priv_apps.add(g["app"])
                break
    for g in app_permissions:
        all_apps.add(g["app"])
        if any(kw in g["role"].lower() for kw in high_priv_keywords):
            high_priv_apps.add(g["app"])

    return {
        "admin_consent": admin_consent,
        "app_permissions": app_permissions,
        "total_grants": len(admin_consent) + len(app_permissions),
        "high_privilege_apps": sorted(high_priv_apps),
        "unique_apps": len(all_apps),
        "app_registrations": app_reg_count,
        "has_data": len(all_apps) > 0 or app_reg_count > 0,
        # Whether the consent-grants file itself was readable. has_data can be
        # True from app registrations alone while the consent-grants read failed;
        # this lets the score flag that instead of crediting the missing read as
        # "no high-privilege apps" (accuracy sweep). NB: build_report_context
        # blanks an error-payload file to "" before this parser runs, so this
        # text-based check is only a fallback for direct callers — the reader
        # overrides grants_read from error_files, which survives the blanking.
        "grants_read": not text.lstrip().startswith("Error"),
    }


def _sensitivity_labels(file_contents: dict[str, str]) -> list[dict] | None:
    """The labels in 19c_purview_sensitivity_labels.json, or None without it.

    The text cuts each name at 45 characters, and its reader skips any line
    that reads like a heading: a label named "No restrictions" or "Purview
    test" was not counted.
    """
    data = _sidecar(file_contents, "19c_purview_sensitivity_labels.txt")
    if data is None:
        return None
    labels = []
    for row in data.get("labels") or []:
        if not isinstance(row, dict):
            continue
        priority = row.get("priority")
        labels.append(
            {
                "name": str(row.get("name") or ""),
                "priority": priority if isinstance(priority, int) else 0,
                "active": bool(row.get("active")),
            }
        )
    return labels


def _parse_purview(file_contents: dict[str, str]) -> dict:
    """Parse Purview/DLP data: sensitivity labels, DLP policies, retention policies."""
    result: dict = {
        "sensitivity_labels": [],
        "sensitivity_label_count": 0,
        "dlp_policies": [],
        "dlp_policy_count": 0,
        "retention_policies": [],
        "retention_policy_count": 0,
        "has_data": False,
    }

    # Sensitivity labels (19c_purview_sensitivity_labels.txt)
    labels_text = file_contents.get("19c_purview_sensitivity_labels.txt", "")
    sidecar_labels = _sensitivity_labels(file_contents)
    if sidecar_labels is not None:
        result["sensitivity_labels"] = sidecar_labels
        result["sensitivity_label_count"] = len(sidecar_labels)
        result["has_data"] = bool(sidecar_labels)
    elif labels_text.strip():
        for line in labels_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-"):
                continue
            if stripped.upper().startswith("NOTE") or stripped.upper().startswith("NO "):
                continue
            low = stripped.lower()
            if (
                "label name" in low
                or "sensitivity label" in low
                or "purview" in low.replace("-", "")
            ):
                continue

            if "|" in stripped:
                parts = [p.strip() for p in stripped.split("|")]
                name = parts[0]
                priority = 0
                active = True
                for p in parts[1:]:
                    if p.isdigit():
                        priority = int(p)
                    elif p.lower() in ("inactive", "disabled", "false", "no"):
                        active = False
                result["sensitivity_labels"].append(
                    {"name": name, "priority": priority, "active": active}
                )
            else:
                cols = re.split(r"\s{2,}", stripped)
                name = cols[0]
                priority = 0
                active = True
                for c in cols[1:]:
                    if c.isdigit():
                        priority = int(c)
                    elif c.lower() in ("inactive", "disabled", "false", "no"):
                        active = False
                if name and name.lower() not in ("name", "label", "priority", "status"):
                    result["sensitivity_labels"].append(
                        {"name": name, "priority": priority, "active": active}
                    )

        result["sensitivity_label_count"] = len(result["sensitivity_labels"])
        if result["sensitivity_label_count"] > 0:
            result["has_data"] = True

    # DLP and retention policies are written as `_section_block` dumps — the
    # same "[i] then Key: Value" format the anti-phish parser reads. The
    # line-based reader that used to live here did not understand that format:
    # it counted the "(none)" empty placeholder as one policy and each field
    # line of a real policy as another, so an empty section reported "1 DLP
    # policy" and the card disagreed with the raw data printed below it.
    # Delegate to the block parser so empty -> 0 and each policy counts once.
    dlp_text = file_contents.get("19d_purview_dlp_policies.txt", "")
    if dlp_text.strip():
        result["dlp_policies"] = [
            {"name": n} for n in _policy_names(file_contents, "19d_purview_dlp_policies.txt")
        ]
        result["dlp_policy_count"] = len(result["dlp_policies"])
        if result["dlp_policy_count"] > 0:
            result["has_data"] = True

    retention_text = file_contents.get("19e_purview_retention_policies.txt", "")
    if retention_text.strip():
        result["retention_policies"] = [
            {"name": n} for n in _policy_names(file_contents, "19e_purview_retention_policies.txt")
        ]
        result["retention_policy_count"] = len(result["retention_policies"])
        if result["retention_policy_count"] > 0:
            result["has_data"] = True

    return result
