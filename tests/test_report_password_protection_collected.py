"""Password protection and Security Defaults, read back from the Password Protection collector.

31_password_protection.txt and 31b_smart_lockout.txt now have JSON twins, and
CIS 1.2.1 (custom banned passwords) and 1.1.7 (baseline sign-in protection)
read them first. Both files are short "Label : value" blocks the text reads
precisely, so here the two must simply agree, and a read that failed must
still leave the control unverifiable.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections.password_protection import PasswordProtectionSection
from app.reports.compliance import _build_compliance_map
from tests.collector_rig import FakeGraph, refused, run_sections

NOT_FOUND = refused(404, "Request_ResourceNotFound", "Resource not found.")


def _setting(**values) -> dict:
    return {"values": [{"name": k, "value": v} for k, v in values.items()]}


DIRECTORY_WITH_LIST = [
    _setting(
        BannedPasswordCheckOnPremisesMode="Enforce",
        EnableBannedPasswordCheckOnPremises="True",
        BannedPasswordList="acme\tkundea",
    )
]


def _routes(**overrides) -> dict:
    routes = {
        "groupSettings": DIRECTORY_WITH_LIST,
        "beta/settings/passwords": NOT_FOUND,
        "policies/authenticationMethodsPolicy": {"authenticationMethodConfigurations": []},
        "policies/identitySecurityDefaultsEnforcementPolicy": {"isEnabled": True},
        "identity/conditionalAccess/namedLocations": [
            {
                "@odata.type": "#microsoft.graph.ipNamedLocation",
                "displayName": "Kontoret",
                "isTrusted": True,
            }
        ],
    }
    routes.update(overrides)
    return routes


async def _collect(tmp_path, *, sidecars: bool, **overrides) -> dict:
    async with FakeGraph(_routes(**overrides)) as fake:
        files = await run_sections(
            PasswordProtectionSection(tmp_path, fake.client), sidecars=sidecars
        )
    return files


def _verdict(files: dict, cis_id: str, ca: dict | None = None) -> str:
    context = {"file_contents": files, "ca": ca or {}}
    return next(r["status"] for r in _build_compliance_map(context) if r["cis_id"] == cis_id)


# ── 31_password_protection ────────────────────────────────────────────────────

BANNED_LIST_CASES = {
    "directory settings with a list": ({}, "pass"),
    "directory settings without one": (
        {
            "groupSettings": [
                _setting(BannedPasswordCheckOnPremisesMode="Audit", BannedPasswordList="")
            ]
        },
        "fail",
    ),
    "the password settings endpoint": (
        {
            "groupSettings": [],
            "beta/settings/passwords": {
                "enableCustomBannedPasswords": True,
                "bannedPasswordList": ["acme", "kundea"],
            },
        },
        "pass",
    ),
    "nothing configured anywhere": ({"groupSettings": []}, "fail"),
}


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
@pytest.mark.parametrize("case", BANNED_LIST_CASES, ids=list(BANNED_LIST_CASES))
async def test_the_banned_password_verdict_agrees_from_either_file(tmp_path, case, sidecars):
    overrides, expected = BANNED_LIST_CASES[case]
    files = await _collect(tmp_path, sidecars=sidecars, **overrides)
    assert ("31_password_protection.json" in files) is sidecars

    assert _verdict(files, "1.2.1") == expected


async def test_the_banned_password_sidecar_is_what_the_check_reads(tmp_path):
    files = await _collect(tmp_path, sidecars=True)
    files["31_password_protection.txt"] = ""

    assert _verdict(files, "1.2.1") == "pass"


async def test_settings_that_could_not_be_read_write_no_sidecar(tmp_path):
    files = await _collect(tmp_path, sidecars=True, groupSettings=refused())

    assert "31_password_protection.json" not in files
    assert "were not measured" in files["31_password_protection.txt"]
    assert _verdict(files, "1.2.1") == "info"


# ── 31b_smart_lockout ─────────────────────────────────────────────────────────

SECURITY_DEFAULTS_CASES = {
    "on": ({"isEnabled": True}, {}, "pass"),
    "off, with CA policies enforcing": (
        {"isEnabled": False},
        {"has_data": True, "enabled": 2},
        "pass",
    ),
    "off, and no CA policy": ({"isEnabled": False}, {"has_data": True, "enabled": 0}, "fail"),
    "not there to read": (NOT_FOUND, {"has_data": True, "enabled": 2}, "info"),
}


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
@pytest.mark.parametrize("case", SECURITY_DEFAULTS_CASES, ids=list(SECURITY_DEFAULTS_CASES))
async def test_the_security_defaults_verdict_agrees_from_either_file(tmp_path, case, sidecars):
    answer, ca, expected = SECURITY_DEFAULTS_CASES[case]
    files = await _collect(
        tmp_path,
        sidecars=sidecars,
        **{"policies/identitySecurityDefaultsEnforcementPolicy": answer},
    )
    assert ("31b_smart_lockout.json" in files) is sidecars

    assert _verdict(files, "1.1.7", ca) == expected


async def test_the_security_defaults_sidecar_is_what_the_check_reads(tmp_path):
    files = await _collect(tmp_path, sidecars=True)
    files["31b_smart_lockout.txt"] = ""

    assert _verdict(files, "1.1.7") == "pass"


async def test_a_refused_security_defaults_read_writes_no_sidecar(tmp_path):
    files = await _collect(
        tmp_path,
        sidecars=True,
        **{"policies/identitySecurityDefaultsEnforcementPolicy": refused()},
    )

    assert "31b_smart_lockout.json" not in files
    assert _verdict(files, "1.1.7", {"has_data": True, "enabled": 2}) == "info"
