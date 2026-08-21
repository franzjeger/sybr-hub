"""The policy overview: one screen answers what a customer has, what moved,
and what to do next.

Composed from three independent sources, each with its own rules and shape:

* the customer's **inventory** — the last run's live policies consolidated
  onto the card, with a plain-language line per policy, produced by
  ``policy_inventory.build_inventory``.
* the **drift** — what moved between the last two runs, produced by
  ``policy_drift.compute_drift``. A first run, a predecessor without
  snapshots, and a run that captured nothing are *unmeasured*, not clean.
* the **standard gap** — each Sybr template, and which of its policies the
  tenant has by name. A policy that is in the standard but not in the live
  list is a gap; a policy that is in the live list and not in the standard
  is a customer-specific decision, and shows up only in the inventory.

The three are independent and read-only — this module calls no Graph and
writes nothing. It composes data already produced by ``policy_inventory``
and ``policy_drift``, plus the Sybr templates on disk. So the overview and
the customer card and the audit report cannot drift from each other: they
share the same building blocks.

Per-policy hints (``improvements``) use the state codes already emitted by
``policy_inventory`` (``on``, ``report-only``, ``off``) — the same enum the
card and the report colour by, so a hint and its state cannot disagree.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Loading the raw objects the inventory summarised ─────────────────────────

def _latest_run(customer_id: str) -> Path | None:
    """The most recent audit run directory for this customer, or None."""
    from app.core.config import get_audit_dir

    root = get_audit_dir() / customer_id
    if not root.is_dir():
        return None
    runs = sorted((p for p in root.iterdir() if p.is_dir()), key=str, reverse=True)
    return runs[0] if runs else None


def _live_ca_by_name(customer_id: str) -> dict[str, dict]:
    """Raw Conditional Access policy objects keyed by display name.

    The inventory on the card carries only name / state / summary — enough
    to display, not enough to evaluate (``lockout_risk`` reads conditions
    and grantControls). Re-reading the latest snapshot is one JSON read per
    overview request, and it keeps the summary in the card separate from
    the check the overview uses, so the two cannot silently diverge.
    """
    latest = _latest_run(customer_id)
    if latest is None:
        return {}
    path = latest / "policy_snapshots" / "conditional_access_policies.json"
    if not path.is_file():
        return {}
    try:
        from app.core.encryption import encrypted_read_json

        env = encrypted_read_json(path)
    except Exception:
        logger.warning("Could not read CA snapshot for %s", customer_id)
        return {}
    if not isinstance(env, dict):
        return {}
    return {
        str(p.get("displayName", "")): p
        for p in (env.get("items") or [])
        if isinstance(p, dict)
    }


def _drift(customer_id: str) -> dict[str, Any]:
    """Latest run's drift against its predecessor, or unmeasured with a reason."""
    from app.core.policy_drift import compute_drift, unmeasured

    latest = _latest_run(customer_id)
    if latest is None:
        return unmeasured("no_runs")
    try:
        return compute_drift(latest)
    except Exception as exc:
        logger.warning("Could not compute drift for %s: %s", customer_id, exc)
        return unmeasured("comparison_failed")


# ── The per-policy improvement hints ─────────────────────────────────────────

# The three codes the hints can carry. The text travels the same way as the
# summary in the inventory (bilingual dict) so the reader gets their own
# language from the interface rather than from the server.
_HINTS = {
    "add_break_glass": {
        "no": (
            "Legg til en break-glass-gruppe til unntakene før du håndhever — "
            "ellers låses administratorer ute av tenanten."
        ),
        "en": (
            "Add a break-glass exclusion group before enforcing — otherwise "
            "administrators lock themselves out of the tenant."
        ),
    },
    "enforce": {
        "no": "Rapporteringmodus — les påloggingsloggene og vurder å håndheve.",
        "en": "Report-only — read the sign-in log and consider enforcing.",
    },
    "enable": {
        "no": "Policyen er deaktivert — vurder å aktivere.",
        "en": "The policy is disabled — consider enabling it.",
    },
}


