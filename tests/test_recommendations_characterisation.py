"""The prioritised recommendations, pinned exactly.

Every stored input is replayed in both languages and the result must match
the snapshot exactly: the ``json.dumps(..., sort_keys=True)`` text, each
recommendation's key order and value types at every depth (a Localised keeps
the key and parameters it is rebuilt from), the exception raised if any, the
warnings logged, and which lists in the output are the caller's own.

tests/recommendations_characterisation.py says where the inputs come from and
how to regenerate the snapshot when a change in behaviour is intended.
"""

from __future__ import annotations

import json

import pytest

from app.reports.recommendations import _build_recommendations
from tests import recommendations_characterisation as rc

_SNAPSHOT = rc.load()
_CASES = list(rc.stored_contexts(_SNAPSHOT))


def _first_difference(want: str, got: str) -> str:
    a, b = json.loads(want), json.loads(got)
    for i, (x, y) in enumerate(zip(a, b, strict=False)):
        if x != y:
            return f"recommendation {i}:\n  expected {x}\n  got      {y}"
    return f"count: expected {len(a)}, got {len(b)}"


def test_the_snapshot_covers_both_languages_and_the_same_signature():
    assert tuple(_SNAPSHOT["langs"]) == rc.LANGS
    # The generator passes most arguments by position.
    assert _SNAPSHOT["signature"] == rc.signature()
    assert len(_CASES) > 400, "the snapshot has lost most of its inputs"


@pytest.mark.parametrize(
    ("context", "expected"),
    [(ctx, exp) for _, ctx, exp in _CASES],
    ids=[name.replace("::", " ") for name, _, _ in _CASES],
)
def test_output_is_unchanged(context, expected):
    for lang, want in expected.items():
        got = rc.comparable(rc.observe(_build_recommendations, rc.clone(context), lang))
        if "raises" in want:
            assert got.get("raises") == want["raises"], f"lang={lang}"
        else:
            assert "raises" not in got, f"lang={lang}: raised {got['raises']}"
            assert got["dump"] == want["dump"], f"lang={lang}: " + _first_difference(
                want["dump"], got["dump"]
            )
            assert got["shapes"] == want["shapes"], f"lang={lang}: key order or value types"
            assert got["aliases"] == want["aliases"], f"lang={lang}: shared input objects"
        assert got["logs"] == want["logs"], f"lang={lang}: warnings logged"
        assert got["mutates"] == want["mutates"], f"lang={lang}: input mutated"
