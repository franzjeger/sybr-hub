"""Report generator — technical and customer-facing HTML/PDF reports."""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.core.config import get_branding, get_logo_path
from app.modules.base import SectionResult, SectionStatus
from app.reports.compliance import _build_compliance_map
from app.reports.evidence import _EVIDENCE_MAP
from app.reports.i18n import T
from app.reports.metrics import (
    _baseline_for,
    _compute_trends,
    _drift_for,
    load_metrics_history,
    load_previous_metrics,
    save_audit_metrics,
)
from app.reports.parsers import (
    _analyze_license_optimization,
    _is_error_payload,
    _parse_admin_roles,
    _parse_azure_overview,
    _parse_backup_coverage,
    _parse_ca_policies,
    _parse_entra_devices,
    _parse_exchange_overview,
    _parse_groups,
    _parse_intune_devices,
    _parse_licenses,
    _parse_mfa,
    _parse_network_audit,
    _parse_oauth_grants,
    _parse_purview,
    _parse_secure_score,
    _parse_sharepoint_settings,
    _parse_signin_risk,
    _parse_spf_dmarc,
    _parse_usage,
    _parse_user_counts,
    _severity,
)
from app.reports.parsers.common import _sidecar
from app.reports.radar import _build_risk_radar, _render_radar_svg
from app.reports.recommendations import _build_finding_rec_map, _build_recommendations
from app.reports.risk import _apply_critical_floor, _compute_risk
from app.reports.summary import _build_executive_summary

log = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _logo_b64(filename: str) -> str:
    """Return base64 data URI for a logo file."""
    logo_dir = Path(__file__).parent.parent.parent / "Logo-Branding"
    path = logo_dir / filename
    if not path.exists():
        return ""
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode()
    return f"data:image/png;base64,{b64}"


def _custom_logo_b64() -> str:
    """Return base64 data URI for the custom logo if it exists, else fallback to bundled logo."""
    custom = get_logo_path()
    if custom:
        data = custom.read_bytes()
        b64 = base64.b64encode(data).decode()
        return f"data:image/png;base64,{b64}"
    # Fallback to bundled logo
    return _logo_b64("300 x 86.png")


def _custom_logo_dark_b64() -> str:
    """Return base64 data URI for the dark-theme logo.

    If a custom logo is uploaded, use it for both themes (user only uploads one).
    Otherwise, use the bundled dark variant if available, falling back to the standard logo.
    """
    custom = get_logo_path()
    if custom:
        data = custom.read_bytes()
        b64 = base64.b64encode(data).decode()
        return f"data:image/png;base64,{b64}"
    # Try dark variant first, fall back to standard
    dark = _logo_b64("Sybr Dark.png")
    return dark if dark else _logo_b64("300 x 86.png")


def _get_app_version() -> str:
    """Return app version string for report footers."""
    try:
        from app.core.version import get_version

        v = get_version()
        return v if v.startswith("v") else f"v{v}"
    except Exception:
        log.warning("Could not resolve app version for the report footer", exc_info=True)
        return "vunknown"


def _jinja_env() -> Environment:
    # autoescape=True, not select_autoescape(["html"]): the templates are named
    # ``*.html.j2``, and select_autoescape matches on the filename suffix, so
    # ``.j2`` fell through to its default (False) and every {{ value }} rendered
    # unescaped. Report context carries attacker-influenceable tenant data
    # (M365 display names, UPNs, device names), so that was a stored-XSS sink.
    # Escape everything; the one intentional-HTML value (radar_svg) is marked
    # ``| safe`` in the template.
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR), encoding="utf-8"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ── Context builder ────────────────────────────────────────────────────────────


