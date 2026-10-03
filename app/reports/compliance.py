"""CIS M365 Benchmark / NIST CSF / ISO 27001 compliance mapping.

Each control is one entry in ``_CONTROLS``: its CIS id, the benchmark's title,
the report category, its NIST CSF 2.0 and ISO 27001:2022 cross-references and
a check that reads the audit and returns ``(status, detail)``, or None for no
row. ``_build_compliance_map`` walks the table in order, so table order is row
order in the report.

Every check keeps three cases apart: a reading that passes, a reading that
does not, and no reading at all. A refusal, an error stub, a licence the
tenant lacks or a section that never ran is "info" (cannot verify), never a
zero and never a pass, and "info" rows stay out of the compliance percentage.

Every detail a reader sees is a key in ``app/reports/i18n.py``, in both
languages, so an English report reads English. A check writes it with:

* ``audit.say("cis_x", count=n)``: the sentence, as plain text;
* ``audit.cannot_verify("cis_gap_x")``: "Cannot be verified: " and why, for
  a row with no reading (status "info");
* ``audit.not_licensed("cis_lic_x")``: "Not licensed: " and which licence.

Keys are named ``cis_<topic>_<case>``; the reasons for a missing reading are
``cis_gap_*`` and for a missing licence ``cis_lic_*``. Placeholders are named,
and a value from the tenant (a domain, a count, a policy name) goes in a
placeholder, never into the key. The oldest rows call ``audit.t(...)``
directly, which gives the same text with its key attached; nothing reads the
difference. A new control adds its keys to i18n.py, its entry to
``_CONTROLS`` below and its files to ``_EVIDENCE_MAP`` in evidence.py.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.modules.m365_audit.sections.apps_oauth import EXPIRY_SOON_DAYS
from app.reports.evidence import (
    _EVIDENCE_MAP,
    _evidence_unavailable,
    _lacks,
    _licensed_capabilities,
    _section_ran,
)
from app.reports.i18n import T
from app.reports.parsers import (
    _count_data_lines,
    _is_audit_relevant_domain,
    _parse_banner_count,
    _risky_users_from_sidecar,
)
from app.reports.parsers.collaboration import (
    _app_credential_counts,
    _onedrive_scan,
    _teams_cross_tenant,
    _teams_guest_settings,
)
from app.reports.parsers.common import _record_count, _sidecar
from app.reports.parsers.email import (
    _defender_policies,
    _dkim_selectors,
    _exchange_dkim_configs,
    _exchange_signs,
    _inbox_rule_counts,
    _key_published,
    _spf_senders,
    _third_party_dkim,
    _unverified_forwarding_count,
)
from app.reports.parsers.identity import _risky_users_from_text
from app.reports.parsers.m365_backup import m365_backup_control

# Names shown next to the ids, so the cross-reference columns are readable.
_NIST_NAMES = {
    "ID.RA-01": "Vulnerabilities in assets are identified, validated, and recorded",
    "PR.AA-01": "Identities and credentials are managed",
    "PR.AA-03": "Users, services, and hardware are authenticated",
    "PR.AA-05": "Access permissions are managed, enforced, and reviewed",
    "PR.DS-01": "Data-at-rest is protected",
    "PR.DS-02": "Data-in-transit is protected",
    "PR.DS-10": "Data-in-use is protected",
    "PR.DS-11": "Backups of data are created, protected, maintained, and tested",
    "PR.PS-04": "Log records are generated and made available for monitoring",
    "PR.PS-05": "Installation and execution of unauthorized software are prevented",
    "DE.AE-03": "Information is correlated from multiple sources",
    "DE.CM-09": "Computing hardware, software, and their data are monitored",
    "RS.AN-03": "Analysis establishes what took place during an incident",
}
_ISO_NAMES = {
    "A.5.14": "Information transfer",
    "A.5.15": "Access control",
    "A.5.16": "Identity management",
    "A.5.18": "Access rights",
    "A.5.28": "Collection of evidence",
    "A.8.1": "User endpoint devices",
    "A.8.3": "Information access restriction",
    "A.8.5": "Secure authentication",
    "A.8.7": "Protection against malware",
    "A.8.8": "Management of technical vulnerabilities",
    "A.8.12": "Data leakage prevention",
    "A.8.13": "Information backup",
    "A.8.15": "Logging",
    "A.8.16": "Monitoring activities",
    "A.8.24": "Use of cryptography",
}

# (status, detail). The detail is shown to the customer as written.
_Verdict = tuple[str, str]


@dataclass(frozen=True)
class _Audit:
    """The parts of a report context the checks read, looked up once."""

    context: dict
    t: T
    # None when the licence section produced nothing: unknown, not "none".
    capabilities: set[str] | None
    fc: dict
    mfa: dict
    ca: dict
    secure_score: dict
    admin_roles: dict
    spf_dmarc: list
    sharepoint: dict
    intune: dict
    oauth: dict
    purview: dict

    @classmethod
    def of(cls, context: dict, t: T) -> _Audit:
        return cls(
            context=context,
            t=t,
            capabilities=_licensed_capabilities(context.get("licenses") or []),
            fc=context.get("file_contents", {}),
            mfa=context.get("mfa", {}),
            ca=context.get("ca", {}),
            secure_score=context.get("secure_score", {}),
            admin_roles=context.get("admin_roles", {}),
            spf_dmarc=context.get("spf_dmarc", []),
            sharepoint=context.get("sharepoint", {}),
            intune=context.get("intune", {}),
            oauth=context.get("oauth", {}),
            purview=context.get("purview", {}),
        )

    def say(self, key: str, **params) -> str:
        """The detail *key* in the report's language, as plain text."""
        return str(self.t(key, **params))

    def cannot_verify(self, key: str, **params) -> str:
        """A row with no reading: "Cannot be verified: " and the reason *key*."""
        return self.say("cis_cannot_verify", reason=self.say(key, **params))

    def not_licensed(self, key: str, **params) -> str:
        """A row the tenant's licences rule out: "Not licensed: " and the reason *key*."""
        return self.say("cis_not_licensed", reason=self.say(key, **params))


@dataclass(frozen=True)
class _Control:
    cis_id: str
    # The benchmark's wording, shown untranslated in both languages.
    title: str
    # An i18n key, resolved in the report's language.
    category: str
    nist: str
    iso: str
    # check(audit) -> verdict; inside _PerDomain, check(audit, record, domain).
    check: Callable[..., _Verdict]


@dataclass(frozen=True)
class _PerDomain:
    """Controls graded once per audited mail domain, all of them domain by domain."""

    controls: tuple[_Control, ...]


# ── Engine ────────────────────────────────────────────────────────────────────


