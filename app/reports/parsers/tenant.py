"""Parsers for tenant-wide data: Secure Score, licences and their use."""

from __future__ import annotations

import re

from app.reports.evidence import _evidence_unavailable
from app.reports.i18n import T
from app.reports.parsers.common import _first_prose_line


def _parse_secure_score(text: str) -> dict:
    m = re.search(r"Score\s*:\s*([\d.]+)\s*/\s*([\d.]+)\s*\(([\d.]+)%\)", text)
    if not m:
        return {"current": 0, "max": 0, "pct": 0, "improvements": [], "has_data": False}
    current, max_, pct = float(m.group(1)), float(m.group(2)), float(m.group(3))

    # The improvement table. Two things used to go wrong here at once: the
    # collector ranked by percentage *descending*, so the list was the controls
    # already at 100%, and this then dropped every row at 0% — the controls
    # with the most to gain. Either alone would have skewed the table; together
    # they guaranteed it showed only completed work.
    improvements = []
    in_table = False
    for line in text.splitlines():
        # Match loosely: runs recorded before the heading gained its ordering
        # note say "Top 20 Improvement Actions (by impact)".
        if "Improvement Actions" in line:
            in_table = True
            continue
        stripped = line.strip()
        if in_table and stripped and not stripped.startswith(("-", "=", "(")):
            if stripped.startswith("Control"):
                continue  # column header
            # Newer rows carry a "Left" column between the percentage and the
            # category; older ones do not. Find the percentage and read the
            # name from everything before it either way.
            m_pct = re.search(r"([\d.]+)\s*%", stripped)
            if m_pct:
                try:
                    score_pct = float(m_pct.group(1))
                except ValueError:
                    continue
                name = stripped[: m_pct.start()].strip()
                remaining = None
                tail = stripped[m_pct.end() :].split()
                if tail:
                    try:
                        remaining = float(tail[0])
                    except ValueError:
                        remaining = None
                if name:
                    entry = {"name": name, "pct": score_pct}
                    if remaining is not None:
                        entry["remaining"] = remaining
                    improvements.append(entry)
        if len(improvements) >= 10:
            break

    return {
        "current": current,
        "max": max_,
        "pct": pct,
        "improvements": improvements,
        "has_data": True,
    }


def _parse_licenses(text: str) -> list[dict]:
    """Parse 02_licenses.txt into a list of {part, used, total, pct, warn}.

    The collector appends a status suffix ("  *** OVER 90% ***") to lines
    where utilisation is ≥90%. Without stripping that suffix, rsplit takes
    "OVER" and "***" as fields and the whole line is silently dropped —
    which means the over-utilised licences (precisely the ones the auditor
    cares about) never reach the report.
    """
    licenses = []
    for line in text.splitlines():
        if "%" not in line or ":" in line:
            continue
        # Strip any trailing status flag before tokenising. Two formats in
        # the wild — "*** OVER 90% ***" (current) and "100%*" (legacy). The
        # first is fatal if not stripped because rsplit takes 'OVER' as a
        # field; the second was handled before but we must keep parsing it.
        cleaned = line.split("***")[0]
        cleaned = cleaned.replace("*", "").strip()
        parts = cleaned.rsplit(None, 3)
        if len(parts) < 4:
            continue
        try:
            part = parts[0]
            used = int(parts[1])
            total = int(parts[2])
            pct = float(parts[3].replace("%", ""))
        except (ValueError, IndexError):
            continue
        # Compute the warn boundary from the raw used/total, not the collector's
        # ROUNDED printed pct — a true utilisation of 89.5% prints "90%" and
        # tripped the warning one seat early (accuracy sweep). Matches the
        # collector's own >=90 check on the unrounded ratio.
        warn = total > 0 and used / total >= 0.9
        licenses.append(
            {
                "part": part,
                "name": _sku_friendly(part),
                "used": used,
                "total": total,
                "pct": pct,
                "warn": warn,
            }
        )
    return licenses


# ── SKU pricing estimates (monthly per-user NOK, approximate list prices) ──
_SKU_MONTHLY_PRICE: dict[str, int] = {
    "SPE_E5": 580,  # Microsoft 365 E5
    "SPE_E3": 380,  # Microsoft 365 E3
    "ENTERPRISEPREMIUM": 580,  # Office 365 E5
    "ENTERPRISEPACK": 260,  # Office 365 E3
    "ENTERPRISEPACK_FACULTY": 260,
    "STANDARDPACK": 100,  # Office 365 E1
    "EMS_E5": 170,  # EMS E5
    "EMS_E3_RMS_adhoc": 110,
    "EMSPREMIUM": 170,  # EMS E5
    "AAD_PREMIUM_P2": 110,
    "AAD_PREMIUM": 70,
    "POWER_BI_PRO": 100,
    "POWER_BI_PREMIUM_PER_USER": 200,
    "PROJECTPREMIUM": 550,  # Project Plan 5
    "PROJECTPROFESSIONAL": 300,  # Project Plan 3
    "VISIOCLIENT": 150,  # Visio Plan 2
    "Microsoft_365_Copilot": 300,  # Copilot
    "FLOW_PER_USER": 150,
    "POWERAPPS_PER_USER": 200,
    "STREAM": 0,  # often free / included
    "TEAMS_EXPLORATORY": 0,
}


