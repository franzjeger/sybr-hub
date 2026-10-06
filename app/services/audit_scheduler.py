"""Automatic audit scheduler with webhook notifications."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import get_scheduler_config, load_app_settings, update_app_settings

log = logging.getLogger(__name__)


# How often the loop re-reads its config. A change in Settings (enable,
# disable, interval) takes effect within this, with no restart.
_TICK_SECONDS = 60


def _load_anchor() -> datetime | None:
    raw = load_app_settings().get("scheduler_state", {}).get("anchor")
    try:
        return datetime.fromisoformat(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _save_anchor(when: datetime | None) -> None:
    def mutate(settings: dict) -> None:
        state = settings.setdefault("scheduler_state", {})
        if when is None:
            state.pop("anchor", None)
        else:
            state["anchor"] = when.isoformat()

    update_app_settings(mutate)


def _is_configured_for_audit(customer: dict) -> bool:
    """Whether the customer record holds enough to build its audit login.

    An app registration needs its tenant and app id; delegated (GDAP) access
    needs only the tenant, as the audit route has it (``_prepare_audit``).
    A missing secret or certificate is not checked here: building the auth
    finds that and the run reports it as a failure, not a skip.
    """
    if not customer.get("TenantId"):
        return False
    return customer.get("AuthMode") == "gdap" or bool(customer.get("ClientId"))


def _webhook_text(value: str) -> str:
    """Plain text in Teams/Slack markdown; no links or formatting from customers."""
    text = str(value)
    for symbol in "[]<>*`_~|":
        text = text.replace(symbol, "")
    text = re.sub(r"(?i)\b(https?|ftp)://", r"\1: //", text)
    text = re.sub(r"(?i)\bwww\.", "www .", text)
    return text.replace("\n", " ").replace("\r", " ")


class AuditScheduler:
    """Runs audits on a schedule and sends webhook alerts on changes.

    The next run is measured from a persisted anchor, not from process start:
    measured from start, every deploy pushed a weekly audit out by another week.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None

    def start(self):
        """Start the loop. Idempotent; the loop itself honours ``enabled``."""
        if self.is_alive():
            return
        self._task = asyncio.create_task(self._loop())

    def is_alive(self) -> bool:
        return bool(self._task and not self._task.done())

    async def stop(self):
        """Cancel the loop and await it, so shutdown does not race the task."""
        task, self._task = self._task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # a teardown error must not block shutdown
                log.warning("Audit scheduler loop errored on stop: %s", exc)

    @staticmethod
    def _due(now: datetime) -> bool:
        config = get_scheduler_config()
        anchor = _load_anchor()
        if not config.get("enabled"):
            # Re-enabling later starts a fresh interval rather than firing at
            # once for every customer because an old anchor is long past.
            if anchor is not None:
                _save_anchor(None)
            return False
        if anchor is None:
            _save_anchor(now)
            return False
        return now >= anchor + timedelta(hours=config.get("interval_hours", 168))

    async def _loop(self):
        """Main scheduler loop."""
        while True:
            try:
                now = datetime.now(UTC)
                if self._due(now):
                    # Anchored before the run: a failing cycle waits a full
                    # interval like a successful one instead of retrying hot.
                    _save_anchor(now)
                    # Credential expiry and the ALSO renewal scan belong to the
                    # task scheduler (alert_check, also_price_refresh). The
                    # post-audit backup stays: it is the opt-in
                    # `backup_after_audit`, not the weekly app_backup task.
                    await self._collect_customer_sites()
                    await self._run_scheduled_audit()
                    await self._maybe_create_backup()
                await asyncio.sleep(_TICK_SECONDS)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Scheduler error: %s", e)
                await asyncio.sleep(_TICK_SECONDS)

    async def _run_scheduled_audit(self):
        """Audit every configured customer, or the one customer the settings name."""
        config = get_scheduler_config()
        if config.get("audit_all_customers", True):
            await self._run_all_customers_audit()
        else:
            await self._run_single_customer_audit(config.get("customer_id"))

    async def _run_single_customer_audit(self, customer_id: str | None):
        """Audit the one customer the scheduler settings name, by its id.

        This mode used to audit whatever the setup staging slot held
        (``load_config()``, audit_config.json): the customer somebody set up
        last, which nobody chose for the schedule, with credentials read from
        that slot and the staging certificate. It now does what the audit
        route does: read the customer's record and certificate path once,
        build the auth from them, and hand both to the collector.

        Settings saved before the id existed say "one customer" without
        saying which. That audits nothing and says so, every cycle, rather
        than fall back to the staging slot. The settings page says it too.
        """
        from app.core.customer import CustomerManager
        from app.modules.m365_audit.auth import get_auth_for_customer

        if not customer_id:
            log.warning(
                "Scheduled audit is set to one customer but names none, so nothing was "
                "audited. Choose the customer under Administrasjon > Varsler og planlagte "
                "oppgaver."
            )
            return
        customer = CustomerManager.get_customer(customer_id)
        if not customer:
            log.warning(
                "Scheduled audit: customer %s no longer exists, so nothing was audited",
                customer_id,
            )
            return
        name = customer.get("CustomerName", customer_id)
        if not _is_configured_for_audit(customer):
            log.warning(
                "Scheduled audit: %s has no Microsoft 365 setup, so nothing was audited", name
            )
            return
        try:
            auth = get_auth_for_customer(customer, CustomerManager.get_cert_path(customer_id))
        except Exception as e:
            log.error("Auth setup failed for customer %s: %s", name, e)
            await self._send_webhook(
                f"⚠️ Scheduled audit failed for {_webhook_text(name)}: {_webhook_text(e)}"
            )
            return
        await self._audit_customer(customer_id, customer, auth)

    async def _audit_customer(
        self, customer_id: str, customer: dict, auth, position: str = ""
    ) -> str:
        """Run one customer's audit with the auth built for it, and report on it.

        Waits for any manual audit. Returns "audited" or the
        failure text. ``position`` ("2/7") goes into the activity log.
        """
        # Imported here, not at module scope: core reaching into web state is
        # a layering compromise made deliberately. A lock of its own in core
        # would not serialise against the manual audit route, which is the
        # only thing this needs to serialise against.
        from app.core import job_state as state
        from app.modules.m365_audit.collector import AuditCollector, make_output_dir
        from app.reports.generator import build_report_context

        name = customer.get("CustomerName", customer_id or "Ukjent")
        suffix = f" ({position})" if position else ""

        # Claimed per customer rather than for a whole cycle. Holding it
        # across every tenant would lock a technician out of running an
        # audit by hand for as long as the cycle lasts, which is the kind
        # of guard people work around.
        while True:
            async with state.audit_lock:
                if not state.audit_running:
                    state.audit_running = True
                    break
            await asyncio.sleep(1)

        try:
            self._log_activity("audit_started", f"Planlagt audit startet{suffix}", name)

            out_dir = make_output_dir(name)
            collector = AuditCollector(auth=auth, out_dir=out_dir)
            results = await collector.run()

            ctx = build_report_context(
                customer_name=name,
                org_domain=customer.get("PrimaryDomain", ""),
                out_dir=out_dir,
                results=results,
                customer_id=customer_id,
            )

            await self._check_and_alert(ctx, name)
            await self._notify_audit_completed(name)

            # Auto-generate report + send email if configured
            await self._auto_report_and_email(name, customer, out_dir, results)

            self._log_activity("audit_completed", f"Planlagt audit fullfort{suffix}", name)
            log.info("Scheduled audit completed for %s", name)
            return "audited"

        except Exception as e:
            log.error("Scheduled audit failed for %s: %s", name, e)
            await self._send_webhook(
                f"⚠️ Scheduled audit failed for {_webhook_text(name)}: {_webhook_text(e)}"
            )
            return str(e)
        finally:
            state.audit_running = False

    async def _run_all_customers_audit(self):
        """Audit every configured customer in turn, touching no global state.

        This used to work by *switching* to each customer: write active.txt,
        copy that customer's config into the one global slot, copy their
        certificate over the one global certificate, audit whatever the
        globals then said, and restore the original at the end.

        Which meant that for the length of a cycle — minutes per tenant,
        potentially hours in total — "which customer is active" was a shared
        variable being rewritten under everyone else. Every route that reads
        the active customer reads those same globals: notes, tags, audit
        scope, the dashboard, the IT-Glue and FortiGate lookups. A technician
        with customer A open, saving a note during a cycle, wrote it into
        whichever customer the scheduler had reached. Silently, and for hours
        at a time. Worse and rarer: the audit reads the customer *name* and
        the customer *credentials* as two separate reads of that global, so a
        switch landing between them files tenant B's findings under customer
        A — the one failure this tool cannot afford, because every downstream
        claim it makes is "this is your tenant".

        The bulk-audit route has always done it correctly (see
        ``routes/audit.py``): build an AuthManager from the customer record
        directly and pass it in. Nothing downstream ever needed the globals —
        ``make_output_dir``, ``build_report_context`` and
        ``_auto_report_and_email`` all take the customer explicitly. The
        switching was doing nothing except creating the hazard.

        Two things fall out of using the customer record directly. Customers
        without a Microsoft 365 setup are skipped rather than attempted. And
        GDAP customers work: ``from_config`` had no GDAP branch, so every
        scheduled audit of a GDAP tenant failed, while the same customer
        audited manually was fine. (The filter that followed still asked for
        a ClientId, which a GDAP customer does not have, so they were skipped
        instead; ``_is_configured_for_audit`` asks what the audit route asks.)
        """
        from app.core.customer import CustomerManager
        from app.modules.m365_audit.auth import get_auth_for_customer

        all_customers = CustomerManager.list_customers()
        if not all_customers:
            log.warning("Scheduled audit: no customers registered, skipping")
            return

        customers = [c for c in all_customers if _is_configured_for_audit(c)]
        unconfigured = len(all_customers) - len(customers)
        if unconfigured:
            log.info("Scheduled audit: skipping %d unconfigured customer(s)", unconfigured)
        if not customers:
            log.warning("Scheduled audit: no customer is configured for auditing, skipping")
            return

        total = len(customers)
        log.info("Scheduled audit cycle starting for %d customer(s)", total)
        audited: list[str] = []
        failed: list[str] = []
        skipped: list[str] = []

        for idx, cust in enumerate(customers):
            cust_id = cust.get("_id", "")
            cust_name = cust.get("CustomerName", cust_id or "Ukjent")

            log.info("Scheduled audit [%d/%d]: %s", idx + 1, total, cust_name)

            try:
                full_cust = CustomerManager.get_customer(cust_id)
                if not full_cust:
                    log.warning("Customer %s not found, skipping", cust_name)
                    failed.append(f"{cust_name} (ikke funnet)")
                    continue
                auth = get_auth_for_customer(full_cust, CustomerManager.get_cert_path(cust_id))
            except Exception as e:
                log.error("Auth setup failed for customer %s: %s", cust_name, e)
                failed.append(f"{cust_name} (autentisering feilet: {e})")
                continue

            outcome = await self._audit_customer(cust_id, full_cust, auth, f"{idx + 1}/{total}")
            if outcome == "audited":
                audited.append(cust_name)
            elif outcome == "skipped":
                skipped.append(f"{cust_name} (audit pagikk)")
            else:
                failed.append(f"{cust_name} ({outcome})")

        # ── Summary ──
        summary_parts = [f"Planlagt audit-syklus fullfort: {len(audited)}/{total} OK"]
        if skipped:
            summary_parts.append(f"Hoppet over: {', '.join(_webhook_text(v) for v in skipped)}")
        if failed:
            summary_parts.append(f"Feilet: {', '.join(_webhook_text(v) for v in failed)}")
        summary_msg = ". ".join(summary_parts)
        log.info(summary_msg)
        if failed or skipped:
            await self._send_webhook(f"⚠️ {summary_msg}")

    async def _collect_customer_sites(self):
        """Visit each customer site over VPN and read what is there.

        Runs as the system account, one site at a time, and leaves no tunnel
        open — see services/site_collector.py for why each of those matters.
        Failures are per-site and reported in the summary rather than raised:
        one customer's VPN being down is not a reason to skip the rest.
        """
        from app.services.site_collector import collect_all

        try:
            summary = await collect_all()
        except Exception as exc:
            log.error("Site collection failed outright: %s", exc)
            await self._send_webhook(f"⚠️ Site collection failed: {_webhook_text(exc)}")
            return

        if summary["failed"]:
            unreachable = [
                r["profile_name"] for r in summary["results"] if r["outcome"] == "failed"
            ]
            await self._send_webhook(
                f"⚠️ Site collection: {summary['collected']}/{summary['sites']} read. "
                f"No data from: {', '.join(_webhook_text(v) for v in unreachable)}"
            )
        self._log_activity(
            "site_collection",
            f"{summary['collected']} av {summary['sites']} lokasjoner lest",
            "",
        )

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

            from sqlmodel import select

            from app.core.customer import CustomerManager
            from app.core.orm import get_session
            from app.models.integrations import AlsoRenewal

            customers = CustomerManager.list_customers()
            linked = [c for c in customers if c.get("AlsoAccountId")]
            if not linked:
                return

            # Find recently scanned (last 24h)
            cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
            recently = set()
            async with get_session() as session:
                result = await session.execute(
                    select(AlsoRenewal.customer_id)
                    .where(AlsoRenewal.scanned_at > cutoff)
                    .distinct()
                )
                recently = {row for row in result.scalars().all()}

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
                        from app.services.also_renewals import cache_renewals

                        await cache_renewals(account_id, subs)
                    scanned += 1
                except Exception as e:
                    log.warning("Scheduled ALSO scan failed for %s: %s", c.get("CustomerName"), e)
                    if "403" in str(e) or "429" in str(e):
                        log.warning("Rate limit hit — stopping ALSO scan early")
                        break
                await asyncio.sleep(1.5)

            remaining = len([c for c in linked if c.get("_id", "") not in recently]) - len(to_scan)
            log.info(
                "Scheduled ALSO renewal scan: %d scanned, %d remaining", scanned, max(0, remaining)
            )

            self._log_activity(
                "also_renewal_scan",
                f"Scanned {scanned} customers, {max(0, remaining)} remaining",
                "",
            )

        except Exception as e:
            log.error("Scheduled ALSO renewal scan failed: %s", e)

    async def _auto_report_and_email(
        self, customer_name: str, config: dict, out_dir: Path, results
    ) -> None:
        """Generate HTML report and send via email if auto-send is configured."""
        from app.core.config import load_app_settings

        settings = load_app_settings()

        try:
            from app.modules.base import SectionResult
            from app.reports.generator import generate_reports

            results_objs = [
                SectionResult(
                    name=r.name,
                    status=r.status,
                    warns=r.warns,
                    warn_levels=r.warn_levels,
                    files=r.files,
                    error=r.error,
                )
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
                    customer_id=config.get("_id") or None,
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
                self._log_activity(
                    "email_sent", f"Planlagt rapport sendt til {recipient}", customer_name
                )
        except Exception as e:
            log.warning("Scheduled email send failed for %s: %s", customer_name, e)

    @staticmethod
    def _log_activity(action: str, detail: str, customer: str) -> None:
        """Log to activity log if available, skip on error.

        Attributed to the system account, not the bare string "scheduler": the
        actor is a real is_system row the log reader can resolve, and it reads
        the same for every unattended subsystem so "what did the hub do on its
        own" is one query, not three spellings.
        """
        try:
            from app.core.activity_log import log_activity
            from app.core.system_user import USERNAME

            log_activity(action=action, detail=detail, customer=customer, user=USERNAME)
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
                alerts.append(
                    f"📉 Risikoscore falt med {abs(delta):.0f} poeng (nå {current['risk_score']['current']})"
                )

        # Secure Score drop (value is threshold int or False to disable)
        ss_threshold = alert_config.get("secure_score_drop", 5)
        if ss_threshold and "secure_score_pct" in current:
            delta = current["secure_score_pct"].get("delta", 0)
            if delta < -ss_threshold:
                alerts.append(
                    f"📉 Secure Score falt med {abs(delta):.1f}% (nå {current['secure_score_pct']['current']:.1f}%)"
                )

        # New risky users
        if (
            alert_config.get("new_risky_users")
            and "users_no_mfa" in current
            and current["users_no_mfa"].get("delta", 0) > 0
        ):
            alerts.append(f"🔓 {current['users_no_mfa']['delta']} nye bruker(e) uten MFA")

        # Expired credentials
        if alert_config.get("expired_credentials"):
            fc = ctx.get("file_contents", {})
            cred_warn = fc.get("17c_app_credential_expiry_WARN.txt", "")
            from app.core.audit_results import credential_expiry_counts
            from app.reports.parsers.collaboration import _app_credential_counts

            # The 17c sidecar's counts first, where the run has them.
            counts = _app_credential_counts(fc) or credential_expiry_counts(cred_warn)
            if counts and counts[0] > 0:
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
            message = f"🔍 **Automatisk audit — {_webhook_text(customer_name)}**\n\n" + "\n".join(
                alerts
            )
            await self._send_webhook(message)
        else:
            log.info("No alerts to send for %s", customer_name)

    async def _notify_audit_completed(self, customer_name: str, ctx: dict | None = None):
        """Send audit-completed notification if enabled."""
        config = get_scheduler_config()
        alert_config = config.get("alert_on", {})
        if not alert_config.get("audit_completed", True):
            return

        if ctx:
            grade = ctx.get("risk", {}).get("grade", "?")
            score = ctx.get("risk", {}).get("score")
            score_text = "ikke målt" if score is None else f"{score}/100"
            from app.reports.metrics import _metric

            def measured(source, key, percent=False):
                value = _metric(ctx.get(source), key)
                if value is None:
                    return "ikke målt"
                return f"{value:.0f}%" if percent else str(value)

            mfa_pct = measured("mfa", "pct", True)
            ss_pct = measured("secure_score", "pct", True)
            no_mfa = measured("mfa", "no_mfa")
            ga_count = measured("admin_roles", "global_admin_count")
            total_warns = len(ctx.get("all_warns", []))
            done_sec = ctx.get("done_sections", 0)
            fail_sec = ctx.get("failed_sections", 0)
            total_sec = ctx.get("total_sections", 0)

            # Grade → color emoji
            grade_emoji = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "🔴"}.get(grade, "⚪")

            lines = [
                f"✅ Audit fullført — {_webhook_text(customer_name)}",
                f"{grade_emoji} Risikokarakter: **{grade}**  |  Score: **{score_text}**",
                f"🔒 MFA-dekning: **{mfa_pct}**  |  Brukere uten MFA: **{no_mfa}**",
                f"🛡️ Secure Score: **{ss_pct}**  |  Global Admin-kontoer: **{ga_count}**",
                f"📋 Seksjoner: **{done_sec}/{total_sec}** OK  |  Advarsler: **{total_warns}**",
            ]
            if fail_sec:
                lines.append(f"⚠️ {fail_sec} seksjon(er) feilet under audit")
            await self._send_webhook("\n".join(lines))
        else:
            await self._send_webhook(f"✅ Audit fullført for **{_webhook_text(customer_name)}**")

    async def _check_credential_expiry(self):
        """Check all customers' credential expiry and send webhook if anything is <30 days."""
        config = get_scheduler_config()
        if not config.get("webhook_url"):
            return
        if not config.get("alert_on", {}).get("expired_credentials", True):
            return

        from datetime import UTC

        from app.core.customer import CustomerManager

        customers = CustomerManager.list_customers()
        alerts: list[str] = []

        for c in customers:
            name = _webhook_text(c.get("CustomerName", "Ukjent"))
            for cred_label, key in [
                ("Client secret", "SecretExpiry"),
                ("Sertifikat", "CertExpiry"),
            ]:
                iso_val = c.get(key, "")
                if not iso_val:
                    continue
                try:
                    dt = datetime.fromisoformat(iso_val.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                    days = (dt - datetime.now(UTC)).days
                except (ValueError, TypeError):
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
            from app.services.backups import create_backup_sync

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
        lines = [line for line in message.split("\n") if line.strip()]
        body: list[dict] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if i == 0:
                # First line is always a prominent heading
                body.append(
                    {
                        "type": "TextBlock",
                        "text": stripped,
                        "wrap": True,
                        "weight": "Bolder",
                        "size": "Medium",
                    }
                )
            else:
                body.append(
                    {
                        "type": "TextBlock",
                        "text": stripped,
                        "wrap": True,
                        "spacing": "Small",
                    }
                )
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
