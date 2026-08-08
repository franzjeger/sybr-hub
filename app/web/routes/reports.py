"""Report generation, export, and delivery routes."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import Response

from app.core.exceptions import (
    AuthError,
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.user import Role, User
from app.web import state
from app.web.i18n import ui_t
from app.web.middleware.auth import (
    get_current_user,
    require_customer_access,
    require_role,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


# ── API: Report helpers ────────────────────────────────────────────────────────


async def _selected_audit_run(
    user: User, *, require_results: bool = False
) -> state.AuditRunContext:
    """Resolve report state owned by this user and revalidate path access."""
    from app.core.customer import CustomerManager
    from app.core.rbac import check_audit_path_access

    active_id = CustomerManager.get_active_id()
    run = state.get_user_audit(user.id, active_id) if active_id else None
    if run is None or run.out_dir is None or not run.out_dir.exists():
        raise ValidationError(ui_t("err_no_audit_results"))
    if require_results and not run.results:
        raise ValidationError(ui_t("err_no_audit_results"))
    if not await check_audit_path_access(user, str(run.out_dir)):
        raise ForbiddenError("Ingen tilgang til denne auditkjøringen")
    return run


@router.post("/open-folder")
async def open_folder(
    body: dict = Body(default={}), user: User = Depends(require_role(Role.admin))
):
    import subprocess
    import sys

    from app.core.config import get_audit_dir

    # Use explicit path if provided, else active audit dir, else base audit dir
    requested_path = body.get("path")
    if requested_path:
        from app.core.rbac import check_audit_path_access

        if not await check_audit_path_access(user, requested_path):
            raise ForbiddenError("Ingen tilgang til denne auditmappen")
        folder = requested_path
    else:
        folder = str((await _selected_audit_run(user)).out_dir)

    if not folder:
        return {"ok": False}

    folder_path = Path(folder).resolve()
    audit_root = Path(get_audit_dir()).resolve()

    # Restrict to audit directory tree to prevent path traversal
    try:
        folder_path.relative_to(audit_root)
    except ValueError:
        logger.warning("Blocked open-folder outside audit dir: %s", folder_path)
        raise ForbiddenError("Auditmappen er utenfor tillatt område") from None
    folder = str(folder_path)

    # If the specific path doesn't exist, fall back to parent or audit dir
    if not folder_path.exists():
        parent = folder_path.parent
        folder = (
            str(parent)
            if parent.exists() and parent.resolve().is_relative_to(audit_root)
            else str(audit_root)
        )
    else:
        folder = str(folder_path)

    try:
        loop = asyncio.get_event_loop()
        if sys.platform == "win32":
            await loop.run_in_executor(None, lambda: subprocess.Popen(["explorer", folder]))
        elif sys.platform == "darwin":
            await loop.run_in_executor(None, lambda: subprocess.Popen(["open", folder]))
        else:
            await loop.run_in_executor(None, lambda: subprocess.Popen(["xdg-open", folder]))
    except Exception as e:
        logger.warning("Failed to open folder %s: %s", folder, e)
    return {"ok": True, "folder": folder}


# ── API: Email ────────────────────────────────────────────────────────────────


@router.post("/email/test")
async def email_test(request: Request, user: User = Depends(require_role(Role.admin))):
    """Send a test email to verify SMTP settings."""
    from app.core.email_sender import send_report_email

    body = await request.json()
    to = body.get("to", "").strip()
    if not to:
        to = body.get("smtp_user", "").strip()
    if not to:
        raise ValidationError(ui_t("err_no_recipient", request))
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: send_report_email(
                to=to,
                subject="SYBR MSP Toolkit — Testepost",
                body_html="<h2>Testepost</h2><p>E-postinnstillingene fungerer korrekt.</p><p style='color:#8b949e;font-size:12px;'>Sendt fra SYBR MSP Toolkit</p>",
                smtp_config=body,
            ),
        )
        return {"ok": True}
    except Exception as e:
        raise ValidationError(str(e)) from e


@router.post("/email/send-report")
async def email_send_report(request: Request, user: User = Depends(get_current_user)):
    """Manually send the latest report to a specified email address."""
    from app.core.config import load_app_settings
    from app.core.email_sender import build_report_body_html, send_report_email

    body = await request.json()
    to = body.get("to", "").strip()
    settings = load_app_settings()
    if not to:
        to = settings.get("email_default_recipient", "").strip()
    if not to:
        raise ValidationError(ui_t("err_no_recipient", request))

    audit_run = await _selected_audit_run(user)
    out_dir = audit_run.out_dir
    assert out_dir is not None

    # Find PDF
    pdf_path = None
    for f in out_dir.iterdir():
        if f.suffix == ".pdf":
            pdf_path = f
            break

    # Load metrics
    metrics = None
    metrics_path = out_dir / "_audit_metrics.json"
    if metrics_path.exists():
        from app.core.encryption import encrypted_read_json

        try:
            metrics = encrypted_read_json(metrics_path)
        except Exception as e:
            logger.warning("Failed to read metrics for email report: %s", e)

    customer_name = out_dir.parent.name.replace("_", " ")
    run_date = out_dir.name
    body_html = build_report_body_html(customer_name, run_date, metrics)
    subject = f"Auditrapport — {customer_name} ({run_date})"

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: send_report_email(
                to=to,
                subject=subject,
                body_html=body_html,
                attachment_path=pdf_path,
                smtp_config=settings,
            ),
        )
        from app.core.activity_log import log_activity as _log_email

        _log_email("email_sent", detail=f"to {to}", customer=customer_name)

        return {"ok": True, "to": to}
    except Exception as e:
        logger.error("Email send failed: %s", e)
        raise IntegrationError("Kunne ikke sende e-post") from e


# ── API: Per-customer summary report ─────────────────────────────────────────


@router.get("/reports/customer-summary/{customer_id}")
async def customer_summary_report(
    customer_id: str,
    request: Request,
    _user: User = Depends(require_customer_access(Role.viewer)),
):
    """Generate an HTML customer summary report combining all data sources.

    Returns printable HTML (use browser Print > Save as PDF).
    """
    import json as _json
    from datetime import datetime

    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager
    from app.core.database import get_db
    from app.core.encryption import encrypted_read_json

    # ── Load customer ──
    customers = CustomerManager.list_customers()
    cust = None
    for c in customers:
        if c.get("_id", "") == customer_id:
            cust = c
            break
    if not cust:
        raise NotFoundError("Customer not found")

    name = cust.get("CustomerName", "Unknown")
    domain = cust.get("PrimaryDomain", "")
    now = datetime.now(UTC)

    # ── Health score ──
    health_score = 100
    health_grade = "-"

    # ── Audit metrics (latest) ──
    audit_metrics: dict = {}
    try:
        async with (
            get_db() as db,
            db.execute(
                "SELECT * FROM audit_metrics WHERE customer_id = ? ORDER BY audit_date DESC LIMIT 1",
                (customer_id,),
            ) as cur,
        ):
            row = await cur.fetchone()
            if row:
                audit_metrics = dict(row)
    except Exception as e:
        logger.debug("Failed to load audit metrics from DB for %s: %s", customer_id, e)

    # Also try file-based metrics
    if not audit_metrics:
        audit_dir = get_audit_dir()
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
        customer_dir = audit_dir / safe_name
        if customer_dir.exists():
            runs = sorted([d for d in customer_dir.iterdir() if d.is_dir()], reverse=True)
            for run_dir in runs:
                metrics_path = run_dir / "_audit_metrics.json"
                if metrics_path.exists():
                    try:
                        audit_metrics = encrypted_read_json(metrics_path)
                    except Exception as e:
                        logger.debug("Failed to read metrics file %s: %s", metrics_path, e)
                    break

    risk_grade = audit_metrics.get("risk_grade", "-")
    risk_score = audit_metrics.get("risk_score", "-")
    mfa_pct = audit_metrics.get("mfa_coverage_pct")
    secure_score = audit_metrics.get("secure_score_pct")
    total_users = audit_metrics.get("total_users", "-")
    users_no_mfa = audit_metrics.get("users_no_mfa", "-")
    last_audit = audit_metrics.get("audit_date", "-")

    # ── ALSO subscriptions ──
    also_subs: list[dict] = []
    also_mrr = 0.0
    try:
        async with (
            get_db() as db,
            db.execute(
                """SELECT r.service_name, r.contract_end, r.account_state,
                          d.monthly_cost, d.currency
                   FROM also_renewals r
                   LEFT JOIN also_subscription_details d ON r.subscription_id = d.subscription_id
                   WHERE r.customer_id = ?""",
                (customer_id,),
            ) as cur,
        ):
            for row in await cur.fetchall():
                r = dict(row)
                also_subs.append(r)
                also_mrr += r.get("monthly_cost") or 0
    except Exception as e:
        logger.debug("Failed to load ALSO subscriptions for %s: %s", customer_id, e)

    # ── Uniweb data ──
    uniweb_data: dict = {}
    uniweb_monthly = 0.0
    try:
        async with (
            get_db() as db,
            db.execute(
                "SELECT data_json FROM uniweb_accounts WHERE customer_id = ?",
                (customer_id,),
            ) as cur,
        ):
            row = await cur.fetchone()
            if row and row["data_json"]:
                uniweb_data = _json.loads(row["data_json"])
    except Exception as e:
        logger.debug("Failed to load Uniweb data for %s: %s", customer_id, e)

    uw_domains = uniweb_data.get("domains", [])
    uw_ssl = uniweb_data.get("ssl", [])
    uw_subs = uniweb_data.get("subscriptions", [])
    for sub in uw_subs:
        price_str = sub.get("Price per month", sub.get("price_monthly", ""))
        try:
            cleaned = (
                str(price_str)
                .replace(",", ".")
                .replace(" ", "")
                .replace("NOK", "")
                .replace("kr", "")
            )
            cleaned = "".join(ch for ch in cleaned if ch.isdigit() or ch == ".")
            if cleaned:
                uniweb_monthly += float(cleaned)
        except (ValueError, TypeError):
            pass

    # ── FortiGate / network info ──
    has_fortigate = bool(cust.get("FortiGateHost"))
    has_unifi = bool(cust.get("UniFiHost"))

    # ── DNS records (SPF/DKIM/DMARC) from domain data ──
    spf_ok = False
    dkim_ok = False
    dmarc_ok = False
    for dom in uw_domains:
        for rec in dom.get("dns", []):
            rtype = (rec.get("type") or "").upper()
            val = (rec.get("value") or "").lower()
            hostname = (rec.get("hostname") or "").lower()
            if rtype == "TXT":
                if "v=spf1" in val:
                    spf_ok = True
                if "v=dmarc1" in val:
                    dmarc_ok = True
            if "_domainkey" in hostname and (
                rtype == "CNAME" or (rtype == "TXT" and "k=rsa" in val)
            ):
                dkim_ok = True

    # ── Compute health grade ──
    score = 100
    if not audit_metrics:
        score -= 20
    else:
        rg = (audit_metrics.get("risk_grade") or "").upper()
        if rg in ("D", "F"):
            score -= 25
        elif rg == "C":
            score -= 10
    if mfa_pct is not None and mfa_pct < 80:
        score -= 15
    score = max(score, 0)
    if score >= 90:
        health_grade = "A"
    elif score >= 75:
        health_grade = "B"
    elif score >= 60:
        health_grade = "C"
    elif score >= 40:
        health_grade = "D"
    else:
        health_grade = "F"
    health_score = score

    total_mrr = round(also_mrr + uniweb_monthly, 2)
    report_date = now.strftime("%d.%m.%Y %H:%M")

    # ── Build HTML report ──
    def _grade_color(g: str) -> str:
        return {"A": "#3fb950", "B": "#4d9fb5", "C": "#d29922", "D": "#f85149", "F": "#8b0000"}.get(
            g, "#888"
        )

    def _check(ok: bool) -> str:
        return (
            '<span style="color:#3fb950;font-weight:700;">&#10003;</span>'
            if ok
            else '<span style="color:#f85149;font-weight:700;">&#10007;</span>'
        )

    def _fmt_nok(val: float) -> str:
        if val == 0:
            return "0 kr"
        return f"{val:,.0f} kr".replace(",", " ")

    def _esc(s: str) -> str:
        return (
            s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        )

    html = f"""<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kunderapport — {_esc(name)}</title>
