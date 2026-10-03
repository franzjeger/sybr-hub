"""Parsers that turn raw audit collector files into structured data."""

from __future__ import annotations

import contextlib
import json
import logging
import re

from app.modules.base import SectionResult
from app.reports.evidence import _evidence_unavailable
from app.reports.i18n import T

log = logging.getLogger(__name__)

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


def _parse_user_counts(text: str) -> dict:
    result = {
        "total": 0,
        "enabled": 0,
        "disabled": 0,
        "guests": 0,
        "hybrid": 0,
        "cloud": 0,
        "has_data": False,
    }
    for line in text.splitlines():
        for key, field in [
            ("Total users", "total"),
            ("Enabled", "enabled"),
            ("Disabled", "disabled"),
            ("Guest accounts", "guests"),
            ("Hybrid (synced)", "hybrid"),
            ("Cloud-only", "cloud"),
        ]:
            if key in line and ":" in line:
                with contextlib.suppress(ValueError):
                    result[field] = int(line.split(":")[-1].strip())
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
        if (
            not stripped
            or stripped.startswith("=")
            or stripped.startswith("-")
            or "Display Name" in stripped
            or "MFA METHOD" in stripped
            or stripped.startswith("NOTE:")
        ):
            continue

        if "|" in stripped:
            # Pipe-delimited: "Name | UPN | MFA:YES | CA:YES | CA_EXCL:NO"
            parts = [p.strip() for p in stripped.split("|")]
            if not any(p.startswith("MFA:") for p in parts):
                continue
            rec = {
                "display_name": parts[0] if parts else "",
                "upn": parts[1] if len(parts) > 1 else "",
                "mfa_registered": False,
                "ca_covered": False,
                "ca_excluded": False,
                "methods": [],
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
            cols = re.split(r"\s{2,}", stripped)
            if len(cols) < 3 or not any(c.strip() in ("YES", "NO") for c in cols[2:]):
                continue
            records.append(
                {
                    "display_name": cols[0].strip(),
                    "upn": cols[1].strip() if len(cols) > 1 else "",
                    "mfa_registered": "YES" in cols[2],
                    "ca_covered": len(cols) > 3 and "YES" in cols[3],
                    "ca_excluded": len(cols) > 4 and "YES" in cols[4],
                    "methods": [],
                }
            )
            continue

        records.append(
            {
                "display_name": _col("display_name"),
                "upn": _col("upn"),
                # "?" is unknown, not "no MFA" — see the collector.
                "mfa_registered": None if mfa_tok == "?" else mfa_tok == "YES",
                "ca_covered": _col("ca") == "YES",
                "ca_excluded": _col("ca_excl") == "YES",
                "methods": [],
            }
        )
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
        m = re.search(r"Effectively covered.*?:\s*(\d+)", ca_analysis_text)
        if m:
            ca_analysis_covered = int(m.group(1))
        m = re.search(r"Users covered by CA MFA.*?:\s*(\d+)", ca_analysis_text)
        if m and not ca_analysis_covered:
            ca_analysis_covered = int(m.group(1))
        m = re.search(r"excluded from CA MFA\s*:\s*(\d+)", ca_analysis_text)
        if m:
            ca_analysis_excluded = int(m.group(1))
        m = re.search(r"NOT covered.*?\((\d+)\)", ca_analysis_text)
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
        users_detail.append(
            {
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
                "unknown": (rec.get("mfa_registered") is None and not u_has_ca and not u_excluded),
                # Same enforcement rule as `covered` above: a CA exclusion means the
                # account is not MFA-enforced, registered method or not.
                "protected": (u_has_mfa or u_has_ca) and not u_excluded,
            }
        )

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
        elif (
            prev_key == "dmarc"
            and (stripped.startswith("v=DMARC1") or stripped == "(none)")
            and current
        ):
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
    ".pphosted.com",  # Proofpoint
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
        (
            "CONDITIONAL ACCESS POLICIES" in text
            or ("Error fetching CA policies" not in text and bool(text.strip()))
        )
        if text.strip()
        else False
    )
    for line in text.splitlines():
        low = line.lower().strip()
        # Support both pipe-delimited ("enabled | PolicyName | ...") and
        # bracket format ("[enabled   ] PolicyName ...")
        if (
            not low
            or low.startswith("=")
            or low.startswith("-")
            or ("state" in low and "policy" in low)
        ):
            continue
        # Report-only first. Graph spells that state
        # "enabledForReportingButNotEnforced", which starts with "enabled", so
        # testing for "[enabled" ahead of it swallowed every report-only policy
        # into the enabled count and left the branch below unreachable. A
        # tenant staging its Conditional Access in report-only mode — where
        # nothing is enforced — was reported as having those policies live.
        if (
            low.startswith("[reportonly")
            or low.startswith("[report_only")
            or low.startswith("[enabledforr")
        ):
            report_only += 1
        elif low.startswith("[enabled"):
            enabled += 1
        elif low.startswith("[disabled"):
            disabled += 1
        # Legacy pipe format
        elif "|" in line:
            squashed = low.replace(" ", "")
            if (
                "enabled" in low
                and "disabled" not in low
                and "reportonly" not in squashed
                and "enabledforreporting" not in squashed
            ):
                enabled += 1
            elif "disabled" in low:
                disabled += 1
            elif "reportonly" in low.replace(" ", ""):
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
_ADMIN_ROLE_SPAN = (2, 42)
_ADMIN_DISPLAY_SPAN = (43, 73)
_ADMIN_UPN_SPAN = (74, 119)
_ADMIN_DISPLAY_WIDTH = _ADMIN_DISPLAY_SPAN[1] - _ADMIN_DISPLAY_SPAN[0]
_UPN_TOKEN_RE = re.compile(r"\S+@\S+")


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
        display = line[upn_start - _ADMIN_DISPLAY_WIDTH - 1 : upn_start - 1].strip()
        upn = line[upn_start : upn_start + 45].strip()
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
        if (
            not stripped
            or stripped.startswith("=")
            or stripped.startswith("-")
            or "ADMIN ROLE" in stripped
            or ("Role" in stripped and "Display Name" in stripped)
        ):
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
        cols = re.split(r"\s{2,}", stripped)
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
                roles.append(
                    {
                        "role": cols[0],
                        "user": " ".join(cols[1:-1]) if len(cols) > 2 else cols[1],
                        "email": cols[-1],
                    }
                )
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


