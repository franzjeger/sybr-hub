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
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.reports.evidence import (
    _CANNOT_VERIFY,
    _EVIDENCE_MAP,
    _NOT_LICENSED,
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
)
from app.reports.parsers.collaboration import (
    _app_credential_counts,
    _onedrive_scan,
    _teams_cross_tenant,
    _teams_guest_settings,
)
from app.reports.parsers.common import _record_count, _sidecar
from app.reports.parsers.email import _defender_policies

# Names shown next to the ids, so the cross-reference columns are readable.
_NIST_NAMES = {
    "ID.RA-01": "Vulnerabilities in assets are identified, validated, and recorded",
    "PR.AA-01": "Identities and credentials are managed",
    "PR.AA-03": "Users, services, and hardware are authenticated",
    "PR.AA-05": "Access permissions are managed, enforced, and reviewed",
    "PR.DS-01": "Data-at-rest is protected",
    "PR.DS-02": "Data-in-transit is protected",
    "PR.DS-10": "Data-in-use is protected",
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
    audit: _Audit, found: bool, file: str, found_detail: str, none_detail: str, gap_detail: str
) -> _Verdict:
    """Pass when found; warn when the section ran and found none; else cannot verify."""
    if found:
        return "pass", found_detail
    if _section_ran(audit.fc, file):
        return "warn", none_detail
    return "info", _CANNOT_VERIFY + gap_detail


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
        return "info", _CANNOT_VERIFY + "autentiseringsmetode-policy utilgjengelig"
    enabled = _phishing_resistant_methods(text, sidecar)
    if enabled:
        return "pass", f"Phishing-resistant metoder aktivert: {', '.join(enabled)}"
    return (
        "warn",
        "Ingen phishing-resistant metoder (FIDO2 / Windows Hello / "
        "x509Certificate) er aktivert i autentiseringsmetode-policyen",
    )


def _global_admins(audit: _Audit) -> _Verdict:
    admin, t = audit.admin_roles, audit.t
    if not admin.get("has_data"):
        return "info", _CANNOT_VERIFY + "admin-rolle data utilgjengelig"
    ga = admin.get("global_admin_count", 0)
    if 2 <= ga <= 4:
        return "pass", t("cis_ga_count", count=ga)
    if ga > 4:
        return "fail", t("cis_ga_too_many", count=ga)
    if ga == 1:
        return "warn", t("cis_ga_too_few", count=ga)
    # Role data but no standing Global Admin: typically PIM/JIT, where every
    # Global Admin is eligible only. Not verifiable from here, so not omitted.
    return "info", "Ingen faste Global Admin-tildelinger funnet. Verifiser PIM/JIT-oppsettet"


def _conditional_access(audit: _Audit) -> _Verdict:
    ca = audit.ca
    if ca.get("has_data") and ca.get("enabled", 0) > 0:
        return "pass", audit.t("cis_active_policies", count=ca["enabled"])
    if ca.get("has_data"):
        return "fail", audit.t.cis_no_active_ca
    return "info", _CANNOT_VERIFY + "audit-data utilgjengelig"


def _pim(audit: _Audit) -> _Verdict:
    text = audit.fc.get("07b_pim_eligible_assignments.txt", "")
    # The banner's own count: the header is written even with no assignments,
    # and counting lines would count the column header.
    count = _parse_banner_count(text)
    if _missing_or_error(text):
        return "info", _CANNOT_VERIFY + "PIM-data utilgjengelig"
    if count is not None and count > 0:
        return "pass", f"{count} PIM-berettigede rolletildelinger funnet"
    if _lacks(audit.capabilities, "entra_p2"):
        # Without an assigned P2 seat there is nothing to configure.
        return "info", _NOT_LICENSED + "PIM krever Entra ID P2, som ikke er tildelt noen bruker"
    return "warn", "Ingen PIM-tildelinger funnet, så roller kan være permanent tildelt"


_BREAK_GLASS_SUMMARY = re.compile(r"break_glass_candidates=(\d+)\s+ca_exclusions_known=(yes|no)")
_CA_EXCLUDED_ADMINS = re.compile(r"ca_excluded_admins=(\d+)")


