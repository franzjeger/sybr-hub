"""An e-mail address or a Temporary Access Pass is not MFA.

The MFA report counted a user as registered when Graph listed any
authentication method other than the password. The e-mail method exists for
self-service password reset and cannot answer an MFA prompt, and a Temporary
Access Pass is a short-lived code for enrolling a real method. A tenant where
SSPR registration had been rolled out showed close to full MFA registration
with nobody able to complete MFA. The break-glass check used the same rule.

The methods are still listed for each user; only the verdict changes. Both
collectors run here against a real GraphClient.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.m365_audit.sections.identity_security import IdentitySecuritySection
from app.modules.m365_audit.sections.users_mfa import MFASection, UsersSection, is_mfa_method
from app.reports.parsers import _parse_mfa
from app.reports.parsers.common import _sidecar
from tests.collector_rig import FakeGraph, run_sections


def _user(uid: str) -> dict:
    return {
        "id": uid,
        "displayName": uid.title(),
        "userPrincipalName": f"{uid}@acme.example",
        "accountEnabled": True,
        "userType": "Member",
        "onPremisesSyncEnabled": False,
        "assignedLicenses": [{"skuId": "sku-1"}],
    }


def _methods(*odata_types: str) -> dict:
    return {"value": [{"@odata.type": f"#microsoft.graph.{t}"} for t in odata_types]}


USERS = [_user("epost"), _user("tap"), _user("app"), _user("begge")]
METHODS = {
    "users/epost/authentication/methods": _methods(
        "passwordAuthenticationMethod", "emailAuthenticationMethod"
    ),
    "users/tap/authentication/methods": _methods(
        "passwordAuthenticationMethod", "temporaryAccessPassAuthenticationMethod"
    ),
    "users/app/authentication/methods": _methods(
        "passwordAuthenticationMethod", "microsoftAuthenticatorAuthenticationMethod"
    ),
    "users/begge/authentication/methods": _methods(
        "emailAuthenticationMethod", "phoneAuthenticationMethod"
    ),
}


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_only_methods_that_can_answer_an_mfa_prompt_count(tmp_path, sidecars):
    routes = {"users": USERS, **METHODS}
    async with FakeGraph(routes) as fake:
        users = UsersSection(tmp_path, fake.client)
        mfa_section = MFASection(tmp_path, fake.client, users.users)
        files = await run_sections(users, mfa_section, sidecars=sidecars)

    mfa = _parse_mfa(
        files["04_mfa_methods.txt"],
        files.get("04b_mfa_ca_analysis.txt", ""),
        [],
        files.get("04_mfa_methods.json", ""),
    )

    assert mfa["total"] == 4
    assert mfa["mfa_registered"] == 2, "the authenticator app and the phone"
    assert mfa["no_mfa_registered"] == 2, "e-mail only, and Temporary Access Pass only"
    # What they do have is still shown to the technician.
    assert "Email OTP" in files["04_mfa_methods.txt"]
    assert "Temp Access Pass" in files["04_mfa_methods.txt"]


async def test_a_global_admin_with_only_an_email_method_has_no_mfa(tmp_path):
    routes = {
        "identityProtection/riskyUsers": [],
        "identityProtection/riskDetections": [],
        "policies/authorizationPolicy": {"allowInvitesFrom": "everyone"},
        "policies/crossTenantAccessPolicy/default": {"isServiceDefault": True},
        "roleManagement/directory/roleEligibilitySchedules": [],
        "auditLogs/directoryAudits": [],
        "security/alerts_v2": [],
        "identityGovernance/accessReviews/definitions": [],
        **METHODS,
    }
    async with FakeGraph(routes) as fake:
        section = IdentitySecuritySection(
            tmp_path,
            fake.client,
            global_admin_ids=["epost", "app"],
            ca_exclusions=set(),
            users_ref=USERS,
            ca_section=SimpleNamespace(policies=[]),
            mfa_analysis_ran=lambda: True,
        )
        files = await run_sections(section, sidecars=True)

    admins = {a["upn"]: a for a in _sidecar(files, "07c_emergency_access_check.txt")["admins"]}
    assert admins["epost@acme.example"]["mfa_registered"] is False
    assert admins["app@acme.example"]["mfa_registered"] is True


def test_the_rule():
    assert is_mfa_method("#microsoft.graph.fido2AuthenticationMethod")
    assert is_mfa_method("#microsoft.graph.softwareOathAuthenticationMethod")
    assert not is_mfa_method("#microsoft.graph.emailAuthenticationMethod")
    assert not is_mfa_method("#microsoft.graph.temporaryAccessPassAuthenticationMethod")
    assert not is_mfa_method("#microsoft.graph.passwordAuthenticationMethod")