def _build_compliance_map(context: dict, lang: str = "no", frameworks: str = "all") -> list[dict]:
    """Map audit findings to CIS Microsoft 365 Foundations Benchmark v3.1 controls.

    *frameworks* controls which cross-reference columns are included:
      "cis"      - CIS only (no extra columns)
      "cis+nist" - CIS + NIST CSF 2.0
      "cis+iso"  - CIS + ISO 27001:2022
      "all"      - CIS + NIST CSF 2.0 + ISO 27001:2022
    """
    audit = _Audit.of(context, T(lang))
    show_nist = frameworks in ("cis+nist", "all")
    show_iso = frameworks in ("cis+iso", "all")
    return [
        _row(audit, control, title, verdict, show_nist, show_iso)
        for control, title, verdict in _verdicts(audit)
    ]


def _verdicts(audit: _Audit) -> Iterator[tuple[_Control, str, _Verdict]]:
    for entry in _CONTROLS:
        if isinstance(entry, _Control):
            yield entry, entry.title, entry.check(audit)
            continue
        for record in audit.spf_dmarc:
            domain = record.get("domain", "")
            if not _is_audit_relevant_domain(domain):
                continue
            for control in entry.controls:
                title = f"{control.title} ({domain})" if domain else control.title
                yield control, title, control.check(audit, record, domain)


def _row(
    audit: _Audit,
    control: _Control,
    title: str,
    verdict: _Verdict,
    show_nist: bool,
    show_iso: bool,
) -> dict:
    status, detail = verdict
    row = {
        "cis_id": control.cis_id,
        "title": title,
        "category": getattr(audit.t, control.category),
        "status": status,
        "detail": detail,
        # Only files this run collected: pointing at a file the report does not
        # carry is worse than pointing at nothing.
        "evidence": [
            f for f in _EVIDENCE_MAP.get(control.cis_id, ()) if audit.fc.get(f, "").strip()
        ],
    }
    if show_nist:
        row["nist_id"] = f"{control.nist}: {_NIST_NAMES[control.nist]}"
    if show_iso:
        row["iso_id"] = f"{control.iso}: {_ISO_NAMES[control.iso]}"
    return row


# ── Shared parsing ────────────────────────────────────────────────────────────


def _missing_or_error(text: str) -> bool:
    return not text.strip() or text.strip().startswith("Error:")


def _bool_setting(text: str, key: str, *, first_line_only: bool) -> bool | None:
    """A "Key: value" flag, or None when absent or unreadable.

    The evidence writer prints booleans as Yes/No, older files as true/false,
    so both are accepted. With *first_line_only* the first line naming the key
    decides even when its value is unreadable; otherwise such a line is skipped.
    """
    for line in text.splitlines():
        if key in line and ":" in line:
            value = line.split(":", 1)[1].strip().rstrip(";").lower()
            if value in ("true", "false", "yes", "no"):
                return value in ("true", "yes")
            if first_line_only:
                return None
    return None


def _setting(fc: dict, filename: str, key: str, *, first_line_only: bool) -> bool | None:
    """A yes/no setting from the file's JSON sidecar, or from its text.

    The sidecar holds it as a boolean or null; a run from before the sidecar
    is read by _bool_setting, as it always was.
    """
    data = _sidecar(fc, filename)
    if data is None:
        return _bool_setting(fc.get(filename, ""), key, first_line_only=first_line_only)
    value = data.get(key)
    return value if isinstance(value, bool) else None


def _purview_count(purview: dict, key: str) -> int:
    """A Purview count, which the parser gives as a list, an int or not at all."""
    raw = purview.get(key, 0) if purview else 0
    if isinstance(raw, list):
        return len(raw)
    return raw if isinstance(raw, int) else 0


def _found_or_gap(
    audit: _Audit, found: bool, file: str, found_detail: str, none_detail: str, gap_key: str
) -> _Verdict:
    """Pass when found; warn when the section ran and found none; else cannot verify."""
    if found:
        return "pass", found_detail
    if _section_ran(audit.fc, file):
        return "warn", none_detail
    return "info", audit.cannot_verify(gap_key)


# ── Identity & access ─────────────────────────────────────────────────────────


def _mfa(audit: _Audit) -> _Verdict:
    # Unreadable MFA state is "info", not a 0% fail: it must not count against
    # the tenant in the percentage.
    mfa, t = audit.mfa, audit.t
    if not mfa.get("has_data"):
        return "info", t.cis_mfa_unavailable
    pct = mfa.get("pct", 0)
    if pct >= 95:
        return "pass", t("cis_mfa_coverage", pct=pct)
    if pct > 0:
        return "partial", t("cis_mfa_partial", pct=pct, no_mfa=mfa.get("no_mfa", 0))
    return "fail", t("cis_mfa_none", no_mfa=mfa.get("no_mfa", 0))


_PHISHING_RESISTANT = frozenset({"fido2", "windowshelloforbusiness", "x509certificate"})


def _phishing_resistant_methods(text: str, sidecar: dict | None = None) -> list[str]:
    """Phishing-resistant methods the policy's "Method  State" table has enabled.

    From 09b_auth_methods_policy.json when the run has it.
    """
    if sidecar is not None:
        return [
            m.get("method") or ""
            for m in sidecar.get("methods") or []
            if (m.get("method") or "").lower().replace(" ", "") in _PHISHING_RESISTANT
            and str(m.get("state") or "").lower() == "enabled"
        ]
    enabled = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("-"):
            continue
        cols = re.split(r"\s{2,}", stripped)
        if len(cols) < 2:
            continue
        if cols[0].lower().replace(" ", "") in _PHISHING_RESISTANT and cols[1].lower() == "enabled":
            enabled.append(cols[0])
    return enabled


def _phishing_resistant_mfa(audit: _Audit) -> _Verdict:
    # CIS asks whether the tenant's policy enables these methods, not what share
    # of users has registered one.
    text = audit.fc.get("09b_auth_methods_policy.txt", "")
    sidecar = _sidecar(audit.fc, "09b_auth_methods_policy.txt")
    # Any "Error" prefix: some sections write "Error fetching …" without a colon.
    if sidecar is None and (not text.strip() or text.lstrip().startswith("Error")):
        return "info", audit.cannot_verify("cis_gap_auth_methods_policy")
    enabled = _phishing_resistant_methods(text, sidecar)
    if enabled:
        return "pass", audit.say("cis_phish_resistant_enabled", methods=", ".join(enabled))
    return "warn", audit.say("cis_phish_resistant_none")


def _global_admins(audit: _Audit) -> _Verdict:
    admin, t = audit.admin_roles, audit.t
    if not admin.get("has_data"):
        return "info", audit.cannot_verify("cis_gap_admin_roles")
    ga = admin.get("global_admin_count", 0)
    if 2 <= ga <= 4:
        return "pass", t("cis_ga_count", count=ga)
    if ga > 4:
        return "fail", t("cis_ga_too_many", count=ga)
    if ga == 1:
        return "warn", t("cis_ga_too_few", count=ga)
    # Role data but no standing Global Admin: typically PIM/JIT, where every
    # Global Admin is eligible only. Not verifiable from here, so not omitted.
    return "info", audit.say("cis_ga_none_standing")