def _emergency_access(audit: _Audit) -> _Verdict:
    # A break-glass account is a cloud admin deliberately excluded from
    # Conditional Access. The file lists every Global Admin, so the verdict
    # comes from the section's summary line, never from counting rows.
    text = audit.fc.get("07c_emergency_access_check.txt", "")
    skipped = "skipping check" in text.lower()
    summary = _BREAK_GLASS_SUMMARY.search(text)
    # Optional, absent on older evidence: tells "an excluded admin is in active
    # use" apart from "no admin is excluded".
    excluded = _CA_EXCLUDED_ADMINS.search(text)
    if _missing_or_error(text) or skipped or summary is None:
        return (
            "info",
            _CANNOT_VERIFY + "break-glass-sjekken ble hoppet over eller mangler oppsummering",
        )
    if summary.group(2) != "yes":
        return (
            "info",
            _CANNOT_VERIFY
            + "CA-unntak ble ikke samlet inn, så nødtilgangskontoer kan ikke bekreftes",
        )
    if int(summary.group(1)) > 0:
        return "pass", f"{int(summary.group(1))} nødtilgangskonto(er) (break glass) oppdaget"
    if excluded is not None and int(excluded.group(1)) > 0:
        return (
            "warn",
            "Adminkonto(er) er unntatt fra Conditional Access, men ingen fungerer som en gyldig "
            "nødtilgangskonto (kontoen(e) er i aktiv bruk)",
        )
    return (
        "warn",
        "Ingen administrator er unntatt fra Conditional Access, og ingen dedikert "
        "nødtilgangskonto er konfigurert",
    )


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
    if _missing_or_error(text):
        return "info", _CANNOT_VERIFY + "data utilgjengelig"
    if "were not measured" in text.lower():
        # The section says it could not read the directory settings.
        return "info", _CANNOT_VERIFY + "katalog-innstillinger kunne ikke leses"
    if _custom_banned_list_active(text):
        return "pass", "Egendefinert forbudt passordliste er aktiv"
    if _lacks(audit.capabilities, "entra_p1"):
        # The custom list needs Entra ID P1; no configuration clears this without it.
        return (
            "info",
            _NOT_LICENSED + "egendefinert passordliste krever Entra ID P1, "
            "som ikke er tildelt noen bruker",
        )
    return "fail", "Kun Microsofts standardliste, ingen egendefinerte forbudte passord"


def _secure_score(audit: _Audit) -> _Verdict:
    ss = audit.secure_score
    # A failed fetch has no pct; reading it as 0 would report a measured FAIL.
    if not ss.get("has_data"):
        return "info", _CANNOT_VERIFY + "Secure Score-data utilgjengelig"
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
        return "info", _CANNOT_VERIFY + "Conditional Access-data utilgjengelig"
    if not ca.get("has_client_app_data"):
        # Audits from before the client-app scope was collected.
        return (
            "info",
            _CANNOT_VERIFY + "auditen er kjørt før klientapp-omfang ble samlet inn. "
            "Kjør en ny audit",
        )
    if ca.get("blocks_legacy_auth"):
        return "pass", "En aktivert CA-policy blokkerer eldre klienter (exchangeActiveSync, other)"
    return "fail", "Ingen aktivert CA-policy blokkerer eldre autentisering"


def _security_defaults(text: str) -> str:
    for line in text.splitlines():
        if "security defaults" in line.lower() and ":" in line:
            return line.split(":", 1)[1].strip().lower()
    return ""


def _baseline_sign_in(audit: _Audit) -> _Verdict:
    # Security Defaults off is correct once Conditional Access is in place, so
    # the CA count is part of the verdict.
    sd = _security_defaults(audit.fc.get("31b_smart_lockout.txt", ""))
    ca = audit.ca
    if sd not in ("true", "false"):
        return "info", _CANNOT_VERIFY + "Security Defaults-status utilgjengelig"
    if sd == "true":
        return "pass", "Security Defaults er aktivert"
    if not ca.get("has_data"):
        # Off, with the CA side unknown: no verdict either way.
        return "info", _CANNOT_VERIFY + "Security Defaults er av, men CA-data er utilgjengelig"
    if ca.get("enabled", 0) > 0:
        return "pass", f"Security Defaults er av, men {ca.get('enabled')} CA-policyer er aktive"
    return "fail", "Verken Security Defaults eller aktive CA-policyer"


