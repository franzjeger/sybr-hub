"""The policies a customer has in production, kept on the customer card.

An audit already captures the tenant's live policy objects as snapshots under
the run directory (``<run>/policy_snapshots/*.json``). Those are per-run and
buried in the audit tree, so answering "what is actually configured for this
customer right now" meant opening a run and reading raw Graph JSON.

This lifts the most recent captured set onto the customer card
(``DATA_DIR/customers/<id>/policies_live.json``) and gives every policy a
plain-language line — in both languages — saying what it does. The customer
detail view and the audit report read it back, so a technician always sees the
policies in production without hunting through runs.

Read-only by construction: it consolidates what the audit already fetched. It
does not call Graph and changes nothing in the tenant.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CARD_FILE = "policies_live.json"

# The snapshots the audit writes today, in the order a reader expects them, with
# a bilingual workload label. Adding a workload later (SharePoint sharing,
# cross-tenant, Teams) is one more entry here plus a describe function.
_WORKLOADS: list[dict[str, Any]] = [
    {
        "key": "conditional_access",
        "snapshot": "conditional_access_policies",
        "label": {"no": "Conditional Access", "en": "Conditional Access"},
    },
    {
        "key": "named_locations",
        "snapshot": "named_locations",
        "label": {"no": "Navngitte lokasjoner", "en": "Named locations"},
    },
    {
        "key": "intune_compliance",
        "snapshot": "intune_compliance_policies",
        "label": {"no": "Intune - samsvarspolicyer", "en": "Intune compliance policies"},
    },
    {
        "key": "intune_config",
        "snapshot": "intune_configuration_profiles",
        "label": {"no": "Intune - konfigurasjonsprofiler", "en": "Intune configuration profiles"},
    },
]

# Conditional Access lifecycle state → a stable code the UI colours by.
_CA_STATE = {
    "enabled": "on",
    "enabledForReportingButNotEnforced": "report-only",
    "disabled": "off",
}

# builtInControls → what the policy makes the user do, in plain language.
_CONTROL = {
    "mfa": {"no": "krev MFA", "en": "require MFA"},
    "block": {"no": "blokker tilgang", "en": "block access"},
    "compliantDevice": {"no": "krev samsvarende enhet", "en": "require compliant device"},
    "domainJoinedDevice": {"no": "krev Entra-hybrid enhet", "en": "require Entra-hybrid device"},
    "approvedApplication": {"no": "krev godkjent app", "en": "require approved app"},
    "compliantApplication": {"no": "krev app-beskyttelse", "en": "require app protection"},
    "passwordChange": {"no": "krev passordbytte", "en": "require password change"},
}


def _snapshot_dir(out_dir: Path) -> Path:
    return out_dir / "policy_snapshots"


def _read_snapshot(out_dir: Path, name: str) -> dict | None:
    """Read one encrypted snapshot envelope, or None if it isn't there."""
    from app.core.encryption import encrypted_read_json

    path = _snapshot_dir(out_dir) / f"{name}.json"
    if not path.is_file():
        return None
    try:
        env = encrypted_read_json(path)
    except Exception as exc:
        logger.warning("Could not read policy snapshot %s: %s", path, exc)
        return None
    if not isinstance(env, dict) or "items" not in env:
        return None
    return env


def _ca_targets(policy: dict) -> dict[str, str]:
    """Who a Conditional Access policy applies to, in plain language."""
    users = (policy.get("conditions") or {}).get("users") or {}
    inc_users = users.get("includeUsers") or []
    inc_roles = users.get("includeRoles") or []
    inc_groups = users.get("includeGroups") or []
    inc_guests = users.get("includeGuestsOrExternalUsers")
    if "All" in inc_users:
        return {"no": "alle brukere", "en": "all users"}
    parts_no: list[str] = []
    parts_en: list[str] = []
    if inc_roles:
        parts_no.append(f"{len(inc_roles)} administratorroller")
        parts_en.append(f"{len(inc_roles)} admin roles")
    if inc_guests:
        parts_no.append("gjester/eksterne")
        parts_en.append("guests/external")
    if inc_groups:
        parts_no.append(f"{len(inc_groups)} grupper")
        parts_en.append(f"{len(inc_groups)} groups")
    if inc_users:
        parts_no.append(f"{len(inc_users)} brukere")
        parts_en.append(f"{len(inc_users)} users")
    if not parts_no:
        return {"no": "utvalgte mål", "en": "selected targets"}
    return {"no": ", ".join(parts_no), "en": ", ".join(parts_en)}


def _ca_controls(policy: dict) -> dict[str, str]:
    controls = (policy.get("grantControls") or {}).get("builtInControls") or []
    if not controls:
        # A session-control-only policy (sign-in frequency, persistent browser).
        if policy.get("sessionControls"):
            return {"no": "sesjonskontroller", "en": "session controls"}
        return {"no": "ingen grant-kontroll", "en": "no grant control"}
    no = ", ".join(_CONTROL.get(c, {}).get("no", c) for c in controls)
    en = ", ".join(_CONTROL.get(c, {}).get("en", c) for c in controls)
    return {"no": no, "en": en}


def _cap(text: str) -> str:
    """Capitalise the first letter only — str.capitalize() lowercases MFA."""
    return text[:1].upper() + text[1:]