def _conditional_access(audit: _Audit) -> _Verdict:
    ca = audit.ca
    if ca.get("has_data") and ca.get("enabled", 0) > 0:
        return "pass", audit.t("cis_active_policies", count=ca["enabled"])
    if ca.get("has_data"):
        return "fail", audit.t.cis_no_active_ca
    return "info", audit.cannot_verify("cis_gap_audit_data")


def _pim(audit: _Audit) -> _Verdict:
    text = audit.fc.get("07b_pim_eligible_assignments.txt", "")
    sidecar = _sidecar(audit.fc, "07b_pim_eligible_assignments.txt")
    # The banner's own count: the header is written even with no assignments,
    # and counting lines would count the column header.
    count = int(sidecar.get("count") or 0) if sidecar is not None else _parse_banner_count(text)
    if sidecar is None and _missing_or_error(text):
        return "info", audit.cannot_verify("cis_gap_pim")
    if count is not None and count > 0:
        return "pass", audit.say("cis_pim_found", count=count)
    if _lacks(audit.capabilities, "entra_p2"):
        # Without an assigned P2 seat there is nothing to configure.
        return "info", audit.not_licensed("cis_lic_pim")
    return "warn", audit.say("cis_pim_none")


_BREAK_GLASS_SUMMARY = re.compile(r"break_glass_candidates=(\d+)\s+ca_exclusions_known=(yes|no)")
_CA_EXCLUDED_ADMINS = re.compile(r"ca_excluded_admins=(\d+)")


def _emergency_access(audit: _Audit) -> _Verdict:
    # A break-glass account is a cloud admin deliberately excluded from
    # Conditional Access. The file lists every Global Admin, so the verdict
    # comes from the section's summary line, never from counting rows.
    # The summary's figures come from 07c_emergency_access_check.json when the
    # run has it, and from the SUMMARY line otherwise.
    sidecar = _sidecar(audit.fc, "07c_emergency_access_check.txt")
    if sidecar is not None:
        unavailable = bool(sidecar.get("skipped"))
        known = bool(sidecar.get("ca_exclusions_known"))
        candidates = int(sidecar.get("break_glass_candidates") or 0)
        excluded_admins = int(sidecar.get("ca_excluded_admins") or 0)
    else:
        text = audit.fc.get("07c_emergency_access_check.txt", "")
        skipped = "skipping check" in text.lower()
        summary = _BREAK_GLASS_SUMMARY.search(text)
        # Optional, absent on older evidence: tells "an excluded admin is in active
        # use" apart from "no admin is excluded".
        excluded = _CA_EXCLUDED_ADMINS.search(text)
        unavailable = _missing_or_error(text) or skipped or summary is None
        known = summary is not None and summary.group(2) == "yes"
        candidates = int(summary.group(1)) if summary is not None else 0
        excluded_admins = int(excluded.group(1)) if excluded is not None else 0
    if unavailable:
        return "info", audit.cannot_verify("cis_gap_break_glass_skipped")
    if not known:
        return "info", audit.cannot_verify("cis_gap_ca_exclusions")
    if candidates > 0:
        return "pass", audit.say("cis_break_glass_found", count=candidates)
    if excluded_admins > 0:
        return "warn", audit.say("cis_break_glass_in_use")
    return "warn", audit.say("cis_break_glass_none")


def _custom_banned_list_active(text: str) -> bool:
    enabled = configured = False
    for line in text.splitlines():
        low = line.lower()
        if "custom banned passwords enabled" in low and ":" in line:
            enabled = line.split(":", 1)[1].strip().lower() in ("true", "yes")
        elif (
            "custom banned passwords" in low
            and ":" in line
            and line.split(":", 1)[1].strip().lower() == "configured"
        ):
            configured = True
    return enabled or configured


def _banned_passwords(audit: _Audit) -> _Verdict:
    # 31_password_protection.txt states the setting explicitly; only an enabled
    # custom list passes.
    text = audit.fc.get("31_password_protection.txt", "")
    # The sidecar is written only when the settings were measured.
    sidecar = _sidecar(audit.fc, "31_password_protection.txt")
    if sidecar is None and _missing_or_error(text):
        return "info", audit.cannot_verify("cis_gap_data")
    if sidecar is None and "were not measured" in text.lower():
        # The section says it could not read the directory settings.
        return "info", audit.cannot_verify("cis_gap_directory_settings")
    if (
        bool(sidecar.get("custom_banned_list_active"))
        if sidecar is not None
        else _custom_banned_list_active(text)
    ):
        return "pass", audit.say("cis_banned_pw_active")
    if _lacks(audit.capabilities, "entra_p1"):
        # The custom list needs Entra ID P1; no configuration clears this without it.
        return "info", audit.not_licensed("cis_lic_banned_pw")
    return "fail", audit.say("cis_banned_pw_default_only")


def _secure_score(audit: _Audit) -> _Verdict:
    ss = audit.secure_score
    # A failed fetch has no pct; reading it as 0 would report a measured FAIL.
    if not ss.get("has_data"):
        return "info", audit.cannot_verify("cis_gap_secure_score")
    pct = ss.get("pct", 0)
    if pct >= 75:
        status = "pass"
    elif pct >= 50:
        status = "partial"
    else:
        status = "fail"
    return status, f"{pct:.0f}%"


def _legacy_auth_blocked(audit: _Audit) -> _Verdict:
    # Entra's tenant-wide block, judged from each CA policy's client-app scope
    # and grant control, never its name. SharePoint's own protocols are 7.2.3.
    ca = audit.ca
    if not ca.get("has_data"):
        return "info", audit.cannot_verify("cis_gap_ca")
    if not ca.get("has_client_app_data"):
        # Audits from before the client-app scope was collected.
        return "info", audit.cannot_verify("cis_gap_client_app_scope")
    if ca.get("blocks_legacy_auth"):
        return "pass", audit.say("cis_legacy_blocked")
    return "fail", audit.say("cis_legacy_not_blocked")


def _security_defaults(text: str) -> str:
    for line in text.splitlines():
        if "security defaults" in line.lower() and ":" in line:
            return line.split(":", 1)[1].strip().lower()
    return ""


def _baseline_sign_in(audit: _Audit) -> _Verdict:
    # Security Defaults off is correct once Conditional Access is in place, so
    # the CA count is part of the verdict.
    sidecar = _sidecar(audit.fc, "31b_smart_lockout.txt")
    if sidecar is not None:
        enabled = sidecar.get("security_defaults_enabled")
        sd = "" if enabled is None else str(enabled).lower()
    else:
        sd = _security_defaults(audit.fc.get("31b_smart_lockout.txt", ""))
    ca = audit.ca
    if sd not in ("true", "false"):
        return "info", audit.cannot_verify("cis_gap_security_defaults")
    if sd == "true":
        return "pass", audit.say("cis_sd_enabled")
    if not ca.get("has_data"):
        # Off, with the CA side unknown: no verdict either way.
        return "info", audit.cannot_verify("cis_gap_sd_off_ca_unknown")
    if ca.get("enabled", 0) > 0:
        return "pass", audit.say("cis_sd_off_ca_active", count=ca.get("enabled"))
    return "fail", audit.say("cis_sd_off_no_ca")


