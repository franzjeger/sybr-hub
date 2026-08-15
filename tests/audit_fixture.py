"""A synthetic but format-accurate audit output directory.

Every string here matches the shape the corresponding parser in
``app.reports.generator`` expects — verified by asserting each section comes
back ``has_data: True`` (see ``test_report_partial_audit.py``). The tenant it
describes is deliberately *healthy*: high MFA coverage, conditional access in
place, backups configured, no open WiFi. That is what makes it useful as a
baseline — any finding that appears when a file is removed from this set is a
finding manufactured by the absence, not by the data.

Keep it healthy. If you add a section here, add a genuinely compliant one.
"""

from __future__ import annotations

import json


def _mfa_table(rows: list[tuple[str, str, str, str, str, str]]) -> str:
    """Render the MFA table exactly as the collector does.

    Fixtures used to feed a pipe-delimited layout that no production code has
    ever emitted, so the suite validated a parser branch the product never
    reaches — which is how a defect that made the headline MFA percentage
    wrong survived ~870 passing tests. Mirror
    app/modules/m365_audit/sections/users_mfa.py instead, including its
    truncation to the column width.
    """
    header = f"  {'Display Name':<35} {'UPN':<45} {'MFA':>5} {'CA':>4} {'CA EXCL':>8}  Methods"
    lines = ["=" * 130, "  MFA METHOD REPORT", "=" * 130, header, "  " + "-" * 126]
    for name, upn, mfa, ca, excl, methods in rows:
        lines.append(
            f"  {name[:35]:<35} {upn[:45]:<45} {mfa:>5} {ca:>4} {excl:>8}  {methods}"
        )
    lines += ["=" * 130, ""]
    return "\n".join(lines)


def _admin_role_table(rows: list[tuple[str, str, str, str]]) -> str:
    """Render the admin-role table exactly as the collector does.

    Mirrors app/modules/m365_audit/sections/groups_roles.py, *including* the
    last-sign-in column it appends whenever the users list is available — the
    column that made the last field a timestamp rather than an email. Fixtures
    used a narrower home-made layout that happened to keep the email last, so
    the suite never saw the shift.
    """
    header = f"  {'Role':<40} {'Display Name':<30} {'UPN':<45} Siste innlogging"
    lines = ["=" * 130, "  ADMIN ROLE ASSIGNMENTS", "=" * 130, header, "  " + "-" * 126]
    for role, display, upn, signin in rows:
        lines.append(f"  {role[:40]:<40} {display[:30]:<30} {upn[:45]:<45} {signin}")
    lines += ["=" * 130, ""]
    return "\n".join(lines)


def _entry_block(title: str, entries: list[dict]) -> str:
    """Render a section block the way app/modules/m365_audit/sections/exchange.py does."""
    lines = ["=" * 80, f"  {title}  ({len(entries)} entries)", "=" * 80]
    if not entries:
        lines += ["  (none)", ""]
        return "\n".join(lines)
    for i, item in enumerate(entries, 1):
        lines.append(f"\n  [{i}]")
        for k, v in item.items():
            lines.append(f"    {k}: {v}")
    lines += ["", "=" * 80, ""]
    return "\n".join(lines)


def _mfa_json(rows: list[tuple[str, str, str, str, str, str]]) -> str:
    """The sidecar users_mfa.py writes beside the table, from the same rows.

    Production prefers this file — the table is fixed-width and a name at the
    column width shifts every later field. Feeding only the table meant the
    golden run and every sweep in test_report_partial_audit.py exercised the
    fallback parser while the product used this one.

    Built from the same tuples as _mfa_table so the two cannot drift, and
    without the table's truncation, which is the collector's behaviour: the
    JSON carries the untruncated displayName.
    """
    return json.dumps({"users": [
        {
            "display_name": name,
            "upn": upn,
            "mfa_registered": mfa == "YES",
            "ca_covered": ca == "YES",
            "ca_excluded": excl == "YES",
            "methods": [] if methods == "(none)" else [m.strip() for m in methods.split(",")],
        }
        for name, upn, mfa, ca, excl, methods in rows
    ]}, indent=1)


def _entra_device_table(rows: list[tuple[str, str, str, str, str, str, str]]) -> str:
    """Mirrors app/modules/m365_audit/sections/entra_devices.py."""
    header = (
        f"  {'Device Name':<35} {'OS':<14} {'OS Ver':<14} "
        f"{'Trust':<12} {'Managed':<8} {'Enabled':<8} Last Sign-in"
    )
    lines = [
        "=" * 120, f"  ENTRA REGISTERED DEVICES  ({len(rows)} total)", "=" * 120,
        header, "  " + "-" * 116,
    ]
    for name, os_name, ver, trust, managed, enabled, seen in rows:
        lines.append(
            f"  {name[:35]:<35} {os_name[:14]:<14} {ver[:14]:<14} "
            f"{trust[:12]:<12} {managed:<8} {enabled:<8} {seen[:19]}"
        )
    lines += ["=" * 120, ""]
    return "\n".join(lines)