def build_report_context(
    customer_name: str,
    org_domain: str,
    out_dir: Path,
    results: list[SectionResult],
    lang: str = "no",
    frameworks: str = "all",
    persist_metrics: bool = True,
) -> dict:
    """Parse one audit run into everything a report or a reader needs.

    ``persist_metrics`` exists because this function writes. It ends by saving
    _audit_metrics.json and inserting a row in audit_metrics, which is right
    when an audit has just produced the run and wrong for everybody else — and
    "everybody else" grew: the baselines endpoint builds a context to *read*
    one, and so does anything that scores an old run.

    Left as it was, a customer card rewrote that run's stored metrics on every
    open, stamping it with the current time. It also cost twenty-one duplicate
    trend rows in one second when a maintenance script walked every run.

    Pass False from any caller that is reading. The default stays True so an
    audit that has just finished keeps recording itself without having to
    remember to ask.
    """
    from app.core.encryption import encrypted_read_text

    file_contents: dict[str, str] = {}
    # Named apart from the "failed_sections" context key, which is a count of
    # sections whose collector reported failure. A section can report success
    # and still write an error into its file, so the two disagree on exactly
    # the tenants this list exists for.
    error_files: list[str] = []
    # .json as well as .txt: the MFA collector writes a machine-readable
    # sidecar next to its rendered table, and globbing only *.txt meant the
    # reader never saw it and silently fell back to parsing the table on every
    # single run — so the sidecar that exists to make the figures reliable was
    # dead weight. Error-payload blanking below applies to both.
    for f in sorted([*out_dir.glob("*.txt"), *out_dir.glob("*.json")]):
        try:
            text = encrypted_read_text(f)
        except Exception:
            text = f.read_text(encoding="utf-8", errors="replace")
        if _is_error_payload(text):
            # Blanked deliberately. Eighteen parsers read these files and none
            # of them checked whether they held data or an error, so a failed
            # section was parsed as content: a two-line 404 from the Purview
            # endpoint became "2 sensitivity labels published", and the CIS
            # control for publishing labels passed on it. Handing the parsers
            # an empty string routes them into the paths that already say
            # "cannot be verified — data unavailable". The failure itself is
            # still reported: the section carries it as a warning.
            log.warning("Section %s holds an error rather than data — not parsed", f.name)
            error_files.append(f.name)
            text = ""
        file_contents[f.name] = text

    def fc(name: str) -> str:
        return file_contents.get(name, "")

    warn_files = [n for n in file_contents if "WARN" in n.upper()]
    all_warns = [w for r in results for w in r.warns]

    secure_score = _parse_secure_score(fc("09_secure_score.txt"))
    users = _parse_user_counts(fc("03_users_count.txt"))
    mfa = _parse_mfa(
        fc("04_mfa_methods.txt"), fc("04b_mfa_ca_analysis.txt"), results, fc("04_mfa_methods.json")
    )
    licenses = _parse_licenses(fc("02_licenses.txt"))
    license_optimization = _analyze_license_optimization(licenses, file_contents, lang=lang)
    spf_dmarc = _parse_spf_dmarc(fc("26_email_dns_spf_dmarc.txt"))
    ca = _parse_ca_policies(fc("08_conditional_access.txt"))
    admin_roles = _parse_admin_roles(fc("07_admin_roles.txt"))
    intune = _parse_intune_devices(
        fc("10_intune_devices_count.txt"),
        fc("10_intune_devices.txt"),
        _sidecar(file_contents, "10_intune_devices.txt"),
    )
    entra_devices = _parse_entra_devices(
        fc("15_entra_devices_count.txt"),
        fc("15_entra_devices.txt"),
        _sidecar(file_contents, "15_entra_devices.txt"),
    )
    usage = _parse_usage(fc("16_usage_summary.txt"), fc("16_usage_active_users.txt"))
    # The claim the Intune figure alone cannot make. Only stated when both
    # sides were actually read: an unmanaged count derived from a refusal is
    # the same mistake in a new place.
    #
    # Single source of truth: the Entra register's own ``isManaged`` flag — the
    # same figure the baseline check (``entra_devices.unmanaged``), the section
    # status and the 15_entra_devices_count file all report. The old
    # ``total - intune_total`` subtracted Intune's *enrolled* count, a different
    # measure, so the recommendation (11/16) disagreed with the count file
    # (9/16) for the same tenant. Fall back to the register's own total-managed
    # (still the register, never Intune's enrolled list) if the unmanaged line
    # is absent.
    if entra_devices.get("has_data") and intune.get("has_data"):
        intune["entra_total"] = entra_devices["total"]
        intune["entra_unmanaged"] = max(
            0,
            entra_devices.get(
                "unmanaged",
                entra_devices["total"] - entra_devices.get("managed", 0),
            ),
        )
    sharepoint = _parse_sharepoint_settings(
        fc("15b_sharepoint_settings.txt"), fc("15_sharepoint_sites.txt"), lang=lang
    )
    oauth = _parse_oauth_grants(fc("17b_oauth_consent_grants.txt"), fc("17_app_registrations.txt"))
    # The reader blanks an error-payload file to "" before the parser sees it, so
    # the parser's own grants_read (derived from the text) can never see the
    # "Error:" stub and is always True in production. error_files survives that
    # blanking, so derive the authoritative signal here: a 17b that was an error
    # payload means the consent-grants read failed (fix review).
    oauth["grants_read"] = "17b_oauth_consent_grants.txt" not in error_files
    groups = _parse_groups(fc("06_groups.txt"))
    azure = _parse_azure_overview(file_contents)
    exchange = _parse_exchange_overview(file_contents)
    backup_coverage = _parse_backup_coverage(file_contents)
    signin_risk = _parse_signin_risk(file_contents)
    purview = _parse_purview(file_contents)
    ext_fwd = fc("28b_exchange_external_forwarding_WARN.txt")
    risky = fc("18_risky_users.txt")
    defender = fc("19b_defender_active_alerts.txt")
    network = _parse_network_audit(file_contents)
    _unavailable = [
        r.name for r in results if r.status in (SectionStatus.SKIPPED, SectionStatus.FAILED)
    ]
    risk = _compute_risk(
        secure_score,
        mfa,
        spf_dmarc,
        all_warns,
        ext_fwd,
        risky,
        defender,
        admin_roles,
        intune,
        sharepoint,
        oauth,
        network=network,
        lang=lang,
        unavailable_sections=_unavailable,
    )
    recs = _build_recommendations(
        mfa,
        spf_dmarc,
        secure_score,
        ext_fwd,
        risky,
        licenses,
        admin_roles,
        intune,
        sharepoint,
        oauth,
        azure,
        file_contents,
        backup_coverage=backup_coverage,
        signin_risk=signin_risk,
        network=network,
        lang=lang,
    )
    # An open critical finding must be visible in the headline grade (F9).
    _apply_critical_floor(risk, recs, lang)

    # Build current metrics snapshot for trend comparison
    current_metrics = {
        "mfa_coverage_pct": mfa.get("pct", 0),
        "secure_score_pct": secure_score.get("pct", 0),
        "total_users": users.get("total", 0),
        "users_no_mfa": mfa.get("no_mfa", 0),
        "ca_policies_enabled": ca.get("enabled", 0),
        "intune_compliance_pct": intune.get("compliance_pct", 0.0),
        "intune_total_devices": intune.get("total", 0),
        "admin_roles_ga_count": admin_roles.get("global_admin_count", 0) if admin_roles else 0,
        "total_warns": len(all_warns),
        "risk_score": risk.get("score", 0),
        "risk_grade": risk.get("grade", ""),
    }
    prev = load_previous_metrics(out_dir)
    trends = _compute_trends(current_metrics, prev)
    metrics_history = load_metrics_history(out_dir)
    # Build full timeline: historical runs + current (for trend charts)
    metrics_timeline = [*metrics_history, current_metrics]

    context = {
        "customer_name": customer_name,
        "org_domain": org_domain,
        "report_date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "report_date_no": datetime.now(UTC).strftime("%d.%m.%Y"),
        "results": results,
        "total_sections": len(results),
        "done_sections": sum(1 for r in results if r.status == SectionStatus.DONE),
        "skipped_sections": sum(1 for r in results if r.status == SectionStatus.SKIPPED),
        "failed_sections": sum(1 for r in results if r.status == SectionStatus.FAILED),
        "warn_files": warn_files,
        "all_warns": all_warns,
        "file_contents": file_contents,
        # Parsed structured data
        "secure_score": secure_score,
        "users": users,
        "mfa": mfa,
        "licenses": licenses,
        "license_optimization": license_optimization,
        "spf_dmarc": spf_dmarc,
        "ca": ca,
        "admin_roles": admin_roles,
        "intune": intune,
        "entra_devices": entra_devices,
        "usage": usage,
        "sharepoint": sharepoint,
        "oauth": oauth,
        "groups": groups,
        "azure": azure,
        "exchange": exchange,
        "backup_coverage": backup_coverage,
        "signin_risk": signin_risk,
        "purview": purview,
        "network": network,
        "risk": risk,
        "recommendations": recs,
        "finding_to_recs": _build_finding_rec_map(recs),
        # Trend comparison
        "previous_metrics": prev,
        "trends": trends,
        "metrics_timeline": metrics_timeline,
        # Raw file snippets (still needed for tech report)
        "tenant_info": fc("01_tenant.txt"),
        "ext_fwd_warn": ext_fwd,
        "inbox_rule_warn": fc("29_exchange_inbox_rules_external_fwd_WARN.txt"),
        "risky_users": risky,
        "defender_alerts": defender,
        "advisor_data": fc("51_azure_advisor.txt"),
        "compliance_policies": fc("11_intune_compliance_policies.txt"),
        "app_registrations": fc("17_app_registrations.txt"),
        "emergency_access": fc("07c_emergency_access_check.txt"),
        "pim_assignments": fc("07b_pim_eligible_assignments.txt"),
        "teams_info": fc("16_teams.txt"),
        "teams_settings": fc("16b_teams_settings.txt"),
        "teams_external": fc("16c_teams_external_access.txt"),
        # Branding
        "branding": get_branding(),
        "logo_dark": _custom_logo_dark_b64(),
        "logo_light": _custom_logo_b64(),
        # Version
        "app_version": _get_app_version(),
        # Helpers
        "SectionStatus": SectionStatus,
        "_severity": _severity,
    }

    # Build compliance mapping after context is ready
    compliance = _build_compliance_map(context, lang=lang, frameworks=frameworks)

    # The break-glass check embeds a machine-readable "SUMMARY: break_glass_…"
    # line in 07c for CIS 1.1.6 to parse — which it just did, above. That token
    # is not human prose, and 07c is rendered verbatim both in the Emergency
    # Access panel and in the raw-evidence appendix (which dumps every file in
    # file_contents). Strip it now, after parsing, from the shared dict and the
    # panel copy, so the internal token never reaches the delivered report.
    _bg_file = "07c_emergency_access_check.txt"
    if file_contents.get(_bg_file):
        _stripped = "\n".join(
            ln
            for ln in file_contents[_bg_file].splitlines()
            if not ln.strip().startswith("SUMMARY:")
        )
        file_contents[_bg_file] = _stripped
        context["emergency_access"] = _stripped
    compliance_pass = sum(1 for c in compliance if c["status"] == "pass")
    compliance_partial = sum(1 for c in compliance if c["status"] in ("partial", "warn"))
    compliance_fail = sum(1 for c in compliance if c["status"] == "fail")
    compliance_total = len(compliance)
    compliance_info = sum(1 for c in compliance if c["status"] == "info")
    compliance_assessed = compliance_total - compliance_info  # exclude "info" from scoring
    compliance_pct = round(compliance_pass / max(compliance_assessed, 1) * 100, 0)
    context["compliance"] = compliance
    context["compliance_pass"] = compliance_pass
    context["compliance_partial"] = compliance_partial
    context["compliance_fail"] = compliance_fail
    context["compliance_total"] = compliance_total
    context["compliance_assessed"] = compliance_assessed
    # The count of controls left out of the denominator. Computed here since
    # the percentage was first introduced, but never passed to a template, so
    # the reports showed a rate without showing what it was a rate of.
    context["compliance_info"] = compliance_info
    context["compliance_pct"] = compliance_pct
    context["show_nist"] = frameworks in ("cis+nist", "all")
    context["show_iso"] = frameworks in ("cis+iso", "all")

    # Which collected files held an error, and which controls they leave
    # unverified. The verdicts themselves already say "cannot be verified";
    # nothing said why, because the evidence links deliberately skip a file
    # whose contents were blanked, so a failed file is the one case that
    # cites nothing. Read out of _EVIDENCE_MAP in the opposite direction,
    # and intersected with the controls the table actually lists so this
    # never points at a row that is not there.
    shown_ids = {c["cis_id"] for c in compliance}
    context["error_files"] = [
        {
            "name": name,
            "controls": sorted(
                cis_id
                for cis_id, files in _EVIDENCE_MAP.items()
                if name in files and cis_id in shown_ids
            ),
        }
        for name in error_files
    ]

    # A count of nought and a count never taken read the same on a report, and
    # a customer cannot tell "you have no sensitivity labels" from "we could
    # not look". The technical report lists the errored sections outright; the
    # customer report showed a brand-coloured 0 with nothing beside it.
    #
    # The flag has to be set from error_files rather than inside the parser:
    # the reader blanks an errored file before any parser sees it, so by the
    # time _parse_purview runs, the evidence that the fetch failed is gone.
    for flag, section in (
        ("sensitivity_labels_unavailable", "19c_purview_sensitivity_labels.txt"),
        ("dlp_unavailable", "19d_purview_dlp_policies.txt"),
        ("retention_unavailable", "19e_purview_retention_policies.txt"),
    ):
        context["purview"][flag] = section in error_files

    # Per-category compliance summary
    cat_summary: dict[str, dict] = {}
    for c in compliance:
        cat = c.get("category", "")
        if cat not in cat_summary:
            cat_summary[cat] = {
                "pass": 0,
                "partial": 0,
                "fail": 0,
                "info": 0,
                "warn": 0,
                "total": 0,
            }
        cat_summary[cat][c["status"]] = cat_summary[cat].get(c["status"], 0) + 1
        cat_summary[cat]["total"] += 1
    context["compliance_by_category"] = cat_summary

    # Executive summary
    context["executive_summary"] = _build_executive_summary(context, lang=lang)

    # Risk radar
    risk_radar = _build_risk_radar(context, lang=lang)
    radar_svg = _render_radar_svg(risk_radar)
    context["risk_radar"] = risk_radar
    context["radar_svg"] = radar_svg

    # ── Remediation tracking ─────────────────────────────────────────────
    # Load per-customer remediation statuses so reports show what has been
    # addressed since the last audit.
    remediation = {}
    try:
        from app.core.customer import CustomerManager

        active_id = CustomerManager.get_active_id()
        if active_id:
            from app.services.remediation import load_remediation_sync

            remediation = load_remediation_sync(active_id)
    except Exception:
        # Non-critical — the report renders without the remediation column.
        log.debug("Remediation data unavailable for this report", exc_info=True)

    # Enrich each recommendation with its remediation status. The store keys
    # by rec_id (the stable, language-independent identity), so look it up by
    # rec_id first. A title fallback keeps old rows — saved before rec_id
    # existed — from silently reading as "open".
    for rec in recs:
        rec_id = rec.get("rec_id", "")
        title = rec.get("title", "")
        if rec_id and rec_id in remediation:
            rec["remediation"] = remediation[rec_id]
        elif title and title in remediation:
            rec["remediation"] = remediation[title]
        else:
            rec["remediation"] = {
                "status": "open",
                "notes": "",
                "updated_by": "",
                "updated_date": "",
            }

    context["remediation"] = remediation
    # Count done/ignored among the findings in THIS report, not across every
    # stored row. A finding can drop out of a later audit while its remediation
    # row persists, which would otherwise push the percentage past 100.
    remediation_done = sum(
        1 for rec in recs if rec.get("remediation", {}).get("status") in ("done", "ignored")
    )
    remediation_total = len(recs) if recs else 0
    context["remediation_done"] = remediation_done
    context["remediation_total"] = remediation_total
    context["remediation_pct"] = (
        round(remediation_done / remediation_total * 100) if remediation_total else 0
    )

    # ── Drift, then the standard that reads it ─────────────────────────────
    # Last, and in this order. The baseline evaluates paths through the
    # finished context, so every key it can name must already be set — drift
    # included, since a check on "no policy disappeared since last audit" is
    # exactly the kind a versioned standard should carry.
    context["drift"] = _drift_for(out_dir)
    context["baseline"] = _baseline_for(context)

    # The policies in production, consolidated from this run's snapshots, each
    # with a plain-language line. Same source the customer card reads, so the
    # report and the card can never disagree about what is configured.
    try:
        from app.core.policy_inventory import build_inventory

        context["policy_inventory"] = build_inventory(out_dir)
    except Exception:
        # The report drops a whole section silently otherwise, and the reader
        # cannot tell "no policies" from "we failed to read them".
        log.warning("Policy inventory could not be built for %s", out_dir, exc_info=True)
        context["policy_inventory"] = None

    if persist_metrics:
        save_audit_metrics(out_dir, context)

    return context