def _describe_ca(policy: dict) -> dict[str, str]:
    """One bilingual sentence: what this CA policy does and to whom."""
    client_types = (policy.get("conditions") or {}).get("clientAppTypes") or []
    legacy_only = set(client_types) <= {"exchangeActiveSync", "other"} and client_types
    targets = _ca_targets(policy)
    controls = _ca_controls(policy)
    scope_no = "eldre autentisering for " if legacy_only else ""
    scope_en = "legacy authentication for " if legacy_only else ""
    return {
        "no": f"{_cap(controls['no'])} — {scope_no}{targets['no']}",
        "en": f"{_cap(controls['en'])} — {scope_en}{targets['en']}",
    }


def _ca_items(env: dict) -> list[dict]:
    items = []
    for p in env.get("items") or []:
        if not isinstance(p, dict):
            continue
        items.append({
            "name": p.get("displayName") or "(uten navn)",
            "state": _CA_STATE.get(str(p.get("state")), str(p.get("state") or "?")),
            "summary": _describe_ca(p),
        })
    return items


def _named_location_items(env: dict) -> list[dict]:
    items = []
    for loc in env.get("items") or []:
        if not isinstance(loc, dict):
            continue
        trusted = bool(loc.get("isTrusted"))
        ip_ranges = loc.get("ipRanges") or []
        countries = (loc.get("countriesAndRegions") or [])
        if countries:
            detail_no = f"{len(countries)} land/regioner"
            detail_en = f"{len(countries)} countries/regions"
        else:
            detail_no = f"{len(ip_ranges)} IP-områder"
            detail_en = f"{len(ip_ranges)} IP ranges"
        items.append({
            "name": loc.get("displayName") or "(uten navn)",
            "state": "trusted" if trusted else "on",
            "summary": {
                "no": ("Betrodd lokasjon — " if trusted else "Lokasjon — ") + detail_no,
                "en": ("Trusted location — " if trusted else "Location — ") + detail_en,
            },
        })
    return items


def _intune_items(env: dict) -> list[dict]:
    items = []
    for pol in env.get("items") or []:
        if not isinstance(pol, dict):
            continue
        # Graph returns the platform via @odata.type, e.g.
        # "#microsoft.graph.windows10CompliancePolicy".
        odata = str(pol.get("@odata.type") or "")
        platform = odata.rsplit(".", 1)[-1].replace("CompliancePolicy", "").replace(
            "GeneralConfiguration", "").replace("Configuration", "") or "policy"
        items.append({
            "name": pol.get("displayName") or "(uten navn)",
            "state": "on",
            "summary": {
                "no": f"Plattform: {platform}",
                "en": f"Platform: {platform}",
            },
        })
    return items


_DESCRIBERS = {
    "conditional_access": _ca_items,
    "named_locations": _named_location_items,
    "intune_compliance": _intune_items,
    "intune_config": _intune_items,
}


def build_inventory(out_dir: Path) -> dict | None:
    """Consolidate a finished run's policy snapshots into a card record.

    Returns None when the run captured no policy snapshots at all (an audit
    that skipped the identity/Intune sections), so the caller does not
    overwrite a good card record with an empty one.
    """
    out_dir = Path(out_dir)
    workloads: dict[str, Any] = {}
    captured_at = None
    total = 0
    for wl in _WORKLOADS:
        env = _read_snapshot(out_dir, wl["snapshot"])
        if env is None:
            continue
        captured_at = captured_at or env.get("captured_at")
        describe = _DESCRIBERS[wl["key"]]
        items = describe(env)
        workloads[wl["key"]] = {
            "label": wl["label"],
            "source": env.get("source", ""),
            "count": len(items),
            "items": items,
        }
        total += len(items)

    if not workloads:
        return None

    return {
        "captured_at": captured_at or datetime.now(UTC).isoformat(),
        "run": out_dir.name,
        "total": total,
        "workloads": workloads,
    }


def save_to_card(customer_id: str, inventory: dict) -> None:
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_write_json

    card_dir = CustomerManager.get_customer_dir(customer_id)
    card_dir.mkdir(parents=True, exist_ok=True)
    encrypted_write_json(card_dir / CARD_FILE, inventory)


def load_from_card(customer_id: str) -> dict | None:
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_read_json

    path = CustomerManager.get_customer_dir(customer_id) / CARD_FILE
    if not path.is_file():
        return None
    try:
        return encrypted_read_json(path)
    except Exception as exc:
        logger.warning("Could not read policies_live.json for %s: %s", customer_id, exc)
        return None


def persist_from_run(out_dir: Path) -> bool:
    """Audit-completion hook: lift this run's policies onto the customer card.

    The customer id is the parent directory of the run — the audit tree and the
    customer card use the same name transform (``customer_dir_name``), so
    ``<audit>/<customer_id>/<run>`` gives the card key directly. Best-effort: a
    failure here must never fail the audit. Returns whether a record was written.
    """
    try:
        out_dir = Path(out_dir)
        customer_id = out_dir.parent.name
        if not customer_id:
            return False
        inventory = build_inventory(out_dir)
        if inventory is None:
            return False
        save_to_card(customer_id, inventory)
        logger.info(
            "Policies-in-production updated for %s: %d across %d workload(s)",
            customer_id, inventory["total"], len(inventory["workloads"]),
        )
        return True
    except Exception as exc:
        logger.warning("Could not persist policy inventory from %s: %s", out_dir, exc)
        return False