def _usage_table(rows: list[tuple[str, str, str]]) -> str:
    """Mirrors app/modules/m365_audit/sections/usage_reports.py."""
    lines = [
        "=" * 110,
        f"  MICROSOFT 365 ACTIVE USERS  (last 90 days, {len(rows)} rows)",
        "=" * 110,
        f"  {'User':<45} {'Products':<28} Last activity",
        "  " + "-" * 106,
    ]
    for upn, products, last in rows:
        lines.append(f"  {upn[:45]:<45} {products[:28]:<28} {last}")
    lines += ["=" * 110, ""]
    return "\n".join(lines)


def _teams_table(rows: list[tuple[str, str, str, str]]) -> str:
    """Mirrors app/modules/m365_audit/sections/teams.py."""
    lines = [
        "=" * 100, f"  MICROSOFT TEAMS  ({len(rows)} total)", "=" * 100,
        f"  {'Team Name':<50} {'Visibility':<15} {'Mail':<40} {'Created'}",
        "  " + "-" * 96,
    ]
    for name, visibility, mail, created in rows:
        lines.append(f"  {name[:50]:<50} {visibility[:15]:<15} {mail[:40]:<40} {created[:19]}")
    lines += ["=" * 100, ""]
    return "\n".join(lines)


# The healthy tenant's users, rendered into both the table and its JSON
# sidecar. Thirty-seven with a registered method, one covered by Conditional
# Access alone — and that one's display name is exactly the 35-character
# column width, where the padding disappears and a whitespace-splitting reader
# merges it with the UPN.
_MFA_ROWS: list[tuple[str, str, str, str, str, str]] = [
    (f"User {i:02d}", f"user{i:02d}@acme.no", "YES", "YES", "NO", "Authenticator")
    for i in range(1, 38)
] + [
    ("Kristoffer Andreas Wilhelmsen Bergs", "user38@acme.no", "NO", "YES", "NO", "(none)"),
]


