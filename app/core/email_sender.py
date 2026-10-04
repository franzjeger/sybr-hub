"""Email sender — send audit reports via SMTP."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

log = logging.getLogger(__name__)


def send_report_email(
    to: str,
    subject: str,
    body_html: str,
    attachment_path: Path | None = None,
    smtp_config: dict | None = None,
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

    from app.core.messages import invalid

    if not server or not user or not password:
        raise invalid("err_smtp_settings_missing")

    # Support comma-separated recipients
    recipients = [addr.strip() for addr in (to or "").split(",") if addr.strip()]
    if not recipients:
        raise invalid("err_smtp_no_recipient")

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


def report_language(pdf_path: Path | None) -> str:
    """The language of the report an e-mail carries, else the hub's language.

    A PDF is rendered from the HTML report beside it, and that file says its
    language in ``<html lang>``. Without an attachment, or for a PDF whose
    HTML is gone, the hub's own language decides: it is the language the
    scheduler writes its reports in.
    """
    import re

    if pdf_path is not None:
        try:
            from app.core.encryption import encrypted_read_text

            head = encrypted_read_text(pdf_path.with_suffix(".html"))[:2000]
            m = re.search(r'<html\b[^>]*\blang="(no|en)"', head)
            if m:
                return m.group(1)
        except Exception as e:  # a missing or unreadable file: fall back
            log.debug("Could not read the language of %s: %s", pdf_path, e)
    from app.core.config import load_app_settings

    lang = load_app_settings().get("ui_language", "no")
    return lang if lang in ("no", "en") else "no"


def report_email_subject(customer_name: str, run_date: str, lang: str = "no") -> str:
    from app.reports.i18n import T

    return str(T(lang)("email_subject", customer=customer_name, date=run_date))


def build_report_body_html(
    customer_name: str,
    run_date: str,
    metrics: dict | None = None,
    *,
    lang: str = "no",
    attached: bool = True,
) -> str:
    """A short HTML summary of the audit, in the report's language.

    It was Norwegian whatever the report's language. It printed "None" for a
    score the audit could not compute and "None%" for coverage it could not
    measure, and it said a PDF was attached when none was: the scheduler
    renders HTML only, so an automatic e-mail usually carried no PDF at all.
    """
    from html import escape

    from app.reports.i18n import T

    t = T(lang)
    m = metrics or {}

    def shown(key: str, suffix: str = "") -> str:
        value = m.get(key)
        if value is None or value == "":
            return escape(t.email_not_measured)
        if isinstance(value, float):
            value = f"{value:.0f}"
        return escape(f"{value}{suffix}")

    risk_grade = str(m.get("risk_grade") or "?")
    grade_color = {
        "A": "#3fb950",
        "B": "#3fb950",
        "C": "#d29922",
        "D": "#f85149",
        "E": "#f85149",
        "F": "#f85149",
    }.get(risk_grade, "#8b949e")
    no_grade = (
        f'<p style="color: #57606a; font-size: 13px;">{escape(t.email_no_grade)}</p>'
        if risk_grade == "?"
        else ""
    )
    attachment = t.email_pdf_attached if attached else t.email_no_pdf

    return f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; color: #1a3148;">
  <h2 style="margin-bottom: 4px;">{escape(t("email_heading", customer=customer_name))}</h2>
  <p style="color: #57606a; margin-top: 0;">{escape(t("email_completed", date=run_date))}</p>

  <table style="border-collapse: collapse; width: 100%; margin: 16px 0;">
    <tr>
      <td style="padding: 12px; background: {grade_color}; color: white; text-align: center; border-radius: 8px 0 0 8px; font-size: 28px; font-weight: bold; width: 80px;">
        {escape(risk_grade)}
      </td>
      <td style="padding: 12px; background: #f5f7fa; border-radius: 0 8px 8px 0;">
        <strong>{escape(t.email_lbl_grade)}:</strong> {escape(risk_grade)}<br>
        <strong>{escape(t.email_lbl_score)}:</strong> {shown("risk_score")}<br>
        <strong>{escape(t.email_lbl_mfa)}:</strong> {shown("mfa_coverage_pct", "%")}<br>
        <strong>{escape(t.email_lbl_secure_score)}:</strong> {shown("secure_score_pct", "%")}<br>
        <strong>{escape(t.email_lbl_users)}:</strong> {shown("total_users")} &nbsp;|&nbsp; <strong>{escape(t.email_lbl_warnings)}:</strong> {shown("total_warns")}
      </td>
    </tr>
  </table>
  {no_grade}
  <p style="color: #57606a; font-size: 13px;">
    {escape(attachment)}
  </p>

  <hr style="border: none; border-top: 1px solid #d0d7de; margin: 20px 0;">
  <p style="color: #8b949e; font-size: 11px;">{escape(t.email_footer)}</p>
</div>
"""


class AutoSendFailure:
    """Why the report e-mail after an audit did not go out, as a message key.

    auto_send_after_audit returned a Norwegian sentence, and the audit screen
    showed it to a reader in any language. The caller words this one: the
    key is in app/core/messages.py, so the web layer renders it in the
    reader's language and the browser from ui_i18n.json. ``str()`` is the
    Norwegian text, for the scheduler's log line, as messages.py has it.
    """

    __slots__ = ("key", "params")

    def __init__(self, key: str, **params: str) -> None:
        self.key = key
        self.params = params

    def __str__(self) -> str:
        from app.core.messages import text

        return text(self.key, **self.params)

    def __repr__(self) -> str:
        return f"AutoSendFailure({self.key!r}, {self.params!r})"


def auto_send_after_audit(out_dir: Path) -> AutoSendFailure | None:
    """If auto-send is enabled, email the run's report.

    None when it went out or auto-send is off; otherwise why it did not.
    """
    from app.core.config import load_app_settings

    settings = load_app_settings()
    if not settings.get("email_auto_send"):
        return None

    recipient = settings.get("email_default_recipient", "").strip()
    if not recipient:
        return AutoSendFailure("err_auto_send_no_recipient")

    smtp_server = settings.get("smtp_server", "").strip()
    if not smtp_server:
        return AutoSendFailure("err_auto_send_no_smtp")

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

    lang = report_language(pdf_path)
    body = build_report_body_html(
        customer_name, run_date, metrics, lang=lang, attached=pdf_path is not None
    )
    subject = report_email_subject(customer_name, run_date, lang)

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
        return AutoSendFailure("err_auto_send_failed", error=str(e))