def _access_reviews(audit: _Audit) -> _Verdict:
    text = audit.fc.get("07d_access_reviews.txt", "")
    reviews = _parse_banner_count(text)
    if _missing_or_error(text):
        return "info", _CANNOT_VERIFY + "data om tilgangsgjennomganger utilgjengelig"
    if reviews:
        return "pass", f"{reviews} tilgangsgjennomgang(er) definert"
    if _lacks(audit.capabilities, "entra_p2"):
        # Without an assigned P2 seat there is nothing to configure.
        return (
            "info",
            _NOT_LICENSED
            + "tilgangsgjennomganger krever Entra ID P2, som ikke er tildelt noen bruker",
        )
    return "warn", "Ingen tilgangsgjennomganger definert"


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
    settings = _colon_settings(text)
    direct_in = settings.get("b2b direct connect in", "")
    system_default = settings.get("system default", "")
    if _missing_or_error(text) or not direct_in:
        return "info", _CANNOT_VERIFY + "kryssleie-innstillinger utilgjengelig"
    if direct_in == "allowed":
        return (
            "warn",
            "B2B direct connect inn er tillatt, så eksterne organisasjoner kan nå "
            "delte Teams-kanaler uten gjestekonto",
        )
    if system_default == "true":
        return "warn", "Kjører Microsofts systemstandard: kryssleie-tilgang er aldri vurdert"
    return "pass", "Kryssleie-tilgang er konfigurert, og direct connect inn er ikke tillatt"


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
            return "info", _CANNOT_VERIFY + "app-registreringer utilgjengelig"
        return "pass", "Ingen utløpte app-credentials"
    if counts is None:
        # The collector's summary line, not "expired" anywhere: the banner says it too.
        m = _CREDENTIAL_SUMMARY.search(warn)
        counts = (int(m.group(1)) if m else 0, int(m.group(2)) if m else 0)
    expired, expiring = counts
    if expired > 0:
        return "fail", f"{expired} utløpte app-credentials oppdaget"
    if expiring > 0:
        return "warn", f"{expiring} app-credentials utløper snart (≤30 dager)"
    return "pass", "Ingen utløpte app-credentials"


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
        f"{count} DLP-policyer konfigurert" if count else "DLP-policyer funnet",
        "Ingen DLP-policyer funnet",
        "Purview DLP-data utilgjengelig",
    )


def _sensitivity_labels(audit: _Audit) -> _Verdict:
    count = _purview_count(audit.purview, "sensitivity_labels")
    return _found_or_gap(
        audit,
        count > 0,
        "19c_purview_sensitivity_labels.txt",
        f"{count} sensitivitetsetiketter publisert",
        "Ingen sensitivitetsetiketter funnet",
        "Purview-etikettdata utilgjengelig",
    )


def _retention_policies(audit: _Audit) -> _Verdict:
    count = _purview_count(audit.purview, "retention_policies")
    return _found_or_gap(
        audit,
        count > 0,
        "19e_purview_retention_policies.txt",
        f"{count} oppbevaringspolicyer",
        "Ingen oppbevaringspolicyer funnet",
        "Purview-oppbevaringsdata utilgjengelig",
    )


def _onedrive_scan_gaps(scan: dict) -> list[str] | None:
    """What kept the sharing scan from covering the tenant; None if nothing did."""
    refused, discovery, folders = scan["refused"], scan["discovery"], scan["folders"]
    scope = scan["scope"]
    if scope.startswith("complete") and refused == 0 and discovery == 0 and folders == 0:
        return None
    gaps = []
    if refused:
        gaps.append(f"{refused} stasjon(er) kunne ikke leses")
    if discovery:
        gaps.append(f"{discovery} oppdagelseskall feilet")
    if folders:
        gaps.append(f"{folders} mappe(r) kunne ikke leses")
    if scope and not scope.startswith("complete"):
        gaps.append("søket nådde en grense før det var ferdig")
    return gaps


def _anonymous_links(audit: _Audit) -> _Verdict:
    # An "Anyone" link needs no sign-in, so one is a finding however partial the
    # scan was; but a zero is only as broad as the scan behind it.
    scan = _onedrive_scan(audit.fc)
    anyone = scan["anyone"]
    gaps = _onedrive_scan_gaps(scan)
    scanned = scan["scanned"]
    if anyone is None:
        return "info", _CANNOT_VERIFY + "OneDrive-delingsdata utilgjengelig"
    if anyone == 0 and gaps is not None:
        return (
            "info",
            "Ingen anonyme delingslenker funnet i det som ble gjennomsøkt, men "
            + (" og ".join(gaps) or "omfanget av søket er ukjent")
            + ", så fravær er ikke bekreftet for hele tenanten",
        )
    if anyone == 0:
        return "pass", f"Ingen anonyme delingslenker funnet i {scanned} stasjon(er)"
    return "fail", f"{anyone} anonym(e) delingslenke(r) som kan åpnes uten pålogging"


