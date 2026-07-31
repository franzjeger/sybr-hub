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

FULL_AUDIT: dict[str, str] = {
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
    "04_mfa_methods.txt": (
        "MFA METHOD REPORT\n"
        "=================\n"
        + "".join(
            f"User {i:02d} | user{i:02d}@acme.no | MFA:YES | CA:YES | EXCL:NO | Authenticator\n"
            for i in range(1, 38)
        )
        + "User 38 | user38@acme.no | MFA:NO | CA:YES | EXCL:NO | (none)\n"
    ),
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
    "07_admin_roles.txt": (
        "ADMIN ROLE ASSIGNMENTS\n"
        "======================\n"
        "Role                     User            Email\n"
        "Global Administrator     Ola Nordmann    ola@acme.no\n"
        "Global Administrator     Kari Nordmann   kari@acme.no\n"
        "Global Administrator     Break Glass     bg@acme.no\n"
        "Security Administrator   Per Hansen      per@acme.no\n"
    ),
    "07b_pim_eligible_assignments.txt": (
        "PIM ELIGIBLE ROLE ASSIGNMENTS (4 total)\n"
        "=======================================\n"
        "Role                     User\n"
        "Global Administrator     ola@acme.no\n"
    ),
    "07c_emergency_access_check.txt": (
        "EMERGENCY / BREAK-GLASS ACCOUNT CHECK\n"
        "=====================================\n"
        "bg@acme.no  excluded from all CA policies  OK\n"
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
        "TEAMS EXTERNAL ACCESS\n"
        "=====================\n"
        "AllowFederatedUsers: True\n"
        "AllowPublicUsers: False\n"
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
    "19c_purview_sensitivity_labels.txt": (
        "PURVIEW SENSITIVITY LABELS\n"
        "==========================\n"
        "Name              Priority   Status\n"
        "Confidential      1          Active\n"
        "Internal          2          Active\n"
    ),
    "19d_purview_dlp_policies.txt": (
        "PURVIEW DLP POLICIES\n"
        "====================\n"
        "Policy Name           Mode\n"
        "PII Protection        Enabled\n"
    ),
    "19e_purview_retention_policies.txt": (
        "PURVIEW RETENTION POLICIES\n"
        "==========================\n"
        "Policy Name           Mode\n"
        "7 Year Retention      Enabled\n"
    ),
    "23_exchange_antiphish.txt": (
        "ANTI-PHISHING POLICIES\n"
        "======================\n"
        "Name                     Enabled\n"
        "Office365 AntiPhish      True\n"
    ),
    "24_exchange_antispam.txt": (
        "ANTI-SPAM POLICIES\n"
        "==================\n"
        "Name                     Enabled\n"
        "Default                  True\n"
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
        "AuditDisabled: false\n"
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

_BROKEN_OVERRIDES: dict[str, str] = {
    # 8 of 40 users have MFA, and no CA policy covers the rest.
    "04_mfa_methods.txt": (
        "MFA METHOD REPORT\n"
        "=================\n"
        + "".join(
            f"User {i:02d} | user{i:02d}@acme.no | MFA:YES | CA:NO | EXCL:NO | Authenticator\n"
            for i in range(1, 9)
        )
        + "".join(
            f"User {i:02d} | user{i:02d}@acme.no | MFA:NO | CA:NO | EXCL:NO | (none)\n"
            for i in range(9, 41)
        )
    ),
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
    "07_admin_roles.txt": (
        "ADMIN ROLE ASSIGNMENTS\n"
        "======================\n"
        "Role                     User            Email\n"
        + "".join(
            f"Global Administrator     Admin {i}        admin{i}@acme.no\n"
            for i in range(1, 8)
        )
    ),
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
        "RISKY USERS\n"
        "===========\n"
        "UPN                   Risk Level    State\n"
        "user09@acme.no        high          atRisk\n"
        "user14@acme.no        high          atRisk\n"
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
        "ACTIVE DEFENDER ALERTS\n"
        "======================\n"
        "Suspicious sign-in from unfamiliar location   high\n"
        "Malware detected on LAPTOP-07                 high\n"
        "Mass download by a single user                medium\n"
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
