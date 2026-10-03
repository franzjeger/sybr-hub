"""Parsers for users, MFA, Conditional Access, admin roles, groups and sign-ins."""

from __future__ import annotations

import contextlib
import json
import re

from app.modules.base import SectionResult
from app.reports.evidence import _evidence_unavailable
from app.reports.parsers.common import _sidecar


def _parse_user_counts(text: str, sidecar: dict | None = None) -> dict:
    """The user counts, from 03_users_count.json when the run has it, else the text."""
    result = {
        "total": 0,
        "enabled": 0,
        "disabled": 0,
        "guests": 0,
        "hybrid": 0,
        "cloud": 0,
        "has_data": False,
    }
    if sidecar is not None:
        for field in ("total", "enabled", "disabled", "guests", "hybrid", "cloud"):
            result[field] = int(sidecar.get(field) or 0)
        result["has_data"] = result["total"] > 0 or result["enabled"] > 0
        return result
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
    ca_analysis: dict | None = None,
) -> dict:
    """Parse MFA coverage from mfa_methods.txt and CA analysis.

    A user is 'MFA covered' if they have MFA methods registered
    OR are covered by a Conditional Access policy that enforces MFA.
    ``ca_analysis`` is 04b_mfa_ca_analysis.json; without it the CA analysis
    figures are read from the text.
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
    if ca_analysis is not None:
        # The same precedence as the text below: effectively covered, else covered.
        ca_analysis_covered = int(ca_analysis.get("effectively_covered") or 0) or int(
            ca_analysis.get("covered") or 0
        )
        ca_analysis_excluded = int(ca_analysis.get("excluded") or 0)
        ca_analysis_not_covered = int(ca_analysis.get("not_covered") or 0)
    elif ca_analysis_text:
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


def _parse_admin_roles(text: str, sidecar: dict | None = None) -> dict:
    """Admin role assignments, from 07_admin_roles.json when the run has it.

    The table cuts role names to 40 characters, display names to 30 and UPNs
    to 45; a cut UPN matched no account in the MFA records, so a Global Admin
    with a long UPN was not recognised as one there. The text is read only for
    runs from before the sidecar.
    """
    roles: list[dict] = [
        {
            "role": a.get("role") or "",
            "user": a.get("display_name") or "",
            # The table's third column: the UPN, or the id of a member without one.
            "email": a.get("upn") or a.get("member_id") or "",
        }
        for a in (sidecar or {}).get("assignments") or []
    ]
    for line in [] if sidecar is not None else text.splitlines():
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


def _parse_groups(text: str, sidecar: dict | None = None) -> dict:
    """Parse 06_groups.txt into group metadata.

    From 06_groups.json when the run has it. Otherwise the collector writes a
    3-column table (Name, Type, Members) — accepts that as the primary format.
    A legacy pipe-delimited format is also accepted so historical audit runs
    still parse. Without the columnar branch the report silently reported
    zero groups for every tenant.
    """
    groups: list[dict] = [
        {
            "name": g.get("name") or "",
            "type": g.get("type") or "",
            "members": g["members"] if isinstance(g.get("members"), int) else 0,
            "members_known": isinstance(g.get("members"), int),
        }
        for g in (sidecar or {}).get("groups") or []
        if g.get("name")
    ]
    for line in [] if sidecar is not None else text.splitlines():
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

    # Parse sign-in activity (05_signin_activity.txt), from its sidecar when the
    # run has one. A failed read writes no sidecar, so the text below then
    # explains the gap as before.
    signin_text = file_contents.get("05_signin_activity.txt", "")
    activity = _sidecar(file_contents, "05_signin_activity.txt")
    if activity is not None:
        named = [u for u in activity.get("users") or [] if u.get("upn")]
        result["total_signins"] = int(activity.get("events") or 0)
        result["unique_users"] = len({u["upn"].lower() for u in named})
        for u in named:
            key = u["upn"].lower()
            success_by_user[key] = success_by_user.get(key, 0) + int(u.get("success") or 0)
        result["has_data"] = True
    elif _evidence_unavailable(signin_text):
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
    failures = _sidecar(file_contents, "05b_signin_failures.txt")
    if failures is not None or not _evidence_unavailable(failure_text):
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

        # A run with the sidecar is read from it, below, and its text not at all.
        for line in [] if failures is not None else failure_text.splitlines():
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

        if failures is not None:
            # Sign-ins without a UPN count towards the total but are nobody's:
            # the text wrote them as "(unknown)", which the loop above took for
            # a failure reason and left out of the total.
            for u in failures.get("users") or []:
                if u.get("upn"):
                    failure_users[u["upn"]] = failure_users.get(u["upn"], 0) + int(
                        u.get("failures") or 0
                    )
            result["total_failures"] = int(failures.get("total_failures") or 0)
            error_code_rows = [
                {
                    "code": str(c.get("code")),
                    "reason": c.get("reason") or "",
                    "count": int(c.get("count") or 0),
                }
                for c in failures.get("error_codes") or []
            ]
            country_rows = [
                {"country": c.get("country") or "", "count": int(c.get("count") or 0)}
                for c in failures.get("countries") or []
            ]
            ip_rows = [
                {"ip": c.get("ip") or "", "count": int(c.get("count") or 0)}
                for c in failures.get("ips") or []
            ]

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
