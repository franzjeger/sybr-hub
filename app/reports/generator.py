"""Report generator — technical and customer-facing HTML/PDF reports."""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import get_branding, get_logo_path
from app.modules.base import SectionResult, SectionStatus
from app.reports.i18n import T

log = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _logo_b64(filename: str) -> str:
    """Return base64 data URI for a logo file."""
    logo_dir = Path(__file__).parent.parent.parent / "Logo-Branding"
    path = logo_dir / filename
    if not path.exists():
        return ""
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode()
    return f"data:image/png;base64,{b64}"


def _custom_logo_b64() -> str:
    """Return base64 data URI for the custom logo if it exists, else fallback to bundled logo."""
    custom = get_logo_path()
    if custom:
        data = custom.read_bytes()
        b64 = base64.b64encode(data).decode()
        return f"data:image/png;base64,{b64}"
    # Fallback to bundled logo
    return _logo_b64("300 x 86.png")


def _custom_logo_dark_b64() -> str:
    """Return base64 data URI for the dark-theme logo.

    If a custom logo is uploaded, use it for both themes (user only uploads one).
    Otherwise, use the bundled dark variant if available, falling back to the standard logo.
    """
    custom = get_logo_path()
    if custom:
        data = custom.read_bytes()
        b64 = base64.b64encode(data).decode()
        return f"data:image/png;base64,{b64}"
    # Try dark variant first, fall back to standard
    dark = _logo_b64("Sybr Dark.png")
    return dark if dark else _logo_b64("300 x 86.png")


def _get_app_version() -> str:
    """Return app version string for report footers."""
    try:
        from app.core.version import get_version
        v = get_version()
        return v if v.startswith("v") else f"v{v}"
    except Exception:
        return "v0.2.0"


def _jinja_env() -> Environment:
    return Environment(
        loader        = FileSystemLoader(str(_TEMPLATES_DIR), encoding="utf-8"),
        autoescape    = select_autoescape(["html"]),
        trim_blocks   = True,
        lstrip_blocks = True,
    )


# ── Data parsers ───────────────────────────────────────────────────────────────

def _parse_secure_score(text: str) -> dict:
    m = re.search(r"Score\s*:\s*([\d.]+)\s*/\s*([\d.]+)\s*\(([\d.]+)%\)", text)
    if not m:
        return {"current": 0, "max": 0, "pct": 0, "improvements": [], "has_data": False}
    current, max_, pct = float(m.group(1)), float(m.group(2)), float(m.group(3))

    improvements = []
    in_table = False
    for line in text.splitlines():
        if "Top 20 Improvement" in line:
            in_table = True
            continue
        if in_table and line.strip() and not line.strip().startswith("-") and not line.strip().startswith("="):
            parts = line.strip().rsplit(None, 2)
            if len(parts) >= 2:
                try:
                    score_pct = float(parts[-2].replace("%", ""))
                    name = parts[0].strip()
                    if name and score_pct > 0:
                        improvements.append({"name": name, "pct": score_pct})
                except (ValueError, IndexError):
                    pass
        if len(improvements) >= 10:
            break

    return {"current": current, "max": max_, "pct": pct, "improvements": improvements, "has_data": True}


def _parse_user_counts(text: str) -> dict:
    result = {"total": 0, "enabled": 0, "disabled": 0, "guests": 0, "hybrid": 0, "cloud": 0,
              "has_data": False}
    for line in text.splitlines():
        for key, field in [
            ("Total users", "total"), ("Enabled", "enabled"), ("Disabled", "disabled"),
            ("Guest accounts", "guests"), ("Hybrid (synced)", "hybrid"), ("Cloud-only", "cloud"),
        ]:
            if key in line and ":" in line:
                try:
                    result[field] = int(line.split(":")[-1].strip())
                except ValueError:
                    pass
    # If we found at least one nonzero value or any tokens parsed, mark as having data.
    # An audit that aborted on the User.Read.All gap leaves an empty file here.
    result["has_data"] = bool(text.strip()) and (result["total"] > 0 or result["enabled"] > 0)
    return result


