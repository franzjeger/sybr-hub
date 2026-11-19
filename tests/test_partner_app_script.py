"""The GDAP partner app is multi-tenant and read-only, and the hub only hands out links.

GDAP gives roles to users in security groups; it does not let an application
read a customer tenant. The hub reads app-only, so the partner app has to be a
multi-tenant registration consented into each customer tenant. The script that
creates it used to make a single-tenant app with Directory.Read.All alone:
every customer token request failed, and listing GDAP relationships (which
needs DelegatedAdminRelationship.Read.All) was refused.

The permission list also decides the blast radius of the one secret the hub
holds for every customer at once, so it may only read.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from app.core.config import REQUIRED_GRAPH_PERMISSIONS

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts/new-partner-app.ps1").read_text(encoding="utf-8")


def _script_permissions() -> list[str]:
    start = SCRIPT.index("# BEGIN GRAPH PERMISSIONS")
    end = SCRIPT.index("# END GRAPH PERMISSIONS")
    return re.findall(r"'([^']+)'", SCRIPT[start:end])


def test_the_app_is_multi_tenant():
    assert "'AzureADMultipleOrgs'" in SCRIPT
    assert "AzureADMyOrg" not in SCRIPT


def test_it_asks_for_what_an_audit_reads_plus_gdap_relationships():
    wanted = set(REQUIRED_GRAPH_PERMISSIONS) | {"DelegatedAdminRelationship.Read.All"}
    assert set(_script_permissions()) == wanted


def test_nothing_it_asks_for_can_write():
    for name in _script_permissions():
        assert "Write" not in name, f"{name} would let one leaked secret write to every customer"


def test_permission_ids_are_resolved_not_copied():
    # A copied GUID that is wrong produces an app with a silent gap.
    assert "AppRoles" in SCRIPT
    assert 'throw "Microsoft Graph has no application permission named' in SCRIPT


# ── Consent link ─────────────────────────────────────────────────────────────


def test_consent_url_points_at_the_customer_tenant():
    from app.web.routes.gdap import consent_url

    url = consent_url("cust-tenant", "partner-app")
    assert url == "https://login.microsoftonline.com/cust-tenant/adminconsent?client_id=partner-app"


@pytest.mark.parametrize(("tid", "cid"), [("", "app"), ("tenant", ""), ("  ", "  ")])
def test_no_consent_url_without_both_ids(tid, cid):
    from app.web.routes.gdap import consent_url

    assert consent_url(tid, cid) == ""


# ── Partner Center client stays read-only ────────────────────────────────────


def test_partner_center_client_only_reads():
    src = (ROOT / "app/integrations/partner_center.py").read_text(encoding="utf-8")
    calls = re.findall(r"self\._client\.(\w+)\(", src)
    # The only POST is the token request.
    assert set(calls) <= {"get", "post", "aclose"}
    assert src.count("self._client.post(") == 1
    assert (
        "_TOKEN_URL" in src[src.index("self._client.post(") - 400 : src.index("self._client.post(")]
    )


# ── Baseline deploy is switched off ──────────────────────────────────────────


@pytest.mark.parametrize("name", ["plan_baseline_deployment", "apply_baseline_deployment"])
def test_baseline_deploy_refuses_before_touching_a_tenant(name, monkeypatch):
    from app.core.exceptions import ValidationError
    from app.models.baseline import M365SecurityBaseline
    from app.web.routes import baseline_deploy

    touched = []

    class _Boom:
        def __init__(self, *a, **k):
            touched.append(a)

    import app.services.baseline_engine as engine_mod

    monkeypatch.setattr(engine_mod, "BaselineEngine", _Boom)

    class _User:
        username = "tester"

    req = baseline_deploy.BaselinePlanRequest(
        baseline=M365SecurityBaseline(), selected=["entra.block_user_consent"]
    )
    with pytest.raises(ValidationError):
        asyncio.run(getattr(baseline_deploy, name)("cust", req, _User()))
    assert touched == []
