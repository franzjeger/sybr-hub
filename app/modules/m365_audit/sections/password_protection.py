"""Section 31 — Entra ID Password Protection: Banned Passwords, Smart Lockout."""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class PasswordProtectionSection(BaseSection):
    name = "Password Protection"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_password_protection()
            await self._collect_smart_lockout()
            await self._collect_password_methods_policy()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Password Protection Settings ───────────────────────────────────────

    async def _collect_password_protection(self) -> None:
        # Fetch group settings that contain password protection config
        custom_banned = None
        lockout_threshold = None
        lockout_duration = None
        enforce_on_prem = None
        mode = None

        try:
            settings_list = await self.graph.get_all(
                "settings",
                params={"$top": "999"},
            )
        except Exception as ex:
            settings_list = []
            self._warn(f"Directory settings fetch failed: {ex}")

        for setting in settings_list:
            values = {
                v.get("name"): v.get("value")
                for v in setting.get("values", [])
            }
            if "BannedPasswordCheckOnPremisesMode" in values:
                mode = values.get("BannedPasswordCheckOnPremisesMode")
                enforce_on_prem = values.get("EnableBannedPasswordCheckOnPremises")
                custom_banned = values.get("BannedPasswordList")

        # Also try the dedicated password protection endpoint (beta)
        try:
            pp_data = await self.graph.get(
                "settings/passwords", beta=True
            )
        except Exception:
            pp_data = None

        # Try the authentication methods policy for password config
        try:
            auth_policy = await self.graph.get(
                "policies/authenticationMethodsPolicy"
            )
            password_config = None
            for cfg in auth_policy.get("authenticationMethodConfigurations", []):
                if cfg.get("id") == "Password" or "password" in cfg.get("@odata.type", "").lower():
                    password_config = cfg
                    break
        except Exception:
            auth_policy = None
            password_config = None

        lines = [
            "=" * 90,
            "  ENTRA ID PASSWORD PROTECTION",
            "=" * 90,
        ]

        if pp_data:
            lines += [
                f"  Custom Banned Passwords Enabled : {pp_data.get('enableCustomBannedPasswords', 'N/A')}",
                f"  Banned Password List            : {pp_data.get('bannedPasswordList', 'N/A')}",
                "",
            ]
        elif mode is not None:
            has_custom = bool(custom_banned) if custom_banned else False
            lines += [
                f"  Password Check Mode             : {mode}",
                f"  Enforce On-Premises             : {enforce_on_prem or 'N/A'}",
                f"  Custom Banned Passwords         : {'Configured' if has_custom else 'Not configured'}",
                "",
            ]
            if not has_custom:
                self._warn("Custom banned password list is not configured — consider adding org-specific terms")
        else:
            lines += [
                "  Password protection settings not found via directory settings.",
                "  This may indicate the tenant is using default settings only.",
                "  NOTE: Custom banned passwords require Microsoft Entra ID P1+ "
                "(formerly Azure AD Premium P1).",
                "",
            ]
            self._warn("Custom banned password list is not configured — consider adding org-specific terms")

        if password_config:
            state = password_config.get("state", "N/A")
            lines += [
                "  Password Authentication Method:",
                f"    State                         : {state}",
                "",
            ]

        lines += ["=" * 90, ""]
        self._save("31_password_protection.txt", "\n".join(lines))

    # ── Smart Lockout ──────────────────────────────────────────────────────

    async def _collect_smart_lockout(self) -> None:
        # Fetch security defaults status
        try:
            sec_defaults = await self.graph.get(
                "policies/identitySecurityDefaultsEnforcementPolicy"
            )
        except Exception as ex:
            err = str(ex)
            if any(k in err for k in ("404", "Not Found")):
                sec_defaults = None
            else:
                self._save("31b_smart_lockout.txt", f"Error: {ex}\n")
                return

        lines = [
            "=" * 90,
            "  SMART LOCKOUT & SECURITY DEFAULTS",
            "=" * 90,
        ]

        if sec_defaults:
            enabled = sec_defaults.get("isEnabled", "N/A")
            lines += [
                f"  Security Defaults Enabled       : {enabled}",
                "",
                "  NOTE: When Security Defaults are enabled, smart lockout is active",
                "  with Microsoft-managed thresholds. Custom lockout settings require",
                "  Microsoft Entra ID Premium and Security Defaults to be disabled.",
                "",
            ]
        else:
            lines += [
                "  Security Defaults               : Not available",
                "",
            ]

        # Try to get named locations (useful context for lockout)
        try:
            locations = await self.graph.get_all(
                "identity/conditionalAccess/namedLocations",
                params={"$top": "999"},
            )
            if locations:
                lines += [
                    f"  Named Locations ({len(locations)}):",
                    f"    {'Name':<45} {'Type':<25} {'Trusted'}",
                    "    " + "-" * 75,
                ]
                for loc in locations:
                    name = (loc.get("displayName") or "")[:45]
                    loc_type = (loc.get("@odata.type") or "").split(".")[-1][:25]
                    trusted = loc.get("isTrusted", "N/A")
                    lines.append(f"    {name:<45} {loc_type:<25} {trusted}")
                lines.append("")
        except Exception as ex:
            self._warn(f"Named locations fetch failed (lockout section): {ex}")

        lines += ["=" * 90, ""]
        self._save("31b_smart_lockout.txt", "\n".join(lines))

    # ── Password Methods Policy ────────────────────────────────────────────

    async def _collect_password_methods_policy(self) -> None:
        try:
            data = await self.graph.get(
                "policies/authenticationMethodsPolicy"
            )
        except Exception as ex:
            self._save("31c_password_methods_policy.txt", f"Error: {ex}\n")
            self._warn(f"Authentication methods policy fetch failed: {ex}")
            return

        configs = data.get("authenticationMethodConfigurations", [])

        # Focus on password-related and SSPR-relevant methods
        relevant_methods = []
        for cfg in configs:
            method_id = cfg.get("id", "")
            odata_type = cfg.get("@odata.type", "")
            method_name = odata_type.split(".")[-1].replace(
                "AuthenticationMethodConfiguration", ""
            ) or method_id
            state = cfg.get("state", "unknown")
            relevant_methods.append((method_name, state))

        lines = [
            "=" * 90,
            f"  AUTHENTICATION METHODS POLICY  ({len(relevant_methods)} methods)",
            "=" * 90,
            f"  {'Method':<50} {'State'}",
            "  " + "-" * 66,
        ]
        for method_name, state in relevant_methods:
            lines.append(f"  {method_name:<50} {state}")

        # SSPR policy info
        lines += [
            "",
            "  NOTE: Self-Service Password Reset (SSPR) configuration is managed",
            "  via the Azure Portal. Methods above determine which auth methods",
            "  are available for SSPR and MFA registration.",
        ]

        lines += ["=" * 90, ""]
        self._save("31c_password_methods_policy.txt", "\n".join(lines))
