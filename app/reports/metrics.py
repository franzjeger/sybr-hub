"""Audit metrics: persistence, history, trends and policy drift."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

# ── Trend comparison ──────────────────────────────────────────────────────────


def _metric(source: dict | None, key: str):
    """Return a metric only when its source section actually produced data.

    These values are *persisted* — to _audit_metrics.json and to the
    audit_metrics table — and they feed the trend charts in the next report.
    A zero written for a section that failed is indistinguishable downstream
    from a measured zero, and _compute_trends only skips None. So a single
    throttled audit would draw MFA coverage collapsing to 0% and recovering,
    in the customer's history, permanently: a later correct audit adds a new
    row but cannot retract the old one.

    None means unknown, is stored as SQL NULL (every one of these columns is
    nullable), and is skipped by the trend comparison.
    """
    if not source or not source.get("has_data"):
        return None
    return source.get(key)


def save_audit_metrics(out_dir: Path, context: dict) -> None:
    """Save key audit metrics as JSON for future trend comparison."""
    mfa = context.get("mfa", {})
    network = context.get("network", {}) or {}
    unifi = (network.get("unifi") or {}) if network.get("has_data") else None
    fortigate = network.get("fortigate") if network.get("has_data") else None

    # A UniFi section that could not be read is not a measurement. It carries
    # device_count=None (rather than the old implicit 0), so treating it as a
    # real section would both sum None into an int below and read a refused
    # controller as "0 devices" in the trend. Drop it to None — the same as a
    # customer with no UniFi at all — so the metrics record "unknown", not zero.
    if unifi and (unifi.get("unavailable") or "error" in unifi):
        unifi = None

    metrics = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mfa_coverage_pct": _metric(mfa, "pct"),
        "secure_score_pct": _metric(context.get("secure_score", {}), "pct"),
        "total_users": _metric(context.get("users", {}), "total"),
        "users_no_mfa": _metric(mfa, "no_mfa"),
        "ca_policies_enabled": _metric(context.get("ca", {}), "enabled"),
        "intune_compliance_pct": _metric(context.get("intune", {}), "compliance_pct"),
        "intune_total_devices": _metric(context.get("intune", {}), "total"),
        "admin_roles_ga_count": _metric(context.get("admin_roles", {}), "global_admin_count"),
        "total_warns": len(context.get("all_warns", [])),
        # _compute_risk already returns None here when a blocking gap makes
        # the grade fiction — carry it through rather than flattening to 0.
        "risk_score": context.get("risk", {}).get("score"),
        "risk_grade": context.get("risk", {}).get("grade", ""),
        # Network metrics — None when the network audit produced nothing, so
        # a customer with no FortiGate/UniFi reachable does not register as
        # "0 devices, 0 default credentials" alongside tenants we did scan.
        "network_devices": None
        if unifi is None and fortigate is None
        else (
            (unifi or {}).get("device_count", 0)
            + (1 if fortigate and "error" not in fortigate else 0)
        ),
        "network_default_creds": (unifi or {}).get("default_creds_count") if unifi else None,
        "network_outdated_fw": (unifi or {}).get("outdated_firmware_count") if unifi else None,
        # The rendered text *and* the recipe for it. The text keeps every
        # existing reader working; the recipe lets a reader in the other
        # language have the sentence rebuilt without re-running the audit.
        "recommendations": [
            {
                "rec_id": r.get("rec_id", ""),
                "priority": r.get("priority", ""),
                "title": str(r.get("title", "")),
                "detail": str(r.get("detail", "")),
                "effort": str(r.get("effort", "")),
                "title_key": r.get("title_key", ""),
                "title_params": r.get("title_params", {}),
                "detail_key": r.get("detail_key", ""),
                "detail_params": r.get("detail_params", {}),
            }
            for r in context.get("recommendations", [])
        ],
    }
    from app.core.encryption import encrypted_write_json

    path = out_dir / "_audit_metrics.json"
    encrypted_write_json(path, metrics)

    # Also persist to DB for trend tracking
    try:
        _save_metrics_to_db(out_dir, metrics)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("Failed to save metrics to DB: %s", e)


def _save_metrics_to_db(out_dir: Path, metrics: dict) -> None:
    """Insert audit metrics into the database for historical trend queries."""
    import sqlite3

    from app.core.database import DB_PATH

    customer_name = out_dir.parent.name.replace("_", " ")
    # Derive customer_id from customer context if available
    customer_id = ""
    try:
        from app.core.credentials import load_config

        cfg = load_config() or {}
        customer_id = cfg.get("_id", cfg.get("TenantId", ""))
    except Exception:
        # Metrics are still written, just not attributed to a customer.
        log.debug("Could not resolve active customer for metrics", exc_info=True)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            """INSERT INTO audit_metrics
               (customer_id, customer_name, audit_date, risk_grade, risk_score,
                mfa_coverage_pct, secure_score_pct, total_users, users_no_mfa,
                ca_policies_enabled, intune_compliance_pct, admin_roles_ga_count,
                metrics_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                customer_id,
                customer_name,
                metrics.get("timestamp", ""),
                metrics.get("risk_grade", ""),
                # No `, 0` fallbacks: these columns are nullable and an
                # unknown must reach the row as NULL, not as a measured zero.
                metrics.get("risk_score"),
                metrics.get("mfa_coverage_pct"),
                metrics.get("secure_score_pct"),
                metrics.get("total_users"),
                metrics.get("users_no_mfa"),
                metrics.get("ca_policies_enabled"),
                metrics.get("intune_compliance_pct"),
                metrics.get("admin_roles_ga_count"),
                __import__("json").dumps(metrics),
                metrics.get("timestamp", ""),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_previous_metrics(out_dir: Path) -> dict | None:
    """Load metrics from the most recent previous audit run in the same customer folder."""
    customer_dir = out_dir.parent
    current_name = out_dir.name

    candidates: list[Path] = []
    for sibling in sorted(customer_dir.iterdir()):
        if (
            sibling.is_dir()
            and sibling.name < current_name
            and (sibling / "_audit_metrics.json").exists()
        ):
            candidates.append(sibling)

    if not candidates:
        return None

    prev_dir = candidates[-1]  # most recent before current (sorted ascending)
    try:
        from app.core.encryption import encrypted_read_json

        return encrypted_read_json(prev_dir / "_audit_metrics.json")
    except Exception as e:
        # Deliberately broad. The old (json.JSONDecodeError, OSError) missed
        # cryptography's InvalidTag, so a metrics file that could not be
        # decrypted — after a master-key rotation, a recreated keyring entry,
        # or plain corruption — took the whole report generation down with
        # it. The trend comparison is an enhancement; the report is the
        # deliverable, and losing the former must never cost the latter.
        logging.getLogger(__name__).warning(
            "Could not read previous metrics from %s: %s", prev_dir.name, e
        )
        return None


def load_metrics_history(out_dir: Path, max_runs: int = 5) -> list[dict]:
    """Load metrics from up to *max_runs* previous audit runs (oldest first).

    Each entry is a dict with at least the metric keys plus a ``_run_label``
    derived from the folder name (typically a date-based string).
    """
    customer_dir = out_dir.parent
    current_name = out_dir.name

    candidates: list[Path] = []
    for sibling in sorted(customer_dir.iterdir()):
        if (
            sibling.is_dir()
            and sibling.name < current_name
            and (sibling / "_audit_metrics.json").exists()
        ):
            candidates.append(sibling)

    # Take the last N (most recent) candidates, keep oldest-first order
    candidates = candidates[-max_runs:]

    history: list[dict] = []
    from app.core.encryption import encrypted_read_json

    for cdir in candidates:
        try:
            data = encrypted_read_json(cdir / "_audit_metrics.json")
            data["_run_label"] = cdir.name
            history.append(data)
        except Exception as e:
            # See load_previous_metrics — an undecryptable run must cost that
            # one point on the chart, not the whole report.
            logging.getLogger(__name__).warning(
                "Skipping unreadable metrics history for %s: %s", cdir.name, e
            )
            continue
    return history


def _compute_trends(current: dict, previous: dict | None) -> dict:
    """Compute deltas between current and previous audit metrics."""
    if not previous:
        return {}

    tracked_keys = [
        "mfa_coverage_pct",
        "secure_score_pct",
        "total_users",
        "users_no_mfa",
        "ca_policies_enabled",
        "intune_compliance_pct",
        "intune_total_devices",
        "admin_roles_ga_count",
        "total_warns",
        "risk_score",
    ]
    trends: dict = {}
    for key in tracked_keys:
        cur_val = current.get(key)
        prev_val = previous.get(key)
        if cur_val is None or prev_val is None:
            continue
        delta = round(cur_val - prev_val, 2)
        # For most metrics, higher is better; for warns/no_mfa/ga_count, lower is better
        lower_is_better = key in ("users_no_mfa", "admin_roles_ga_count", "total_warns")
        if delta == 0:
            continue
        improved = (delta < 0) if lower_is_better else (delta > 0)
        trends[key] = {
            "current": cur_val,
            "previous": prev_val,
            "delta": delta,
            "improved": improved,
        }
    return trends


def _drift_for(out_dir: Path) -> dict:
    """Policy drift for this run, or a stated reason there is none to show.

    Wrapped for the same reason load_previous_metrics is: drift is an
    enhancement to the report, and the report is the deliverable. A snapshot
    that will not decrypt must cost the comparison, never the document.

    The fallback is the module's own "not measured" shape rather than an empty
    diff — an empty diff reads as "nothing changed", which is a claim about
    the tenant made on the strength of an exception.
    """
    from app.core.policy_drift import compute_drift, unmeasured

    try:
        return compute_drift(out_dir)
    except Exception as e:
        log.warning("Drift comparison failed for %s: %s", out_dir.name, e)
        return unmeasured("comparison_failed")


def _baseline_for(context: dict) -> dict | None:
    """Judge the finished context against the house standard.

    Returns None when there is no baseline to judge by — a malformed or
    missing document is a fault in our configuration, and the report says
    nothing rather than inventing a verdict from it. The template omits the
    section entirely in that case.
    """
    from app.core.baseline import BaselineError, default_baseline_id, evaluate

    baseline_id = default_baseline_id()
    try:
        return evaluate(baseline_id, context)
    except BaselineError as e:
        log.warning("Baseline %s could not judge this run: %s", baseline_id, e)
        return None
    except Exception as e:
        log.warning("Baseline %s raised while judging this run: %s", baseline_id, e)
        return None