# E5 SKUs and their E3 equivalents (for potential downgrade detection)
_E5_SKUS = {"SPE_E5", "ENTERPRISEPREMIUM"}


_E3_SKUS = {"SPE_E3", "ENTERPRISEPACK"}


# Graph reports licences by their skuPartNumber — SPE_E3, O365_BUSINESS_PREMIUM
# — which reads as nothing to a customer and misleads even a technician
# (O365_BUSINESS_PREMIUM is Business *Standard*, not Premium). Map the ones an
# SMB tenant actually carries to the name Microsoft sells them under. The raw
# part number is still shown beside it for anyone matching against Graph.
_SKU_FRIENDLY: dict[str, str] = {
    "SPB": "Microsoft 365 Business Premium",
    "O365_BUSINESS_PREMIUM": "Microsoft 365 Business Standard",
    "O365_BUSINESS_ESSENTIALS": "Microsoft 365 Business Basic",
    "O365_BUSINESS": "Microsoft 365 Apps for Business",
    "OFFICESUBSCRIPTION": "Microsoft 365 Apps for Enterprise",
    "SPE_E3": "Microsoft 365 E3",
    "SPE_E5": "Microsoft 365 E5",
    "SPE_F1": "Microsoft 365 F3",
    "SPE_F5_SECCOMP": "Microsoft 365 F5 Security + Compliance",
    "ENTERPRISEPACK": "Office 365 E3",
    "ENTERPRISEPREMIUM": "Office 365 E5",
    "STANDARDPACK": "Office 365 E1",
    "DESKLESSPACK": "Office 365 F3",
    "EXCHANGESTANDARD": "Exchange Online (Plan 1)",
    "EXCHANGEENTERPRISE": "Exchange Online (Plan 2)",
    "EXCHANGEDESKLESS": "Exchange Online Kiosk",
    "EMS": "Enterprise Mobility + Security E3",
    "EMSPREMIUM": "Enterprise Mobility + Security E5",
    "AAD_PREMIUM": "Entra ID P1",
    "AAD_PREMIUM_P2": "Entra ID P2",
    "INTUNE_A": "Intune Plan 1",
    "Microsoft_365_Copilot": "Microsoft 365 Copilot",
    "MCOMEETADV": "Microsoft 365 Audio Conferencing",
    "MCOEV": "Microsoft Teams Phone Standard",
    "PHONESYSTEM_VIRTUALUSER": "Teams Phone Resource Account",
    "TEAMS_EXPLORATORY": "Microsoft Teams Exploratory",
    "Microsoft_Teams_Premium": "Microsoft Teams Premium",
    "POWER_BI_PRO": "Power BI Pro",
    "POWER_BI_STANDARD": "Power BI (free)",
    "FLOW_FREE": "Power Automate (free)",
    "POWERAPPS_VIRAL": "Power Apps (trial)",
    "PROJECTPROFESSIONAL": "Project Plan 3",
    "PROJECTPREMIUM": "Project Plan 5",
    "VISIOCLIENT": "Visio Plan 2",
    "WINDOWS_STORE": "Windows Store for Business",
    "WIN10_PRO_ENT_SUB": "Windows 10/11 Enterprise E3",
    "MDATP_XPLAT": "Defender for Endpoint",
    "ATP_ENTERPRISE": "Defender for Office 365 (Plan 1)",
    "THREAT_INTELLIGENCE": "Defender for Office 365 (Plan 2)",
}


def _sku_friendly(part: str) -> str:
    """The name Microsoft sells a SKU under, or the part number if unmapped."""
    return _SKU_FRIENDLY.get((part or "").strip(), (part or "").strip())


def _parse_stale_accounts(text: str) -> list[dict]:
    """Parse 03b_stale_accounts.txt into a list of stale user dicts."""
    accounts: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("=")
            or stripped.startswith("-")
            or "Display Name" in stripped
            or "STALE" in stripped
            or "NOTE:" in stripped
            or "Stale accounts" in stripped
        ):
            continue
        # Format: Name(35)  UPN(45)  LastSignIn(22)  Days(5)  Licensed(8)
        cols = re.split(r"\s{2,}", stripped)
        if len(cols) >= 4:
            name = cols[0].strip()
            upn = cols[1].strip()
            licensed_str = cols[-1].strip() if len(cols) >= 5 else "No"
            days_str = cols[-2].strip() if len(cols) >= 5 else cols[-1].strip()
            try:
                days = int(days_str)
            except ValueError:
                days = None
            accounts.append(
                {
                    "name": name,
                    "upn": upn,
                    "days_inactive": days,
                    "licensed": licensed_str.upper().startswith("Y"),
                }
            )
    return accounts


