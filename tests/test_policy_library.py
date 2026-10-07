"""Customer intent must stay distinct from measured, effective tenant policy."""

from datetime import date, timedelta

import pytest

from app.core import policy_library as library
from app.core.customer import CustomerManager
from app.core.encryption import encrypted_read_json, encrypted_write_json
from app.core.exceptions import ConflictError, ToolkitError, ValidationError
from app.core.policy_templates import load_template
from app.models.user import Role
from tests.scope_fixtures import ACME, BETA, _reset_middleware_state, _scope_env, client, login


@pytest.fixture(autouse=True)
def isolated_plans(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.customer._CUSTOMERS_DIR", tmp_path / "customers")


def test_catalog_has_actionable_bilingual_guidance_and_closed_dependencies():
    data = library.catalog()
    policies = {p["id"]: p for p in data["policies"]}
    assert len(policies) >= 39
    assert {a["id"] for a in data["areas"]} >= {
        "intune",
        "sharepoint",
        "teams",
        "onedrive",
        "purview",
        "ca",
    }
    for p in policies.values():
        for field in ("name", "desired", "license", "why", "impact", "verify", "rollback"):
            assert p[field]["no"] and p[field]["en"], (p["id"], field)
        assert len(p["settings"]) >= 2
        assert all(s["no"] and s["en"] for s in p["settings"])
        assert all(d in policies for d in p["dependencies"])
        assert all(s["url"].startswith("https://learn.microsoft.com/") for s in p["sources"])

        def visit(pid, ancestors):
            assert pid not in ancestors, "dependency cycle"
            for dep in policies[pid]["dependencies"]:
                visit(dep, ancestors | {pid})

        visit(p["id"], set())
        if p["deployment"]:
            template = load_template(p["deployment"]["template_id"])
            assert any(
                pol["displayName"] == p["deployment"]["policy_name"] for pol in template["policies"]
            )
    for pack in data["packages"]:
        assert pack["policy_ids"]
        assert set(pack["policy_ids"]) <= policies.keys()
        assert all(
            set(policies[pid]["dependencies"]) <= set(pack["policy_ids"])
            for pid in pack["policy_ids"]
        )
    assert sum(bool(p.get("recommended")) for p in data["packages"]) == 1


def test_new_plan_is_unassessed_and_saving_tailored_plan_adds_dependencies():
    assert library.load_plan(ACME)["package_id"] is None
    plan = library.save_plan(ACME, "managed-workplace", ["ca-compliant"], 0, "reviewer")
    assert {
        "ca-compliant",
        "intune-compliance",
        "intune-encryption",
        "intune-firewall",
        "entra-emergency",
    } <= set(plan["policy_ids"])
    assert plan["reviews"] == {}
    assert library.load_plan(BETA)["policy_ids"] == []
    path = CustomerManager.get_customer_dir(ACME) / "policy_plan.json"
    assert b"ca-compliant" not in path.read_bytes()
    assert encrypted_read_json(path)["updated_by"] == "reviewer"


def test_empty_selection_is_distinct_from_whole_package():
    assert library.save_plan(ACME, "foundation", [], 0, "u")["policy_ids"] == []
    plan = library.save_plan(ACME, "foundation", None, 1, "u")
    assert plan["policy_ids"]


def test_stale_tab_cannot_overwrite_another_review_or_plan():
    library.save_plan(ACME, "foundation", None, 0, "u")
    library.save_review(
        ACME, "ca-mfa", "aligned", "Pilot and assignments checked: ticket 42", None, 1, "v"
    )
    with pytest.raises(ConflictError):
        library.save_plan(ACME, "advanced", None, 1, "u")
    with pytest.raises(ConflictError):
        library.save_review(ACME, "ca-mfa", "needs_change", "Old tab", None, 1, "u")
    plan = library.load_plan(ACME)
    assert plan["package_id"] == "foundation"
    assert plan["reviews"]["ca-mfa"]["reviewed_by"] == "v"


@pytest.mark.parametrize(
    "status,note,due",
    [
        ("aligned", "", None),
        ("needs_change", "  ", None),
        ("exception", "Approved", None),
        ("exception", "Approved", date.today()),
        ("aligned", "Evidence", date.today() - timedelta(days=1)),
    ],
)
def test_review_requires_evidence_and_exceptions_need_future_expiry(status, note, due):
    with pytest.raises(ValidationError):
        library.save_review(ACME, "ca-mfa", status, note, due, 0, "u")
    assert library.load_plan(ACME)["revision"] == 0


def test_changed_guidance_and_expired_review_need_reassessment(monkeypatch):
    plan = library.save_review(
        ACME, "ca-mfa", "exception", "Approved ticket 12", date.today() + timedelta(days=2), 0, "u"
    )
    assert plan["reviews"]["ca-mfa"]["stale"] is False
    original = library.catalog

    def changed():
        data = original()
        next(p for p in data["policies"] if p["id"] == "ca-mfa")["fingerprint"] = "new-content"
        return data

    monkeypatch.setattr(library, "catalog", changed)
    assert library.load_plan(ACME)["reviews"]["ca-mfa"]["stale"] is True
    monkeypatch.setattr(library, "catalog", original)
    path = CustomerManager.get_customer_dir(ACME) / "policy_plan.json"
    saved = encrypted_read_json(path)
    saved["reviews"]["ca-mfa"]["review_due"] = date.today().isoformat()
    encrypted_write_json(path, saved)
    assert library.load_plan(ACME)["reviews"]["ca-mfa"]["stale"] is True
    reset = library.save_review(ACME, "ca-mfa", "not_assessed", "", None, 1, "u")
    assert "ca-mfa" not in reset["reviews"]


def test_corrupt_stored_plan_is_never_overwritten():
    path = CustomerManager.get_customer_dir(ACME) / "policy_plan.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"broken-encrypted-data")
    with pytest.raises(ToolkitError):
        library.save_plan(ACME, "foundation", None, 0, "u")
    assert path.read_bytes() == b"broken-encrypted-data"


async def test_viewer_can_read_but_only_granted_writers_can_save(client):
    viewer = await login("policy-viewer", role=Role.viewer, customers=(ACME,), write=False)
    read = client.get(f"/api/policy-overview/{ACME}", headers=viewer)
    assert read.status_code == 200
    assert read.json()["catalog"]["policies"]
    assert read.json()["plan"]["reviews"] == {}
    payload = {"package_id": "foundation", "expected_revision": 0}
    assert (
        client.post(f"/api/policy-overview/{ACME}/plan", headers=viewer, json=payload).status_code
        == 403
    )
    tech = await login("policy-tech", customers=(ACME,))
    assert (
        client.post(f"/api/policy-overview/{BETA}/plan", headers=tech, json=payload).status_code
        == 403
    )
    assert client.get(f"/api/policy-overview/{BETA}", headers=tech).status_code == 403
    # Internal customer plans need can_write, not tenant_write.
    saved = client.post(f"/api/policy-overview/{ACME}/plan", headers=tech, json=payload)
    assert saved.status_code == 200, saved.text
    review = client.post(
        f"/api/policy-overview/{ACME}/reviews/ca-mfa",
        headers=tech,
        json={
            "status": "aligned",
            "note": "Assignments and sign-in pilot verified",
            "expected_revision": 1,
        },
    )
    assert review.status_code == 200, review.text
    conflict = client.post(
        f"/api/policy-overview/{ACME}/plan", headers={**tech, "Accept-Language": "en"}, json=payload
    )
    assert conflict.status_code == 409
    assert "another tab" in conflict.json()["error"]
    assert (
        client.post(
            f"/api/policy-overview/{ACME}/plan", headers=tech, json={**payload, "apply": True}
        ).status_code
        == 422
    )


def test_two_writers_with_same_revision_do_not_drop_each_others_changes():
    from concurrent.futures import ThreadPoolExecutor

    def save(package):
        try:
            return library.save_plan(ACME, package, None, 0, package)["package_id"]
        except ConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["foundation", "advanced"]))
    assert results.count("conflict") == 1
    assert library.load_plan(ACME)["revision"] == 1
    assert library.load_plan(ACME)["package_id"] in results


async def test_matching_another_customers_audit_folder_is_not_read_access(
    client, tmp_path, monkeypatch
):
    from app.core.encryption import encrypted_write_json
    from tests.scope_fixtures import CUSTOMERS

    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path / "audits")
    run = tmp_path / "audits" / "Acme_AS" / "2026-10-01_120000"
    run.mkdir(parents=True)
    encrypted_write_json(run / "_audit_metrics.json", {})
    # A lossy folder-name collision requires grants for all matching customers.
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [CUSTOMERS[0], {**CUSTOMERS[1], "CustomerName": "Acme AS"}]),
    )
    headers = await login("collision-policy-reader", customers=(ACME,), write=False)
    response = client.get(f"/api/policy-overview/{ACME}", headers=headers)
    assert response.status_code == 403, response.text
