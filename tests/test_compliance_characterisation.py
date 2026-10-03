"""The CIS compliance map's output, pinned row for row.

Every stored input is replayed in both languages and every framework
selection, and the result must match the snapshot exactly: the
``json.dumps(..., sort_keys=True)`` text, plus each row's key order and value
types (a Localised detail keeps the key and parameters it is rebuilt from).

tests/compliance_characterisation.py says where the inputs come from and how
to regenerate the snapshot when a change in behaviour is intended.
"""

from __future__ import annotations

import json

import pytest

from app.reports.compliance import _build_compliance_map
from tests import compliance_characterisation as cc

_SNAPSHOT = cc.load()
_CASES = list(cc.stored_contexts(_SNAPSHOT))


def _first_difference(want: str, got: str) -> str:
    a, b = json.loads(want), json.loads(got)
    for i, (x, y) in enumerate(zip(a, b, strict=False)):
        if x != y:
            return f"row {i}:\n  expected {x}\n  got      {y}"
    return f"row count: expected {len(a)}, got {len(b)}"


def test_the_snapshot_covers_both_languages_and_every_framework_selection():
    assert tuple(_SNAPSHOT["langs"]) == cc.LANGS
    assert tuple(_SNAPSHOT["frameworks"]) == cc.FRAMEWORKS
    assert len(_CASES) > 500, "the snapshot has lost most of its inputs"


@pytest.mark.parametrize(
    ("context", "expected"),
    [(ctx, exp) for _, ctx, exp in _CASES],
    ids=[name.replace("::", " ") for name, _, _ in _CASES],
)
def test_output_is_unchanged(context, expected):
    for key, want in expected.items():
        lang, frameworks = key.split("|")
        got = cc.observe(_build_compliance_map, cc.clone(context), lang, frameworks)
        where = f"lang={lang} frameworks={frameworks}"
        if "raises" in want:
            assert got.get("raises") == want["raises"], where
            continue
        assert "raises" not in got, f"{where}: raised {got['raises']}"
        assert got["dump"] == want["dump"], f"{where}: " + _first_difference(
            want["dump"], got["dump"]
        )
        assert got["shapes"] == want["shapes"], f"{where}: key order or value types changed"
