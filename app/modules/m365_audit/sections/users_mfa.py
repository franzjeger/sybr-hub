"""Sections 03 & 04 — Users and MFA Methods."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient

logger = logging.getLogger(__name__)

# Friendly labels for @odata.type values
_METHOD_LABELS: dict[str, str] = {
    "#microsoft.graph.phoneAuthenticationMethod":             "Phone (SMS/Call)",
    "#microsoft.graph.microsoftAuthenticatorAuthenticationMethod": "Authenticator App",
    "#microsoft.graph.fido2AuthenticationMethod":             "FIDO2 Key",
    "#microsoft.graph.windowsHelloForBusinessAuthenticationMethod": "Windows Hello",
    "#microsoft.graph.emailAuthenticationMethod":             "Email OTP",
    "#microsoft.graph.temporaryAccessPassAuthenticationMethod": "Temp Access Pass",
    "#microsoft.graph.softwareOathAuthenticationMethod":      "OATH TOTP",
    "#microsoft.graph.passwordAuthenticationMethod":          "Password",
}


def _method_label(odata_type: str) -> str:
    return _METHOD_LABELS.get(odata_type, odata_type.split(".")[-1])


class UsersSection(BaseSection):
    name = "Users"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph
        self.users: list[dict] = []

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            select = (
                "id,displayName,userPrincipalName,accountEnabled,"
                "createdDateTime,lastPasswordChangeDateTime,assignedLicenses,"
                "userType,onPremisesSyncEnabled,jobTitle,department,mail,"
                "mobilePhone,usageLocation,passwordPolicies,signInActivity"
            )
            fetched = await self.graph.get_all(
                "users",
                params={"$select": select, "$top": "999"},
            )
            # Mutate in place so MFASection's reference stays valid
            self.users.clear()
            self.users.extend(fetched)

            total    = len(self.users)
            enabled  = sum(1 for u in self.users if u.get("accountEnabled"))
            disabled = total - enabled
            guests   = sum(1 for u in self.users if u.get("userType") == "Guest")
            hybrid   = sum(1 for u in self.users if u.get("onPremisesSyncEnabled"))
            cloud    = total - hybrid

            # ── Detail file ───────────────────────────────────────────────────
            header = (
                f"  {'Display Name':<35} {'UPN':<45} {'Enabled':>7} "
                f"{'Type':<8} {'Lic':>3} {'Sync':>4} {'Dept'}"
            )
            lines = [
                "=" * 120,
                "  USER INVENTORY",
                "=" * 120,
                header,
                "  " + "-" * 116,
            ]
            for u in self.users:
                name    = (u.get("displayName") or "")[:35]
                upn     = (u.get("userPrincipalName") or "")[:45]
                enabled_str = "Yes" if u.get("accountEnabled") else "No"
                utype   = u.get("userType") or "Member"
                lic_cnt = len(u.get("assignedLicenses") or [])
                synced  = "Yes" if u.get("onPremisesSyncEnabled") else "No"
                dept    = (u.get("department") or "")[:30]
                lines.append(
                    f"  {name:<35} {upn:<45} {enabled_str:>7} "
                    f"{utype:<8} {lic_cnt:>3} {synced:>4}  {dept}"
                )
            lines += ["=" * 120, ""]
            self._save("03_users.txt", "\n".join(lines))

            # ── Count file ────────────────────────────────────────────────────
            count_lines = [
                "=" * 40,
                "  USER COUNT SUMMARY",
                "=" * 40,
                f"  Total users    : {total}",
                f"  Enabled        : {enabled}",
                f"  Disabled       : {disabled}",
                f"  Guest accounts : {guests}",
                f"  Cloud-only     : {cloud}",
                f"  Hybrid (synced): {hybrid}",
                "=" * 40,
                "",
            ]
            self._save("03_users_count.txt", "\n".join(count_lines))
            self._detect_stale_accounts()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result


    def _detect_stale_accounts(self) -> None:
        """Identify enabled Member accounts with no sign-in in 90+ days."""
        _STALE_DAYS = 90
        now = datetime.now(timezone.utc)

        enabled_members = [
            u for u in self.users
            if u.get("accountEnabled") and u.get("userType", "Member") == "Member"
        ]

        # Check whether signInActivity data is available at all
        has_any_sign_in_data = any(
            u.get("signInActivity") for u in enabled_members
        )

        stale: list[dict] = []
        for u in enabled_members:
            activity = u.get("signInActivity") or {}
            last_interactive = activity.get("lastSignInDateTime")
            last_non_interactive = activity.get("lastNonInteractiveSignInDateTime")

            # Use interactive sign-in as primary, non-interactive as fallback
            last_str = last_interactive or last_non_interactive
            if last_str:
                try:
                    last_dt = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
                except ValueError:
                    last_dt = None
            else:
                last_dt = None

            if last_dt is not None:
                days_inactive = (now - last_dt).days
                if days_inactive < _STALE_DAYS:
                    continue
            else:
                days_inactive = None  # never signed in

            is_licensed = bool(u.get("assignedLicenses"))
            stale.append({
                "name": (u.get("displayName") or "")[:35],
                "upn": (u.get("userPrincipalName") or "")[:45],
                "last_sign_in": last_dt,
                "days_inactive": days_inactive,
                "licensed": is_licensed,
            })

        # Build output
        lines = [
            "=" * 120,
            f"  STALE ACCOUNT DETECTION  (inactive >= {_STALE_DAYS} days or never signed in)",
            "=" * 120,
            "",
        ]

        if not has_any_sign_in_data:
            lines.append(
                "  NOTE: signInActivity data is null for all users. This field requires"
            )
            lines.append(
                "  at minimum a Microsoft Entra ID P1 (formerly Azure AD Premium P1) license."
            )
            lines.append(
                "  Unable to detect stale accounts."
            )
            lines += ["", "=" * 120, ""]
            self._save("03b_stale_accounts.txt", "\n".join(lines))
            return

        lines.append(f"  Stale accounts found: {len(stale)}")
        lines.append("")

        if stale:
            header = (
                f"  {'Display Name':<35} {'UPN':<45} {'Last Sign-In':<22} "
                f"{'Days':>5} {'Licensed':>8}"
            )
            lines.append(header)
            lines.append("  " + "-" * 116)

            for s in stale:
                last_str = (
                    s["last_sign_in"].strftime("%Y-%m-%d %H:%M")
                    if s["last_sign_in"]
                    else "Never"
                )
                days_str = str(s["days_inactive"]) if s["days_inactive"] is not None else "N/A"
                lic_str = "Yes" if s["licensed"] else "No"
                lines.append(
                    f"  {s['name']:<35} {s['upn']:<45} {last_str:<22} "
                    f"{days_str:>5} {lic_str:>8}"
                )

        lines += ["", "=" * 120, ""]
        self._save("03b_stale_accounts.txt", "\n".join(lines))

        # Warn about licensed stale accounts (wasted licenses)
        licensed_stale = [s for s in stale if s["licensed"]]
        if licensed_stale:
            self._warn(
                f"{len(licensed_stale)} stale account(s) still have licenses assigned (wasted licenses)"
            )
            warn_lines = [
                "=" * 120,
                "  WARNING: LICENSED STALE ACCOUNTS (potential wasted licenses)",
                "=" * 120,
                "",
                f"  {len(licensed_stale)} enabled account(s) with licenses have not signed in for "
                f"{_STALE_DAYS}+ days (or never).",
                "",
                f"  {'Display Name':<35} {'UPN':<45} {'Last Sign-In':<22} {'Days':>5}",
                "  " + "-" * 108,
            ]
            for s in licensed_stale:
                last_str = (
                    s["last_sign_in"].strftime("%Y-%m-%d %H:%M")
                    if s["last_sign_in"]
                    else "Never"
                )
                days_str = str(s["days_inactive"]) if s["days_inactive"] is not None else "N/A"
                warn_lines.append(
                    f"  {s['name']:<35} {s['upn']:<45} {last_str:<22} {days_str:>5}"
                )
            warn_lines += ["", "=" * 120, ""]
            self._save("03c_stale_accounts_WARN.txt", "\n".join(warn_lines))


def _policy_enforces_mfa(policy: dict) -> bool:
    """Return True if a CA policy enforces MFA (enabled + mfa control or auth strength)."""
    if policy.get("state") != "enabled":
        return False
    grant = policy.get("grantControls") or {}
    built_in = grant.get("builtInControls") or []
    if "mfa" in built_in:
        return True
    if grant.get("authenticationStrength"):
        return True
    return False


class MFASection(BaseSection):
    name = "MFA Methods"

    def __init__(
        self,
        out_dir: Path,
        graph: GraphClient,
        users: list[dict],
        progress_cb=None,
        concurrency: int = 10,
        ca_section=None,
    ):
        super().__init__(out_dir, progress_cb)
        self.graph       = graph
        self.users       = users
        self.concurrency = concurrency
        self._ca_section = ca_section  # reference to CA section; read .policies at runtime
        # Set of user IDs excluded from MFA-enforcing CA policies (incl. exclude
        # groups' members). Populated in place when this section runs, and shared
        # by reference with the break-glass check, which previously always saw an
        # empty set and reported "cannot confirm" over data we had (review, F8).
        self.mfa_excluded_ids: set[str] = set()

    @property
    def ca_policies(self) -> list[dict]:
        """Read CA policies from the CA section at runtime (after it has collected)."""
        if self._ca_section is not None:
            return self._ca_section.policies
        return []

    async def _get_methods(self, user_id: str) -> Optional[list[str]]:
        """Return this user's registered MFA methods, or None if unknown.

        None means the lookup failed — throttling, a transient 5xx, a missing
        permission. It is deliberately distinct from ``[]`` ("this user has no
        methods registered"), because collapsing the two is what turns a
        throttled audit into a page of users falsely reported as having no MFA.
        The Graph client raises rather than returning empty for exactly this
        reason; swallowing that here would undo it at the call site.
        """
        try:
            data    = await self.graph.get(f"users/{user_id}/authentication/methods")
            methods = data.get("value", [])
            return [
                _method_label(m.get("@odata.type", ""))
                for m in methods
                if m.get("@odata.type") != "#microsoft.graph.passwordAuthenticationMethod"
            ]
        except Exception as e:
            logger.warning("Could not read auth methods for user %s: %s", user_id, e)
            return None

    async def _analyse_ca_policies(self) -> tuple[
        list[dict], set[str], set[str], dict[str, list[str]], dict[str, dict]
    ]:
        """Analyse CA policies for MFA enforcement.

        Returns:
            mfa_policies  – list of CA policy dicts that enforce MFA
            covered_ids   – set of user IDs covered by group-based MFA CA policies
            excluded_ids  – set of user IDs explicitly excluded from MFA CA policies
            group_names   – mapping of group ID → list of member display names
            group_info    – mapping of group ID → group metadata (for dynamic groups)
        """
        mfa_policies: list[dict] = [
            p for p in self.ca_policies if _policy_enforces_mfa(p)
        ]

        if not mfa_policies:
            return mfa_policies, set(), set(), {}, {}

        # Collect all include/exclude group IDs across MFA policies
        include_group_ids: set[str] = set()
        exclude_group_ids: set[str] = set()
        all_users_targeted = False

        for policy in mfa_policies:
            conditions = policy.get("conditions") or {}
            users_cond = conditions.get("users") or {}
            inc_users = users_cond.get("includeUsers") or []
            if "All" in inc_users:
                all_users_targeted = True
            for gid in (users_cond.get("includeGroups") or []):
                include_group_ids.add(gid)
            for gid in (users_cond.get("excludeGroups") or []):
                exclude_group_ids.add(gid)

        # Fetch members from include and exclude groups concurrently
        all_group_ids = include_group_ids | exclude_group_ids
        group_members: dict[str, list[dict]] = {}
        group_names: dict[str, list[str]] = {}

        # Fetch group info FIRST so we know which groups are dynamic
        group_info: dict[str, dict] = {}
        if all_group_ids:
            sem = asyncio.Semaphore(self.concurrency)

            async def fetch_group_info(gid: str) -> tuple[str, dict]:
                async with sem:
                    info = await self.graph.get(
                        f"groups/{gid}",
                        params={"$select": "displayName,groupTypes,membershipRule"},
                    )
                return gid, info

            info_results = await asyncio.gather(
                *[fetch_group_info(gid) for gid in all_group_ids],
                return_exceptions=True,
            )
            for result in info_results:
                if isinstance(result, Exception):
                    continue
                gid, info = result
                group_info[gid] = info

        def _is_dynamic(gid: str) -> bool:
            info = group_info.get(gid, {})
            return "DynamicMembership" in (info.get("groupTypes") or [])

        if all_group_ids:
            sem = asyncio.Semaphore(self.concurrency)
            _member_select = {"$select": "id,displayName,userPrincipalName"}

            async def fetch_group(gid: str) -> tuple[str, list[dict]]:
                """Fetch group members with dynamic-group awareness.

                Dynamic groups (membershipRule-based) often return 0 from
                /members; /transitiveMembers is the correct endpoint for them.
                We try the best endpoint first, then fall back to the other.
                """
                async with sem:
                    dynamic = _is_dynamic(gid)
                    # Choose primary and fallback endpoints
                    primary  = "transitiveMembers" if dynamic else "members"
                    fallback = "members" if dynamic else "transitiveMembers"

                    members: list[dict] = []
                    try:
                        members = await self.graph.get_all(
                            f"groups/{gid}/{primary}",
                            params={**_member_select},
                        )
                    except Exception:
                        pass

                    # If primary returned nothing, try the other endpoint
                    if not members:
                        try:
                            members = await self.graph.get_all(
                                f"groups/{gid}/{fallback}",
                                params={**_member_select},
                            )
                        except Exception:
                            pass

                return gid, members

            group_results = await asyncio.gather(
                *[fetch_group(gid) for gid in all_group_ids],
                return_exceptions=True,
            )
            for result in group_results:
                if isinstance(result, Exception):
                    continue
                gid, members = result
                group_members[gid] = members
                group_names[gid] = [
                    m.get("displayName") or m.get("userPrincipalName") or m.get("id", "")
                    for m in members
                ]

        # Ensure every group ID has an entry even if all fetches failed
        for gid in all_group_ids:
            if gid not in group_members:
                group_members[gid] = []
                group_names[gid] = []

        # Build covered / excluded user ID sets
        covered_ids: set[str] = set()
        excluded_ids: set[str] = set()

        if all_users_targeted:
            # All users are included; covered = everyone
            covered_ids = {u["id"] for u in self.users if u.get("id")}

        for gid in include_group_ids:
            for m in group_members.get(gid, []):
                mid = m.get("id")
                if mid:
                    covered_ids.add(mid)

        for gid in exclude_group_ids:
            for m in group_members.get(gid, []):
                mid = m.get("id")
                if mid:
                    excluded_ids.add(mid)

        # Collect explicit user-level exclusions
        for policy in mfa_policies:
            conditions = policy.get("conditions") or {}
            users_cond = conditions.get("users") or {}
            for uid in (users_cond.get("excludeUsers") or []):
                excluded_ids.add(uid)

        return mfa_policies, covered_ids, excluded_ids, group_names, group_info

    def _save_ca_analysis(
        self,
        mfa_policies: list[dict],
        covered_ids: set[str],
        excluded_ids: set[str],
        group_names: dict[str, list[str]],
        group_info: dict[str, dict] | None = None,
    ) -> None:
        """Write 04b_mfa_ca_analysis.txt with CA MFA enforcement details."""
        lines = [
            "=" * 120,
            "  CONDITIONAL ACCESS — MFA ENFORCEMENT ANALYSIS",
            "=" * 120,
            "",
        ]

        if not mfa_policies:
            lines.append("  No Conditional Access policies that enforce MFA were found.")
            lines += ["", "=" * 120, ""]
            self._save("04b_mfa_ca_analysis.txt", "\n".join(lines))
            return

        # ── Section 1: Policies that enforce MFA ────────────────────────────
        lines.append(f"  MFA-ENFORCING POLICIES ({len(mfa_policies)})")
        lines.append("  " + "-" * 80)
        for p in mfa_policies:
            name = p.get("displayName") or p.get("id") or "(unnamed)"
            state = p.get("state", "unknown")
            grant = p.get("grantControls") or {}
            controls = ", ".join(grant.get("builtInControls") or [])
            has_strength = "Yes" if grant.get("authenticationStrength") else "No"
            lines.append(f"  Policy : {name}")
            lines.append(f"    State            : {state}")
            lines.append(f"    Built-in controls: {controls or '(none)'}")
            lines.append(f"    Auth strength    : {has_strength}")

            conditions = p.get("conditions") or {}
            users_cond = conditions.get("users") or {}
            inc_users = users_cond.get("includeUsers") or []
            inc_groups = users_cond.get("includeGroups") or []
            exc_users = users_cond.get("excludeUsers") or []
            exc_groups = users_cond.get("excludeGroups") or []

            lines.append(f"    Include users    : {', '.join(inc_users) if inc_users else '(none)'}")
            lines.append(f"    Include groups   : {', '.join(inc_groups) if inc_groups else '(none)'}")
            lines.append(f"    Exclude users    : {', '.join(exc_users) if exc_users else '(none)'}")
            lines.append(f"    Exclude groups   : {', '.join(exc_groups) if exc_groups else '(none)'}")
            lines.append("")

        # ── Section 2: Targeted groups and their members ────────────────────
        gi = group_info or {}
        if group_names or gi:
            lines.append("  TARGETED GROUPS AND MEMBERS")
            lines.append("  " + "-" * 80)
            all_gids = set(group_names.keys()) | set(gi.keys())
            for gid in sorted(all_gids):
                info = gi.get(gid, {})
                display_name = info.get("displayName") or gid
                group_types = info.get("groupTypes") or []
                is_dynamic = "DynamicMembership" in group_types
                names = group_names.get(gid, [])
                type_label = " (Dynamic)" if is_dynamic else ""
                lines.append(f"  Group: {display_name}{type_label}  ({len(names)} member(s))")
                lines.append(f"    ID: {gid}")
                if is_dynamic and len(names) == 0:
                    rule = info.get("membershipRule") or "(no rule available)"
                    lines.append(f"    Membership Rule: {rule}")
                    lines.append("    NOTE: Dynamic group — 0 members resolved; rule shown above.")
                for n in sorted(names):
                    lines.append(f"    - {n}")
                lines.append("")

        # ── Section 3: User coverage summary ────────────────────────────────
        lines.append("  USER COVERAGE SUMMARY")
        lines.append("  " + "-" * 80)

        # Build lookup from user id → upn
        user_lookup = {
            u["id"]: u.get("userPrincipalName") or u.get("displayName") or u["id"]
            for u in self.users if u.get("id")
        }

        covered_not_excluded = covered_ids - excluded_ids
        lines.append(f"  Users covered by CA MFA (incl. groups) : {len(covered_ids)}")
        lines.append(f"  Users excluded from CA MFA             : {len(excluded_ids)}")
        lines.append(f"  Effectively covered (covered − excluded): {len(covered_not_excluded)}")
        lines.append("")

        if covered_not_excluded:
            lines.append("  Effectively covered users:")
            for uid in sorted(covered_not_excluded):
                label = user_lookup.get(uid, uid)
                lines.append(f"    - {label}")
            lines.append("")

        not_covered = set(user_lookup.keys()) - covered_not_excluded
        if not_covered:
            lines.append(f"  Users NOT covered by CA MFA ({len(not_covered)}):")
            for uid in sorted(not_covered):
                label = user_lookup.get(uid, uid)
                lines.append(f"    - {label}")
            lines.append("")

        lines += ["=" * 120, ""]
        self._save("04b_mfa_ca_analysis.txt", "\n".join(lines))

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            # Only check enabled Member users
            targets = [
                u for u in self.users
                if u.get("accountEnabled") and u.get("userType", "Member") == "Member"
            ]

            sem = asyncio.Semaphore(self.concurrency)

            async def bounded_fetch(user: dict) -> tuple[dict, list[str]]:
                async with sem:
                    methods = await self._get_methods(user["id"])
                return user, methods

            results = await asyncio.gather(*[bounded_fetch(u) for u in targets])

            # ── CA policy analysis ──────────────────────────────────────────
            mfa_policies, covered_ids, excluded_ids, group_names, group_info = (
                await self._analyse_ca_policies()
            )
            # Share the excluded set (in place) so the break-glass check can
            # correlate Global Admins against it instead of guessing (F8).
            self.mfa_excluded_ids.clear()
            self.mfa_excluded_ids.update(excluded_ids)

            header = (
                f"  {'Display Name':<35} {'UPN':<45} {'MFA':>5} {'CA':>4} {'CA EXCL':>8}  Methods"
            )
            lines = [
                "=" * 130,
                "  MFA METHOD REPORT",
                "=" * 130,
                header,
                "  " + "-" * 126,
            ]
            # Three states, not two: a user whose lookup failed is *unknown*,
            # not "no MFA". Bucketing unknowns with the failures is what turns
            # a throttled run into a page of false findings — and this metric
            # reaches the customer-facing report and the IT Glue asset.
            no_mfa_users = []
            unknown_users = []
            # Structured records alongside the text table. The report used to
            # recover these numbers by splitting the rendered table on runs of
            # two or more spaces, which silently breaks the moment a display
            # name reaches the column width and its padding disappears — every
            # field then shifts by one and the headline MFA percentage is
            # wrong in either direction. The table stays, for humans; the
            # figures come from here.
            records: list[dict] = []
            for user, methods in results:
                name = (user.get("displayName") or "")[:35]
                upn  = (user.get("userPrincipalName") or "")[:45]
                uid  = user.get("id", "")
                if methods is None:
                    mfa_str, method_str = "?", "(lookup failed)"
                    unknown_users.append(upn)
                else:
                    mfa_str = "YES" if methods else "NO"
                    method_str = ", ".join(methods) if methods else "(none)"
                    if not methods:
                        no_mfa_users.append(upn)
                ca_str = "YES" if uid in covered_ids else "NO"
                ca_excl_str = "YES" if uid in excluded_ids else "NO"
                records.append({
                    "display_name": user.get("displayName") or "",
                    "upn": user.get("userPrincipalName") or "",
                    # None means "could not be determined", which is not the
                    # same as False and must never be counted as "no MFA".
                    "mfa_registered": None if methods is None else bool(methods),
                    "ca_covered": uid in covered_ids,
                    "ca_excluded": uid in excluded_ids,
                    "methods": list(methods or []),
                })
                lines.append(
                    f"  {name:<35} {upn:<45} {mfa_str:>5} {ca_str:>4} {ca_excl_str:>8}  {method_str}"
                )

            if unknown_users:
                lines += [
                    "",
                    f"  NOTE: {len(unknown_users)} user(s) marked '?' — their authentication",
                    "  methods could not be read (throttling, transient error or missing",
                    "  permission). They are NOT counted as lacking MFA. Re-run to resolve.",
                ]

            lines += ["=" * 130, ""]

            if no_mfa_users:
                self._warn(
                    f"{len(no_mfa_users)} enabled member user(s) have no MFA methods registered"
                )
            if unknown_users:
                self._warn(
                    f"MFA status could not be determined for {len(unknown_users)} user(s) — "
                    f"coverage figures are incomplete"
                )

            self._save("04_mfa_methods.txt", "\n".join(lines))
            self._save("04_mfa_methods.json", json.dumps({"users": records}, indent=1))

            # ── Save CA analysis report ─────────────────────────────────────
            self._save_ca_analysis(mfa_policies, covered_ids, excluded_ids, group_names, group_info)

            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result