def _access_reviews(audit: _Audit) -> _Verdict:
    text = audit.fc.get("07d_access_reviews.txt", "")
    sidecar = _sidecar(audit.fc, "07d_access_reviews.txt")
    reviews = int(sidecar.get("count") or 0) if sidecar is not None else _parse_banner_count(text)
    if sidecar is None and _missing_or_error(text):
        return "info", audit.cannot_verify("cis_gap_access_reviews")
    if reviews:
        return "pass", audit.say("cis_access_reviews_found", count=reviews)
    if _lacks(audit.capabilities, "entra_p2"):
        # Without an assigned P2 seat there is nothing to configure.
        return "info", audit.not_licensed("cis_lic_access_reviews")
    return "warn", audit.say("cis_access_reviews_none")


def _colon_settings(text: str) -> dict[str, str]:
    settings = {}
    for line in text.splitlines():
        if ":" in line and not line.strip().startswith("="):
            key, value = line.split(":", 1)
            settings[key.strip().lower()] = value.strip().lower()
    return settings


def _cross_tenant_access(audit: _Audit) -> _Verdict:
    # Allowed B2B collaboration is how most organisations work, not a finding.
    # Two things are: direct connect inbound (external organisations in Teams
    # shared channels without a guest account), and a tenant still on
    # Microsoft's system default, which has never decided anything here.
    text = audit.fc.get("18c_cross_tenant_access_policy.txt", "")
    sidecar = _sidecar(audit.fc, "18c_cross_tenant_access_policy.txt")
    if sidecar is not None:
        # As the text spells them, lower-cased, with "n/a" for a value Graph
        # did not give.
        def spelled(value) -> str:
            return "n/a" if value is None else str(value).lower()

        direct_in = spelled(sidecar.get("b2b_direct_connect_inbound"))
        system_default = spelled(sidecar.get("is_service_default"))
    else:
        settings = _colon_settings(text)
        direct_in = settings.get("b2b direct connect in", "")
        system_default = settings.get("system default", "")
    if (sidecar is None and _missing_or_error(text)) or not direct_in:
        return "info", audit.cannot_verify("cis_gap_cross_tenant")
    if direct_in == "allowed":
        return "warn", audit.say("cis_xt_direct_in_allowed")
    if system_default == "true":
        return "warn", audit.say("cis_xt_system_default")
    return "pass", audit.say("cis_xt_configured")


# ── Applications ──────────────────────────────────────────────────────────────


def _third_party_apps(audit: _Audit) -> _Verdict:
    oauth = audit.oauth
    grants = oauth.get("total_grants", 0)
    apps = oauth.get("unique_apps", 0)
    app_regs = oauth.get("app_registrations", 0)
    high_priv = len(oauth.get("high_privilege_apps", []))
    if high_priv > 5:
        return "warn", audit.t(
            "cis_oauth_warn", apps=apps, grants=grants, high_priv=high_priv, app_regs=app_regs
        )
    return "info", audit.t("cis_oauth_info", apps=apps, grants=grants, app_regs=app_regs)


_CREDENTIAL_SUMMARY = re.compile(r"(\d+)\s+expired\s*,\s*(\d+)\s+expiring", re.IGNORECASE)


def _app_credentials(audit: _Audit) -> _Verdict:
    # The 17c sidecar's counts first, where the run has them. Without it, the
    # WARN file exists only when there is something to warn about, so its
    # absence is a clean result only if the app-registrations section ran.
    counts = _app_credential_counts(audit.fc)
    warn = audit.fc.get("17c_app_credential_expiry_WARN.txt", "")
    if counts is None and not warn.strip():
        if not _section_ran(audit.fc, "17_app_registrations.txt"):
            return "info", audit.cannot_verify("cis_gap_app_registrations")
        return "pass", audit.say("cis_app_creds_none_expired")
    if counts is None:
        # The collector's summary line, not "expired" anywhere: the banner says it too.
        m = _CREDENTIAL_SUMMARY.search(warn)
        counts = (int(m.group(1)) if m else 0, int(m.group(2)) if m else 0)
    expired, expiring = counts
    if expired > 0:
        return "fail", audit.say("cis_app_creds_expired", count=expired)
    if expiring > 0:
        # The collector's own rule, fewer than EXPIRY_SOON_DAYS whole days
        # left, not the "at most 30" this used to print over its count.
        return "warn", audit.say("cis_app_creds_expiring", count=expiring, days=EXPIRY_SOON_DAYS)
    return "pass", audit.say("cis_app_creds_none_expired")


# ── Data protection, SharePoint & OneDrive ────────────────────────────────────
#
# The Purview controls are gated on the parsed count, never on the text: an
# empty section is written as a "(none)" block, which is non-empty text.


def _dlp_policies(audit: _Audit) -> _Verdict:
    text = audit.fc.get("19d_purview_dlp_policies.txt", "")
    count = _purview_count(audit.purview, "dlp_policies")
    found = count > 0 or ("enabled" in text.lower() and "enforce" in text.lower())
    return _found_or_gap(
        audit,
        found,
        "19d_purview_dlp_policies.txt",
        audit.say("cis_dlp_count", count=count) if count else audit.say("cis_dlp_found"),
        audit.say("cis_dlp_none"),
        "cis_gap_dlp",
    )


def _sensitivity_labels(audit: _Audit) -> _Verdict:
    count = _purview_count(audit.purview, "sensitivity_labels")
    return _found_or_gap(
        audit,
        count > 0,
        "19c_purview_sensitivity_labels.txt",
        audit.say("cis_labels_count", count=count),
        audit.say("cis_labels_none"),
        "cis_gap_labels",
    )


def _retention_policies(audit: _Audit) -> _Verdict:
    count = _purview_count(audit.purview, "retention_policies")
    return _found_or_gap(
        audit,
        count > 0,
        "19e_purview_retention_policies.txt",
        audit.say("cis_retention_count", count=count),
        audit.say("cis_retention_none"),
        "cis_gap_retention",
    )


def _onedrive_scan_gaps(audit: _Audit, scan: dict) -> list[str] | None:
    """What kept the sharing scan from covering the tenant; None if nothing did."""
    refused, discovery, folders = scan["refused"], scan["discovery"], scan["folders"]
    scope = scan["scope"]
    if scope.startswith("complete") and refused == 0 and discovery == 0 and folders == 0:
        return None
    gaps = []
    if refused:
        gaps.append(audit.say("cis_od_gap_refused", count=refused))
    if discovery:
        gaps.append(audit.say("cis_od_gap_discovery", count=discovery))
    if folders:
        gaps.append(audit.say("cis_od_gap_folders", count=folders))
    if scope and not scope.startswith("complete"):
        gaps.append(audit.say("cis_od_gap_limit"))
    return gaps