# ── HTML generation ────────────────────────────────────────────────────────────


def generate_html(context: dict, output_path: Path, template_name: str) -> Path:
    env = _jinja_env()
    template = env.get_template(template_name)
    html = template.render(**context)
    from app.core.encryption import encrypted_write_text

    encrypted_write_text(output_path, html)
    return output_path


def _make_pdf_url_fetcher():
    """Build a fetcher that refuses every resource except data: URIs.

    The report embeds all its assets — logos included — as ``data:`` URIs, so
    nothing legitimate is loaded from disk or the network. WeasyPrint renders
    the report HTML server-side, and that HTML carries attacker-influenceable
    tenant fields (a display name, a device name). Without this fetcher, an
    injected ``<img src="http://169.254.169.254/…">`` or ``url('file:///etc/…')``
    would make the server fetch an attacker-chosen internal or local URL at
    render time — an SSRF / local-file read that the browser-side CSP on the
    served HTML never applies to. Allow only data:, block the rest.

    WeasyPrint 70 expects ``url_fetcher`` to be an instance of its
    ``URLFetcher`` class (or a subclass overriding ``fetch()``), not a plain
    function: its image-loading path reads ``url_fetcher._fail_on_errors``
    directly, with no ``getattr`` default, so a bare function raising here —
    exactly what the block-non-data-URL case below does — used to surface as
    a confusing ``AttributeError`` instead of the intended ``ValueError``.
    Subclassing gives the fetcher that attribute (inherited from
    ``URLFetcher.__init__``) so a blocked URL fails the way it is meant to.
    """
    from weasyprint import URLFetcher

    class _ReportURLFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            if url.startswith("data:"):
                return super().fetch(url, headers=headers)
            raise ValueError(f"Blocked non-data URL during report render: {url[:80]}")

    return _ReportURLFetcher()


