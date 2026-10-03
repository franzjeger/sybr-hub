"""Evidence availability and labelling helpers for report sections."""

from __future__ import annotations

import re


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
# A verdict read from a JSON sidecar names the sidecar first, then the text it
# falls back to for runs from before it: the sidecar is where the figure comes
# from, and the appendix carries it beside the text. Naming only the text
# showed a technician tracing a verdict the file the reader did not use.
_EVIDENCE_MAP: dict[str, tuple[str, ...]] = {
    # Leaving the MFA sidecar undeclared meant removing every file this control
    # named still left the verdict standing on the one file nobody had listed.
    "1.1.1": (
        "04_mfa_methods.json",
        "04_mfa_methods.txt",
        "04b_mfa_ca_analysis.json",
        "04b_mfa_ca_analysis.txt",
    ),
    "1.1.2": ("09b_auth_methods_policy.json", "09b_auth_methods_policy.txt"),
    "1.1.3": ("07_admin_roles.json", "07_admin_roles.txt"),
    "1.1.4": ("08_conditional_access.json", "08_conditional_access.txt"),
    "1.1.5": (
        "07b_pim_eligible_assignments.json",
        "07b_pim_eligible_assignments.txt",
        "32_pim_roles.txt",
    ),
    "1.1.6": ("07c_emergency_access_check.json", "07c_emergency_access_check.txt"),
    "1.1.7": (
        "31b_smart_lockout.json",
        "31b_smart_lockout.txt",
        "08_conditional_access.json",
        "08_conditional_access.txt",
    ),
    "1.1.8": ("07d_access_reviews.json", "07d_access_reviews.txt"),
    "1.1.9": ("18c_cross_tenant_access_policy.json", "18c_cross_tenant_access_policy.txt"),
    "1.2.1": ("31_password_protection.json", "31_password_protection.txt"),
    "1.4": ("09_secure_score.json", "09_secure_score.txt"),
    "2.1": (
        "17b_oauth_consent_grants.json",
        "17b_oauth_consent_grants.txt",
        "17_app_registrations.json",
        "17_app_registrations.txt",
    ),
    # 17_app_registrations.txt is not incidental here: it is what separates
    # "no expired credentials" from "the section never ran", so the verdict is
    # formed from it as much as from the expiry files.
    "2.1.2": (
        "17_app_registrations.txt",
        "17c_app_credential_expiry.json",
        "17c_app_credential_expiry.txt",
        "17c_app_credential_expiry_WARN.txt",
    ),
    "3.1.1": ("19d_purview_dlp_policies.json", "19d_purview_dlp_policies.txt"),
    "3.2.1": ("19c_purview_sensitivity_labels.json", "19c_purview_sensitivity_labels.txt"),
    "4.1": ("27c_exchange_org_config.json", "27c_exchange_org_config.txt"),
    "4.2": ("23_exchange_antiphish.json", "23_exchange_antiphish.txt"),
    "4.3": ("24_exchange_antispam.json", "24_exchange_antispam.txt"),
    # The two WARN files carry the finding; the two plain files are what say
    # the scan ran at all, and the "pass" branch is formed from those. Listing
    # only three of the four meant a technician tracing a pass was shown every
    # file except the one that produced it. The plain files' sidecars count
    # the forwarding the run could not place, which makes it "cannot verify".
    "4.4": (
        "28_exchange_mailbox_forwarding.json",
        "28_exchange_mailbox_forwarding.txt",
        "28b_exchange_external_forwarding_WARN.txt",
        "29_exchange_inbox_rules_external_fwd.json",
        "29_exchange_inbox_rules_external_fwd.txt",
        "29_exchange_inbox_rules_external_fwd_WARN.txt",
    ),
    "4.5": ("27_exchange_defender_policies.json", "27_exchange_defender_policies.txt"),
    "4.6": ("27_exchange_defender_policies.json", "27_exchange_defender_policies.txt"),
    "5.1.1": ("08_conditional_access.json", "08_conditional_access.txt"),
    "5.2.1": ("26_email_dns_spf_dmarc.json", "26_email_dns_spf_dmarc.txt"),
    "5.2.2": ("26_email_dns_spf_dmarc.json", "26_email_dns_spf_dmarc.txt"),
    # Whether Exchange signs for the domain (25), and who sends its mail and
    # which DKIM keys are published (26).
    "5.2.3": (
        "25_exchange_dkim.json",
        "25_exchange_dkim.txt",
        "26_email_dns_spf_dmarc.json",
        "26_email_dns_spf_dmarc.txt",
    ),
    "6.1.1": (
        "11_intune_compliance_policies.json",
        "11_intune_compliance_policies.txt",
        "10_intune_devices.json",
        "10_intune_devices_count.txt",
    ),
    "7.2.1": ("15b_sharepoint_settings.json", "15b_sharepoint_settings.txt"),
    "7.2.2": ("19e_purview_retention_policies.json", "19e_purview_retention_policies.txt"),
    # SharePoint's own legacy-protocol flag, not Entra's: that is 5.1.1.
    "7.2.3": ("15b_sharepoint_settings.json", "15b_sharepoint_settings.txt"),
    "7.2.4": ("25_onedrive_sharing.json", "25_onedrive_sharing.txt"),
    "8.1.1": ("16c_teams_external_access.json", "16c_teams_external_access.txt"),
    "8.1.2": ("30b_teams_guest_access.json", "30b_teams_guest_access.txt"),
    "9.1": (
        "27d_exchange_admin_audit_log_config.json",
        "27d_exchange_admin_audit_log_config.txt",
    ),
    "9.2": (
        "19b_defender_active_alerts.json",
        "19b_defender_active_alerts.txt",
        "19b_defender_alert_count.txt",
    ),
    "9.3": ("18_risky_users.json", "18_risky_users.txt"),
    # Microsoft 365 Backup and the backup vendors' apps, both in one section.
    "11.2": ("34_m365_backup.json", "34_m365_backup.txt"),
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
        rest = stripped[len(label) :].lstrip()
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


# Which SKU part numbers carry which capability. Only the ones a CIS control
# actually gates on; this is not meant to be a complete Microsoft catalogue,
# and an unknown SKU deliberately yields "unknown" rather than "absent".
#
# O365_BUSINESS_PREMIUM is Microsoft 365 Business *Standard*, not Premium —
# Microsoft's part number predates the rename. Business Premium is SPB, and
# it is the one that carries Entra ID P1, Intune and Defender for Office P1.
# Getting that pair backwards turns a licence gap into a config finding.
_SKU_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "AAD_PREMIUM": ("entra_p1",),
    "AAD_PREMIUM_P2": ("entra_p1", "entra_p2"),
    "EMS": ("entra_p1", "intune"),
    "EMSPREMIUM": ("entra_p1", "entra_p2", "intune"),
    "SPB": ("entra_p1", "intune", "defender_office"),
    "SPE_E3": ("entra_p1", "intune"),
    "SPE_E5": ("entra_p1", "entra_p2", "intune", "defender_office", "purview"),
    "ENTERPRISEPREMIUM": ("entra_p1", "entra_p2", "intune", "defender_office", "purview"),
    "INTUNE_A": ("intune",),
    "ATP_ENTERPRISE": ("defender_office",),
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
