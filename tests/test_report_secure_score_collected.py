"""Secure Score and the authentication methods policy, read back from the Secure Score collector.

The collector's files are read here exactly as a run leaves them, through a
real GraphClient answering from tests/collector_rig.py.
"""

from __future__ import annotations

from app.modules.m365_audit.sections.secure_score import SecureScoreSection
from app.reports.parsers import _parse_secure_score
from app.reports.recommendations import _build_recommendations
from tests.collector_rig import FakeGraph, run_sections

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