def _parse_shared_mailbox_upns(text: str) -> set[str]:
    """UPNs of shared and room mailboxes from 20_exchange_mailboxes.txt.

    These never sign in by design, so licence optimisation must not read a
    licensed shared/room mailbox as an "inactive user" to deprovision.
    """
    shared: set[str] = set()
    for line in text.splitlines():
        if "SharedMailbox" not in line and "RoomMailbox" not in line:
            continue
        cols = re.split(r"\s{2,}", line.strip())
        upn = next((c for c in cols if "@" in c), "")
        if upn:
            shared.add(upn.lower())
    return shared


def _analyze_license_optimization(
    licenses: list[dict],
    file_contents: dict[str, str],
    lang: str = "no",
) -> dict:
    """Cross-reference license assignments with user activity to find waste.

    Returns dict with total_waste_estimate, unused_licenses, over_provisioned,
    downgrade_candidates, and optimization_suggestions.
    """
    t = T(lang)

    unused_licenses: list[dict] = []
    over_provisioned: list[dict] = []
    downgrade_candidates: list[dict] = []
    suggestions: list[dict] = []
    total_waste = 0

    # 1. Parse stale accounts to find inactive licensed users
    stale_text = file_contents.get("03b_stale_accounts.txt", "")
    stale_accounts = _parse_stale_accounts(stale_text)
    licensed_stale = [s for s in stale_accounts if s.get("licensed")]

    # A shared/room mailbox never signs in, so a licensed one showing up "stale"
    # is not an inactive *user* to deprovision — treating it as one gives false
    # advice and inflates the estimate. Split them: a real inactive user keeps
    # the "remove licence" finding; a licensed shared/room mailbox gets its own,
    # correctly framed one (a shared mailbox needs no licence under 50 GB).
    shared_upns = _parse_shared_mailbox_upns(file_contents.get("20_exchange_mailboxes.txt", ""))
    licensed_stale_users = [
        s for s in licensed_stale if (s.get("upn") or "").lower() not in shared_upns
    ]
    licensed_shared = [s for s in licensed_stale if (s.get("upn") or "").lower() in shared_upns]

    # USAGE-WEIGHTED average paid-SKU price, used to estimate both kinds of
    # waste. An unweighted average across SKU TYPES priced every stale seat at
    # the blend of all types, so a tenant whose seats are mostly a cheap SKU
    # (e.g. F1) but which also holds a few expensive ones had the saving badly
    # overstated (M365 review: 251 seats x ~203 kr). Weighting by seats in use
    # makes the estimate reflect the tenant's actual licence mix. The stale
    # accounts' own SKUs are not recorded per-account, so this is the best
    # estimate available without that data.
    weighted_sum = 0
    weighted_seats = 0
    for lic in licenses:
        price = _SKU_MONTHLY_PRICE.get(lic["part"], 0)
        if price > 0 and lic["used"] > 0:
            weighted_sum += price * lic["used"]
            weighted_seats += lic["used"]
    avg_price = int(weighted_sum / weighted_seats) if weighted_seats else 300

    if licensed_stale_users:
        waste_amount = len(licensed_stale_users) * avg_price

        for s in licensed_stale_users:
            days_label = (
                str(s["days_inactive"]) + " " + t.lo_days
                if s["days_inactive"] is not None
                else t.lo_never_signed_in
            )
            unused_licenses.append(
                {
                    "name": s["name"],
                    "upn": s["upn"],
                    "days_inactive": s["days_inactive"],
                    "days_label": days_label,
                }
            )
        total_waste += waste_amount

        suggestions.append(
            {
                "type": "unused",
                "title": t("lo_suggest_remove_unused", count=len(licensed_stale_users)),
                "detail": t(
                    "lo_suggest_remove_unused_detail",
                    count=len(licensed_stale_users),
                    amount=waste_amount,
                ),
                "priority": "high",
                "savings": waste_amount,
            }
        )

    if licensed_shared:
        shared_waste = len(licensed_shared) * avg_price
        total_waste += shared_waste
        suggestions.append(
            {
                "type": "shared_mailbox_licensed",
                "title": t("lo_suggest_shared_licensed", count=len(licensed_shared)),
                "detail": t(
                    "lo_suggest_shared_licensed_detail",
                    count=len(licensed_shared),
                    amount=shared_waste,
                ),
                "priority": "medium",
                "savings": shared_waste,
            }
        )

    # 2. Over-provisioned SKUs: purchased > assigned (unused seats being paid for)
    for lic in licenses:
        unused_count = lic["total"] - lic["used"]
        if unused_count > 5 and lic["total"] > 0 and lic["pct"] < 70:
            price = _SKU_MONTHLY_PRICE.get(lic["part"], 0)
            waste = unused_count * price
            over_provisioned.append(
                {
                    "part": lic["part"],
                    "name": _sku_friendly(lic["part"]),
                    "used": lic["used"],
                    "total": lic["total"],
                    "unused": unused_count,
                    "monthly_waste": waste,
                }
            )
            if waste > 0:
                total_waste += waste
                suggestions.append(
                    {
                        "type": "over_provisioned",
                        "title": t("lo_suggest_reduce_sku", part=_sku_friendly(lic["part"])),
                        "detail": t(
                            "lo_suggest_reduce_sku_detail",
                            part=_sku_friendly(lic["part"]),
                            unused=unused_count,
                            used=lic["used"],
                            total=lic["total"],
                            amount=waste,
                        ),
                        "priority": "medium",
                        "savings": waste,
                    }
                )

    # 3. Potential E5 -> E3 downgrades
    # If E5 SKUs exist, flag as potential downgrade opportunity for review
    e5_licenses = [lic for lic in licenses if lic["part"] in _E5_SKUS]
    for e5 in e5_licenses:
        price_diff = _SKU_MONTHLY_PRICE.get(e5["part"], 580) - 380  # E5-E3 price gap
        if e5["used"] > 0 and price_diff > 0:
            downgrade_candidates.append(
                {
                    "part": e5["part"],
                    "name": _sku_friendly(e5["part"]),
                    "users": e5["used"],
                    "potential_saving_per_user": price_diff,
                    "potential_saving_total": e5["used"] * price_diff,
                }
            )
            suggestions.append(
                {
                    "type": "downgrade",
                    "title": t("lo_suggest_downgrade", part=_sku_friendly(e5["part"])),
                    "detail": t(
                        "lo_suggest_downgrade_detail",
                        part=_sku_friendly(e5["part"]),
                        users=e5["used"],
                        saving=price_diff,
                        total=e5["used"] * price_diff,
                    ),
                    "priority": "low",
                    "savings": e5["used"] * price_diff,
                }
            )

    # Sort suggestions by savings descending
    suggestions.sort(key=lambda s: s.get("savings", 0), reverse=True)

    # Distinguish *why* stale data is unavailable so the report can be honest:
    #   - file missing entirely → audit didn't collect it (toolkit gap or
    #     missing AuditLog.Read.All consent), NOT a licensing problem
    #   - file present with "NOTE:" → audit ran but tenant lacks P1
    has_stale_data = bool(stale_text.strip()) and "NOTE:" not in stale_text
    if not stale_text.strip():
        no_data_reason = "not_collected"
    elif "NOTE:" in stale_text:
        no_data_reason = "license_p1_missing"
    else:
        no_data_reason = None

    return {
        "total_waste_estimate": total_waste,
        "unused_licenses": unused_licenses,
        "over_provisioned": over_provisioned,
        "downgrade_candidates": downgrade_candidates,
        "optimization_suggestions": suggestions,
        "has_data": has_stale_data,
        "no_data_reason": no_data_reason,
    }


