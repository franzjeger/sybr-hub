"""Automatic audit scheduler with webhook notifications."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import get_audit_dir, get_scheduler_config

log = logging.getLogger(__name__)

class AuditScheduler:
    """Runs audits on a schedule and sends webhook alerts on changes."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def start(self):
        """Start the scheduler loop if enabled."""
        config = get_scheduler_config()
        if not config.get("enabled"):
            log.info("Scheduler disabled")
            return
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())
        log.info("Scheduler started (interval: %dh)", config.get("interval_hours", 168))

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self):
        """Main scheduler loop."""
        while True:
            config = get_scheduler_config()
            interval = config.get("interval_hours", 168) * 3600

            try:
                await asyncio.sleep(interval)
                await self._run_scheduled_audit()
                await self._check_credential_expiry()
                await self._scan_also_renewals()
                await self._maybe_create_backup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Scheduler error: %s", e)
                await asyncio.sleep(300)  # retry in 5 min

    async def _run_scheduled_audit(self):
        """Run audits for all customers (or just the active one) depending on config."""
        config = get_scheduler_config()
        audit_all = config.get("audit_all_customers", True)

        if audit_all:
            await self._run_all_customers_audit()
        else:
            await self._run_single_customer_audit()

    async def _run_single_customer_audit(self):
        """Run an audit for the currently active customer only."""
        from app.core.credentials import load_config
        from app.modules.m365_audit.auth import AuthManager
        from app.modules.m365_audit.collector import AuditCollector, make_output_dir

        cfg = load_config()
        if not cfg:
            return

        customer_name = cfg.get("CustomerName", "Ukjent")
        log.info("Scheduled audit starting for %s", customer_name)

        try:
            self._log_activity("audit_started", "Planlagt audit startet", customer_name)
            auth = AuthManager.from_config()
            out_dir = make_output_dir(customer_name)
            collector = AuditCollector(auth=auth, out_dir=out_dir)
            results = await collector.run()

            from app.reports.generator import build_report_context
            ctx = build_report_context(
                customer_name=customer_name,
                org_domain=cfg.get("PrimaryDomain", ""),
                out_dir=out_dir,
                results=results,
            )

            await self._check_and_alert(ctx, customer_name)
            await self._notify_audit_completed(customer_name)

            # Auto-generate report + send email if configured
            await self._auto_report_and_email(customer_name, cfg, out_dir, results)

            self._log_activity("audit_completed", "Planlagt audit fullfort", customer_name)

        except Exception as e:
            log.error("Scheduled audit failed: %s", e)
            await self._send_webhook(f"⚠️ Scheduled audit failed for {customer_name}: {e}")

    async def _run_all_customers_audit(self):
        """Rotate through all customers, audit each one, and restore the original active customer."""
        import shutil

        from app.core.credentials import cert_path as get_cert_path
        from app.core.credentials import save_config
        from app.core.customer import CustomerManager
        from app.modules.m365_audit.auth import AuthManager
        from app.modules.m365_audit.collector import AuditCollector, make_output_dir
        from app.reports.generator import build_report_context

        # Remember original active customer to restore afterwards
        original_active_id = CustomerManager.get_active_id()

        customers = CustomerManager.list_customers()
        if not customers:
            log.warning("Scheduled audit: no customers registered, skipping")
            return

        total = len(customers)
        log.info("Scheduled audit cycle starting for %d customer(s)", total)
        audited: list[str] = []
        failed: list[str] = []

        for idx, cust in enumerate(customers):
            cust_id = cust.get("_id", "")
            cust_name = cust.get("CustomerName", cust_id or "Ukjent")

            log.info("Scheduled audit [%d/%d]: %s", idx + 1, total, cust_name)

            # ── Switch to this customer ──
            try:
                full_cust = CustomerManager.get_customer(cust_id)
                if not full_cust:
                    log.warning("Customer %s not found, skipping", cust_name)
                    failed.append(f"{cust_name} (ikke funnet)")
                    continue

                CustomerManager.set_active(cust_id)
                config_to_save = {k: v for k, v in full_cust.items() if not k.startswith("_")}
                save_config(config_to_save)

                # Copy certificate for this customer
                cert_path = CustomerManager.get_cert_path(cust_id)
                if cert_path.exists():
                    shutil.copy2(str(cert_path), str(get_cert_path()))
            except Exception as e:
                log.error("Failed to switch to customer %s: %s", cust_name, e)
                failed.append(f"{cust_name} (bytte feilet: {e})")
                continue

            # ── Run audit for this customer ──
            try:
                self._log_activity("audit_started", f"Planlagt audit startet ({idx+1}/{total})", cust_name)

                auth = AuthManager.from_config()
                out_dir = make_output_dir(cust_name)
                collector = AuditCollector(auth=auth, out_dir=out_dir)
                results = await collector.run()

                ctx = build_report_context(
                    customer_name=cust_name,
                    org_domain=full_cust.get("PrimaryDomain", ""),
                    out_dir=out_dir,
                    results=results,
                )

                await self._check_and_alert(ctx, cust_name)
                await self._notify_audit_completed(cust_name)

                # Auto-generate report + send email if configured
                await self._auto_report_and_email(cust_name, full_cust, out_dir, results)

                audited.append(cust_name)
                self._log_activity("audit_completed", f"Planlagt audit fullfort ({idx+1}/{total})", cust_name)
                log.info("Scheduled audit completed for %s", cust_name)

            except Exception as e:
                log.error("Scheduled audit failed for %s: %s", cust_name, e)
                failed.append(f"{cust_name} ({e})")
                await self._send_webhook(f"⚠️ Scheduled audit failed for {cust_name}: {e}")

        # ── Restore original active customer ──
        if original_active_id:
            try:
                CustomerManager.set_active(original_active_id)
                orig_cust = CustomerManager.get_customer(original_active_id)
                if orig_cust:
                    config_to_save = {k: v for k, v in orig_cust.items() if not k.startswith("_")}
                    save_config(config_to_save)
                    cert_path = CustomerManager.get_cert_path(original_active_id)
                    if cert_path.exists():
                        shutil.copy2(str(cert_path), str(get_cert_path()))
            except Exception as e:
                log.error("Failed to restore original active customer: %s", e)

        # ── Summary ──
        summary_parts = [f"Planlagt audit-syklus fullfort: {len(audited)}/{total} OK"]
        if failed:
            summary_parts.append(f"Feilet: {', '.join(failed)}")
        summary_msg = ". ".join(summary_parts)
        log.info(summary_msg)
        if failed:
            await self._send_webhook(f"⚠️ {summary_msg}")

    async def _scan_also_renewals(self):
        """Scan a batch of ALSO-linked customers for renewal data.

        Scans up to 10 customers per cycle with 3s delay between calls.
        Skips customers already scanned in the last 24h.
        Over ~10 cycles, the full customer base gets cached.
        """
        from app.core.config import load_app_settings
        settings = load_app_settings()
        if not settings.get("also_password"):
            return  # ALSO not configured

        log.info("Scheduled ALSO renewal scan starting")
        try:
            from datetime import timedelta

            from app.core.customer import CustomerManager
            from app.core.database import get_db

            customers = CustomerManager.list_customers()
            linked = [c for c in customers if c.get("AlsoAccountId")]
            if not linked:
                return

            # Find recently scanned (last 24h)
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            recently = set()
            async with get_db() as db:
                async with db.execute(
                    "SELECT DISTINCT customer_id FROM also_renewals WHERE scanned_at > ?", (cutoff,)
                ) as cur:
                    recently = {row["customer_id"] for row in await cur.fetchall()}

            to_scan = [c for c in linked if c.get("_id", "") not in recently][:25]
            if not to_scan:
                log.info("ALSO renewal scan: all %d linked customers already cached", len(linked))
                return

            # Get ALSO client
            from app.integrations.also_cloud import AlsoCloudClient
            client = AlsoCloudClient(
                settings.get("also_username", ""),
                settings.get("also_password", ""),
                settings.get("also_country", "no"),
            )

            scanned = 0
            for c in to_scan:
                account_id = str(c["AlsoAccountId"])
                try:
                    subs = await client.get_subscriptions(account_id)
                    if subs:
                        from app.web.routes.also import _cache_renewals
                        await _cache_renewals(account_id, subs)
                    scanned += 1
                except Exception as e:
                    log.warning("Scheduled ALSO scan failed for %s: %s", c.get("CustomerName"), e)
                    if "403" in str(e) or "429" in str(e):
                        log.warning("Rate limit hit — stopping ALSO scan early")
                        break
                await asyncio.sleep(1.5)

            remaining = len([c for c in linked if c.get("_id", "") not in recently]) - len(to_scan)
            log.info("Scheduled ALSO renewal scan: %d scanned, %d remaining", scanned, max(0, remaining))

            self._log_activity("also_renewal_scan", f"Scanned {scanned} customers, {max(0, remaining)} remaining", "")

        except Exception as e:
            log.error("Scheduled ALSO renewal scan failed: %s", e)

    async def _auto_report_and_email(self, customer_name: str, config: dict, out_dir: Path, results) -> None:
        """Generate HTML report and send via email if auto-send is configured."""
        from app.core.config import load_app_settings
        settings = load_app_settings()

        try:
            from app.modules.base import SectionResult, SectionStatus
            from app.reports.generator import generate_reports
            results_objs = [
                SectionResult(name=r.name, status=r.status, warns=r.warns,
                              warn_levels=r.warn_levels, files=r.files, error=r.error)
                for r in results
            ]
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: generate_reports(
                    customer_name=customer_name,
                    org_domain=config.get("PrimaryDomain", ""),
                    out_dir=out_dir,
                    results=results_objs,
                    formats=["html"],
                    report_type="tech",
                    lang=settings.get("ui_language", "no"),
                ),
            )
            log.info("Scheduled report generated for %s", customer_name)
        except Exception as e:
            log.warning("Scheduled report generation failed for %s: %s", customer_name, e)
            return

        # Send email if auto-send is enabled
        if not settings.get("email_auto_send"):
            return

        try:
            from app.core.email_sender import auto_send_after_audit
            loop = asyncio.get_event_loop()
            err = await loop.run_in_executor(None, lambda: auto_send_after_audit(out_dir))
            if err:
                log.warning("Scheduled email failed for %s: %s", customer_name, err)
            else:
                recipient = settings.get("email_default_recipient", "")
                log.info("Scheduled report emailed for %s to %s", customer_name, recipient)
                self._log_activity("email_sent", f"Planlagt rapport sendt til {recipient}", customer_name)
        except Exception as e:
            log.warning("Scheduled email send failed for %s: %s", customer_name, e)

    @staticmethod
    def _log_activity(action: str, detail: str, customer: str) -> None:
        """Log to activity log if available, skip on error."""
        try:
            from app.core.activity_log import log_activity
            log_activity(action=action, detail=detail, customer=customer, user="scheduler")
        except Exception as e:
            log.debug("Activity log write failed: %s", e)

    async def _check_and_alert(self, ctx: dict, customer_name: str):
        """Compare current metrics with previous and send alerts."""
        config = get_scheduler_config()
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            return

        alert_config = config.get("alert_on", {})
        alerts: list[str] = []

        current = ctx.get("trends", {})

        # Risk score drop (value is threshold int or False to disable)
        risk_threshold = alert_config.get("risk_score_drop", 5)
        if risk_threshold and "risk_score" in current:
            delta = current["risk_score"].get("delta", 0)
            if delta < -risk_threshold:
                alerts.append(f"📉 Risikoscore falt med {abs(delta):.0f} poeng (nå {current['risk_score']['current']})")

        # Secure Score drop (value is threshold int or False to disable)
        ss_threshold = alert_config.get("secure_score_drop", 5)
        if ss_threshold and "secure_score_pct" in current:
            delta = current["secure_score_pct"].get("delta", 0)
            if delta < -ss_threshold:
                alerts.append(f"📉 Secure Score falt med {abs(delta):.1f}% (nå {current['secure_score_pct']['current']:.1f}%)")

        # New risky users
        if alert_config.get("new_risky_users") and "users_no_mfa" in current:
            if current["users_no_mfa"].get("delta", 0) > 0:
                alerts.append(f"🔓 {current['users_no_mfa']['delta']} nye bruker(e) uten MFA")

        # Expired credentials
        if alert_config.get("expired_credentials"):
            fc = ctx.get("file_contents", {})
            cred_warn = fc.get("17c_app_credential_expiry_WARN.txt", "")
            if cred_warn and "Expired" in cred_warn:
                alerts.append("🔑 App-credentials har utløpt — integrasjoner kan være brutt")

        # NSG warnings
        if alert_config.get("new_nsg_warnings"):
            fc = ctx.get("file_contents", {})
            nsg_warns = [k for k in fc if "nsg_risky" in k.lower() and "WARN" in k]
            if nsg_warns:
                alerts.append("🛡️ Nye risikable NSG-regler oppdaget i Azure")

        # MFA coverage below threshold (value is threshold % or False to disable)
        mfa_threshold = alert_config.get("mfa_below_threshold", 80)
        if mfa_threshold and "mfa_coverage_pct" in current:
            mfa_pct = current["mfa_coverage_pct"].get("current", 100)
            if mfa_pct < mfa_threshold:
                alerts.append(f"🔓 MFA-dekning er {mfa_pct:.0f}% (under terskel {mfa_threshold}%)")

        if alerts:
            message = f"🔍 **Automatisk audit — {customer_name}**\n\n" + "\n".join(alerts)
            await self._send_webhook(message)
        else:
            log.info("No alerts to send for %s", customer_name)

    async def _notify_audit_completed(self, customer_name: str, ctx: Optional[dict] = None):
        """Send audit-completed notification if enabled."""
        config = get_scheduler_config()
        alert_config = config.get("alert_on", {})
        if not alert_config.get("audit_completed", True):
            return

        if ctx:
            grade       = ctx.get("risk", {}).get("grade", "?")
            score       = ctx.get("risk", {}).get("score", 0)
            mfa_pct     = ctx.get("mfa", {}).get("pct", 0)
            ss_pct      = ctx.get("secure_score", {}).get("pct", 0)
            no_mfa      = ctx.get("mfa", {}).get("no_mfa", 0)
            ga_count    = (ctx.get("admin_roles") or {}).get("global_admin_count", 0)
            total_warns = len(ctx.get("all_warns", []))
            done_sec    = ctx.get("done_sections", 0)
            fail_sec    = ctx.get("failed_sections", 0)
            total_sec   = ctx.get("total_sections", 0)

            # Grade → color emoji
            grade_emoji = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "🔴"}.get(grade, "⚪")

            lines = [
                f"✅ Audit fullført — {customer_name}",
                f"{grade_emoji} Risikokarakter: **{grade}**  |  Score: **{score}/100**",
                f"🔒 MFA-dekning: **{mfa_pct:.0f}%**  |  Brukere uten MFA: **{no_mfa}**",
                f"🛡️ Secure Score: **{ss_pct:.0f}%**  |  Global Admin-kontoer: **{ga_count}**",
                f"📋 Seksjoner: **{done_sec}/{total_sec}** OK  |  Advarsler: **{total_warns}**",
            ]
            if fail_sec:
                lines.append(f"⚠️ {fail_sec} seksjon(er) feilet under audit")
            await self._send_webhook("\n".join(lines))
        else:
            await self._send_webhook(f"✅ Audit fullført for **{customer_name}**")

    async def _check_credential_expiry(self):
        """Check all customers' credential expiry and send webhook if anything is <30 days."""
        config = get_scheduler_config()
        if not config.get("webhook_url"):
            return
        if not config.get("alert_on", {}).get("expired_credentials", True):
            return

        from datetime import timezone as _tz

        from app.core.customer import CustomerManager

        customers = CustomerManager.list_customers()
        alerts: list[str] = []

        for c in customers:
            name = c.get("CustomerName", "Ukjent")
            for cred_label, key in [("Client secret", "SecretExpiry"), ("Sertifikat", "CertExpiry")]:
                iso_val = c.get(key, "")
                if not iso_val:
                    continue
                try:
                    dt = datetime.fromisoformat(iso_val.replace("Z", "+00:00"))
                    days = (dt - datetime.now(_tz.utc)).days
                except ValueError:
                    continue

                if days < 0:
                    alerts.append(f"[{name}] {cred_label} UTLOPT ({iso_val[:10]})")
                elif days < 7:
                    alerts.append(f"[{name}] {cred_label} utloper om {days} dager! (kritisk)")
                elif days < 30:
                    alerts.append(f"[{name}] {cred_label} utloper om {days} dager")

        if alerts:
            message = "**Credential-varsler:**\n\n" + "\n".join(alerts)
            await self._send_webhook(message)

    async def _maybe_create_backup(self):
        """Create a backup after scheduled audits if configured."""
        config = get_scheduler_config()
        if not config.get("backup_after_audit"):
            return
        try:
            loop = asyncio.get_event_loop()
            from app.web.routes.backup import create_backup_sync
            result = await loop.run_in_executor(None, create_backup_sync)
            log.info("Post-audit backup created: %s", result.get("path", "?"))
            self._log_activity("backup_created", f"Automatisk backup: {result.get('path', '')}", "")
        except Exception as e:
            log.error("Post-audit backup failed: %s", e)

    @staticmethod
    def _build_adaptive_card(message: str) -> dict:
        """Build an Adaptive Card body from a plain-text message.

        Lines starting with an emoji header (e.g. '📋 **Title**') become a
        bold heading; remaining lines become individual TextBlock rows.
        """
        lines = [l for l in message.split("\n") if l.strip()]
        body: list[dict] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if i == 0:
                # First line is always a prominent heading
                body.append({
                    "type": "TextBlock",
                    "text": stripped,
                    "wrap": True,
                    "weight": "Bolder",
                    "size": "Medium",
                })
            else:
                body.append({
                    "type": "TextBlock",
                    "text": stripped,
                    "wrap": True,
                    "spacing": "Small",
                })
        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": body,
        }

    async def _send_webhook(self, message: str):
        """Send message to Teams/Slack webhook using shared sender."""
        config = get_scheduler_config()
        url = config.get("webhook_url", "")
        if not url:
            return
        from app.services.webhook_sender import send_simple_message
        await send_simple_message(url, message)

# Singleton
scheduler = AuditScheduler()