def _anonymous_links(audit: _Audit) -> _Verdict:
    # An "Anyone" link needs no sign-in, so one is a finding however partial the
    # scan was; but a zero is only as broad as the scan behind it.
    scan = _onedrive_scan(audit.fc)
    anyone = scan["anyone"]
    gaps = _onedrive_scan_gaps(audit, scan)
    scanned = scan["scanned"]
    if anyone is None:
        return "info", audit.cannot_verify("cis_gap_onedrive")
    if anyone == 0 and gaps is not None:
        joined = audit.say("cis_joiner_and").join(gaps) or audit.say("cis_od_scope_unknown")
        return "info", audit.say("cis_od_partial", gaps=joined)
    if anyone == 0:
        return "pass", audit.say("cis_od_none", count=scanned)
    return "fail", audit.say("cis_od_anyone", count=anyone)


def _sharepoint_legacy_auth(audit: _Audit) -> _Verdict:
    # legacy_auth defaults to False when the admin settings were never read, so
    # it means nothing without has_data and legacy_auth_known.
    sp = audit.sharepoint
    if not sp.get("has_data"):
        return "info", audit.cannot_verify("cis_gap_sp_tenant")
    if not sp.get("legacy_auth_known"):
        return "info", audit.cannot_verify("cis_gap_field_not_collected")
    if sp.get("legacy_auth"):
        return "fail", audit.t.cis_legacy_auth_enabled
    return "pass", audit.t.cis_legacy_auth_disabled


def _sharepoint_sharing(audit: _Audit) -> _Verdict:
    # has_data is true once the site list parsed; the sharing level comes from
    # the separate admin-settings file, and "unknown" means it was not read.
    sp, t = audit.sharepoint, audit.t
    if not sp.get("has_data") or sp.get("sharing_level") == "unknown":
        return "info", audit.cannot_verify("cis_gap_sp_settings")
    level = sp.get("sharing_level", "")
    raw = (sp.get("sharing") or "").lower().replace(" ", "")
    if level == "ok":
        return "pass", sp.get("sharing_label", "")
    if raw == "externaluserandguestsharing":
        # Anyone-with-the-link is the opposite of managed external sharing.
        return "fail", sp.get("sharing_label", t.cis_sp_open)
    return "warn", sp.get("sharing_label", t.cis_sp_open)


# ── Email ─────────────────────────────────────────────────────────────────────


def _mailbox_audit(audit: _Audit) -> _Verdict:
    text = audit.fc.get("27c_exchange_org_config.txt", "")
    disabled = _setting(
        audit.fc, "27c_exchange_org_config.txt", "AuditDisabled", first_line_only=False
    )
    if disabled is False:
        return "pass", audit.say("cis_mailbox_audit_on")
    if disabled is True:
        return "fail", audit.say("cis_mailbox_audit_off")
    if text.strip():
        return "info", audit.say("cis_mailbox_audit_unclear")
    # Every other control with nothing to read says so in an info row; this
    # one used to drop out of the report instead.
    return "info", audit.cannot_verify("cis_gap_exo_org_config")


def _policy_count(audit: _Audit, file: str, found: str, none: str, gap: str) -> _Verdict:
    """*found* takes the count; *none* and *gap* are keys as they are."""
    # A section that ran and lists no policies is a reading of an unprotected
    # tenant; a section that did not run is no reading at all.
    if not _section_ran(audit.fc, file):
        return "info", audit.cannot_verify(gap)
    count = _record_count(audit.fc, file)
    if count > 0:
        return "pass", audit.say(found, count=count)
    return "fail", audit.say(none)


def _antiphish(audit: _Audit) -> _Verdict:
    return _policy_count(
        audit,
        "23_exchange_antiphish.txt",
        "cis_antiphish_found",
        "cis_antiphish_none",
        "cis_gap_antiphish",
    )


def _antispam(audit: _Audit) -> _Verdict:
    return _policy_count(
        audit,
        "24_exchange_antispam.txt",
        "cis_antispam_found",
        "cis_antispam_none",
        "cis_gap_antispam",
    )


def _external_forwarding(audit: _Audit) -> _Verdict:
    # The findings are in the *_WARN files. 28_ and 29_ are written whenever
    # the check runs and list internal forwarding too (29_ in older runs was
    # the all-clear result), so those two only show that the check ran.
    fc = audit.fc
    external = fc.get("28b_exchange_external_forwarding_WARN.txt", "")
    inbox_rules = fc.get("29_exchange_inbox_rules_external_fwd_WARN.txt", "")
    if external.strip() or inbox_rules.strip():
        return "warn", audit.say("cis_fwd_external")
    # A target the run could not place inside or outside the tenant is
    # neither a finding nor a pass.
    unverified = [
        audit.say(key, count=n)
        for n, key in (
            (_unverified_forwarding_count(fc), "cis_fwd_unverified_mailboxes"),
            (_inbox_rule_counts(fc)["unverified"], "cis_fwd_unverified_rules"),
        )
        if n
    ]
    if unverified:
        what = audit.say("cis_joiner_and").join(unverified)
        return "info", audit.cannot_verify("cis_fwd_unverified", what=what)
    if _section_ran(
        fc, "28_exchange_mailbox_forwarding.txt", "29_exchange_inbox_rules_external_fwd.txt"
    ):
        return "pass", audit.say("cis_fwd_none")
    return "info", audit.cannot_verify("cis_gap_forwarding")


def _defender_policy(audit: _Audit, kind: str, label: str) -> _Verdict:
    """Safe Links / Safe Attachments: on, present but off, unlicensed, absent, unknown."""
    state = _defender_policies(audit.fc)[kind]
    enabled = state["enabled"]
    if enabled > 0:
        return "pass", audit.say("cis_defender_active", count=enabled, policy=label)
    if state["present"]:
        return "fail", audit.say("cis_defender_disabled", policy=label)
    if _lacks(audit.capabilities, "defender_office"):
        # Not in the tenant's SKUs: the absence is the licence, not the setup.
        return "info", audit.not_licensed("cis_lic_defender", policy=label)
    if _section_ran(audit.fc, "27_exchange_defender_policies.txt"):
        return "warn", audit.say("cis_defender_none", policy=label)
    return "info", audit.cannot_verify("cis_gap_defender_policies")


# Enabled counts come from the parsed policy blocks: a policy named "Safe Links"
# can be switched off.


def _safe_links(audit: _Audit) -> _Verdict:
    return _defender_policy(audit, "safe_links", "Safe Links")


def _safe_attachments(audit: _Audit) -> _Verdict:
    return _defender_policy(audit, "safe_attachments", "Safe Attachments")


# Per-domain checks. A failed DNS lookup comes back as "ERROR (...)", never as
# "MISSING", and is cannot-verify rather than an absent record.


def _spf(audit: _Audit, record: dict, domain: str) -> _Verdict:
    spf = record.get("spf", "")
    unresolved = spf.strip().upper().startswith("ERROR")
    if "OK" in spf:
        return "pass", spf
    if unresolved:
        return "info", audit.cannot_verify("cis_gap_spf_lookup", domain=domain, result=spf)
    return "fail", spf or audit.t.cis_spf_missing