def _sharepoint_legacy_auth(audit: _Audit) -> _Verdict:
    # legacy_auth defaults to False when the admin settings were never read, so
    # it means nothing without has_data and legacy_auth_known.
    sp = audit.sharepoint
    if not sp.get("has_data"):
        return "info", _CANNOT_VERIFY + "SharePoint-tenant-innstillinger utilgjengelig"
    if not sp.get("legacy_auth_known"):
        return (
            "info",
            _CANNOT_VERIFY + "auditen er kjørt før dette feltet ble samlet inn. Kjør en ny audit",
        )
    if sp.get("legacy_auth"):
        return "fail", audit.t.cis_legacy_auth_enabled
    return "pass", audit.t.cis_legacy_auth_disabled


def _sharepoint_sharing(audit: _Audit) -> _Verdict:
    # has_data is true once the site list parsed; the sharing level comes from
    # the separate admin-settings file, and "unknown" means it was not read.
    sp, t = audit.sharepoint, audit.t
    if not sp.get("has_data") or sp.get("sharing_level") == "unknown":
        return "info", _CANNOT_VERIFY + "SharePoint-innstillinger utilgjengelig"
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
        return "pass", "Mailbox audit er aktivert (AuditDisabled=False)"
    if disabled is True:
        return "fail", "Mailbox audit er deaktivert (AuditDisabled=True)"
    if text.strip():
        return "info", "Kunne ikke fastslå audit-status fra org-config"
    # Every other control with nothing to read says so in an info row; this
    # one used to drop out of the report instead.
    return "info", _CANNOT_VERIFY + "Exchange-organisasjonsoppsettet ble ikke samlet inn"


def _policy_count(audit: _Audit, file: str, found: str, none: str, gap: str) -> _Verdict:
    # A section that ran and lists no policies is a reading of an unprotected
    # tenant; a section that did not run is no reading at all.
    if not _section_ran(audit.fc, file):
        return "info", _CANNOT_VERIFY + gap
    count = _record_count(audit.fc, file)
    if count > 0:
        return "pass", f"{count} {found}"
    return "fail", none


def _antiphish(audit: _Audit) -> _Verdict:
    return _policy_count(
        audit,
        "23_exchange_antiphish.txt",
        "anti-phishing-policy(er) konfigurert",
        "Ingen anti-phishing-policyer konfigurert",
        "anti-phishing-data utilgjengelig",
    )


def _antispam(audit: _Audit) -> _Verdict:
    return _policy_count(
        audit,
        "24_exchange_antispam.txt",
        "anti-spam-policy(er) konfigurert",
        "Ingen anti-spam-policyer konfigurert",
        "anti-spam-data utilgjengelig (kjør Get-HostedContentFilterPolicy i EOP)",
    )


def _external_forwarding(audit: _Audit) -> _Verdict:
    # The findings are in the *_WARN files. 28_ is written whenever the check
    # runs and lists internal forwarding too, and 29_ is the all-clear result,
    # so those two only show that the check ran.
    fc = audit.fc
    external = fc.get("28b_exchange_external_forwarding_WARN.txt", "")
    inbox_rules = fc.get("29_exchange_inbox_rules_external_fwd_WARN.txt", "")
    if external.strip() or inbox_rules.strip():
        return "warn", "Ekstern videresending oppdaget på en eller flere postbokser"
    if _section_ran(
        fc, "28_exchange_mailbox_forwarding.txt", "29_exchange_inbox_rules_external_fwd.txt"
    ):
        return "pass", "Ingen ekstern videresending oppdaget"
    return "info", _CANNOT_VERIFY + "videresendingsdata utilgjengelig"


def _defender_policy(audit: _Audit, kind: str, label: str) -> _Verdict:
    """Safe Links / Safe Attachments: on, present but off, unlicensed, absent, unknown."""
    state = _defender_policies(audit.fc)[kind]
    enabled = state["enabled"]
    if enabled > 0:
        return "pass", f"{enabled} aktiv(e) {label}-policy(er)"
    if state["present"]:
        return "fail", f"{label}-policy(er) finnes men er deaktivert"
    if _lacks(audit.capabilities, "defender_office"):
        # Not in the tenant's SKUs: the absence is the licence, not the setup.
        return "info", _NOT_LICENSED + f"{label} krever Defender for Office 365 Plan 1"
    if _section_ran(audit.fc, "27_exchange_defender_policies.txt"):
        return "warn", f"Ingen {label}-policyer funnet"
    return "info", _CANNOT_VERIFY + "Defender-policydata utilgjengelig"


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
        return "info", _CANNOT_VERIFY + f"SPF-oppslaget for {domain} feilet med {spf}"
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
        return "partial", f"p=none (kun overvåking): {published}" if published else dmarc
    if dmarc.strip().upper().startswith("ERROR"):
        return "info", _CANNOT_VERIFY + f"DMARC-oppslaget for {domain} feilet med {dmarc}"
    return "fail", dmarc or audit.t.cis_dmarc_missing