def _parse_entra_devices(count_text: str, detail_text: str) -> dict:
    """The directory's own device register, beside the Intune one.

    Its whole purpose is the gap between the two counts: devices the tenant
    has, minus devices Intune manages, is the unmanaged-endpoint finding. With
    only the Intune figure, a tenant with forty joined machines and no
    enrolment read as "no devices found".
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


def _parse_intune_devices(count_text: str, detail_text: str) -> dict:
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
    result["noncompliant_devices"] = [
        d for d in result["devices"] if d.get("compliance", "").lower() not in ("compliant", "")
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
    # having 108.
    site_count = _count_data_lines(sites_text)

    # A personal site is identified by its host, not by the word "personal"
    # appearing anywhere on the line. This tenant has an ordinary team site
    # named "Personal FF HF" at /sites/pers, which the substring match filed as
    # a OneDrive — the one "personal" site in a report where there are none.
    personal_sites = sum(
        1
        for line in sites_text.splitlines()
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
    high_priv_keywords = {
        "fullcontrol",
        "readwrite.all",
        "accessasuser.all",
        "manage",
        "rolemanagement.readwrite",
    }

    _UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    section = ""

    for line in text.splitlines():
        stripped = line.strip()
        if "ADMIN CONSENT" in stripped or "CONSENT GRANTS" in stripped or "TENANT-WIDE" in stripped:
            section = "admin"
            continue
        elif "APPLICATION PERMISSIONS" in stripped:
            section = "app"
            continue
        elif not stripped or stripped.startswith("===") or stripped.startswith("-"):
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
            cols = re.split(r"\s{2,}", stripped)
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
            groups.append(
                {
                    "name": name,
                    "type": gtype,
                    "members": members,
                    "members_known": members_known,
                }
            )

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


# A protected item in one of these states is not backing the VM up: it was
# stopped, paused or suspended, or never valid. Its recovery points may still
# exist, but nothing new is being taken.
_BACKUP_INACTIVE_STATES = {"protectionstopped", "protectionpaused", "backupssuspended", "invalid"}

# The VM listing trims names to this width. A legacy run without the JSON
# sidecar can only match a trimmed name by prefix.
_VM_NAME_WIDTH = 35


def _vm_inventory(file_contents: dict[str, str]) -> list[dict]:
    """Every VM, as {"name", "id"}. The JSON sidecar when the run wrote one."""
    vms: list[dict] = []
    sidecars = [
        f for f in _find_azure_json(file_contents, "30_azure_vms") if "cpu_metrics" not in f[0]
    ]
    for _fname, content, _sub in sidecars:
        try:
            data = json.loads(content)
        except ValueError:
            continue
        for vm in data.get("vms") or []:
            if vm.get("name"):
                vms.append({"name": vm["name"], "id": (vm.get("id") or "").lower()})
    if sidecars:
        return vms
    for fname, content, _sub in _find_azure_files(file_contents, "30_azure_vms"):
        if "cpu_metrics" in fname:
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("=")
                or stripped.startswith("-")
                or "VM Name" in stripped
                or "AZURE VIRTUAL" in stripped
                or stripped.startswith("Error")
            ):
                continue
            cols = re.split(r"\s{2,}", stripped)
            if len(cols) >= 4:
                vms.append({"name": cols[0], "id": ""})
    return vms


def _backup_inventory(file_contents: dict[str, str]) -> dict:
    """What the vaults protect: {"read", "complete", "vaults", "items"}.

    read: some vault data was read successfully (an empty read counts).
    complete: every vault's item list was read in full. When it was not, a VM
    missing from the list may still be protected, so it cannot be named.
    """
    out: dict = {"read": False, "complete": True, "vaults": set(), "items": []}
    sidecars = _find_azure_json(file_contents, "52_azure_backup")
    for _fname, content, _sub in sidecars:
        try:
            data = json.loads(content)
        except ValueError:
            continue
        out["read"] = True
        for vault in data.get("vaults") or []:
            out["vaults"].add(vault.get("name") or "")
            if vault.get("items_error"):
                out["complete"] = False
            for item in vault.get("items") or []:
                state = (item.get("protection_state") or "").lower()
                out["items"].append(
                    {
                        "name": (item.get("friendly_name") or item.get("name") or "").lower(),
                        "id": (item.get("source_resource_id") or "").lower(),
                        "active": state not in _BACKUP_INACTIVE_STATES,
                    }
                )
    if sidecars:
        return out

    # A run from before the sidecar. This is the format _collect_backup writes:
    # a "Vault    : name" block per vault, then "      - <name>  Status:..."
    # per protected item. The item lines start with "-", and an earlier parser
    # skipped every line that did, so it read no items at all and listed every
    # VM as unprotected.
    for _fname, content, _sub in _find_azure_files(file_contents, "52_azure_backup"):
        if not content.strip() or content.strip().startswith("Error:"):
            continue
        out["read"] = True
        for line in content.splitlines():
            stripped = line.strip()
            vault = re.match(r"Vault\s*:\s*(.+)$", stripped)
            if vault:
                out["vaults"].add(vault.group(1).strip())
            elif stripped.startswith("Protected Items:") and "Error" in stripped:
                out["complete"] = False
            elif re.match(r"\.\.\. and \d+ more items", stripped):
                # Listings were cut at 15 items per vault.
                out["complete"] = False
            elif stripped.startswith("- "):
                name = re.split(r"\s{2,}", stripped[2:].strip())[0]
                state = re.search(r"State:(\S+)", stripped)
                active = not state or state.group(1).lower() not in _BACKUP_INACTIVE_STATES
                out["items"].append({"name": name.lower(), "id": "", "active": active})
    return out


def _parse_backup_coverage(file_contents: dict[str, str]) -> dict:
    """Cross-reference Azure VMs with the items the backup vaults protect.

    Coverage is a cross-reference between two independently collected files.
    If the backup half was not read, every VM would fall into
    vms_not_backed_up: a high-priority "these servers have no backup" finding,
    naming each one, from a file nobody read. So coverage is only known when
    the vault data was read, and when the item lists were complete or every VM
    was found in them anyway. An empty *successful* read is a real finding.

    A VM matches an item by resource id when the run recorded ids, otherwise by
    name. An item whose protection was stopped, paused or suspended does not
    count: nothing new is being backed up.
    """
    vms = _vm_inventory(file_contents)
    backup = _backup_inventory(file_contents)
    by_id = {i["id"]: i for i in backup["items"] if i["id"]}
    by_name = {}
    for item in backup["items"]:
        by_name.setdefault(item["name"], item)

    def match(vm: dict) -> dict | None:
        if vm["id"] and vm["id"] in by_id:
            return by_id[vm["id"]]
        name = vm["name"].lower()
        if name in by_name:
            return by_name[name]
        if len(vm["name"]) == _VM_NAME_WIDTH:
            return next((i for n, i in by_name.items() if n.startswith(name)), None)
        return None

    vms_total = len(vms)
    matched = {vm["name"]: match(vm) for vm in vms}
    all_found = bool(vms) and all(item is not None for item in matched.values())
    coverage_known = backup["read"] and vms_total > 0 and (backup["complete"] or all_found)

    vms_backed_up = 0
    vms_not_backed_up: list[str] = []
    vms_backup_stopped: list[str] = []
    if coverage_known:
        for vm in vms:
            item = matched[vm["name"]]
            if item is not None and item["active"]:
                vms_backed_up += 1
            else:
                vms_not_backed_up.append(vm["name"])
                if item is not None:
                    vms_backup_stopped.append(vm["name"])

    backup_pct = (vms_backed_up / vms_total * 100) if coverage_known else 0.0

    return {
        "vms_total": vms_total,
        "vms_backed_up": vms_backed_up,
        "vms_not_backed_up": vms_not_backed_up,  # empty unless coverage_known
        "vms_backup_stopped": vms_backup_stopped,  # a subset of the above
        "backup_pct": round(backup_pct, 1),
        "vaults": len(backup["vaults"]),
        "coverage_known": coverage_known,
        "has_data": vms_total > 0 or len(backup["vaults"]) > 0,
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
            _banner = re.search(r"\(.*?([\d,]+)\s+events\)", stripped)
            if _banner:
                with contextlib.suppress(ValueError):
                    result["total_signins"] = int(_banner.group(1).replace(",", ""))
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
            cols = re.split(r"\s{2,}", stripped)
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
                cols = re.split(r"\s{2,}", stripped)
                cnt = _num_tail(cols)
                if cnt is not None and len(cols) >= 2:
                    error_code_rows.append(
                        {
                            "code": cols[0],
                            "reason": cols[1] if len(cols) >= 3 else "",
                            "count": cnt,
                        }
                    )
                continue
            if section == "countries":
                cols = re.split(r"\s{2,}", stripped)
                cnt = _num_tail(cols)
                if cnt is not None and len(cols) >= 2:
                    country_rows.append({"country": " ".join(cols[:-1]), "count": cnt})
                continue
            if section == "ips":
                cols = re.split(r"\s{2,}", stripped)
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
                    elif not p.startswith("*"):  # skip the "*** THRESHOLD ***" flag
                        reason = p
                if user:
                    failure_users[user] = failure_users.get(user, 0) + count
                    total_failures += count
                if reason and reason.lower() not in ("reason", "error", "status"):
                    failure_reasons[reason] = failure_reasons.get(reason, 0) + count
            else:
                cols = re.split(r"\s{2,}", stripped)
                if len(cols) >= 2:
                    low_first = cols[0].lower()
                    if low_first in (
                        "user",
                        "userprincipalname",
                        "upn",
                        "display name",
                        "name",
                        "reason",
                    ):
                        continue
                    user = ""
                    reason = ""
                    count = 1
                    for c in cols:
                        if "@" in c:
                            user = c
                        elif c.isdigit():
                            count = int(c)
                        elif (
                            c.lower() not in ("true", "false", "yes", "no")
                            and len(c) > 3
                            and not c.startswith("*")
                        ):
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
        result["dlp_policies"] = [{"name": n} for n in _extract_policy_names(dlp_text)]
        result["dlp_policy_count"] = len(result["dlp_policies"])
        if result["dlp_policy_count"] > 0:
            result["has_data"] = True

    retention_text = file_contents.get("19e_purview_retention_policies.txt", "")
    if retention_text.strip():
        result["retention_policies"] = [{"name": n} for n in _extract_policy_names(retention_text)]
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
        rest = fname[len(base) :]
        if rest == ".txt":
            matches.append((fname, content, ""))
        elif rest.startswith("_") and rest.endswith(".txt"):
            sub_name = rest[1:-4]  # strip leading _ and .txt
            matches.append((fname, content, sub_name))
    return matches


def _find_azure_json(file_contents: dict[str, str], prefix: str) -> list[tuple[str, str, str]]:
    """Like _find_azure_files, for the .json sidecars some collectors write."""
    matches = []
    for fname, content in file_contents.items():
        if not fname.startswith(prefix):
            continue
        rest = fname[len(prefix) :]
        if rest == ".json":
            matches.append((fname, content, ""))
        elif rest.startswith("_") and rest.endswith(".json"):
            matches.append((fname, content, rest[1:-5]))
    return matches


def _parse_azure_overview(file_contents: dict[str, str]) -> dict:
    """Parse Azure data files into a structured overview.

    Supports both single-subscription (e.g. 30_azure_vms.txt) and
    multi-subscription (e.g. 30_azure_vms_Corp-Backend-01.txt) file naming.
    Aggregates data across all subscriptions.
    """
    result: dict = {
        "subscriptions": [],
        "per_sub": [],  # per-subscription breakdown
        "total_resources": 0,
        "resource_types": {},  # type -> count (aggregated)
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
        if (
            not line
            or line.startswith("=")
            or line.startswith("NOTE")
            or line.startswith("Falling")
            or line.startswith("To audit")
            or line.startswith("AZURE SUB")
        ):
            continue
        if "[" in line and "]" in line:
            parts = line.rsplit("[", 1)
            state = parts[1].rstrip("]").strip()
            name_id = parts[0].strip()
            m = re.search(
                r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", name_id
            )
            if m:
                sub_id = m.group(1)
                name = name_id[: m.start()].strip()
                result["subscriptions"].append({"name": name, "id": sub_id, "state": state})

    # ── Resource inventory (aggregate across all subs) ─────────────────────
    for _fname, content, sub_name in _find_azure_files(
        file_contents, "60_azure_resource_inventory_summary"
    ):
        sub_resources = 0
        sub_types: dict[str, int] = {}
        sub_rgs: list[dict] = []
        in_types = False
        in_rgs = False

        for line in content.splitlines():
            if "By Type:" in line:
                in_types = True
                in_rgs = False
                continue
            elif "By Resource Group:" in line:
                in_rgs = True
                in_types = False
                continue
            elif line.strip().startswith("=") or line.strip().startswith("-") or not line.strip():
                continue
            elif "AZURE RESOURCE" in line:
                m = re.search(r"\((\d+) resources?\)", line)
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
                        result["resource_types"][name] = (
                            result["resource_types"].get(name, 0) + count
                        )
                    elif in_rgs and name and name not in ("Resource Group", "Count"):
                        sub_rgs.append({"name": name, "count": count})
                        result["resource_groups"].append(
                            {"name": f"{name} ({sub_name})" if sub_name else name, "count": count}
                        )
                except ValueError:
                    pass

        result["total_resources"] += sub_resources
        if sub_resources > 0 or sub_types:
            result["per_sub"].append(
                {
                    "name": sub_name or "Default",
                    "resources": sub_resources,
                    "types": sorted(sub_types.items(), key=lambda x: -x[1]),
                    "rgs": sub_rgs,
                }
            )

    # ── VMs (aggregate across all subs) ────────────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "30_azure_vms"):
        if "cpu_metrics" in fname:
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("=")
                or stripped.startswith("-")
                or "VM Name" in stripped
                or "AZURE VIRTUAL" in stripped
            ):
                continue
            cols = re.split(r"\s{2,}", stripped)
            if len(cols) >= 4:
                result["vms"].append(
                    {
                        "name": cols[0],
                        "rg": cols[1] if len(cols) > 1 else "",
                        "location": cols[2] if len(cols) > 2 else "",
                        "os": cols[3] if len(cols) > 3 else "",
                        "size": cols[4] if len(cols) > 4 else "",
                        "status": cols[5] if len(cols) > 5 else "",
                        "subscription": sub_name,
                    }
                )

    # ── Storage accounts ───────────────────────────────────────────────────
    for _fname, content, sub_name in _find_azure_files(file_contents, "35_azure_storage"):
        for line in content.splitlines():
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("=")
                or stripped.startswith("-")
                or "Account Name" in stripped
                or "AZURE STORAGE" in stripped
            ):
                continue
            cols = re.split(r"\s{2,}", stripped)
            if len(cols) >= 3:
                result["storage_accounts"].append(
                    {
                        "name": cols[0],
                        "sku": cols[1] if len(cols) > 1 else "",
                        "kind": cols[2] if len(cols) > 2 else "",
                        "subscription": sub_name,
                    }
                )

    # ── NSGs ───────────────────────────────────────────────────────────────
    for fname, content, sub_name in _find_azure_files(file_contents, "32_azure_nsgs"):
        if "risky" in fname or "WARN" in fname:
            continue
        m = re.search(r"\((\d+) total\)", content)
        if m and int(m.group(1)) > 0:
            result["nsgs"].append({"subscription": sub_name, "count": int(m.group(1))})

    # ── Advisor recommendations (with details) ──────────────────────────────
    for _fname, content, sub_name in _find_azure_files(file_contents, "51_azure_advisor"):
        m = re.search(r"\((\d+) total\)", content)
        if m:
            result["advisor_recs"] += int(m.group(1))

        # Parse individual recommendations
        current_category = ""
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Category header: "[Cost]  (16 recommendations)"
            cat_m = re.match(r"\[(\w+)\]", line)
            if cat_m:
                current_category = cat_m.group(1)
                i += 1
                continue
            # Recommendation: "    [High    ]  Description text"
            rec_m = re.match(r"\[(\w+)\s*\]\s+(.+)", line)
            if rec_m:
                impact = rec_m.group(1)
                desc = rec_m.group(2).strip()
                resource = ""
                # Next line might be "Resource: ..."
                if i + 1 < len(lines) and "Resource:" in lines[i + 1]:
                    resource = lines[i + 1].strip().replace("Resource:", "").strip()
                    i += 1
                result["advisor_details"].append(
                    {
                        "category": current_category,
                        "impact": impact,
                        "description": desc,
                        "resource": resource,
                        "subscription": sub_name,
                    }
                )
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
    for _fname, content, sub_name in _find_azure_files(
        file_contents, "61_azure_orphaned_resources"
    ):
        m = re.search(r"\((\d+) found\)", content)
        if m:
            result["orphaned"] += int(m.group(1))
        for line in content.splitlines():
            line = line.strip()
            if (
                not line
                or line.startswith("=")
                or line.startswith("No orphaned")
                or "ORPHANED" in line
            ):
                continue
            # Format: "DISK (unattached) : diskname  500 GB  Standard_LRS  RG: rg-name"
            type_m = re.match(r"(\w[\w\s]*?)\s*\((\w+)\)\s*:\s*(.+)", line)
            if type_m:
                result["orphaned_details"].append(
                    {
                        "type": type_m.group(1).strip(),
                        "status": type_m.group(2).strip(),
                        "detail": type_m.group(3).strip(),
                        "subscription": sub_name,
                    }
                )

    # Convert resource_types dict to sorted list
    result["resource_types_list"] = sorted(
        [{"type": k, "count": v} for k, v in result["resource_types"].items()],
        key=lambda x: -x["count"],
    )

    result["has_data"] = (
        result["total_resources"] > 0 or len(result["vms"]) > 0 or len(result["subscriptions"]) > 0
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
    inbox_rules_text = file_contents.get(
        "29_exchange_inbox_rules_external_fwd_WARN.txt", ""
    ) or file_contents.get("29_exchange_inbox_rules_external_fwd.txt", "")
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
_HEADER_TOTAL_RE = re.compile(r"^[A-Z][^\(]*\(.*\b\d+\s+[A-Za-z][A-Za-z-]*\b.*\)\s*$")
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
_BANNER_PARENS_RE = re.compile(r"\(([^)]*)\)")
_BANNER_COUNT_RE = re.compile(
    r"\b(\d+)\s+(?:total|entries|found|unresolved|events?|mailboxes|results?|"
    r"assignments?|policies|devices)\b",
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


_EMPTY_PLACEHOLDER_RE = re.compile(r"^\(?\s*(none|ingen|n/?a|empty|tom)\s*\)?\.?$", re.IGNORECASE)
# "[1]" — the per-record index a multi-line section writes before its fields.
_RECORD_INDEX_RE = re.compile(r"^\[\d+\]$")
# "Name: Scanner spam-bypass" — a field line inside such a record. The field
# name may be lower-case: 22_exchange_connectors.txt writes "outbound:" and
# "inbound:", and requiring a capital meant its one record was not recognised
# as multi-line at all. Row counting then reported the tenant's single
# connector as three, on the customer-facing report as well as the technical
# one. Only a file that already carries "[n]" index lines can reach the
# multi-line branch, so relaxing this cannot pull a plain table into it.
_RECORD_FIELD_RE = re.compile(r"^[A-Za-z][A-Za-z ]{0,30}:\s")


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
    cols = [c for c in re.split(r"\s{2,}", stripped) if c]

    if len(cols) == 1:
        return (
            stripped == stripped.upper()
            and any(ch.isalpha() for ch in stripped)
            and not any(ch.isdigit() or ch in "@/:" for ch in stripped)
        )

    if not near_rule:
        return False

    return all(c[:1].isupper() and not any(ch.isdigit() or ch in "@/:" for ch in c) for c in cols)


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
    return bool(_HEADER_TOTAL_RE.match(stripped))


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
            in_table = True  # a heading or a column header; never a row
            continue
        if not in_table:
            continue
        if not s or s.startswith("==="):
            in_table = False  # blank line or frame ends the table
            continue
        if s.startswith("---"):
            continue  # the rule under a header, or a divider
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
        cause = "output may be truncated" if rows < declared else "non-record lines may be counted"
        log.warning(
            "Section banner declares %d record(s) but %d row(s) are present — "
            "using the row count; %s",
            declared,
            rows,
            cause,
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
    for name, key in (("60_fortigate_audit.txt", "fortigate"), ("61_unifi_audit.txt", "unifi")):
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
                name,
                exc,
            )
    return result