<style>
  @media print {{ @page {{ margin: 15mm; }} body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; font-size:13px; color:#1a1a2e; background:#fff; padding:32px; max-width:900px; margin:0 auto; }}
  h1 {{ font-size:24px; font-weight:800; margin-bottom:4px; }}
  h2 {{ font-size:16px; font-weight:700; margin:28px 0 12px; padding-bottom:6px; border-bottom:2px solid #e5e7eb; color:#1a1a2e; }}
  .meta {{ font-size:12px; color:#6b7280; margin-bottom:24px; }}
  .grade-badge {{ display:inline-block; width:48px; height:48px; line-height:48px; border-radius:12px; font-weight:800; font-size:24px; color:#fff; text-align:center; }}
  .kpi-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:24px; }}
  .kpi {{ padding:16px 12px; border:1px solid #e5e7eb; border-radius:8px; text-align:center; }}
  .kpi-val {{ font-size:20px; font-weight:700; }}
  .kpi-label {{ font-size:11px; color:#6b7280; text-transform:uppercase; margin-top:4px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; margin-bottom:16px; }}
  th {{ text-align:left; padding:8px; background:#f8f9fa; border-bottom:2px solid #e5e7eb; font-weight:600; font-size:11px; text-transform:uppercase; color:#6b7280; }}
  td {{ padding:8px; border-bottom:1px solid #f0f0f0; }}
  .section {{ margin-bottom:8px; }}
  .footer {{ margin-top:40px; padding-top:16px; border-top:1px solid #e5e7eb; font-size:11px; color:#9ca3af; text-align:center; }}
  .print-btn {{ position:fixed; top:16px; right:16px; background:#4d9fb5; color:#fff; border:none; padding:10px 20px; border-radius:8px; font-size:14px; font-weight:600; cursor:pointer; box-shadow:0 2px 8px rgba(0,0,0,0.15); }}
  .print-btn:hover {{ background:#3a8a9e; }}
  @media print {{ .print-btn {{ display:none; }} }}
</style>
</head>
<body>
<button class="print-btn" onclick="window.print()">&#128438; Skriv ut / PDF</button>

<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;">
  <div>
    <h1>{_esc(name)}</h1>
    <div class="meta">{_esc(domain)} &middot; Rapport generert: {report_date}</div>
  </div>
  <div style="text-align:center;">
    <div class="grade-badge" style="background:{_grade_color(health_grade)};">{health_grade}</div>
    <div style="font-size:11px;color:#6b7280;margin-top:4px;">Helsescore: {health_score}/100</div>
  </div>
</div>

<div class="kpi-grid">
  <div class="kpi"><div class="kpi-val" style="color:{_grade_color(risk_grade) if isinstance(risk_grade, str) and risk_grade in "ABCDF" else "#888"};">{risk_grade}</div><div class="kpi-label">Risikograd</div></div>
  <div class="kpi"><div class="kpi-val">{f"{mfa_pct:.0f}%" if mfa_pct is not None else "-"}</div><div class="kpi-label">MFA-dekning</div></div>
  <div class="kpi"><div class="kpi-val">{f"{secure_score:.0f}%" if secure_score is not None else "-"}</div><div class="kpi-label">Secure Score</div></div>
  <div class="kpi"><div class="kpi-val">{_fmt_nok(total_mrr)}</div><div class="kpi-label">Total MRR</div></div>
</div>

<h2>Sikkerhet</h2>
<div class="section">
<table>
  <tr><td style="width:200px;color:#6b7280;">MFA-dekning</td><td style="font-weight:600;">{f"{mfa_pct:.1f}%" if mfa_pct is not None else "Ingen data"}</td></tr>
  <tr><td style="color:#6b7280;">Brukere uten MFA</td><td style="font-weight:600;{" color:#f85149;" if isinstance(users_no_mfa, int) and users_no_mfa > 0 else ""}">{users_no_mfa}</td></tr>
  <tr><td style="color:#6b7280;">Totale brukere</td><td style="font-weight:600;">{total_users}</td></tr>
  <tr><td style="color:#6b7280;">Risikograd</td><td style="font-weight:600;">{risk_grade}</td></tr>
  <tr><td style="color:#6b7280;">Risikoscore</td><td style="font-weight:600;">{risk_score}</td></tr>
  <tr><td style="color:#6b7280;">Secure Score</td><td style="font-weight:600;">{f"{secure_score:.1f}%" if secure_score is not None else "-"}</td></tr>
  <tr><td style="color:#6b7280;">Siste audit</td><td>{last_audit}</td></tr>
</table>
</div>

<h2>Nettverk</h2>
<div class="section">
<table>
  <tr><td style="width:200px;color:#6b7280;">FortiGate</td><td>{_check(has_fortigate)} {"Konfigurert" if has_fortigate else "Ikke konfigurert"}</td></tr>
  <tr><td style="color:#6b7280;">UniFi</td><td>{_check(has_unifi)} {"Konfigurert" if has_unifi else "Ikke konfigurert"}</td></tr>
</table>
</div>

<h2>Domener og e-postsikkerhet</h2>
<div class="section">
<table>
  <tr><td style="width:200px;color:#6b7280;">Uniweb-domener</td><td style="font-weight:600;">{len(uw_domains)}</td></tr>
  <tr><td style="color:#6b7280;">SSL-sertifikater</td><td style="font-weight:600;">{len(uw_ssl)}</td></tr>
  <tr><td style="color:#6b7280;">SPF</td><td>{_check(spf_ok)}</td></tr>
  <tr><td style="color:#6b7280;">DKIM</td><td>{_check(dkim_ok)}</td></tr>
  <tr><td style="color:#6b7280;">DMARC</td><td>{_check(dmarc_ok)}</td></tr>
</table>
"""

    if uw_domains:
        html += "<table><thead><tr><th>Domene</th><th>Utloper</th></tr></thead><tbody>"
        for dom in uw_domains:
            html += f"<tr><td>{_esc(dom.get('name', ''))}</td><td>{_esc(dom.get('expiry', ''))}</td></tr>"
        html += "</tbody></table>"

    html += "</div>"

    # ── ALSO Licenses ──
    html += '<h2>Lisenser (ALSO Cloud)</h2><div class="section">'
    if also_subs:
        html += f'<p style="margin-bottom:8px;color:#6b7280;">Totalt ALSO MRR: <strong style="color:#1a1a2e;">{_fmt_nok(also_mrr)}</strong> &middot; {len(also_subs)} abonnement</p>'
        html += '<table><thead><tr><th>Tjeneste</th><th>Status</th><th>Utloper</th><th style="text-align:right;">MND-kostnad</th></tr></thead><tbody>'
        for sub in also_subs:
            mc = sub.get("monthly_cost") or 0
            html += f'<tr><td>{_esc(sub.get("service_name", ""))}</td><td>{_esc(sub.get("account_state", ""))}</td><td>{_esc(sub.get("contract_end", "")[:10] if sub.get("contract_end") else "")}</td><td style="text-align:right;">{_fmt_nok(mc)}</td></tr>'
        html += "</tbody></table>"
    else:
        html += '<p style="color:#9ca3af;">Ingen ALSO-abonnement funnet.</p>'
    html += "</div>"

    # ── Uniweb Hosting ──
    html += '<h2>Hosting (Uniweb)</h2><div class="section">'
    if uw_subs:
        html += f'<p style="margin-bottom:8px;color:#6b7280;">Totalt Uniweb MND: <strong style="color:#1a1a2e;">{_fmt_nok(uniweb_monthly)}</strong> &middot; {len(uw_subs)} abonnement</p>'
        html += '<table><thead><tr><th>Tjeneste</th><th style="text-align:right;">MND-pris</th></tr></thead><tbody>'
        for sub in uw_subs:
            sname = sub.get("name", sub.get("Subscription", ""))
            sprice = sub.get("Price per month", sub.get("price_monthly", ""))
            html += f'<tr><td>{_esc(str(sname))}</td><td style="text-align:right;">{_esc(str(sprice))}</td></tr>'
        html += "</tbody></table>"
    else:
        html += '<p style="color:#9ca3af;">Ingen Uniweb-abonnement funnet.</p>'
    html += "</div>"

    # ── Footer ──
    html += f"""
<div class="footer">
  SYBR MSP Toolkit &middot; Generert {report_date} &middot; {_esc(name)}
</div>
</body>
</html>"""

    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Content-Disposition": f'inline; filename="report_{customer_id}.html"',
        },
    )


# ── API: CSV / Excel export ──────────────────────────────────────────────────


@router.post("/report/csv")
async def export_csv(user: User = Depends(get_current_user)):
    """Export key audit metrics as CSV."""
    audit_run = await _selected_audit_run(user, require_results=True)
    out_dir = audit_run.out_dir
    assert out_dir is not None

    from app.core.credentials import load_config
    from app.modules.base import SectionResult, SectionStatus
    from app.reports.generator import build_report_context

    cfg = load_config() or {}

    results = [
        SectionResult(
            name=r["name"],
            status=SectionStatus[r["status"].upper()],
            warns=r.get("warns", []),
            files=r.get("files", []),
            error=r.get("error"),
        )
        for r in audit_run.results
    ]

    customer_name = cfg.get("CustomerName", "Ukjent")
    dir_customer = out_dir.parent.name.replace("_", " ")
    if dir_customer and dir_customer != customer_name:
        customer_name = dir_customer

    ctx = build_report_context(
        customer_name=customer_name,
        org_domain=cfg.get("PrimaryDomain", ""),
        out_dir=out_dir,
        results=results,
    )

    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    # Header
    writer.writerow(["Kategori", "Metrikk", "Verdi", "Status"])

    # Key metrics
    writer.writerow(["Kunde", "Navn", customer_name, ""])
    writer.writerow(["Kunde", "Domene", ctx.get("org_domain", ""), ""])
    writer.writerow(["Kunde", "Rapportdato", ctx.get("report_date", ""), ""])
    writer.writerow(["Sikkerhet", "Risikograd", ctx["risk"]["grade"], ctx["risk"]["level"]])
    writer.writerow(["Sikkerhet", "Risikoscore", ctx["risk"]["score"], "av 100"])
    writer.writerow(["Brukere", "Totalt", ctx["users"]["total"], ""])
    writer.writerow(["Brukere", "Aktive", ctx["users"]["enabled"], ""])
    writer.writerow(["Brukere", "Gjester", ctx["users"]["guests"], ""])
    writer.writerow(["MFA", "Dekning %", ctx["mfa"]["pct"], ""])
    writer.writerow(
        ["MFA", "Uten MFA", ctx["mfa"]["no_mfa"], "Kritisk" if ctx["mfa"]["no_mfa"] > 0 else "OK"]
    )
    writer.writerow(["Secure Score", "Score %", ctx["secure_score"]["pct"], ""])
    writer.writerow(["Conditional Access", "Aktive policyer", ctx["ca"]["enabled"], ""])

    if ctx.get("intune", {}).get("total", 0) > 0:
        writer.writerow(["Intune", "Enheter totalt", ctx["intune"]["total"], ""])
        writer.writerow(["Intune", "Samsvar %", ctx["intune"]["compliance_pct"], ""])
        writer.writerow(["Intune", "Ikke-samsvar", ctx["intune"]["noncompliant"], ""])

    if ctx.get("admin_roles"):
        writer.writerow(["Admin", "Global Admins", ctx["admin_roles"]["global_admin_count"], ""])
        writer.writerow(["Admin", "Rolletildelinger", ctx["admin_roles"]["total_assignments"], ""])

    # Licenses
    for lic in ctx.get("licenses", []):
        status = "Advarsel" if lic["warn"] else "OK"
        writer.writerow(
            ["Lisens", lic["part"], f"{lic['used']}/{lic['total']} ({lic['pct']:.0f}%)", status]
        )

    # Recommendations
    for i, rec in enumerate(ctx.get("recommendations", []), 1):
        writer.writerow(["Anbefaling", f"#{i} {rec['title']}", rec["priority"], rec["effort"]])

    # All warnings
    for w in ctx.get("all_warns", []):
        writer.writerow(["Varsel", w, "", ""])

    csv_content = output.getvalue()

    # Save CSV to audit folder
    csv_path = out_dir / f"audit_export_{customer_name.replace(' ', '_')}.csv"
    csv_path.write_text(csv_content, encoding="utf-8-sig")  # BOM for Excel compat

    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
    )


@router.post("/export/excel")
async def export_dashboard_excel(user: User = Depends(get_current_user)):
    """Export the caller's customers with metrics as Excel-compatible CSV.

    Took no user argument at all, so it exported every customer's audit
    metrics — grade, score, MFA coverage, admin counts — to anyone logged in,
    and wrote the cross-customer result to disk in plaintext besides.
    """
    import csv
    import io

    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_read_json
    from app.core.rbac import filter_customers, get_accessible_customer_ids

    customers = filter_customers(
        CustomerManager.list_customers(), await get_accessible_customer_ids(user)
    )
    audit_dir = get_audit_dir()

    headers = [
        "Customer",
        "Domain",
        "Risk Grade",
        "Risk Score",
        "MFA Coverage %",
        "Secure Score %",
        "Total Users",
        "Users Without MFA",
        "CA Policies",
        "Intune Compliance %",
        "Global Admins",
        "Last Audit Date",
        "Tags",
    ]

    rows = []
    for c in customers:
        name = c.get("CustomerName", "Ukjent")
        domain = c.get("PrimaryDomain", "")
        cid = c.get("_id", "")
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
        customer_dir = audit_dir / safe_name

        metrics = {}
        last_audit = ""
        if customer_dir.exists():
            runs = sorted([d for d in customer_dir.iterdir() if d.is_dir()], reverse=True)
            for run_dir in runs:
                metrics_path = run_dir / "_audit_metrics.json"
                if metrics_path.exists():
                    try:
                        metrics = encrypted_read_json(metrics_path)
                        last_audit = run_dir.name
                    except Exception as e:
                        logger.warning("Failed to read metrics for %s: %s", run_dir, e)
                    break

        # Format last audit date for readability
        fmt_date = last_audit
        if last_audit and len(last_audit) >= 13:
            try:
                fmt_date = (
                    f"{last_audit[8:10]}:{last_audit[11:13]} {last_audit[0:10].replace('-', '.')}"
                )
            except (IndexError, ValueError) as e:
                logger.debug("Failed to format audit date %s: %s", last_audit, e)

        tags = CustomerManager.get_tags(cid)
        tag_str = ", ".join(tags) if tags else ""

        rows.append(
            [
                name,
                domain,
                metrics.get("risk_grade", ""),
                metrics.get("risk_score", ""),
                round(metrics["mfa_coverage_pct"], 1) if "mfa_coverage_pct" in metrics else "",
                round(metrics["secure_score_pct"], 1) if "secure_score_pct" in metrics else "",
                metrics.get("total_users", ""),
                metrics.get("users_no_mfa", ""),
                metrics.get("ca_policies_enabled", ""),
                round(metrics["intune_compliance_pct"], 1)
                if "intune_compliance_pct" in metrics
                else "",
                metrics.get("admin_roles_ga_count", ""),
                fmt_date,
                tag_str,
            ]
        )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)

    csv_content = output.getvalue()

    # Save to audit output directory
    from datetime import datetime as _dt

    timestamp = _dt.now().strftime("%Y-%m-%d_%H%M")
    csv_path = audit_dir / f"dashboard_export_{timestamp}.csv"
    csv_path.write_text(csv_content, encoding="utf-8-sig")

    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="dashboard_export_{timestamp}.csv"',
            "X-File-Path": str(csv_path),
        },
    )


# ── API: Report generation ───────────────────────────────────────────────────


@router.post("/report/generate")
async def generate_report(request: Request, user: User = Depends(get_current_user)):
    audit_run = await _selected_audit_run(user, require_results=True)
    out_dir = audit_run.out_dir
    assert out_dir is not None

    body = await request.json()
    fmt = body.get("format", "html")
    report_type = body.get("report_type", "tech")
    lang = body.get("lang", "no")
    frameworks = body.get("frameworks", "all")
    theme = body.get("theme", "light")
    formats = ["html"] if fmt == "html" else ["html", "pdf"]

    from app.core.config import AUDIT_DIR
    from app.core.credentials import load_config
    from app.modules.base import SectionResult, SectionStatus
    from app.reports.generator import generate_reports

    cfg = load_config() or {}
    results = [
        SectionResult(
            name=r["name"],
            status=SectionStatus[r["status"].upper()],
            warns=r.get("warns", []),
            files=r.get("files", []),
            error=r.get("error"),
        )
        for r in audit_run.results
    ]

    # Derive customer name from loaded audit dir if config doesn't match
    customer_name = cfg.get("CustomerName", "Ukjent")
    org_domain = cfg.get("PrimaryDomain", "")
    dir_customer = out_dir.parent.name.replace("_", " ")
    if dir_customer and dir_customer != customer_name:
        customer_name = dir_customer
        org_domain = ""  # unknown for historical runs of different customers

    try:
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(
            None,
            lambda: generate_reports(
                customer_name=customer_name,
                org_domain=org_domain,
                out_dir=out_dir,
                results=results,
                formats=formats,
                report_type=report_type,
                lang=lang,
                frameworks=frameworks,
                theme=theme,
            ),
        )
        html_path = output.get("html")
        pdf_path = output.get("pdf")
        resp: dict = {"ok": True}
        if html_path:
            resp["html_url"] = f"/audit_data/{html_path.relative_to(AUDIT_DIR)}"
        if pdf_path:
            resp["pdf_url"] = f"/audit_data/{pdf_path.relative_to(AUDIT_DIR)}"

        from app.core.activity_log import log_activity as _log_act2

        _log_act2("report_generated", detail=f"{report_type}/{fmt}", customer=customer_name)

        return resp
    except Exception as e:
        logger.error("Report generation failed: %s", e)
        raise IntegrationError("Rapportgenerering feilet") from e


# ── Report Archive ────────────────────────────────────────────────────────────


@router.get("/reports/archive")
async def list_report_archive(user: User = Depends(get_current_user)):
    """List all audit report directories grouped by customer."""

    from app.core.config import get_audit_dir

    audit_dir = get_audit_dir()
    if not audit_dir.exists():
        return {"customers": [], "total_reports": 0, "total_size_mb": 0}

    # Scoped: this listing is what tells a caller which paths exist under the
    # audit tree, and /audit_data serves them.
    from app.core.rbac import check_audit_path_access

    customers: list[dict] = []
    total_reports = 0
    total_size = 0

    for customer_dir in sorted(audit_dir.iterdir()):
        if not customer_dir.is_dir():
            continue
        if not await check_audit_path_access(user, customer_dir.name):
            continue
        runs: list[dict] = []
        for run_dir in sorted(customer_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            files = list(run_dir.iterdir())
            size = sum(f.stat().st_size for f in files if f.is_file())
            has_pdf = any(f.suffix in (".pdf", ".enc") and "pdf" in f.name.lower() for f in files)
            has_html = any(f.suffix == ".html" for f in files)
            runs.append(
                {
                    "name": run_dir.name,
                    "path": str(run_dir.relative_to(audit_dir)),
                    "file_count": len(files),
                    "size_bytes": size,
                    "size_mb": round(size / 1048576, 1),
                    "has_pdf": has_pdf,
                    "has_html": has_html,
                    "date": run_dir.name[:10] if len(run_dir.name) >= 10 else "",
                }
            )
            total_reports += 1
            total_size += size

        if runs:
            customers.append(
                {
                    "customer_name": customer_dir.name.replace("_", " "),
                    "dir_name": customer_dir.name,
                    "runs": runs,
                    "run_count": len(runs),
                    "total_size_mb": round(sum(r["size_bytes"] for r in runs) / 1048576, 1),
                }
            )

    return {
        "customers": customers,
        "total_reports": total_reports,
        "total_size_mb": round(total_size / 1048576, 1),
    }


@router.post("/reports/archive/delete")
async def delete_report(request: Request, user: User = Depends(require_role(Role.admin))):
    """Delete a specific report run directory. Requires admin."""
    import shutil

    from app.core.activity_log import log_activity
    from app.core.config import get_audit_dir

    body = await request.json()
    rel_path = body.get("path", "").strip()
    if not rel_path:
        raise ValidationError("Path required")

    audit_dir = get_audit_dir()
    target = (audit_dir / rel_path).resolve()

    # Security: ensure target is inside audit_dir
    if not str(target).startswith(str(audit_dir.resolve())):
        raise AuthError("Invalid path")
    if not target.exists() or not target.is_dir():
        raise NotFoundError("Not found")

    shutil.rmtree(target)
    log_activity("report_deleted", detail=f"Deleted report: {rel_path}", user=user.username)
    return {"ok": True, "deleted": rel_path}


@router.post("/reports/archive/cleanup")
async def cleanup_old_reports(request: Request, user: User = Depends(require_role(Role.admin))):
    """Delete reports older than N months. Requires admin."""
    import shutil
    from datetime import datetime, timedelta

    from app.core.activity_log import log_activity
    from app.core.config import get_audit_dir

    body = await request.json()
    months = int(body.get("months", 6))
    cutoff = datetime.now(UTC) - timedelta(days=months * 30)
    audit_dir = get_audit_dir()

    deleted = 0
    freed_bytes = 0

    if not audit_dir.exists():
        return {"ok": True, "deleted": 0, "freed_mb": 0}

    for customer_dir in audit_dir.iterdir():
        if not customer_dir.is_dir():
            continue
        for run_dir in list(customer_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            # Parse date from dir name (format: YYYY-MM-DD_HHMM)
            try:
                date_str = run_dir.name[:10]
                run_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
            except (ValueError, IndexError):
                continue
            if run_date < cutoff:
                size = sum(f.stat().st_size for f in run_dir.rglob("*") if f.is_file())
                shutil.rmtree(run_dir)
                deleted += 1
                freed_bytes += size

        # Clean up empty customer dirs
        if customer_dir.exists() and not any(customer_dir.iterdir()):
            customer_dir.rmdir()

    log_activity(
        "reports_cleanup",
        detail=f"Cleaned up {deleted} reports older than {months} months, freed {round(freed_bytes / 1048576, 1)} MB",
        user=user.username,
    )
    return {"ok": True, "deleted": deleted, "freed_mb": round(freed_bytes / 1048576, 1)}


# ── Multi-Customer Batch Report (QBR) ────────────────────────────────────────


@router.post("/reports/batch-summary")
async def batch_summary_report(request: Request, user: User = Depends(get_current_user)):
    """Generate a combined HTML report with summaries for all audited customers."""
    from datetime import datetime

    from app.core.config import get_audit_dir, load_app_settings
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_read_json

    body = await request.json()
    customer_ids = body.get("customer_ids", [])  # empty = all with metrics

    customers = CustomerManager.list_customers()
    audit_dir = get_audit_dir()
    settings = load_app_settings()
    company = (settings.get("branding") or {}).get("company_name", "SYBR AS")
    now = datetime.now(UTC)

    summaries: list[dict] = []

    for c in customers:
        cid = c.get("_id", "")
        if customer_ids and cid not in customer_ids:
            continue
        name = c.get("CustomerName", "Unknown")
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
        customer_dir = audit_dir / safe_name
        if not customer_dir.exists():
            continue

        runs = sorted([d for d in customer_dir.iterdir() if d.is_dir()], reverse=True)
        for run_dir in runs:
            metrics_path = run_dir / "_audit_metrics.json"
            if metrics_path.exists():
                try:
                    m = encrypted_read_json(metrics_path)
                    summaries.append(
                        {
                            "name": name,
                            "domain": c.get("PrimaryDomain", ""),
                            "grade": m.get("risk_grade", "-"),
                            "score": m.get("risk_score", "-"),
                            "mfa": m.get("mfa_coverage_pct"),
                            "ss": m.get("secure_score_pct"),
                            "users": m.get("total_users", 0),
                            "warns": m.get("total_warns", 0),
                            "date": run_dir.name[:10],
                        }
                    )
                except Exception as e:
                    logger.debug("Failed to read metrics for %s: %s", name, e)
                break

    if not summaries:
        raise NotFoundError("No audited customers found")

    summaries.sort(key=lambda x: x.get("score", 0))

    # Grade stats
    grades = {}
    for s in summaries:
        g = s["grade"]
        grades[g] = grades.get(g, 0) + 1
    avg_score = (
        round(
            sum(s.get("score", 0) for s in summaries if isinstance(s.get("score"), (int, float)))
            / len(summaries),
            1,
        )
        if summaries
        else 0
    )
    avg_mfa = (
        round(sum(s.get("mfa", 0) or 0 for s in summaries) / len(summaries), 1) if summaries else 0
    )

    grade_colors = {"A": "#3fb950", "B": "#4d9fb5", "C": "#d29922", "D": "#f85149", "F": "#8b0000"}

    # Build HTML
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>QBR Security Summary — {company}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 24px; color: #1a1a2e; background: #fff; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  .subtitle {{ color: #666; font-size: 13px; margin-bottom: 24px; }}
  .kpi-row {{ display: flex; gap: 16px; margin-bottom: 24px; }}
  .kpi {{ flex: 1; padding: 16px; border: 1px solid #e5e7eb; border-radius: 8px; text-align: center; }}
  .kpi-val {{ font-size: 28px; font-weight: 800; }}
  .kpi-label {{ font-size: 11px; color: #888; text-transform: uppercase; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; padding: 8px 12px; border-bottom: 2px solid #e5e7eb; font-size: 11px; text-transform: uppercase; color: #888; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #f0f0f0; }}
  .grade {{ display: inline-block; width: 28px; height: 28px; line-height: 28px; border-radius: 6px; text-align: center; color: #fff; font-weight: 800; font-size: 14px; }}
  .footer {{ margin-top: 32px; padding-top: 12px; border-top: 1px solid #e5e7eb; font-size: 11px; color: #999; }}
  @media print {{ body {{ padding: 12px; }} }}
</style></head><body>
<h1>Quarterly Security Summary</h1>
<div class="subtitle">Generated {now.strftime("%Y-%m-%d %H:%M")} UTC by {company} — {len(summaries)} customers</div>

<div class="kpi-row">
  <div class="kpi"><div class="kpi-val">{len(summaries)}</div><div class="kpi-label">Customers</div></div>
  <div class="kpi"><div class="kpi-val">{avg_score}/100</div><div class="kpi-label">Avg Risk Score</div></div>
  <div class="kpi"><div class="kpi-val">{avg_mfa:.0f}%</div><div class="kpi-label">Avg MFA</div></div>
  <div class="kpi"><div class="kpi-val">{grades.get("A", 0) + grades.get("B", 0)}</div><div class="kpi-label">Grade A/B</div></div>
  <div class="kpi"><div class="kpi-val" style="color:#f85149;">{grades.get("D", 0) + grades.get("F", 0)}</div><div class="kpi-label">Grade D/F</div></div>
</div>

<table>
<thead><tr><th>Customer</th><th>Domain</th><th style="text-align:center;">Grade</th><th style="text-align:center;">Score</th><th style="text-align:center;">MFA%</th><th style="text-align:center;">Secure Score%</th><th style="text-align:center;">Users</th><th style="text-align:center;">Warnings</th><th>Last Audit</th></tr></thead>
<tbody>"""

    for s in summaries:
        gc = grade_colors.get(s["grade"], "#888")
        mfa_str = f"{s['mfa']:.0f}%" if s["mfa"] is not None else "-"
        ss_str = f"{s['ss']:.0f}%" if s["ss"] is not None else "-"
        mfa_color = (
            "#3fb950"
            if (s["mfa"] or 0) >= 95
            else "#d29922"
            if (s["mfa"] or 0) >= 80
            else "#f85149"
        )
        html += f"""<tr>
  <td style="font-weight:600;">{s["name"]}</td>
  <td style="color:#888;font-size:12px;">{s["domain"]}</td>
  <td style="text-align:center;"><span class="grade" style="background:{gc};">{s["grade"]}</span></td>
  <td style="text-align:center;font-weight:600;">{s["score"]}</td>
  <td style="text-align:center;font-weight:600;color:{mfa_color};">{mfa_str}</td>
  <td style="text-align:center;">{ss_str}</td>
  <td style="text-align:center;">{s["users"]}</td>
  <td style="text-align:center;color:{"#f85149" if s["warns"] > 0 else "#888"};">{s["warns"]}</td>
  <td style="font-size:12px;color:#888;">{s["date"]}</td>
</tr>"""

    html += f"""</tbody></table>
<div class="footer">Generated by {company} MSP Toolkit v{{version}} — Confidential</div>
</body></html>"""

    # Fill version
    try:
        from app.core.version import get_version

        html = html.replace("{version}", get_version())
    except Exception as e:
        logger.debug("Failed to resolve version string: %s", e)
        html = html.replace("{version}", "")

    from app.core.activity_log import log_activity

    log_activity("batch_report_generated", detail=f"{len(summaries)} customers", user=user.username)

    return Response(content=html, media_type="text/html")