def _dkim(audit: _Audit, record: dict, domain: str) -> _Verdict:
    signing = record.get("dkim", "")
    dkim1 = record.get("dkim1", "")
    dkim2 = record.get("dkim2", "")
    detail = signing or dkim1 or ""
    valid = False
    if signing and ("enabled" in signing.lower() or "OK" in signing):
        valid = True  # M365 signing config
    elif "cname" in dkim1.lower() or "cname" in dkim2.lower():
        valid = True  # Microsoft's CNAME selectors
    elif "k=rsa" in dkim1.lower() or "k=rsa" in dkim2.lower():
        valid = True  # a third-party key
        detail = dkim1 or dkim2
    # The parser adds these keys only when the DNS output had a DKIM line, so
    # their presence separates "looked and found nothing" from "never checked".
    checked = any(k in record for k in ("dkim", "dkim1", "dkim2"))
    # Only the M365 selectors (dkim1) can make this cannot-verify: dkim2 probes
    # guessed third-party names, and a blip there must not hide a definite miss.
    if valid:
        return "pass", detail
    if "error" in dkim1.lower():
        return (
            "info",
            _CANNOT_VERIFY + f"DKIM-oppslaget for M365-selektorene til {domain} feilet med {dkim1}",
        )
    if detail:
        return "fail", detail
    if checked:
        return "fail", "No DKIM record found"
    return "info", _CANNOT_VERIFY + "DKIM ikke kontrollert for dette domenet"


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
        reason = intune.get("unavailable_reason") or "Intune-data utilgjengelig"
        return "info", _CANNOT_VERIFY + reason
    if not has_policies and not has_devices and intune.get("entra_total", 0) > 0:
        # Devices the directory knows and Intune manages none of: every endpoint
        # sits outside compliance management.
        return "fail", t("cis_entra_devices_unmanaged", total=intune["entra_total"])
    if not has_policies and not has_devices:
        return "info", t.cis_no_intune
    if not has_policies and unreadable:
        return "info", _CANNOT_VERIFY + "Intune-compliance-policyer utilgjengelig"
    if not has_policies:
        # With no policy to evaluate, device compliance is undefined.
        return "fail", "Enheter er enrolled, men ingen Intune-compliance-policyer er konfigurert"
    if not has_devices:
        return (
            "pass",
            f"{policy_count} compliance-policy(er) konfigurert (ingen enheter enrolled)",
        )
    pct = intune.get("compliance_pct", 0)
    if pct >= 90:
        return "pass", t("cis_compliance_pct", pct=pct)
    return "partial", t(
        "cis_compliance_partial", pct=pct, noncompliant=intune.get("noncompliant", 0)
    )


# ── Teams ─────────────────────────────────────────────────────────────────────

_RESTRICTED = ("block", "disabl", "none", "restrict", "denied")


def _teams_b2b_verdict(collab: str, direct: str) -> _Verdict:
    # Graded per access type: Microsoft's default blocks Direct Connect while
    # allowing collaboration, so "blocked" is in almost every file. Direct
    # Connect inbound open grants shared-channel trust and fails; open
    # collaboration with Direct Connect restricted warns.
    collab_open = bool(collab) and not any(k in collab.lower() for k in _RESTRICTED)
    direct_open = bool(direct) and not any(k in direct.lower() for k in _RESTRICTED)
    if direct_open:
        return "fail", "B2B Direct Connect innkommende tillater ekstern tilgang uten begrensning"
    if collab_open:
        return (
            "warn",
            "B2B Collaboration innkommende tillater ekstern tilgang og bør begrenses mot policy",
        )
    return "pass", "Ekstern tilgang er begrenset"


def _teams_access_from_text(text: str) -> _Verdict:
    # Older federation-style output, or partner configurations only.
    low = text.lower()
    if "blocked" in low or "disabled" in low:
        return "pass", "Ekstern tilgang er begrenset"
    if "allowed for all" in low or "everyone" in low or "no restrictions" in low:
        return "fail", "Ekstern tilgang er uten begrensninger (anyone-mode)"
    return "warn", "Ekstern tilgang er aktivert med begrensninger og bør gjennomgås mot policy"