FULL_AUDIT: dict[str, str] = {
    # Cross-tenant access, configured rather than left on the system default,
    # with direct connect inbound closed.
    "18c_cross_tenant_access_policy.txt": (
        "=" * 70 + "\n"
        "  CROSS-TENANT ACCESS POLICY\n"
        + "=" * 70 + "\n"
        "  Default Settings:\n"
        "    B2B Collab Inbound     : allowed\n"
        "    B2B Collab Outbound    : allowed\n"
        "    B2B Direct Connect In  : blocked\n"
        "    System Default         : false\n"
        + "=" * 70 + "\n"
    ),
    # Baseline sign-in protection: Security Defaults off is the correct state
    # for a tenant running Conditional Access, which this one does.
    "31b_smart_lockout.txt": (
        "=" * 70 + "\n"
        "  SMART LOCKOUT & SECURITY DEFAULTS\n"
        + "=" * 70 + "\n"
        "  Security Defaults Enabled       : False\n"
        + "=" * 70 + "\n"
    ),
    "07d_access_reviews.txt": (
        "=" * 70 + "\n"
        "  ACCESS REVIEW DEFINITIONS  (2 total)\n"
        + "=" * 70 + "\n"
        "  Review Name              Status     Recurrence   Created\n"
        "  " + "-" * 66 + "\n"
        "  Guest access review      InProgress monthly      2026-01-01\n"
        "  Admin role review        InProgress quarterly    2026-01-01\n"
        + "=" * 70 + "\n"
    ),
    "25_onedrive_sharing.txt": (
        "=" * 70 + "\n"
        "  ONEDRIVE / SHAREPOINT EXTERNAL SHARING AUDIT\n"
        + "=" * 70 + "\n"
        "  Drives scanned       : 12\n"
        "  Total shared items   : 3\n"
        "  'Anyone' links       : 0\n"
        "  External user shares : 0\n"
        # A healthy synthetic tenant represents a scan that reached every
        # discovered drive and nested folder without exhausting its budget.
        "  Drives refused       : 0\n"
        "  Discovery failures   : 0\n"
        "  Folder failures      : 0\n"
        "  Folders examined     : 96\n"
        "  Items examined       : 1204\n"
        "  Graph requests used  : 121 of 1500\n"
        "  Scan scope           : complete (depth 3, max 40 folders per drive)\n"
        + "=" * 70 + "\n"
    ),
    "01_tenant.txt": (
        "TENANT INFORMATION\n"
        "==================\n"
        "Display Name: Acme AS\n"
        "Tenant ID: 00000000-0000-0000-0000-000000000001\n"
        "Primary Domain: acme.no\n"
    ),
    "02_licenses.txt": (
        "LICENSE OVERVIEW\n"
        "================\n"
        "SKU                        Used   Total\n"
        "SPE_E3                       38      40\n"
        "EMS                          38      40\n"
    ),
    "03_users_count.txt": (
        "USER COUNTS\n"
        "===========\n"
        "Total users: 40\n"
        "Enabled: 38\n"
        "Disabled: 2\n"
        "Guest accounts: 3\n"
        "Hybrid (synced): 0\n"
        "Cloud-only: 40\n"
    ),
    # 38 users, 37 with MFA registered, 1 covered by CA only → 100% effective.
    "04_mfa_methods.txt": _mfa_table(_MFA_ROWS),
    # The sidecar production actually reads. Same rows, so the two cannot
    # disagree about the tenant the way a hand-written pair would.
    "04_mfa_methods.json": _mfa_json(_MFA_ROWS),
    "04b_mfa_ca_analysis.txt": (
        "CONDITIONAL ACCESS MFA ANALYSIS\n"
        "===============================\n"
        "Policy 'Require MFA for all users' enforces MFA for 38 user(s).\n"
    ),
    "05_signin_activity.txt": (
        "SIGN-IN ACTIVITY (LAST 30 DAYS)\n"
        "===============================\n"
        "Total sign-ins: 4210\n"
        "Unique users: 38\n"
    ),
    "05b_signin_failures.txt": (
        "SIGN-IN FAILURES\n"
        "================\n"
        "User                  Reason                 Count\n"
        "user07@acme.no        Invalid password       3\n"
    ),
    "06_groups.txt": (
        "GROUPS\n"
        "======\n"
        "Name              Type          Members\n"
        "All Staff         Microsoft365  38\n"
        "IT Admins         Security      4\n"
    ),
    "11_intune_compliance_policies.txt": (
        "INTUNE COMPLIANCE POLICIES\n"
        "==========================\n"
        "Name                     Platform    Assigned\n"
        "Windows Baseline         Windows     Yes\n"
        "iOS Baseline             iOS         Yes\n"
    ),
    "07_admin_roles.txt": _admin_role_table([
        ("Global Administrator", "Ola Nordmann", "ola@acme.no", "2026-03-20 14:30"),
        ("Global Administrator", "Kari Nordmann", "kari@acme.no", "2026-03-19 09:05"),
        # Break-glass accounts are meant to sit unused; the collector writes
        # "Aldri" for them, which is another non-email final column.
        ("Global Administrator", "Break Glass", "bg@acme.no", "Aldri"),
        ("Security Administrator", "Per Hansen", "per@acme.no", "2026-03-21 08:00"),
    ]),
    "07b_pim_eligible_assignments.txt": (
        "PIM ELIGIBLE ROLE ASSIGNMENTS (4 total)\n"
        "=======================================\n"
        "Role                     User\n"
        "Global Administrator     ola@acme.no\n"
    ),
    "07c_emergency_access_check.txt": (
        "==========================================================================================\n"
        "  EMERGENCY / BREAK-GLASS ACCOUNT CHECK\n"
        "==========================================================================================\n"
        "  User (UPN)                                     MFA Registered  CA Excluded  Notes\n"
        "  ------------------------------------------------------------------------------------------\n"
        "  bg@acme.no                                                 NO          Yes  "
        "No MFA — potential break-glass; Excluded from CA — confirmed break-glass candidate\n"
        "  SUMMARY: break_glass_candidates=1 ca_exclusions_known=yes global_admins=1\n"
        "==========================================================================================\n"
    ),
    "08_conditional_access.txt": (
        "CONDITIONAL ACCESS POLICIES\n"
        "===========================\n"
        "[enabled   ] Require MFA for all users\n"
        "[enabled   ] Block legacy authentication\n"
        "[enabled   ] Require compliant device\n"
        "[enabled   ] Require MFA for admins\n"
    ),
    "09_secure_score.txt": (
        "MICROSOFT SECURE SCORE\n"
        "======================\n"
        "Score: 340.0 / 400.0 (85.0%)\n"
    ),
    "09b_auth_methods_policy.txt": (
        "AUTHENTICATION METHODS POLICY\n"
        "=============================\n"
        "Method                    State\n"
        "Fido2                     enabled\n"
        "MicrosoftAuthenticator    enabled\n"
        "Sms                       disabled\n"
    ),
    "10_intune_devices_count.txt": (
        "INTUNE DEVICE COUNT\n"
        "===================\n"
        "Total devices: 40\n"
        "Compliant: 39\n"
        "Non-compliant: 1\n"
    ),
    "10_intune_devices.txt": (
        "INTUNE DEVICES\n"
        "==============\n"
        "Device        OS         Compliance     User\n"
        "LAPTOP-01     Windows    Compliant      ola@acme.no\n"
        "LAPTOP-02     Windows    Compliant      kari@acme.no\n"
    ),
    "15_sharepoint_sites.txt": (
        "SHAREPOINT SITES\n"
        "================\n"
        "Site                          Storage\n"
        "https://acme.sharepoint.com   12 GB\n"
    ),
    "15b_sharepoint_settings.txt": (
        "SHAREPOINT TENANT SETTINGS\n"
        "==========================\n"
        "Sharing Capability: ExistingExternalUserSharingOnly\n"
        "Legacy Auth: false\n"
        "Unmanaged Devices: false\n"
    ),
    "16c_teams_external_access.txt": (
        # The real format teams.py emits (crossTenantAccessPolicy). This tenant
        # has external collaboration on but not wide open — a genuine review
        # item (warn), not empty data.
        "======================================================================\n"
        "  TEAMS / CROSS-TENANT EXTERNAL ACCESS POLICY\n"
        "======================================================================\n"
        "  Default Inbound Settings:\n"
        "    B2B Collaboration  : allowed\n"
        "    B2B Direct Connect : allowed\n"
        "\n"
        "  Partner Configurations: (none)\n"
        "======================================================================\n"
    ),
    "17_app_registrations.txt": (
        "APP REGISTRATIONS\n"
        "=================\n"
        "Name              AppId                                  Owners\n"
        "Sybr HUB          00000000-0000-0000-0000-0000000000aa   ola@acme.no\n"
    ),
    "17b_oauth_consent_grants.txt": (
        "OAUTH CONSENT GRANTS\n"
        "====================\n"
        "App               Scope                    ConsentType\n"
        "Sybr HUB          User.Read.All            AllPrincipals\n"
    ),
    "19_entra_audit_log_admin_activity.txt": (
        "ADMIN AUDIT LOG (LAST 14 DAYS)\n"
        "==============================\n"
        "Date         Actor          Activity\n"
        "2026-01-02   ola@acme.no    Update conditional access policy\n"
        "2026-01-03   kari@acme.no   Add member to role\n"
    ),
    "19b_defender_alert_count.txt": (
        "DEFENDER ALERT COUNT\n"
        "====================\n"
        "0 active alerts\n"
    ),
    # Both of these carry their count in the header the collector writes.
    # The score used to branch on "No risky" / "No active" — phrases no
    # collector produces, which existed only in this fixture. A clean tenant
    # was charged five points for each, and nothing failed, because the
    # fixture had been written to match the parser rather than the collector.
    "18_risky_users.txt": (
        "==========================================================================================\n"
        "  RISKY USERS  (0 total)\n"
        "==========================================================================================\n"
        "  UPN                                                Risk Level      Risk State           Last Updated\n"
        "  --------------------------------------------------------------------------------------\n"
        "==========================================================================================\n"
    ),
    "19b_defender_active_alerts.txt": (
        "==============================================================================================================\n"
        "  DEFENDER ACTIVE ALERTS  (0 unresolved)\n"
        "==============================================================================================================\n"
        "  Alert Title                                        Severity     Status          Created\n"
        "  ----------------------------------------------------------------------------------------------------------\n"
        "==============================================================================================================\n"
    ),
    "19c_purview_sensitivity_labels.txt": (
        "PURVIEW SENSITIVITY LABELS\n"
        "==========================\n"
        "Name              Priority   Status\n"
        "Confidential      1          Active\n"
        "Internal          2          Active\n"
    ),
    # Real collector format — a `_section_block` dump, one policy per [i] — so
    # the seam matches app/modules/m365_audit/sections/exchange.py:_save_dlp /
    # _save_retention rather than a hand-written column table the parser never
    # actually receives.
    "19d_purview_dlp_policies.txt": _entry_block(
        "PURVIEW DLP POLICIES",
        [{"Name": "PII Protection", "Mode": "Enable", "Priority": "0"}],
    ),
    "19e_purview_retention_policies.txt": _entry_block(
        "PURVIEW RETENTION POLICIES",
        [{"Name": "7 Year Retention", "Enabled": "True"}],
    ),
    "23_exchange_antiphish.txt": _entry_block(
        "EXCHANGE ANTI-PHISHING POLICIES",
        [{"Name": "Office365 AntiPhish", "Enabled": "Yes"}],
    ),
    "24_exchange_antispam.txt": _entry_block(
        "EXCHANGE ANTI-SPAM POLICIES",
        [{"Name": "Default", "SpamAction": "MoveToJmf", "Enabled": "Yes"}],
    ),
    "26_email_dns_spf_dmarc.txt": (
        "EMAIL DNS SECURITY\n"
        "==================\n"
        "Domain : acme.no\n"
        "SPF   : OK (v=spf1 include:spf.protection.outlook.com -all)\n"
        "DMARC : OK (v=DMARC1; p=reject; rua=mailto:dmarc@acme.no)\n"
        "DKIM (sel1) : CNAME selector1._domainkey.acme.no OK\n"
        "DKIM (sel2) : CNAME selector2._domainkey.acme.no OK\n"
    ),
    "27_exchange_defender_policies.txt": (
        "DEFENDER FOR OFFICE 365 POLICIES\n"
        "================================\n"
        "Name: Safe Links Policy\n"
        "PolicyType: SafeLinksPolicy\n"
        "Enabled: True\n"
        "\n"
        "Name: Safe Attachments Policy\n"
        "PolicyType: SafeAttachmentsPolicy\n"
        "Enabled: True\n"
    ),
    "27c_exchange_org_config.txt": (
        "EXCHANGE ORG CONFIG\n"
        "===================\n"
        # Real collector shape: _save_org_config renders the bool via _fmt_val,
        # which emits "No"/"Yes" — NOT "false"/"true". The old fixture matched
        # the parser instead of the collector, hiding an inert control.
        "  AuditDisabled: No\n"
    ),
    "27d_exchange_admin_audit_log_config.txt": (
        "EXCHANGE ADMIN AUDIT LOG CONFIG\n"
        "===============================\n"
        # CIS 9.1 signal. _save_admin_audit_log_config renders the bool via
        # _fmt_val, so a healthy (UAL-on) tenant reads "Yes", not "True" — the
        # collector shape, so the control's pass path is exercised for real.
        "  UnifiedAuditLogIngestionEnabled: Yes\n"
    ),
    "28_exchange_mailbox_forwarding.txt": (
        "MAILBOX FORWARDING CHECK\n"
        "========================\n"
        "No mailboxes with external forwarding configured.\n"
    ),
    "29_exchange_inbox_rules_external_fwd.txt": (
        "INBOX RULES WITH EXTERNAL FORWARDING\n"
        "====================================\n"
        "No inbox rules forwarding outside the tenant.\n"
    ),
    "31_password_protection.txt": (
        "PASSWORD PROTECTION\n"
        "===================\n"
        "Custom Banned Passwords Enabled : True\n"
        "Banned Password List : 12 entries\n"
    ),
    "45_azure_subscriptions.txt": (
        "AZURE SUBSCRIPTIONS\n"
        "===================\n"
        "Name              SubscriptionId                         State\n"
        "Acme Production   00000000-0000-0000-0000-0000000000b1   Enabled\n"
    ),
    "30_azure_vms.txt": (
        "AZURE VIRTUAL MACHINES\n"
        "======================\n"
        "VM Name        Size          Location    Status\n"
        "vm-dc-01       Standard_D2   westeurope  running\n"
        "vm-app-01      Standard_D4   westeurope  running\n"
    ),
    "52_azure_backup.txt": (
        "AZURE BACKUP PROTECTED ITEMS\n"
        "============================\n"
        "Vault: rsv-prod\n"
        "Name           Type          Status\n"
        "vm-dc-01       AzureVM       Protected\n"
        "vm-app-01      AzureVM       Protected\n"
    ),
    "51_azure_advisor.txt": (
        "AZURE ADVISOR RECOMMENDATIONS\n"
        "=============================\n"
        "2 recommendations\n"
    ),
    "61_unifi_audit.txt": (
        '{"mode": "controller", "sites": 1, "device_count": 4, "devices": [], '
        '"wlan_count": 2, "wlans": ['
        '{"name": "Acme-Corp", "security": "wpa3", "security_label": "WPA3", '
        '"vlan": "", "enabled": true, "guest": false}, '
        '{"name": "Acme-Guest", "security": "wpapsk", "security_label": "WPA2", '
        '"vlan": "", "enabled": true, "guest": true}], '
        '"network_count": 3, "firewall_rules": 12, "active_alarms": 0, '
        '"outdated_firmware_count": 0, "eol_count": 0, "default_creds_count": 0}'
    ),
    # ── The rest of what a real run writes ───────────────────────────────────
    #
    # Everything below was read by the report and absent here, so no sweep in
    # test_report_partial_audit.py could reach it: not removable, not stubbable,
    # and the controls and parsers behind it never exercised in either
    # direction. Written in the collectors' own shapes, and healthy, per the
    # rule at the top of this file.

    # users_mfa.py. Nothing stale, so no licence-waste finding — the parser
    # skips the banner, the NOTE block and the "Stale accounts found" line, so
    # a clean tenant parses to an empty list rather than to one phantom row.
    "03b_stale_accounts.txt": (
        "=" * 120 + "\n"
        "  STALE ACCOUNT DETECTION  (inactive >= 90 days or never signed in)\n"
        + "=" * 120 + "\n"
        "\n"
        "  Stale accounts found: 0\n"
        "\n"
        "\n"
        + "=" * 120 + "\n"
    ),

    # entra_devices.py. Forty joined machines, all Intune-managed — the count
    # that matters is total minus Intune's, and 10_intune_devices_count.txt
    # says forty, so the unmanaged-endpoint gap is zero.
    "15_entra_devices.txt": _entra_device_table([
        (f"LAPTOP-{i:02d}", "Windows", "10.0.22631", "AzureAd", "yes", "yes",
         "2026-01-02T08:14:00")
        for i in range(1, 41)
    ]),
    "15_entra_devices_count.txt": (
        "ENTRA DEVICE COUNT SUMMARY\n"
        "Total: 40\n"
        "Managed: 40\n"
        "Unmanaged: 0\n"
        "Enabled: 40\n"
        "Trust AzureAd: 40\n"
    ),

    # teams.py. Both files are carried into the report context as raw text.
    "16_teams.txt": _teams_table([
        ("Ledergruppen", "private", "ledergruppen@acme.no", "2024-03-04T09:00:00"),
        ("Prosjekt Nordlys", "private", "nordlys@acme.no", "2025-01-20T13:30:00"),
        ("Hele Acme", "public", "alle@acme.no", "2023-08-11T10:15:00"),
    ]),
    "16b_teams_settings.txt": (
        "=" * 70 + "\n"
        "  TEAMS SETTINGS (via teamwork endpoint)\n"
        + "=" * 70 + "\n"
        "  SfB Interop Enabled             : Disabled\n"
        "\n"
        "  Messaging Settings:\n"
        "    Allow User Edit Messages       : Enabled\n"
        "    Allow User Delete Messages     : Disabled\n"
        "    Allow Owner Delete Messages    : Enabled\n"
        "    Allow Teams Mentions           : Enabled\n"
        "    Allow Channel Mentions         : Enabled\n"
        + "=" * 70 + "\n"
    ),

    # usage_reports.py. The claim subscribedSkus cannot make: seats assigned
    # is not seats used. Everyone here has signed in, so no idle-licence
    # finding — which is what makes a later one meaningful.
    "16_usage_active_users.txt": _usage_table([
        (f"user{i:02d}@acme.no", "MICROSOFT 365 E3", "2026-01-02")
        for i in range(1, 39)
    ]),
    "16_usage_summary.txt": (
        "MICROSOFT 365 USAGE SUMMARY\n"
        "Period days: 90\n"
        "Total: 38\n"
        "Deleted: 0\n"
        "Active users: 38\n"
        "No activity: 0\n"
        "Licensed without activity: 0\n"
        "Names concealed: no\n"
    ),

    # apps_oauth.py. One credential on the one app registration, well short of
    # expiry. CIS 2.1.2's verdict comes from the WARN file, which is absent
    # here precisely because there is nothing to warn about.
    "17c_app_credential_expiry.txt": (
        "=" * 140 + "\n"
        "  APP REGISTRATION CREDENTIAL EXPIRY REPORT\n"
        + "=" * 140 + "\n"
        "\n"
        "  Total credentials : 1\n"
        "  Expired           : 0\n"
        "  Critical (<30d)   : 0\n"
        "  Warning  (<90d)   : 0\n"
        "  OK / No Expiry    : 1\n"
        "\n"
        f"  {'App Name':<40} {'Type':<12} {'Credential Name':<30} "
        f"{'Expiry Date':<22} {'Days Left':>9}  Status\n"
        "  " + "-" * 136 + "\n"
        f"  {'Sybr HUB':<40} {'Secret':<12} {'hub-api-secret':<30} "
        f"{'2027-06-01 12:00':<22} {'510':>9}  OK\n"
        "\n"
        + "=" * 140 + "\n"
    ),

    # identity_security.py. The detections behind 18_risky_users.txt, which
    # also reports none.
    "18d_risk_detections.txt": (
        "=" * 120 + "\n"
        "  RISK DETECTIONS  (0 events)\n"
        + "=" * 120 + "\n"
        f"  {'User':<40} {'Risk Type':<35} {'Level':<10} {'State':<15} Detected\n"
        "  " + "-" * 116 + "\n"
        + "=" * 120 + "\n"
    ),

    # exchange.py. Forty mailboxes against forty licensed users, and the two
    # sections whose emptiness the report counts rather than reads: a banner
    # declaring zero settles the count, so the "(none)" placeholder underneath
    # is furniture and not a record.
    "20_exchange_mailboxes_count.txt": (
        "=" * 40 + "\n"
        "  EXCHANGE MAILBOX COUNT\n"
        + "=" * 40 + "\n"
        "  Total     : 40\n"
        "  User      : 38\n"
        "  Shared    : 2\n"
        "  Room      : 0\n"
        + "=" * 40 + "\n"
    ),
    "21_exchange_transport_rules.txt": (
        "=" * 80 + "\n"
        "  EXCHANGE TRANSPORT RULES  (0 entries)\n"
        + "=" * 80 + "\n"
        "  (none)\n"
    ),
    "22_exchange_connectors.txt": (
        "=" * 80 + "\n"
        "  EXCHANGE CONNECTORS  (0 entries)\n"
        + "=" * 80 + "\n"
        "  (none)\n"
    ),

    # teams_policies.py. CIS 8.1.2 grades this: guests cannot invite guests,
    # and the guest role is not "same as member".
    "30b_teams_guest_access.txt": (
        "=" * 90 + "\n"
        "  TEAMS / ENTRA ID GUEST ACCESS SETTINGS\n"
        + "=" * 90 + "\n"
        "  Allow Invites From       : Admins and Guest Inviters\n"
        "  Guest User Role          : Restricted access (most restrictive)\n"
        "\n"
        "  Cross-Tenant Defaults:\n"
        "    B2B Collab Inbound     : blocked\n"
        "    B2B Collab Outbound    : blocked\n"
        "    B2B Direct Inbound     : blocked\n"
        "\n"
        + "=" * 90 + "\n"
    ),

    # pim.py. Two banners in one file, which is why _parse_banner_count
    # refuses to answer for it: taking the first would call a tenant with
    # permanent Global Administrators "zero privileged assignments". Here the
    # admin roles are eligible rather than standing, and nothing is permanent,
    # so no PERMANENT CRITICAL block is written.
    "32_pim_roles.txt": (
        "=" * 110 + "\n"
        "  PRIVILEGED IDENTITY MANAGEMENT (PIM) — ROLE ASSIGNMENTS\n"
        + "=" * 110 + "\n"
        "\n"
        "  ELIGIBLE (Just-In-Time) ASSIGNMENTS  (4 total)\n"
        "  " + "-" * 106 + "\n"
        f"  {'Role':<45} {'Principal':<40} {'Type':<15} Expiry\n"
        "  " + "-" * 106 + "\n"
        f"  {'Global Administrator':<45} {'Ola Nordmann':<40} {'user':<15} No expiry\n"
        f"  {'Global Administrator':<45} {'Kari Nordmann':<40} {'user':<15} No expiry\n"
        f"  {'Exchange Administrator':<45} {'Ola Nordmann':<40} {'user':<15} No expiry\n"
        f"  {'Security Reader':<45} {'Per Hansen':<40} {'user':<15} No expiry\n"
        "\n"
        "  ACTIVE ASSIGNMENTS  (2 total: 0 permanent, 2 time-bound/activated)\n"
        "  " + "-" * 106 + "\n"
        f"  {'Role':<45} {'Principal':<35} {'Type':<12} {'Assignment':<12} End\n"
        "  " + "-" * 106 + "\n"
        f"  {'Global Administrator':<45} {'Ola Nordmann':<35} {'user':<12} "
        f"{'Activated':<12} 2026-01-02T17:00:00\n"
        f"  {'Security Reader':<45} {'Per Hansen':<35} {'user':<12} "
        f"{'Activated':<12} 2026-01-02T15:30:00\n"
        "\n"
        "  " + "=" * 60 + "\n"
        "  SUMMARY\n"
        "  " + "=" * 60 + "\n"
        "    Eligible (JIT) assignments   : 4\n"
        "    Active assignments           : 2\n"
        "      Permanent                  : 0\n"
        "      Time-bound / Activated     : 2\n"
        "\n"
        + "=" * 110 + "\n"
    ),
}