def generate_pdf(html_path: Path, output_path: Path) -> Path:
    try:
        from weasyprint import HTML

        from app.core.encryption import encrypted_read_text

        html_content = encrypted_read_text(html_path)
        HTML(
            string=html_content,
            base_url=str(html_path.parent),
            url_fetcher=_make_pdf_url_fetcher(),
        ).write_pdf(str(output_path))
        return output_path
    except ImportError:
        raise RuntimeError(
            "WeasyPrint er ikke installert, så PDF-generering er utilgjengelig."
        ) from None
    except Exception as e:
        raise RuntimeError(f"PDF-generering feilet: {e}") from e


# ── Main interface ─────────────────────────────────────────────────────────────


def generate_reports(
    customer_name: str,
    org_domain: str,
    out_dir: Path,
    results: list[SectionResult],
    formats: list[str] = ("html",),
    report_type: str = "tech",  # "tech" or "customer"
    lang: str = "no",  # "no" or "en"
    frameworks: str = "all",  # "cis" | "cis+nist" | "cis+iso" | "all"
    theme: str = "light",  # "light" or "dark"
) -> dict[str, Path]:
    context = build_report_context(
        customer_name, org_domain, out_dir, results, lang=lang, frameworks=frameworks
    )

    # Add translation helper — use {{ t.key }} or {{ t('key', count=5) }} in templates
    context["t"] = T(lang)
    context["lang"] = lang
    context["theme"] = theme

    template_name = (
        "report_customer.html.j2" if report_type == "customer" else "report_tech.html.j2"
    )
    suffix = "_customer" if report_type == "customer" else "_tech"
    date_str = datetime.now().strftime("%Y-%m-%d")

    output: dict[str, Path] = {}
    html_path = out_dir / f"audit_report{suffix}_{date_str}.html"

    if "html" in formats or "pdf" in formats:
        generate_html(context, html_path, template_name)
        output["html"] = html_path

    if "pdf" in formats:
        pdf_path = html_path.with_suffix(".pdf")
        generate_pdf(html_path, pdf_path)
        output["pdf"] = pdf_path

    return output