def _teams_external_access(audit: _Audit) -> _Verdict:
    access = _teams_cross_tenant(audit.fc)
    if access is None:
        return "info", _CANNOT_VERIFY + "Teams external access-data utilgjengelig"
    collab, direct, partners = access["collab"], access["direct"], access["partners"]
    if not collab and not direct and partners is None:
        # Every access type N/A and no partner configurations: the policy was
        # not returned, or the tenant is on defaults. No evidence either way.
        return (
            "info",
            _CANNOT_VERIFY
            + "kryssleie-tilgangspolicy ikke innsamlet eller tenant på Microsoft-standard",
        )
    if collab or direct:
        return _teams_b2b_verdict(collab, direct)
    return _teams_access_from_text(partners)


def _teams_guest_access(audit: _Audit) -> _Verdict:
    # Read from the Teams section's guest file, where teams_policies.py has
    # already mapped the Graph values to readable names.
    invites, role = _teams_guest_settings(audit.fc)
    if not invites:
        return "info", _CANNOT_VERIFY + "gjesteinnstillinger ble ikke hentet"
    detail = f"Invitasjoner: {invites}. Gjesterolle: {role or 'ukjent'}"
    if "same as member" in role.lower():
        # Worse than any invitation setting: whoever gets in sees what a member sees.
        return "fail", detail + ". Gjester har samme tilgang som ansatte"
    if invites.lower().startswith("everyone"):
        return "fail", detail + ". Gjester kan invitere flere gjester"
    if "member" in invites.lower():
        return "warn", detail + ". Alle ansatte kan invitere gjester"
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
        return (
            "pass",
            "Unified Audit Log-ingestion er aktivert (UnifiedAuditLogIngestionEnabled=True)",
        )
    if enabled is False:
        return (
            "fail",
            "Unified Audit Log-ingestion er deaktivert (UnifiedAuditLogIngestionEnabled=False). "
            "Kjør Set-AdminAuditLogConfig -UnifiedAuditLogIngestionEnabled $true",
        )
    return (
        "info",
        _CANNOT_VERIFY + "Unified Audit Log-innstillingen ble ikke hentet. "
        "Verifiser Set-AdminAuditLogConfig -UnifiedAuditLogIngestionEnabled manuelt",
    )


def _defender_alerts(audit: _Audit) -> _Verdict:
    text = audit.fc.get("19b_defender_active_alerts.txt", "")
    # Rows are counted rather than a phrase matched; the header's wording varies.
    open_alerts = _count_data_lines(text) if text.strip() else 0
    if open_alerts > 0:
        return "warn", f"{open_alerts} aktive Defender-varsler krever oppfølging"
    # An empty alerts file means "no alerts" only if the query ran.
    if _section_ran(audit.fc, "19b_defender_alert_count.txt", "19b_defender_active_alerts.txt"):
        return "pass", "Ingen aktive Defender-varsler"
    return "info", _CANNOT_VERIFY + "Defender-varseldata utilgjengelig"


def _risky_user_rows(text: str) -> tuple[int, int]:
    """(rows, high- or medium-risk rows) in the "upn  risk-level  state" table."""
    rows = high = 0
    for line in text.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("=")
            or stripped.startswith("-")
            or "UPN" in stripped
            or "RISKY USERS" in stripped.upper()
        ):
            continue
        cols = re.split(r"\s{2,}", stripped)
        if len(cols) >= 3 and "@" in cols[0]:
            rows += 1
            if cols[1].strip().lower() in ("high", "medium"):
                high += 1
    return rows, high


def _risky_users(audit: _Audit) -> _Verdict:
    # Structured rows, not the word "high" anywhere in the file.
    raw = audit.context.get("risky_users")
    text = raw if isinstance(raw, str) else ""
    if _evidence_unavailable(text):
        return "info", _CANNOT_VERIFY + "risky-users-data utilgjengelig (krever Entra ID P2)"
    rows, high = _risky_user_rows(text)
    if high > 0:
        return "fail", f"{high} brukere med høy/medium risiko er oppdaget og må undersøkes"
    if rows > 0:
        return "warn", f"{rows} brukere er flagget med lav risiko og bør gjennomgås"
    return "pass", "Ingen risikobrukere oppdaget"


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
