"""Secure Score and the authentication methods policy, read back from the Secure Score collector.

The collector's files are read here exactly as a run leaves them, through a
real GraphClient answering from tests/collector_rig.py. 09_secure_score.txt
and 09b_auth_methods_policy.txt now have JSON twins that the readers prefer;
over the same tenant the two must agree, and the sidecar must keep what the
table cuts: an improvement action's title beyond 70 characters.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections.secure_score import SecureScoreSection
from app.reports.compliance import _build_compliance_map
from app.reports.parsers import _parse_secure_score
from app.reports.parsers.common import _sidecar
from app.reports.recommendations import _build_recommendations
from tests.collector_rig import FakeGraph, refused, run_sections

LONG_TITLE = (
    "Ensure the 'Password expiration policy' is set to "
    "'Set passwords to never expire (recommended)'"
)
assert len(LONG_TITLE) > 70

SCORE = {
    "createdDateTime": "2026-10-01T03:00:00Z",
    "currentScore": 45.67,
    "maxScore": 120.0,
    "controlScores": [
        {"controlName": "scid_mfa", "scoreInPercentage": 0.0, "controlCategory": "Identity"},
        {"controlName": "scid_pwd", "scoreInPercentage": 50.0, "controlCategory": "Identity"},
        {"controlName": "scid_dlp", "scoreInPercentage": 20.0, "controlCategory": "Data"},
        {"controlName": "scid_done", "scoreInPercentage": 100.0, "controlCategory": "Apps"},
    ],
}

PROFILES = [
    {"id": "scid_mfa", "maxScore": 10.0, "title": "Ensure MFA is enabled for all users"},
    {"id": "scid_pwd", "maxScore": 30.0, "title": LONG_TITLE},
    {"id": "scid_dlp", "maxScore": 5.0, "title": "Turn on DLP policies"},
    {"id": "scid_done", "maxScore": 8.0, "title": "Already done"},
]


def _routes(**overrides) -> dict:
    routes = {
        "security/secureScores": {"value": [SCORE]},
        "security/secureScoreControlProfiles": PROFILES,
        "policies/authenticationMethodsPolicy": {"authenticationMethodConfigurations": []},
        "identity/conditionalAccess/authenticationStrength/policies": [],
    }
    routes.update(overrides)
    return routes


async def _collect(tmp_path, *, sidecars: bool, **overrides) -> dict:
    async with FakeGraph(_routes(**overrides)) as fake:
        files = await run_sections(SecureScoreSection(tmp_path, fake.client), sidecars=sidecars)
        assert fake.unrouted == []
    return files


async def test_the_text_carries_each_actions_category_to_the_recommendation(tmp_path):
    files = await _collect(tmp_path, sidecars=False)

    score = _parse_secure_score(files["09_secure_score.txt"])

    assert [i["category"] for i in score["improvements"]] == ["Identity", "Identity", "Data"]
    recs = _build_recommendations(
        mfa={"has_data": False},
        spf_dmarc=[],
        secure_score=score,
        ext_fwd="",
        risky_users="",
        licenses=[],
    )
    rec = next(r for r in recs if r["finding_id"] == "finding-securescore")
    assert rec["sub_items"][0] == f"{LONG_TITLE[:70]} (Identity)"
    assert not any(item.endswith("()") for item in rec["sub_items"])


# ── 09_secure_score: sidecar and text ─────────────────────────────────────────

SHORT_PROFILES = [{**p, "title": p["title"][:40].rstrip()} for p in PROFILES]


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_score_reads_the_same_from_either_file(tmp_path, sidecars):
    files = await _collect(
        tmp_path, sidecars=sidecars, **{"security/secureScoreControlProfiles": SHORT_PROFILES}
    )
    sidecar = _sidecar(files, "09_secure_score.txt")
    assert (sidecar is not None) is sidecars

    score = _parse_secure_score(files["09_secure_score.txt"], sidecar)

    assert score == {
        "current": 45.7,
        "max": 120.0,
        "pct": 38.1,
        "improvements": [
            {
                "name": LONG_TITLE[:40].rstrip(),
                "pct": 50.0,
                "remaining": 15.0,
                "category": "Identity",
            },
            {
                "name": "Ensure MFA is enabled for all users",
                "pct": 0.0,
                "remaining": 10.0,
                "category": "Identity",
            },
            {"name": "Turn on DLP policies", "pct": 20.0, "remaining": 4.0, "category": "Data"},
        ],
        "has_data": True,
    }


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_without_control_profiles_the_ranking_agrees_from_either_file(tmp_path, sidecars):
    files = await _collect(
        tmp_path, sidecars=sidecars, **{"security/secureScoreControlProfiles": refused()}
    )

    score = _parse_secure_score(
        files["09_secure_score.txt"], _sidecar(files, "09_secure_score.txt")
    )

    assert [(i["name"], i["pct"]) for i in score["improvements"]] == [
        ("scid_mfa", 0.0),
        ("scid_dlp", 20.0),
        ("scid_pwd", 50.0),
    ]
    assert all("remaining" not in i for i in score["improvements"]), "no points to show"


async def test_the_sidecar_keeps_the_whole_title(tmp_path):
    files = await _collect(tmp_path, sidecars=True)

    score = _parse_secure_score(
        files["09_secure_score.txt"], _sidecar(files, "09_secure_score.txt")
    )

    assert score["improvements"][0]["name"] == LONG_TITLE


async def test_the_score_sidecar_is_what_the_reader_reads(tmp_path):
    files = await _collect(tmp_path, sidecars=True)
    sidecar = _sidecar(files, "09_secure_score.txt")

    score = _parse_secure_score("", sidecar)

    assert score["has_data"] is True
    assert score["pct"] == 38.1
    assert len(score["improvements"]) == 3
    assert sidecar["current"] == 45.67, "the sidecar keeps the score unrounded"


@pytest.mark.parametrize("answer", [refused(), {"value": []}], ids=["refused", "no score recorded"])
async def test_no_score_writes_no_sidecar_and_reads_as_unmeasured(tmp_path, answer):
    files = await _collect(tmp_path, sidecars=True, **{"security/secureScores": answer})

    assert "09_secure_score.json" not in files
    score = _parse_secure_score(files.get("09_secure_score.txt", ""), None)
    assert score["has_data"] is False


# ── 09b_auth_methods_policy ───────────────────────────────────────────────────


def _method(kind: str, state: str) -> dict:
    return {
        "@odata.type": f"#microsoft.graph.{kind}AuthenticationMethodConfiguration",
        "id": kind[0].upper() + kind[1:],
        "state": state,
    }


METHODS_POLICY = {
    "authenticationMethodConfigurations": [
        _method("fido2", "enabled"),
        _method("microsoftAuthenticator", "enabled"),
        _method("sms", "disabled"),
        _method("voice", "disabled"),
        _method("x509Certificate", "disabled"),
    ]
}

# A user whose only registered method is the phone: both phone methods are off.
PHONE_ONLY = {
    "has_data": True,
    "users": [{"name": "Ola Nordmann", "upn": "ola@acme.example", "methods": "Phone (SMS/Call)"}],
}


def _policy_verdicts(files: dict) -> tuple[str, str, dict | None]:
    rows = _build_compliance_map({"file_contents": files}, lang="no")
    row = next(r for r in rows if r["cis_id"] == "1.1.2")
    recs = _build_recommendations(
        mfa=PHONE_ONLY,
        spf_dmarc=[],
        secure_score={"has_data": False},
        ext_fwd="",
        risky_users="",
        licenses=[],
        file_contents=files,
    )
    lockout = next((r for r in recs if r["finding_id"] == "finding-auth-method-lockout"), None)
    return row["status"], row["detail"], lockout


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_methods_policy_reads_the_same_from_either_file(tmp_path, sidecars):
    files = await _collect(
        tmp_path, sidecars=sidecars, **{"policies/authenticationMethodsPolicy": METHODS_POLICY}
    )
    assert ("09b_auth_methods_policy.json" in files) is sidecars

    status, detail, lockout = _policy_verdicts(files)

    assert status == "pass"
    assert detail.endswith("fido2"), "x509Certificate is disabled"
    assert lockout is not None
    assert lockout["sub_items"] == ["Ola Nordmann (ola@acme.example)"]


async def test_the_methods_policy_sidecar_is_what_the_readers_read(tmp_path):
    files = await _collect(
        tmp_path, sidecars=True, **{"policies/authenticationMethodsPolicy": METHODS_POLICY}
    )
    files["09b_auth_methods_policy.txt"] = ""

    status, _detail, lockout = _policy_verdicts(files)

    assert status == "pass"
    assert lockout is not None


async def test_a_refused_methods_policy_writes_no_sidecar(tmp_path):
    files = await _collect(
        tmp_path, sidecars=True, **{"policies/authenticationMethodsPolicy": refused()}
    )

    assert "09b_auth_methods_policy.json" not in files
    status, _detail, lockout = _policy_verdicts(files)
    assert status == "info"
    assert lockout is None
