"""Sections 06 & 07 — Groups and Admin Roles."""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient

_GLOBAL_ADMIN_ROLE = "Company Administrator"  # display name in Graph
_GA_WARN_THRESHOLD = 5


def _group_type(group: dict) -> str:
    gtypes   = group.get("groupTypes") or []
    security = group.get("securityEnabled", False)
    mail     = group.get("mailEnabled", False)
    rule     = group.get("membershipRule")

    if "Unified" in gtypes:
        return "Microsoft 365"
    if rule:
        return "Dynamic"
    if security and not mail:
        return "Security"
    if mail and not security:
        return "Distribution"
    return "Other"


class GroupsSection(BaseSection):
    name = "Groups"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            groups = await self.graph.get_all(
                "groups",
                params={
                    "$select": "id,displayName,groupTypes,securityEnabled,mailEnabled,membershipRule",
                    "$top":    "999",
                },
            )

            header = f"  {'Group Name':<50} {'Type':<16} {'Members':>8}"
            lines = [
                "=" * 80,
                f"  GROUPS  ({len(groups)} total)",
                "=" * 80,
                header,
                "  " + "-" * 76,
            ]

            _consistency_hdr = {"ConsistencyLevel": "eventual"}

            for g in groups:
                gid  = g.get("id", "")
                name = (g.get("displayName") or "")[:50]
                gtype = _group_type(g)
                is_dynamic = "DynamicMembership" in (g.get("groupTypes") or []) or bool(g.get("membershipRule"))

                # Fetch member count
                # Dynamic groups need /transitiveMembers; ConsistencyLevel must be an HTTP header.
                member_count = "N/A"
                primary_endpoint = "transitiveMembers" if is_dynamic else "members"
                fallback_endpoint = "members" if is_dynamic else "transitiveMembers"

                try:
                    resp = await self.graph.get(
                        f"groups/{gid}/{primary_endpoint}/$count",
                        extra_headers=_consistency_hdr,
                    )
                    if isinstance(resp, int):
                        member_count = str(resp)
                    elif isinstance(resp, dict) and "value" in resp:
                        member_count = str(resp["value"])
                except Exception:
                    pass

                # Fallback if primary returned 0 or N/A
                if member_count in ("N/A", "0"):
                    try:
                        resp = await self.graph.get(
                            f"groups/{gid}/{fallback_endpoint}/$count",
                            extra_headers=_consistency_hdr,
                        )
                        if isinstance(resp, int) and resp > 0:
                            member_count = str(resp)
                        elif isinstance(resp, dict) and int(resp.get("value", 0)) > 0:
                            member_count = str(resp["value"])
                    except Exception:
                        pass

                lines.append(f"  {name:<50} {gtype:<16} {member_count:>8}")

            lines += ["=" * 80, ""]
            self._save("06_groups.txt", "\n".join(lines))
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result


class AdminRolesSection(BaseSection):
    name = "Admin Roles"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None, users_ref: list | None = None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph
        self._users_ref = users_ref or []
        # Populated during collect() and read by IdentitySecuritySection's
        # break-glass check, which runs later in the same sequential pass.
        # Mutated in place rather than reassigned, so the reference handed to
        # that section at construction stays valid — the same idiom as
        # UsersSection.users.
        self.global_admin_ids: list[str] = []

    def _get_last_signin(self, upn: str) -> str:
        """Look up last sign-in from the users list (already fetched by UsersSection)."""
        upn_lower = upn.lower()
        for u in self._users_ref:
            if (u.get("userPrincipalName") or "").lower() == upn_lower:
                activity = u.get("signInActivity") or {}
                interactive = activity.get("lastSignInDateTime") or ""
                non_interactive = activity.get("lastNonInteractiveSignInDateTime") or ""
                last = interactive or non_interactive
                if last:
                    return last[:16].replace("T", " ")  # "2026-03-20 14:30"
                return "Aldri"
        return ""

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            # No $top: /directoryRoles supports only $select, $filter (eq) and
            # $expand, and rejects anything else with 400 — which took the whole
            # Admin Roles section down. It returns just the roles activated in
            # the tenant, a short list with no paging, so there is nothing to
            # page through anyway. The members call below is a directoryObject
            # collection and does support it.
            roles = await self.graph.get_all("directoryRoles")

            has_signin = bool(self._users_ref)
            hdr = f"  {'Role':<40} {'Display Name':<30} {'UPN':<45}"
            if has_signin:
                hdr += f" {'Siste innlogging'}"

            lines = [
                "=" * 130,
                "  ADMIN ROLE ASSIGNMENTS",
                "=" * 130,
                hdr,
                "  " + "-" * 126,
            ]

            global_admin_count = 0

            for role in roles:
                role_id   = role.get("id", "")
                role_name = role.get("displayName", "Unknown Role")

                try:
                    members = await self.graph.get_all(
                        f"directoryRoles/{role_id}/members",
                        params={"$top": "999"},
                    )
                except Exception as ex:
                    lines.append(
                        f"  {role_name:<40} {'N/A — ' + str(ex)[:50]}"
                    )
                    self._warn(
                        f"Members fetch failed for role '{role_name}': {ex}"
                    )
                    continue

                if not members:
                    continue

                for m in members:
                    display = (m.get("displayName") or "")[:30]
                    upn     = m.get("userPrincipalName") or m.get("id") or ""
                    # Truncate every field to its column width, the way the
                    # display name already was. A role name longer than 40
                    # characters ("Azure Information Protection Administrator"
                    # is 42) padded to 40 emits *no* separator, so the report's
                    # column offsets shift and the role and the user run into
                    # one field with nothing left to tell them apart.
                    line = f"  {role_name[:40]:<40} {display:<30} {upn[:45]:<45}"
                    if has_signin:
                        last_signin = self._get_last_signin(upn)
                        line += f" {last_signin}"
                    lines.append(line)
                    if role_name in ("Global Administrator", "Company Administrator"):
                        global_admin_count += 1
                        member_id = m.get("id")
                        if member_id and member_id not in self.global_admin_ids:
                            self.global_admin_ids.append(member_id)

            lines += ["=" * 130, ""]
            self._save("07_admin_roles.txt", "\n".join(lines))

            if global_admin_count > _GA_WARN_THRESHOLD:
                self._warn(
                    f"Found {global_admin_count} Global Administrators "
                    f"(threshold: {_GA_WARN_THRESHOLD})"
                )

            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result
