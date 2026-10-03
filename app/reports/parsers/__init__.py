"""Parsers that turn raw audit collector files into structured data.

One module per domain, each holding the parsers for the files its collectors
write:

    common         row and banner counting, Azure file lookup, error payloads
    identity       users, MFA, Conditional Access, admin roles, groups, sign-ins
    tenant         Secure Score, licences, licence optimisation, usage reports
    email          Exchange Online, DNS (SPF, DKIM, DMARC)
    collaboration  SharePoint, OAuth consent grants and app registrations, Purview
    devices        Intune and Entra ID devices
    azure          Azure inventory, VMs and backup coverage
    m365_backup    backup of the Microsoft 365 data: Microsoft 365 Backup, vendor apps
    network        FortiGate and UniFi quick audits

The names below are re-exported so code written against the single module this
used to be keeps importing from ``app.reports.parsers``. A test that patches a
parser must patch it in the module that defines it, which is where its callers
look it up.
"""

from __future__ import annotations

from app.reports.parsers.azure import _parse_azure_overview, _parse_backup_coverage
from app.reports.parsers.collaboration import (
    _parse_oauth_grants,
    _parse_purview,
    _parse_sharepoint_settings,
)
from app.reports.parsers.common import (
    _count_data_lines,
    _extract_policy_names,
    _is_error_payload,
    _is_multiline_record_format,
    _parse_banner_count,
)
from app.reports.parsers.devices import _parse_entra_devices, _parse_intune_devices
from app.reports.parsers.email import (
    _count_defender_policy_state,
    _is_audit_relevant_domain,
    _parse_exchange_overview,
    _parse_spf_dmarc,
    _severity,
)
from app.reports.parsers.identity import (
    _MFA_COLS,
    _mfa_user_records,
    _parse_admin_roles,
    _parse_ca_policies,
    _parse_groups,
    _parse_mfa,
    _parse_signin_risk,
    _parse_user_counts,
    _risky_users_from_sidecar,
)
from app.reports.parsers.m365_backup import _parse_m365_backup
from app.reports.parsers.network import _parse_network_audit
from app.reports.parsers.tenant import (
    _analyze_license_optimization,
    _parse_licenses,
    _parse_secure_score,
    _parse_usage,
    _sku_friendly,
)

__all__ = [
    "_MFA_COLS",
    "_analyze_license_optimization",
    "_count_data_lines",
    "_count_defender_policy_state",
    "_extract_policy_names",
    "_is_audit_relevant_domain",
    "_is_error_payload",
    "_is_multiline_record_format",
    "_mfa_user_records",
    "_parse_admin_roles",
    "_parse_azure_overview",
    "_parse_backup_coverage",
    "_parse_banner_count",
    "_parse_ca_policies",
    "_parse_entra_devices",
    "_parse_exchange_overview",
    "_parse_groups",
    "_parse_intune_devices",
    "_parse_licenses",
    "_parse_m365_backup",
    "_parse_mfa",
    "_parse_network_audit",
    "_parse_oauth_grants",
    "_parse_purview",
    "_parse_secure_score",
    "_parse_sharepoint_settings",
    "_parse_signin_risk",
    "_parse_spf_dmarc",
    "_parse_usage",
    "_parse_user_counts",
    "_risky_users_from_sidecar",
    "_severity",
    "_sku_friendly",
]