def _dmarc(audit: _Audit, record: dict, domain: str) -> _Verdict:
    dmarc = record.get("dmarc", "")
    published = record.get("dmarc_record", "")
    detail = dmarc
    if published and published != "(none)":
        detail = f"{dmarc}: {published}" if dmarc else published
    if "reject" in dmarc.lower():
        return "pass", detail
    if "quarantine" in dmarc.lower():
        return "partial", detail
    if "p=none" in dmarc.lower() or "p=none" in published.lower():
        return "partial", (
            audit.say("cis_dmarc_monitor_only", record=published) if published else dmarc
        )
    if dmarc.strip().upper().startswith("ERROR"):
        return "info", audit.cannot_verify("cis_gap_dmarc_lookup", domain=domain, result=dmarc)
    return "fail", dmarc or audit.t.cis_dmarc_missing


def _dkim(audit: _Audit, record: dict, domain: str) -> _Verdict:
    """DKIM for one mail domain: is its mail signed by whoever sends it?

    The control used to pass on a CNAME anywhere in the DNS summary, so a
    Mailchimp k1 CNAME passed an Exchange DKIM control, and M365 selectors
    published in DNS passed it with signing switched off in Exchange. Its
    branch for a third-party key looked for "k=rsa", which the collector never
    writes ("TXT present"), so a Google key failed. It now decides on who
    sends the domain's mail: Exchange Online's own signing config (25), or a
    third party's key for a domain whose SPF record (26) says that third
    party sends its mail. The sidecar and the text give the same records.
    """
    signs = _exchange_signs(_exchange_dkim_configs(audit.fc), domain)
    if signs:
        return "pass", audit.say("cis_dkim_exchange_signs", domain=domain)
    senders = _spf_senders(record)
    if senders == {"none"}:
        return "pass", audit.say("cis_dkim_no_mail", domain=domain)
    keys = _third_party_dkim(record)
    if senders and "exchange" not in senders:
        # The data names who sends the domain's mail, and it is not Exchange.
        signed = [(name, selector) for name, selector in keys if name in senders]
        if signed:
            name, selector = signed[0]
            return "pass", audit.say(
                "cis_dkim_third_party_signs", domain=domain, name=name, selector=selector
            )
        return "warn", audit.say(
            "cis_dkim_third_party_unsigned", domain=domain, senders=", ".join(sorted(senders))
        )
    # Exchange sends the domain's mail, or the data does not say who does.
    detail = audit.say("cis_dkim_exchange_not_signing", domain=domain)
    if signs is None:
        # Exchange's signing config was not collected. DNS can still say no:
        # without the M365 selectors published, Exchange cannot sign with the
        # domain. Published, they say only that signing was set up, not that
        # it was switched on. Only the M365 selectors decide here: the others
        # are guessed third-party names, and a blip there must not hide a miss.
        dkim1 = str(record.get("dkim1") or "")
        m365 = [_dkim_selectors(record).get(s) for s in ("selector1", "selector2")]
        if "error" in dkim1.lower():
            return "info", audit.cannot_verify("cis_gap_dkim_lookup", domain=domain, result=dkim1)
        if any(s and _key_published(s) for s in m365):
            return "info", audit.cannot_verify("cis_gap_dkim_not_fetched", domain=domain)
        if not all(s == "MISSING" for s in m365):
            return "info", audit.cannot_verify("cis_gap_dkim_unchecked")
        detail = audit.say("cis_dkim_no_m365_selectors", domain=domain)
    if keys:
        names = ", ".join(sorted({name for name, _ in keys}))
        scope = "cis_dkim_key_scope_exchange_too" if senders else "cis_dkim_key_scope"
        detail = audit.say(scope, detail=detail, names=names)
    # Exchange Online does not sign this domain's mail: the control's own
    # question answered no, graded like a missing SPF or DMARC record.
    return "fail", detail


def dkim_status_by_domain(context: dict) -> dict[str, str]:
    """CIS 5.2.3's status for each mail domain, for a table that shows DKIM per domain.

    The customer report's email table judged DKIM itself, "found" unless every
    selector summary said MISSING somewhere, so it could print "Found" beside
    a 5.2.3 that warned signing was off, on the same page.
    """
    audit = _Audit.of(context, T("no"))
    return {
        str(record.get("domain") or ""): _dkim(audit, record, str(record.get("domain") or ""))[0]
        for record in audit.spf_dmarc
        if isinstance(record, dict)
    }


# ── Devices ───────────────────────────────────────────────────────────────────


def _device_compliance(audit: _Audit) -> _Verdict:
    # The control asks whether compliance policies are configured, not how many
    # devices currently meet them.
    intune, t = audit.intune, audit.t
    text = audit.fc.get("11_intune_compliance_policies.txt", "")
    # The sidecar's count when the run wrote one. A refused read writes none,
    # and is written as a "(not available)" block with prose in it; counting
    # its lines as policies would turn "not allowed to look" into "policies
    # are configured".
    sidecar = _sidecar(audit.fc, "11_intune_compliance_policies.txt")
    unreadable = sidecar is None and _evidence_unavailable(text)
    if sidecar is not None:
        policy_count = int(sidecar.get("count") or 0)
    else:
        policy_count = 0 if unreadable else _count_data_lines(text)
    has_policies = policy_count > 0
    has_devices = intune.get("has_data") and intune.get("total", 0) > 0
    if intune.get("unavailable") and not has_policies:
        # The collector's own words for the refusal, when it gave any.
        reason = intune.get("unavailable_reason")
        if reason:
            return "info", audit.say("cis_cannot_verify", reason=reason)
        return "info", audit.cannot_verify("cis_gap_intune")
    if not has_policies and not has_devices and intune.get("entra_total", 0) > 0:
        # Devices the directory knows and Intune manages none of: every endpoint
        # sits outside compliance management.
        return "fail", t("cis_entra_devices_unmanaged", total=intune["entra_total"])
    if not has_policies and not has_devices:
        return "info", t.cis_no_intune
    if not has_policies and unreadable:
        return "info", audit.cannot_verify("cis_gap_intune_policies")
    if not has_policies:
        # With no policy to evaluate, device compliance is undefined.
        return "fail", audit.say("cis_devices_no_policies")
    if not has_devices:
        return "pass", audit.say("cis_policies_no_devices", count=policy_count)
    pct = intune.get("compliance_pct", 0)
    if pct >= 90:
        return "pass", t("cis_compliance_pct", pct=pct)
    return "partial", t(
        "cis_compliance_partial", pct=pct, noncompliant=intune.get("noncompliant", 0)
    )


# ── Teams ─────────────────────────────────────────────────────────────────────

_RESTRICTED = ("block", "disabl", "none", "restrict", "denied")


