"""Automatic alert engine — checks critical events and sends Teams/email notifications.

Monitors SSL/domain expiry, FortiGate threats, firmware status, ALSO license
renewals, and MFA coverage.  Deduplicates alerts within 24 h using a simple
JSON file so the same alert is never sent twice in a row.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app.core.config import CONFIG_DIR, load_app_settings, save_app_settings
from app.core.database import get_db

logger = logging.getLogger(__name__)

# ── Alert history / dedup persistence ─────────────────────────────────────────

_ALERT_HISTORY_PATH = CONFIG_DIR / "alert_history.json"
_DEDUP_HOURS = 24


class AlertCheckFailed(Exception):
    """One check could not run.

    Each check used to log its failure and return an empty list, which the
    summary then added to nothing. "Fant 0 varsler" was the same sentence
    whether every certificate was healthy or the table holding them had gone
    missing — and the alerting page shows that number as all-clear.
    """

    def __init__(self, check: str):
        super().__init__(check)
        self.check = check


def _load_alert_history() -> list[dict]:
    """Load alert history from JSON file."""
    if _ALERT_HISTORY_PATH.exists():
        try:
            return json.loads(_ALERT_HISTORY_PATH.read_text("utf-8"))
        except Exception as e:
            logger.warning("Failed to load alert history: %s", e)
    return []


def _save_alert_history(history: list[dict]) -> None:
    """Persist alert history to JSON file."""
    _ALERT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ALERT_HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), "utf-8")


def _alert_fingerprint(alert: dict) -> str:
    """Create a stable hash for dedup — same type+item+customer = same alert."""
    raw = f"{alert.get('type', '')}|{alert.get('item', '')}|{alert.get('customer', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_duplicate(alert: dict, history: list[dict]) -> bool:
    """Return True if alert was already sent within the last _DEDUP_HOURS."""
    fp = _alert_fingerprint(alert)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=_DEDUP_HOURS)).isoformat()
    for h in history:
        if h.get("fingerprint") == fp and h.get("sent_at", "") > cutoff:
            return True
    return False


# ── Default alert configuration ──────────────────────────────────────────────

DEFAULT_ALERT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "notify_teams": True,
    "notify_email": False,
    "email_recipient": "",
    "rules": {
        "ssl_expiry": {"enabled": True, "days": 14},
        "domain_expiry": {"enabled": True, "days": 14},
        "fortigate_threats": {"enabled": True, "threshold": 50},
        "firmware_outdated": {"enabled": True},
        "also_license_expiry": {"enabled": True, "days": 14},
        "mfa_coverage": {"enabled": True, "threshold": 80},
        "pentest_critical": {"enabled": True},
        # A removed Conditional Access policy barely moves the Secure Score and
        # raises no alert from Microsoft. Drift has been computed at every
        # audit since the snapshots landed and nobody was told — the finding
        # sat in a report waiting for somebody to open it.
        "policy_drift": {"enabled": True, "alert_on_changed": False},
    },
}


def get_alert_config() -> dict:
    """Load alert config from app settings, merging with defaults."""
    settings = load_app_settings()
    saved = settings.get("alert_config", {})
    merged = {**DEFAULT_ALERT_CONFIG}
    merged.update({k: v for k, v in saved.items() if k != "rules"})
    # Deep-merge rules
    merged_rules = {**DEFAULT_ALERT_CONFIG["rules"]}
    for rk, rv in saved.get("rules", {}).items():
        if rk in merged_rules and isinstance(rv, dict):
            merged_rules[rk] = {**merged_rules[rk], **rv}
        else:
            merged_rules[rk] = rv
    merged["rules"] = merged_rules
    return merged


def save_alert_config(config: dict) -> None:
    """Persist alert config to app settings."""
    settings = load_app_settings()
    settings["alert_config"] = config
    save_app_settings(settings)


def get_customer_alert_overrides(customer_id: str) -> dict:
    """Get per-customer alert threshold overrides, or empty dict."""
    from app.core.customer import CustomerManager
    c = CustomerManager.get_customer(customer_id)
    return c.get("alert_overrides", {}) if c else {}


def get_effective_threshold(customer_id: str, rule: str, field: str, default):
    """Get effective threshold for a customer, checking per-customer overrides first."""
    overrides = get_customer_alert_overrides(customer_id)
    if rule in overrides and field in overrides[rule]:
        return overrides[rule][field]
    config = get_alert_config()
    rules = config.get("rules", {})
    return rules.get(rule, {}).get(field, default)


# ── Data source checks ───────────────────────────────────────────────────────


async def _check_ssl_expiry(days_threshold: int) -> list[dict]:
    """Check Uniweb SSL certificates expiring within threshold days."""
    alerts: list[dict] = []
    now = datetime.now(timezone.utc)
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT name, customer_id, data_json FROM uniweb_accounts"
            ) as cur:
                rows = await cur.fetchall()
        for row in rows:
            data = json.loads(row["data_json"]) if row["data_json"] else {}
            acct_name = row["name"]
            for cert in data.get("ssl", []):
                expiry_str = (cert.get("expiry") or "").strip()
                if not expiry_str or len(expiry_str) < 10:
                    continue
                try:
                    exp_date = datetime.fromisoformat(expiry_str[:10]).replace(tzinfo=timezone.utc)
                    remaining = (exp_date - now).days
                except (ValueError, TypeError):
                    continue
                if remaining <= days_threshold:
                    severity = "critical" if remaining < 7 else "warning"
                    if remaining < 0:
                        detail = f"SSL-sertifikat UTLØPT for {abs(remaining)} dager siden ({expiry_str[:10]})"
                        severity = "critical"
                    else:
                        detail = f"SSL-sertifikat utløper om {remaining} dager ({expiry_str[:10]})"
                    alerts.append({
                        "type": "ssl_expiry",
                        "severity": severity,
                        "customer": acct_name,
                        "item": cert.get("domain", ""),
                        "detail": detail,
                        "days_remaining": remaining,
                    })
    except Exception as exc:
        logger.warning("Alert check ssl_expiry failed: %s", exc)
        raise AlertCheckFailed("ssl_expiry") from exc
    return alerts


async def _check_domain_expiry(days_threshold: int) -> list[dict]:
    """Check Uniweb domains expiring within threshold days."""
    alerts: list[dict] = []
    now = datetime.now(timezone.utc)
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT name, customer_id, data_json FROM uniweb_accounts"
            ) as cur:
                rows = await cur.fetchall()
        for row in rows:
            data = json.loads(row["data_json"]) if row["data_json"] else {}
            acct_name = row["name"]
            for dom in data.get("domains", []):
                expiry_str = (dom.get("expiry") or "").strip()
                if not expiry_str or len(expiry_str) < 10:
                    continue
                try:
                    exp_date = datetime.fromisoformat(expiry_str[:10]).replace(tzinfo=timezone.utc)
                    remaining = (exp_date - now).days
                except (ValueError, TypeError):
                    continue
                if remaining <= days_threshold:
                    severity = "critical" if remaining < 7 else "warning"
                    if remaining < 0:
                        detail = f"Domene UTLØPT for {abs(remaining)} dager siden ({expiry_str[:10]})"
                        severity = "critical"
                    else:
                        detail = f"Domene utløper om {remaining} dager ({expiry_str[:10]})"
                    alerts.append({
                        "type": "domain_expiry",
                        "severity": severity,
                        "customer": acct_name,
                        "item": dom.get("domain", ""),
                        "detail": detail,
                        "days_remaining": remaining,
                    })
    except Exception as exc:
        logger.warning("Alert check domain_expiry failed: %s", exc)
        raise AlertCheckFailed("domain_expiry") from exc
    return alerts


async def _check_fortigate_threats(threshold: int) -> list[dict]:
    """Check for FortiGate threat spikes above threshold."""
    alerts: list[dict] = []
    try:
        from app.services.fortigate_api import poll_all_fortigates
        results = await poll_all_fortigates()
        for fg in results:
            cust_name = fg.get("customer_name", fg.get("customer_id", "?"))
            threat_count = fg.get("threat_count", 0)
            if threat_count and threat_count > threshold:
                alerts.append({
                    "type": "fortigate_threats",
                    "severity": "critical" if threat_count > threshold * 2 else "warning",
                    "customer": cust_name,
                    "item": fg.get("hostname", "FortiGate"),
                    "detail": f"{threat_count} trusler siste 24t (terskel: {threshold})",
                    "days_remaining": 0,
                })
    except Exception as exc:
        logger.warning("Alert check fortigate_threats failed: %s", exc)
        raise AlertCheckFailed("fortigate_threats") from exc
    return alerts


async def _check_firmware_outdated() -> list[dict]:
    """Check for outdated FortiGate firmware (< 7.4)."""
    alerts: list[dict] = []
    try:
        from app.services.fortigate_api import poll_all_fortigates
        results = await poll_all_fortigates()
        for fg in results:
            if fg.get("status") != "online":
                continue
            firmware = fg.get("firmware", "")
            if not firmware:
                continue
            try:
                parts = firmware.replace("v", "").split(".")
                major = int(parts[0])
                minor = int(parts[1]) if len(parts) > 1 else 0
                if major < 7 or (major == 7 and minor < 4):
                    cust_name = fg.get("customer_name", fg.get("customer_id", "?"))
                    alerts.append({
                        "type": "firmware_outdated",
                        "severity": "warning",
                        "customer": cust_name,
                        "item": fg.get("hostname", "FortiGate"),
                        "detail": f"Firmware {firmware} er utdatert (anbefalt >= 7.4)",
                        "days_remaining": 0,
                    })
            except (ValueError, IndexError):
                pass
    except Exception as exc:
        logger.warning("Alert check firmware_outdated failed: %s", exc)
        raise AlertCheckFailed("firmware_outdated") from exc
    return alerts


async def _check_also_license_expiry(days_threshold: int) -> list[dict]:
    """Check ALSO Cloud Marketplace renewals expiring within threshold days."""
    alerts: list[dict] = []
    now = datetime.now(timezone.utc)
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_name, service_display, contract_end "
                "FROM also_renewals WHERE contract_end IS NOT NULL AND handled = 0"
            ) as cur:
                rows = await cur.fetchall()
        for row in rows:
            end_str = (row["contract_end"] or "").strip()
            if not end_str or len(end_str) < 10:
                continue
            try:
                end_date = datetime.fromisoformat(end_str[:10]).replace(tzinfo=timezone.utc)
                remaining = (end_date - now).days
            except (ValueError, TypeError):
                continue
            if remaining <= days_threshold:
                severity = "critical" if remaining < 7 else "warning"
                if remaining < 0:
                    detail = f"Lisens UTLØPT for {abs(remaining)} dager siden ({end_str[:10]})"
                    severity = "critical"
                else:
                    detail = f"Lisens utløper om {remaining} dager ({end_str[:10]})"
                alerts.append({
                    "type": "also_license_expiry",
                    "severity": severity,
                    "customer": row["customer_name"],
                    "item": row["service_display"],
                    "detail": detail,
                    "days_remaining": remaining,
                })
    except Exception as exc:
        logger.warning("Alert check also_license_expiry failed: %s", exc)
        raise AlertCheckFailed("also_license_expiry") from exc
    return alerts



async def _check_policy_drift(alert_on_changed: bool = False) -> list[dict]:
    """Security policies that moved since the previous audit.

    The one this codebase most needed. A tenant can hold the same Secure Score
    for six months while somebody disables the policy requiring MFA for
    administrators: Microsoft raises nothing, the score barely notices, and the
    only record was a section of a report nobody had reason to open.

    Removals are critical and changes are optional, because they are different
    news. A policy that is gone is gone; a policy whose fields moved is usually
    somebody working, and alerting on every edit is how an alert channel
    becomes something people mute.

    Drift that could not be measured is silent. "No policy was removed" and
    "there was nothing to compare against" are different claims, and only the
    first is worth waking somebody for.
    """
    alerts: list[dict] = []
    unreadable: list[str] = []
    try:
        from app.core.config import get_audit_dir
        from app.core.customer import CustomerManager
        from app.core.policy_drift import compute_drift

        names = {}
        for c in CustomerManager.list_customers():
            real = c.get("CustomerName", "")
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in real)
            names[safe] = real or safe

        root = get_audit_dir()
        if not root.is_dir():
            return alerts

        for customer_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            runs = sorted((p for p in customer_dir.iterdir() if p.is_dir()), reverse=True)
            if not runs:
                continue
            try:
                drift = compute_drift(runs[0])
            except Exception as exc:
                # One unreadable tenant must not take the others with it. The
                # loop used to sit inside the check's single try, so the first
                # customer that failed ended the sweep and every tenant sorted
                # after it went unexamined — with the partial result returned
                # as if it were the whole answer.
                logger.warning(
                    "Policy drift unreadable for %s: %s", customer_dir.name, exc
                )
                unreadable.append(customer_dir.name)
                continue
            if not drift.get("measured"):
                # Nothing to compare against is not "nothing changed".
                continue

            customer = names.get(customer_dir.name, customer_dir.name)
            for snapshot in drift.get("snapshots", []):
                if not snapshot.get("comparable"):
                    continue
                for policy in snapshot.get("removed", []):
                    alerts.append({
                        "type": "policy_drift",
                        "severity": "critical",
                        "customer": customer,
                        "item": policy.get("name") or policy.get("id", ""),
                        "detail": (
                            f"Sikkerhetspolicyen «{policy.get('name') or policy.get('id')}» "
                            f"er fjernet siden {drift.get('compared_with')}."
                        ),
                        "days_remaining": 0,
                    })
                if not alert_on_changed:
                    continue
                for policy in snapshot.get("changed", []):
                    alerts.append({
                        "type": "policy_drift",
                        "severity": "warning",
                        "customer": customer,
                        "item": policy.get("name") or policy.get("id", ""),
                        "detail": (
                            f"«{policy.get('name') or policy.get('id')}» er endret siden "
                            f"{drift.get('compared_with')}: "
                            f"{', '.join(policy.get('fields', []))}."
                        ),
                        "days_remaining": 0,
                    })
    except Exception as exc:
        # Only the setup — the customer list and the audit directory. A single
        # tenant failing is handled in the loop, because the invariant that a
        # per-tenant failure must not lose the run predates this and is right.
        logger.warning("Alert check policy_drift failed: %s", exc)
        raise AlertCheckFailed("policy_drift") from exc
    if unreadable:
        logger.warning(
            "Policy drift skipped %d tenant(s): %s",
            len(unreadable), ", ".join(unreadable),
        )
    return alerts


async def _check_mfa_coverage(threshold: float) -> list[dict]:
    """Check audit metrics for MFA coverage below threshold."""
    alerts: list[dict] = []
    try:
        from app.core.customer import CustomerManager
        customer_map: dict[str, str] = {}
        for c in CustomerManager.list_customers():
            cid = c.get("_id", "")
            if cid:
                customer_map[cid] = c.get("CustomerName", "")

        # Get latest metrics per customer
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id, mfa_coverage_pct, audit_date "
                "FROM audit_metrics ORDER BY audit_date DESC"
            ) as cur:
                seen: set[str] = set()
                for row in await cur.fetchall():
                    cid = row["customer_id"]
                    if cid in seen:
                        continue
                    seen.add(cid)
                    mfa_pct = row["mfa_coverage_pct"]
                    if mfa_pct is not None and mfa_pct < threshold:
                        cust_name = customer_map.get(cid, cid)
                        alerts.append({
                            "type": "mfa_coverage",
                            "severity": "critical" if mfa_pct < 50 else "warning",
                            "customer": cust_name,
                            "item": "MFA-dekning",
                            "detail": f"MFA-dekning {mfa_pct:.0f}% (under terskel {threshold:.0f}%)",
                            "days_remaining": 0,
                        })
    except Exception as exc:
        logger.warning("Alert check mfa_coverage failed: %s", exc)
        raise AlertCheckFailed("mfa_coverage") from exc
    return alerts


async def _check_pentest_critical() -> list[dict]:
    """Check recent pentest scans for critical/high findings not yet alerted."""
    alerts: list[dict] = []
    try:
        async with get_db() as db:
            # Get scans from the last 24 h
            async with db.execute(
                "SELECT target, scan_type, findings_json, customer_id, scanned_at "
                "FROM pentest_scans WHERE scanned_at > datetime('now', '-1 day') "
                "ORDER BY scanned_at DESC LIMIT 50"
            ) as cur:
                rows = await cur.fetchall()
        for row in rows:
            findings = json.loads(row["findings_json"]) if row["findings_json"] else []
            critical = [f for f in findings if f.get("severity") in ("critical", "high")]
            if not critical:
                continue
            target = row["target"]
            cust = row["customer_id"] or target
            for f in critical[:5]:  # cap per scan
                sev = f.get("severity", "high")
                alerts.append({
                    "type": "pentest_critical",
                    "severity": "critical" if sev == "critical" else "warning",
                    "customer": cust,
                    "item": f.get("title", target),
                    "detail": f.get("detail", "")[:200],
                    "recommendation": f.get("remediation", ""),
                    "days_remaining": 0,
                })
    except Exception as exc:
        logger.debug("Alert check pentest_critical: %s", exc)
    return alerts


# ── Recommendation text enrichment ──────────────────────────────────────────

_RECOMMENDATIONS: dict[str, str] = {
    "policy_drift": (
        "Bekreft at fjerningen var tilsiktet. Var den ikke det, kan policyen "
        "settes tilbake fra siste gjenopprettingspunkt under Policy-utrulling."
    ),
    "ssl_expiry": "Forny sertifikatet med certbot/Let's Encrypt, eller kontakt CA-en din. Sett opp automatisk fornyelse.",
    "domain_expiry": "Forny domenet hos registraren. Aktiver auto-renew for å unngå at domenet utløper.",
    "fortigate_threats": "Gjennomgå IPS/AV-loggene på FortiGate. Vurder å blokkere kilde-IP og oppdater signaturer.",
    "firmware_outdated": "Oppgrader FortiGate firmware til >= 7.4. Planlegg oppgraderingsvindu og ta backup først.",
    "also_license_expiry": "Kontakt ALSO eller kunden for å fornye lisensen. Sjekk om tjenesten fortsatt er i bruk.",
    "mfa_coverage": "Aktiver MFA for brukere uten. Start med globale admins, deretter alle interaktive kontoer.",
    "pentest_critical": "Se remediation i pentest-rapporten. Fiks kritiske funn først, deretter høye.",
}


def _recommend(alert: dict) -> str:
    """Return a short recommendation based on alert type."""
    return _RECOMMENDATIONS.get(alert.get("type", ""), "")


# ── Notification senders ─────────────────────────────────────────────────────


async def send_teams_alert(webhook_url: str, alerts: list[dict]) -> None:
    """Send alert summary to Teams/Slack webhook using Adaptive Card."""
    if not webhook_url or not alerts:
        return

    # Build message text
    critical = [a for a in alerts if a["severity"] == "critical"]
    warnings = [a for a in alerts if a["severity"] == "warning"]

    lines = [f"🚨 **SYBR MSP Toolkit — {len(alerts)} varsel(er)**"]
    if critical:
        lines.append(f"**Kritiske ({len(critical)}):**")
        for a in critical[:10]:
            lines.append(f"🔴 [{a['customer']}] {a['item']}: {a['detail']}")
    if warnings:
        lines.append(f"**Advarsler ({len(warnings)}):**")
        for a in warnings[:10]:
            lines.append(f"🟡 [{a['customer']}] {a['item']}: {a['detail']}")
    if len(alerts) > 20:
        lines.append(f"_...og {len(alerts) - 20} flere_")

    message = "\n".join(lines)

    # Build Adaptive Card
    body_blocks: list[dict] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if i == 0:
            body_blocks.append({
                "type": "TextBlock",
                "text": stripped,
                "wrap": True,
                "weight": "Bolder",
                "size": "Medium",
            })
        else:
            body_blocks.append({
                "type": "TextBlock",
                "text": stripped,
                "wrap": True,
                "spacing": "Small",
            })

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body_blocks,
    }

    # Detect webhook type and format payload
    url_lower = webhook_url.lower()
    if "logic.azure.com" in url_lower or "powerautomate" in url_lower or "flow.microsoft.com" in url_lower:
        payload = card
    elif "office.com" in url_lower or "webhook.office" in url_lower:
        payload = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }],
        }
    else:
        payload = {"text": message}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code >= 400:
                logger.warning("Alert webhook failed: %d %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.error("Alert webhook error: %s", exc)


async def send_email_alert(smtp_config: dict, recipient: str, alerts: list[dict]) -> bool:
    """Send alert summary via SMTP email. True if it went out.

    Returned None before, and the caller counted a channel as notified on the
    strength of having called this — including when SMTP raised and the error
    was swallowed two lines below.
    """
    if not recipient or not alerts:
        return False

    import asyncio

    from app.core.email_sender import send_report_email

    critical = [a for a in alerts if a["severity"] == "critical"]
    warnings = [a for a in alerts if a["severity"] == "warning"]

    # Build HTML body
    rows_html = ""
    for a in alerts:
        color = "#f85149" if a["severity"] == "critical" else "#d29922"
        sev_label = "Kritisk" if a["severity"] == "critical" else "Advarsel"
        rows_html += f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #d0d7de;">
                <span style="color:{color};font-weight:600;">{sev_label}</span>
            </td>
            <td style="padding:8px;border-bottom:1px solid #d0d7de;">{a['customer']}</td>
            <td style="padding:8px;border-bottom:1px solid #d0d7de;">{a['item']}</td>
            <td style="padding:8px;border-bottom:1px solid #d0d7de;">{a['detail']}</td>
        </tr>"""

    body_html = f"""\
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:700px;margin:0 auto;color:#1a3148;">
  <h2 style="margin-bottom:4px;">SYBR MSP Toolkit — Automatiske varsler</h2>
  <p style="color:#57606a;margin-top:0;">{len(alerts)} varsel(er) oppdaget — {len(critical)} kritiske, {len(warnings)} advarsler</p>
  <table style="border-collapse:collapse;width:100%;margin:16px 0;font-size:13px;">
    <thead>
      <tr style="background:#f5f7fa;">
        <th style="text-align:left;padding:8px;border-bottom:2px solid #d0d7de;">Alvorlighet</th>
        <th style="text-align:left;padding:8px;border-bottom:2px solid #d0d7de;">Kunde</th>
        <th style="text-align:left;padding:8px;border-bottom:2px solid #d0d7de;">Element</th>
        <th style="text-align:left;padding:8px;border-bottom:2px solid #d0d7de;">Detaljer</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
  <hr style="border:none;border-top:1px solid #d0d7de;margin:20px 0;">
  <p style="color:#8b949e;font-size:11px;">Sendt automatisk fra SYBR MSP Toolkit</p>
</div>"""

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: send_report_email(
                to=recipient,
                subject=f"SYBR MSP Toolkit — {len(alerts)} varsel(er)",
                body_html=body_html,
                smtp_config=smtp_config,
            ),
        )
    except Exception as exc:
        logger.error("Alert email failed: %s", exc)
        return False
    return True


