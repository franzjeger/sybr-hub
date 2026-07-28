"""Email sender — send audit reports via SMTP."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def send_report_email(
    to: str,
    subject: str,
    body_html: str,
    attachment_path: Optional[Path] = None,
    smtp_config: Optional[dict] = None,
) -> None:
    """Send an HTML email with optional PDF attachment.

    Args:
        to: Recipient email address (comma-separated for multiple recipients).
        subject: Email subject line.
        body_html: HTML body content.
        attachment_path: Path to encrypted PDF on disk (will be decrypted before attaching).
        smtp_config: Dict with keys: smtp_server, smtp_port, smtp_user, smtp_password, smtp_from.

    Raises:
        ValueError: If configuration is missing.
        smtplib.SMTPException: On SMTP errors.
    """
    if not smtp_config:
        from app.core.config import load_app_settings
        smtp_config = load_app_settings()

    server = smtp_config.get("smtp_server", "").strip()
    port = int(smtp_config.get("smtp_port", 587))
    user = smtp_config.get("smtp_user", "").strip()
    password = smtp_config.get("smtp_password", "").strip()
    from_addr = smtp_config.get("smtp_from", "").strip() or user

    from app.core.exceptions import ValidationError
    if not server or not user or not password:
        raise ValidationError("SMTP-innstillinger mangler (server, bruker eller passord)")

    if not to or not to.strip():
        raise ValidationError("Ingen mottaker-epostadresse angitt")

    # Support comma-separated recipients
    recipients = [addr.strip() for addr in to.split(",") if addr.strip()]
    if not recipients:
        raise ValidationError("Ingen mottaker-epostadresse angitt")

    msg = MIMEMultipart("mixed")
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    msg.attach(MIMEText(body_html, "html", "utf-8"))

    # Attach decrypted PDF if provided
    if attachment_path and attachment_path.exists():
        from app.core.encryption import encrypted_read_bytes
        pdf_data = encrypted_read_bytes(attachment_path)
        part = MIMEApplication(pdf_data, _subtype="pdf")
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=attachment_path.name,
        )
        msg.attach(part)

    log.info("Sending email to %s via %s:%s", recipients, server, port)

    if port == 465:
        # SSL (implicit TLS)
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(server, port, context=context, timeout=30) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        # STARTTLS (port 587 or other)
        context = ssl.create_default_context()
        with smtplib.SMTP(server, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(msg)

    log.info("Email sent successfully to %s", recipients)


def build_report_body_html(
    customer_name: str,
    run_date: str,
    metrics: Optional[dict] = None,
) -> str:
    """Build a brief HTML email body summarizing the audit."""
    risk_grade = (metrics or {}).get("risk_grade", "?")
    risk_score = (metrics or {}).get("risk_score", "?")
    mfa_pct = (metrics or {}).get("mfa_coverage_pct", "?")
    secure_score = (metrics or {}).get("secure_score_pct", "?")
    total_users = (metrics or {}).get("total_users", "?")
    total_warns = (metrics or {}).get("total_warns", "?")

    grade_color = {
        "A": "#3fb950", "B": "#3fb950",
        "C": "#d29922", "D": "#f85149",
        "E": "#f85149", "F": "#f85149",
    }.get(risk_grade, "#8b949e")

    return f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; color: #1a3148;">
  <h2 style="margin-bottom: 4px;">Auditrapport: {customer_name}</h2>
  <p style="color: #57606a; margin-top: 0;">Audit fullfort {run_date}</p>

  <table style="border-collapse: collapse; width: 100%; margin: 16px 0;">
    <tr>
      <td style="padding: 12px; background: {grade_color}; color: white; text-align: center; border-radius: 8px 0 0 8px; font-size: 28px; font-weight: bold; width: 80px;">
        {risk_grade}
      </td>
      <td style="padding: 12px; background: #f5f7fa; border-radius: 0 8px 8px 0;">
        <strong>Risikograd:</strong> {risk_grade} (poeng: {risk_score})<br>
        <strong>MFA-dekning:</strong> {mfa_pct}%<br>
        <strong>Secure Score:</strong> {secure_score}%<br>
        <strong>Brukere:</strong> {total_users} &nbsp;|&nbsp; <strong>Varsler:</strong> {total_warns}
      </td>
    </tr>
  </table>

  <p style="color: #57606a; font-size: 13px;">
    PDF-rapporten er vedlagt denne e-posten. For full detaljer, se den vedlagte rapporten.
  </p>

  <hr style="border: none; border-top: 1px solid #d0d7de; margin: 20px 0;">
  <p style="color: #8b949e; font-size: 11px;">Sendt automatisk fra SYBR MSP Toolkit</p>
</div>
"""


def auto_send_after_audit(out_dir: Path) -> Optional[str]:
    """If auto-send is enabled, generate PDF and email it. Returns None on success, error string on failure."""
    from app.core.config import load_app_settings

    settings = load_app_settings()
    if not settings.get("email_auto_send"):
        return None

    recipient = settings.get("email_default_recipient", "").strip()
    if not recipient:
        return "Auto-send aktivert, men ingen standard mottaker konfigurert"

    smtp_server = settings.get("smtp_server", "").strip()
    if not smtp_server:
        return "Auto-send aktivert, men SMTP-server ikke konfigurert"

    # Find the PDF report in out_dir
    pdf_path = None
    for f in out_dir.iterdir():
        if f.suffix == ".pdf" and "tech" not in f.name.lower():
            pdf_path = f
            break
    if not pdf_path:
        # Fall back to any PDF
        for f in out_dir.iterdir():
            if f.suffix == ".pdf":
                pdf_path = f
                break

    # Load metrics for the email body
    metrics = None
    metrics_path = out_dir / "_audit_metrics.json"
    if metrics_path.exists():
        from app.core.encryption import encrypted_read_json
        try:
            metrics = encrypted_read_json(metrics_path)
        except Exception as e:
            log.warning("Failed to load audit metrics for email: %s", e)

    customer_name = out_dir.parent.name.replace("_", " ")
    run_date = out_dir.name

    body = build_report_body_html(customer_name, run_date, metrics)
    subject = f"Auditrapport — {customer_name} ({run_date})"

    try:
        send_report_email(
            to=recipient,
            subject=subject,
            body_html=body,
            attachment_path=pdf_path,
            smtp_config=settings,
        )
        return None  # success
    except Exception as e:
        log.exception("auto_send_after_audit failed")
        return f"E-post feilet: {e}"