def _teams_b2b_verdict(audit: _Audit, collab: str, direct: str) -> _Verdict:
    # Graded per access type: Microsoft's default blocks Direct Connect while
    # allowing collaboration, so "blocked" is in almost every file. Direct
    # Connect inbound open grants shared-channel trust and fails; open
    # collaboration with Direct Connect restricted warns.
    collab_open = bool(collab) and not any(k in collab.lower() for k in _RESTRICTED)
    direct_open = bool(direct) and not any(k in direct.lower() for k in _RESTRICTED)
    if direct_open:
        return "fail", audit.say("cis_teams_direct_open")
    if collab_open:
        return "warn", audit.say("cis_teams_collab_open")
    return "pass", audit.say("cis_teams_restricted")


def _teams_access_from_text(audit: _Audit, text: str) -> _Verdict:
    # Older federation-style output, or partner configurations only.
    low = text.lower()
    if "blocked" in low or "disabled" in low:
        return "pass", audit.say("cis_teams_restricted")
    if "allowed for all" in low or "everyone" in low or "no restrictions" in low:
        return "fail", audit.say("cis_teams_unrestricted")
    return "warn", audit.say("cis_teams_limited")


def _teams_external_access(audit: _Audit) -> _Verdict:
    access = _teams_cross_tenant(audit.fc)
    if access is None:
        return "info", audit.cannot_verify("cis_gap_teams_external")
    collab, direct, partners = access["collab"], access["direct"], access["partners"]
    if not collab and not direct and partners is None:
        # Every access type N/A and no partner configurations: the policy was
        # not returned, or the tenant is on defaults. No evidence either way.
        return "info", audit.cannot_verify("cis_gap_teams_policy_default")
    if collab or direct:
        return _teams_b2b_verdict(audit, collab, direct)
    return _teams_access_from_text(audit, partners)


def _teams_guest_access(audit: _Audit) -> _Verdict:
    # Read from the Teams section's guest file, where teams_policies.py has
    # already mapped the Graph values to readable names.
    invites, role = _teams_guest_settings(audit.fc)
    if not invites:
        return "info", audit.cannot_verify("cis_gap_guest_settings")
    detail = audit.say(
        "cis_guest_settings", invites=invites, role=role or audit.say("cis_guest_role_unknown")
    )
    if "same as member" in role.lower():
        # Worse than any invitation setting: whoever gets in sees what a member sees.
        return "fail", audit.say("cis_guest_same_as_member", detail=detail)
    if invites.lower().startswith("everyone"):
        return "fail", audit.say("cis_guest_can_invite", detail=detail)
    if "member" in invites.lower():
        return "warn", audit.say("cis_guest_members_invite", detail=detail)
    return "pass", detail


# ── Logging & monitoring ──────────────────────────────────────────────────────


def _unified_audit_log(audit: _Audit) -> _Verdict:
    # The Exchange/Purview ingestion toggle from Get-AdminAuditLogConfig. The
    # Entra directory audit log is always on and says nothing about it.
    enabled = _setting(
        audit.fc,
        "27d_exchange_admin_audit_log_config.txt",
        "UnifiedAuditLogIngestionEnabled",
        first_line_only=True,
    )
    if enabled is True:
        return "pass", audit.say("cis_ual_on")
    if enabled is False:
        return "fail", audit.say("cis_ual_off")
    return "info", audit.cannot_verify("cis_gap_ual")


def _defender_alerts(audit: _Audit) -> _Verdict:
    text = audit.fc.get("19b_defender_active_alerts.txt", "")
    sidecar = _sidecar(audit.fc, "19b_defender_active_alerts.txt")
    if sidecar is not None:
        open_alerts = int(sidecar.get("count") or 0)
    else:
        # Rows are counted rather than a phrase matched; the header's wording varies.
        open_alerts = _count_data_lines(text) if text.strip() else 0
    if open_alerts > 0:
        return "warn", audit.say("cis_defender_alerts_open", count=open_alerts)
    # An empty alerts file means "no alerts" only if the query ran.
    if sidecar is not None or _section_ran(
        audit.fc, "19b_defender_alert_count.txt", "19b_defender_active_alerts.txt"
    ):
        return "pass", audit.say("cis_defender_alerts_none")
    return "info", audit.cannot_verify("cis_gap_defender_alerts")


def _risky_user_rows(text: str) -> tuple[int, int]:
    """(rows, high- or medium-risk rows) in the "upn  risk-level  state" table."""
    users = _risky_users_from_text(text)
    return len(users), sum(1 for u in users if u["level"].lower() in ("high", "medium"))


def _risky_users(audit: _Audit) -> _Verdict:
    # Structured rows, not the word "high" anywhere in the file.
    raw = audit.context.get("risky_users")
    text = raw if isinstance(raw, str) else ""
    users = _risky_users_from_sidecar(audit.fc)
    if users is None and _evidence_unavailable(text):
        return "info", audit.cannot_verify("cis_gap_risky_users")
    if users is not None:
        rows = len(users)
        high = sum(1 for u in users if u["level"].lower() in ("high", "medium"))
    else:
        rows, high = _risky_user_rows(text)
    if high > 0:
        return "fail", audit.say("cis_risky_high", count=high)
    if rows > 0:
        return "warn", audit.say("cis_risky_low", count=rows)
    return "pass", audit.say("cis_risky_none")


# ── The controls, in report order ─────────────────────────────────────────────

_IDENTITY = "cis_cat_identity"
_GENERAL = "cis_cat_general"
_APPLICATIONS = "cis_cat_applications"
_DATA = "cis_cat_data"
_EMAIL = "cis_cat_email"
_DEVICES = "cis_cat_devices"
_TEAMS = "cis_cat_teams"
_LOGGING = "cis_cat_logging"

