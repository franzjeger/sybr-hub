"""Report generator — technical and customer-facing HTML/PDF reports."""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

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
        return "vunknown"


def _jinja_env() -> Environment:
    # autoescape=True, not select_autoescape(["html"]): the templates are named
    # ``*.html.j2``, and select_autoescape matches on the filename suffix, so
    # ``.j2`` fell through to its default (False) and every {{ value }} rendered
    # unescaped. Report context carries attacker-influenceable tenant data
    # (M365 display names, UPNs, device names), so that was a stored-XSS sink.
    # Escape everything; the one intentional-HTML value (radar_svg) is marked
    # ``| safe`` in the template.
    return Environment(
        loader        = FileSystemLoader(str(_TEMPLATES_DIR), encoding="utf-8"),
        autoescape    = True,
        trim_blocks   = True,
        lstrip_blocks = True,
    )


# ── Data parsers ───────────────────────────────────────────────────────────────

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
                tail = stripped[m_pct.end():].split()
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


# Column offsets of the MFA table, which the collector writes as
#   f"  {name:<35} {upn:<45} {mfa:>5} {ca:>4} {ca_excl:>8}  {methods}"
_MFA_COLS = {
    "display_name": (2, 37),
    "upn": (38, 83),
    "mfa": (84, 89),
    "ca": (90, 94),
    "ca_excl": (95, 103),
}


def _mfa_user_records(json_text: str, table_text: str) -> list[dict]:
    """Per-user MFA rows, preferring the collector's machine-readable sidecar.

    The table is fixed-width, and the collector truncates the display name to
    exactly the column width before padding it to that same width. At 35
    characters the padding disappears, one space separates name from UPN, and
    a reader that splits on runs of two-or-more spaces merges the two — every
    subsequent field shifts left by one, so the MFA column is read out of the
    CA column and the headline coverage figure is wrong in either direction. A
    doubled space inside a name ("Ola  Nordmann") shifts it the other way.

    So: use 04_mfa_methods.json when it is there, and for runs recorded before
    it existed, slice the table by column offset instead of by whitespace.
    """
    if json_text.strip():
        try:
            data = json.loads(json_text)
            users = data.get("users")
            if isinstance(users, list):
                return users
        except (ValueError, AttributeError):
            pass  # fall through to the table

    records: list[dict] = []
    for line in table_text.splitlines():
        stripped = line.strip()
        if (not stripped or stripped.startswith("=") or stripped.startswith("-")
                or "Display Name" in stripped or "MFA METHOD" in stripped
                or stripped.startswith("NOTE:")):
            continue

        if "|" in stripped:
            # Pipe-delimited: "Name | UPN | MFA:YES | CA:YES | CA_EXCL:NO"
            parts = [p.strip() for p in stripped.split("|")]
            if not any(p.startswith("MFA:") for p in parts):
                continue
            rec = {
                "display_name": parts[0] if parts else "",
                "upn": parts[1] if len(parts) > 1 else "",
                "mfa_registered": False, "ca_covered": False,
                "ca_excluded": False, "methods": [],
            }
            for p in parts:
                if p.startswith("MFA:"):
                    rec["mfa_registered"] = "YES" in p
                elif p.startswith("CA:"):
                    rec["ca_covered"] = "YES" in p
                elif p.startswith(("CA_EXCL:", "EXCL:")):
                    rec["ca_excluded"] = "YES" in p
            records.append(rec)
            continue

        def _col(key: str, _line: str = line) -> str:
            start, end = _MFA_COLS[key]
            return _line[start:end].strip()

        mfa_tok = _col("mfa")
        if mfa_tok not in ("YES", "NO", "?"):
            # Not the known layout — fall back to the old split so an
            # unrecognised historical format still yields something.
            cols = re.split(r'\s{2,}', stripped)
            if len(cols) < 3 or not any(c.strip() in ("YES", "NO") for c in cols[2:]):
                continue
            records.append({
                "display_name": cols[0].strip(),
                "upn": cols[1].strip() if len(cols) > 1 else "",
                "mfa_registered": "YES" in cols[2],
                "ca_covered": len(cols) > 3 and "YES" in cols[3],
                "ca_excluded": len(cols) > 4 and "YES" in cols[4],
                "methods": [],
            })
            continue

        records.append({
            "display_name": _col("display_name"),
            "upn": _col("upn"),
            # "?" is unknown, not "no MFA" — see the collector.
            "mfa_registered": None if mfa_tok == "?" else mfa_tok == "YES",
            "ca_covered": _col("ca") == "YES",
            "ca_excluded": _col("ca_excl") == "YES",
            "methods": [],
        })
    return records


