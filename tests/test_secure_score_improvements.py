"""«Topp forbedringsområder» listed the things already done.

Two filters, pointing the same wrong way, in two files.

The collector sorted controlScores by ``scoreInPercentage`` *descending* and
headed the result "Top 20 Improvement Actions (by impact)". That field is how
much of a control's own maximum the tenant has already earned, so 100% means
fully implemented and nothing to improve. The table was the twenty controls
the customer had finished — every row 100.0% — under a heading telling them to
go and do those things.

Then the report's parser dropped every row at 0%, which is exactly the set
with the most to gain. Either alone would have skewed the table; together they
guaranteed it showed only completed work.

"By impact" also needs the points at stake, and controlScores does not carry
them — secureScoreControlProfiles does. A control at 50% of thirty points is
worth more than one at 0% of one point, and percentage alone cannot see that.
"""

from __future__ import annotations

import inspect

import pytest

from app.modules.m365_audit.sections.secure_score import SecureScoreSection
from app.reports.generator import _parse_secure_score


def _score_payload(controls: list[dict]) -> dict:
    return {"value": [{
        "createdDateTime": "2026-08-09T00:00:00Z",
        "currentScore": 120.0, "maxScore": 278.0,
        "controlScores": controls,
    }]}


class _Graph:
    """Just enough Graph to drive the section."""

    def __init__(self, controls: list[dict], profiles: list[dict] | None):
        self._controls = controls
        self._profiles = profiles

    async def get(self, path, params=None, **kw):
        if path.startswith("security/secureScores"):
            return _score_payload(self._controls)
        return {}

    async def get_all(self, path, params=None, **kw):
        if path == "security/secureScoreControlProfiles":
            if self._profiles is None:
                raise PermissionError("403")
            return self._profiles
        return []


def _run(tmp_path, controls, profiles=None) -> str:
    import asyncio

    from app.core.encryption import encrypted_read_text
    section = SecureScoreSection(tmp_path, _Graph(controls, profiles))
    asyncio.run(section._collect_score())
    # The collector encrypts what it writes; read it back the way the report
    # does rather than off the raw bytes.
    return encrypted_read_text(tmp_path / "09_secure_score.txt")


_CONTROLS = [
    {"controlName": "mdo_safedocuments", "scoreInPercentage": 100.0, "controlCategory": "Apps"},
    {"controlName": "RoleOverlap", "scoreInPercentage": 100.0, "controlCategory": "Identity"},
    {"controlName": "MFARegistrationV2", "scoreInPercentage": 0.0, "controlCategory": "Identity"},
    {"controlName": "BlockLegacyAuth", "scoreInPercentage": 50.0, "controlCategory": "Identity"},
]
_PROFILES = [
    {"id": "mdo_safedocuments", "maxScore": 5},
    {"id": "RoleOverlap", "maxScore": 3},
    {"id": "MFARegistrationV2", "maxScore": 10},
    {"id": "BlockLegacyAuth", "maxScore": 40},
]


# ── The collector ────────────────────────────────────────────────────────────

def test_a_finished_control_is_not_an_improvement_action(tmp_path):
    text = _run(tmp_path, _CONTROLS, _PROFILES)
    body = text.split("Improvement Actions")[1]
    assert "mdo_safedocuments" not in body
    assert "RoleOverlap" not in body


def test_the_biggest_remaining_gain_comes_first(tmp_path):
    # BlockLegacyAuth is half done but worth 40, so 20 points are left.
    # MFARegistrationV2 is untouched but worth only 10.
    body = _run(tmp_path, _CONTROLS, _PROFILES).split("Improvement Actions")[1]
    assert body.index("BlockLegacyAuth") < body.index("MFARegistrationV2"), (
        "ordered by percentage alone, a cheap untouched control outranks an "
        "expensive half-finished one"
    )


def test_the_points_left_are_shown(tmp_path):
    body = _run(tmp_path, _CONTROLS, _PROFILES).split("Improvement Actions")[1]
    assert "20.0" in body   # 40 * (1 - 0.5)
    assert "10.0" in body   # 10 * (1 - 0.0)


def test_without_the_profiles_it_says_which_ordering_it_used(tmp_path):
    text = _run(tmp_path, _CONTROLS, profiles=None)
    assert "by how far from done" in text
    assert "by points still available" not in text


def test_and_still_leaves_out_the_finished_ones(tmp_path):
    body = _run(tmp_path, _CONTROLS, profiles=None).split("Improvement Actions")[1]
    assert "mdo_safedocuments" not in body
    assert "MFARegistrationV2" in body


def test_a_fully_implemented_tenant_says_so(tmp_path):
    done = [{"controlName": "x", "scoreInPercentage": 100.0, "controlCategory": "c"}]
    assert "every scored control is fully implemented" in _run(tmp_path, done, [])


def test_the_ranking_is_not_reversed_any_more():
    source = inspect.getsource(SecureScoreSection)
    assert 'key=lambda c: c.get("scoreInPercentage", 0),\n            reverse=True' not in source


# ── The parser ───────────────────────────────────────────────────────────────

def _report(rows: str, heading: str = "Top 20 Improvement Actions (by points still available):") -> dict:
    return _parse_secure_score(
        "=" * 80 + "\n  SECURE SCORE\n" + "=" * 80 + "\n"
        "  Score         : 120.0 / 278.0  (43.2%)\n"
        "  As of         : 2026-08-09T00:00:00Z\n\n"
        f"  {heading}\n"
        f"  {'Control':<50} {'Score%':>7}  {'Left':>6}  Category\n"
        "  " + "-" * 76 + "\n" + rows + "\n" + "=" * 80 + "\n"
    )


def test_a_control_at_zero_percent_is_kept():
    got = _report(f"  {'MFARegistrationV2':<50} {0.0:>6.1f}%  {'10.0':>6}  Identity")
    assert [i["name"] for i in got["improvements"]] == ["MFARegistrationV2"], (
        "the rows with the most to gain were the ones being dropped"
    )


def test_the_remaining_points_survive_the_parse():
    got = _report(f"  {'BlockLegacyAuth':<50} {50.0:>6.1f}%  {'20.0':>6}  Identity")
    assert got["improvements"][0]["remaining"] == 20.0


def test_the_column_header_is_not_read_as_a_control():
    got = _report(f"  {'MFARegistrationV2':<50} {0.0:>6.1f}%  {'10.0':>6}  Identity")
    assert all(i["name"] != "Control" for i in got["improvements"])


def test_an_older_run_without_the_left_column_still_parses():
    # Runs recorded before this change say "(by impact)" and have three
    # columns. They are stored on disk and re-rendered on demand.
    got = _parse_secure_score(
        "  Score         : 120.0 / 278.0  (43.2%)\n"
        "  Top 20 Improvement Actions (by impact):\n"
        f"  {'Control':<50} {'Score%':>7}  Category\n"
        "  " + "-" * 76 + "\n"
        f"  {'MFARegistrationV2':<50} {0.0:>6.1f}%  Identity\n"
    )
    assert [i["name"] for i in got["improvements"]] == ["MFARegistrationV2"]
    assert "remaining" not in got["improvements"][0]


def test_the_headline_numbers_are_unchanged():
    got = _report(f"  {'x':<50} {0.0:>6.1f}%  {'1.0':>6}  c")
    assert (got["current"], got["max"], got["pct"]) == (120.0, 278.0, 43.2)
    assert got["has_data"] is True


@pytest.mark.parametrize("lang", ["no", "en"])
def test_the_new_column_is_translated(lang):
    from app.reports.i18n import TRANSLATIONS
    assert TRANSLATIONS["points_left"][lang].strip()