_CONTROLS: tuple[_Control | _PerDomain, ...] = (
    _Control(
        "1.1.1",
        "Ensure MFA is enabled for all users",
        _IDENTITY,
        nist="PR.AA-01",
        iso="A.8.5",
        check=_mfa,
    ),
    _Control(
        "1.1.2",
        "Ensure phishing-resistant MFA methods are enabled",
        _IDENTITY,
        nist="PR.AA-03",
        iso="A.8.5",
        check=_phishing_resistant_mfa,
    ),
    _Control(
        "1.1.3",
        "Ensure fewer than 5 Global Admins",
        _IDENTITY,
        nist="PR.AA-05",
        iso="A.5.15",
        check=_global_admins,
    ),
    _Control(
        "1.1.4",
        "Ensure Conditional Access policies are configured",
        _IDENTITY,
        nist="PR.AA-01",
        iso="A.8.3",
        check=_conditional_access,
    ),
    _Control(
        "1.1.5",
        "Ensure PIM is used for privileged role activation",
        _IDENTITY,
        nist="PR.AA-05",
        iso="A.5.18",
        check=_pim,
    ),
    _Control(
        "1.1.6",
        "Ensure emergency access accounts are configured",
        _IDENTITY,
        nist="PR.AA-01",
        iso="A.5.16",
        check=_emergency_access,
    ),
    _Control(
        "1.2.1",
        "Ensure custom banned passwords are configured",
        _IDENTITY,
        nist="PR.AA-03",
        iso="A.8.5",
        check=_banned_passwords,
    ),
    _Control(
        "1.4",
        "Ensure Microsoft Secure Score is above 75%",
        _GENERAL,
        nist="ID.RA-01",
        iso="A.8.8",
        check=_secure_score,
    ),
    _Control(
        "2.1",
        "Ensure third-party apps are reviewed",
        _APPLICATIONS,
        nist="PR.AA-05",
        iso="A.8.3",
        check=_third_party_apps,
    ),
    _Control(
        "2.1.2",
        "Ensure app credentials are not expired",
        _APPLICATIONS,
        nist="PR.AA-01",
        iso="A.5.16",
        check=_app_credentials,
    ),
    _Control(
        "3.1.1",
        "Ensure DLP policies are configured",
        _DATA,
        nist="PR.DS-10",
        iso="A.8.12",
        check=_dlp_policies,
    ),
    _Control(
        "3.2.1",
        "Ensure sensitivity labels are published",
        _DATA,
        nist="PR.DS-02",
        iso="A.5.14",
        check=_sensitivity_labels,
    ),
    _Control(
        "4.1",
        "Ensure mailbox audit logging is enabled",
        _EMAIL,
        nist="PR.PS-04",
        iso="A.8.16",
        check=_mailbox_audit,
    ),
    _Control(
        "4.2",
        "Ensure anti-phishing policies are configured",
        _EMAIL,
        nist="PR.DS-02",
        iso="A.8.24",
        check=_antiphish,
    ),
    _Control(
        "4.3",
        "Ensure anti-spam policies are configured",
        _EMAIL,
        nist="PR.PS-05",
        iso="A.8.7",
        check=_antispam,
    ),
    _Control(
        "4.4",
        "Ensure mail forwarding to external domains is restricted",
        _EMAIL,
        nist="PR.DS-02",
        iso="A.5.14",
        check=_external_forwarding,
    ),
    _Control(
        "4.5",
        "Ensure Safe Links is enabled",
        _EMAIL,
        nist="DE.CM-09",
        iso="A.8.7",
        check=_safe_links,
    ),
    _Control(
        "4.6",
        "Ensure Safe Attachments is enabled",
        _EMAIL,
        nist="DE.CM-09",
        iso="A.8.7",
        check=_safe_attachments,
    ),
    _Control(
        "5.1.1",
        "Ensure legacy authentication is blocked",
        _IDENTITY,
        nist="PR.AA-03",
        iso="A.8.5",
        check=_legacy_auth_blocked,
    ),
    _Control(
        "1.1.7",
        "Ensure baseline sign-in protection is in place",
        _IDENTITY,
        nist="PR.AA-03",
        iso="A.8.5",
        check=_baseline_sign_in,
    ),
    _Control(
        "1.1.8",
        "Ensure access reviews are configured",
        _IDENTITY,
        nist="PR.AA-05",
        iso="A.5.18",
        check=_access_reviews,
    ),
    _Control(
        "1.1.9",
        "Ensure cross-tenant access settings are reviewed",
        _IDENTITY,
        nist="PR.AA-05",
        iso="A.5.14",
        check=_cross_tenant_access,
    ),
    _Control(
        "7.2.4",
        "Ensure anonymous sharing links are not in use",
        _DATA,
        nist="PR.AA-05",
        iso="A.5.14",
        check=_anonymous_links,
    ),
    _Control(
        "7.2.3",
        "Ensure legacy authentication protocols are disabled in SharePoint",
        _DATA,
        nist="PR.AA-03",
        iso="A.8.5",
        check=_sharepoint_legacy_auth,
    ),
    _PerDomain(
        (
            _Control(
                "5.2.1",
                "Ensure SPF is configured",
                _EMAIL,
                nist="PR.DS-02",
                iso="A.5.14",
                check=_spf,
            ),
            _Control(
                "5.2.2",
                "Ensure DMARC is configured",
                _EMAIL,
                nist="PR.DS-02",
                iso="A.5.14",
                check=_dmarc,
            ),
            _Control(
                "5.2.3",
                "Ensure DKIM is enabled",
                _EMAIL,
                nist="PR.DS-02",
                iso="A.8.24",
                check=_dkim,
            ),
        )
    ),
    _Control(
        "6.1.1",
        "Ensure device compliance policies are configured",
        _DEVICES,
        nist="PR.AA-05",
        iso="A.8.1",
        check=_device_compliance,
    ),
    _Control(
        "7.2.1",
        "Ensure SharePoint external sharing is managed",
        _DATA,
        nist="PR.AA-05",
        iso="A.5.14",
        check=_sharepoint_sharing,
    ),
    _Control(
        "7.2.2",
        "Ensure data retention policies are configured",
        _DATA,
        nist="PR.DS-01",
        iso="A.8.12",
        check=_retention_policies,
    ),
    # The M365 benchmark has no backup control. CIS Controls v8 safeguard 11.2,
    # "Perform automated backups", is the nearest CIS reference; the id names
    # the framework so the row is not read as an M365 benchmark number. The
    # verdict is formed in parsers/m365_backup.py from 34_m365_backup.
    _Control(
        "CIS v8 11.2",
        "Ensure Microsoft 365 data is backed up",
        _DATA,
        nist="PR.DS-11",
        iso="A.8.13",
        check=m365_backup_control,
    ),
    _Control(
        "8.1.1",
        "Ensure external access in Teams is managed",
        _TEAMS,
        nist="PR.AA-05",
        iso="A.5.14",
        check=_teams_external_access,
    ),
    _Control(
        "8.1.2",
        "Ensure Teams guest access is restricted",
        _TEAMS,
        nist="PR.AA-05",
        iso="A.5.14",
        check=_teams_guest_access,
    ),
    _Control(
        "9.1",
        "Ensure unified audit logging is enabled",
        _LOGGING,
        nist="PR.PS-04",
        iso="A.8.15",
        check=_unified_audit_log,
    ),
    _Control(
        "9.2",
        "Ensure security alerts are monitored",
        _LOGGING,
        nist="DE.AE-03",
        iso="A.8.16",
        check=_defender_alerts,
    ),
    _Control(
        "9.3",
        "Ensure risky user detections are investigated",
        _LOGGING,
        nist="RS.AN-03",
        iso="A.5.28",
        check=_risky_users,
    ),
)


def _all_controls() -> Iterator[_Control]:
    for entry in _CONTROLS:
        yield from (entry,) if isinstance(entry, _Control) else entry.controls


# The cross-references by CIS id, for readers that look one control up.
_FRAMEWORK_MAP: dict[str, dict[str, str]] = {
    c.cis_id: {
        "nist_id": c.nist,
        "nist_name": _NIST_NAMES[c.nist],
        "iso_id": c.iso,
        "iso_name": _ISO_NAMES[c.iso],
    }
    for c in _all_controls()
}