def _parse_mfa(text: str, ca_analysis_text: str, results: list[SectionResult]) -> dict:
    """Parse MFA coverage from mfa_methods.txt and CA analysis.

    A user is 'MFA covered' if they have MFA methods registered
    OR are covered by a Conditional Access policy that enforces MFA.
    """
    # Parse MFA methods report — supports multiple formats:
    # 1. Pipe-delimited: "Name | UPN | MFA:YES | Methods: ..."
    # 2. Column-aligned:  "Name  UPN  YES  YES  NO  Methods"
    total = 0
    mfa_registered = 0
    ca_covered = 0
    ca_excluded = 0
    fully_unprotected = 0
    effectively_covered = 0

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("-") or "Display Name" in stripped or "MFA METHOD" in stripped:
            continue

        has_mfa = False
        has_ca = False
        is_excluded = False

        if "|" in stripped:
            # Pipe-delimited format: "Name | UPN | MFA:YES | CA:YES | ..."
            parts = [p.strip() for p in stripped.split("|")]
            for p in parts:
                if p.startswith("MFA:"):
                    has_mfa = "YES" in p
                elif p.startswith("CA:"):
                    has_ca = "YES" in p
                elif p.startswith("CA_EXCL:") or p.startswith("EXCL:"):
                    is_excluded = "YES" in p
            # Old format without CA column: "Name | UPN | MFA:YES | Methods: ..."
            if any(p.startswith("MFA:") for p in parts):
                total += 1
            else:
                continue
        else:
            # Space-aligned columnar format
            cols = re.split(r'\s{2,}', stripped)
            if len(cols) < 3:
                continue
            # Look for YES/NO in the columns
            found_yn = False
            for c in cols[2:]:
                if c.strip() in ("YES", "NO"):
                    found_yn = True
                    break
            if not found_yn:
                continue
            total += 1
            has_mfa = "YES" in cols[2] if len(cols) > 2 else False
            has_ca = "YES" in cols[3] if len(cols) > 3 else False
            is_excluded = "YES" in cols[4] if len(cols) > 4 else False

        if has_mfa:
            mfa_registered += 1
        if has_ca:
            ca_covered += 1
        if is_excluded:
            ca_excluded += 1
        if not has_mfa and not has_ca:
            fully_unprotected += 1
        if has_mfa or (has_ca and not is_excluded):
            effectively_covered += 1

    # Also parse CA analysis for coverage stats if available
    ca_analysis_covered = 0
    ca_analysis_excluded = 0
    ca_analysis_not_covered = 0
    if ca_analysis_text:
        m = re.search(r'Effectively covered.*?:\s*(\d+)', ca_analysis_text)
        if m:
            ca_analysis_covered = int(m.group(1))
        m = re.search(r'Users covered by CA MFA.*?:\s*(\d+)', ca_analysis_text)
        if m and not ca_analysis_covered:
            ca_analysis_covered = int(m.group(1))
        m = re.search(r'excluded from CA MFA\s*:\s*(\d+)', ca_analysis_text)
        if m:
            ca_analysis_excluded = int(m.group(1))
        m = re.search(r'NOT covered.*?\((\d+)\)', ca_analysis_text)
        if m:
            ca_analysis_not_covered = int(m.group(1))

    # Use the best available data — CA analysis as fallback when MFA methods empty
    if total == 0 and ca_analysis_covered > 0:
        effectively_covered = ca_analysis_covered
        ca_covered = ca_analysis_covered
        ca_excluded = ca_analysis_excluded
        total = ca_analysis_covered + ca_analysis_not_covered
        # If we still don't have total, covered IS the total we know about
        if total == 0:
            total = ca_analysis_covered

    pct = (effectively_covered / total * 100) if total > 0 else 0
    no_mfa = total - effectively_covered

    # Build per-user detail list for drill-down
    users_detail: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("-") or "Display Name" in stripped or "MFA METHOD" in stripped:
            continue
        if "|" in stripped:
            parts = [p.strip() for p in stripped.split("|")]
            u_has_mfa = any("YES" in p for p in parts if p.startswith("MFA:"))
            u_has_ca = any("YES" in p for p in parts if p.startswith("CA:"))
            u_excluded = any("YES" in p for p in parts if p.startswith("CA_EXCL:") or p.startswith("EXCL:"))
            u_methods = ""
            for p in parts:
                if p.startswith("Methods:"):
                    u_methods = p.replace("Methods:", "").strip()
            u_name = parts[0] if parts else ""
            u_upn = parts[1] if len(parts) > 1 else ""
        else:
            cols = re.split(r'\s{2,}', stripped)
            if len(cols) < 3:
                continue
            found_yn = any(c.strip() in ("YES", "NO") for c in cols[2:])
            if not found_yn:
                continue
            u_name = cols[0].strip()
            u_upn = cols[1].strip() if len(cols) > 1 else ""
            u_has_mfa = "YES" in cols[2] if len(cols) > 2 else False
            u_has_ca = "YES" in cols[3] if len(cols) > 3 else False
            u_excluded = "YES" in cols[4] if len(cols) > 4 else False
            u_methods = cols[5].strip() if len(cols) > 5 else ""

        u_protected = u_has_mfa or (u_has_ca and not u_excluded)
        users_detail.append({
            "name": u_name,
            "upn": u_upn,
            "has_mfa": u_has_mfa,
            "has_ca": u_has_ca,
            "ca_excluded": u_excluded,
            "methods": u_methods if u_methods and u_methods != "(none)" else "",
            "protected": u_protected,
        })

    return {
        "covered": effectively_covered,
        "total": total,
        "pct": round(pct, 1),
        "no_mfa": max(0, no_mfa),
        "mfa_registered": mfa_registered,
        "ca_covered": ca_covered,
        "ca_excluded": ca_excluded,
        "fully_unprotected": fully_unprotected,
        "users": users_detail,
        "has_data": total > 0,
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
            part  = parts[0]
            used  = int(parts[1])
            total = int(parts[2])
            pct   = float(parts[3].replace("%", ""))
        except (ValueError, IndexError):
            continue
        warn = pct >= 90 and total > 0
        licenses.append({
            "part": part, "used": used, "total": total,
            "pct": pct, "warn": warn,
        })
    return licenses


# ── SKU pricing estimates (monthly per-user NOK, approximate list prices) ──
_SKU_MONTHLY_PRICE: dict[str, int] = {
    "SPE_E5": 580,                      # Microsoft 365 E5
    "SPE_E3": 380,                      # Microsoft 365 E3
    "ENTERPRISEPREMIUM": 580,           # Office 365 E5
    "ENTERPRISEPACK": 260,              # Office 365 E3
    "ENTERPRISEPACK_FACULTY": 260,
    "STANDARDPACK": 100,                # Office 365 E1
    "EMS_E5": 170,                      # EMS E5
    "EMS_E3_RMS_adhoc": 110,
    "EMSPREMIUM": 170,                  # EMS E5
    "AAD_PREMIUM_P2": 110,
    "AAD_PREMIUM": 70,
    "POWER_BI_PRO": 100,
    "POWER_BI_PREMIUM_PER_USER": 200,
    "PROJECTPREMIUM": 550,              # Project Plan 5
    "PROJECTPROFESSIONAL": 300,         # Project Plan 3
    "VISIOCLIENT": 150,                 # Visio Plan 2
    "Microsoft_365_Copilot": 300,       # Copilot
    "FLOW_PER_USER": 150,
    "POWERAPPS_PER_USER": 200,
    "STREAM": 0,                        # often free / included
    "TEAMS_EXPLORATORY": 0,
}

# E5 SKUs and their E3 equivalents (for potential downgrade detection)
_E5_SKUS = {"SPE_E5", "ENTERPRISEPREMIUM"}
_E3_SKUS = {"SPE_E3", "ENTERPRISEPACK"}


def _parse_stale_accounts(text: str) -> list[dict]:
    """Parse 03b_stale_accounts.txt into a list of stale user dicts."""
    accounts: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("-") or "Display Name" in stripped or "STALE" in stripped or "NOTE:" in stripped or "Stale accounts" in stripped:
            continue
        # Format: Name(35)  UPN(45)  LastSignIn(22)  Days(5)  Licensed(8)
        cols = re.split(r'\s{2,}', stripped)
        if len(cols) >= 4:
            name = cols[0].strip()
            upn = cols[1].strip()
            licensed_str = cols[-1].strip() if len(cols) >= 5 else "No"
            days_str = cols[-2].strip() if len(cols) >= 5 else cols[-1].strip()
            try:
                days = int(days_str)
            except ValueError:
                days = None
            accounts.append({
                "name": name,
                "upn": upn,
                "days_inactive": days,
                "licensed": licensed_str.upper().startswith("Y"),
            })
    return accounts


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

    if licensed_stale:
        # Estimate cost: assume average license cost for stale users
        # Try to determine the most common paid SKU price
        sku_prices = []
        for lic in licenses:
            part = lic["part"]
            price = _SKU_MONTHLY_PRICE.get(part, 0)
            if price > 0 and lic["used"] > 0:
                sku_prices.append(price)
        avg_price = int(sum(sku_prices) / len(sku_prices)) if sku_prices else 300
        waste_amount = len(licensed_stale) * avg_price

        for s in licensed_stale:
            days_label = (
                str(s["days_inactive"]) + " " + t.lo_days
                if s["days_inactive"] is not None
                else t.lo_never_signed_in
            )
            unused_licenses.append({
                "name": s["name"],
                "upn": s["upn"],
                "days_inactive": s["days_inactive"],
                "days_label": days_label,
            })
        total_waste += waste_amount

        suggestions.append({
            "type": "unused",
            "title": t("lo_suggest_remove_unused", count=len(licensed_stale)),
            "detail": t("lo_suggest_remove_unused_detail", count=len(licensed_stale), amount=waste_amount),
            "priority": "high",
            "savings": waste_amount,
        })

    # 2. Over-provisioned SKUs: purchased > assigned (unused seats being paid for)
    for lic in licenses:
        unused_count = lic["total"] - lic["used"]
        if unused_count > 5 and lic["total"] > 0 and lic["pct"] < 70:
            price = _SKU_MONTHLY_PRICE.get(lic["part"], 0)
            waste = unused_count * price
            over_provisioned.append({
                "part": lic["part"],
                "used": lic["used"],
                "total": lic["total"],
                "unused": unused_count,
                "monthly_waste": waste,
            })
            if waste > 0:
                total_waste += waste
                suggestions.append({
                    "type": "over_provisioned",
                    "title": t("lo_suggest_reduce_sku", part=lic["part"]),
                    "detail": t("lo_suggest_reduce_sku_detail",
                                part=lic["part"], unused=unused_count,
                                used=lic["used"], total=lic["total"],
                                amount=waste),
                    "priority": "medium",
                    "savings": waste,
                })

    # 3. Potential E5 -> E3 downgrades
    # If E5 SKUs exist, flag as potential downgrade opportunity for review
    e5_licenses = [l for l in licenses if l["part"] in _E5_SKUS]
    for e5 in e5_licenses:
        price_diff = _SKU_MONTHLY_PRICE.get(e5["part"], 580) - 380  # E5-E3 price gap
        if e5["used"] > 0 and price_diff > 0:
            downgrade_candidates.append({
                "part": e5["part"],
                "users": e5["used"],
                "potential_saving_per_user": price_diff,
                "potential_saving_total": e5["used"] * price_diff,
            })
            suggestions.append({
                "type": "downgrade",
                "title": t("lo_suggest_downgrade", part=e5["part"]),
                "detail": t("lo_suggest_downgrade_detail",
                            part=e5["part"], users=e5["used"],
                            saving=price_diff, total=e5["used"] * price_diff),
                "priority": "low",
                "savings": e5["used"] * price_diff,
            })

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


def _parse_spf_dmarc(text: str) -> list[dict]:
    domains = []
    current: dict = {}
    prev_key = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Domain :"):
            if current:
                domains.append(current)
            current = {"domain": stripped.split(":", 1)[1].strip()}
            prev_key = ""
        elif stripped.startswith("SPF") and ":" in stripped and current:
            current["spf"] = stripped.split(":", 1)[1].strip()
            prev_key = "spf"
        elif stripped.startswith("DMARC") and ":" in stripped and current:
            current["dmarc"] = stripped.split(":", 1)[1].strip()
            prev_key = "dmarc"
        elif prev_key == "spf" and stripped.startswith("v=spf1") and current:
            current["spf_record"] = stripped
            prev_key = ""
        elif prev_key == "dmarc" and (stripped.startswith("v=DMARC1") or stripped == "(none)") and current:
            current["dmarc_record"] = stripped if stripped != "(none)" else ""
            prev_key = ""
        elif stripped.startswith("DKIM") and ":" in stripped and current:
            val = stripped.split(":", 1)[1].strip()
            low = stripped.lower()
            if "sel1" in low or "(m365)" in low or "dkim1" not in current:
                current["dkim1"] = val
            elif "sel2" in low or "dkim2" not in current:
                current["dkim2"] = val
            if "found" in low:
                current["dkim_found"] = val
            prev_key = ""
        elif stripped.startswith("MTA-STS") and current:
            current["mta_sts"] = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
            prev_key = ""
        else:
            prev_key = ""
    if current:
        domains.append(current)
    return domains


# Domains to exclude from SPF/DMARC compliance checks — these are either
# Microsoft infrastructure domains or third-party service domains where
# the customer has no control over DNS records.
_IGNORED_DOMAIN_SUFFIXES = (
    ".onmicrosoft.com",
    ".mail.onmicrosoft.com",
    ".sharepoint.com",
    # Anti-spam / anti-phishing gateway domains (no customer DNS control)
    ".inkyphishfence.com",
    ".mimecast.com",
    ".pphosted.com",       # Proofpoint
    ".barracudanetworks.com",
)


def _is_audit_relevant_domain(domain: str) -> bool:
    """Return True if a domain should be included in SPF/DMARC compliance checks."""
    d = domain.lower()
    return not any(d.endswith(suffix) for suffix in _IGNORED_DOMAIN_SUFFIXES)


def _parse_ca_policies(text: str) -> dict:
    enabled = disabled = report_only = 0
    # Detect whether the audit produced a report (banner present) so a
    # tenant with zero CA policies — legitimate for tenants without Entra
    # ID Premium — isn't conflated with "the fetch failed". This is the
    # difference between CIS 1.1.4 reporting `fail` ("no CA policies, but
    # you should configure them") vs `info` ("we couldn't even check").
    audit_succeeded = (
        "CONDITIONAL ACCESS POLICIES" in text
        or "Error fetching CA policies" not in text and bool(text.strip())
    ) if text.strip() else False
    for line in text.splitlines():
        l = line.lower().strip()
        # Support both pipe-delimited ("enabled | PolicyName | ...") and
        # bracket format ("[enabled   ] PolicyName ...")
        if not l or l.startswith("=") or l.startswith("-") or "state" in l and "policy" in l:
            continue
        if l.startswith("[enabled"):
            enabled += 1
        elif l.startswith("[disabled"):
            disabled += 1
        elif l.startswith("[reportonly") or l.startswith("[report_only") or l.startswith("[enabledforr"):
            report_only += 1
        # Legacy pipe format
        elif "|" in line:
            if "enabled" in l and "disabled" not in l and "reportonly" not in l.replace(" ", ""):
                enabled += 1
            elif "disabled" in l:
                disabled += 1
            elif "reportonly" in l.replace(" ", ""):
                report_only += 1
    total = enabled + disabled + report_only
    return {
        "enabled": enabled,
        "disabled": disabled,
        "report_only": report_only,
        "has_data": audit_succeeded or total > 0,
    }


def _parse_admin_roles(text: str) -> dict:
    roles: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("-") or "ADMIN ROLE" in stripped or ("Role" in stripped and "Display Name" in stripped):
            continue

        # Format 1: pipe-delimited "Role | User | email"
        if "|" in stripped:
            parts = [p.strip() for p in stripped.split("|")]
            if len(parts) >= 3:
                roles.append({"role": parts[0], "user": parts[1], "email": parts[2]})
            continue

        # Format 2: columnar "Role                User                email@domain"
        cols = re.split(r'\s{2,}', stripped)
        if len(cols) >= 3:
            # Last column should look like an email or UPN
            if "@" in cols[-1]:
                roles.append({"role": cols[0], "user": cols[1], "email": cols[-1]})
            elif len(cols) >= 2:
                roles.append({"role": cols[0], "user": " ".join(cols[1:-1]) if len(cols) > 2 else cols[1], "email": cols[-1]})
    ga_count = sum(1 for r in roles if r["role"] == "Global Administrator")
    role_counts: dict[str, int] = {}
    for r in roles:
        role_counts[r["role"]] = role_counts.get(r["role"], 0) + 1
    role_summary = sorted(
        [{"role": k, "count": v} for k, v in role_counts.items()],
        key=lambda x: (-x["count"], x["role"]),
    )
    global_admin_users = [r for r in roles if r["role"] == "Global Administrator"]
    return {
        "roles": roles,
        "global_admin_count": ga_count,
        "global_admin_users": global_admin_users,
        "total_assignments": len(roles),
        "unique_roles": len(role_counts),
        "role_summary": role_summary,
        "has_data": len(roles) > 0,
    }


def _parse_intune_devices(count_text: str, detail_text: str) -> dict:
    result = {"total": 0, "windows": 0, "ios": 0, "android": 0, "macos": 0,
              "compliant": 0, "noncompliant": 0, "unknown": 0,
              "compliance_pct": 0.0, "devices": []}

    # Track whether the audit produced a parseable report at all — even a
    # zero-device tenant gets the "INTUNE DEVICE COUNT SUMMARY" banner from
    # the collector. Without this signal, a small M365-only tenant with no
    # Intune-enrolled devices would be reported as "Intune-data utilgjengelig"
    # in data_quality_issues, when in fact the audit completed fine and
    # measured zero devices.
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
            result["devices"].append({
                "name": parts.get("name", parts.get("devicename", "")),
                "os": parts.get("os", ""),
                "user": parts.get("user", parts.get("userprincipalname", "")),
                "compliance": parts.get("compliance", parts.get("compliancestate", "")),
                "enrolled": parts.get("enrolled", parts.get("enrolleddatetime", "")),
            })
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

            for line in lines[header_idx + 1:]:
                if not line.strip() or line.strip().startswith("=") or line.strip().startswith("-"):
                    continue
                if len(line) < col_compl + 5:
                    continue
                dev_name = line[2:col_os].strip() if col_os > 0 else line[:36].strip()
                os_name = line[col_os:col_owner].strip() if col_owner > col_os else ""
                compliance = line[col_compl:col_sync].strip() if col_sync > col_compl else line[col_compl:].strip()
                enrolled = line[col_sync:].strip() if col_sync > 0 else ""
                owner = line[col_owner:col_compl].strip() if col_compl > col_owner else ""

                if dev_name and dev_name != "Device Name":
                    result["devices"].append({
                        "name": dev_name,
                        "os": os_name.split()[0] if os_name else "",
                        "user": owner,
                        "compliance": compliance,
                        "enrolled": enrolled,
                    })
    result["noncompliant_devices"] = [
        d for d in result["devices"]
        if d.get("compliance", "").lower() not in ("compliant", "")
    ]
    # has_data means "audit produced a parseable report" — NOT "≥1 device
    # exists". A small M365-only tenant with no Intune-enrolled devices
    # legitimately reports 0; that's a measurement, not a gap.
    result["has_data"] = audit_succeeded or result["total"] > 0 or len(result["devices"]) > 0
    return result


def _parse_sharepoint_settings(settings_text: str, sites_text: str, lang: str = "no") -> dict:
    t = T(lang)
    settings: dict[str, str] = {}
    for line in settings_text.splitlines():
        if ":" in line and not line.strip().startswith("==="):
            k, v = line.split(":", 1)
            settings[k.strip().lower()] = v.strip()

    sharing_raw = settings.get("sharing capability", "")
    sharing_map = {
        "disabled":                          ("ok",      t.sp_sharing_disabled),
        "existingexternalusersharingonly":    ("ok",      t.sp_sharing_existing_guests),
        "externalusersharingonly":            ("warning", t.sp_sharing_guests_only),
        "externaluserandguestsharing":        ("warning", t.sp_sharing_guests_anon),
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

    legacy_auth = settings.get("legacy auth", "").lower() == "true"

    site_count = 0
    personal_sites = 0
    for line in sites_text.splitlines():
        if line.strip() and not line.strip().startswith("==="):
            site_count += 1
            if "-my.sharepoint.com" in line.lower() or "personal" in line.lower():
                personal_sites += 1

    return {
        "sharing": sharing_raw,
        "sharing_level": sharing_level,
        "sharing_label": sharing_label,
        "legacy_auth": legacy_auth,
        "unmanaged_devices": settings.get("unmanaged devices", "").lower() == "true",
        "site_count": site_count,
        "personal_sites": personal_sites,
        "team_sites": max(0, site_count - personal_sites),
        "has_data": bool(settings) or site_count > 0,
    }


def _parse_oauth_grants(text: str, app_reg_text: str = "") -> dict:
    admin_consent: list[dict] = []
    app_permissions: list[dict] = []
    high_priv_keywords = {"fullcontrol", "readwrite.all", "accessasuser.all",
                          "manage", "rolemanagement.readwrite"}

    _UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
    section = ""
    in_data = False

    for line in text.splitlines():
        stripped = line.strip()
        if "ADMIN CONSENT" in stripped or "CONSENT GRANTS" in stripped or "TENANT-WIDE" in stripped:
            section = "admin"
            in_data = False
            continue
        elif "APPLICATION PERMISSIONS" in stripped:
            section = "app"
            in_data = False
            continue
        elif not stripped or stripped.startswith("==="):
            continue
        elif stripped.startswith("-"):
            in_data = True
            continue

        # Format 1: Pipe-delimited with "App:" prefix
        if "App:" in stripped:
            parts = stripped.split("|")
            app_name = parts[0].replace("App:", "").strip()
            if app_name.startswith("["):
                idx = app_name.find("]")
                if idx > 0:
                    app_name = app_name[idx + 1:].strip()
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
                    if p.startswith("Role:"): role = p.replace("Role:", "").strip()
                    elif p.startswith("Resource:"): resource = p.replace("Resource:", "").strip()
                app_permissions.append({"app": app_name, "role": role, "resource": resource})
            continue

        # Format 2: Columnar with GUIDs — "ClientID  ResourceID  Scopes"
        # Also: "Client (SP ID)    Resource ID    Scopes" header
        if "Client" in stripped and "Resource" in stripped and "Scope" in stripped:
            in_data = True
            continue

        cols = re.split(r'\s{2,}', stripped)
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
        m = re.search(r'\((\d+) total\)', app_reg_text)
        if m:
            app_reg_count = int(m.group(1))

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
    }


def _parse_groups(text: str) -> dict:
    """Parse 06_groups.txt into group metadata.

    The collector writes a 3-column table (Name, Type, Members) — accepts
    that as the primary format. A legacy pipe-delimited format is also
    accepted so historical audit runs still parse. Without the columnar
    branch the report silently reported zero groups for every tenant.
    """
    groups: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("-"):
            continue
        # Skip headers / section labels
        upper = stripped.upper()
        if upper.startswith("GROUPS") or "GROUP NAME" in upper:
            continue

        name = gtype = ""
        members = 0
        members_known = False

        # Legacy pipe-delimited format ("Name | Type | Members")
        if "|" in stripped:
            parts = [p.strip() for p in stripped.split("|")]
            if len(parts) >= 3:
                name = parts[0]
                gtype = parts[1].replace("Type:", "").strip()
                raw = parts[2].replace("Members:", "").strip()
                try:
                    members = int(raw)
                    members_known = True
                except ValueError:
                    members_known = False
        else:
            # Columnar: at least Name + Type + (Members or "N/A")
            cols = re.split(r'\s{2,}', stripped)
            if len(cols) < 3:
                continue
            name = cols[0].strip()
            # Members lives in the LAST column; type is everything between
            # (the type field can contain a single space, e.g. "Microsoft 365").
            raw = cols[-1].strip()
            try:
                members = int(raw)
                members_known = True
            except ValueError:
                # "N/A" or similar — fetch failed for this group, keep it
                # but don't claim a member count.
                members_known = False
            gtype = " ".join(cols[1:-1]).strip() if len(cols) > 2 else ""

        if name:
            groups.append({
                "name": name,
                "type": gtype,
                "members": members,
                "members_known": members_known,
            })

    by_type: dict[str, int] = {}
    empty = 0
    dynamic = 0
    for g in groups:
        by_type[g["type"]] = by_type.get(g["type"], 0) + 1
        # Only count a group as empty when we actually know its size — a
        # failed member-count fetch ("N/A") is not the same as zero.
        if g["members_known"] and g["members"] == 0:
            empty += 1
        if "Dynamic" in g["type"]:
            dynamic += 1

    return {
        "total": len(groups),
        "by_type": by_type,
        "empty_groups": empty,
        "dynamic_groups": dynamic,
        "groups": groups,
        "has_data": len(groups) > 0,
    }


def _parse_backup_coverage(file_contents: dict[str, str]) -> dict:
    """Cross-reference Azure VMs with backup protected items."""
    # Collect all VM names
    vm_names: list[str] = []
    for fname, content, sub_name in _find_azure_files(file_contents, "30_azure_vms"):
        if "cpu_metrics" in fname:
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-") or "VM Name" in stripped or "AZURE VIRTUAL" in stripped:
                continue
            cols = re.split(r'\s{2,}', stripped)
            if len(cols) >= 4:
                vm_names.append(cols[0])

    # Collect all backup protected item names.
    #
    # backup_data_read is the whole point of this block. Coverage is a
    # cross-reference between two independently-collected files, and if the
    # backup half is absent or errored then backed_up_names is empty and every
    # VM falls into vms_not_backed_up — a high-priority "these servers have no
    # backup" finding, naming each one, derived entirely from a file we never
    # read. An empty *successful* read is a different thing and still a real
    # finding.
    backed_up_names: set[str] = set()
    vault_names: set[str] = set()
    backup_data_read = False
    for fname, content, sub_name in _find_azure_files(file_contents, "52_azure_backup"):
        if not content.strip() or content.strip().startswith("Error:"):
            continue
        backup_data_read = True
        current_vault = ""
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("="):
                continue
            # Detect vault name lines
            if "vault" in stripped.lower() and (":" in stripped or "[" in stripped):
                vault_match = re.search(r'(?:Vault|vault)\s*[:\[]\s*(.+?)[\]\s]*$', stripped)
                if vault_match:
                    current_vault = vault_match.group(1).strip()
                    vault_names.add(current_vault)
                continue
            if stripped.startswith("-") or stripped.upper().startswith("NO ") or stripped.upper().startswith("NOTE"):
                continue
            # Parse protected item lines
            cols = re.split(r'\s{2,}', stripped)
            if cols:
                item_name = cols[0].strip()
                if item_name and item_name not in ("Name", "Protected Item", "Item Name", "Container"):
                    backed_up_names.add(item_name.lower())

    # Cross-reference — only meaningful when both halves were read.
    vms_total = len(vm_names)
    coverage_known = backup_data_read and vms_total > 0

    vms_backed_up = 0
    vms_not_backed_up: list[str] = []
    if coverage_known:
        for vm in vm_names:
            if vm.lower() in backed_up_names:
                vms_backed_up += 1
            else:
                vms_not_backed_up.append(vm)

    backup_pct = (vms_backed_up / vms_total * 100) if coverage_known else 0.0

    return {
        "vms_total": vms_total,
        "vms_backed_up": vms_backed_up,
        "vms_not_backed_up": vms_not_backed_up,   # empty unless coverage_known
        "backup_pct": round(backup_pct, 1),
        "vaults": len(vault_names),
        "coverage_known": coverage_known,
        "has_data": vms_total > 0 or len(vault_names) > 0,
    }


def _parse_signin_risk(file_contents: dict[str, str]) -> dict:
    """Parse sign-in activity and failure data for risk analysis."""
    result: dict = {
        "total_signins": 0,
        "unique_users": 0,
        "total_failures": 0,
        "top_failure_users": [],
        "top_failure_reasons": [],
        "brute_force_suspects": [],
        "has_data": False,
    }

    # Parse sign-in activity (05_signin_activity.txt)
    signin_text = file_contents.get("05_signin_activity.txt", "")
    if signin_text.strip():
        users_seen: set[str] = set()
        signin_count = 0
        for line in signin_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-"):
                continue
            if stripped.upper().startswith("NOTE") or stripped.upper().startswith("NO "):
                continue
            if ":" in stripped:
                key, val = stripped.split(":", 1)
                key_low = key.strip().lower()
                try:
                    v = int(val.strip().replace(",", ""))
                    if "total" in key_low and ("sign" in key_low or "login" in key_low):
                        result["total_signins"] = v
                        continue
                    elif "unique" in key_low and "user" in key_low:
                        result["unique_users"] = v
                        continue
                except ValueError:
                    pass
            cols = re.split(r'\s{2,}', stripped)
            if len(cols) >= 2:
                low_first = cols[0].lower()
                if low_first in ("user", "userprincipalname", "upn", "display name", "name"):
                    continue
                if "@" in cols[0] or "." in cols[0]:
                    users_seen.add(cols[0].lower())
                    signin_count += 1

        if result["total_signins"] == 0 and signin_count > 0:
            result["total_signins"] = signin_count
        if result["unique_users"] == 0 and users_seen:
            result["unique_users"] = len(users_seen)
        if signin_text.strip():
            result["has_data"] = True

    # Parse sign-in failures (05b_signin_failures.txt)
    failure_text = file_contents.get("05b_signin_failures.txt", "")
    if failure_text.strip():
        result["has_data"] = True
        failure_users: dict[str, int] = {}
        failure_reasons: dict[str, int] = {}
        total_failures = 0

        for line in failure_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-"):
                continue
            if stripped.upper().startswith("NOTE") or stripped.upper().startswith("NO "):
                continue
            if ":" in stripped:
                key, val = stripped.split(":", 1)
                key_low = key.strip().lower()
                try:
                    v = int(val.strip().replace(",", ""))
                    if "total" in key_low and ("fail" in key_low or "error" in key_low):
                        result["total_failures"] = v
                        continue
                except ValueError:
                    pass

            if "|" in stripped:
                parts = [p.strip() for p in stripped.split("|")]
                user = ""
                reason = ""
                count = 1
                for p in parts:
                    if "@" in p:
                        user = p
                    elif p.isdigit():
                        count = int(p)
                    else:
                        reason = p
                if user:
                    failure_users[user] = failure_users.get(user, 0) + count
                    total_failures += count
                if reason and reason.lower() not in ("reason", "error", "status"):
                    failure_reasons[reason] = failure_reasons.get(reason, 0) + count
            else:
                cols = re.split(r'\s{2,}', stripped)
                if len(cols) >= 2:
                    low_first = cols[0].lower()
                    if low_first in ("user", "userprincipalname", "upn", "display name", "name", "reason"):
                        continue
                    user = ""
                    reason = ""
                    count = 1
                    for c in cols:
                        if "@" in c:
                            user = c
                        elif c.isdigit():
                            count = int(c)
                        elif c.lower() not in ("true", "false", "yes", "no") and len(c) > 3:
                            reason = c
                    if user:
                        failure_users[user] = failure_users.get(user, 0) + count
                        total_failures += count
                    if reason:
                        failure_reasons[reason] = failure_reasons.get(reason, 0) + count

        if result["total_failures"] == 0:
            result["total_failures"] = total_failures

        sorted_users = sorted(failure_users.items(), key=lambda x: -x[1])
        result["top_failure_users"] = [{"user": u, "count": c} for u, c in sorted_users[:5]]

        sorted_reasons = sorted(failure_reasons.items(), key=lambda x: -x[1])
        result["top_failure_reasons"] = [{"reason": r, "count": c} for r, c in sorted_reasons[:5]]

        result["brute_force_suspects"] = [u for u, c in failure_users.items() if c >= 50]

    return result


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
    if labels_text.strip():
        for line in labels_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-"):
                continue
            if stripped.upper().startswith("NOTE") or stripped.upper().startswith("NO "):
                continue
            low = stripped.lower()
            if "label name" in low or "sensitivity label" in low or "purview" in low.replace("-", ""):
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
                result["sensitivity_labels"].append({"name": name, "priority": priority, "active": active})
            else:
                cols = re.split(r'\s{2,}', stripped)
                name = cols[0]
                priority = 0
                active = True
                for c in cols[1:]:
                    if c.isdigit():
                        priority = int(c)
                    elif c.lower() in ("inactive", "disabled", "false", "no"):
                        active = False
                if name and name.lower() not in ("name", "label", "priority", "status"):
                    result["sensitivity_labels"].append({"name": name, "priority": priority, "active": active})

        result["sensitivity_label_count"] = len(result["sensitivity_labels"])
        if result["sensitivity_label_count"] > 0:
            result["has_data"] = True

    # DLP policies (19d_purview_dlp_policies.txt)
    dlp_text = file_contents.get("19d_purview_dlp_policies.txt", "")
    if dlp_text.strip():
        for line in dlp_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-"):
                continue
            if stripped.upper().startswith("NOTE") or stripped.upper().startswith("NO "):
                continue
            low = stripped.lower()
            if "policy name" in low or "dlp polic" in low or "purview" in low.replace("-", ""):
                continue

            if "|" in stripped:
                parts = [p.strip() for p in stripped.split("|")]
                name = parts[0]
            else:
                cols = re.split(r'\s{2,}', stripped)
                name = cols[0]

            if name and name.lower() not in ("name", "policy", "status", "mode"):
                result["dlp_policies"].append({"name": name})

        result["dlp_policy_count"] = len(result["dlp_policies"])
        if result["dlp_policy_count"] > 0:
            result["has_data"] = True

    # Retention policies (19e_purview_retention_policies.txt)
    retention_text = file_contents.get("19e_purview_retention_policies.txt", "")
    if retention_text.strip():
        for line in retention_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-"):
                continue
            if stripped.upper().startswith("NOTE") or stripped.upper().startswith("NO "):
                continue
            low = stripped.lower()
            if "policy name" in low or "retention polic" in low or "purview" in low.replace("-", ""):
                continue

            if "|" in stripped:
                parts = [p.strip() for p in stripped.split("|")]
                name = parts[0]
            else:
                cols = re.split(r'\s{2,}', stripped)
                name = cols[0]

            if name and name.lower() not in ("name", "policy", "status", "mode"):
                result["retention_policies"].append({"name": name})

        result["retention_policy_count"] = len(result["retention_policies"])
        if result["retention_policy_count"] > 0:
            result["has_data"] = True

    return result


def _find_azure_files(file_contents: dict[str, str], prefix: str) -> list[tuple[str, str, str]]:
    """Find all Azure files matching a prefix, with or without subscription suffix.

    Returns list of (filename, content, subscription_name).
    Matches both '30_azure_vms.txt' and '30_azure_vms_Corp-Backend-01.txt'.
    """
    base = prefix.replace(".txt", "")
    matches = []
    for fname, content in file_contents.items():
        if not fname.startswith(base):
            continue
        rest = fname[len(base):]
        if rest == ".txt":
            matches.append((fname, content, ""))
        elif rest.startswith("_") and rest.endswith(".txt"):
            sub_name = rest[1:-4]  # strip leading _ and .txt
            matches.append((fname, content, sub_name))
    return matches


def _parse_azure_overview(file_contents: dict[str, str]) -> dict:
    """Parse Azure data files into a structured overview.

    Supports both single-subscription (e.g. 30_azure_vms.txt) and
    multi-subscription (e.g. 30_azure_vms_Corp-Backend-01.txt) file naming.
    Aggregates data across all subscriptions.
    """
    result: dict = {
        "subscriptions": [],
        "per_sub": [],          # per-subscription breakdown
        "total_resources": 0,
        "resource_types": {},   # type -> count (aggregated)
        "resource_groups": [],
        "vms": [],
        "storage_accounts": [],
        "nsgs": [],
        "advisor_recs": 0,
        "advisor_details": [],  # list of {"category", "impact", "description", "resource", "subscription"}
        "orphaned": 0,
        "orphaned_details": [],  # list of {"type", "name", "detail", "subscription"}
        "has_data": False,
    }

    # ── Subscriptions ──────────────────────────────────────────────────────
    sub_text = file_contents.get("45_azure_subscriptions.txt", "")
    for line in sub_text.splitlines():
        line = line.strip()
        if not line or line.startswith("=") or line.startswith("NOTE") or line.startswith("Falling") or line.startswith("To audit") or line.startswith("AZURE SUB"):
            continue
        if "[" in line and "]" in line:
            parts = line.rsplit("[", 1)
            state = parts[1].rstrip("]").strip()
            name_id = parts[0].strip()
            m = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', name_id)
            if m:
                sub_id = m.group(1)
                name = name_id[:m.start()].strip()
                result["subscriptions"].append({"name": name, "id": sub_id, "state": state})

    # ── Resource inventory (aggregate across all subs) ─────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "60_azure_resource_inventory_summary"):
        sub_resources = 0
        sub_types: dict[str, int] = {}
        sub_rgs: list[dict] = []
        in_types = False
        in_rgs = False

        for line in content.splitlines():
            if "By Type:" in line:
                in_types = True; in_rgs = False; continue
            elif "By Resource Group:" in line:
                in_rgs = True; in_types = False; continue
            elif line.strip().startswith("=") or line.strip().startswith("-") or not line.strip():
                continue
            elif "AZURE RESOURCE" in line:
                m = re.search(r'\((\d+) resources?\)', line)
                if m:
                    sub_resources = int(m.group(1))
                continue

            parts = line.rsplit(None, 1)
            if len(parts) == 2:
                try:
                    count = int(parts[1])
                    name = parts[0].strip()
                    if in_types and name and name not in ("Type", "Count"):
                        sub_types[name] = sub_types.get(name, 0) + count
                        result["resource_types"][name] = result["resource_types"].get(name, 0) + count
                    elif in_rgs and name and name not in ("Resource Group", "Count"):
                        sub_rgs.append({"name": name, "count": count})
                        result["resource_groups"].append({"name": f"{name} ({sub_name})" if sub_name else name, "count": count})
                except ValueError:
                    pass

        result["total_resources"] += sub_resources
        if sub_resources > 0 or sub_types:
            result["per_sub"].append({
                "name": sub_name or "Default",
                "resources": sub_resources,
                "types": sorted(sub_types.items(), key=lambda x: -x[1]),
                "rgs": sub_rgs,
            })

    # ── VMs (aggregate across all subs) ────────────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "30_azure_vms"):
        if "cpu_metrics" in fname:
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-") or "VM Name" in stripped or "AZURE VIRTUAL" in stripped:
                continue
            cols = re.split(r'\s{2,}', stripped)
            if len(cols) >= 4:
                result["vms"].append({
                    "name": cols[0],
                    "rg": cols[1] if len(cols) > 1 else "",
                    "location": cols[2] if len(cols) > 2 else "",
                    "os": cols[3] if len(cols) > 3 else "",
                    "size": cols[4] if len(cols) > 4 else "",
                    "status": cols[5] if len(cols) > 5 else "",
                    "subscription": sub_name,
                })

    # ── Storage accounts ───────────────────────────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "35_azure_storage"):
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-") or "Account Name" in stripped or "AZURE STORAGE" in stripped:
                continue
            cols = re.split(r'\s{2,}', stripped)
            if len(cols) >= 3:
                result["storage_accounts"].append({
                    "name": cols[0],
                    "sku": cols[1] if len(cols) > 1 else "",
                    "kind": cols[2] if len(cols) > 2 else "",
                    "subscription": sub_name,
                })

    # ── NSGs ───────────────────────────────────────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "32_azure_nsgs"):
        if "risky" in fname or "WARN" in fname:
            continue
        m = re.search(r'\((\d+) total\)', content)
        if m and int(m.group(1)) > 0:
            result["nsgs"].append({"subscription": sub_name, "count": int(m.group(1))})

    # ── Advisor recommendations (with details) ──────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "51_azure_advisor"):
        m = re.search(r'\((\d+) total\)', content)
        if m:
            result["advisor_recs"] += int(m.group(1))

        # Parse individual recommendations
        current_category = ""
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Category header: "[Cost]  (16 recommendations)"
            cat_m = re.match(r'\[(\w+)\]', line)
            if cat_m:
                current_category = cat_m.group(1)
                i += 1
                continue
            # Recommendation: "    [High    ]  Description text"
            rec_m = re.match(r'\[(\w+)\s*\]\s+(.+)', line)
            if rec_m:
                impact = rec_m.group(1)
                desc = rec_m.group(2).strip()
                resource = ""
                # Next line might be "Resource: ..."
                if i + 1 < len(lines) and "Resource:" in lines[i + 1]:
                    resource = lines[i + 1].strip().replace("Resource:", "").strip()
                    i += 1
                result["advisor_details"].append({
                    "category": current_category,
                    "impact": impact,
                    "description": desc,
                    "resource": resource,
                    "subscription": sub_name,
                })
            i += 1

    # Deduplicate advisor details (same description counted once, with count)
    seen: dict[str, dict] = {}
    for ad in result["advisor_details"]:
        key = f"{ad['category']}|{ad['description']}"
        if key in seen:
            seen[key]["count"] += 1
        else:
            seen[key] = {**ad, "count": 1}
    result["advisor_summary"] = sorted(
        seen.values(),
        key=lambda x: ({"High": 0, "Medium": 1, "Low": 2}.get(x["impact"], 3), x["category"]),
    )

    # ── Orphaned resources (with details) ──────────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "61_azure_orphaned_resources"):
        m = re.search(r'\((\d+) found\)', content)
        if m:
            result["orphaned"] += int(m.group(1))
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("=") or line.startswith("No orphaned") or "ORPHANED" in line:
                continue
            # Format: "DISK (unattached) : diskname  500 GB  Standard_LRS  RG: rg-name"
            type_m = re.match(r'(\w[\w\s]*?)\s*\((\w+)\)\s*:\s*(.+)', line)
            if type_m:
                result["orphaned_details"].append({
                    "type": type_m.group(1).strip(),
                    "status": type_m.group(2).strip(),
                    "detail": type_m.group(3).strip(),
                    "subscription": sub_name,
                })

    # Convert resource_types dict to sorted list
    result["resource_types_list"] = sorted(
        [{"type": k, "count": v} for k, v in result["resource_types"].items()],
        key=lambda x: -x["count"],
    )

    result["has_data"] = (
        result["total_resources"] > 0
        or len(result["vms"]) > 0
        or len(result["subscriptions"]) > 0
    )
    return result


def _parse_exchange_overview(file_contents: dict[str, str]) -> dict:
    """Parse Exchange data files into a structured overview."""
    result = {
        "mailbox_total": 0,
        "mailbox_user": 0,
        "mailbox_shared": 0,
        "transport_rules": 0,
        "connectors": 0,
        "antiphish_policies": [],
        "antispam_policies": [],
        "forwarding_count": 0,
        "external_forwarding": False,
        "inbox_rules_external": 0,
        "has_data": False,
    }

    # Mailbox counts — flexible key matching (same pattern as Intune parser)
    count_text = file_contents.get("20_exchange_mailboxes_count.txt", "")
    for line in count_text.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower().replace("-", "").replace(" ", "")
        try:
            v = int(val.strip())
        except ValueError:
            continue
        if "total" in key:
            result["mailbox_total"] = v
        elif key in ("user", "usermailbox", "usermailboxes"):
            result["mailbox_user"] = v
        elif key in ("shared", "sharedmailbox", "sharedmailboxes"):
            result["mailbox_shared"] = v

    # Transport rules — count non-empty, non-header lines
    transport_text = file_contents.get("21_exchange_transport_rules.txt", "")
    result["transport_rules"] = _count_data_lines(transport_text)

    # Connectors — count non-empty, non-header lines
    connectors_text = file_contents.get("22_exchange_connectors.txt", "")
    result["connectors"] = _count_data_lines(connectors_text)

    # Anti-phish policies — extract policy names
    antiphish_text = file_contents.get("23_exchange_antiphish.txt", "")
    result["antiphish_policies"] = _extract_policy_names(antiphish_text)

    # Anti-spam policies — extract policy names
    antispam_text = file_contents.get("24_exchange_antispam.txt", "")
    result["antispam_policies"] = _extract_policy_names(antispam_text)

    # Mailbox forwarding count
    fwd_text = file_contents.get("28_exchange_mailbox_forwarding.txt", "")
    result["forwarding_count"] = _count_data_lines(fwd_text)

    # External forwarding warning flag
    ext_fwd_text = file_contents.get("28b_exchange_external_forwarding_WARN.txt", "")
    result["external_forwarding"] = bool(ext_fwd_text and ext_fwd_text.strip())

    # Inbox rules with external forwarding
    inbox_rules_text = file_contents.get("29_exchange_inbox_rules_external_fwd.txt", "")
    result["inbox_rules_external"] = _count_data_lines(inbox_rules_text)

    result["has_data"] = (
        result["mailbox_total"] > 0
        or result["transport_rules"] > 0
        or len(result["antiphish_policies"]) > 0
        or result["forwarding_count"] > 0
    )
    return result


_HEADER_TOTAL_RE = re.compile(
    r'^[A-Z][^\(]*\(.*\b\d+\s+(total|found|events?)\b.*\)\s*$'
)
_BANNER_COUNT_RE = re.compile(r'\(\s*(\d+)\s+(?:total|found|events?)\b', re.IGNORECASE)


def _count_defender_policy_state(text: str) -> tuple[int, int]:
    """Walk the 27_exchange_defender_policies.txt file and return
    (safe_links_enabled, safe_attachments_enabled) counts.

    The Exchange collector writes each policy as a small block of
    `Key: Value` lines separated by blank lines. A previous version of
    the compliance check just matched the substring "safe links" /
    "safe attach" anywhere in the file, which counted a disabled policy
    as enabled. This helper parses the blocks and only counts entries
    whose PolicyType is SafeLinks* / SafeAttachments* AND Enabled is True.
    """
    safe_links = safe_attach = 0
    block: dict[str, str] = {}

    def _flush() -> None:
        nonlocal safe_links, safe_attach
        if not block:
            return
        ptype = block.get("policytype", "").lower()
        enabled = block.get("enabled", "").strip().lower() in ("true", "yes", "1")
        if not enabled:
            block.clear()
            return
        if "safelinks" in ptype.replace(" ", "") or "safe link" in ptype:
            safe_links += 1
        if "safeattach" in ptype.replace(" ", "") or "safe attach" in ptype:
            safe_attach += 1
        block.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("-"):
            _flush()
            continue
        if ":" in stripped:
            key, val = stripped.split(":", 1)
            block[key.strip().lower()] = val.strip()
    _flush()
    return safe_links, safe_attach


def _parse_banner_count(text: str) -> int | None:
    """Pull the authoritative count from a collector banner.

    Many audit files write `SECTION NAME  (N total)` as their header. That's
    the number the collector intended; trying to re-count by scanning data
    rows is error-prone because column headers and continuation lines look
    like data. Returns None if no banner is found, the int otherwise.
    """
    for line in text.splitlines():
        m = _BANNER_COUNT_RE.search(line)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return None


def _count_data_lines(text: str) -> int:
    """Count non-empty, non-header/separator lines in a text block.

    Skips the section banner ("TRANSPORT RULES  (5 total)"), table headers
    (a row whose tokens are all capitalised words), and the NOTE / NO prefix
    lines. Without skipping the "(N total)" banner the count is off by one
    every time — transport_rules, connectors and forwarding_count all read
    through this helper, so even a +1 here biases the entire Exchange
    overview.
    """
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("=") or stripped.startswith("-") or stripped.startswith("#"):
            continue
        if stripped.upper().startswith("NOTE") or stripped.upper().startswith("NO "):
            continue
        # Skip section banner like "TRANSPORT RULES  (5 total)" or "ALERTS  (12 found)"
        if _HEADER_TOTAL_RE.match(stripped):
            continue
        count += 1
    return count


def _extract_policy_names(text: str) -> list[str]:
    """Extract policy names from Exchange policy output."""
    names = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("-"):
            continue
        # Lines with "Name:" or "Policy:" prefix
        if ":" in stripped:
            key, val = stripped.split(":", 1)
            key_low = key.strip().lower()
            if key_low in ("name", "policy", "policyname"):
                val = val.strip()
                if val:
                    names.append(val)
                continue
        # Otherwise treat non-header lines as policy names
        if not stripped.upper().startswith("NOTE") and not stripped.upper().startswith("NO "):
            names.append(stripped)
    return names


def _is_error_payload(text: str) -> bool:
    """True if a section file holds a collector's error instead of its data.

    A section that fails writes the exception into the file it would otherwise
    have filled, so the file exists, is non-empty, and looks parseable. Every
    parser here then treats it as content.

    Matched on the first few lines only, and on the shapes the collectors
    actually emit. Files like 05b_signin_failures.txt and 18_risky_users.txt
    contain the word "error" in their *data* — they open with a header rule,
    and must not be blanked.
    """
    head = "\n".join(text.strip().splitlines()[:3]).lower()
    if not head:
        return False
    return (
        head.startswith("error:")
        or "client error '4" in head
        or "server error '5" in head
        or "query failed" in head
        or "fetch failed" in head
        or "collection failed" in head
    )


def _severity(status: str) -> str:
    s = status.upper()
    if s.startswith("ERROR") or "QUERY FAILED" in s:
        return "warning"  # transport error — an unanswered lookup is not a clean pass
    if "MISSING" in s or "CRITICAL" in s:
        return "critical"
    if "WEAK" in s or "WARN" in s or "QUARANTINE" in s or "NONE" in s:
        return "warning"
    return "ok"


def _parse_network_audit(file_contents: dict) -> dict:
    """Parse network audit data from saved quick-audit JSON files."""
    import json as _json
    result: dict = {"fortigate": None, "unifi": None, "has_data": False}
    # FortiGate
    fg_raw = file_contents.get("60_fortigate_audit.txt", "")
    if fg_raw.strip():
        try:
            result["fortigate"] = _json.loads(fg_raw)
            result["has_data"] = True
        except Exception:
            pass
    # UniFi
    uf_raw = file_contents.get("61_unifi_audit.txt", "")
    if uf_raw.strip():
        try:
            result["unifi"] = _json.loads(uf_raw)
            result["has_data"] = True
        except Exception:
            pass
    return result


def _is_open_wlan(wlan: dict) -> bool:
    """True only when this WLAN is positively identified as unencrypted.

    Reports are rendered from audit JSON saved on disk, so this has to cope
    with three vintages: files written before ``security_label`` existed,
    files where the controller never returned a security field at all, and
    current files. In every one of them, "we could not tell" must come back
    False — an open-WiFi finding is critical-priority and named by SSID in
    the report, so it has to rest on a reading.
    """
    from app.services.unifi_api import is_open_wlan_security

    label = wlan.get("security_label")
    if label is not None:
        return label == "Open"
    return is_open_wlan_security(wlan.get("security"))


def _compute_network_risk(network: dict) -> dict:
    """Compute network-specific risk factors. Returns {penalty, findings}."""
    penalty = 0
    findings: list[str] = []

    fg = network.get("fortigate")
    if fg and "error" not in fg:
        # Admin without 2FA
        admins_no_2fa = [a for a in fg.get("admins", []) if not a.get("two_factor")]
        if admins_no_2fa:
            penalty += min(5, len(admins_no_2fa) * 2)
            findings.append(f"{len(admins_no_2fa)} FortiGate-admin uten 2FA")
        # Allow-all policies
        allow_all = [w for w in fg.get("policy_warnings", []) if "allow-all" in w.lower()]
        if allow_all:
            penalty += min(5, len(allow_all) * 3)
            findings.append(f"{len(allow_all)} allow-all-regler")
        # No-logging policies
        no_log = [w for w in fg.get("policy_warnings", []) if "logging" in w.lower()]
        if no_log:
            penalty += min(3, len(no_log))
            findings.append(f"{len(no_log)} regler uten logging")

    uf = network.get("unifi")
    if uf and "error" not in uf:
        # Default credentials
        default_creds = uf.get("default_creds_count", 0)
        if default_creds:
            penalty += min(10, default_creds * 5)
            findings.append(f"{default_creds} enheter med standard-passord")
        # Outdated firmware
        outdated = uf.get("outdated_firmware_count", 0)
        eol = uf.get("eol_count", 0)
        if eol:
            penalty += min(5, eol * 3)
            findings.append(f"{eol} EOL-enheter")
        if outdated:
            penalty += min(3, outdated * 2)
            findings.append(f"{outdated} enheter med utdatert firmware")
        # Check for open WiFi in controller mode
        if uf.get("mode") == "controller":
            for w in uf.get("wlans", []):
                if _is_open_wlan(w) and w.get("enabled", True):
                    penalty += 5
                    findings.append("Åpent WiFi-nettverk")
                    break

    return {"penalty": min(15, penalty), "findings": findings}


def _compute_risk(
    secure_score: dict,
    mfa: dict,
    spf_dmarc: list[dict],
    all_warns: list[str],
    ext_fwd: str,
    risky_users: str,
    defender: str,
    admin_roles: dict | None = None,
    intune: dict | None = None,
    sharepoint: dict | None = None,
    oauth: dict | None = None,
    network: dict | None = None,
    lang: str = "no",
) -> dict:
    """Compute a security health score from 0 (worst) to 100 (best).

    Weight budget (100 points total):
      - MFA coverage:         35 pts
      - Secure Score:         20 pts
      - Email security:       10 pts
      - External forwarding:  10 pts  (critical finding)
      - Defender alerts:      10 pts  (critical finding)
      - Risky users:           5 pts
      - Admin roles:           5 pts
      - Intune compliance:     5 pts
      - SharePoint / OAuth:    variable (bonus deductions)
      - Network security:     15 pts  (FortiGate + UniFi findings)
    """
    score = 100
    data_quality_issues: list[str] = []  # Track missing/unverifiable data
    blocking_data_gaps: list[str] = []   # Gaps that invalidate the whole grade

    # ── MFA coverage (up to 35 pts) ──────────────────────────────────
    if mfa.get("has_data"):
        mfa_pct = mfa.get("pct", 0)
        no_mfa  = mfa.get("no_mfa", 0)
        mfa_penalty = round(35 * (1 - mfa_pct / 100))
        mfa_penalty_abs = min(35, no_mfa * 2)
        score -= max(mfa_penalty, mfa_penalty_abs)
    else:
        # MFA is the largest single weight (35/100). Without it, any computed
        # grade is fiction — flag as blocking so the grade renders as INVALID
        # rather than fabricating a B/70 from partial inputs.
        data_quality_issues.append("MFA-dekning utilgjengelig")
        blocking_data_gaps.append("MFA-dekning utilgjengelig — auditen mangler brukerdata (sjekk Graph-tillatelser)")

    # ── Secure Score (up to 20 pts) ──────────────────────────────────
    if secure_score.get("has_data"):
        ss_pct = secure_score.get("pct", 0)
        score -= round(20 * (1 - ss_pct / 100))
    else:
        data_quality_issues.append("Microsoft Secure Score utilgjengelig")

    # ── Email security (up to 10 pts) ────────────────────────────────
    email_penalty = 0
    for d in spf_dmarc:
        spf   = d.get("spf", "")
        dmarc = d.get("dmarc", "")
        if "MISSING" in spf or "CRITICAL" in spf:
            email_penalty = max(email_penalty, 10)
        elif "WEAK" in spf or "WARN" in spf:
            email_penalty = max(email_penalty, 5)
        if "MISSING" in dmarc:
            email_penalty = max(email_penalty, 8)
        elif "NONE" in dmarc:
            email_penalty = max(email_penalty, 5)
    score -= email_penalty

    # ── Admin roles (up to 5 pts) ────────────────────────────────────
    # Only score when we actually have role data — has_data=False means the
    # /directoryRoles fetch failed, so a 0-admin reading is missing data,
    # not "no admin sprawl". Same pattern repeats for SharePoint and OAuth.
    if admin_roles and admin_roles.get("has_data"):
        ga = admin_roles.get("global_admin_count", 0)
        if ga > 4:
            score -= 5
        elif ga > 2:
            score -= 3
    elif admin_roles is not None:
        data_quality_issues.append("Admin-roller utilgjengelig")

    # ── Intune compliance (up to 5 pts) ──────────────────────────────
    if intune and intune.get("has_data") and intune.get("total", 0) > 0:
        cpct = intune.get("compliance_pct", 0)
        if cpct < 50:
            score -= 5
        elif cpct < 80:
            score -= 3
    elif intune is not None and not intune.get("has_data"):
        data_quality_issues.append("Intune-data utilgjengelig")

    # ── SharePoint sharing ───────────────────────────────────────────
    if sharepoint and sharepoint.get("has_data"):
        if sharepoint.get("sharing_level") == "warning":
            score -= 3
        if sharepoint.get("legacy_auth"):
            score -= 2
    elif sharepoint is not None and not sharepoint.get("has_data"):
        data_quality_issues.append("SharePoint-konfigurasjon utilgjengelig")

    # ── OAuth high-privilege apps ────────────────────────────────────
    if oauth and oauth.get("has_data"):
        if len(oauth.get("high_privilege_apps", [])) > 5:
            score -= 3
    elif oauth is not None and not oauth.get("has_data"):
        data_quality_issues.append("OAuth-grants utilgjengelig")

    # ── Critical findings ────────────────────────────────────────────

    # External forwarding (up to 10 pts) — any active forwarding is severe
    if ext_fwd and ext_fwd.strip():
        # Count forwarding rules from lines (more rules = worse)
        fwd_lines = [l for l in ext_fwd.strip().splitlines()
                     if l.strip() and not l.strip().startswith("=") and not l.strip().startswith("-")]
        score -= min(10, max(5, len(fwd_lines) * 2))

    # Risky users (up to 5 pts)
    if risky_users and "No risky" not in risky_users and "not available" not in risky_users.lower() and "requires" not in risky_users.lower() and risky_users.strip():
        score -= 5

    # Defender alerts (up to 10 pts) — scale with number of alerts
    if defender and "No active" not in defender and defender.strip():
        alert_lines = [l for l in defender.strip().splitlines()
                       if l.strip() and not l.strip().startswith("=") and not l.strip().startswith("-")
                       and "alert" not in l.strip().lower().split(":")[:1]]
        alert_count = max(1, len(alert_lines))
        # 3 pts base + 1 per alert, capped at 10
        score -= min(10, 3 + alert_count)

    # ── Network security (up to 15 pts) ────────────────────────────
    if network and network.get("has_data"):
        net_risk = _compute_network_risk(network)
        score -= net_risk["penalty"]

    score = max(0, min(100, score))

    t = T(lang)

    # If essential inputs are missing, refuse to grade. Returning a number here
    # would be misleading — the score function literally cannot evaluate the
    # tenant. Consumers should display "Ufullstendige data" and the gap list.
    if blocking_data_gaps:
        return {
            "score": None,
            "grade": "?",
            "level": t.risk_level_invalid,
            "color": "gray",
            "data_quality_issues": data_quality_issues,
            "blocking_data_gaps": blocking_data_gaps,
            "has_full_data": False,
        }

    # ── Grade thresholds: A(80-100), B(60-79), C(40-59), D(20-39), F(0-19) ──
    if score >= 80:
        grade, level, color = "A", t.risk_level_good, "green"
    elif score >= 60:
        grade, level, color = "B", t.risk_level_satisfactory, "blue"
    elif score >= 40:
        grade, level, color = "C", t.risk_level_needs_action, "orange"
    elif score >= 20:
        grade, level, color = "D", t.risk_level_weak, "red"
    else:
        grade, level, color = "F", t.risk_level_critical, "darkred"

    return {
        "score": score,
        "grade": grade,
        "level": level,
        "color": color,
        "data_quality_issues": data_quality_issues,
        "blocking_data_gaps": [],
        "has_full_data": len(data_quality_issues) == 0,
    }


def _build_finding_rec_map(recs: list[dict]) -> dict[str, list[int]]:
    """Build a mapping from finding_id → list of recommendation indices (1-based)."""
    result: dict[str, list[int]] = {}
    for rec in recs:
        fid = rec.get("finding_id", "")
        if fid:
            result.setdefault(fid, []).append(rec.get("rec_index", 0))
    return result


def _build_recommendations(
    mfa: dict,
    spf_dmarc: list[dict],
    secure_score: dict,
    ext_fwd: str,
    risky_users: str,
    licenses: list[dict],
    admin_roles: dict | None = None,
    intune: dict | None = None,
    sharepoint: dict | None = None,
    oauth: dict | None = None,
    azure: dict | None = None,
    file_contents: dict | None = None,
    backup_coverage: dict | None = None,
    signin_risk: dict | None = None,
    network: dict | None = None,
    lang: str = "no",
) -> list[dict]:
    t = T(lang)
    recs = []

    # Only emit MFA recs if we actually measured MFA. Without data, "0 users
    # without MFA" would suppress the rec even though we don't know the truth.
    if mfa.get("has_data") and mfa.get("no_mfa", 0) > 0:
        # Build list of unprotected users from the MFA file
        unprotected = []
        fc = file_contents or {}
        for line in fc.get("04_mfa_methods.txt", "").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-") or "Display Name" in stripped or "MFA METHOD" in stripped:
                continue
            cols = re.split(r'\s{2,}', stripped)
            if len(cols) >= 5:
                has_mfa_col = "YES" in cols[2] if len(cols) > 2 else False
                has_ca_col = "YES" in cols[3] if len(cols) > 3 else False
                if not has_mfa_col and not has_ca_col:
                    upn = cols[1].strip() if len(cols) > 1 else cols[0]
                    name = cols[0].strip()
                    unprotected.append(f"{name} ({upn})")

        detail = t("rec_mfa_detail",
                    registered=mfa.get('mfa_registered', 0),
                    ca_covered=mfa.get('ca_covered', 0),
                    no_mfa=mfa['no_mfa'])
        recs.append({
            "priority": "critical",
            "finding_id": "finding-mfa",
            "title": t("rec_mfa_title", count=mfa['no_mfa']),
            "detail": detail,
            "effort": t.rec_effort_low,
            "sub_items": unprotected[:50],
            "doc_url": "https://learn.microsoft.com/en-us/entra/identity/authentication/concept-mfa-howitworks",
        })

    for d in spf_dmarc:
        if not _is_audit_relevant_domain(d.get("domain", "")):
            continue
        if "MISSING" in d.get("dmarc", "") or "WEAK" in d.get("dmarc", ""):
            recs.append({
                "priority": "high",
                "finding_id": "finding-email",
                "title": t("rec_dmarc_title", domain=d['domain']),
                "detail": t.rec_dmarc_detail,
                "effort": t.rec_effort_low,
                "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/office-365-security/email-authentication-dmarc-configure",
            })
            break

    for d in spf_dmarc:
        if not _is_audit_relevant_domain(d.get("domain", "")):
            continue
        if "MISSING" in d.get("spf", "") or "CRITICAL" in d.get("spf", ""):
            recs.append({
                "priority": "high",
                "finding_id": "finding-email",
                "title": t("rec_spf_title", domain=d['domain']),
                "detail": t.rec_spf_detail,
                "effort": t.rec_effort_low,
                "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/office-365-security/email-authentication-spf-configure",
            })
            break

    if ext_fwd and ext_fwd.strip():
        # Parse forwarding entries: "  UserName  →  smtp:external@example.com"
        fwd_items = []
        for line in ext_fwd.splitlines():
            line = line.strip()
            if "→" in line:
                parts = line.split("→", 1)
                mailbox = parts[0].strip()
                target = parts[1].strip().replace("smtp:", "").replace("SMTP:", "")
                fwd_items.append(f"{mailbox} → {target}")
        fwd_count = len(fwd_items) if fwd_items else t.rec_ext_fwd_unknown_count
        recs.append({
            "priority": "critical",
            "finding_id": "finding-fwd",
            "title": t("rec_ext_fwd_title", count=fwd_count),
            "detail": t.rec_ext_fwd_detail,
            "effort": t.rec_effort_immediate,
            "sub_items": fwd_items,
            "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/office-365-security/outbound-spam-policies-external-email-forwarding",
        })

    if risky_users and "No risky" not in risky_users and "not available" not in risky_users.lower() and "requires" not in risky_users.lower() and risky_users.strip():
        # Parse risky user entries from columnar format
        risky_items = []
        for line in risky_users.splitlines():
            line = line.strip()
            if not line or line.startswith("=") or line.startswith("-") or "UPN" in line or "RISKY" in line:
                continue
            cols = re.split(r'\s{2,}', line)
            if len(cols) >= 3:
                upn = cols[0].strip()
                level = cols[1].strip()
                state = cols[2].strip()
                risky_items.append(t("rec_risky_user_line", upn=upn, level=level, state=state))
        # Only emit the recommendation if we actually parsed at least one risky
        # user. The file may contain a header but no rows (e.g. when the audit
        # ran but no users currently match) — surfacing an empty "Risky users
        # detected" rec with no count/list would be a misleading false positive.
        if risky_items:
            title_suffix = t("rec_risky_users_suffix", count=len(risky_items))
            recs.append({
                "priority": "high",
                "finding_id": "finding-risky",
                "title": t("rec_risky_users_title", suffix=title_suffix),
                "detail": t.rec_risky_users_detail,
                "effort": t.rec_effort_low,
                "sub_items": risky_items,
                "doc_url": "https://learn.microsoft.com/en-us/entra/id-protection/howto-identity-protection-investigate-risk",
            })

    if secure_score.get("pct", 100) < 80 and secure_score.get("improvements"):
        prio = "high" if secure_score["pct"] < 50 else "medium"
        improvements = secure_score["improvements"]
        recs.append({
            "priority": prio,
            "finding_id": "finding-securescore",
            "title": t("rec_secure_score_title", pct=secure_score['pct'], count=len(improvements)),
            "detail": t("rec_secure_score_detail", pct=secure_score['pct'],
                        current=secure_score.get('current', 0), max=secure_score.get('max', 0)),
            "effort": t.rec_effort_medium,
            "sub_items": [f"{imp['name']} ({imp.get('category', '')})" for imp in improvements],
            "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/defender/microsoft-secure-score",
        })

    for lic in licenses:
        if lic["warn"]:
            recs.append({
                "priority": "medium",
                "title": t("rec_license_title", part=lic['part']),
                "detail": t("rec_license_detail", used=lic['used'], total=lic['total'], pct=lic['pct']),
                "effort": t.rec_effort_low,
            })

    # Admin roles
    if admin_roles and admin_roles.get("global_admin_count", 0) > 4:
        recs.append({
            "priority": "high",
            "finding_id": "finding-ga",
            "title": t("rec_ga_title", count=admin_roles['global_admin_count']),
            "detail": t.rec_ga_detail,
            "effort": t.rec_effort_medium,
            "doc_url": "https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/best-practices",
        })

    # Intune compliance
    if intune and intune.get("noncompliant", 0) > 0:
        prio = "high" if intune.get("compliance_pct", 100) < 50 else "medium"
        recs.append({
            "priority": prio,
            "finding_id": "finding-intune",
            "title": t("rec_intune_title", count=intune['noncompliant']),
            "detail": t("rec_intune_detail", pct=intune.get('compliance_pct', 0)),
            "effort": t.rec_effort_medium,
            "doc_url": "https://learn.microsoft.com/en-us/mem/intune/protect/device-compliance-get-started",
        })

    # SharePoint external sharing. _parse_sharepoint_settings defaults
    # sharing_level to "warning" for an unrecognised or absent "Sharing
    # Capability" value, so without the has_data gate an audit that never
    # reached SharePoint admin settings raised "external sharing is at its
    # most permissive level" against every tenant. _compute_risk already
    # gates on has_data for exactly this reason.
    if sharepoint and sharepoint.get("has_data") and sharepoint.get("sharing_level") == "warning":
        recs.append({
            "priority": "medium",
            "finding_id": "finding-sp",
            "title": t.rec_sp_sharing_title,
            "detail": t.rec_sp_sharing_detail,
            "effort": t.rec_effort_low,
            "doc_url": "https://learn.microsoft.com/en-us/sharepoint/turn-external-sharing-on-or-off",
        })

    # SharePoint legacy auth
    if sharepoint and sharepoint.get("has_data") and sharepoint.get("legacy_auth"):
        recs.append({
            "priority": "medium",
            "title": t.rec_sp_legacy_title,
            "detail": t.rec_sp_legacy_detail,
            "effort": t.rec_effort_low,
            "doc_url": "https://learn.microsoft.com/en-us/entra/identity/conditional-access/overview",
        })

    # OAuth high-privilege apps
    if oauth and oauth.get("high_privilege_apps"):
        apps = oauth["high_privilege_apps"]
        recs.append({
            "priority": "medium",
            "finding_id": "finding-oauth",
            "title": t("rec_oauth_title", count=len(apps)),
            "detail": t.rec_oauth_detail,
            "effort": t.rec_effort_medium,
            "sub_items": apps,
            "doc_url": "https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/manage-application-permissions",
        })

    # ── Azure recommendations ────────────────────────────────────────────
    fc = file_contents or {}

    # NSG risky rules (from WARN files) — with specific rules
    nsg_warns = [k for k in fc if "nsg_risky" in k.lower() and "WARN" in k]
    if nsg_warns:
        nsg_sub_items = []
        for k in nsg_warns:
            for line in fc[k].splitlines():
                line = line.strip()
                if line.startswith("NSG ") or (line.startswith("\u26a0") and "NSG" in line):
                    nsg_sub_items.append(line.lstrip("\u26a0 ").strip())
        recs.append({
            "priority": "critical",
            "title": t("rec_nsg_title", count=len(nsg_sub_items)),
            "detail": t.rec_nsg_detail,
            "effort": t.rec_effort_medium,
            "sub_items": nsg_sub_items,
        })

    # Azure Advisor — break down by category with specific actions
    if azure and azure.get("advisor_summary"):
        by_cat: dict[str, list] = {}
        for ad in azure["advisor_summary"]:
            by_cat.setdefault(ad["category"], []).append(ad)

        cat_priority = {"Security": "high", "HighAvailability": "high",
                        "Cost": "medium", "Performance": "medium",
                        "OperationalExcellence": "low"}
        cat_labels_map = {
            "Security": t.rec_advisor_cat_security,
            "HighAvailability": t.rec_advisor_cat_ha,
            "Cost": t.rec_advisor_cat_cost,
            "Performance": t.rec_advisor_cat_performance,
            "OperationalExcellence": t.rec_advisor_cat_ops,
        }

        for cat, items in by_cat.items():
            high_impact = [i for i in items if i["impact"] == "High"]
            if not high_impact and len(items) < 3:
                continue

            cat_label = cat_labels_map.get(cat, cat)
            sub_items = []
            for item in items:
                count_str = f" (x{item['count']})" if item["count"] > 1 else ""
                sub = f"[{item['impact']}] {item['description']}{count_str}"
                if item.get("subscription"):
                    sub += f" \u2014 {item['subscription']}"
                sub_items.append(sub)

            recs.append({
                "priority": cat_priority.get(cat, "medium"),
                "title": t("rec_advisor_title", category=cat_label, count=len(items)),
                "detail": t("rec_advisor_detail", high_count=len(high_impact)),
                "effort": t.rec_effort_medium,
                "sub_items": sub_items,
            })

    # Orphaned resources
    if azure and azure.get("orphaned", 0) > 0:
        orphan_details = azure.get("orphaned_details", [])
        recs.append({
            "priority": "low",
            "title": t("rec_orphaned_title", count=azure['orphaned']),
            "detail": t.rec_orphaned_detail,
            "effort": t.rec_effort_low,
            "sub_items": [f"{o['type']} ({o['status']}): {o['detail']}" for o in orphan_details],
        })

    # Stale accounts (from WARN file)
    stale_warn = fc.get("03c_stale_accounts_WARN.txt", "")
    if stale_warn and stale_warn.strip():
        import re as _re
        m = _re.search(r'(\d+)\s+licensed.*stale', stale_warn, _re.IGNORECASE)
        if not m:
            m = _re.search(r'(\d+)\s+stale', stale_warn, _re.IGNORECASE)
        count = int(m.group(1)) if m else 0
        if count > 0:
            recs.append({
                "priority": "medium",
                "title": t("rec_stale_title", count=count),
                "detail": t.rec_stale_detail,
                "effort": t.rec_effort_low,
            })

    # App credential expiry (from WARN file). The collector writes an explicit
    # summary line ("X expired, Y expiring within Z days.") at the top of the
    # WARN file; parse that rather than counting substrings across the whole
    # file, which double-counts the header word "EXPIRED", the subline itself,
    # and each per-row "Status: EXPIRED" — inflating the total by ~3 every
    # time the recommendation fires.
    cred_warn = fc.get("17c_app_credential_expiry_WARN.txt", "")
    if cred_warn and cred_warn.strip():
        m = re.search(
            r'(\d+)\s+expired\s*,\s*(\d+)\s+expiring',
            cred_warn,
            re.IGNORECASE,
        )
        if m:
            expired_count = int(m.group(1))
            critical_count = int(m.group(2))
        else:
            # Fallback: parse per-row Status field on lines that aren't headers
            # or separators. Less precise than the summary line but better than
            # the old "count substring everywhere" approach.
            expired_count = 0
            critical_count = 0
            for line in cred_warn.splitlines():
                stripped = line.strip()
                if (
                    not stripped
                    or stripped.startswith("=")
                    or stripped.startswith("-")
                    or "WARNING" in stripped
                    or "App Name" in stripped
                ):
                    continue
                # Status is the last whitespace-separated token on data rows.
                tokens = stripped.split()
                if not tokens:
                    continue
                status = tokens[-1].upper()
                if status == "EXPIRED":
                    expired_count += 1
                elif status == "CRITICAL":
                    critical_count += 1
        total = expired_count + critical_count
        if total > 0:
            recs.append({
                "priority": "high" if expired_count > 0 else "medium",
                "title": t("rec_cred_expiry_title", count=total),
                "detail": t("rec_cred_expiry_detail", expired=expired_count, critical=critical_count),
                "effort": t.rec_effort_low,
            })

    # Backup coverage — VMs without backup
    if backup_coverage and backup_coverage.get("coverage_known") and backup_coverage.get("vms_not_backed_up"):
        not_backed = backup_coverage["vms_not_backed_up"]
        recs.append({
            "priority": "high",
            "title": t("rec_backup_title", count=len(not_backed)),
            "detail": t.rec_backup_detail,
            "effort": t.rec_effort_low,
            "sub_items": not_backed,
        })

    # Sign-in risk — brute force suspects
    if signin_risk and signin_risk.get("brute_force_suspects"):
        suspects = signin_risk["brute_force_suspects"]
        recs.append({
            "priority": "high",
            "title": t("rec_brute_force_title", count=len(suspects)),
            "detail": t.rec_brute_force_detail,
            "effort": t.rec_effort_immediate,
            "sub_items": suspects,
        })

    # ── Network recommendations (FortiGate + UniFi) ─────────────────────
    if network and network.get("has_data"):
        fg = network.get("fortigate")
        uf = network.get("unifi")

        # FortiGate: admin without 2FA
        if fg and "error" not in fg:
            admins_no_2fa = [a for a in fg.get("admins", []) if not a.get("two_factor")]
            if admins_no_2fa:
                recs.append({
                    "priority": "critical",
                    "finding_id": "finding-fg-admin-2fa",
                    "title": t("rec_fg_admin_no_2fa_title", count=len(admins_no_2fa)),
                    "detail": t.rec_fg_admin_no_2fa_detail,
                    "effort": t.rec_effort_low,
                    # .get, not [] — this dict is json.loads of a file on disk,
                    # so it can predate a field or be a partial write. The
                    # surrounding filters are already defensive; indexing here
                    # threw KeyError out of build_report_context and cost the
                    # whole report for the sake of a label in a sub-item.
                    "sub_items": [
                        f"{a.get('name', '?')} ({a.get('profile', '?')})"
                        for a in admins_no_2fa
                    ],
                })
            # Allow-all rules
            allow_all = [w for w in fg.get("policy_warnings", []) if "allow-all" in w.lower()]
            if allow_all:
                recs.append({
                    "priority": "critical",
                    "finding_id": "finding-fg-allow-all",
                    "title": t("rec_fg_allow_all_title", count=len(allow_all)),
                    "detail": t.rec_fg_allow_all_detail,
                    "effort": t.rec_effort_medium,
                    "sub_items": allow_all,
                })
            # No-logging rules
            no_log = [w for w in fg.get("policy_warnings", []) if "logging" in w.lower()]
            if no_log:
                recs.append({
                    "priority": "high",
                    "finding_id": "finding-fg-no-logging",
                    "title": t("rec_fg_no_logging_title", count=len(no_log)),
                    "detail": t.rec_fg_no_logging_detail,
                    "effort": t.rec_effort_low,
                    "sub_items": no_log,
                })
            # Admin without trusted host
            admins_no_trust = [a for a in fg.get("admins", []) if not a.get("trusthost")]
            if admins_no_trust:
                recs.append({
                    "priority": "high",
                    "finding_id": "finding-fg-no-trusthost",
                    "title": t("rec_fg_no_trusthost_title", count=len(admins_no_trust)),
                    "detail": t.rec_fg_no_trusthost_detail,
                    "effort": t.rec_effort_low,
                    "sub_items": [a.get("name", "?") for a in admins_no_trust],
                })

        # UniFi findings
        if uf and "error" not in uf:
            default_creds = uf.get("default_creds_count", 0)
            if default_creds:
                cred_devices = [d.get("label", d.get("host", "")) for d in uf.get("devices", []) if d.get("default_credentials")]
                recs.append({
                    "priority": "critical",
                    "finding_id": "finding-uf-default-creds",
                    "title": t("rec_uf_default_creds_title", count=default_creds),
                    "detail": t.rec_uf_default_creds_detail,
                    "effort": t.rec_effort_immediate,
                    "sub_items": cred_devices,
                })
            eol_count = uf.get("eol_count", 0)
            if eol_count:
                eol_devices = [f"{d.get('label', d.get('host', ''))} ({d.get('fw_check', {}).get('model', '')})"
                               for d in uf.get("devices", []) if d.get("fw_check", {}).get("eol")]
                recs.append({
                    "priority": "critical",
                    "finding_id": "finding-uf-eol",
                    "title": t("rec_uf_eol_title", count=eol_count),
                    "detail": t.rec_uf_eol_detail,
                    "effort": t.rec_effort_medium,
                    "sub_items": eol_devices,
                })
            outdated = uf.get("outdated_firmware_count", 0)
            if outdated:
                fw_devices = [f"{d.get('label', d.get('host', ''))}: {d.get('firmware', '')} → {d.get('fw_check', {}).get('latest', '')}"
                              for d in uf.get("devices", []) if d.get("fw_check", {}).get("up_to_date") is False and not d.get("fw_check", {}).get("eol")]
                recs.append({
                    "priority": "high",
                    "finding_id": "finding-uf-outdated-fw",
                    "title": t("rec_uf_outdated_fw_title", count=outdated),
                    "detail": t.rec_uf_outdated_fw_detail,
                    "effort": t.rec_effort_low,
                    "sub_items": fw_devices,
                })
            # Factory default devices
            factory_devs = [d for d in uf.get("devices", []) if d.get("is_default_config")]
            if factory_devs:
                recs.append({
                    "priority": "high",
                    "finding_id": "finding-uf-factory-default",
                    "title": t("rec_uf_factory_default_title", count=len(factory_devs)),
                    "detail": t.rec_uf_factory_default_detail,
                    "effort": t.rec_effort_medium,
                    "sub_items": [d.get("label", d.get("host", "")) for d in factory_devs],
                })
            # Open WiFi (controller mode)
            if uf.get("mode") == "controller":
                open_wlans = [w.get("name", "") for w in uf.get("wlans", [])
                              if _is_open_wlan(w) and w.get("enabled")]
                if open_wlans:
                    recs.append({
                        "priority": "critical",
                        "finding_id": "finding-uf-open-wifi",
                        "title": t.rec_uf_open_wifi_title,
                        "detail": t.rec_uf_open_wifi_detail,
                        "effort": t.rec_effort_low,
                        "sub_items": open_wlans,
                    })

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 9))

    # Assign 1-based index and build finding→rec cross-reference
    for i, rec in enumerate(recs):
        rec["rec_index"] = i + 1

    return recs