# ── The same tenant, badly run ────────────────────────────────────────────────
#
# The healthy fixture above proves the report raises no *false* findings. It
# says nothing about whether real ones still fire — and every fix in this area
# made the report quieter, so that is the direction the risk now runs. These
# overrides describe a tenant with a genuine problem in each scored area.
#
# Keep it broken. If you add a finding to the report, break something here so
# the finding has something to catch.

_BROKEN_MFA_ROWS: list[tuple[str, str, str, str, str, str]] = [
    (f"User {i:02d}", f"user{i:02d}@acme.no", "YES", "NO", "NO", "Authenticator")
    for i in range(1, 9)
] + [
    (f"User {i:02d}", f"user{i:02d}@acme.no", "NO", "NO", "NO", "(none)")
    for i in range(9, 41)
]

_BROKEN_OVERRIDES: dict[str, str] = {
    # 8 of 40 users have MFA, and no CA policy covers the rest. Both files, or
    # the healthy sidecar inherited from FULL_AUDIT wins and this tenant is not
    # broken at all — production prefers the JSON, so overriding only the table
    # left four findings-tests asserting against the healthy numbers.
    "04_mfa_methods.txt": _mfa_table(_BROKEN_MFA_ROWS),
    "04_mfa_methods.json": _mfa_json(_BROKEN_MFA_ROWS),
    "04b_mfa_ca_analysis.txt": (
        "CONDITIONAL ACCESS MFA ANALYSIS\n"
        "===============================\n"
        "No conditional access policy enforces MFA.\n"
    ),
    "08_conditional_access.txt": (
        "CONDITIONAL ACCESS POLICIES\n"
        "===========================\n"
        "[disabled  ] Require MFA for all users\n"
    ),
    "09_secure_score.txt": (
        "MICROSOFT SECURE SCORE\n"
        "======================\n"
        "Score: 120.0 / 400.0 (30.0%)\n"
        "Top 20 Improvement Actions\n"
        "Require MFA for administrative roles          12.0%   High\n"
        "Enable Safe Attachments                        8.0%   High\n"
    ),
    # Seven global admins.
    "07_admin_roles.txt": _admin_role_table([
        ("Global Administrator", f"Admin {i}", f"admin{i}@acme.no", "2026-03-20 14:30")
        for i in range(1, 8)
    ]),
    "10_intune_devices_count.txt": (
        "INTUNE DEVICE COUNT\n"
        "===================\n"
        "Total devices: 40\n"
        "Compliant: 12\n"
        "Non-compliant: 28\n"
    ),
    "15b_sharepoint_settings.txt": (
        "SHAREPOINT TENANT SETTINGS\n"
        "==========================\n"
        "Sharing Capability: ExternalUserAndGuestSharing\n"
        "Legacy Auth: true\n"
        "Unmanaged Devices: true\n"
    ),
    "26_email_dns_spf_dmarc.txt": (
        "EMAIL DNS SECURITY\n"
        "==================\n"
        "Domain : acme.no\n"
        "SPF   : MISSING\n"
        "DMARC : MISSING\n"
        "DKIM (sel1) : NOT FOUND\n"
    ),
    "18_risky_users.txt": (
        "==========================================================================================\n"
        "  RISKY USERS  (2 total)\n"
        "==========================================================================================\n"
        "  UPN                                                Risk Level      Risk State           Last Updated\n"
        "  --------------------------------------------------------------------------------------\n"
        "  user09@acme.no                                     high            atRisk               2026-01-02T09:00:00\n"
        "  user14@acme.no                                     high            atRisk               2026-01-03T11:20:00\n"
        "==========================================================================================\n"
    ),
    # The collector writes this file only when it finds something.
    "28b_exchange_external_forwarding_WARN.txt": (
        "====================================================\n"
        "  EXTERNAL MAILBOX FORWARDING WARNING  (2 mailboxes)\n"
        "====================================================\n"
        "  Ola Nordmann  →  ola.private@gmail.com\n"
        "  Kari Nordmann  →  kari@competitor.example\n"
    ),
    "19b_defender_alert_count.txt": (
        "DEFENDER ALERT COUNT\n"
        "====================\n"
        "3 active alerts\n"
    ),
    "19b_defender_active_alerts.txt": (
        "==============================================================================================================\n"
        "  DEFENDER ACTIVE ALERTS  (3 unresolved)\n"
        "==============================================================================================================\n"
        "  Alert Title                                        Severity     Status          Created\n"
        "  ----------------------------------------------------------------------------------------------------------\n"
        "  Suspicious sign-in from unfamiliar location        high         newAlert        2026-01-02T08:11:00\n"
        "  Malware detected on LAPTOP-07                      high         inProgress      2026-01-02T14:02:00\n"
        "  Mass download by a single user                     medium       newAlert        2026-01-03T07:45:00\n"
        "==============================================================================================================\n"
    ),
    # A FortiGate with every finding the report knows how to raise.
    "60_fortigate_audit.txt": (
        '{"hostname": "acme-fgt-01", "version": "7.4.3", '
        '"admins": ['
        '{"name": "admin", "two_factor": false, "trusthost": false}, '
        '{"name": "svc-monitor", "two_factor": false, "trusthost": true}], '
        '"policy_warnings": ['
        '"Policy 12 \\"any-any\\" is an allow-all rule", '
        '"Policy 19 has no logging enabled"]}'
    ),
    "61_unifi_audit.txt": (
        '{"mode": "controller", "sites": 1, "device_count": 6, "devices": [], '
        '"wlan_count": 2, "wlans": ['
        '{"name": "Acme-Corp", "security": "wpapsk", "security_label": "WPA2", '
        '"vlan": "", "enabled": true, "guest": false}, '
        '{"name": "Acme-Open", "security": "open", "security_label": "Open", '
        '"vlan": "", "enabled": true, "guest": true}], '
        '"network_count": 3, "firewall_rules": 4, "active_alarms": 2, '
        '"outdated_firmware_count": 3, "eol_count": 2, "default_creds_count": 1}'
    ),
}

BROKEN_AUDIT: dict[str, str] = {**FULL_AUDIT, **_BROKEN_OVERRIDES}