# ── Main alert check ─────────────────────────────────────────────────────────


async def run_alert_check() -> dict:
    """Run all alert checks, deduplicate, and send notifications.

    Returns a summary dict with alerts found, sent, and deduplicated counts.
    """
    config = get_alert_config()
    rules = config.get("rules", {})
    settings = load_app_settings()

    all_alerts: list[dict] = []
    failed_checks: list[str] = []

    async def _run(name: str, coro) -> None:
        """Run one check, and remember it if it could not run.

        A check that raised contributes nothing, exactly as before — the
        difference is that the caller is told which one, so "no alerts" and
        "the check that would have found them is broken" stop being the same
        answer.
        """
        try:
            all_alerts.extend(await coro)
        except AlertCheckFailed as exc:
            failed_checks.append(exc.check)
        except Exception as exc:  # a check that failed in some new way
            logger.warning("Alert check %s failed: %s", name, exc)
            failed_checks.append(name)

    # Run enabled checks
    if rules.get("ssl_expiry", {}).get("enabled"):
        days = rules["ssl_expiry"].get("days", 14)
        await _run("ssl_expiry", _check_ssl_expiry(days))

    if rules.get("domain_expiry", {}).get("enabled"):
        days = rules["domain_expiry"].get("days", 14)
        await _run("domain_expiry", _check_domain_expiry(days))

    if rules.get("fortigate_threats", {}).get("enabled"):
        threshold = rules["fortigate_threats"].get("threshold", 50)
        await _run("fortigate_threats", _check_fortigate_threats(threshold))

    if rules.get("firmware_outdated", {}).get("enabled"):
        await _run("firmware_outdated", _check_firmware_outdated())

    if rules.get("also_license_expiry", {}).get("enabled"):
        days = rules["also_license_expiry"].get("days", 14)
        await _run("also_license_expiry", _check_also_license_expiry(days))

    if rules.get("mfa_coverage", {}).get("enabled"):
        threshold = rules["mfa_coverage"].get("threshold", 80)
        await _run("mfa_coverage", _check_mfa_coverage(threshold))

    if rules.get("policy_drift", {}).get("enabled", True):
        await _run(
            "policy_drift",
            _check_policy_drift(rules["policy_drift"].get("alert_on_changed", False)),
        )

    # Pentest critical findings (from recent saved scans)
    if rules.get("pentest_critical", {}).get("enabled", True):
        await _run("pentest_critical", _check_pentest_critical())

    # Dedup against history
    history = _load_alert_history()
    new_alerts = [a for a in all_alerts if not _is_duplicate(a, history)]

    # Enrich alerts with recommendation text
    for a in new_alerts:
        if "recommendation" not in a:
            a["recommendation"] = _recommend(a)

    sent_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    if new_alerts:
        # Build summary facts for KPI strip
        critical_count = sum(1 for a in new_alerts if a["severity"] == "critical")
        warning_count = sum(1 for a in new_alerts if a["severity"] == "warning")
        facts = [
            ("Nye varsler", str(len(new_alerts))),
            ("Kritiske", str(critical_count)),
            ("Advarsler", str(warning_count)),
        ]

        dashboard_url = settings.get("dashboard_url", "")

        # Send Teams/Slack webhook via shared sender
        if config.get("notify_teams"):
            webhook_url = settings.get("scheduler", {}).get("webhook_url", "")
            if webhook_url:
                from app.services.webhook_sender import send_webhook
                ok = await send_webhook(
                    webhook_url,
                    title=f"🚨 SYBR MSP Toolkit — {len(new_alerts)} varsel(er)",
                    alerts=new_alerts,
                    subtitle=f"{critical_count} kritiske, {warning_count} advarsler",
                    facts=facts,
                    dashboard_url=dashboard_url,
                )
                if ok:
                    sent_count += 1

        # Send email
        if config.get("notify_email"):
            recipient = config.get("email_recipient", "") or settings.get("email_default_recipient", "")
            if recipient and await send_email_alert(settings, recipient, new_alerts):
                sent_count += 1

        # Record in history — but only what actually went out.
        #
        # The history is what _is_duplicate suppresses against for the next 24
        # hours, and it was written whether or not any channel had accepted the
        # alerts. So a webhook URL left blank, an SMTP server refusing, or
        # notifications simply switched off marked every new alert as sent and
        # the next run deduplicated it away. A critical certificate-expiry
        # alert whose only channel was broken was raised once, delivered
        # nowhere, and never mentioned again.
        if sent_count:
            for a in new_alerts:
                history.append({
                    "fingerprint": _alert_fingerprint(a),
                    "type": a["type"],
                    "severity": a["severity"],
                    "customer": a["customer"],
                    "item": a["item"],
                    "detail": a["detail"],
                    "sent_at": now_iso,
                })

            # Prune history older than 30 days
            cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            history = [h for h in history if h.get("sent_at", "") > cutoff_30d]
            _save_alert_history(history)
        else:
            logger.warning(
                "%d new alert(s) reached no channel — not recorded as sent, so "
                "the next run raises them again", len(new_alerts)
            )

    try:
        from app.core.activity_log import log_activity
        _failed = f", {len(failed_checks)} sjekk(er) feilet: {', '.join(failed_checks)}" if failed_checks else ""
        log_activity(
            "alert_check",
            detail=f"Fant {len(all_alerts)} varsler, {len(new_alerts)} nye, "
                   f"sendt via {sent_count} kanal(er){_failed}",
        )
    except Exception as e:
        logger.debug("Activity log write failed: %s", e)

    return {
        "total_found": len(all_alerts),
        "new_alerts": len(new_alerts),
        "deduplicated": len(all_alerts) - len(new_alerts),
        "channels_notified": sent_count,
        # Which checks did not run. Without this the caller cannot tell a
        # tenant with nothing wrong from one whose checks are broken.
        "failed_checks": failed_checks,
        "delivered": bool(sent_count) or not new_alerts,
        "alerts": [
            {
                "type": a["type"],
                "severity": a["severity"],
                "customer": a["customer"],
                "item": a["item"],
                "detail": a["detail"],
            }
            for a in all_alerts
        ],
    }


def get_alert_history(limit: int = 100) -> list[dict]:
    """Return recent alert history entries."""
    history = _load_alert_history()
    # Sort by sent_at descending
    history.sort(key=lambda h: h.get("sent_at", ""), reverse=True)
    return history[:limit]