# ── Trend comparison ──────────────────────────────────────────────────────────

def _metric(source: dict | None, key: str):
    """Return a metric only when its source section actually produced data.

    These values are *persisted* — to _audit_metrics.json and to the
    audit_metrics table — and they feed the trend charts in the next report.
    A zero written for a section that failed is indistinguishable downstream
    from a measured zero, and _compute_trends only skips None. So a single
    throttled audit would draw MFA coverage collapsing to 0% and recovering,
    in the customer's history, permanently: a later correct audit adds a new
    row but cannot retract the old one.

    None means unknown, is stored as SQL NULL (every one of these columns is
    nullable), and is skipped by the trend comparison.
    """
    if not source or not source.get("has_data"):
        return None
    return source.get(key)


def save_audit_metrics(out_dir: Path, context: dict) -> None:
    """Save key audit metrics as JSON for future trend comparison."""
    mfa      = context.get("mfa", {})
    network  = context.get("network", {}) or {}
    unifi    = (network.get("unifi") or {}) if network.get("has_data") else None
    fortigate = network.get("fortigate") if network.get("has_data") else None

    metrics = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mfa_coverage_pct": _metric(mfa, "pct"),
        "secure_score_pct": _metric(context.get("secure_score", {}), "pct"),
        "total_users": _metric(context.get("users", {}), "total"),
        "users_no_mfa": _metric(mfa, "no_mfa"),
        "ca_policies_enabled": _metric(context.get("ca", {}), "enabled"),
        "intune_compliance_pct": _metric(context.get("intune", {}), "compliance_pct"),
        "intune_total_devices": _metric(context.get("intune", {}), "total"),
        "admin_roles_ga_count": _metric(context.get("admin_roles", {}), "global_admin_count"),
        "total_warns": len(context.get("all_warns", [])),
        # _compute_risk already returns None here when a blocking gap makes
        # the grade fiction — carry it through rather than flattening to 0.
        "risk_score": context.get("risk", {}).get("score"),
        "risk_grade": context.get("risk", {}).get("grade", ""),
        # Network metrics — None when the network audit produced nothing, so
        # a customer with no FortiGate/UniFi reachable does not register as
        # "0 devices, 0 default credentials" alongside tenants we did scan.
        "network_devices": None if unifi is None and fortigate is None else (
            (unifi or {}).get("device_count", 0)
            + (1 if fortigate and "error" not in fortigate else 0)
        ),
        "network_default_creds": (unifi or {}).get("default_creds_count") if unifi else None,
        "network_outdated_fw": (unifi or {}).get("outdated_firmware_count") if unifi else None,
        "recommendations": [
            {"priority": r.get("priority", ""), "title": r.get("title", ""), "detail": r.get("detail", ""), "effort": r.get("effort", "")}
            for r in context.get("recommendations", [])
        ],
    }
    from app.core.encryption import encrypted_write_json
    path = out_dir / "_audit_metrics.json"
    encrypted_write_json(path, metrics)

    # Also persist to DB for trend tracking
    try:
        _save_metrics_to_db(out_dir, metrics)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to save metrics to DB: %s", e)


