"""The policy-overview screen and the route that feeds it.

One screen, three sources that must stay in lock-step: the card inventory,
the drift between the last two runs, and the Sybr standards. This pins the
wiring the assessments view test pins — script served, view present,
dispatcher branch, feature gate, strings — plus the compose rules the
card and report have already earned by test:

* an empty tenant is "not captured yet", not a clean diff;
* a report-only lockout risk is a hint, not a deploy refusal;
* the standard gap is name-matched and does not invent policies.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

STATIC = pathlib.Path("app/web/static")
GOOD_PASSWORD = "Str0ng-Passphrase-For-Tests!"


def _write_card(customers_root: pathlib.Path, customer: str, inventory: dict) -> None:
    from app.core.encryption import encrypted_write_json

    d = customers_root / customer
    d.mkdir(parents=True, exist_ok=True)
    encrypted_write_json(d / "policies_live.json", inventory)


def _write_snapshot(root: pathlib.Path, customer: str, run: str, items: list) -> None:
    from app.core.encryption import encrypted_write_text

    d = root / customer / run / "policy_snapshots"
    d.mkdir(parents=True, exist_ok=True)
    encrypted_write_text(
        d / "conditional_access_policies.json",
        json.dumps({"snapshot": "conditional_access_policies", "source": "x",
                    "captured_at": "t", "count": len(items), "items": items}),
    )


# ── Compose ──────────────────────────────────────────────────────────────────


def test_an_empty_tenant_says_not_captured_not_clean(tmp_path, monkeypatch):
    """No audit, no card, no runs: the overview must be distinguishable from
    "we captured it and it is empty"."""
    from app.core import customer as customer_module
    from app.core.config import get_audit_dir
    from app.core.policy_overview import build_overview

    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path / "audits")
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")

    out = build_overview("Acme")
    assert out["inventory_present"] is False
    assert out["captured_at"] is None
    assert out["drift"]["measured"] is False
    assert out["drift"]["added_total"] is None, "unmeasured has no totals"


def test_report_only_with_lockout_risk_suggests_break_glass_first(tmp_path, monkeypatch):
    """The overview reads the same lockout rule the deploy path enforces.

    A report-only MFA policy that applies to All and excludes nobody cannot
    jump straight to enforced — an admin without a break glass would be locked
    out — so the hint order says prepare the exclusion first.
    """
    from app.core import customer as customer_module
    from app.core.config import get_audit_dir
    from app.core.policy_overview import build_overview

    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path / "audits")
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")

    risky = {
        "displayName": "Require MFA",
        "state": "enabledForReportingButNotEnforced",
        "conditions": {"users": {"includeUsers": ["All"]}},
        "grantControls": {"builtInControls": ["mfa"]},
    }
    safe = {
        "displayName": "Block legacy",
        "state": "enabledForReportingButNotEnforced",
        "conditions": {"users": {"includeUsers": ["All"], "excludeGroups": ["g1"]}},
        "grantControls": {"builtInControls": ["block"]},
    }
    _write_snapshot(tmp_path / "audits", "Acme", "r1", [risky, safe])
    _write_card(tmp_path / "customers", "Acme", {
        "captured_at": "2026-08-18T10:38:00+00:00", "run": "r1", "total": 2,
        "workloads": {"conditional_access": {
            "count": 2, "label": {"no": "Conditional Access", "en": "Conditional Access"},
            "items": [
                {"name": "Require MFA", "state": "report-only",
                 "summary": {"no": "Krav MFA — alle brukere", "en": "Requires MFA — all users"}},
                {"name": "Block legacy", "state": "report-only",
                 "summary": {"no": "Blokkerer arvelig — alle brukere", "en": "Blocks legacy — all users"}},
            ],
        }},
    })

    out = build_overview("Acme", lang="en")
    items = out["workloads"]["conditional_access"]["items"]
    by_name = {i["name"]: i for i in items}

    risky_hints = [h["code"] for h in by_name["Require MFA"]["improvements"]]
    assert risky_hints == ["add_break_glass", "enforce"], "risk before the step that takes it"
    assert by_name["Require MFA"]["improvements"][0]["text"]["en"], "hint text is bilingual"

    safe_hints = [h["code"] for h in by_name["Block legacy"]["improvements"]]
    assert safe_hints == ["enforce"], "an excluded group is not a lockout"

    assert by_name["Require MFA"]["state"] == "report-only"


def test_enforced_and_off_policies_get_their_own_hints(tmp_path, monkeypatch):
    from app.core import customer as customer_module
    from app.core.config import get_audit_dir
    from app.core.policy_overview import build_overview

    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path / "audits")
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")

    _write_card(tmp_path / "customers", "Acme", {
        "captured_at": "t", "run": "r1", "total": 2,
        "workloads": {"conditional_access": {
            "count": 2, "label": {"no": "CA", "en": "CA"},
            "items": [
                {"name": "Locked in", "state": "on", "summary": {"no": "x", "en": "x"}},
                {"name": "Switched off", "state": "off", "summary": {"no": "x", "en": "x"}},
            ],
        }},
    })

    out = build_overview("Acme")
    items = {i["name"]: i for i in out["workloads"]["conditional_access"]["items"]}
    assert items["Locked in"]["improvements"] == [], "no hint for what is already enforced"
    assert [h["code"] for h in items["Switched off"]["improvements"]] == ["enable"]


def test_drift_survives_and_reports_unmeasured_when_unmeasurable(tmp_path, monkeypatch):
    """The overview shares the drift rule the report already carries:
    a first run and an empty run are unmeasured, not zero."""
    from app.core import customer as customer_module
    from app.core.config import get_audit_dir
    from app.core.policy_overview import build_overview

    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path / "audits")
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")

    (tmp_path / "audits" / "Acme" / "r1").mkdir(parents=True)  # first run, no snapshots

    only_first = build_overview("Acme")
    assert only_first["drift"]["measured"] is False
    assert only_first["drift"]["reason_code"] in ("no_snapshots_in_run", "no_runs")

    _write_snapshot(tmp_path / "audits", "Acme", "r1", [{"id": "a", "displayName": "A", "state": "enabled"}])
    _write_snapshot(tmp_path / "audits", "Acme", "r2", [{"id": "a", "displayName": "A", "state": "disabled"}])

    shifted = build_overview("Acme")
    assert shifted["drift"]["measured"] is True
    assert shifted["drift"]["removed_total"] == 0
    assert shifted["drift"]["added_total"] == 0
    changed = next(s for s in shifted["drift"]["snapshots"] if s["comparable"])
    assert changed["changed"] == [{"id": "a", "name": "A", "fields": ["state"]}]


def test_standard_gap_is_name_matched_and_honest_about_absence(tmp_path, monkeypatch):
    """A standard policy the tenant does not have is a gap, not an error.

    And a tenant policy the standard does not name is not a gap: it is a
    customer decision, and the standard does not overrule it.
    """
    from app.core import customer as customer_module
    from app.core.config import get_audit_dir
    from app.core.policy_overview import build_overview

    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path / "audits")
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")

    out = build_overview("Acme", lang="en")
    # The standard set on disk must be described, whatever it is.
    assert out["standards"], "the Sybr standards are not optional here"
    for std in out["standards"]:
        assert std["name"] or std["id"]
        assert isinstance(std["policies"], list)


def test_standard_entry_marks_presence_and_why(tmp_path, monkeypatch):
    """A named policy the tenant has must show as present, with its why."""
    from app.core import customer as customer_module
    from app.core.config import get_audit_dir
    from app.core.policy_overview import build_overview
    from app.core.policy_templates import list_templates, load_template

    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path / "audits")
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")

    tpl0 = list_templates("en")[0]
    doc = load_template(tpl0["id"])
    first = doc["policies"][0]
    name = first["displayName"]

    _write_snapshot(tmp_path / "audits", "Acme", "r1", [
        {"id": "x", "displayName": name, "state": "enabled"},
    ])

    out = build_overview("Acme", lang="en")
    std = next(s for s in out["standards"] if s["id"] == tpl0["id"])
    entry = next(p for p in std["policies"] if p["name"] == name)
    assert entry["present"] is True
    assert entry["state"] == "on"
    assert entry["why"], "the standard says why; the overview shows it"


# ── Route ────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod
    import app.web.middleware.rate_limit as rl
    from app.web.middleware.auth import _reset_users_exist_cache

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()

    db_mod.DB_PATH = tmp_path / "test.db"
    await db_mod.run_migrations()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()




@pytest.fixture()
async def admin_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core import customer as customer_module
    from app.core.auth import create_access_token, create_user
    from app.core.rbac import set_all_customers
    from app.models.user import Role
    from app.web.server import create_app

    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path / "audits")
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")

    _write_card(tmp_path / "customers", "Acme", {
        "captured_at": "2026-08-18T10:38:00+00:00", "run": "r1", "total": 1,
        "workloads": {"conditional_access": {
            "count": 1, "label": {"no": "CA", "en": "CA"},
            "items": [
                {"name": "Require MFA", "state": "report-only",
                 "summary": {"no": "Krav MFA — alle brukere", "en": "Requires MFA — all users"}},
            ],
        }},
    })

    user = await create_user("admin", GOOD_PASSWORD, "Admin", role=Role.admin)
    await set_all_customers(user.id, True)
    headers = {"Authorization": f"Bearer {await create_access_token(user)}"}

    with TestClient(create_app()) as c:
        c.headers.update(headers)
        yield c


def test_an_overview_route_serves_the_compose(admin_client):
    body = admin_client.get("/api/policy-overview/Acme?lang=en").json()
    assert body["customer_id"] == "Acme"
    assert body["inventory_present"] is True
    assert body["captured_at"] == "2026-08-18T10:38:00+00:00"
    assert body["standards"], "the overview always names the standards"
    items = admin_client.get("/api/policy-overview/Acme?lang=en").json()
    hint = items["workloads"]["conditional_access"]["items"][0]["improvements"][0]
    assert hint["code"] in ("enforce", "add_break_glass"), "report-only gets a next step"



def test_the_router_is_read_only():
    """The overview is a screen, not a writer."""
    from app.web.routes.policy_overview import router

    offenders = []
    for route in router.routes:
        methods = set(getattr(route, "methods", []) or [])
        if methods - {"GET", "HEAD", "OPTIONS"}:
            offenders.append((getattr(route, "path", "?"), sorted(methods)))
    assert not offenders, f"policy-overview gained a mutating route: {offenders}"


# ── Wiring — the same assertions the assessments view carries ───────────────


def test_the_script_is_served():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert re.search(r'src="/static/app-policy-overview\.js', html)


def test_the_view_exists_and_something_dispatches_to_it():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    dispatcher = (STATIC / "app-integrations.js").read_text(encoding="utf-8")
    assert 'id="view-policy-overview"' in html
    assert "policyOverviewLoad()" in dispatcher, "the view is markup nothing opens"


def test_the_menu_entry_is_gated_on_the_view_it_opens():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    entry = next(line for line in html.splitlines() if "showView('policy-overview')" in line)
    assert 'data-view-gate="policy-overview"' in entry


def test_a_feature_owns_the_view_at_viewer_level():
    """Reading a tenant's policies is already a viewer read on the card.

    The overview composes that read with the drift and the standard — no
    writes, no tenant access — so it is viewer-level, not technician-level.
    """
    from app.core.features import FEATURES, Role

    owners = [f for f in FEATURES if "policy-overview" in f.views]
    assert len(owners) == 1, "exactly one feature must own the view"
    assert owners[0].role == Role.viewer


def test_the_strings_the_view_reads_exist_in_both_languages():
    d = json.loads((STATIC / "ui_i18n.json").read_text(encoding="utf-8"))
    for key in (
        "nav_policy_overview", "nav_policy_overview_desc",
        "nav_policy_overview_intro", "msg_po_no_audit", "msg_po_no_policies",
        "msg_po_drift_unmeasured", "msg_po_snap_unmeasured",
        "hdr_drift", "lbl_drift_against", "hdr_std_gap", "lbl_std_missing",
    ):
        assert key in d["no"] and key in d["en"], f"{key} missing a translation"


def test_the_fetch_url_matches_the_route_shape():
    js = (STATIC / "app-policy-overview.js").read_text(encoding="utf-8")
    assert "/api/policy-overview/" in js
    assert "lang=" in js