def _parse_usage(summary_text: str, detail_text: str) -> dict:
    """Licence usage, which the licence inventory alone cannot report.

    subscribedSkus says how many seats are assigned. It says nothing about
    whether anyone signed into them, and "106 of 106 assigned" reads as
    healthy right up until you learn a fifth of them have not been touched
    in a quarter.
    """
    result = {
        "total": 0,
        "active": 0,
        "no_activity": 0,
        "licensed_idle": 0,
        "period_days": 90,
        "concealed": False,
        "has_data": False,
        "unavailable": False,
        "unavailable_reason": "",
    }
    if _evidence_unavailable(summary_text) and _evidence_unavailable(detail_text):
        if (summary_text or detail_text or "").strip():
            result["unavailable"] = True
            result["unavailable_reason"] = _first_prose_line(detail_text) or _first_prose_line(
                summary_text
            )
        return result

    fields = {
        "total": "total",
        "active users": "active",
        "no activity": "no_activity",
        "licensed without activity": "licensed_idle",
        "period days": "period_days",
    }
    for line in (summary_text or "").splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key == "names concealed":
            result["concealed"] = val.lower() == "yes"
            result["has_data"] = True
        elif key in fields:
            try:
                result[fields[key]] = int(val)
                result["has_data"] = True
            except ValueError:
                pass
    return result