def _save_metrics_to_db(out_dir: Path, metrics: dict) -> None:
    """Insert audit metrics into the database for historical trend queries."""
    import sqlite3

    from app.core.database import DB_PATH
    customer_name = out_dir.parent.name.replace("_", " ")
    # Derive customer_id from customer context if available
    customer_id = ""
    try:
        from app.core.credentials import load_config
        cfg = load_config() or {}
        customer_id = cfg.get("_id", cfg.get("TenantId", ""))
    except Exception:
        pass
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            """INSERT INTO audit_metrics
               (customer_id, customer_name, audit_date, risk_grade, risk_score,
                mfa_coverage_pct, secure_score_pct, total_users, users_no_mfa,
                ca_policies_enabled, intune_compliance_pct, admin_roles_ga_count,
                metrics_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                customer_id,
                customer_name,
                metrics.get("timestamp", ""),
                metrics.get("risk_grade", ""),
                # No `, 0` fallbacks: these columns are nullable and an
                # unknown must reach the row as NULL, not as a measured zero.
                metrics.get("risk_score"),
                metrics.get("mfa_coverage_pct"),
                metrics.get("secure_score_pct"),
                metrics.get("total_users"),
                metrics.get("users_no_mfa"),
                metrics.get("ca_policies_enabled"),
                metrics.get("intune_compliance_pct"),
                metrics.get("admin_roles_ga_count"),
                __import__("json").dumps(metrics),
                metrics.get("timestamp", ""),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_previous_metrics(out_dir: Path) -> dict | None:
    """Load metrics from the most recent previous audit run in the same customer folder."""
    customer_dir = out_dir.parent
    current_name = out_dir.name

    candidates: list[Path] = []
    for sibling in sorted(customer_dir.iterdir()):
        if (
            sibling.is_dir()
            and sibling.name < current_name
            and (sibling / "_audit_metrics.json").exists()
        ):
            candidates.append(sibling)

    if not candidates:
        return None

    prev_dir = candidates[-1]  # most recent before current (sorted ascending)
    try:
        from app.core.encryption import encrypted_read_json
        return encrypted_read_json(prev_dir / "_audit_metrics.json")
    except Exception as e:
        # Deliberately broad. The old (json.JSONDecodeError, OSError) missed
        # cryptography's InvalidTag, so a metrics file that could not be
        # decrypted — after a master-key rotation, a recreated keyring entry,
        # or plain corruption — took the whole report generation down with
        # it. The trend comparison is an enhancement; the report is the
        # deliverable, and losing the former must never cost the latter.
        logging.getLogger(__name__).warning(
            "Could not read previous metrics from %s: %s", prev_dir.name, e
        )
        return None


def load_metrics_history(out_dir: Path, max_runs: int = 5) -> list[dict]:
    """Load metrics from up to *max_runs* previous audit runs (oldest first).

    Each entry is a dict with at least the metric keys plus a ``_run_label``
    derived from the folder name (typically a date-based string).
    """
    customer_dir = out_dir.parent
    current_name = out_dir.name

    candidates: list[Path] = []
    for sibling in sorted(customer_dir.iterdir()):
        if (
            sibling.is_dir()
            and sibling.name < current_name
            and (sibling / "_audit_metrics.json").exists()
        ):
            candidates.append(sibling)

    # Take the last N (most recent) candidates, keep oldest-first order
    candidates = candidates[-max_runs:]

    history: list[dict] = []
    from app.core.encryption import encrypted_read_json
    for cdir in candidates:
        try:
            data = encrypted_read_json(cdir / "_audit_metrics.json")
            data["_run_label"] = cdir.name
            history.append(data)
        except Exception as e:
            # See load_previous_metrics — an undecryptable run must cost that
            # one point on the chart, not the whole report.
            logging.getLogger(__name__).warning(
                "Skipping unreadable metrics history for %s: %s", cdir.name, e
            )
            continue
    return history


def _compute_trends(current: dict, previous: dict | None) -> dict:
    """Compute deltas between current and previous audit metrics."""
    if not previous:
        return {}

    tracked_keys = [
        "mfa_coverage_pct", "secure_score_pct", "total_users", "users_no_mfa",
        "ca_policies_enabled", "intune_compliance_pct", "intune_total_devices",
        "admin_roles_ga_count", "total_warns", "risk_score",
    ]
    trends: dict = {}
    for key in tracked_keys:
        cur_val = current.get(key)
        prev_val = previous.get(key)
        if cur_val is None or prev_val is None:
            continue
        delta = round(cur_val - prev_val, 2)
        # For most metrics, higher is better; for warns/no_mfa/ga_count, lower is better
        lower_is_better = key in ("users_no_mfa", "admin_roles_ga_count", "total_warns")
        if delta == 0:
            continue
        improved = (delta < 0) if lower_is_better else (delta > 0)
        trends[key] = {
            "current": cur_val,
            "previous": prev_val,
            "delta": delta,
            "improved": improved,
        }
    return trends


## NIST CSF 2.0 / ISO 27001:2022 cross-reference for each CIS M365 Benchmark control
## Each entry includes human-readable names so reports are informative, not just IDs.
_FRAMEWORK_MAP: dict[str, dict[str, str]] = {
    # ── Identity & Access ──
    "1.1.1": {"nist_id": "PR.AA-1", "nist_name": "Identities and credentials are managed",
              "iso_id": "A.8.5",  "iso_name": "Secure authentication"},
    "1.1.2": {"nist_id": "PR.AA-3", "nist_name": "Users, services, and hardware are authenticated",
              "iso_id": "A.8.5",  "iso_name": "Secure authentication"},
    "1.1.3": {"nist_id": "PR.AA-5", "nist_name": "Access permissions are managed",
              "iso_id": "A.5.15", "iso_name": "Access control"},
    "1.1.4": {"nist_id": "PR.AA-1", "nist_name": "Identities and credentials are managed",
              "iso_id": "A.8.3",  "iso_name": "Information access restriction"},
    "1.1.5": {"nist_id": "PR.AA-5", "nist_name": "Access permissions are managed",
              "iso_id": "A.5.18", "iso_name": "Access rights"},
    "1.1.6": {"nist_id": "PR.AA-1", "nist_name": "Identities and credentials are managed",
              "iso_id": "A.5.16", "iso_name": "Identity management"},
    "1.2.1": {"nist_id": "PR.AA-3", "nist_name": "Users, services, and hardware are authenticated",
              "iso_id": "A.8.5",  "iso_name": "Secure authentication"},
    "1.4":   {"nist_id": "ID.RA-1", "nist_name": "Asset vulnerabilities are identified",
              "iso_id": "A.8.8",  "iso_name": "Management of technical vulnerabilities"},
    # ── Applications & OAuth ──
    "2.1":   {"nist_id": "PR.AA-5", "nist_name": "Access permissions are managed",
              "iso_id": "A.8.3",  "iso_name": "Information access restriction"},
    "2.1.2": {"nist_id": "PR.AA-1", "nist_name": "Identities and credentials are managed",
              "iso_id": "A.5.16", "iso_name": "Identity management"},
    # ── Data Protection ──
    "3.1.1": {"nist_id": "PR.DS-5", "nist_name": "Protections against data leaks are implemented",
              "iso_id": "A.8.12", "iso_name": "Data leakage prevention"},
    "3.2.1": {"nist_id": "PR.DS-2", "nist_name": "Data-in-transit is protected",
              "iso_id": "A.5.14", "iso_name": "Information transfer"},
    # ── Email & Exchange ──
    "4.1":   {"nist_id": "DE.CM-1", "nist_name": "Networks are monitored for anomalous events",
              "iso_id": "A.8.16", "iso_name": "Monitoring activities"},
    "4.2":   {"nist_id": "PR.DS-2", "nist_name": "Data-in-transit is protected",
              "iso_id": "A.8.24", "iso_name": "Use of cryptography"},
    "4.3":   {"nist_id": "PR.PS-5", "nist_name": "Installation and execution of unauthorized software is prevented",
              "iso_id": "A.8.7",  "iso_name": "Protection against malware"},
    "4.4":   {"nist_id": "PR.DS-2", "nist_name": "Data-in-transit is protected",
              "iso_id": "A.5.14", "iso_name": "Information transfer"},
    "4.5":   {"nist_id": "DE.CM-4", "nist_name": "Malicious code is detected",
              "iso_id": "A.8.7",  "iso_name": "Protection against malware"},
    "4.6":   {"nist_id": "DE.CM-4", "nist_name": "Malicious code is detected",
              "iso_id": "A.8.7",  "iso_name": "Protection against malware"},
    # ── Email Authentication ──
    "5.1.1": {"nist_id": "PR.AA-3", "nist_name": "Users, services, and hardware are authenticated",
              "iso_id": "A.8.5",  "iso_name": "Secure authentication"},
    "5.2.1": {"nist_id": "PR.DS-2", "nist_name": "Data-in-transit is protected",
              "iso_id": "A.5.14", "iso_name": "Information transfer"},
    "5.2.2": {"nist_id": "PR.DS-2", "nist_name": "Data-in-transit is protected",
              "iso_id": "A.5.14", "iso_name": "Information transfer"},
    "5.2.3": {"nist_id": "PR.DS-2", "nist_name": "Data-in-transit is protected",
              "iso_id": "A.8.24", "iso_name": "Use of cryptography"},
    # ── Devices ──
    "6.1.1": {"nist_id": "PR.AA-5", "nist_name": "Access permissions are managed",
              "iso_id": "A.8.1",  "iso_name": "User endpoint devices"},
    # ── SharePoint & Data ──
    "7.2.1": {"nist_id": "PR.DS-5", "nist_name": "Protections against data leaks are implemented",
              "iso_id": "A.5.14", "iso_name": "Information transfer"},
    "7.2.2": {"nist_id": "PR.DS-5", "nist_name": "Protections against data leaks are implemented",
              "iso_id": "A.8.12", "iso_name": "Data leakage prevention"},
    # ── Teams ──
    "8.1.1": {"nist_id": "PR.AA-5", "nist_name": "Access permissions are managed",
              "iso_id": "A.5.14", "iso_name": "Information transfer"},
    "8.1.2": {"nist_id": "PR.DS-5", "nist_name": "Protections against data leaks are implemented",
              "iso_id": "A.5.14", "iso_name": "Information transfer"},
    # ── Logging & Monitoring ──
    "9.1":   {"nist_id": "DE.CM-1", "nist_name": "Networks are monitored for anomalous events",
              "iso_id": "A.8.15", "iso_name": "Logging"},
    "9.2":   {"nist_id": "DE.AE-3", "nist_name": "Event data are correlated from multiple sources",
              "iso_id": "A.8.16", "iso_name": "Monitoring activities"},
    "9.3":   {"nist_id": "RS.AN-3", "nist_name": "Forensic analysis is conducted",
              "iso_id": "A.5.28", "iso_name": "Collection of evidence"},
}


def _section_ran(fc: dict, *names: str) -> bool:
    """True when at least one of the named collector outputs is usable.

    A file that is absent, empty, or an "Error:" stub means the section
    produced no reading. Zero policies in a file that *was* written is a
    reading — and a completely different claim. Compliance controls kept
    conflating the two, so a tenant whose Exchange section never ran was
    attested as having no external forwarding and failed for having no
    anti-spam policy, on identical evidence: nothing.
    """
    for name in names:
        text = fc.get(name, "")
        stripped = text.strip() if isinstance(text, str) else ""
        if stripped and not stripped.startswith("Error:"):
            return True
    return False


_CANNOT_VERIFY = "Kan ikke verifiseres — "


def _build_compliance_map(context: dict, lang: str = "no", frameworks: str = "all") -> list[dict]:
    """Map audit findings to CIS Microsoft 365 Foundations Benchmark v3.1 controls.

    *frameworks* controls which cross-reference columns are included:
      "cis"      – CIS only (no extra columns)
      "cis+nist" – CIS + NIST CSF 2.0
      "cis+iso"  – CIS + ISO 27001:2022
      "all"      – CIS + NIST CSF 2.0 + ISO 27001:2022
    """
    t = T(lang)
    controls = []
    show_nist = frameworks in ("cis+nist", "all")
    show_iso  = frameworks in ("cis+iso", "all")

    # Helper — includes human-readable framework names
    def add(cis_id, title, category, status, detail=""):
        entry = {"cis_id": cis_id, "title": title, "category": category, "status": status, "detail": detail}
        fw = _FRAMEWORK_MAP.get(cis_id, {})
        if show_nist:
            nid = fw.get("nist_id", "")
            entry["nist_id"] = f"{nid}: {fw['nist_name']}" if nid and fw.get("nist_name") else nid
        if show_iso:
            iid = fw.get("iso_id", "")
            entry["iso_id"] = f"{iid}: {fw['iso_name']}" if iid and fw.get("iso_name") else iid
        controls.append(entry)

    mfa = context.get("mfa", {})
    ca = context.get("ca", {})
    ss = context.get("secure_score", {})
    admin = context.get("admin_roles", {})
    spf = context.get("spf_dmarc", [])
    sp = context.get("sharepoint", {})
    intune = context.get("intune", {})
    exchange = context.get("exchange", {})
    fc = context.get("file_contents", {})
    oauth = context.get("oauth", {})
    purview = context.get("purview", {})
    groups = context.get("groups", {})
    signin_risk = context.get("signin_risk", {})

    # ═══ 1. IDENTITY & ACCESS ═══

    # 1.1.1 MFA. The old branch collapsed "we could not read MFA state" and
    # "we read it and nobody has MFA" into one "fail" — the translation string
    # even said "not available or 0% coverage". Both halves were wrong: an
    # unverifiable control landed in compliance_fail and stayed in the
    # compliance_pct denominator (compliance_assessed excludes "info"
    # precisely so it wouldn't), and a genuine 0% was described as missing
    # data. Every neighbouring control here already uses "info" +
    # "Kan ikke verifiseres" for the unverifiable case.
    if not mfa.get("has_data"):
        add("1.1.1", "Ensure MFA is enabled for all users", t.cis_cat_identity, "info",
            t.cis_mfa_unavailable)
    elif mfa.get("pct", 0) >= 95:
        add("1.1.1", "Ensure MFA is enabled for all users", t.cis_cat_identity, "pass",
            t("cis_mfa_coverage", pct=mfa.get('pct', 0)))
    elif mfa.get("pct", 0) > 0:
        add("1.1.1", "Ensure MFA is enabled for all users", t.cis_cat_identity, "partial",
            t("cis_mfa_partial", pct=mfa.get('pct', 0), no_mfa=mfa.get('no_mfa', 0)))
    else:
        add("1.1.1", "Ensure MFA is enabled for all users", t.cis_cat_identity, "fail",
            t("cis_mfa_none", no_mfa=mfa.get('no_mfa', 0)))

    # 1.1.2 Phishing-resistant MFA. CIS says phishing-resistant methods
    # should be "preferred" (i.e. enabled at the policy level). The previous
    # implementation invented a 50%-of-users threshold, which doesn't appear
    # in any CIS document — a tenant could PASS with only 50% phishing-
    # resistant coverage, or FAIL despite having FIDO2 fully enabled for
    # admins. CIS's actual ask is configuration-level: is the tenant's
    # authenticationMethodsPolicy set to allow/prefer FIDO2 (or Microsoft
    # Authenticator passkeys)? Read the auth-methods-policy file and check
    # the state of the phishing-resistant methods.
    auth_methods_text = fc.get("09b_auth_methods_policy.txt", "")
    if not auth_methods_text.strip() or auth_methods_text.strip().startswith("Error:"):
        add("1.1.2", "Ensure phishing-resistant MFA methods are enabled",
            t.cis_cat_identity, "info",
            "Kan ikke verifiseres — autentiseringsmetode-policy utilgjengelig")
    else:
        # Walk the "Method  State" table. The file lists each method type
        # (Fido2, MicrosoftAuthenticator, Sms, etc.) and its state.
        _phishing_resistant = {"fido2", "windowshelloforbusiness", "x509certificate"}
        enabled_pr_methods: list[str] = []
        for line in auth_methods_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-"):
                continue
            cols = re.split(r'\s{2,}', stripped)
            if len(cols) < 2:
                continue
            method = cols[0].lower().replace(" ", "")
            state = cols[1].lower()
            if method == "method" and state == "state":
                continue
            if method in _phishing_resistant and state == "enabled":
                enabled_pr_methods.append(cols[0])
        if enabled_pr_methods:
            add("1.1.2", "Ensure phishing-resistant MFA methods are enabled",
                t.cis_cat_identity, "pass",
                f"Phishing-resistant metoder aktivert: {', '.join(enabled_pr_methods)}")
        else:
            add("1.1.2", "Ensure phishing-resistant MFA methods are enabled",
                t.cis_cat_identity, "warn",
                "Ingen phishing-resistant metoder (FIDO2 / Windows Hello / "
                "x509Certificate) er aktivert i autentiseringsmetode-policyen")

    # 1.1.3 Global Admins
    if admin.get("has_data"):
        ga = admin.get("global_admin_count", 0)
        if 2 <= ga <= 4:
            add("1.1.3", "Ensure fewer than 5 Global Admins", t.cis_cat_identity, "pass",
                t("cis_ga_count", count=ga))
        elif ga > 4:
            add("1.1.3", "Ensure fewer than 5 Global Admins", t.cis_cat_identity, "fail",
                t("cis_ga_too_many", count=ga))
        elif ga == 1:
            add("1.1.3", "Ensure fewer than 5 Global Admins", t.cis_cat_identity, "warn",
                t("cis_ga_too_few", count=ga))
    else:
        add("1.1.3", "Ensure fewer than 5 Global Admins", t.cis_cat_identity, "info",
            "Kan ikke verifiseres — admin-rolle data utilgjengelig")

    # 1.1.4 CA policies
    if ca.get("has_data") and ca.get("enabled", 0) > 0:
        add("1.1.4", "Ensure Conditional Access policies are configured", t.cis_cat_identity, "pass",
            t("cis_active_policies", count=ca['enabled']))
    elif ca.get("has_data"):
        add("1.1.4", "Ensure Conditional Access policies are configured", t.cis_cat_identity, "fail",
            t.cis_no_active_ca)
    else:
        add("1.1.4", "Ensure Conditional Access policies are configured", t.cis_cat_identity, "info",
            "Kan ikke verifiseres — audit-data utilgjengelig")

    # 1.1.5 PIM is used for admin roles. The collector writes the header
    # ("PIM ELIGIBLE ROLE ASSIGNMENTS (N total)") even when N=0, so a simple
    # `"eligible" in pim_text` match always passed — a false attestation
    # for every tenant that doesn't use PIM. Parse the banner's explicit
    # count rather than counting lines (which would include the column
    # header row).
    pim_text = fc.get("07b_pim_eligible_assignments.txt", "")
    pim_count = _parse_banner_count(pim_text)
    if not pim_text.strip() or pim_text.strip().startswith("Error:"):
        add("1.1.5", "Ensure PIM is used for privileged role activation", t.cis_cat_identity, "info",
            "Kan ikke verifiseres — PIM-data utilgjengelig")
    elif pim_count is not None and pim_count > 0:
        add("1.1.5", "Ensure PIM is used for privileged role activation", t.cis_cat_identity, "pass",
            f"{pim_count} PIM-berettigede rolletildelinger funnet")
    else:
        add("1.1.5", "Ensure PIM is used for privileged role activation", t.cis_cat_identity, "warn",
            "Ingen PIM-tildelinger funnet — roller kan være permanent tildelt")

    # 1.1.6 Emergency access accounts. Same substring-on-banner bug as 1.1.5
    # — the file always contains the header "EMERGENCY / BREAK-GLASS ACCOUNT
    # CHECK", which made every tenant look like they had break-glass accounts.
    # Look for actual user rows (any line containing a UPN).
    emerg_text = fc.get("07c_emergency_access_check.txt", "")
    emerg_user_rows = sum(
        1 for line in emerg_text.splitlines()
        if "@" in line and "skipping" not in line.lower() and "ID provided" not in line
    )
    if not emerg_text.strip() or emerg_text.strip().startswith("Error:"):
        add("1.1.6", "Ensure emergency access accounts are configured", t.cis_cat_identity, "info",
            "Kan ikke verifiseres — data utilgjengelig")
    elif emerg_user_rows > 0:
        add("1.1.6", "Ensure emergency access accounts are configured", t.cis_cat_identity, "pass",
            f"{emerg_user_rows} nødtilgangskonto(er) (break glass) oppdaget")
    else:
        add("1.1.6", "Ensure emergency access accounts are configured", t.cis_cat_identity, "warn",
            "Ingen nødtilgangskontoer identifisert")

    # 1.2.1 Password protection / custom banned passwords. The previous code
    # read 09c_auth_strength_policies.txt — wrong file, that's about FIDO2
    # auth strength, not banned passwords. It then matched substring "banned"
    # or "custom" anywhere in the text → false PASS on the auth-strength
    # banner line. Banned-password config is in 31_password_protection.txt
    # which has explicit lines like:
    #   "Custom Banned Passwords Enabled : True"
    # Parse that explicitly so we can only PASS when the feature is actually
    # turned on with a non-empty banned list.
    pwd_text = fc.get("31_password_protection.txt", "")
    if not pwd_text.strip() or pwd_text.strip().startswith("Error:"):
        add("1.2.1", "Ensure custom banned passwords are configured", t.cis_cat_identity, "info",
            "Kan ikke verifiseres — data utilgjengelig")
    else:
        custom_enabled = False
        list_configured = False
        for line in pwd_text.splitlines():
            low = line.lower()
            if "custom banned passwords enabled" in low and ":" in line:
                val = line.split(":", 1)[1].strip().lower()
                custom_enabled = val in ("true", "yes")
            elif "custom banned passwords" in low and ":" in line:
                val = line.split(":", 1)[1].strip().lower()
                if val == "configured":
                    list_configured = True
        if custom_enabled or list_configured:
            add("1.2.1", "Ensure custom banned passwords are configured", t.cis_cat_identity, "pass",
                "Egendefinert forbudt passordliste er aktiv")
        else:
            add("1.2.1", "Ensure custom banned passwords are configured", t.cis_cat_identity, "fail",
                "Kun Microsofts standardliste — ingen egendefinerte forbudte passord (krever Entra ID P1+)")

    # 1.4 Secure Score. ss.get("pct", 0) silently defaulted to 0 when the
    # secure-score fetch failed, then the verdict tree below evaluated `< 50`
    # and reported FAIL — a false negative dressed up as a measurement.
    if not ss.get("has_data"):
        add("1.4", "Ensure Microsoft Secure Score is above 75%", t.cis_cat_general, "info",
            "Kan ikke verifiseres — Secure Score-data utilgjengelig")
    else:
        ss_pct = ss.get("pct", 0)
        if ss_pct >= 75:
            add("1.4", "Ensure Microsoft Secure Score is above 75%", t.cis_cat_general, "pass", f"{ss_pct:.0f}%")
        elif ss_pct >= 50:
            add("1.4", "Ensure Microsoft Secure Score is above 75%", t.cis_cat_general, "partial", f"{ss_pct:.0f}%")
        else:
            add("1.4", "Ensure Microsoft Secure Score is above 75%", t.cis_cat_general, "fail", f"{ss_pct:.0f}%")

    # ═══ 2. APPLICATIONS ═══

    grants = oauth.get("total_grants", 0)
    apps = oauth.get("unique_apps", 0)
    app_regs = oauth.get("app_registrations", 0)
    high_priv = len(oauth.get("high_privilege_apps", []))
    if high_priv > 5:
        add("2.1", "Ensure third-party apps are reviewed", t.cis_cat_applications,
            "warn", t("cis_oauth_warn", apps=apps, grants=grants, high_priv=high_priv, app_regs=app_regs))
    else:
        add("2.1", "Ensure third-party apps are reviewed", t.cis_cat_applications,
            "info", t("cis_oauth_info", apps=apps, grants=grants, app_regs=app_regs))

    # 2.1.2 App credential expiry. Substring matching ("expired" anywhere in
    # the file) matched the WARN banner word and reported FAIL even when
    # the file just said "no expired credentials". Use the explicit summary
    # line ("X expired, Y expiring within Z days.") that the collector emits.
    #
    # The WARN file only exists when there is something to warn about, so its
    # absence reads as "no expired credentials" — but only if the section that
    # would have written it actually ran. Without that check, a failed
    # app-registrations fetch was attested as a clean bill of health.
    cred_warn = fc.get("17c_app_credential_expiry_WARN.txt", "")
    if not cred_warn.strip() and not _section_ran(fc, "17_app_registrations.txt"):
        add("2.1.2", "Ensure app credentials are not expired", t.cis_cat_applications, "info",
            _CANNOT_VERIFY + "app-registreringer utilgjengelig")
    elif not cred_warn.strip():
        add("2.1.2", "Ensure app credentials are not expired", t.cis_cat_applications, "pass",
            "Ingen utløpte app-credentials")
    else:
        m = re.search(r'(\d+)\s+expired\s*,\s*(\d+)\s+expiring', cred_warn, re.IGNORECASE)
        expired_n = int(m.group(1)) if m else 0
        critical_n = int(m.group(2)) if m else 0
        if expired_n > 0:
            add("2.1.2", "Ensure app credentials are not expired", t.cis_cat_applications, "fail",
                f"{expired_n} utløpte app-credentials oppdaget")
        elif critical_n > 0:
            add("2.1.2", "Ensure app credentials are not expired", t.cis_cat_applications, "warn",
                f"{critical_n} app-credentials utløper snart (≤30 dager)")
        else:
            add("2.1.2", "Ensure app credentials are not expired", t.cis_cat_applications, "pass",
                "Ingen utløpte app-credentials")

    # ═══ 3. DATA PROTECTION ═══

    # 3.1.1 DLP policies
    dlp_text = fc.get("19d_purview_dlp_policies.txt", "")
    _dlp_raw = purview.get("dlp_policies", 0) if purview else 0
    dlp_count = len(_dlp_raw) if isinstance(_dlp_raw, list) else (_dlp_raw if isinstance(_dlp_raw, int) else 0)
    if dlp_count > 0 or ("enabled" in dlp_text.lower() and "enforce" in dlp_text.lower()):
        add("3.1.1", "Ensure DLP policies are configured", t.cis_cat_data, "pass",
            f"{dlp_count} DLP-policyer konfigurert" if dlp_count else "DLP-policyer funnet")
    elif dlp_text.strip():
        add("3.1.1", "Ensure DLP policies are configured", t.cis_cat_data, "partial",
            "DLP-policyer finnes men kan være i test-/overvåkingsmodus")
    elif _section_ran(fc, "19d_purview_dlp_policies.txt"):
        add("3.1.1", "Ensure DLP policies are configured", t.cis_cat_data, "warn",
            "Ingen DLP-policyer funnet")
    else:
        add("3.1.1", "Ensure DLP policies are configured", t.cis_cat_data, "info",
            _CANNOT_VERIFY + "Purview DLP-data utilgjengelig")

    # 3.2.1 Sensitivity labels
    _labels_raw = purview.get("sensitivity_labels", 0) if purview else 0
    labels = len(_labels_raw) if isinstance(_labels_raw, list) else (_labels_raw if isinstance(_labels_raw, int) else 0)
    labels_text = fc.get("19c_purview_sensitivity_labels.txt", "")
    if labels > 0 or ("label" in labels_text.lower() and labels_text.strip()):
        add("3.2.1", "Ensure sensitivity labels are published", t.cis_cat_data, "pass",
            f"{labels} sensitivitetsetiketter publisert" if labels else "Sensitivitetsetiketter funnet")
    elif _section_ran(fc, "19c_purview_sensitivity_labels.txt"):
        add("3.2.1", "Ensure sensitivity labels are published", t.cis_cat_data, "warn",
            "Ingen sensitivitetsetiketter funnet")
    else:
        add("3.2.1", "Ensure sensitivity labels are published", t.cis_cat_data, "info",
            _CANNOT_VERIFY + "Purview-etikettdata utilgjengelig")

    # ═══ 4. EMAIL SECURITY ═══

    # 4.1 Audit logging. The previous code matched substrings "AuditDisabled"
    # and "True"/"False" independently across the entire file — so a config
    # with `AuditDisabled: False` plus any other line containing the word
    # "True" elsewhere (e.g. "ExternalForwarding: True") could flip the
    # verdict. Parse the specific AuditDisabled line and its value.
    org_config = fc.get("27c_exchange_org_config.txt", "")
    audit_disabled_val = None
    for line in org_config.splitlines():
        if "AuditDisabled" in line and ":" in line:
            val = line.split(":", 1)[1].strip().rstrip(";").lower()
            if val in ("true", "false"):
                audit_disabled_val = val == "true"
                break
    if audit_disabled_val is False:
        add("4.1", "Ensure mailbox audit logging is enabled", t.cis_cat_email, "pass",
            "Mailbox audit er aktivert (AuditDisabled=False)")
    elif audit_disabled_val is True:
        add("4.1", "Ensure mailbox audit logging is enabled", t.cis_cat_email, "fail",
            "Mailbox audit er deaktivert (AuditDisabled=True)")
    elif org_config.strip():
        add("4.1", "Ensure mailbox audit logging is enabled", t.cis_cat_email, "info",
            "Kunne ikke fastslå audit-status fra org-config")

    # 4.2 Anti-phishing. _section_ran, not .strip(): an "Error: access denied"
    # stub is non-empty and would otherwise attest that policies exist.
    if _section_ran(fc, "23_exchange_antiphish.txt"):
        add("4.2", "Ensure anti-phishing policies are configured", t.cis_cat_email, "pass",
            "Anti-phishing-policyer er konfigurert")
    else:
        # An absent 23_ file is the Exchange section not running, not a tenant
        # without anti-phishing policies.
        add("4.2", "Ensure anti-phishing policies are configured", t.cis_cat_email, "info",
            _CANNOT_VERIFY + "anti-phishing-data utilgjengelig")

    # 4.3 Anti-spam — always add the entry. The control used to be silently
    # omitted when the file was empty, so a tenant with no anti-spam policies
    # got no CIS 4.3 row at all. Keeping the row is right; grading it FAIL on
    # an empty file was not — an absent 24_ file means the Exchange section
    # did not run, and "no policies" and "no data" are different claims.
    if _section_ran(fc, "24_exchange_antispam.txt"):
        add("4.3", "Ensure anti-spam policies are configured", t.cis_cat_email, "pass",
            "Anti-spam-policyer er konfigurert")
    else:
        add("4.3", "Ensure anti-spam policies are configured", t.cis_cat_email, "info",
            _CANNOT_VERIFY + "anti-spam-data utilgjengelig "
            "(kjør Get-HostedContentFilterPolicy i EOP)")

    # 4.4 External forwarding. This read the wrong two files, in both
    # directions:
    #
    #   28_exchange_mailbox_forwarding.txt is written unconditionally and
    #   lists *all* forwarding, internal included — and its own title is
    #   "MAILBOX FORWARDING", so `"forwarding" in text` was true for every
    #   tenant whose Exchange section ran. The external-forwarding warning
    #   goes to a separate file, 28b_..._WARN.txt.
    #
    #   29_exchange_inbox_rules_external_fwd.txt is, by the collector's
    #   naming convention, the *clean* result — when rules are found it
    #   writes 29_..._WARN.txt instead. So the check treated the all-clear
    #   file as evidence and never looked at the file that carries the
    #   finding.
    #
    # Net: a guaranteed false "external forwarding detected" for everyone,
    # and blind to the real thing. _compute_risk had this right already; it
    # reads 28b_..._WARN.txt.
    ext_fwd_warn   = fc.get("28b_exchange_external_forwarding_WARN.txt", "")
    inbox_fwd_warn = fc.get("29_exchange_inbox_rules_external_fwd_WARN.txt", "")
    if ext_fwd_warn.strip() or inbox_fwd_warn.strip():
        add("4.4", "Ensure mail forwarding to external domains is restricted", t.cis_cat_email, "warn",
            "Ekstern videresending oppdaget på en eller flere postbokser")
    elif _section_ran(fc, "28_exchange_mailbox_forwarding.txt",
                      "29_exchange_inbox_rules_external_fwd.txt"):
        # The unconditional file is present, so the check genuinely ran.
        add("4.4", "Ensure mail forwarding to external domains is restricted", t.cis_cat_email, "pass",
            "Ingen ekstern videresending oppdaget")
    else:
        add("4.4", "Ensure mail forwarding to external domains is restricted", t.cis_cat_email, "info",
            _CANNOT_VERIFY + "videresendingsdata utilgjengelig")

    # 4.5 / 4.6 Safe Links and Safe Attachments. The previous logic matched
    # the substring "safe links" / "safe attach" anywhere in the file —
    # which also matched a `Name: Safe Links policy` line on a policy that
    # had `Enabled: False`. Parse the policy blocks and require an
    # explicitly Enabled=True entry of the right PolicyType.
    defender = fc.get("27_exchange_defender_policies.txt", "")
    safe_links_enabled, safe_attach_enabled = _count_defender_policy_state(defender)

    if safe_links_enabled > 0:
        add("4.5", "Ensure Safe Links is enabled", t.cis_cat_email, "pass",
            f"{safe_links_enabled} aktiv(e) Safe Links-policy(er)")
    elif "safelinks" in defender.lower() or "safe links" in defender.lower():
        # Policy exists but is disabled
        add("4.5", "Ensure Safe Links is enabled", t.cis_cat_email, "fail",
            "Safe Links-policy(er) finnes men er deaktivert")
    elif _section_ran(fc, "27_exchange_defender_policies.txt"):
        add("4.5", "Ensure Safe Links is enabled", t.cis_cat_email, "warn",
            "Ingen Safe Links-policyer funnet (krever Defender for Office 365)")
    else:
        add("4.5", "Ensure Safe Links is enabled", t.cis_cat_email, "info",
            _CANNOT_VERIFY + "Defender-policydata utilgjengelig")

    if safe_attach_enabled > 0:
        add("4.6", "Ensure Safe Attachments is enabled", t.cis_cat_email, "pass",
            f"{safe_attach_enabled} aktiv(e) Safe Attachments-policy(er)")
    elif "safeattach" in defender.lower() or "safe attach" in defender.lower():
        add("4.6", "Ensure Safe Attachments is enabled", t.cis_cat_email, "fail",
            "Safe Attachments-policy(er) finnes men er deaktivert")
    elif _section_ran(fc, "27_exchange_defender_policies.txt"):
        add("4.6", "Ensure Safe Attachments is enabled", t.cis_cat_email, "warn",
            "Ingen Safe Attachments-policyer funnet (krever Defender for Office 365)")
    else:
        add("4.6", "Ensure Safe Attachments is enabled", t.cis_cat_email, "info",
            _CANNOT_VERIFY + "Defender-policydata utilgjengelig")

    # ═══ 5. EMAIL AUTHENTICATION ═══

    # 5.1.1 Legacy auth blocked. The sharepoint parser returns legacy_auth=True
    # only when the settings dict contains "legacy auth: true"; if the audit
    # never reached SharePoint admin settings, the field defaults to False and
    # the control would silently report "pass" — a false attestation. Gate on
    # has_data so missing input is reported as info instead.
    if not sp.get("has_data"):
        add("5.1.1", "Ensure legacy authentication is blocked", t.cis_cat_identity, "info",
            "Kan ikke verifiseres — SharePoint-tenant-innstillinger utilgjengelig")
    elif sp.get("legacy_auth"):
        add("5.1.1", "Ensure legacy authentication is blocked", t.cis_cat_identity, "fail",
            t.cis_legacy_auth_enabled)
    else:
        add("5.1.1", "Ensure legacy authentication is blocked", t.cis_cat_identity, "pass",
            t.cis_legacy_auth_disabled)

    # 5.2.1/5.2.2/5.2.3 SPF, DMARC, DKIM per domain
    for d in spf:
        domain = d.get("domain", "")
        if not _is_audit_relevant_domain(domain):
            continue
        spf_s = d.get("spf", "")
        dmarc_s = d.get("dmarc", "")
        dkim_s = d.get("dkim", "")

        # SPF
        if "OK" in spf_s:
            add("5.2.1", f"Ensure SPF is configured — {domain}", t.cis_cat_email, "pass", spf_s)
        else:
            add("5.2.1", f"Ensure SPF is configured — {domain}", t.cis_cat_email, "fail",
                spf_s or t.cis_spf_missing)

        # DMARC
        dmarc_record = d.get("dmarc_record", "")
        dmarc_detail = dmarc_s
        if dmarc_record and dmarc_record != "(none)":
            dmarc_detail = f"{dmarc_s} — {dmarc_record}" if dmarc_s else dmarc_record
        if "reject" in dmarc_s.lower():
            add("5.2.2", f"Ensure DMARC is configured — {domain}", t.cis_cat_email, "pass", dmarc_detail)
        elif "quarantine" in dmarc_s.lower():
            add("5.2.2", f"Ensure DMARC is configured — {domain}", t.cis_cat_email, "partial", dmarc_detail)
        elif "p=none" in dmarc_s.lower() or "p=none" in dmarc_record.lower():
            add("5.2.2", f"Ensure DMARC is configured — {domain}", t.cis_cat_email, "partial",
                f"p=none (kun overvåking) — {dmarc_record}" if dmarc_record else dmarc_s)
        else:
            add("5.2.2", f"Ensure DMARC is configured — {domain}", t.cis_cat_email, "fail",
                dmarc_s or t.cis_dmarc_missing)

        # DKIM — M365 signing config or CNAME/TXT presence
        dkim1 = d.get("dkim1", "")
        dkim2 = d.get("dkim2", "")
        dkim_detail = dkim_s or dkim1 or ""
        dkim_valid = False
        if dkim_s and ("enabled" in dkim_s.lower() or "OK" in dkim_s):
            dkim_valid = True
        elif "cname" in dkim1.lower() or "cname" in dkim2.lower():
            dkim_valid = True  # Microsoft DKIM via CNAME selectors
        elif "k=rsa" in dkim1.lower() or "k=rsa" in dkim2.lower():
            dkim_valid = True  # Third-party DKIM key published
            dkim_detail = dkim1 or dkim2
        # The parser only creates dkim/dkim1/dkim2 when the DNS output carried
        # a DKIM line, so key presence is what separates "we looked and found
        # nothing" from "DKIM was never checked for this domain". Without the
        # distinction a domain whose DKIM lookup did not run failed the
        # control — once per domain, so a multi-domain tenant collected a
        # whole column of false failures.
        dkim_checked = any(k in d for k in ("dkim", "dkim1", "dkim2"))
        if dkim_valid:
            add("5.2.3", f"Ensure DKIM is enabled — {domain}", t.cis_cat_email, "pass", dkim_detail)
        elif dkim_detail:
            add("5.2.3", f"Ensure DKIM is enabled — {domain}", t.cis_cat_email, "fail", dkim_detail)
        elif dkim_checked:
            add("5.2.3", f"Ensure DKIM is enabled — {domain}", t.cis_cat_email, "fail", "No DKIM record found")
        else:
            add("5.2.3", f"Ensure DKIM is enabled — {domain}", t.cis_cat_email, "info",
                _CANNOT_VERIFY + "DKIM ikke kontrollert for dette domenet")

    # ═══ 6. DEVICES ═══

    # 6.1.1 The control is *literally* about compliance policies being
    # configured — not about how many devices currently meet them. The old
    # code only checked compliance_pct, so a tenant with 0 policies but 0
    # devices (everything looks "compliant" by default) would PASS. Look
    # at the policy file too. A tenant with policies + low %% gets partial;
    # a tenant with no policies at all gets fail regardless of %.
    policy_text = fc.get("11_intune_compliance_policies.txt", "")
    has_policies = (
        bool(policy_text.strip())
        and not policy_text.strip().startswith("Error:")
        and _count_data_lines(policy_text) > 0
    )
    has_devices = intune.get("has_data") and intune.get("total", 0) > 0
    if not has_policies and not has_devices:
        add("6.1.1", "Ensure device compliance policies are configured", t.cis_cat_devices, "info",
            t.cis_no_intune)
    elif not has_policies and not _section_ran(fc, "11_intune_compliance_policies.txt"):
        # Devices enrolled but the policy file was never written. "No
        # compliance policies configured" and "we could not read the
        # compliance policies" are the same absence here, and only one of
        # them is a CIS failure. This is the shape an empty-audit check
        # cannot catch: the Intune section half-succeeded.
        add("6.1.1", "Ensure device compliance policies are configured", t.cis_cat_devices, "info",
            _CANNOT_VERIFY + "Intune-compliance-policyer utilgjengelig")
    elif not has_policies:
        # Devices exist but no compliance policies — the control fails
        # regardless of how many devices look "compliant" (with no policy
        # to evaluate, compliance is undefined).
        add("6.1.1", "Ensure device compliance policies are configured", t.cis_cat_devices, "fail",
            "Enheter er enrolled, men ingen Intune-compliance-policyer er konfigurert")
    elif not has_devices:
        # Policies exist but no devices — pass on configuration, note absence
        add("6.1.1", "Ensure device compliance policies are configured", t.cis_cat_devices, "pass",
            f"{_count_data_lines(policy_text)} compliance-policy(er) konfigurert (ingen enheter enrolled)")
    else:
        cpct = intune.get("compliance_pct", 0)
        if cpct >= 90:
            add("6.1.1", "Ensure device compliance policies are configured", t.cis_cat_devices, "pass",
                t("cis_compliance_pct", pct=cpct))
        else:
            add("6.1.1", "Ensure device compliance policies are configured", t.cis_cat_devices, "partial",
                t("cis_compliance_partial", pct=cpct, noncompliant=intune.get('noncompliant', 0)))

    # ═══ 7. SHAREPOINT & DATA ═══

    # 7.2.1 SharePoint external sharing. The sharing_level comes from the
    # parser's sharing_map; "ok" = sharing limited or disabled (compliant),
    # "warning" = sharing allowed broadly. The previous version reported
    # "warn" for everything except "ok" — meaning a tenant configured for
    # ExternalUserAndGuestSharing (i.e. anyone-with-the-link) got an amber
    # flag instead of a red one. CIS 7.2.1 expects external sharing to be
    # *managed*, and "anyone" is the opposite of managed.
    # has_data alone is not enough: it is true as soon as the *site list*
    # parsed, and the sharing capability comes from the separate admin-
    # settings file. sharing_level == "unknown" is the parser saying it did
    # not read that field.
    if not sp.get("has_data") or sp.get("sharing_level") == "unknown":
        add("7.2.1", "Ensure SharePoint external sharing is managed", t.cis_cat_data, "info",
            "Kan ikke verifiseres — SharePoint-innstillinger utilgjengelig")
    else:
        sharing = sp.get("sharing_level", "")
        sharing_raw = (sp.get("sharing") or "").lower().replace(" ", "")
        if sharing == "ok":
            add("7.2.1", "Ensure SharePoint external sharing is managed", t.cis_cat_data, "pass",
                sp.get("sharing_label", ""))
        elif sharing_raw == "externaluserandguestsharing":
            # Anyone-with-the-link: explicit FAIL, not just WARN
            add("7.2.1", "Ensure SharePoint external sharing is managed", t.cis_cat_data, "fail",
                sp.get("sharing_label", t.cis_sp_open))
        else:
            add("7.2.1", "Ensure SharePoint external sharing is managed", t.cis_cat_data, "warn",
                sp.get("sharing_label", t.cis_sp_open))

    # 7.2.2 Retention policies
    retention_text = fc.get("19e_purview_retention_policies.txt", "")
    _ret_raw = purview.get("retention_policies", 0) if purview else 0
    ret_count = len(_ret_raw) if isinstance(_ret_raw, list) else (_ret_raw if isinstance(_ret_raw, int) else 0)
    if ret_count > 0 or retention_text.strip():
        add("7.2.2", "Ensure data retention policies are configured", t.cis_cat_data, "pass",
            f"{ret_count} oppbevaringspolicyer" if ret_count else "Oppbevaringspolicyer funnet")
    elif _section_ran(fc, "19e_purview_retention_policies.txt"):
        add("7.2.2", "Ensure data retention policies are configured", t.cis_cat_data, "warn",
            "Ingen oppbevaringspolicyer funnet")
    else:
        add("7.2.2", "Ensure data retention policies are configured", t.cis_cat_data, "info",
            _CANNOT_VERIFY + "Purview-oppbevaringsdata utilgjengelig")

    # ═══ 8. TEAMS ═══

    teams_ext = fc.get("16c_teams_external_access.txt", "")
    if teams_ext.strip():
        teams_ext_low = teams_ext.lower()
        if "blocked" in teams_ext_low or "disabled" in teams_ext_low:
            add("8.1.1", "Ensure external access in Teams is managed", t.cis_cat_teams, "pass",
                "Ekstern tilgang er begrenset")
        elif "allowed for all" in teams_ext_low or "everyone" in teams_ext_low or "no restrictions" in teams_ext_low:
            # Explicit fail when external access is wide open
            add("8.1.1", "Ensure external access in Teams is managed", t.cis_cat_teams, "fail",
                "Ekstern tilgang er uten begrensninger — anyone-mode")
        else:
            # Partial: some restriction in place but not "blocked" — review
            add("8.1.1", "Ensure external access in Teams is managed", t.cis_cat_teams, "warn",
                "Ekstern tilgang er aktivert med begrensninger — bør gjennomgås mot policy")
    else:
        add("8.1.1", "Ensure external access in Teams is managed", t.cis_cat_teams, "info",
            "Kan ikke verifiseres — Teams external access-data utilgjengelig")

    teams_settings = fc.get("16b_teams_settings.txt", "")
    if teams_settings.strip():
        add("8.1.2", "Ensure Teams guest access is reviewed", t.cis_cat_teams, "info",
            "Teams-innstillinger er hentet — gjennomgå gjeste-/eksternpolicyer")

    # ═══ 9. LOGGING & MONITORING ═══

    # 9.1 Unified audit log — gate on whether the directoryAudits file actually
    # contains events. Previously this was a hardcoded "pass" which meant every
    # tenant — even those with audit logging disabled — got a false PASS
    # attestation against CIS 9.1, ISO A.8.15 and NIST DE.CM-1. The directory
    # audit file is written by identity_security.py; if logging is off the call
    # still succeeds but returns zero events, which is exactly the case the
    # control is supposed to flag.
    audit_log_text = fc.get("19_entra_audit_log_admin_activity.txt", "")
    audit_log_data_rows = _count_data_lines(audit_log_text) if audit_log_text else 0
    if audit_log_text.strip().startswith("Error:") or not audit_log_text.strip():
        add("9.1", "Ensure unified audit logging is enabled", t.cis_cat_logging, "info",
            "Kan ikke verifiseres — audit-loggen er ikke hentet (mangler tilgang eller feilet)")
    elif audit_log_data_rows == 0:
        add("9.1", "Ensure unified audit logging is enabled", t.cis_cat_logging, "fail",
            "Audit-loggen ble hentet, men inneholder ingen hendelser — unified audit log "
            "kan være deaktivert (Set-AdminAuditLogConfig -UnifiedAuditLogIngestionEnabled $true)")
    else:
        add("9.1", "Ensure unified audit logging is enabled", t.cis_cat_logging, "pass",
            f"{audit_log_data_rows} hendelser i administrativ audit-logg de siste 14 dagene")

    # 9.2 Defender alerts. An empty alerts file was read as "no alerts", which
    # is only true when the alert query ran — the count file states that
    # explicitly, so require one of the two to have been written.
    defender_alerts = fc.get("19b_defender_active_alerts.txt", "")
    alert_count_text = fc.get("19b_defender_alert_count.txt", "")
    if defender_alerts.strip() and "0 active" not in alert_count_text.lower():
        add("9.2", "Ensure security alerts are monitored", t.cis_cat_logging, "warn",
            "Aktive Defender-varsler krever oppfølging")
    elif _section_ran(fc, "19b_defender_alert_count.txt", "19b_defender_active_alerts.txt"):
        add("9.2", "Ensure security alerts are monitored", t.cis_cat_logging, "pass",
            "Ingen aktive Defender-varsler")
    else:
        add("9.2", "Ensure security alerts are monitored", t.cis_cat_logging, "info",
            _CANNOT_VERIFY + "Defender-varseldata utilgjengelig")

    # 9.3 Risky users. Substring "high" matched "high availability" or any
    # other use of that word in the file (including the header). The signin
    # risk parser already gave us structured counts — use those.
    risky_struct = signin_risk if isinstance(signin_risk, dict) else {}
    risky_text = context.get("risky_users", "") if isinstance(context.get("risky_users"), str) else ""
    has_risky_data = bool(risky_text.strip()) and not risky_text.strip().startswith("Error:") \
        and "not available" not in risky_text.lower() and "requires" not in risky_text.lower()

    if not has_risky_data:
        add("9.3", "Ensure risky user detections are investigated", t.cis_cat_logging, "info",
            "Kan ikke verifiseres — risky-users-data utilgjengelig (krever Entra ID P2)")
    else:
        # Count structured rows: lines that look like "upn  risk-level  state"
        risky_rows = 0
        high_risk_rows = 0
        for line in risky_text.splitlines():
            stripped = line.strip()
            if (not stripped or stripped.startswith("=") or stripped.startswith("-")
                or "UPN" in stripped or "RISKY USERS" in stripped.upper()):
                continue
            cols = re.split(r'\s{2,}', stripped)
            if len(cols) >= 3 and "@" in cols[0]:
                risky_rows += 1
                if cols[1].strip().lower() in ("high", "medium"):
                    high_risk_rows += 1
        if high_risk_rows > 0:
            add("9.3", "Ensure risky user detections are investigated", t.cis_cat_logging, "fail",
                f"{high_risk_rows} brukere med høy/medium risiko oppdaget — krever undersøkelse")
        elif risky_rows > 0:
            add("9.3", "Ensure risky user detections are investigated", t.cis_cat_logging, "warn",
                f"{risky_rows} brukere flagget med risiko (lav nivå) — gjennomgå")
        else:
            add("9.3", "Ensure risky user detections are investigated", t.cis_cat_logging, "pass",
                "Ingen risikobrukere oppdaget")

    return controls


# ── Executive summary ──────────────────────────────────────────────────────────

def _build_executive_summary(context: dict, lang: str = "no") -> list[str]:
    t = T(lang)
    bullets = []
    users = context.get("users", {})
    mfa = context.get("mfa", {})
    ca = context.get("ca", {})
    ss = context.get("secure_score", {})
    intune = context.get("intune", {})
    azure = context.get("azure", {})
    admin = context.get("admin_roles", {})
    risk = context.get("risk", {})
    recs = context.get("recommendations", [])

    # Environment size. "The environment has 0 users (0 active, 0 guests)" is
    # not a description of a tenant, it is a description of a failed audit —
    # and it opened the summary.
    if users.get("has_data"):
        bullets.append(t("exec_env_size",
                         total=users.get('total', 0),
                         enabled=users.get('enabled', 0),
                         guests=users.get('guests', 0),
                         azure_resources=azure.get('total_resources', 0) if azure.get('has_data') else 0,
                         subscriptions=len(azure.get('subscriptions', [])) if azure.get('has_data') else 0))
    else:
        bullets.append(t.exec_env_size_unavailable)

    # MFA status — gate on has_data, not on pct. A tenant where every user is
    # unprotected scores 0%, and branching on the number alone announced the
    # single worst identity finding in the product as "data not available".
    if not mfa.get("has_data"):
        bullets.append(t.exec_mfa_unavailable)
    elif mfa.get("pct", 0) >= 95:
        bullets.append(t("exec_mfa_good", pct=mfa['pct']))
    else:
        bullets.append(t("exec_mfa_partial", pct=mfa.get('pct', 0), no_mfa=mfa.get('no_mfa', 0)))

    # Secure Score — same reasoning; 0% is a reading, not a missing reading.
    if ss.get("has_data"):
        if ss.get("pct", 0) >= 75:
            bullets.append(t("exec_ss_good", pct=ss['pct']))
        else:
            bullets.append(t("exec_ss_low", pct=ss['pct'], count=len(ss.get('improvements', []))))

    # Intune
    if intune.get("total", 0) > 0:
        if intune.get("noncompliant", 0) > 0:
            bullets.append(t("exec_intune_noncompliant",
                             noncompliant=intune['noncompliant'],
                             total=intune['total'],
                             pct=100-intune.get('compliance_pct', 0)))
        else:
            bullets.append(t("exec_intune_ok", total=intune['total']))

    # CA policies
    if ca.get("enabled", 0) > 0:
        bullets.append(t("exec_ca_active", count=ca['enabled']))

    # Critical findings
    critical_recs = [r for r in recs if r.get("priority") == "critical"]
    high_recs = [r for r in recs if r.get("priority") == "high"]
    if critical_recs:
        titles = [r["title"] for r in critical_recs[:3]]
        bullets.append(t("exec_critical_findings", count=len(critical_recs), titles='; '.join(titles)))
    if high_recs:
        bullets.append(t("exec_high_findings", count=len(high_recs)))

    # Admin roles
    ga = admin.get("global_admin_count", 0)
    if ga > 4:
        bullets.append(t("exec_ga_too_many", count=ga))

    # Overall. _compute_risk returns score=None / grade="?" when a blocking gap
    # makes the grade fiction; formatting that into "{score}/100" printed the
    # literal "None/100" in the customer-facing summary.
    if risk.get("score") is None:
        bullets.append(t.exec_overall_invalid)
    else:
        grade_text = {"A": t.exec_grade_a, "B": t.exec_grade_b, "C": t.exec_grade_c, "D": t.exec_grade_d}
        bullets.append(t("exec_overall",
                         grade=risk.get('grade', '?'),
                         score=risk['score'],
                         description=grade_text.get(risk.get('grade', 'C'), t.exec_grade_unknown)))

    return bullets


# ── Risk radar ─────────────────────────────────────────────────────────────────

def _build_risk_radar(context: dict, lang: str = "no") -> dict:
    """Compute risk scores per category for radar chart.

    Only axes backed by data we actually collected are returned. An axis whose
    source section failed, was throttled out, or never ran is *omitted* — not
    plotted at some neutral-looking default. A fabricated 80 on the Azure axis
    reads to a technician as "we checked Azure and it is fine", which is the
    opposite of the truth, and a fabricated 0 sends them chasing a finding that
    does not exist. Both are worse than an absent axis.

    Returns an empty dict when nothing can be scored. `_render_radar_svg`
    additionally declines to draw fewer than three axes, and the template hides
    the whole block when no SVG comes back.
    """
    t = T(lang)

    risk = context.get("risk", {})
    if risk.get("blocking_data_gaps"):
        return {}

    categories: dict[str, int] = {}

    # ── Identity (MFA + CA + admin roles) ────────────────────────────
    # Average over the inputs that were measured, not over all three. A failed
    # /identity/conditionalAccess/policies fetch reads as "0 policies enabled"
    # in the parsed dict, which used to drag this axis toward red on its own.
    identity_parts: list[float] = []
    mfa = context.get("mfa", {})
    if mfa.get("has_data"):
        identity_parts.append(min(100, mfa.get("pct", 0)))
    ca = context.get("ca", {})
    if ca.get("has_data"):
        ca_enabled = ca.get("enabled", 0)
        identity_parts.append(100 if ca_enabled >= 3 else ca_enabled * 30)
    admin_roles = context.get("admin_roles", {})
    if admin_roles.get("has_data"):
        ga = admin_roles.get("global_admin_count", 0)
        identity_parts.append(
            100 if 2 <= ga <= 4 else max(0, 100 - (ga - 4) * 20) if ga > 4 else 50
        )
    if identity_parts:
        categories[t.radar_identity] = min(100, int(sum(identity_parts) / len(identity_parts)))

    # ── Devices ──────────────────────────────────────────────────────
    # has_data means "the Intune audit produced a parseable report" — see
    # _parse_intune_devices — which is not the same as "this tenant enrols
    # devices". Both must hold before a compliance percentage means anything.
    intune = context.get("intune", {})
    if intune.get("has_data") and intune.get("total", 0) > 0:
        categories[t.radar_devices] = int(intune.get("compliance_pct", 0))

    # ── Email — only score customer-owned domains ────────────────────
    spf = context.get("spf_dmarc", [])
    email_score = 100
    scored_domains = 0
    for d in spf:
        if not _is_audit_relevant_domain(d.get("domain", "")):
            continue
        scored_domains += 1
        if "MISSING" in d.get("spf", "") or "MISSING" in d.get("dmarc", ""):
            email_score -= 30
        elif "WEAK" in d.get("spf", "") or "WEAK" in d.get("dmarc", ""):
            email_score -= 15
    # No relevant domain resolved means the DNS section did not run or returned
    # nothing — a perfect 100 there would be an assurance we never earned.
    if scored_domains:
        categories[t.radar_email] = max(0, email_score)

    # ── Azure ────────────────────────────────────────────────────────
    azure = context.get("azure", {})
    if azure.get("has_data"):
        azure_score = 80  # baseline for a subscription we could enumerate
        if azure.get("orphaned", 0) > 0:
            azure_score -= 10
        if azure.get("advisor_recs", 0) > 20:
            azure_score -= 20
        elif azure.get("advisor_recs", 0) > 5:
            azure_score -= 10
        categories[t.radar_azure] = max(0, azure_score)

    # ── Data Protection ──────────────────────────────────────────────
    # _parse_purview only sets has_data once it has found at least one label,
    # DLP policy, or retention policy, so the 50 baseline is a floor this axis
    # never actually lands on. That is deliberate: a tenant with none of the
    # three is indistinguishable from one where Purview was never collected,
    # and the honest rendering of "indistinguishable" is no axis at all.
    purview = context.get("purview", {})
    if purview.get("has_data"):
        data_score = 50  # baseline
        if purview.get("sensitivity_label_count", 0) > 0:
            data_score += 20
        if purview.get("dlp_policy_count", 0) > 0:
            data_score += 20
        if purview.get("retention_policy_count", 0) > 0:
            data_score += 10
        categories[t.radar_data] = min(100, data_score)

    return categories


def _render_radar_svg(categories: dict) -> str:
    """Render a radar/spider chart as inline SVG."""
    import math

    cats = list(categories.items())
    n = len(cats)
    if n < 3:
        return ""

    cx, cy = 150, 150  # center
    max_r = 120  # max radius

    # Build SVG
    svg = [f'<svg viewBox="0 0 300 320" xmlns="http://www.w3.org/2000/svg" style="max-width:400px;width:100%;">']

    # Background circles (grid)
    for pct in [25, 50, 75, 100]:
        r = max_r * pct / 100
        svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="0.5"/>')

    # Axis lines and labels
    for i, (label, score) in enumerate(cats):
        angle = (2 * math.pi * i / n) - math.pi / 2  # start from top
        x_end = cx + max_r * math.cos(angle)
        y_end = cy + max_r * math.sin(angle)
        svg.append(f'<line x1="{cx}" y1="{cy}" x2="{x_end:.1f}" y2="{y_end:.1f}" stroke="#d0d7de" stroke-width="0.5"/>')

        # Label
        lx = cx + (max_r + 20) * math.cos(angle)
        ly = cy + (max_r + 20) * math.sin(angle)
        anchor = "middle"
        if lx < cx - 10: anchor = "end"
        elif lx > cx + 10: anchor = "start"
        svg.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="11" fill="#6b7280" font-family="sans-serif" dominant-baseline="middle">{label}</text>')

        # Score label
        sx = cx + (max_r * score / 100 + 12) * math.cos(angle)
        sy = cy + (max_r * score / 100 + 12) * math.sin(angle)
        svg.append(f'<text x="{sx:.1f}" y="{sy:.1f}" text-anchor="middle" font-size="10" fill="#0f4c81" font-weight="700" font-family="sans-serif" dominant-baseline="middle">{score}</text>')

    # Data polygon
    points = []
    for i, (label, score) in enumerate(cats):
        angle = (2 * math.pi * i / n) - math.pi / 2
        r = max_r * score / 100
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        points.append(f"{x:.1f},{y:.1f}")

    svg.append(f'<polygon points="{" ".join(points)}" fill="rgba(15,76,129,0.15)" stroke="#0f4c81" stroke-width="2"/>')

    # Data points
    for i, (label, score) in enumerate(cats):
        angle = (2 * math.pi * i / n) - math.pi / 2
        r = max_r * score / 100
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#0f4c81"/>')

    svg.append('</svg>')
    return "\n".join(svg)


# ── Context builder ────────────────────────────────────────────────────────────

def build_report_context(
    customer_name: str,
    org_domain:    str,
    out_dir:       Path,
    results:       list[SectionResult],
    lang:          str = "no",
    frameworks:    str = "all",
) -> dict:
    from app.core.encryption import encrypted_read_text
    file_contents: dict[str, str] = {}
    failed_sections: list[str] = []
    for f in sorted(out_dir.glob("*.txt")):
        try:
            text = encrypted_read_text(f)
        except Exception:
            text = f.read_text(encoding="utf-8", errors="replace")
        if _is_error_payload(text):
            # Blanked deliberately. Eighteen parsers read these files and none
            # of them checked whether they held data or an error, so a failed
            # section was parsed as content: a two-line 404 from the Purview
            # endpoint became "2 sensitivity labels published", and the CIS
            # control for publishing labels passed on it. Handing the parsers
            # an empty string routes them into the paths that already say
            # "cannot be verified — data unavailable". The failure itself is
            # still reported: the section carries it as a warning.
            log.warning("Section %s holds an error rather than data — not parsed", f.name)
            failed_sections.append(f.name)
            text = ""
        file_contents[f.name] = text

    def fc(name: str) -> str:
        return file_contents.get(name, "")

    warn_files = [n for n in file_contents if "WARN" in n.upper()]
    all_warns  = [w for r in results for w in r.warns]

    secure_score = _parse_secure_score(fc("09_secure_score.txt"))
    users        = _parse_user_counts(fc("03_users_count.txt"))
    mfa          = _parse_mfa(fc("04_mfa_methods.txt"), fc("04b_mfa_ca_analysis.txt"), results)
    licenses     = _parse_licenses(fc("02_licenses.txt"))
    license_optimization = _analyze_license_optimization(licenses, file_contents, lang=lang)
    spf_dmarc    = _parse_spf_dmarc(fc("26_email_dns_spf_dmarc.txt"))
    ca           = _parse_ca_policies(fc("08_conditional_access.txt"))
    admin_roles  = _parse_admin_roles(fc("07_admin_roles.txt"))
    intune       = _parse_intune_devices(fc("10_intune_devices_count.txt"), fc("10_intune_devices.txt"))
    sharepoint   = _parse_sharepoint_settings(fc("15b_sharepoint_settings.txt"), fc("15_sharepoint_sites.txt"), lang=lang)
    oauth        = _parse_oauth_grants(fc("17b_oauth_consent_grants.txt"), fc("17_app_registrations.txt"))
    groups       = _parse_groups(fc("06_groups.txt"))
    azure        = _parse_azure_overview(file_contents)
    exchange     = _parse_exchange_overview(file_contents)
    backup_coverage = _parse_backup_coverage(file_contents)
    signin_risk  = _parse_signin_risk(file_contents)
    purview      = _parse_purview(file_contents)
    ext_fwd      = fc("28b_exchange_external_forwarding_WARN.txt")
    risky        = fc("18_risky_users.txt")
    defender     = fc("19b_defender_active_alerts.txt")
    network      = _parse_network_audit(file_contents)
    risk         = _compute_risk(secure_score, mfa, spf_dmarc, all_warns, ext_fwd, risky, defender,
                                 admin_roles, intune, sharepoint, oauth, network=network, lang=lang)
    recs         = _build_recommendations(mfa, spf_dmarc, secure_score, ext_fwd, risky, licenses,
                                          admin_roles, intune, sharepoint, oauth,
                                          azure, file_contents,
                                          backup_coverage=backup_coverage,
                                          signin_risk=signin_risk,
                                          network=network,
                                          lang=lang)

    # Build current metrics snapshot for trend comparison
    current_metrics = {
        "mfa_coverage_pct": mfa.get("pct", 0),
        "secure_score_pct": secure_score.get("pct", 0),
        "total_users": users.get("total", 0),
        "users_no_mfa": mfa.get("no_mfa", 0),
        "ca_policies_enabled": ca.get("enabled", 0),
        "intune_compliance_pct": intune.get("compliance_pct", 0.0),
        "intune_total_devices": intune.get("total", 0),
        "admin_roles_ga_count": admin_roles.get("global_admin_count", 0) if admin_roles else 0,
        "total_warns": len(all_warns),
        "risk_score": risk.get("score", 0),
        "risk_grade": risk.get("grade", ""),
    }
    prev = load_previous_metrics(out_dir)
    trends = _compute_trends(current_metrics, prev)
    metrics_history = load_metrics_history(out_dir)
    # Build full timeline: historical runs + current (for trend charts)
    metrics_timeline = metrics_history + [current_metrics]

    context = {
        "customer_name":   customer_name,
        "org_domain":      org_domain,
        "report_date":     datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "report_date_no":  datetime.now(timezone.utc).strftime("%d.%m.%Y"),
        "results":         results,
        "total_sections":  len(results),
        "done_sections":   sum(1 for r in results if r.status == SectionStatus.DONE),
        "skipped_sections":sum(1 for r in results if r.status == SectionStatus.SKIPPED),
        "failed_sections": sum(1 for r in results if r.status == SectionStatus.FAILED),
        "warn_files":      warn_files,
        "all_warns":       all_warns,
        "file_contents":   file_contents,
        # Parsed structured data
        "secure_score":    secure_score,
        "users":           users,
        "mfa":             mfa,
        "licenses":        licenses,
        "license_optimization": license_optimization,
        "spf_dmarc":       spf_dmarc,
        "ca":              ca,
        "admin_roles":     admin_roles,
        "intune":          intune,
        "sharepoint":      sharepoint,
        "oauth":           oauth,
        "groups":          groups,
        "azure":           azure,
        "exchange":        exchange,
        "backup_coverage": backup_coverage,
        "signin_risk":     signin_risk,
        "purview":         purview,
        "network":         network,
        "risk":            risk,
        "recommendations": recs,
        "finding_to_recs": _build_finding_rec_map(recs),
        # Trend comparison
        "previous_metrics": prev,
        "trends":           trends,
        "metrics_timeline": metrics_timeline,
        # Raw file snippets (still needed for tech report)
        "tenant_info":     fc("01_tenant.txt"),
        "ext_fwd_warn":    ext_fwd,
        "inbox_rule_warn": fc("29_exchange_inbox_rules_external_fwd_WARN.txt"),
        "risky_users":     risky,
        "defender_alerts": defender,
        "advisor_data":    fc("51_azure_advisor.txt"),
        "compliance_policies": fc("11_intune_compliance_policies.txt"),
        "app_registrations":   fc("17_app_registrations.txt"),
        "emergency_access":    fc("07c_emergency_access_check.txt"),
        "pim_assignments":     fc("07b_pim_eligible_assignments.txt"),
        "teams_info":          fc("16_teams.txt"),
        "teams_settings":      fc("16b_teams_settings.txt"),
        "teams_external":      fc("16c_teams_external_access.txt"),
        # Branding
        "branding":        get_branding(),
        "logo_dark":       _custom_logo_dark_b64(),
        "logo_light":      _custom_logo_b64(),
        # Version
        "app_version":     _get_app_version(),
        # Helpers
        "SectionStatus":   SectionStatus,
        "_severity":       _severity,
    }

    # Build compliance mapping after context is ready
    compliance = _build_compliance_map(context, lang=lang, frameworks=frameworks)
    compliance_pass = sum(1 for c in compliance if c["status"] == "pass")
    compliance_partial = sum(1 for c in compliance if c["status"] in ("partial", "warn"))
    compliance_fail = sum(1 for c in compliance if c["status"] == "fail")
    compliance_total = len(compliance)
    compliance_info = sum(1 for c in compliance if c["status"] == "info")
    compliance_assessed = compliance_total - compliance_info  # exclude "info" from scoring
    compliance_pct = round(compliance_pass / max(compliance_assessed, 1) * 100, 0)
    context["compliance"] = compliance
    context["compliance_pass"] = compliance_pass
    context["compliance_partial"] = compliance_partial
    context["compliance_fail"] = compliance_fail
    context["compliance_total"] = compliance_total
    context["compliance_assessed"] = compliance_assessed
    context["compliance_pct"] = compliance_pct
    context["show_nist"] = frameworks in ("cis+nist", "all")
    context["show_iso"]  = frameworks in ("cis+iso", "all")

    # Per-category compliance summary
    cat_summary: dict[str, dict] = {}
    for c in compliance:
        cat = c.get("category", "")
        if cat not in cat_summary:
            cat_summary[cat] = {"pass": 0, "partial": 0, "fail": 0, "info": 0, "warn": 0, "total": 0}
        cat_summary[cat][c["status"]] = cat_summary[cat].get(c["status"], 0) + 1
        cat_summary[cat]["total"] += 1
    context["compliance_by_category"] = cat_summary

    # Executive summary
    context["executive_summary"] = _build_executive_summary(context, lang=lang)

    # Risk radar
    risk_radar = _build_risk_radar(context, lang=lang)
    radar_svg = _render_radar_svg(risk_radar)
    context["risk_radar"] = risk_radar
    context["radar_svg"] = radar_svg

    # ── Remediation tracking ─────────────────────────────────────────────
    # Load per-customer remediation statuses so reports show what has been
    # addressed since the last audit.
    remediation = {}
    try:
        from app.core.customer import CustomerManager
        active_id = CustomerManager.get_active_id()
        if active_id:
            from app.services.remediation import load_remediation_sync
            remediation = load_remediation_sync(active_id)
    except Exception:
        pass  # non-critical — proceed without remediation data

    # Enrich each recommendation with its remediation status
    for rec in recs:
        title = rec.get("title", "")
        if title in remediation:
            rec["remediation"] = remediation[title]
        else:
            rec["remediation"] = {"status": "open", "notes": "", "updated_by": "", "updated_date": ""}

    context["remediation"] = remediation
    remediation_done = sum(1 for v in remediation.values() if v.get("status") in ("done", "ignored"))
    remediation_total = len(recs) if recs else 0
    context["remediation_done"] = remediation_done
    context["remediation_total"] = remediation_total
    context["remediation_pct"] = round(remediation_done / remediation_total * 100) if remediation_total else 0

    save_audit_metrics(out_dir, context)

    return context


# ── HTML generation ────────────────────────────────────────────────────────────

def generate_html(context: dict, output_path: Path, template_name: str) -> Path:
    env      = _jinja_env()
    template = env.get_template(template_name)
    html     = template.render(**context)
    from app.core.encryption import encrypted_write_text
    encrypted_write_text(output_path, html)
    return output_path


def generate_pdf(html_path: Path, output_path: Path) -> Path:
    try:
        from weasyprint import HTML

        from app.core.encryption import encrypted_read_text
        html_content = encrypted_read_text(html_path)
        HTML(string=html_content, base_url=str(html_path.parent)).write_pdf(str(output_path))
        return output_path
    except ImportError:
        raise RuntimeError("WeasyPrint ikke installert — PDF-generering utilgjengelig.")
    except Exception as e:
        raise RuntimeError(f"PDF-generering feilet: {e}")


# ── Main interface ─────────────────────────────────────────────────────────────

def generate_reports(
    customer_name: str,
    org_domain:    str,
    out_dir:       Path,
    results:       list[SectionResult],
    formats:       list[str] = ("html",),
    report_type:   str = "tech",   # "tech" or "customer"
    lang:          str = "no",     # "no" or "en"
    frameworks:    str = "all",    # "cis" | "cis+nist" | "cis+iso" | "all"
    theme:         str = "light",  # "light" or "dark"
) -> dict[str, Path]:
    context = build_report_context(customer_name, org_domain, out_dir, results, lang=lang, frameworks=frameworks)

    # Add translation helper — use {{ t.key }} or {{ t('key', count=5) }} in templates
    context["t"] = T(lang)
    context["lang"] = lang
    context["theme"] = theme

    template_name = "report_customer.html.j2" if report_type == "customer" else "report_tech.html.j2"
    suffix        = "_customer" if report_type == "customer" else "_tech"
    date_str      = datetime.now().strftime("%Y-%m-%d")

    output: dict[str, Path] = {}
    html_path = out_dir / f"audit_report{suffix}_{date_str}.html"

    if "html" in formats or "pdf" in formats:
        generate_html(context, html_path, template_name)
        output["html"] = html_path

    if "pdf" in formats:
        pdf_path = html_path.with_suffix(".pdf")
        generate_pdf(html_path, pdf_path)
        output["pdf"] = pdf_path

    return output