def _parse_mfa(
    text: str,
    ca_analysis_text: str,
    results: list[SectionResult],
    json_text: str = "",
) -> dict:
    """Parse MFA coverage from mfa_methods.txt and CA analysis.

    A user is 'MFA covered' if they have MFA methods registered
    OR are covered by a Conditional Access policy that enforces MFA.
    """
    total = 0
    mfa_registered = 0
    ca_covered = 0
    ca_excluded = 0
    fully_unprotected = 0
    effectively_covered = 0
    unknown = 0

    records = _mfa_user_records(json_text, text)
    for rec in records:
        total += 1
        # None is "could not be determined". Counting it as False is what
        # turns a throttled run into a page of false "no MFA" findings.
        has_mfa = rec.get("mfa_registered") is True
        has_ca = bool(rec.get("ca_covered"))
        is_excluded = bool(rec.get("ca_excluded"))
        # A Conditional-Access exclusion means MFA is not *enforced* at sign-in:
        # the account opens with a password alone. A registered method is not
        # enforcement, so an exclusion vetoes coverage even for a user who has
        # a method registered. Treating a registered-but-excluded user as
        # covered is what let a Global Admin and a brute-forced account excluded
        # from the MFA policy score as "100% covered, 1.1.1 passed".
        covered = (has_mfa or has_ca) and not is_excluded

        # Unknown means the user's protection could not be established. A
        # failed method lookup on its own does not mean that: a Conditional
        # Access policy enforcing MFA settles the question whichever way the
        # lookup went. Counting such a user as unknown *and* as covered put
        # them in the numerator and took them out of the denominator, which
        # is how this read 102%.
        # A CA exclusion settles the question the same way a CA grant does: the
        # account is *known* to be unenforced, so it belongs in no_mfa, not in
        # the unknown bucket — even if the method lookup itself failed. Leaving
        # an excluded-and-unknown user in `unknown` drops them from no_mfa while
        # the recommendation still lists them by name, reintroducing the very
        # card-vs-list contradiction this pass removes.
        if rec.get("mfa_registered") is None and not covered and not is_excluded:
            unknown += 1

        if has_mfa:
            mfa_registered += 1
        if has_ca:
            ca_covered += 1
        if is_excluded:
            ca_excluded += 1
        if not has_mfa and not has_ca:
            fully_unprotected += 1
        if covered:
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

    # Users whose method lookup failed are unknown, not unprotected, so they
    # are excluded from both the headline count and its denominator. Counting
    # them as missing MFA made the figure say five users lack it while the
    # recommendation — which only names users whose status is known — listed
    # none of them, and it turns a throttled run into a page of false
    # findings. The count is still reported separately so it is not hidden.
    measured = max(0, total - unknown)
    # Every record counted as covered is one whose state was determined, so it
    # is inside `measured` by construction and this cannot exceed 100. The
    # assertion is the invariant, not a clamp: a clamp would have shown 100%
    # here and left the two sets quietly disagreeing.
    assert effectively_covered <= measured or measured == 0, (
        f"MFA numerator {effectively_covered} exceeds denominator {measured}"
    )
    pct = (effectively_covered / measured * 100) if measured > 0 else 0
    no_mfa = max(0, measured - effectively_covered)

    # Build per-user detail list for drill-down
    # Built from the same records as the figures above. This loop kept its own
    # whitespace splitter after the coverage counts moved off it, so the report
    # printed a red "1 user without MFA" directly above a table listing two —
    # one of them with MFA registered, and with the literal "YES" rendered
    # under the e-mail column, because every field had shifted by one. Both
    # readers used to be wrong in the same way and agreed; fixing only one is
    # what made the contradiction visible on the page.
    users_detail: list[dict] = []
    for rec in records:
        u_has_mfa = rec.get("mfa_registered") is True
        u_has_ca = bool(rec.get("ca_covered"))
        u_excluded = bool(rec.get("ca_excluded"))
        u_methods = ", ".join(rec.get("methods") or [])
        users_detail.append({
            "name": rec.get("display_name", ""),
            "upn": rec.get("upn", ""),
            "has_mfa": u_has_mfa,
            "has_ca": u_has_ca,
            "ca_excluded": u_excluded,
            "methods": u_methods if u_methods and u_methods != "(none)" else "",
            # A user whose lookup failed is unknown, not unprotected — keep them
            # out of the "these people have no MFA" table. But a CA *exclusion*
            # settles enforcement regardless of the lookup: such a user is known
            # to be unenforced and is counted in no_mfa by the coverage loop
            # above (its comment at "A CA exclusion settles the question…"), so
            # they must NOT be flagged unknown here either — otherwise the
            # partition below drops them from both buckets and no longer sums to
            # no_mfa. Mirror the coverage loop's rule (line ~295) exactly.
            "unknown": (rec.get("mfa_registered") is None
                        and not u_has_ca and not u_excluded),
            # Same enforcement rule as `covered` above: a CA exclusion means the
            # account is not MFA-enforced, registered method or not.
            "protected": (u_has_mfa or u_has_ca) and not u_excluded,
        })

    # Two different claims, reported apart. "Coverage" counts a user as
    # protected when an enabled CA policy will force MFA at sign-in, whether
    # or not they have ever registered a method — defensible, since the
    # account cannot be reached with a password alone. But it reads as
    # "everyone has MFA set up", and on the tenant this was written against
    # 47 of the 185 covered users had no method registered at all. The report
    # said 99.5% coverage on the same page as "42 users have no MFA methods",
    # and a reader could not reconcile the two. Both numbers are now named.
    registered_pct = round(mfa_registered / measured * 100, 1) if measured else 0.0
    # Split no_mfa into a clean partition, so the report can word it honestly: a
    # measured, not-covered user either has NO method registered at all, or has
    # one registered but is EXCLUDED from enforcement by a CA policy. Conflating
    # the two told customers to "register MFA" when the fix was to drop a CA
    # exclusion (M365 review, F1/F2). These two sum to no_mfa by construction.
    no_mfa_registered = sum(
        1 for u in users_detail if not u["unknown"] and not u["protected"] and not u["has_mfa"]
    )
    registered_but_excluded = sum(
        1 for u in users_detail if not u["unknown"] and not u["protected"] and u["has_mfa"]
    )
    return {
        "covered": effectively_covered,
        "registered_pct": registered_pct,
        "enforced_only": max(0, effectively_covered - mfa_registered),
        "total": total,
        "measured": measured,
        "unknown": unknown,
        "pct": round(pct, 1),
        "no_mfa": max(0, no_mfa),
        "no_mfa_registered": no_mfa_registered,
        "registered_but_excluded": registered_but_excluded,
        "mfa_registered": mfa_registered,
        "ca_covered": ca_covered,
        "ca_excluded": ca_excluded,
        "fully_unprotected": fully_unprotected,
        "users": users_detail,
        # `measured`, not `total`. `total` counts records; a record whose
        # lookup failed is a record, so a run where every single lookup was
        # throttled still had has_data True, pct 0, and cost the full 35-point
        # MFA weight — a grade B presented as a measurement of a tenant nobody
        # managed to read. Every consumer of this flag already handles False
        # correctly: the CIS control goes to "info", the executive summary
        # says unavailable, the radar axis skips the input, and the score
        # declares a blocking gap. The predicate was the only thing wrong.
        "has_data": measured > 0,
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
        # Compute the warn boundary from the raw used/total, not the collector's
        # ROUNDED printed pct — a true utilisation of 89.5% prints "90%" and
        # tripped the warning one seat early (accuracy sweep). Matches the
        # collector's own >=90 check on the unrounded ratio.
        warn = total > 0 and used / total >= 0.9
        licenses.append({
            "part": part, "name": _sku_friendly(part), "used": used, "total": total,
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
    licensed_stale_users = [s for s in licensed_stale if (s.get("upn") or "").lower() not in shared_upns]
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
            unused_licenses.append({
                "name": s["name"],
                "upn": s["upn"],
                "days_inactive": s["days_inactive"],
                "days_label": days_label,
            })
        total_waste += waste_amount

        suggestions.append({
            "type": "unused",
            "title": t("lo_suggest_remove_unused", count=len(licensed_stale_users)),
            "detail": t("lo_suggest_remove_unused_detail", count=len(licensed_stale_users), amount=waste_amount),
            "priority": "high",
            "savings": waste_amount,
        })

    if licensed_shared:
        shared_waste = len(licensed_shared) * avg_price
        total_waste += shared_waste
        suggestions.append({
            "type": "shared_mailbox_licensed",
            "title": t("lo_suggest_shared_licensed", count=len(licensed_shared)),
            "detail": t("lo_suggest_shared_licensed_detail", count=len(licensed_shared), amount=shared_waste),
            "priority": "medium",
            "savings": shared_waste,
        })

    # 2. Over-provisioned SKUs: purchased > assigned (unused seats being paid for)
    for lic in licenses:
        unused_count = lic["total"] - lic["used"]
        if unused_count > 5 and lic["total"] > 0 and lic["pct"] < 70:
            price = _SKU_MONTHLY_PRICE.get(lic["part"], 0)
            waste = unused_count * price
            over_provisioned.append({
                "part": lic["part"],
                "name": _sku_friendly(lic["part"]),
                "used": lic["used"],
                "total": lic["total"],
                "unused": unused_count,
                "monthly_waste": waste,
            })
            if waste > 0:
                total_waste += waste
                suggestions.append({
                    "type": "over_provisioned",
                    "title": t("lo_suggest_reduce_sku", part=_sku_friendly(lic["part"])),
                    "detail": t("lo_suggest_reduce_sku_detail",
                                part=_sku_friendly(lic["part"]), unused=unused_count,
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
                "name": _sku_friendly(e5["part"]),
                "users": e5["used"],
                "potential_saving_per_user": price_diff,
                "potential_saving_total": e5["used"] * price_diff,
            })
            suggestions.append({
                "type": "downgrade",
                "title": t("lo_suggest_downgrade", part=_sku_friendly(e5["part"])),
                "detail": t("lo_suggest_downgrade_detail",
                            part=_sku_friendly(e5["part"]), users=e5["used"],
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
        # Report-only first. Graph spells that state
        # "enabledForReportingButNotEnforced", which starts with "enabled", so
        # testing for "[enabled" ahead of it swallowed every report-only policy
        # into the enabled count and left the branch below unreachable. A
        # tenant staging its Conditional Access in report-only mode — where
        # nothing is enforced — was reported as having those policies live.
        if (l.startswith("[reportonly") or l.startswith("[report_only")
                or l.startswith("[enabledforr")):
            report_only += 1
        elif l.startswith("[enabled"):
            enabled += 1
        elif l.startswith("[disabled"):
            disabled += 1
        # Legacy pipe format
        elif "|" in line:
            squashed = l.replace(" ", "")
            if ("enabled" in l and "disabled" not in l
                    and "reportonly" not in squashed
                    and "enabledforreporting" not in squashed):
                enabled += 1
            elif "disabled" in l:
                disabled += 1
            elif "reportonly" in l.replace(" ", ""):
                report_only += 1
    total = enabled + disabled + report_only
    legacy = _parse_ca_legacy_auth_block(text)
    return {
        "enabled": enabled,
        "disabled": disabled,
        "report_only": report_only,
        "has_data": audit_succeeded or total > 0,
        "blocks_legacy_auth": legacy["blocks"],
        "has_client_app_data": legacy["collected"],
    }


# Legacy client apps in Graph's vocabulary. A policy scoped to these and
# nothing else is a legacy-authentication block; one scoped to "all" is a
# broad policy that happens to include them, which is a different thing and
# deliberately not counted.
_LEGACY_CLIENT_APPS = {"exchangeactivesync", "other"}

# Grant controls a legacy client cannot satisfy. "block" is the modern way to
# write it. "mfa" has the same effect and predates the block control: legacy
# protocols have no way to perform a second factor, so the grant can never be
# met and the sign-in is refused. Grading that tenant as a failure would be a
# false finding about a tenant that has in fact closed the hole.
_LEGACY_DENYING_GRANTS = {"block", "mfa"}


def _parse_ca_legacy_auth_block(text: str) -> dict:
    """Whether an enabled CA policy blocks legacy authentication.

    Read from the policy's own client-app scope and grant control, not from
    its name. A policy called "Block legacy authentication" is evidence of
    what someone intended to build, not of what it does — and the tenant this
    was written against has one that is Microsoft-managed, so the name is not
    even the administrator's word for it.

    "collected" separates a tenant that has no such policy from an audit taken
    before the client-app scope was written to the section file at all. Without
    that the control would read every older audit as a failure.
    """
    blocks = False
    collected = False
    state = ""
    grants: list[str] = []
    apps: set[str] = set()

    def verdict() -> bool:
        # Scoped to legacy clients only, and blocking. A policy covering "all"
        # client apps is not a legacy-auth block even though it catches them.
        return (
            state == "enabled"
            and bool(apps)
            and apps <= _LEGACY_CLIENT_APPS
            and bool(set(grants) & _LEGACY_DENYING_GRANTS)
        )

    for line in text.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("["):
            blocks = blocks or verdict()
            state = low[1:].split("]")[0].strip()
            grants, apps = [], set()
        elif low.startswith("grant controls:"):
            grants = [g.strip().lower() for g in stripped.split(":", 1)[1].split(",")]
        elif low.startswith("client apps:"):
            collected = True
            value = stripped.split(":", 1)[1].strip()
            if value.lower() != "not specified":
                apps = {a.strip().lower() for a in value.split(",") if a.strip()}

    blocks = blocks or verdict()
    return {"blocks": blocks, "collected": collected}


# The collector writes fixed-width columns — groups_roles.py:186 —
#   f"  {role:<40} {display:<30} {upn:<45}"
# with an optional last-sign-in column appended when it has the users list.
# Splitting on runs of whitespace loses to that format twice over: a display
# name of exactly 30 characters leaves a single space before the UPN, and the
# sign-in column means the *last* field is a timestamp rather than an email —
# so "@" in cols[-1] is False and every assignment came back with the user and
# email fields shifted one column to the left. Slice by the offsets instead.
_ADMIN_ROLE_SPAN    = (2, 42)
_ADMIN_DISPLAY_SPAN = (43, 73)
_ADMIN_UPN_SPAN     = (74, 119)
_ADMIN_DISPLAY_WIDTH = _ADMIN_DISPLAY_SPAN[1] - _ADMIN_DISPLAY_SPAN[0]
_UPN_TOKEN_RE = re.compile(r'\S+@\S+')


def _admin_role_record(line: str) -> dict | None:
    """Slice one fixed-width assignment line, or None if it is not one.

    Two shapes are accepted. The first is the collector's own, sliced at its
    column offsets. The second is a file written before the collector truncated
    the role name to its width: an over-long role eats its own padding and
    shifts every later field right, but the *display* column is still padded to
    30, so the UPN's position still fixes where the two columns before it begin.
    """
    if len(line) < _ADMIN_UPN_SPAN[0] or not line.startswith("  "):
        return None

    def _record(role_end: int, upn_start: int) -> dict | None:
        role = line[2:role_end].strip()
        display = line[upn_start - _ADMIN_DISPLAY_WIDTH - 1:upn_start - 1].strip()
        upn = line[upn_start:upn_start + 45].strip()
        if not role or "@" not in upn:
            return None
        return {"role": role, "user": display, "email": upn}

    # The column separators have to actually be separators before the offsets
    # mean anything.
    if line[_ADMIN_ROLE_SPAN[1]] == " " and line[_ADMIN_DISPLAY_SPAN[1]] == " ":
        fixed = _record(_ADMIN_ROLE_SPAN[1], _ADMIN_UPN_SPAN[0])
        if fixed:
            return fixed

    # Shifted row: anchor on the UPN and count back over the padded display
    # column. The sign-in column never contains "@", so the last such token on
    # the line is the UPN.
    tokens = _UPN_TOKEN_RE.findall(line)
    if not tokens:
        return None
    upn_start = line.rfind(tokens[-1])
    sep = upn_start - _ADMIN_DISPLAY_WIDTH - 2
    if sep < 2 or line[sep] != " " or line[upn_start - 1] != " ":
        return None
    return _record(sep, upn_start)


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

        # Format 2: the collector's own fixed-width columns.
        fixed = _admin_role_record(line)
        if fixed:
            roles.append(fixed)
            continue

        # Format 3: any other columnar "Role   User   email@domain" layout.
        cols = re.split(r'\s{2,}', stripped)
        # Drop a trailing sign-in column so the email stays last for the tests
        # below — the fixed-width path above handles the collector's own lines,
        # but a role or UPN long enough to overflow its column lands here.
        if len(cols) >= 4 and "@" not in cols[-1] and "@" in cols[-2]:
            cols = cols[:-1]
        if len(cols) >= 3:
            # Last column should look like an email or UPN
            if "@" in cols[-1]:
                roles.append({"role": cols[0], "user": cols[1], "email": cols[-1]})
            elif len(cols) >= 2:
                roles.append({"role": cols[0], "user": " ".join(cols[1:-1]) if len(cols) > 2 else cols[1], "email": cols[-1]})
    # Graph's displayName for the global admin role is "Company Administrator"
    # — the collector says so at groups_roles.py:10 and counts both. Matching
    # only the friendly name meant a tenant that reports the legacy one had
    # ga_count == 0: CIS 1.1.3 emitted no row at all, because every branch
    # tests a count that could not be reached, and the admin-sprawl penalty
    # silently dropped out of the risk score.
    _GA_ROLE_NAMES = ("Global Administrator", "Company Administrator")
    ga_count = sum(1 for r in roles if r["role"] in _GA_ROLE_NAMES)
    role_counts: dict[str, int] = {}
    for r in roles:
        role_counts[r["role"]] = role_counts.get(r["role"], 0) + 1
    role_summary = sorted(
        [{"role": k, "count": v} for k, v in role_counts.items()],
        key=lambda x: (-x["count"], x["role"]),
    )
    global_admin_users = [r for r in roles if r["role"] in _GA_ROLE_NAMES]
    return {
        "roles": roles,
        "global_admin_count": ga_count,
        "global_admin_users": global_admin_users,
        "total_assignments": len(roles),
        "unique_roles": len(role_counts),
        "role_summary": role_summary,
        "has_data": len(roles) > 0,
    }


def _first_prose_line(text: str) -> str:
    """The first sentence under a "(not available)" banner.

    The collector writes the cause there — which permission, or which licence
    — so the report can say it instead of offering the reader a guess between
    two possibilities the audit had already told apart.
    """
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or set(stripped) == {"="}:
            continue
        if "(not available)" in stripped.lower():
            continue
        if stripped.lower().startswith(("error details", "graph said")):
            continue
        return stripped
    return ""


def _parse_usage(summary_text: str, detail_text: str) -> dict:
    """Licence usage, which the licence inventory alone cannot report.

    subscribedSkus says how many seats are assigned. It says nothing about
    whether anyone signed into them, and "106 of 106 assigned" reads as
    healthy right up until you learn a fifth of them have not been touched
    in a quarter.
    """
    result = {"total": 0, "active": 0, "no_activity": 0, "licensed_idle": 0,
              "period_days": 90, "concealed": False,
              "has_data": False, "unavailable": False, "unavailable_reason": ""}
    if _evidence_unavailable(summary_text) and _evidence_unavailable(detail_text):
        if (summary_text or detail_text or "").strip():
            result["unavailable"] = True
            result["unavailable_reason"] = (
                _first_prose_line(detail_text) or _first_prose_line(summary_text)
            )
        return result

    fields = {
        "total": "total", "active users": "active", "no activity": "no_activity",
        "licensed without activity": "licensed_idle", "period days": "period_days",
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


def _parse_entra_devices(count_text: str, detail_text: str) -> dict:
    """The directory's own device register, beside the Intune one.

    Its whole purpose is the gap between the two counts: devices the tenant
    has, minus devices Intune manages, is the unmanaged-endpoint finding. With
    only the Intune figure, a tenant with forty joined machines and no
    enrolment read as "no devices found".
    """
    result = {"total": 0, "managed": 0, "unmanaged": 0, "enabled": 0,
              "has_data": False, "unavailable": False, "unavailable_reason": ""}
    if _evidence_unavailable(count_text) and _evidence_unavailable(detail_text):
        if (count_text or detail_text or "").strip():
            result["unavailable"] = True
            result["unavailable_reason"] = (
                _first_prose_line(detail_text) or _first_prose_line(count_text)
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


def _parse_intune_devices(count_text: str, detail_text: str) -> dict:
    result = {"total": 0, "windows": 0, "ios": 0, "android": 0, "macos": 0,
              "compliant": 0, "noncompliant": 0, "unknown": 0,
              "compliance_pct": 0.0, "devices": [],
              "unavailable": False, "unavailable_reason": ""}

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
        result["unavailable_reason"] = _first_prose_line(detail_text) or _first_prose_line(count_text)
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

    # Three states, not two. The collector did not write this line at all until
    # recently, and reading its absence as "false" meant the control that
    # grades it passed on every tenant ever audited, whatever the setting was.
    legacy_raw = settings.get("legacy auth", "").strip().lower()
    legacy_auth = legacy_raw == "true"
    legacy_known = legacy_raw in ("true", "false")

    # Counted through the shared helper rather than a local loop. The loop here
    # skipped only "===" lines, so the banner, the column header and the "---"
    # rule were each counted as a site: a tenant with 105 sites was reported as
    # having 108.
    site_count = _count_data_lines(sites_text)

    # A personal site is identified by its host, not by the word "personal"
    # appearing anywhere on the line. This tenant has an ordinary team site
    # named "Personal FF HF" at /sites/pers, which the substring match filed as
    # a OneDrive — the one "personal" site in a report where there are none.
    personal_sites = sum(
        1 for line in sites_text.splitlines()
        if "-my.sharepoint.com" in line.lower() or "/personal/" in line.lower()
    )

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
        # Whether the consent-grants file itself was readable. has_data can be
        # True from app registrations alone while the consent-grants read failed;
        # this lets the score flag that instead of crediting the missing read as
        # "no high-privilege apps" (accuracy sweep). NB: build_report_context
        # blanks an error-payload file to "" before this parser runs, so this
        # text-based check is only a fallback for direct callers — the reader
        # overrides grants_read from error_files, which survives the blanking.
        "grants_read": not text.lstrip().startswith("Error"),
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


# The collector distinguishes "the tenant is not licensed for this" from "the
# app registration may not read it". Only the first is a finding about the
# customer; the second is a finding about our own configuration, and a report
# must not present one as the other.
_LICENCE_GAP_RE = re.compile(r"licence gap|lisens", re.IGNORECASE)

# Successful sign-ins that, alongside 50+ failures, mark a probable stale/cached
# credential (a device retrying an old password) rather than a guessing attack.
_STALE_CREDENTIAL_SUCCESSES = 20


def _parse_signin_risk(file_contents: dict[str, str]) -> dict:
    """Parse sign-in activity and failure data for risk analysis."""
    result: dict = {
        "total_signins": 0,
        "unique_users": 0,
        "total_failures": 0,
        "top_failure_users": [],
        "top_failure_reasons": [],
        "top_error_codes": [],
        "top_source_countries": [],
        "top_source_ips": [],
        "brute_force_suspects": [],
        "stale_credential_users": [],
        "has_data": False,
        "no_data_reason": None,
    }

    # Per-user successful sign-ins, kept to tell a stale cached credential (many
    # successes interleaved with the failures) from a real password attack.
    success_by_user: dict[str, int] = {}

    # Parse sign-in activity (05_signin_activity.txt)
    signin_text = file_contents.get("05_signin_activity.txt", "")
    if _evidence_unavailable(signin_text):
        # The collector writes a "(not available)" block naming the cause.
        # Reading it as data would have set has_data from its mere presence and
        # published a tenant with zero sign-ins and zero failures; writing no
        # file at all — the old behaviour on a 403 — made the whole section
        # vanish from the document without a word, so a reader could not tell
        # it had been attempted. Carry the reason instead, and say it.
        if not signin_text.strip():
            result["no_data_reason"] = "not_collected"
        elif _LICENCE_GAP_RE.search(signin_text):
            result["no_data_reason"] = "license_p1_missing"
        else:
            result["no_data_reason"] = "not_collected"
    elif signin_text.strip():
        users_seen: set[str] = set()
        signin_count = 0
        for line in signin_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("=") or stripped.startswith("-"):
                continue
            if stripped.upper().startswith("NOTE") or stripped.upper().startswith("NO "):
                continue
            # The collector puts the event count in its banner —
            # "SIGN-IN ACTIVITY  (last 30 days — 1234 events)" — which carries
            # no "key: value" colon, so the branch below never saw it and the
            # fallback set total_signins to the number of rendered rows. That
            # is the user count, so "Total sign-ins" and "Unique users" came
            # out identical while the real figure sat unread in the file.
            _banner = re.search(r'\(.*?([\d,]+)\s+events\)', stripped)
            if _banner:
                try:
                    result["total_signins"] = int(_banner.group(1).replace(",", ""))
                except ValueError:
                    pass
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
                    # cols == [UPN, Success, Failures, Unknown, Total]; keep the
                    # success count for the brute-force-vs-stale classifier.
                    if len(cols) >= 2 and cols[1].replace(",", "").isdigit():
                        success_by_user[cols[0].lower()] = int(cols[1].replace(",", ""))

        if result["total_signins"] == 0 and signin_count > 0:
            result["total_signins"] = signin_count
        if result["unique_users"] == 0 and users_seen:
            result["unique_users"] = len(users_seen)
        if signin_text.strip():
            result["has_data"] = True

    # Parse sign-in failures (05b_signin_failures.txt)
    failure_text = file_contents.get("05b_signin_failures.txt", "")
    if not _evidence_unavailable(failure_text):
        result["has_data"] = True
        failure_users: dict[str, int] = {}
        failure_reasons: dict[str, int] = {}
        error_code_rows: list[dict] = []
        country_rows: list[dict] = []
        ip_rows: list[dict] = []
        total_failures = 0
        # The file is the per-user table followed by labelled breakdown blocks.
        # Track which block we are in so a country name is not read as a failure
        # reason and an error code is not read as a user's failure count.
        section = "users"

        def _num_tail(cols: list[str]) -> int | None:
            tail = cols[-1].replace(",", "") if cols else ""
            return int(tail) if tail.isdigit() else None

        for line in failure_text.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("TOP ERROR CODES"):
                section = "codes"
                continue
            if upper.startswith("TOP SOURCE COUNTRIES"):
                section = "countries"
                continue
            if upper.startswith("TOP SOURCE IP"):
                section = "ips"
                continue
            if not stripped or stripped.startswith("=") or stripped.startswith("-"):
                continue
            if stripped.upper().startswith("NOTE") or stripped.upper().startswith("NO "):
                continue
            # The section banner ("SIGN-IN FAILURES  (last 30 days ...)") sits
            # between the rule lines and would otherwise be read as a failure
            # reason, printing itself in the report's "common failure reasons".
            if upper.startswith("SIGN-IN FAILURES"):
                continue

            if section == "codes":
                cols = re.split(r'\s{2,}', stripped)
                cnt = _num_tail(cols)
                if cnt is not None and len(cols) >= 2:
                    error_code_rows.append({
                        "code": cols[0],
                        "reason": cols[1] if len(cols) >= 3 else "",
                        "count": cnt,
                    })
                continue
            if section == "countries":
                cols = re.split(r'\s{2,}', stripped)
                cnt = _num_tail(cols)
                if cnt is not None and len(cols) >= 2:
                    country_rows.append({"country": " ".join(cols[:-1]), "count": cnt})
                continue
            if section == "ips":
                cols = re.split(r'\s{2,}', stripped)
                cnt = _num_tail(cols)
                if cnt is not None and len(cols) >= 2:
                    ip_rows.append({"ip": " ".join(cols[:-1]), "count": cnt})
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
                    elif not p.startswith("*"):   # skip the "*** THRESHOLD ***" flag
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
                        elif (c.lower() not in ("true", "false", "yes", "no")
                              and len(c) > 3 and not c.startswith("*")):
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

        result["top_error_codes"] = error_code_rows[:10]
        result["top_source_countries"] = country_rows[:10]
        result["top_source_ips"] = ip_rows[:10]

        # Strict > 50 to match the collector's own "*** THRESHOLD EXCEEDED ***"
        # flag (signins._FAILURE_THRESHOLD, `cnt > 50`). >= 50 flagged a user at
        # exactly 50 that the evidence file did not, so the finding and its
        # evidence disagreed on who crossed the line (accuracy sweep).
        #
        # Failure count alone cannot tell an attack from a stale cached password:
        # a device retrying an old credential produces a burst of failures
        # *interleaved with successful sign-ins*, while a genuine guessing attack
        # has few or no successes. A user over the threshold with many successes
        # is therefore reported separately at low severity, not among brute-force
        # suspects — which also stops the false "under active password attack"
        # MFA label for that account (it reads brute_force_suspects).
        suspects: list[str] = []
        stale: list[str] = []
        for u, c in failure_users.items():
            if c <= 50:
                continue
            if success_by_user.get(u.lower(), 0) >= _STALE_CREDENTIAL_SUCCESSES:
                stale.append(u)
            else:
                suspects.append(u)
        result["brute_force_suspects"] = suspects
        result["stale_credential_users"] = stale

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

    # DLP and retention policies are written as `_section_block` dumps — the
    # same "[i] then Key: Value" format the anti-phish parser reads. The
    # line-based reader that used to live here did not understand that format:
    # it counted the "(none)" empty placeholder as one policy and each field
    # line of a real policy as another, so an empty section reported "1 DLP
    # policy" and the card disagreed with the raw data printed below it.
    # Delegate to the block parser so empty -> 0 and each policy counts once.
    dlp_text = file_contents.get("19d_purview_dlp_policies.txt", "")
    if dlp_text.strip():
        result["dlp_policies"] = [{"name": n} for n in _extract_policy_names(dlp_text)]
        result["dlp_policy_count"] = len(result["dlp_policies"])
        if result["dlp_policy_count"] > 0:
            result["has_data"] = True

    retention_text = file_contents.get("19e_purview_retention_policies.txt", "")
    if retention_text.strip():
        result["retention_policies"] = [
            {"name": n} for n in _extract_policy_names(retention_text)
        ]
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

    # Inbox rules with external forwarding.
    #
    # The collector signals the finding by renaming the file, not by writing
    # anything inside it: rules found go to 29_..._WARN.txt, and the plain name
    # is the all-clear. Reading only the plain name meant this count was zero
    # precisely when it should not have been, and that number is printed on the
    # customer-facing report — while CIS 4.4 on the same report flagged the
    # forwarding correctly, because it reads the WARN file. The report
    # contradicted itself, and the reassuring half was the wrong half.
    #
    # Same trap 4.4 itself fell into once; see the note on that check.
    inbox_rules_text = (
        file_contents.get("29_exchange_inbox_rules_external_fwd_WARN.txt", "")
        or file_contents.get("29_exchange_inbox_rules_external_fwd.txt", "")
    )
    result["inbox_rules_external"] = _count_data_lines(inbox_rules_text)

    result["has_data"] = (
        result["mailbox_total"] > 0
        or result["transport_rules"] > 0
        or len(result["antiphish_policies"]) > 0
        or result["forwarding_count"] > 0
    )
    return result


# Permissive about what surrounds the count: banners in the wild include
# "(5 total)", "(0 entries)" and "(last 14 days — 0 events)". Requiring the
# digits to follow the parenthesis directly missed the third and counted it as
# an audit-log event.
_HEADER_TOTAL_RE = re.compile(
    r'^[A-Z][^\(]*\(.*\b\d+\s+[A-Za-z][A-Za-z-]*\b.*\)\s*$'
)
# Banner counts: pull the parenthesised part, then take the first number that
# is attached to a word meaning "how many". The vocabulary is deliberate —
# position alone cannot decide it, as two real banners show:
#
#   "(26 total: 26 permanent, 0 time-bound/activated)"  -> 26, the first number
#   "(last 14 days — 0 events)"                         -> 0, the last one
#
# Neither first-wins nor last-wins is right; "total" and "events" are the
# count words and "days" is not. An unrecognised banner yields None and the
# caller counts rows, which is the safe direction.
_BANNER_PARENS_RE = re.compile(r'\(([^)]*)\)')
_BANNER_COUNT_RE = re.compile(
    r'\b(\d+)\s+(?:total|entries|found|unresolved|events?|mailboxes|results?|'
    r'assignments?|policies|devices)\b',
    re.IGNORECASE,
)


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


_EMPTY_PLACEHOLDER_RE = re.compile(
    r'^\(?\s*(none|ingen|n/?a|empty|tom)\s*\)?\.?$', re.IGNORECASE
)
# "[1]" — the per-record index a multi-line section writes before its fields.
_RECORD_INDEX_RE = re.compile(r'^\[\d+\]$')
# "Name: Scanner spam-bypass" — a field line inside such a record. The field
# name may be lower-case: 22_exchange_connectors.txt writes "outbound:" and
# "inbound:", and requiring a capital meant its one record was not recognised
# as multi-line at all. Row counting then reported the tenant's single
# connector as three, on the customer-facing report as well as the technical
# one. Only a file that already carries "[n]" index lines can reach the
# multi-line branch, so relaxing this cannot pull a plain table into it.
_RECORD_FIELD_RE = re.compile(r'^[A-Za-z][A-Za-z ]{0,30}:\s')


def _looks_like_column_header(line: str, *, near_rule: bool = True) -> bool:
    """True for a table header row or a bare section title.

    Two shapes, both of which were being counted as data:

    "Policy Name  Platform  Created" — columns split on runs of whitespace, at
    least two of them, every token starting with a capital and none carrying
    the characters that mark real data (digits, @, /, :).

    "USER INVENTORY" — a single all-caps title with no banner count after it.
    That one made every bannerless section read one too high.

    The column shape alone is not enough, because real rows land on it. Two
    that did: an OAuth grant reading "AvePoint Fly | Microsoft Graph |
    User.Read", and a PIM assignment whose principal name was truncated to
    exactly the column width, closing the gap that would have exposed the
    lower-case "servicePrinc" beside it. Eleven consent grants and one
    privileged assignment were being dropped from their counts.

    So position decides. Every header these collectors emit is written against
    a "---" or "===" rule, and across a full audit that held without exception:
    67 of 67 headers sat next to one, and all 12 lines matching the column
    shape away from a rule were data. near_rule carries that context in; the
    all-caps title needs no such help, since a lone capitalised word is not a
    record in any of these files.

    Mistaking a data row for a header undercounts, which is the same class of
    error this exists to prevent.
    """
    stripped = line.strip()
    cols = [c for c in re.split(r'\s{2,}', stripped) if c]

    if len(cols) == 1:
        return (
            stripped == stripped.upper()
            and any(ch.isalpha() for ch in stripped)
            and not any(ch.isdigit() or ch in "@/:" for ch in stripped)
        )

    if not near_rule:
        return False

    return all(
        c[:1].isupper() and not any(ch.isdigit() or ch in "@/:" for ch in c)
        for c in cols
    )


def _parse_banner_count(text: str) -> int | None:
    """Pull the authoritative count from a collector banner.

    Many audit files write `SECTION NAME  (N total)` as their header. That's
    the number the collector intended; trying to re-count by scanning data
    rows is error-prone because column headers and continuation lines look
    like data.

    Returns None when there is no banner *or* when the file carries more than
    one. 32_pim_roles.txt is the reason for the second case: it holds two
    sub-sections, "ELIGIBLE ... (0 total)" followed by "ACTIVE ASSIGNMENTS
    (26 total: ...)". Taking the first banner as the file's count reported zero
    privileged assignments for a tenant with twenty-six permanent ones, two of
    them Global Administrator. No single number describes such a file, so the
    caller falls back to counting rows.
    """
    counts: list[int] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for inside in _BANNER_PARENS_RE.findall(stripped):
            found = _BANNER_COUNT_RE.findall(inside)
            if found:
                counts.append(int(found[0]))
                break

    if len(counts) != 1:
        return None
    return counts[0]


def _is_furniture(stripped: str, *, near_rule: bool = True) -> bool:
    """True for a line that is never data, whichever branch is counting.

    Separators, NOTE prose, "(none)" placeholders, column headers and the
    section banner itself. Counting any of these is how a tenant with no Intune
    compliance policies came to be reported as having one, and how two empty
    Purview sections passed their CIS controls.

    near_rule says whether this line sits against a "---" or "===" rule, which
    is what separates a column header from a data row that happens to share its
    shape. It defaults to True so a caller judging a line in isolation keeps
    the older, more aggressive reading.
    """
    if not stripped:
        return True
    if stripped.startswith(("=", "-", "#")):
        return True
    if stripped.upper().startswith("NOTE") or stripped.upper().startswith("NO "):
        return True
    if _EMPTY_PLACEHOLDER_RE.match(stripped):
        return True
    if _looks_like_column_header(stripped, near_rule=near_rule):
        return True
    if _HEADER_TOTAL_RE.match(stripped):
        return True
    return False


def _is_underlined(stripped_lines: list[str], i: int) -> bool:
    """True when line i is immediately underlined by a "---" rule.

    Underlined, not merely near a rule: the first data row of every table sits
    directly below the rule that underlines the header, so "next to a rule"
    catches it too, and eleven OAuth consent grants stayed missing.

    A dashed rule specifically. "===" frames titles and closes the file, so
    accepting it would eat the last row of a table instead — which is a real
    row, and the first version of this did exactly that. Across a full audit
    all 39 column headers were underlined by "---" and none by "===".
    """
    nxt = stripped_lines[i + 1] if i + 1 < len(stripped_lines) else ""
    return nxt.startswith("---")


def _is_multiline_record_format(text: str) -> bool:
    """True when a section renders one record across several lines.

    Transport rules are the case that matters: each rule is an "[n]" index
    followed by indented "Key: value" lines and a free-text Description that
    wraps. Row counting cannot work on that shape at all — one rule with a
    four-line description reads as nine rows.
    """
    indexed_records = 0
    keyed_lines = 0
    for line in text.splitlines():
        stripped = line.strip()
        if _RECORD_INDEX_RE.match(stripped):
            indexed_records += 1
        elif _RECORD_FIELD_RE.match(stripped):
            keyed_lines += 1
    return indexed_records > 0 and keyed_lines > indexed_records


def _count_table_rows(stripped_lines: list[str]) -> int:
    """Count the rows inside a section's tables, not every line in the file.

    These files carry more than their table. A summary block follows the rows
    in PIM and in mailbox delegations; a severity tally precedes them in the
    Defender alerts; the compliance score holds two tables under one banner.
    Counting the whole file made all four disagree with their own headers —
    one privileged-assignment file read thirty-one where twenty-six were
    listed, because four summary lines and a heading were counted as records.

    A table is what a "---" rule underlines: the header sits on the rule, and
    the rows run until a blank line, a "===" frame, or the next header. Files
    with no such structure fall back to counting the whole thing, which is what
    every count file and free-text section needs.
    """
    def underlined(i: int) -> bool:
        s = stripped_lines[i]
        return bool(s) and not s.startswith(("---", "===")) and _is_underlined(stripped_lines, i)

    if not any(underlined(i) for i in range(len(stripped_lines))):
        return sum(1 for s in stripped_lines if not _is_furniture(s))

    # One pass, because the regions overlap otherwise. A sub-section banner is
    # underlined by the same kind of rule as the column header beneath it, so
    # treating every underlined line as the start of its own table counted the
    # PIM assignments twice and its column headers as records — thirty-one
    # became fifty-four. Walking once, a header simply opens the table and the
    # next header closes it.
    rows = 0
    in_table = False
    for i, s in enumerate(stripped_lines):
        if underlined(i):
            in_table = True          # a heading or a column header; never a row
            continue
        if not in_table:
            continue
        if not s or s.startswith("==="):
            in_table = False         # blank line or frame ends the table
            continue
        if s.startswith("---"):
            continue                 # the rule under a header, or a divider
        if not _is_furniture(s, near_rule=False):
            rows += 1
    return rows


def _count_data_lines(text: str) -> int:
    """How many records a section file holds.

    Three branches, in priority order. They are named and separate on purpose:
    this used to be decided implicitly by which regex happened to match first,
    and the answer came out wrong in both directions.

    1. Banner declares zero. Settled, whatever the vocabulary — entries, total,
       found, unresolved, events, mailboxes. No row counting runs, because the
       rows in an empty section are furniture and counting them is precisely
       the bug: "(0 entries)" over a "(none)" placeholder was read as one
       policy, and passed a CIS control on it.

    2. Banner declares N > 0 and the file uses a multi-line record format.
       The banner wins; see _is_multiline_record_format.

    3. Anything else — a plain table, one record per line. Rows win and the
       banner is only a sanity check. A file listing one row is one row even if
       its header claims twelve; a disagreement means the output was truncated,
       so the smaller honest number is used and the mismatch is logged.
    """
    declared = _parse_banner_count(text)

    # Branch 1 — declared empty.
    if declared == 0:
        return 0

    # Branch 2 — declared non-empty, records span lines.
    if declared is not None and _is_multiline_record_format(text):
        return declared

    # Branch 3 — tabular, or no banner at all.
    stripped_lines = [line.strip() for line in text.splitlines()]
    rows = _count_table_rows(stripped_lines)
    if declared is not None and declared != rows:
        # The two directions mean different things and the message used to
        # assert truncation for both. Fewer rows than declared is consistent
        # with truncated output. More rows than declared is not — the section
        # cannot hold records the collector never wrote — so it means extra
        # lines are being counted, typically a summary or a second table under
        # one banner. Naming which one is observed keeps the log from claiming
        # a cause it has no evidence for.
        cause = ("output may be truncated" if rows < declared
                 else "non-record lines may be counted")
        log.warning(
            "Section banner declares %d record(s) but %d row(s) are present — "
            "using the row count; %s", declared, rows, cause
        )
    return rows


def _extract_policy_names(text: str) -> list[str]:
    """One name per policy from a ``_section_block`` dump.

    The block format numbers each policy ``[i]`` and follows it with
    ``Key: Value`` field lines; an empty section is written as ``(none)``. The
    previous reader treated every non-header line as a policy name, so it
    counted the ``(none)`` placeholder as one policy and each of a policy's
    field lines as a separate policy — a single six-field anti-phish policy read
    as "7". Count the ``[i]`` blocks and take each block's Name/Identity field
    (only the first, so a policy carrying both Name and Identity is not doubled).
    """
    names: list[str] = []
    have_block = False
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^\[\d+\]$", stripped):
            if have_block:
                names.append(current or f"Policy {len(names) + 1}")
            have_block = True
            current = None
            continue
        if have_block and current is None and ":" in stripped:
            key, val = stripped.split(":", 1)
            if key.strip().lower() in ("name", "identity", "policyname", "policy"):
                v = val.strip()
                if v:
                    current = v
    if have_block:
        names.append(current or f"Policy {len(names) + 1}")
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
    """Parse network audit data from saved quick-audit JSON files.

    A file that is present but will not parse is *not* the same as no network
    audit. Both used to produce has_data=False, and the caller reads that to
    decide whether to run _compute_network_risk at all — so a malformed file
    dropped the firewall findings and their risk penalty, and the customer
    scored better for it. Unreadable is now recorded and reported as itself.
    """
    import json as _json
    result: dict = {
        "fortigate": None,
        "unifi": None,
        "has_data": False,
        # Files that had content and could not be read. Empty is the good case;
        # non-empty means the report is missing findings it should have had.
        "unreadable": [],
    }
    for name, key in (("60_fortigate_audit.txt", "fortigate"),
                      ("61_unifi_audit.txt", "unifi")):
        raw = file_contents.get(name, "")
        if not raw.strip():
            continue
        try:
            result[key] = _json.loads(raw)
            result["has_data"] = True
        except Exception as exc:
            result["unreadable"].append(name)
            log.warning(
                "Network audit file %s is present but could not be parsed (%s). "
                "Its findings and their risk penalty are missing from this report.",
                name, exc,
            )
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
    unavailable_sections: list[str] | None = None,
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
        # The collector keeps unknowns out of both sides of the fraction,
        # which is right — a throttled lookup is not a user without MFA. But
        # the percentage that survives is then measured on a subset, and
        # nothing said so. Ninety of a hundred lookups failing still read as
        # "100% MFA coverage, grade A" on the strength of ten users.
        _unknown = mfa.get("unknown", 0)
        if _unknown:
            data_quality_issues.append(
                f"MFA-dekning målt på {mfa.get('measured', 0)} av "
                f"{mfa.get('total', 0)} brukere — {_unknown} oppslag feilet"
            )
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
    # A failed DoH lookup comes back as "ERROR (...)", never MISSING/WEAK, so an
    # errored domain silently contributes 0 penalty. Track whether any domain
    # produced a real verdict: if the whole set errored, the 10 points are not
    # "earned clean", they are unmeasured — flag it like every other axis. And
    # match p=none on the classifier's actual token ("p=none"), not "NONE", which
    # never matched and let a monitor-only DMARC policy score clean (accuracy sweep).
    email_penalty = 0
    email_measured = 0
    for d in spf_dmarc:
        spf   = d.get("spf", "")
        dmarc = d.get("dmarc", "")
        spf_errored   = spf.strip().upper().startswith("ERROR")
        dmarc_errored = dmarc.strip().upper().startswith("ERROR")
        if not (spf_errored and dmarc_errored):
            email_measured += 1
        if not spf_errored:
            if "MISSING" in spf or "CRITICAL" in spf:
                email_penalty = max(email_penalty, 10)
            elif "WEAK" in spf or "WARN" in spf:
                email_penalty = max(email_penalty, 5)
        if not dmarc_errored:
            if "MISSING" in dmarc:
                email_penalty = max(email_penalty, 8)
            elif "p=none" in dmarc.lower() or "WEAK" in dmarc.upper():
                email_penalty = max(email_penalty, 5)
            elif "quarantine" in dmarc.lower():
                # p=quarantine is CIS "partial", not a clean pass — reject is the
                # target. The classifier tokenises it as "WARN (p=quarantine)",
                # which matched none of the branches above, so a monitor-stronger-
                # than-none-but-not-reject policy scored as clean here just as it
                # did on the radar. Small penalty, mirroring the partial credit.
                email_penalty = max(email_penalty, 3)
    score -= email_penalty
    if spf_dmarc and email_measured == 0:
        data_quality_issues.append("E-postsikkerhet ikke vurdert — DNS-oppslag feilet")

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
        sharing = sharepoint.get("sharing_level")
        if sharing == "warning":
            score -= 3
        if sharepoint.get("legacy_auth"):
            score -= 2
        # has_data means the site *list* was read; the tenant sharing/legacy-auth
        # settings are a separate admin read that can fail while the sites
        # succeed. When those fields were never established, that is unmeasured,
        # not a clean pass — flag it (accuracy sweep).
        if sharing in (None, "unknown") or not sharepoint.get("legacy_auth_known"):
            data_quality_issues.append("SharePoint-konfigurasjon utilgjengelig")
    elif sharepoint is not None and not sharepoint.get("has_data"):
        data_quality_issues.append("SharePoint-konfigurasjon utilgjengelig")

    # ── OAuth high-privilege apps ────────────────────────────────────
    if oauth and oauth.get("has_data"):
        if len(oauth.get("high_privilege_apps", [])) > 5:
            score -= 3
        # has_data can be True from app registrations alone; if the consent-grants
        # read itself failed, the high-privilege count is incomplete, not clean.
        if not oauth.get("grants_read", True):
            data_quality_issues.append("OAuth-grants utilgjengelig")
    elif oauth is not None and not oauth.get("has_data"):
        data_quality_issues.append("OAuth-grants utilgjengelig")

    # ── Critical findings ────────────────────────────────────────────

    # External forwarding (up to 10 pts) — any active forwarding is severe
    if ext_fwd and ext_fwd.strip():
        # Count only the actual "mailbox → target" rows — the same arrow the
        # finding-fwd rec keys on. The old banner/prose filter still counted a
        # header line as a rule, over-penalising by one (accuracy sweep). The
        # min-5 floor keeps "any forwarding present is severe".
        fwd_lines = [l for l in ext_fwd.splitlines() if "→" in l]
        score -= min(10, max(5, len(fwd_lines) * 2))

    # Risky users (up to 5 pts). The guard against reading a refusal as a
    # finding was already here; what was missing is that it said nothing. A
    # tenant without Entra ID P2, or one where the fetch was refused, scored
    # identically to one verified to have no risky users.
    _risky_n = _reported_count(risky_users)
    if _evidence_unavailable(risky_users):
        # Only when the file exists and turned out to be prose. An absent file
        # means the section never ran, and that is already declared by name
        # through unavailable_sections; this branch covers the case that one
        # cannot see — the section reported DONE and one fetch inside it did not.
        if risky_users and risky_users.strip():
            data_quality_issues.append(
                "Risikobrukere ikke vurdert — krever Entra ID P2 og AuditLog-tilgang"
            )
    elif _risky_n is not None:
        if _risky_n > 0:
            score -= 5
    elif risky_users and "No risky" not in risky_users and risky_users.strip():
        score -= 5

    # Defender alerts (up to 10 pts) — scale with number of alerts.
    # The collector writes "Error: {ex}" into this file when the fetch fails,
    # and that stub is truthy, does not say "No active", and is not empty — so
    # it counted as one alert and cost four points. A 403 on the Defender
    # endpoint scored the same as a tenant with a live phishing alert, with
    # nothing to say the alert was invented. Every other reader of this file
    # already checks; the score was the one that did not.
    if _evidence_unavailable(defender):
        if defender and defender.strip():
            data_quality_issues.append(
                "Defender-varsler utilgjengelig — ingen vurdering av aktive varsler"
            )
    else:
        alert_count = _reported_count(defender)
        if alert_count is None and defender and "No active" not in defender and defender.strip():
            # No count in the header. Fall back to counting rows, as before.
            alert_lines = [l for l in defender.strip().splitlines()
                           if l.strip() and not l.strip().startswith("=")
                           and not l.strip().startswith("-")]
            alert_count = max(1, len(alert_lines))
        if alert_count:
            # 3 pts base + 1 per alert, capped at 10
            score -= min(10, 3 + alert_count)

    # ── Network security (up to 15 pts) ────────────────────────────
    if network and network.get("has_data"):
        net_risk = _compute_network_risk(network)
        score -= net_risk["penalty"]
    # A file that would not parse is an input this function could not read, and
    # that is what data_quality_issues is for — every other unverifiable input
    # is declared there. Not blocking: the network is worth 15 points against
    # MFA's 35, so refusing to grade the whole tenant over one corrupt file is
    # heavier than the gap warrants. But it must be visible beside the score,
    # not only in a recommendation further down the report.
    # A section that did not run keeps its points. The collector records the
    # failure and the report counts it, but the count never reached the score,
    # so a tenant whose Exchange collection failed — which the collector itself
    # calls a routine outcome — scored as though Exchange were clean, with
    # nothing beside the score to say otherwise.
    for _section in unavailable_sections or []:
        data_quality_issues.append(
            f"{_section} ble ikke fullført — funnene derfra mangler i scoren"
        )

    for _unreadable in (network or {}).get("unreadable", []):
        data_quality_issues.append(
            f"Nettverksaudit utilgjengelig — {_unreadable} kunne ikke leses "
            f"(scoren mangler inntil 15 poeng straff)"
        )

    # A FortiGate that answered its status probe but refused the admin or policy
    # sub-read reports those counts as None. The admin/policy findings key on the
    # (now empty) lists, so a refused read renders "no 2FA/trust-host/allow-all
    # issues" — a false clean. Declare it, matching the whole-section contract.
    _fg = (network or {}).get("fortigate")
    if isinstance(_fg, dict) and "error" not in _fg:
        if _fg.get("admin_count") is None:
            data_quality_issues.append(
                "FortiGate-administratorer kunne ikke leses — 2FA/trust-host-funn mangler")
        if _fg.get("policy_count") is None:
            data_quality_issues.append(
                "FortiGate-brannmurregler kunne ikke leses — allow-all/logging-funn mangler")

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


def _apply_critical_floor(risk: dict, recs: list[dict], lang: str = "no") -> dict:
    """Cap the letter grade when there are unaddressed critical findings.

    A weighted numeric score can average a critical away: a tenant with two
    critical findings and 0% Intune compliance read "B / Satisfactory" because
    the score still cleared 60. The number is kept, but the grade is floored so
    the headline cannot say "good" over an open critical — cap at C for one or
    two criticals, D for more (M365 review, F9). Mutates and returns risk.
    """
    if risk.get("score") is None:   # "?" / invalid — nothing to floor
        return risk
    criticals = sum(1 for r in recs if r.get("priority") == "critical")
    if criticals == 0:
        return risk
    t = T(lang)
    order = ["A", "B", "C", "D", "F"]
    cap = "C" if criticals <= 2 else "D"
    cap_meta = {"C": (t.risk_level_needs_action, "orange"), "D": (t.risk_level_weak, "red")}
    grade = risk.get("grade", "A")
    if grade in order and order.index(grade) < order.index(cap):
        risk["grade"] = cap
        risk["level"], risk["color"] = cap_meta[cap]
        risk["capped_by_criticals"] = criticals
    return risk


def _build_finding_rec_map(recs: list[dict]) -> dict[str, list[int]]:
    """Build a mapping from finding_id → list of recommendation indices (1-based)."""
    result: dict[str, list[int]] = {}
    for rec in recs:
        fid = rec.get("finding_id", "")
        if fid:
            result.setdefault(fid, []).append(rec.get("rec_index", 0))
    return result


# Registered-method labels (04_mfa_methods) → the authentication-methods policy
# IDs (09b) that make them usable. A phone can be used via SMS or Voice, so it is
# only unusable when BOTH are disabled.
#
# The keys MUST be the exact display labels the collector emits, i.e. the values
# of users_mfa._METHOD_LABELS — a mismatch makes _auth_method_lockout_users treat
# the method as an unrecognised (assumed-usable) label and silently drop the
# lockout warning for anyone whose only method is that one. tests/test_recommendation_identity.py
# cross-checks the two maps so they cannot drift again (M365 review follow-up).
_METHOD_LABEL_TO_POLICY: dict[str, set[str]] = {
    "Authenticator App":     {"microsoftAuthenticator"},
    "Phone (SMS/Call)":      {"sms", "voice"},
    "FIDO2 Key":             {"fido2"},
    "OATH TOTP":             {"softwareOath"},
    "Windows Hello":         {"windowsHelloForBusiness"},
    "Temp Access Pass":      {"temporaryAccessPass"},
    "Email OTP":             {"email"},
    "Certificate":           {"x509Certificate"},
}


def _disabled_auth_methods(policy_text: str) -> set[str]:
    """Method IDs the authentication-methods policy (09b) reports as disabled."""
    disabled: set[str] = set()
    for line in policy_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lower() == "disabled":
            disabled.add(parts[0])
    return disabled


def _auth_method_lockout_users(mfa: dict, policy_text: str) -> list[str]:
    """Users whose EVERY registered method is disabled in the policy.

    Enforcing MFA would lock these accounts out — the report never compared the
    two files, so the discrepancy went unflagged (M365 review, F5). Conservative:
    an unrecognised method label is assumed usable, so this only fires when a
    user has methods and none of them can be used.
    """
    disabled = _disabled_auth_methods(policy_text)
    if not disabled:
        return []
    locked_out: list[str] = []
    for u in mfa.get("users") or []:
        methods = [m.strip() for m in (u.get("methods") or "").split(",") if m.strip()]
        if not methods:
            continue
        usable = False
        for label in methods:
            ids = _METHOD_LABEL_TO_POLICY.get(label)
            if ids is None or any(pid not in disabled for pid in ids):
                usable = True
                break
        if not usable:
            locked_out.append(f"{u.get('name', '')} ({u.get('upn', '')})")
    return locked_out


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

    # Which collected file each recommendation was formed from. Inline rather
    # than in a lookup table, as the CIS controls use: the key "finding-email"
    # is shared by two recommendations, and a value sitting in the same dict as
    # the verdict cannot drift away from the code that produced it.
    #
    # Only files this run collected are named, so a citation always points at
    # something the reader can open.
    def ev(*names: str) -> list[str]:
        have = file_contents or {}
        return [n for n in names if have.get(n, "").strip()]

    # A Conditional-Access exclusion removes MFA enforcement. When the excluded
    # account is also a Global Admin or is being actively brute-forced, that is
    # not a footnote in the raw data — it is the most exposed account in the
    # tenant, reachable with a password alone. It gets its own dedicated critical
    # finding, computed FIRST so the same account is not also counted by the
    # general MFA rec below: surfacing one account as two criticals is the
    # double-count the review flagged (M365 review, F2).
    excluded_users = [u for u in (mfa.get("users") or []) if u.get("ca_excluded")]
    high_risk: list[str] = []
    high_risk_upns: set[str] = set()
    if excluded_users:
        ga_emails = {
            (g.get("email") or "").strip().lower()
            for g in (admin_roles or {}).get("global_admin_users", [])
        }
        bf_emails = {
            (u or "").strip().lower()
            for u in (signin_risk or {}).get("brute_force_suspects", [])
        }
        for u in excluded_users:
            upn = (u.get("upn") or "").strip().lower()
            reasons = []
            if upn and upn in ga_emails:
                reasons.append(t.rec_mfa_excluded_ga)
            if upn and upn in bf_emails:
                reasons.append(t.rec_mfa_excluded_bruteforce)
            if reasons:
                label = u.get("name") or u.get("upn") or ""
                high_risk.append(f"{label} ({u.get('upn', '')}) — {', '.join(reasons)}")
                if upn:
                    high_risk_upns.add(upn)

    # Users without enforced MFA that are NOT already the dedicated high-risk
    # finding above. Naming the same account here too is what let no_mfa say "2"
    # while the two criticals described one account each. Only emit if there is
    # someone left to name, so the count in the title matches the list under it.
    if mfa.get("has_data"):
        fc = file_contents or {}
        not_enforced = [
            f"{r.get('display_name', '')} ({r.get('upn', '')})"
            for r in _mfa_user_records(
                fc.get("04_mfa_methods.json", ""), fc.get("04_mfa_methods.txt", "")
            )
            # Someone whose status we know AND who is not MFA-enforced: no method
            # registered, or registered but CA-excluded (the exclusion means MFA
            # is not enforced). Minus anyone already in finding-mfa-excluded.
            if (((r.get("mfa_registered") is False and not r.get("ca_covered"))
                 or r.get("ca_excluded"))
                and (r.get("upn") or "").strip().lower() not in high_risk_upns)
        ]
        # Count = the summary no_mfa less the high-risk accounts already moved to
        # finding-mfa-excluded, so the same account is never counted by both
        # criticals; suppress the rec entirely when every not-enforced account is
        # already covered there (M365 review, F2).
        adjusted_no_mfa = max(0, mfa.get("no_mfa", 0) - len(high_risk_upns))
        if adjusted_no_mfa > 0:
            # The high-risk excluded accounts are broken out into
            # finding-mfa-excluded, and this card's title (adjusted_no_mfa) and
            # sub_items already exclude them. The detail breakdown must exclude
            # them too, or it re-describes — and re-counts — the accounts the
            # other critical already owns, so the card's own numbers stop adding
            # up (title says N, "X have no method; Y are excluded" sums to more).
            # Each high-risk account is CA-excluded, so it sits in exactly one
            # partition bucket: registered_but_excluded if it has a method, else
            # no_mfa_registered. Subtract it from that bucket so
            # no_mfa_registered + registered_but_excluded == adjusted_no_mfa.
            hr_registered = sum(
                1 for u in (mfa.get("users") or [])
                if (u.get("upn") or "").strip().lower() in high_risk_upns
                and u.get("has_mfa")
            )
            hr_no_method = len(high_risk_upns) - hr_registered
            detail = t("rec_mfa_detail",
                        registered=mfa.get('mfa_registered', 0),
                        ca_covered=mfa.get('ca_covered', 0),
                        no_mfa_registered=max(0, mfa.get('no_mfa_registered', 0) - hr_no_method),
                        registered_but_excluded=max(0, mfa.get('registered_but_excluded', 0) - hr_registered))
            recs.append({
                "priority": "critical",
                "evidence": ev("04_mfa_methods.txt", "04b_mfa_ca_analysis.txt"),
                "finding_id": "finding-mfa",
                "title": t("rec_mfa_title", count=adjusted_no_mfa),
                "detail": detail,
                "effort": t.rec_effort_low,
                "sub_items": not_enforced[:50],
                "doc_url": "https://learn.microsoft.com/en-us/entra/identity/authentication/concept-mfa-howitworks",
            })

    if high_risk:
        recs.append({
            "priority": "critical",
            "evidence": ev("04b_mfa_ca_analysis.txt", "07_admin_roles.txt"),
            "finding_id": "finding-mfa-excluded",
            "title": t("rec_mfa_excluded_title", count=len(high_risk)),
            "detail": t.rec_mfa_excluded_detail,
            "effort": t.rec_effort_immediate,
            "sub_items": high_risk[:50],
            "doc_url": "https://learn.microsoft.com/en-us/entra/identity/conditional-access/concept-conditional-access-users-groups",
        })

    for d in spf_dmarc:
        if not _is_audit_relevant_domain(d.get("domain", "")):
            continue
        if "MISSING" in d.get("dmarc", "") or "WEAK" in d.get("dmarc", ""):
            recs.append({
                "priority": "high",
                "finding_id": "finding-email",
                "evidence": ev("26_email_dns_spf_dmarc.txt"),
                "title": t("rec_dmarc_title", domain=d['domain']),
                "detail": t.rec_dmarc_detail,
                "effort": t.rec_effort_low,
                "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/office-365-security/email-authentication-dmarc-configure",
            })
            # No break: one finding per offending domain. The domain is a rec_id
            # identity param, so a break hid every domain after the first — a
            # multi-domain tenant saw only one of its DMARC gaps (accuracy sweep).

    for d in spf_dmarc:
        if not _is_audit_relevant_domain(d.get("domain", "")):
            continue
        if "MISSING" in d.get("spf", "") or "CRITICAL" in d.get("spf", "") or "WEAK" in d.get("spf", ""):
            recs.append({
                "priority": "high",
                "finding_id": "finding-email",
                "evidence": ev("26_email_dns_spf_dmarc.txt"),
                "title": t("rec_spf_title", domain=d['domain']),
                "detail": t.rec_spf_detail,
                "effort": t.rec_effort_low,
                "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/office-365-security/email-authentication-spf-configure",
            })
            # No break: one finding per offending domain (see the DMARC loop). A
            # WEAK SPF (~all softfail) now also triggers the rec, matching the
            # grade, which already penalised it while raising no recommendation.

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
            "evidence": ev("28b_exchange_external_forwarding_WARN.txt", "28_exchange_mailbox_forwarding.txt"),
            "finding_id": "finding-fwd",
            "title": t("rec_ext_fwd_title", count=fwd_count),
            "detail": t.rec_ext_fwd_detail,
            "effort": t.rec_effort_immediate,
            "sub_items": fwd_items,
            "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/office-365-security/outbound-spam-policies-external-email-forwarding",
        })

    if risky_users and "No risky" not in risky_users and not _evidence_unavailable(risky_users):
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
                # Only users currently at risk belong in a "risky users" finding.
                # An account that was remediated or the alert dismissed is no
                # longer a live risk; listing it told the customer to investigate
                # something already handled (accuracy sweep).
                if state.lower().replace(" ", "") in (
                        "remediated", "dismissed", "confirmedsafe", "safe"):
                    continue
                risky_items.append(t("rec_risky_user_line", upn=upn, level=level, state=state))
        # Only emit the recommendation if we actually parsed at least one risky
        # user. The file may contain a header but no rows (e.g. when the audit
        # ran but no users currently match) — surfacing an empty "Risky users
        # detected" rec with no count/list would be a misleading false positive.
        if risky_items:
            title_suffix = t("rec_risky_users_suffix", count=len(risky_items))
            recs.append({
                "priority": "high",
                "evidence": ev("18_risky_users.txt", "18d_risk_detections.txt"),
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
            "evidence": ev("09_secure_score.txt"),
            "finding_id": "finding-securescore",
            "title": t("rec_secure_score_title", pct=secure_score['pct'], count=len(improvements)),
            "detail": t("rec_secure_score_detail", pct=secure_score['pct'],
                        current=secure_score.get('current', 0), max=secure_score.get('max', 0)),
            "effort": t.rec_effort_medium,
            "sub_items": [f"{imp['name']} ({imp.get('category', '')})" for imp in improvements],
            "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/defender/microsoft-secure-score",
        })

    # Licence utilisation ("near capacity") is a commercial note, not a security
    # finding. Injected here it used to outrank real security recs (SharePoint
    # external sharing) as a "medium". It is already surfaced by the licences
    # table's "near limit" badge and the License Optimization section, so it is
    # intentionally NOT added to the security recommendations.

    # Admin roles
    if admin_roles and admin_roles.get("global_admin_count", 0) > 4:
        recs.append({
            "priority": "high",
            "evidence": ev("07_admin_roles.txt"),
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
            "evidence": ev("10_intune_devices_count.txt", "10_intune_devices.txt"),
            "finding_id": "finding-intune",
            "title": t("rec_intune_title", count=intune['noncompliant']),
            "detail": t("rec_intune_detail", pct=intune.get('compliance_pct', 0)),
            "effort": t.rec_effort_medium,
            "doc_url": "https://learn.microsoft.com/en-us/mem/intune/protect/device-compliance-get-started",
        })

    # Entra-registered endpoints Intune does not manage. Raised on its own,
    # independent of the compliance % (which only speaks to *enrolled* devices):
    # a tenant with some enrolled devices still has unmanaged endpoints, and that
    # gap was previously surfaced only when there were NO Intune devices at all
    # (M365 review, F10b).
    if intune and intune.get("entra_unmanaged", 0) > 0 and intune.get("entra_total", 0) > 0:
        entra_unmanaged = intune["entra_unmanaged"]
        entra_total = intune["entra_total"]
        prio = "high" if entra_unmanaged / entra_total >= 0.5 else "medium"
        recs.append({
            "priority": prio,
            "evidence": ev("15_entra_devices_count.txt", "10_intune_devices_count.txt"),
            "finding_id": "finding-entra-unmanaged",
            "title": t("rec_entra_unmanaged_title", count=entra_unmanaged),
            "detail": t("rec_entra_unmanaged_detail", unmanaged=entra_unmanaged, total=entra_total),
            "effort": t.rec_effort_medium,
            "doc_url": "https://learn.microsoft.com/en-us/mem/intune/enrollment/device-enrollment",
        })

    # Lockout cross-check: a user's registered methods may all be disabled in the
    # authentication-methods policy, so enforcing MFA would lock them out. The
    # report never compared the two files (M365 review, F5).
    auth_policy_text = (file_contents or {}).get("09b_auth_methods_policy.txt", "")
    if auth_policy_text and mfa.get("users"):
        locked_out = _auth_method_lockout_users(mfa, auth_policy_text)
        if locked_out:
            recs.append({
                "priority": "high",
                "evidence": ev("09b_auth_methods_policy.txt", "04_mfa_methods.txt"),
                "finding_id": "finding-auth-method-lockout",
                "title": t("rec_auth_lockout_title", count=len(locked_out)),
                "detail": t.rec_auth_lockout_detail,
                "effort": t.rec_effort_medium,
                "sub_items": locked_out[:50],
                "doc_url": "https://learn.microsoft.com/en-us/entra/identity/authentication/concept-authentication-methods-manage",
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
            "evidence": ev("15b_sharepoint_settings.txt"),
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
            "finding_id": "finding-sp-legacy",
            "evidence": ev("15b_sharepoint_settings.txt"),
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
            "evidence": ev("17b_oauth_consent_grants.txt", "17_app_registrations.txt"),
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
            "finding_id": "finding-nsg",
            "evidence": sorted(nsg_warns),
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
        # The collector's summary line reads "N enabled account(s) with licenses
        # have not signed in for …". The old patterns ("N licensed … stale",
        # "N stale") matched neither the summary line nor the banner, so the count
        # was always 0 and this finding never fired (accuracy sweep).
        m = _re.search(r'(\d+)\s+enabled account\(s\) with licenses', stale_warn, _re.IGNORECASE)
        if not m:
            m = _re.search(r'(\d+)\s+licensed.*stale', stale_warn, _re.IGNORECASE)
        if not m:
            m = _re.search(r'(\d+)\s+stale', stale_warn, _re.IGNORECASE)
        count = int(m.group(1)) if m else 0
        if count > 0:
            recs.append({
                "priority": "medium",
                "finding_id": "finding-stale",
                "evidence": ev("03c_stale_accounts_WARN.txt", "03b_stale_accounts.txt"),
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
                "finding_id": "finding-cred-expiry",
                "evidence": ev("17c_app_credential_expiry_WARN.txt", "17c_app_credential_expiry.txt"),
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
            "finding_id": "finding-brute-force",
            "evidence": ev("05b_signin_failures.txt", "05_signin_activity.txt"),
            "title": t("rec_brute_force_title", count=len(suspects)),
            "detail": t.rec_brute_force_detail,
            "effort": t.rec_effort_immediate,
            "sub_items": suspects,
        })

    # Sign-in risk — probable stale/cached credentials (not an attack). Many
    # failures interleaved with successful sign-ins mean a device retrying an old
    # password; reported at low severity so it does not read as an attack.
    if signin_risk and signin_risk.get("stale_credential_users"):
        stale = signin_risk["stale_credential_users"]
        recs.append({
            "priority": "low",
            "finding_id": "finding-stale-credential",
            "evidence": ev("05_signin_activity.txt", "05b_signin_failures.txt"),
            "title": t("rec_stale_cred_title", count=len(stale)),
            "detail": t.rec_stale_cred_detail,
            "effort": t.rec_effort_low,
            "sub_items": stale,
        })

    # ── Network recommendations (FortiGate + UniFi) ─────────────────────
    # A file that would not parse leaves this section silent, and silence here
    # reads as "nothing found on the network" — the opposite of what happened.
    # Say it in the report, not only in the log the customer never sees.
    for _unreadable in (network or {}).get("unreadable", []):
        recs.append({
            "priority": "high",
            "title": t("rec_network_audit_unreadable_title", file=_unreadable),
            "detail": t.rec_network_audit_unreadable_detail,
            "effort": t.rec_effort_immediate,
            # The file that would not parse is both the provenance and the
            # whole finding, so naming it is not a formality here.
            "evidence": [_unreadable],
        })

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

    return _label_recommendations(recs)


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

    # A UniFi section that could not be read is not a measurement. It carries
    # device_count=None (rather than the old implicit 0), so treating it as a
    # real section would both sum None into an int below and read a refused
    # controller as "0 devices" in the trend. Drop it to None — the same as a
    # customer with no UniFi at all — so the metrics record "unknown", not zero.
    if unifi and (unifi.get("unavailable") or "error" in unifi):
        unifi = None

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
        # The rendered text *and* the recipe for it. The text keeps every
        # existing reader working; the recipe lets a reader in the other
        # language have the sentence rebuilt without re-running the audit.
        "recommendations": [
            {
                "rec_id": r.get("rec_id", ""),
                "priority": r.get("priority", ""),
                "title": str(r.get("title", "")),
                "detail": str(r.get("detail", "")),
                "effort": str(r.get("effort", "")),
                "title_key": r.get("title_key", ""),
                "title_params": r.get("title_params", {}),
                "detail_key": r.get("detail_key", ""),
                "detail_params": r.get("detail_params", {}),
            }
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


# Params that name *which* thing a recommendation is about, as opposed to how
# much of it there is. "fonnafly.com" identifies a finding; "3 mailboxes" is how
# big it is this week. Only the former may enter the id, or marking an item done
# would come undone the moment the count moved.
_REC_IDENTITY_PARAMS = ("domain", "part", "category", "sku", "name")


def _label_recommendations(recs: list[dict]) -> list[dict]:
    """Give each recommendation a stable id and the recipe for its own text.

    The id is language-independent so remediation state survives a language
    change — it used to be keyed on the rendered title, which meant an operator
    who marked something done in Norwegian would find it open again in English.

    The key and params come off the Localised strings the builder already
    produced, so there is nothing to keep in step by hand.
    """
    from app.reports.i18n import Localised

    seen: dict[str, int] = {}
    for rec in recs:
        for field in ("title", "detail"):
            value = rec.get(field)
            if isinstance(value, Localised):
                rec[f"{field}_key"] = value.key
                rec[f"{field}_params"] = dict(value.params)

        base = rec.get("title_key") or rec.get("finding_id") or "rec"
        params = rec.get("title_params") or {}
        rec_id = ":".join(
            [base]
            + [str(params[k]) for k in _REC_IDENTITY_PARAMS if params.get(k) not in (None, "")]
        )
        # Two recommendations from one key with nothing to tell them apart is a
        # bug in the builder, but a silently shared id would merge their
        # remediation state, so they are separated and the collision logged.
        seen[rec_id] = seen.get(rec_id, 0) + 1
        if seen[rec_id] > 1:
            log.warning("Recommendation id %r is not unique - disambiguating", rec_id)
            rec_id = f"{rec_id}#{seen[rec_id]}"
        rec["rec_id"] = rec_id
    return recs


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
    "1.1.7": {"nist_id": "PR.AA-3", "nist_name": "Users, services, and hardware are authenticated",
              "iso_id": "A.8.5",  "iso_name": "Secure authentication"},
    "1.1.8": {"nist_id": "PR.AA-5", "nist_name": "Access permissions are managed",
              "iso_id": "A.5.18", "iso_name": "Access rights"},
    "1.1.9": {"nist_id": "PR.AA-5", "nist_name": "Access permissions are managed",
              "iso_id": "A.5.14", "iso_name": "Information transfer"},
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
    "7.2.4": {"nist_id": "PR.DS-5", "nist_name": "Protections against data leaks are implemented",
              "iso_id": "A.5.14", "iso_name": "Information transfer"},
    "7.2.2": {"nist_id": "PR.DS-5", "nist_name": "Protections against data leaks are implemented",
              "iso_id": "A.8.12", "iso_name": "Data leakage prevention"},
    "7.2.3": {"nist_id": "PR.AA-3", "nist_name": "Users, services, and hardware are authenticated",
              "iso_id": "A.8.5",  "iso_name": "Secure authentication"},
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


def _evidence_unavailable(text: str) -> bool:
    """True when a collector file explains an absence rather than reporting one.

    Collectors write two shapes of non-reading: an ``Error:`` stub, and a
    "(not available)" block naming a licence or permission gap. Both are prose
    about why nothing was measured, and neither is evidence of anything about
    the tenant. This was checked in three places with three slightly different
    substring tests, and not at all in the fourth.
    """
    if not isinstance(text, str):
        return True
    stripped = text.strip()
    if not stripped or stripped.startswith("Error:"):
        return True
    # Only in the head. Every collector writes these markers in the title line
    # or the cause block right under it — the longest is five lines. Searching
    # the whole file instead meant one genuine finding whose text happened to
    # say "requires" made the entire file read as unmeasured, which silently
    # drops its penalty. A miss here is worse than a stub read as data: the
    # stub costs points, the miss hides a real finding.
    head = "\n".join(stripped.splitlines()[:12]).lower()
    return "not available" in head or "requires" in head or "krever" in head


_HEADER_COUNT = re.compile(r"\((\d+)\s+(?:total|unresolved|found)\)")


def _reported_count(text: str) -> int | None:
    """How many rows the collector says it wrote, taken from its own header.

    Both files that feed a critical-finding penalty carry it: "RISKY USERS
    (0 total)", "DEFENDER ACTIVE ALERTS  (3 unresolved)". None means the text
    has no such header and the caller must fall back.

    Counting rendered lines instead charged a tenant for its title and column
    header. Worse, the sentinels the score actually branched on — "No risky",
    "No active" — are phrases no collector writes. They exist only in the test
    fixture, so a clean tenant was charged five points for having no risky
    users and five more for having no Defender alerts, and one real alert
    scored one point worse than none. The fixture was written to match the
    parser rather than the collector, which is why nothing failed.
    """
    m = _HEADER_COUNT.search(text or "")
    return int(m.group(1)) if m else None


def _section_ran(fc: dict, *names: str) -> bool:
    """True when at least one of the named collector outputs is usable.

    A file that is absent, empty, an "Error:" stub or a "(not available)"
    explanation means the section produced no reading. Zero policies in a file
    that *was* written is a reading — and a completely different claim.
    Compliance controls kept conflating the two, so a tenant whose Exchange
    section never ran was attested as having no external forwarding and failed
    for having no anti-spam policy, on identical evidence: nothing.
    """
    return any(not _evidence_unavailable(fc.get(name, "")) for name in names)


_CANNOT_VERIFY = "Kan ikke verifiseres — "

# Which collected files each CIS verdict is formed from.
#
# The technical report already carries every file the audit produced, so the
# evidence is in the reader's hands — but nothing says which of the seventy-two
# backs a given control, and finding out meant reading the code. A verdict a
# technician cannot trace to its source is a verdict they have to take on
# faith, which is the opposite of what this report is for.
#
# Each entry was read off the block that produces the control, not inferred:
# the parsed inputs (mfa, ca, admin_roles, secure_score, oauth, sharepoint,
# spf_dmarc, intune) come from the files named where build_report_context calls
# the parsers, and the rest read fc directly.
#
# 5.1.1 is the one worth a note: it reads SharePoint's legacy-auth protocol
# flag, not Entra's. A tenant can block legacy auth with a Conditional Access
# policy and still fail this, or the reverse. The file named here is the one
# the verdict actually comes from, whatever the title suggests.
_EVIDENCE_MAP: dict[str, tuple[str, ...]] = {
    # The JSON sidecar first: it is what _mfa_user_records actually reads, and
    # leaving it undeclared meant removing every file this control named still
    # left the verdict standing on the one file nobody had listed. A technician
    # tracing an MFA pass was shown the fixed-width table the reader falls back
    # to, not the source of the number.
    "1.1.1": ("04_mfa_methods.json", "04_mfa_methods.txt", "04b_mfa_ca_analysis.txt"),
    "1.1.2": ("09b_auth_methods_policy.txt",),
    "1.1.3": ("07_admin_roles.txt",),
    "1.1.4": ("08_conditional_access.txt",),
    "1.1.5": ("07b_pim_eligible_assignments.txt", "32_pim_roles.txt"),
    "1.1.6": ("07c_emergency_access_check.txt",),
    "1.1.7": ("31b_smart_lockout.txt", "08_conditional_access.txt"),
    "1.1.8": ("07d_access_reviews.txt",),
    "1.1.9": ("18c_cross_tenant_access_policy.txt",),
    "1.2.1": ("31_password_protection.txt",),
    "1.4":   ("09_secure_score.txt",),
    "2.1":   ("17b_oauth_consent_grants.txt", "17_app_registrations.txt"),
    # 17_app_registrations.txt is not incidental here: it is what separates
    # "no expired credentials" from "the section never ran", so the verdict is
    # formed from it as much as from the expiry files.
    "2.1.2": ("17_app_registrations.txt",
              "17c_app_credential_expiry.txt", "17c_app_credential_expiry_WARN.txt"),
    "3.1.1": ("19d_purview_dlp_policies.txt",),
    "3.2.1": ("19c_purview_sensitivity_labels.txt",),
    "4.1":   ("27c_exchange_org_config.txt",),
    "4.2":   ("23_exchange_antiphish.txt",),
    "4.3":   ("24_exchange_antispam.txt",),
    # The two WARN files carry the finding; the two plain files are what say
    # the scan ran at all, and the "pass" branch is formed from those. Listing
    # only three of the four meant a technician tracing a pass was shown every
    # file except the one that produced it.
    "4.4":   ("28_exchange_mailbox_forwarding.txt",
              "28b_exchange_external_forwarding_WARN.txt",
              "29_exchange_inbox_rules_external_fwd.txt",
              "29_exchange_inbox_rules_external_fwd_WARN.txt"),
    "4.5":   ("27_exchange_defender_policies.txt",),
    "4.6":   ("27_exchange_defender_policies.txt",),
    "5.1.1": ("08_conditional_access.txt",),
    "5.2.1": ("26_email_dns_spf_dmarc.txt",),
    "5.2.2": ("26_email_dns_spf_dmarc.txt",),
    "5.2.3": ("26_email_dns_spf_dmarc.txt",),
    "6.1.1": ("11_intune_compliance_policies.txt", "10_intune_devices_count.txt"),
    "7.2.1": ("15b_sharepoint_settings.txt",),
    "7.2.2": ("19e_purview_retention_policies.txt",),
    "7.2.3": ("15b_sharepoint_settings.txt",),
    "7.2.4": ("25_onedrive_sharing.txt",),
    "8.1.1": ("16c_teams_external_access.txt",),
    "8.1.2": ("30b_teams_guest_access.txt",),
    "9.1":   ("27d_exchange_admin_audit_log_config.txt",),
    "9.2":   ("19b_defender_active_alerts.txt", "19b_defender_alert_count.txt"),
    "9.3":   ("18_risky_users.txt",),
}


def _labelled_value(text: str, label: str) -> str:
    """Pull "  Label   : value" out of a section file.

    Returns "" when the label is absent or the value is a placeholder, so an
    unanswered field reads as no data rather than as the string "N/A".
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(label):
            continue
        rest = stripped[len(label):].lstrip()
        if not rest.startswith(":"):
            continue
        value = rest[1:].strip()
        return "" if value.upper() in ("N/A", "NA", "-", "") else value
    return ""


def _labelled_int(text: str, label: str) -> int | None:
    """Return a labelled count, preserving absent as distinct from zero."""
    value = _labelled_value(text, label)
    try:
        return int(value.replace(",", "").split()[0])
    except (ValueError, IndexError):
        return None


_NOT_LICENSED = "Ikke lisensiert — "

# Which SKU part numbers carry which capability. Only the ones a CIS control
# actually gates on; this is not meant to be a complete Microsoft catalogue,
# and an unknown SKU deliberately yields "unknown" rather than "absent".
#
# O365_BUSINESS_PREMIUM is Microsoft 365 Business *Standard*, not Premium —
# Microsoft's part number predates the rename. Business Premium is SPB, and
# it is the one that carries Entra ID P1, Intune and Defender for Office P1.
# Getting that pair backwards turns a licence gap into a config finding.
_SKU_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "AAD_PREMIUM":        ("entra_p1",),
    "AAD_PREMIUM_P2":     ("entra_p1", "entra_p2"),
    "EMS":                ("entra_p1", "intune"),
    "EMSPREMIUM":         ("entra_p1", "entra_p2", "intune"),
    "SPB":                ("entra_p1", "intune", "defender_office"),
    "SPE_E3":             ("entra_p1", "intune"),
    "SPE_E5":             ("entra_p1", "entra_p2", "intune", "defender_office", "purview"),
    "ENTERPRISEPREMIUM":  ("entra_p1", "entra_p2", "intune", "defender_office", "purview"),
    "INTUNE_A":           ("intune",),
    "ATP_ENTERPRISE":     ("defender_office",),
    "THREAT_INTELLIGENCE": ("defender_office",),
    "INFORMATION_PROTECTION_COMPLIANCE": ("purview",),
}


def _licensed_capabilities(licenses: list[dict] | None) -> set[str] | None:
    """Capabilities assigned to at least one user, or None if unknown.

    Ownership is not entitlement in practice: this tenant holds one
    AAD_PREMIUM_P2 with zero seats assigned, which grants nobody anything.
    Counting it as present would let a P2-gated control be scored as a
    configuration failure the customer could act on, when the honest finding
    is that the licence needs assigning first.

    None when the licence section produced nothing. An empty inventory and an
    uncollected one are not the same claim, and callers must not read "no
    licence data" as "no licence" — that is the absence-as-finding mistake this
    whole pass exists to remove, and it is easy to make right here.
    """
    if not licenses:
        return None
    capabilities: set[str] = set()
    for lic in licenses:
        if lic.get("used", 0) <= 0:
            continue
        for capability in _SKU_CAPABILITIES.get(lic.get("part", ""), ()):
            capabilities.add(capability)
    return capabilities


def _lacks(capabilities: set[str] | None, capability: str) -> bool:
    """True only when the licence inventory was read and lacks *capability*."""
    return capabilities is not None and capability not in capabilities


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

    # What the tenant can actually do. A control gated on a licence nobody
    # holds is a purchasing decision, not a misconfiguration, and scoring it as
    # a deviation puts work on the customer's list that they cannot do.
    capabilities = _licensed_capabilities(context.get("licenses") or [])

    # Helper — includes human-readable framework names
    def add(cis_id, title, category, status, detail=""):
        entry = {"cis_id": cis_id, "title": title, "category": category, "status": status, "detail": detail}
        # Only name files this run actually collected. Pointing a reader at a
        # file that is not in the report is worse than pointing at nothing.
        entry["evidence"] = [f for f in _EVIDENCE_MAP.get(cis_id, ()) if fc.get(f, "").strip()]
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
    # Match any "Error…" prefix, not just the "Error:" convention. The section now
    # emits the standard "Error:" sentinel on a throttled or permission-denied
    # read, but it historically wrote "Error fetching …" (no colon) which slipped
    # this guard and scored a real WARN over unverifiable data; the broadened
    # match is belt-and-suspenders against any error phrasing (accuracy sweep).
    if not auth_methods_text.strip() or auth_methods_text.lstrip().startswith("Error"):
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
            # ga == 0 with role data present — e.g. a PIM/JIT tenant whose Global
            # Admins are all eligible (no standing GA). Without this branch the
            # control emitted no verdict at all and silently vanished from the
            # report (accuracy sweep). Report it as unverifiable, not omitted.
            add("1.1.3", "Ensure fewer than 5 Global Admins", t.cis_cat_identity, "info",
                "Ingen faste Global Admin-tildelinger funnet — verifiser PIM/JIT-oppsett")
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
    elif _lacks(capabilities, "entra_p2"):
        # PIM is an Entra ID P2 feature. Without an assigned P2 seat there is
        # nothing to configure, so "no assignments found" describes the licence
        # rather than the tenant's hygiene.
        add("1.1.5", "Ensure PIM is used for privileged role activation", t.cis_cat_identity, "info",
            _NOT_LICENSED + "PIM krever Entra ID P2, som ikke er tildelt noen bruker")
    else:
        add("1.1.5", "Ensure PIM is used for privileged role activation", t.cis_cat_identity, "warn",
            "Ingen PIM-tildelinger funnet — roller kan være permanent tildelt")

    # 1.1.6 Emergency access accounts. The break-glass file lists EVERY Global
    # Admin, not just dedicated emergency-access accounts, so "any row with a
    # UPN → break-glass account detected" is wrong: once the rows carried GUIDs
    # (no '@') it under-counted to 0 and always warned; once the section started
    # printing UPNs it over-counted every admin and flipped to a false PASS
    # ("N break-glass accounts") on a tenant that has none (M365 review follow-up).
    # A real break-glass account is a cloud admin *intentionally excluded from
    # Conditional Access* so it still works during an MFA/CA outage — that is the
    # only reliable signal here. Read the section's machine-readable summary
    # instead of scraping rows, and fail closed when the exclusion data was not
    # collected rather than guessing a clean answer.
    emerg_text = fc.get("07c_emergency_access_check.txt", "")
    emerg_skipped = "skipping check" in emerg_text.lower()
    bg_summary = re.search(
        r"break_glass_candidates=(\d+)\s+ca_exclusions_known=(yes|no)", emerg_text
    )
    # Separate, optional: how many admins are CA-excluded at all. Lets the
    # zero-candidate case distinguish "an admin is excluded but does not qualify
    # as break-glass (it is in active use)" from "no admin is excluded". Absent
    # on older evidence, in which case the generic wording is used.
    bg_excluded = re.search(r"ca_excluded_admins=(\d+)", emerg_text)
    if (not emerg_text.strip() or emerg_text.strip().startswith("Error:")
            or emerg_skipped or bg_summary is None):
        # No summary line means either the check was skipped or the file predates
        # this format — in both cases we cannot verify, so do not assert a verdict.
        add("1.1.6", "Ensure emergency access accounts are configured", t.cis_cat_identity, "info",
            _CANNOT_VERIFY + "break-glass-sjekken ble hoppet over eller mangler oppsummering")
    elif bg_summary.group(2) != "yes":
        add("1.1.6", "Ensure emergency access accounts are configured", t.cis_cat_identity, "info",
            _CANNOT_VERIFY + "CA-unntak ble ikke samlet inn — kan ikke bekrefte nødtilgangskontoer")
    elif int(bg_summary.group(1)) > 0:
        add("1.1.6", "Ensure emergency access accounts are configured", t.cis_cat_identity, "pass",
            f"{int(bg_summary.group(1))} nødtilgangskonto(er) (break glass) oppdaget")
    elif bg_excluded is not None and int(bg_excluded.group(1)) > 0:
        add("1.1.6", "Ensure emergency access accounts are configured", t.cis_cat_identity, "warn",
            "Adminkonto(er) er unntatt fra Conditional Access, men ingen fungerer som en gyldig "
            "nødtilgangskonto (kontoen(e) er i aktiv bruk)")
    else:
        add("1.1.6", "Ensure emergency access accounts are configured", t.cis_cat_identity, "warn",
            "Ingen administrator er unntatt fra Conditional Access, og ingen dedikert "
            "nødtilgangskonto er konfigurert")

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
    elif "were not measured" in pwd_text.lower():
        # The section could not read the directory settings and says so verbatim
        # ("…settings were not measured. This is not a finding about the tenant").
        # Honour that: an unreadable fetch is cannot-verify, not a Critical FAIL
        # manufactured from absent evidence (accuracy sweep).
        add("1.2.1", "Ensure custom banned passwords are configured", t.cis_cat_identity, "info",
            _CANNOT_VERIFY + "katalog-innstillinger kunne ikke leses")
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
        elif _lacks(capabilities, "entra_p1"):
            # The collector already writes "requires Entra ID P1+" into its own
            # output. Scoring it as a failure anyway put a Critical item on the
            # customer's list that no amount of configuration would clear.
            add("1.2.1", "Ensure custom banned passwords are configured", t.cis_cat_identity, "info",
                _NOT_LICENSED + "egendefinert passordliste krever Entra ID P1, "
                                "som ikke er tildelt noen bruker")
        else:
            add("1.2.1", "Ensure custom banned passwords are configured", t.cis_cat_identity, "fail",
                "Kun Microsofts standardliste — ingen egendefinerte forbudte passord")

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
    # Gate on the parsed count, not on `dlp_text.strip()`. The collector writes
    # an empty section as a "(none)" _section_block, which is non-empty text —
    # so the old `elif dlp_text.strip()` graded a tenant with zero DLP policies
    # "partial: policies exist", contradicting the card that (correctly) shows 0.
    # Zero policies on a section that ran is a warn; the control asks whether DLP
    # is configured, and it is not.
    if dlp_count > 0 or ("enabled" in dlp_text.lower() and "enforce" in dlp_text.lower()):
        add("3.1.1", "Ensure DLP policies are configured", t.cis_cat_data, "pass",
            f"{dlp_count} DLP-policyer konfigurert" if dlp_count else "DLP-policyer funnet")
    elif _section_ran(fc, "19d_purview_dlp_policies.txt"):
        add("3.1.1", "Ensure DLP policies are configured", t.cis_cat_data, "warn",
            "Ingen DLP-policyer funnet")
    else:
        add("3.1.1", "Ensure DLP policies are configured", t.cis_cat_data, "info",
            _CANNOT_VERIFY + "Purview DLP-data utilgjengelig")

    # 3.2.1 Sensitivity labels
    # Gate the pass on the parsed COUNT only. The old fallback also passed when
    # the raw text merely contained the word "label" — but the file is titled
    # "PURVIEW SENSITIVITY LABELS" with a "Label Name" column, so that substring
    # is present even at zero labels, and the control passed on empty evidence.
    # A tenant with no published labels now correctly lands in the warn branch.
    _labels_raw = purview.get("sensitivity_labels", 0) if purview else 0
    labels = len(_labels_raw) if isinstance(_labels_raw, list) else (_labels_raw if isinstance(_labels_raw, int) else 0)
    if labels > 0:
        add("3.2.1", "Ensure sensitivity labels are published", t.cis_cat_data, "pass",
            f"{labels} sensitivitetsetiketter publisert")
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
            # The evidence writer renders the bool via _fmt_val → "Yes"/"No", not
            # "true"/"false"; matching only true/false made this control inert and
            # fail-open — an audit-disabled tenant scored "info" (dropped from the
            # denominator) instead of "fail" (accuracy sweep). Accept both shapes.
            if val in ("true", "false", "yes", "no"):
                audit_disabled_val = val in ("true", "yes")
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

    # 4.2 Anti-phishing. Three states, not two. _section_ran only says a
    # reading exists; it does not say the tenant has any policies. A file
    # reading "(0 entries)" over "(none)" is a real reading of an unprotected
    # tenant, and grading it "pass" attested to protection that is not there.
    if _section_ran(fc, "23_exchange_antiphish.txt"):
        _antiphish_n = _count_data_lines(fc.get("23_exchange_antiphish.txt", ""))
        if _antiphish_n > 0:
            add("4.2", "Ensure anti-phishing policies are configured", t.cis_cat_email, "pass",
                f"{_antiphish_n} anti-phishing-policy(er) konfigurert")
        else:
            add("4.2", "Ensure anti-phishing policies are configured", t.cis_cat_email, "fail",
                "Ingen anti-phishing-policyer konfigurert")
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
        _antispam_n = _count_data_lines(fc.get("24_exchange_antispam.txt", ""))
        if _antispam_n > 0:
            add("4.3", "Ensure anti-spam policies are configured", t.cis_cat_email, "pass",
                f"{_antispam_n} anti-spam-policy(er) konfigurert")
        else:
            add("4.3", "Ensure anti-spam policies are configured", t.cis_cat_email, "fail",
                "Ingen anti-spam-policyer konfigurert")
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
    elif _lacks(capabilities, "defender_office"):
        # Defender for Office is not in this tenant's SKUs, so the
        # absence of policies is the licence, not the configuration.
        add("4.5", "Ensure Safe Links is enabled", t.cis_cat_email, "info",
            _NOT_LICENSED + "Safe Links krever Defender for Office 365 Plan 1")
    elif _section_ran(fc, "27_exchange_defender_policies.txt"):
        add("4.5", "Ensure Safe Links is enabled", t.cis_cat_email, "warn",
            "Ingen Safe Links-policyer funnet")
    else:
        add("4.5", "Ensure Safe Links is enabled", t.cis_cat_email, "info",
            _CANNOT_VERIFY + "Defender-policydata utilgjengelig")

    if safe_attach_enabled > 0:
        add("4.6", "Ensure Safe Attachments is enabled", t.cis_cat_email, "pass",
            f"{safe_attach_enabled} aktiv(e) Safe Attachments-policy(er)")
    elif "safeattach" in defender.lower() or "safe attach" in defender.lower():
        add("4.6", "Ensure Safe Attachments is enabled", t.cis_cat_email, "fail",
            "Safe Attachments-policy(er) finnes men er deaktivert")
    elif _lacks(capabilities, "defender_office"):
        # Defender for Office is not in this tenant's SKUs, so the
        # absence of policies is the licence, not the configuration.
        add("4.6", "Ensure Safe Attachments is enabled", t.cis_cat_email, "info",
            _NOT_LICENSED + "Safe Attachments krever Defender for Office 365 Plan 1")
    elif _section_ran(fc, "27_exchange_defender_policies.txt"):
        add("4.6", "Ensure Safe Attachments is enabled", t.cis_cat_email, "warn",
            "Ingen Safe Attachments-policyer funnet")
    else:
        add("4.6", "Ensure Safe Attachments is enabled", t.cis_cat_email, "info",
            _CANNOT_VERIFY + "Defender-policydata utilgjengelig")

    # ═══ 5. EMAIL AUTHENTICATION ═══

    # 5.1.1 Legacy authentication blocked in Entra.
    #
    # This used to read SharePoint's legacy-auth protocol flag. The two are
    # different settings on different services: a tenant can block legacy
    # authentication tenant-wide with a Conditional Access policy and still
    # have SharePoint's own protocols enabled, or the reverse. So the control
    # attested to something it had not measured, and nothing anywhere checked
    # the Entra side — the single highest-value hardening step in a tenant.
    #
    # The verdict comes from the policy's client-app scope and grant control,
    # never its display name. SharePoint's flag is now its own control below.
    if not ca.get("has_data"):
        add("5.1.1", "Ensure legacy authentication is blocked", t.cis_cat_identity, "info",
            _CANNOT_VERIFY + "Conditional Access-data utilgjengelig")
    elif not ca.get("has_client_app_data"):
        # An audit taken before the client-app scope was collected. Reading
        # that absence as a failure would fail every tenant on old output.
        add("5.1.1", "Ensure legacy authentication is blocked", t.cis_cat_identity, "info",
            _CANNOT_VERIFY + "auditen er kjørt før klientapp-omfang ble samlet inn — "
            "kjør en ny audit")
    elif ca.get("blocks_legacy_auth"):
        add("5.1.1", "Ensure legacy authentication is blocked", t.cis_cat_identity, "pass",
            "En aktivert CA-policy blokkerer eldre klienter (exchangeActiveSync, other)")
    else:
        add("5.1.1", "Ensure legacy authentication is blocked", t.cis_cat_identity, "fail",
            "Ingen aktivert CA-policy blokkerer eldre autentisering")

    # 1.1.7 Security Defaults. Collected since the section was written and
    # never graded: 31b_smart_lockout.txt records whether they are on, and a
    # tenant with neither Security Defaults nor a Conditional Access policy has
    # no baseline sign-in protection at all. Disabling them is correct once CA
    # is in place, which is why the CA count is part of the verdict rather than
    # this flag alone.
    lockout_text = fc.get("31b_smart_lockout.txt", "")
    sd_raw = ""
    for line in lockout_text.splitlines():
        if "security defaults" in line.lower() and ":" in line:
            sd_raw = line.split(":", 1)[1].strip().lower()
            break
    if sd_raw not in ("true", "false"):
        add("1.1.7", "Ensure baseline sign-in protection is in place", t.cis_cat_identity,
            "info", _CANNOT_VERIFY + "Security Defaults-status utilgjengelig")
    elif sd_raw == "true":
        add("1.1.7", "Ensure baseline sign-in protection is in place", t.cis_cat_identity,
            "pass", "Security Defaults er aktivert")
    elif not ca.get("has_data"):
        # Security Defaults are off, and whether that is fine depends entirely
        # on the Conditional Access side. Without it there is no verdict to
        # give: calling it a failure would manufacture a finding out of a
        # missing file, which is what the partial-audit test caught here.
        add("1.1.7", "Ensure baseline sign-in protection is in place", t.cis_cat_identity,
            "info", _CANNOT_VERIFY + "Security Defaults er av, men CA-data er utilgjengelig")
    elif ca.get("enabled", 0) > 0:
        add("1.1.7", "Ensure baseline sign-in protection is in place", t.cis_cat_identity,
            "pass", f"Security Defaults er av, men {ca.get('enabled')} CA-policyer er aktive")
    else:
        add("1.1.7", "Ensure baseline sign-in protection is in place", t.cis_cat_identity,
            "fail", "Verken Security Defaults eller aktive CA-policyer")

    # 1.1.8 Access reviews. Also collected and never graded. Gated on P2:
    # without an assigned seat there is nothing to configure, so "none found"
    # describes the licence rather than the tenant.
    reviews_text = fc.get("07d_access_reviews.txt", "")
    reviews = _parse_banner_count(reviews_text)
    if not reviews_text.strip() or reviews_text.strip().startswith("Error:"):
        add("1.1.8", "Ensure access reviews are configured", t.cis_cat_identity, "info",
            _CANNOT_VERIFY + "data om tilgangsgjennomganger utilgjengelig")
    elif reviews:
        add("1.1.8", "Ensure access reviews are configured", t.cis_cat_identity, "pass",
            f"{reviews} tilgangsgjennomgang(er) definert")
    elif _lacks(capabilities, "entra_p2"):
        add("1.1.8", "Ensure access reviews are configured", t.cis_cat_identity, "info",
            _CANNOT_VERIFY + "tilgangsgjennomganger krever Entra ID P2, som ingen bruker har")
    else:
        add("1.1.8", "Ensure access reviews are configured", t.cis_cat_identity, "warn",
            "Ingen tilgangsgjennomganger definert")

    # 1.1.9 Cross-tenant access. Collected since the section was written and
    # only readable at all since the collector was pointed at the right
    # endpoint; both values had been "N/A" on every tenant before that.
    #
    # Inbound and outbound B2B collaboration being allowed is not a finding.
    # It is how most organisations work, and grading it as a failure would
    # tell a customer to break their own collaboration. Two things are worth
    # saying: B2B direct connect inbound lets external organisations into
    # Teams shared channels without a guest account, and a tenant still on
    # Microsoft's system default has never made a decision here at all.
    xt_text = fc.get("18c_cross_tenant_access_policy.txt", "")
    xt = {}
    for line in xt_text.splitlines():
        if ":" in line and not line.strip().startswith("="):
            k, v = line.split(":", 1)
            xt[k.strip().lower()] = v.strip().lower()
    dc_in = xt.get("b2b direct connect in", "")
    service_default = xt.get("system default", "")

    if not xt_text.strip() or xt_text.strip().startswith("Error:") or not dc_in:
        add("1.1.9", "Ensure cross-tenant access settings are reviewed", t.cis_cat_identity,
            "info", _CANNOT_VERIFY + "kryssleie-innstillinger utilgjengelig")
    elif dc_in == "allowed":
        add("1.1.9", "Ensure cross-tenant access settings are reviewed", t.cis_cat_identity,
            "warn", "B2B direct connect inn er tillatt — eksterne organisasjoner kan nå "
                    "delte Teams-kanaler uten gjestekonto")
    elif service_default == "true":
        add("1.1.9", "Ensure cross-tenant access settings are reviewed", t.cis_cat_identity,
            "warn", "Kjører Microsofts systemstandard — kryssleie-tilgang er aldri vurdert")
    else:
        add("1.1.9", "Ensure cross-tenant access settings are reviewed", t.cis_cat_identity,
            "pass", "Kryssleie-tilgang er konfigurert, og direct connect inn er ikke tillatt")

    # 7.2.4 Anonymous sharing links. 25_onedrive_sharing.txt counts them and
    # nothing read it. An "Anyone" link needs no sign-in, so one is a finding
    # regardless of how the tenant-level sharing capability is set.
    od_text = fc.get("25_onedrive_sharing.txt", "")
    anyone = _labelled_int(od_text, "'Anyone' links")
    # A zero is only as broad as the scan behind it. A find still fails however
    # partial the scan was, but absence passes only when discovery, drive roots,
    # nested folders and the request budget all completed without a gap.
    _od_refused = _labelled_int(od_text, "Drives refused") or 0
    _od_discovery_failures = _labelled_int(od_text, "Discovery failures") or 0
    _od_folder_failures = _labelled_int(od_text, "Folder failures") or 0
    _od_scope = _labelled_value(od_text, "Scan scope")
    _od_complete = (
        _od_scope.startswith("complete")
        and _od_refused == 0
        and _od_discovery_failures == 0
        and _od_folder_failures == 0
    )
    _od_scanned = _labelled_int(od_text, "Drives scanned") or 0
    if anyone is None:
        add("7.2.4", "Ensure anonymous sharing links are not in use", t.cis_cat_data, "info",
            _CANNOT_VERIFY + "OneDrive-delingsdata utilgjengelig")
    elif anyone == 0 and not _od_complete:
        gaps = []
        if _od_refused:
            gaps.append(f"{_od_refused} stasjon(er) kunne ikke leses")
        if _od_discovery_failures:
            gaps.append(f"{_od_discovery_failures} oppdagelseskall feilet")
        if _od_folder_failures:
            gaps.append(f"{_od_folder_failures} mappe(r) kunne ikke leses")
        if _od_scope and not _od_scope.startswith("complete"):
            gaps.append("søket nådde en grense før det var ferdig")
        add("7.2.4", "Ensure anonymous sharing links are not in use", t.cis_cat_data, "info",
            "Ingen anonyme delingslenker funnet i det som ble gjennomsøkt, men "
            + (" og ".join(gaps) or "omfanget av søket er ukjent")
            + " — fravær er ikke bekreftet for hele tenanten")
    elif anyone == 0:
        add("7.2.4", "Ensure anonymous sharing links are not in use", t.cis_cat_data, "pass",
            f"Ingen anonyme delingslenker funnet i {_od_scanned} stasjon(er)")
    else:
        add("7.2.4", "Ensure anonymous sharing links are not in use", t.cis_cat_data, "fail",
            f"{anyone} anonym(e) delingslenke(r) — tilgjengelig uten pålogging")

    # 7.2.3 SharePoint's own legacy protocols — what 5.1.1 used to measure
    # under the wrong name. The parser returns legacy_auth=True only when the
    # settings dict says so; if the audit never reached SharePoint admin
    # settings the field defaults to False and this would silently pass, so it
    # gates on has_data.
    if not sp.get("has_data"):
        add("7.2.3", "Ensure legacy authentication protocols are disabled in SharePoint",
            t.cis_cat_data, "info",
            _CANNOT_VERIFY + "SharePoint-tenant-innstillinger utilgjengelig")
    elif not sp.get("legacy_auth_known"):
        add("7.2.3", "Ensure legacy authentication protocols are disabled in SharePoint",
            t.cis_cat_data, "info",
            _CANNOT_VERIFY + "auditen er kjørt før dette feltet ble samlet inn — "
            "kjør en ny audit")
    elif sp.get("legacy_auth"):
        add("7.2.3", "Ensure legacy authentication protocols are disabled in SharePoint",
            t.cis_cat_data, "fail", t.cis_legacy_auth_enabled)
    else:
        add("7.2.3", "Ensure legacy authentication protocols are disabled in SharePoint",
            t.cis_cat_data, "pass", t.cis_legacy_auth_disabled)

    # 5.2.1/5.2.2/5.2.3 SPF, DMARC, DKIM per domain
    for d in spf:
        domain = d.get("domain", "")
        if not _is_audit_relevant_domain(domain):
            continue
        spf_s = d.get("spf", "")
        dmarc_s = d.get("dmarc", "")
        dkim_s = d.get("dkim", "")

        # A failed lookup is not an absent record. The DNS section is careful
        # to keep them apart — SERVFAIL and a DoH outage come back as
        # "ERROR (...)", never "MISSING" — and these two checks threw that
        # away by treating everything that was not a pass as a failure. The
        # result was "configure SPF" for a domain that may well have it,
        # repeated per domain. 5.2.3 below already guards against this; these
        # two were left behind when it was fixed.
        unresolved = spf_s.strip().upper().startswith("ERROR")

        # SPF
        if "OK" in spf_s:
            add("5.2.1", f"Ensure SPF is configured — {domain}", t.cis_cat_email, "pass", spf_s)
        elif unresolved:
            add("5.2.1", f"Ensure SPF is configured — {domain}", t.cis_cat_email, "info",
                _CANNOT_VERIFY + f"SPF-oppslaget feilet for {domain} — {spf_s}")
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
        elif dmarc_s.strip().upper().startswith("ERROR"):
            add("5.2.2", f"Ensure DMARC is configured — {domain}", t.cis_cat_email, "info",
                _CANNOT_VERIFY + f"DMARC-oppslaget feilet for {domain} — {dmarc_s}")
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
        # A DoH lookup failure comes back as "ERROR (...)" in the selector value,
        # exactly as SPF/DMARC above — grade it cannot-verify, not a FAIL. The
        # comment on 5.2.1/5.2.2 claims "5.2.3 below already guards against this";
        # it did not, so a transient DoH outage scored a false DKIM FAIL per
        # domain (accuracy sweep). Gate ONLY on the M365 selectors (dkim1): dkim2
        # is a best-effort probe of guessed third-party selector names, and a blip
        # on one of those must not suppress a definitive "M365 DKIM missing" FAIL
        # to cannot-verify (fix review). dkim2 still counts toward a PASS above
        # (a real third-party key), just not toward the error gate. Checked after
        # dkim_valid so a valid selector alongside an errored one still passes.
        dkim_errored = "error" in dkim1.lower()
        if dkim_valid:
            add("5.2.3", f"Ensure DKIM is enabled — {domain}", t.cis_cat_email, "pass", dkim_detail)
        elif dkim_errored:
            add("5.2.3", f"Ensure DKIM is enabled — {domain}", t.cis_cat_email, "info",
                _CANNOT_VERIFY + f"DKIM-oppslaget for M365-selektorene feilet for {domain} — {dkim1}")
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
    # _evidence_unavailable, not a startswith("Error:") of its own: a refusal
    # is also written as a "(not available)" block naming the permission, and
    # that block has prose in it. Counting its lines as policies would turn
    # "we were not allowed to look" into "policies are configured" — the
    # inversion of the failure this control exists to catch.
    policies_unreadable = _evidence_unavailable(policy_text)
    has_policies = not policies_unreadable and _count_data_lines(policy_text) > 0
    has_devices = intune.get("has_data") and intune.get("total", 0) > 0
    if intune.get("unavailable") and not has_policies:
        # Graph refused the device read. "No Intune devices found" is a claim
        # about the tenant, and this control has no evidence for it.
        add("6.1.1", "Ensure device compliance policies are configured", t.cis_cat_devices, "info",
            _CANNOT_VERIFY + (intune.get("unavailable_reason") or "Intune-data utilgjengelig"))
    elif not has_policies and not has_devices and intune.get("entra_total", 0) > 0:
        # The directory knows devices; Intune manages none of them. That is not
        # "no devices found" — it is every endpoint in the tenant sitting
        # outside compliance management, which is the failure this control is
        # for. Reporting it as info was an artefact of only ever asking Intune.
        add("6.1.1", "Ensure device compliance policies are configured", t.cis_cat_devices, "fail",
            t("cis_entra_devices_unmanaged", total=intune["entra_total"]))
    elif not has_policies and not has_devices:
        add("6.1.1", "Ensure device compliance policies are configured", t.cis_cat_devices, "info",
            t.cis_no_intune)
    elif not has_policies and policies_unreadable:
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
    _ret_raw = purview.get("retention_policies", 0) if purview else 0
    ret_count = len(_ret_raw) if isinstance(_ret_raw, list) else (_ret_raw if isinstance(_ret_raw, int) else 0)
    # Count-gated, not text-gated: the "(none)" _section_block placeholder is
    # non-empty text, so `or retention_text.strip()` passed the control on a
    # section with zero retention policies while the card showed 0. Empty →
    # warn, matching 3.1.1 and 3.2.1.
    if ret_count > 0:
        add("7.2.2", "Ensure data retention policies are configured", t.cis_cat_data, "pass",
            f"{ret_count} oppbevaringspolicyer")
    elif _section_ran(fc, "19e_purview_retention_policies.txt"):
        add("7.2.2", "Ensure data retention policies are configured", t.cis_cat_data, "warn",
            "Ingen oppbevaringspolicyer funnet")
    else:
        add("7.2.2", "Ensure data retention policies are configured", t.cis_cat_data, "info",
            _CANNOT_VERIFY + "Purview-oppbevaringsdata utilgjengelig")

    # ═══ 8. TEAMS ═══

    teams_ext = fc.get("16c_teams_external_access.txt", "")
    _b2b_collab = _labelled_value(teams_ext, "B2B Collaboration")
    _b2b_direct = _labelled_value(teams_ext, "B2B Direct Connect")
    _has_partner_cfg = "Partner Configurations (" in teams_ext
    if not teams_ext.strip():
        add("8.1.1", "Ensure external access in Teams is managed", t.cis_cat_teams, "info",
            "Kan ikke verifiseres — Teams external access-data utilgjengelig")
    elif not _b2b_collab and not _b2b_direct and not _has_partner_cfg:
        # Data present but every access-type is N/A and there are no partner
        # configurations — the cross-tenant policy was not returned, or the
        # tenant is on Microsoft defaults. That is no evidence either way, so it
        # must not read as "enabled with restrictions" drawn from empty fields
        # (M365 review, F4).
        add("8.1.1", "Ensure external access in Teams is managed", t.cis_cat_teams, "info",
            _CANNOT_VERIFY + "kryssleie-tilgangspolicy ikke innsamlet eller tenant på Microsoft-standard")
    else:
        teams_ext_low = teams_ext.lower()
        if "blocked" in teams_ext_low or "disabled" in teams_ext_low:
            add("8.1.1", "Ensure external access in Teams is managed", t.cis_cat_teams, "pass",
                "Ekstern tilgang er begrenset")
        elif "allowed for all" in teams_ext_low or "everyone" in teams_ext_low or "no restrictions" in teams_ext_low:
            # Explicit fail when external access is wide open
            add("8.1.1", "Ensure external access in Teams is managed", t.cis_cat_teams, "fail",
                "Ekstern tilgang er uten begrensninger — anyone-mode")
        else:
            # A real access-type value is present but not "blocked" — review
            add("8.1.1", "Ensure external access in Teams is managed", t.cis_cat_teams, "warn",
                "Ekstern tilgang er aktivert med begrensninger — bør gjennomgås mot policy")

    # 8.1.2 Guest access.
    #
    # This read 16b_teams_settings.txt and emitted a permanent "info" saying
    # the settings had been fetched. That file holds messaging settings, every
    # value N/A on a real tenant, and nothing whatsoever about guests — so the
    # control asserted it had data because a file existed, and was the only one
    # of the thirty that could never pass or fail. A control that cannot reach
    # a verdict is decoration in a compliance table.
    #
    # The guest settings live in the Teams section's own file, already mapped
    # from the raw Graph values to readable names by teams_policies.py.
    guest_txt = fc.get("30b_teams_guest_access.txt", "")
    invites = _labelled_value(guest_txt, "Allow Invites From")
    guest_role = _labelled_value(guest_txt, "Guest User Role")

    if not invites:
        add("8.1.2", "Ensure Teams guest access is restricted", t.cis_cat_teams, "info",
            _CANNOT_VERIFY + "gjesteinnstillinger ble ikke hentet")
    else:
        detail = f"Invitasjoner: {invites}. Gjesterolle: {guest_role or 'ukjent'}"
        if "same as member" in guest_role.lower():
            # Worse than any invitation setting: whoever gets in sees what a
            # member sees, so the invitation gate stops mattering.
            add("8.1.2", "Ensure Teams guest access is restricted", t.cis_cat_teams, "fail",
                detail + " — gjester har samme tilgang som ansatte")
        elif invites.lower().startswith("everyone"):
            add("8.1.2", "Ensure Teams guest access is restricted", t.cis_cat_teams, "fail",
                detail + " — gjester kan invitere flere gjester")
        elif "member" in invites.lower():
            add("8.1.2", "Ensure Teams guest access is restricted", t.cis_cat_teams, "warn",
                detail + " — alle ansatte kan invitere gjester")
        else:
            add("8.1.2", "Ensure Teams guest access is restricted", t.cis_cat_teams, "pass",
                detail)

    # ═══ 9. LOGGING & MONITORING ═══

    # 9.1 Unified audit log. History: first a hardcoded "pass" (false attestation
    # for every tenant), then gated on the Entra directoryAudits row count — but
    # that log is ALWAYS on and independent of the Exchange/Purview Unified Audit
    # Log INGESTION toggle this control is about, so both graded verdicts were
    # wrong (a false PASS on a UAL-off tenant, a false FAIL on a quiet-but-enabled
    # one), and it was then downgraded to a permanent cannot-verify.
    #
    # The real signal is `Get-AdminAuditLogConfig | UnifiedAuditLogIngestionEnabled`,
    # now collected by the EXO helper into 27d. Parse that specific line — the
    # evidence writer renders the bool via _fmt_val → "Yes"/"No" (not
    # "true"/"false"), so accept both shapes, exactly as 4.1 does. Fail-closed: a
    # missing or unreadable setting stays cannot-verify (info), never a
    # manufactured pass or fail.
    ual_text = fc.get("27d_exchange_admin_audit_log_config.txt", "")
    ual_enabled = None
    for line in ual_text.splitlines():
        if "UnifiedAuditLogIngestionEnabled" in line and ":" in line:
            val = line.split(":", 1)[1].strip().rstrip(";").lower()
            if val in ("true", "false", "yes", "no"):
                ual_enabled = val in ("true", "yes")
            break
    if ual_enabled is True:
        add("9.1", "Ensure unified audit logging is enabled", t.cis_cat_logging, "pass",
            "Unified Audit Log-ingestion er aktivert (UnifiedAuditLogIngestionEnabled=True)")
    elif ual_enabled is False:
        add("9.1", "Ensure unified audit logging is enabled", t.cis_cat_logging, "fail",
            "Unified Audit Log-ingestion er deaktivert (UnifiedAuditLogIngestionEnabled=False) — "
            "kjør Set-AdminAuditLogConfig -UnifiedAuditLogIngestionEnabled $true")
    else:
        add("9.1", "Ensure unified audit logging is enabled", t.cis_cat_logging, "info",
            _CANNOT_VERIFY + "Unified Audit Log-innstillingen ble ikke hentet — "
            "verifiser Set-AdminAuditLogConfig -UnifiedAuditLogIngestionEnabled manuelt")

    # 9.2 Defender alerts. An empty alerts file was read as "no alerts", which
    # is only true when the alert query ran — the count file states that
    # explicitly, so require one of the two to have been written.
    defender_alerts = fc.get("19b_defender_active_alerts.txt", "")
    alert_count_text = fc.get("19b_defender_alert_count.txt", "")
    # Count the alert rows rather than matching a phrase. The guard used to
    # look for "0 active" while the collector writes "(0 unresolved)", so the
    # substring never matched and a tenant with zero alerts was told that
    # active alerts required follow-up — a warning raised by a string that was
    # never going to be there.
    open_alerts = _count_data_lines(defender_alerts) if defender_alerts.strip() else 0
    if open_alerts > 0:
        add("9.2", "Ensure security alerts are monitored", t.cis_cat_logging, "warn",
            f"{open_alerts} aktive Defender-varsler krever oppfølging")
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
    has_risky_data = not _evidence_unavailable(risky_text)

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
    else:
        _mpct = mfa.get("pct", 0)
        _mtot = mfa.get("total", 0)
        _munk = mfa.get("unknown", 0)
        # A high percentage measured on a heavily-throttled subset is not "well
        # protected". The score already flags the subset; the exec summary must
        # not contradict it with an all-clear (accuracy sweep).
        if _mtot > 0 and _munk / _mtot >= 0.1:
            bullets.append(t("exec_mfa_subset", pct=_mpct,
                             measured=mfa.get("measured", _mtot - _munk),
                             total=_mtot, unknown=_munk))
        elif _mpct >= 95:
            bullets.append(t("exec_mfa_good", pct=_mpct))
        else:
            bullets.append(t("exec_mfa_partial", pct=_mpct, no_mfa=mfa.get('no_mfa', 0)))

    # Secure Score — same reasoning; 0% is a reading, not a missing reading.
    if ss.get("has_data"):
        if ss.get("pct", 0) >= 75:
            bullets.append(t("exec_ss_good", pct=ss['pct']))
        else:
            bullets.append(t("exec_ss_low", pct=ss['pct'], count=len(ss.get('improvements', []))))

    # Intune. "All compliant" must mean every device is CONFIRMED compliant, not
    # merely "zero non-compliant" — devices in grace-period / not-evaluated sit in
    # a third (unknown) bucket, and claiming an all-clear over them contradicted
    # compliance_pct and the score's own penalty. The non-compliant percentage is
    # taken from the non-compliant count, not 100-compliance_pct (which folds in
    # the unknown bucket and disagreed with the "{n} of {total}" it sits beside).
    if intune.get("total", 0) > 0:
        _it = intune["total"]
        _inc = intune.get("noncompliant", 0)
        # The real parser always sets "compliant"; fall back to the old binary
        # assumption (total - noncompliant) only when it is absent, so the
        # three-way logic engages exactly when there is a measured unknown bucket.
        _ic = intune.get("compliant", _it - _inc)
        if _inc > 0:
            bullets.append(t("exec_intune_noncompliant",
                             noncompliant=_inc, total=_it,
                             pct=round(_inc / _it * 100)))
        elif _ic >= _it:
            bullets.append(t("exec_intune_ok", total=_it))
        else:
            bullets.append(t("exec_intune_partial", compliant=_ic, total=_it,
                             unknown=_it - _ic - _inc))

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
        # "F" must map to a description at least as severe as "D" — without it the
        # worst tenants had their posture printed as "unknown" (accuracy sweep).
        grade_text = {"A": t.exec_grade_a, "B": t.exec_grade_b, "C": t.exec_grade_c,
                      "D": t.exec_grade_d, "F": t.exec_grade_f}
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

    # ── Email — read the verdict the CIS email controls already reached ──
    # The axis used to run its own SPF/DMARC ladder that knew only MISSING and
    # WEAK, so a DMARC p=quarantine (which the collector tokenises as "WARN")
    # and a missing DKIM — both graded by the CIS Email controls — deducted
    # nothing, and the axis sat at 100 while the compliance table showed those
    # very controls failing. That contradiction is exactly what a reader loses
    # trust over. Score the axis off the compliance map instead: pass = full
    # credit, partial = half, fail = none, and "info" (could-not-verify)
    # excluded exactly as compliance_pct excludes it. One source of truth, so
    # the radar and the table can never disagree again. No assessable email
    # control (every domain ignored, or the DNS section never ran) means no
    # axis — a fabricated 100 there would be an assurance we never earned, the
    # same rule every other axis on this chart already follows.
    _email_credit = {"pass": 1.0, "partial": 0.5, "fail": 0.0}
    email_controls = [
        c for c in context.get("compliance", [])
        if c.get("category") == t.cis_cat_email and c.get("status") in _email_credit
    ]
    if email_controls:
        email_score = sum(_email_credit[c["status"]] for c in email_controls) / len(email_controls)
        categories[t.radar_email] = round(email_score * 100)

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

        # Label. Escaped even though the categories are fixed names today: the
        # result is injected into the report via {{ radar_svg | safe }}, so an
        # unescaped label would be an injection sink the moment a category name
        # ever becomes data-derived.
        from html import escape as _xml_escape
        lx = cx + (max_r + 20) * math.cos(angle)
        ly = cy + (max_r + 20) * math.sin(angle)
        anchor = "middle"
        if lx < cx - 10: anchor = "end"
        elif lx > cx + 10: anchor = "start"
        svg.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="11" fill="#6b7280" font-family="sans-serif" dominant-baseline="middle">{_xml_escape(str(label))}</text>')

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

def _drift_for(out_dir: Path) -> dict:
    """Policy drift for this run, or a stated reason there is none to show.

    Wrapped for the same reason load_previous_metrics is: drift is an
    enhancement to the report, and the report is the deliverable. A snapshot
    that will not decrypt must cost the comparison, never the document.

    The fallback is the module's own "not measured" shape rather than an empty
    diff — an empty diff reads as "nothing changed", which is a claim about
    the tenant made on the strength of an exception.
    """
    from app.core.policy_drift import compute_drift, unmeasured

    try:
        return compute_drift(out_dir)
    except Exception as e:
        log.warning("Drift comparison failed for %s: %s", out_dir.name, e)
        return unmeasured("comparison_failed")


def _baseline_for(context: dict) -> dict | None:
    """Judge the finished context against the house standard.

    Returns None when there is no baseline to judge by — a malformed or
    missing document is a fault in our configuration, and the report says
    nothing rather than inventing a verdict from it. The template omits the
    section entirely in that case.
    """
    from app.core.baseline import BaselineError, default_baseline_id, evaluate

    baseline_id = default_baseline_id()
    try:
        return evaluate(baseline_id, context)
    except BaselineError as e:
        log.warning("Baseline %s could not judge this run: %s", baseline_id, e)
        return None
    except Exception as e:
        log.warning("Baseline %s raised while judging this run: %s", baseline_id, e)
        return None


def build_report_context(
    customer_name: str,
    org_domain:    str,
    out_dir:       Path,
    results:       list[SectionResult],
    lang:          str = "no",
    frameworks:    str = "all",
    persist_metrics: bool = True,
) -> dict:
    """Parse one audit run into everything a report or a reader needs.

    ``persist_metrics`` exists because this function writes. It ends by saving
    _audit_metrics.json and inserting a row in audit_metrics, which is right
    when an audit has just produced the run and wrong for everybody else — and
    "everybody else" grew: the baselines endpoint builds a context to *read*
    one, and so does anything that scores an old run.

    Left as it was, a customer card rewrote that run's stored metrics on every
    open, stamping it with the current time. It also cost twenty-one duplicate
    trend rows in one second when a maintenance script walked every run.

    Pass False from any caller that is reading. The default stays True so an
    audit that has just finished keeps recording itself without having to
    remember to ask.
    """
    from app.core.encryption import encrypted_read_text
    file_contents: dict[str, str] = {}
    # Named apart from the "failed_sections" context key, which is a count of
    # sections whose collector reported failure. A section can report success
    # and still write an error into its file, so the two disagree on exactly
    # the tenants this list exists for.
    error_files: list[str] = []
    # .json as well as .txt: the MFA collector writes a machine-readable
    # sidecar next to its rendered table, and globbing only *.txt meant the
    # reader never saw it and silently fell back to parsing the table on every
    # single run — so the sidecar that exists to make the figures reliable was
    # dead weight. Error-payload blanking below applies to both.
    for f in sorted([*out_dir.glob("*.txt"), *out_dir.glob("*.json")]):
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
            error_files.append(f.name)
            text = ""
        file_contents[f.name] = text

    def fc(name: str) -> str:
        return file_contents.get(name, "")

    warn_files = [n for n in file_contents if "WARN" in n.upper()]
    all_warns  = [w for r in results for w in r.warns]

    secure_score = _parse_secure_score(fc("09_secure_score.txt"))
    users        = _parse_user_counts(fc("03_users_count.txt"))
    mfa          = _parse_mfa(fc("04_mfa_methods.txt"), fc("04b_mfa_ca_analysis.txt"), results, fc("04_mfa_methods.json"))
    licenses     = _parse_licenses(fc("02_licenses.txt"))
    license_optimization = _analyze_license_optimization(licenses, file_contents, lang=lang)
    spf_dmarc    = _parse_spf_dmarc(fc("26_email_dns_spf_dmarc.txt"))
    ca           = _parse_ca_policies(fc("08_conditional_access.txt"))
    admin_roles  = _parse_admin_roles(fc("07_admin_roles.txt"))
    intune       = _parse_intune_devices(fc("10_intune_devices_count.txt"), fc("10_intune_devices.txt"))
    entra_devices = _parse_entra_devices(fc("15_entra_devices_count.txt"), fc("15_entra_devices.txt"))
    usage        = _parse_usage(fc("16_usage_summary.txt"), fc("16_usage_active_users.txt"))
    # The claim the Intune figure alone cannot make. Only stated when both
    # sides were actually read: an unmanaged count derived from a refusal is
    # the same mistake in a new place.
    #
    # Single source of truth: the Entra register's own ``isManaged`` flag — the
    # same figure the baseline check (``entra_devices.unmanaged``), the section
    # status and the 15_entra_devices_count file all report. The old
    # ``total - intune_total`` subtracted Intune's *enrolled* count, a different
    # measure, so the recommendation (11/16) disagreed with the count file
    # (9/16) for the same tenant. Fall back to the register's own total-managed
    # (still the register, never Intune's enrolled list) if the unmanaged line
    # is absent.
    if entra_devices.get("has_data") and intune.get("has_data"):
        intune["entra_total"] = entra_devices["total"]
        intune["entra_unmanaged"] = max(
            0,
            entra_devices.get(
                "unmanaged",
                entra_devices["total"] - entra_devices.get("managed", 0),
            ),
        )
    sharepoint   = _parse_sharepoint_settings(fc("15b_sharepoint_settings.txt"), fc("15_sharepoint_sites.txt"), lang=lang)
    oauth        = _parse_oauth_grants(fc("17b_oauth_consent_grants.txt"), fc("17_app_registrations.txt"))
    # The reader blanks an error-payload file to "" before the parser sees it, so
    # the parser's own grants_read (derived from the text) can never see the
    # "Error:" stub and is always True in production. error_files survives that
    # blanking, so derive the authoritative signal here: a 17b that was an error
    # payload means the consent-grants read failed (fix review).
    oauth["grants_read"] = "17b_oauth_consent_grants.txt" not in error_files
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
    _unavailable = [
        r.name for r in results
        if r.status in (SectionStatus.SKIPPED, SectionStatus.FAILED)
    ]
    risk         = _compute_risk(secure_score, mfa, spf_dmarc, all_warns, ext_fwd, risky, defender,
                                 admin_roles, intune, sharepoint, oauth, network=network, lang=lang,
                                 unavailable_sections=_unavailable)
    recs         = _build_recommendations(mfa, spf_dmarc, secure_score, ext_fwd, risky, licenses,
                                          admin_roles, intune, sharepoint, oauth,
                                          azure, file_contents,
                                          backup_coverage=backup_coverage,
                                          signin_risk=signin_risk,
                                          network=network,
                                          lang=lang)
    # An open critical finding must be visible in the headline grade (F9).
    _apply_critical_floor(risk, recs, lang)

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
        "entra_devices":   entra_devices,
        "usage":           usage,
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

    # The break-glass check embeds a machine-readable "SUMMARY: break_glass_…"
    # line in 07c for CIS 1.1.6 to parse — which it just did, above. That token
    # is not human prose, and 07c is rendered verbatim both in the Emergency
    # Access panel and in the raw-evidence appendix (which dumps every file in
    # file_contents). Strip it now, after parsing, from the shared dict and the
    # panel copy, so the internal token never reaches the delivered report.
    _bg_file = "07c_emergency_access_check.txt"
    if file_contents.get(_bg_file):
        _stripped = "\n".join(
            ln for ln in file_contents[_bg_file].splitlines()
            if not ln.strip().startswith("SUMMARY:")
        )
        file_contents[_bg_file] = _stripped
        context["emergency_access"] = _stripped
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
    # The count of controls left out of the denominator. Computed here since
    # the percentage was first introduced, but never passed to a template, so
    # the reports showed a rate without showing what it was a rate of.
    context["compliance_info"] = compliance_info
    context["compliance_pct"] = compliance_pct
    context["show_nist"] = frameworks in ("cis+nist", "all")
    context["show_iso"]  = frameworks in ("cis+iso", "all")

    # Which collected files held an error, and which controls they leave
    # unverified. The verdicts themselves already say "cannot be verified";
    # nothing said why, because the evidence links deliberately skip a file
    # whose contents were blanked, so a failed file is the one case that
    # cites nothing. Read out of _EVIDENCE_MAP in the opposite direction,
    # and intersected with the controls the table actually lists so this
    # never points at a row that is not there.
    shown_ids = {c["cis_id"] for c in compliance}
    context["error_files"] = [
        {
            "name": name,
            "controls": sorted(
                cis_id for cis_id, files in _EVIDENCE_MAP.items()
                if name in files and cis_id in shown_ids
            ),
        }
        for name in error_files
    ]

    # A count of nought and a count never taken read the same on a report, and
    # a customer cannot tell "you have no sensitivity labels" from "we could
    # not look". The technical report lists the errored sections outright; the
    # customer report showed a brand-coloured 0 with nothing beside it.
    #
    # The flag has to be set from error_files rather than inside the parser:
    # the reader blanks an errored file before any parser sees it, so by the
    # time _parse_purview runs, the evidence that the fetch failed is gone.
    for flag, section in (
        ("sensitivity_labels_unavailable", "19c_purview_sensitivity_labels.txt"),
        ("dlp_unavailable", "19d_purview_dlp_policies.txt"),
        ("retention_unavailable", "19e_purview_retention_policies.txt"),
    ):
        context["purview"][flag] = section in error_files

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

    # Enrich each recommendation with its remediation status. The store keys
    # by rec_id (the stable, language-independent identity), so look it up by
    # rec_id first. A title fallback keeps old rows — saved before rec_id
    # existed — from silently reading as "open".
    for rec in recs:
        rec_id = rec.get("rec_id", "")
        title = rec.get("title", "")
        if rec_id and rec_id in remediation:
            rec["remediation"] = remediation[rec_id]
        elif title and title in remediation:
            rec["remediation"] = remediation[title]
        else:
            rec["remediation"] = {"status": "open", "notes": "", "updated_by": "", "updated_date": ""}

    context["remediation"] = remediation
    # Count done/ignored among the findings in THIS report, not across every
    # stored row. A finding can drop out of a later audit while its remediation
    # row persists, which would otherwise push the percentage past 100.
    remediation_done = sum(
        1 for rec in recs if rec.get("remediation", {}).get("status") in ("done", "ignored")
    )
    remediation_total = len(recs) if recs else 0
    context["remediation_done"] = remediation_done
    context["remediation_total"] = remediation_total
    context["remediation_pct"] = round(remediation_done / remediation_total * 100) if remediation_total else 0

    # ── Drift, then the standard that reads it ─────────────────────────────
    # Last, and in this order. The baseline evaluates paths through the
    # finished context, so every key it can name must already be set — drift
    # included, since a check on "no policy disappeared since last audit" is
    # exactly the kind a versioned standard should carry.
    context["drift"] = _drift_for(out_dir)
    context["baseline"] = _baseline_for(context)

    # The policies in production, consolidated from this run's snapshots, each
    # with a plain-language line. Same source the customer card reads, so the
    # report and the card can never disagree about what is configured.
    try:
        from app.core.policy_inventory import build_inventory
        context["policy_inventory"] = build_inventory(out_dir)
    except Exception:
        context["policy_inventory"] = None

    if persist_metrics:
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


def _pdf_url_fetcher(url: str):
    """Refuse every resource the report render tries to fetch except data: URIs.

    The report embeds all its assets — logos included — as ``data:`` URIs, so
    nothing legitimate is loaded from disk or the network. WeasyPrint renders
    the report HTML server-side, and that HTML carries attacker-influenceable
    tenant fields (a display name, a device name). Without this fetcher, an
    injected ``<img src="http://169.254.169.254/…">`` or ``url('file:///etc/…')``
    would make the server fetch an attacker-chosen internal or local URL at
    render time — an SSRF / local-file read that the browser-side CSP on the
    served HTML never applies to. Allow only data:, block the rest.
    """
    from weasyprint import default_url_fetcher
    if url.startswith("data:"):
        return default_url_fetcher(url)
    raise ValueError(f"Blocked non-data URL during report render: {url[:80]}")


def generate_pdf(html_path: Path, output_path: Path) -> Path:
    try:
        from weasyprint import HTML

        from app.core.encryption import encrypted_read_text
        html_content = encrypted_read_text(html_path)
        HTML(
            string=html_content,
            base_url=str(html_path.parent),
            url_fetcher=_pdf_url_fetcher,
        ).write_pdf(str(output_path))
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