def _improvements_for(state_code: str, raw: dict) -> list[dict[str, Any]]:
    """Per-policy improvement hints, read-only.

    The state code is the derived value in the inventory (``on``,
    ``report-only``, ``off``) — the same enum the card and the report
    render. The raw body is the policy as Graph returned it, needed because
    ``lockout_risk`` reads conditions and grantControls, which the inventory
    deliberately does not keep.

    A policy that is enforced already has no improvement to suggest here:
    the next step (deleting, weakening, adding an exclusion) is a decision
    a human makes with context this overview cannot claim to hold.
    """
    if state_code == "report-only":
        from app.modules.m365_audit.policy_deploy import (
            ENABLED,
            lockout_risk,
            strip_server_fields,
        )

        enforced = {**strip_server_fields(raw), "state": ENABLED}
        refusal = lockout_risk(enforced)
        hints = []
        if refusal:
            hints.append({"code": "add_break_glass", "text": dict(_HINTS["add_break_glass"])})
        hints.append({"code": "enforce", "text": dict(_HINTS["enforce"])})
        return hints

    if state_code == "off":
        return [{"code": "enable", "text": dict(_HINTS["enable"])}]

    return []


# ── The standard gap ─────────────────────────────────────────────────────────

def _localised(value: Any, lang: str) -> str:
    if isinstance(value, dict):
        return str(value.get(lang) or value.get("no") or "")
    return str(value or "")


def _standard_gaps(lang: str, live_by_name: dict[str, dict]) -> list[dict[str, Any]]:
    """Each Sybr standard, and which of its policies the tenant has by name.

    Name-matched, not behaviour-matched: the standard's policies are ours and
    we chose their names, so an exact-name match is the right test. A tenant
    with a policy that does the same job under another name is a customer
    decision the standard does not override, and the adoption path in the
    deploy view is the way to record that.
    """
    from app.core.policy_templates import TemplateError, list_templates, load_template

    try:
        templates = list_templates(lang)
    except TemplateError as exc:
        logger.warning("Could not list templates: %s", exc)
        templates = []

    out = []
    for tpl in templates:
        try:
            doc = load_template(tpl["id"])
        except TemplateError:
            continue
        entries = []
        for policy in doc["policies"]:
            name = str(policy.get("displayName", ""))
            raw = live_by_name.get(name)
            if raw is None:
                state_code: str | None = None
                present = False
            else:
                # The card inventory maps state; use its enum.
                state_map = {
                    "enabled": "on",
                    "enabledForReportingButNotEnforced": "report-only",
                    "disabled": "off",
                }
                state_code = state_map.get(str(raw.get("state")), str(raw.get("state") or "?"))
                present = True
            entries.append({
                "name": name,
                "present": present,
                "state": state_code,
                "why": _localised(policy.get("why"), lang),
            })
        out.append({
            "id": tpl["id"],
            "name": tpl["name"],
            "version": tpl["version"],
            "policies": entries,
        })
    return out


# ── Composing ────────────────────────────────────────────────────────────────

def build_overview(customer_id: str, lang: str = "no") -> dict[str, Any]:
    """Compose the customer's full policy overview.

    Read-only: it calls ``policy_inventory.load_from_card``,
    ``policy_drift.compute_drift``, and the template loader, and returns
    what they say. An empty tenant (no audit, no card, no runs) is a valid
    answer, with ``inventory_present=False`` and ``unmeasured`` drift, not
    an empty dict — the interface should be able to tell "we have not
    captured this yet" from "we have captured it and it is empty".
    """
    from app.core.policy_inventory import load_from_card

    inventory = load_from_card(customer_id)
    drift = _drift(customer_id)
    live_by_name = _live_ca_by_name(customer_id)

    workloads = (inventory or {}).get("workloads") or {}
    ca = dict(workloads.get("conditional_access") or {})
    if ca:
        items = []
        for item in ca.get("items") or []:
            if not isinstance(item, dict):
                continue
            raw = live_by_name.get(str(item.get("name", ""))) or {}
            items.append({**item, "improvements": _improvements_for(str(item.get("state") or ""), raw)})
        ca["items"] = items
        workloads = {**workloads, "conditional_access": ca}

    return {
        "customer_id": customer_id,
        "captured_at": (inventory or {}).get("captured_at"),
        "run": (inventory or {}).get("run"),
        "inventory_present": inventory is not None,
        "workloads": workloads,
        "drift": drift,
        "standards": _standard_gaps(lang, live_by_name),
    }
