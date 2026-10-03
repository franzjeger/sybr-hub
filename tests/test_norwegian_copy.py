"""The Norwegian copy keeps to one voice and one glossary.

Two kinds of drift crept into the strings over time. Em and en dashes, which
read as translated English in Norwegian UI text, and several words for the
same thing: "Varsler" meant alerts, warnings and notifications at once, and the
0-100 score where 100 is best was called a risk score. These tests hold the
line the copy pass drew.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from app.web.i18n import _UI_STRINGS

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _norwegian() -> dict[str, str]:
    ui = json.loads((ROOT / "app/web/static/ui_i18n.json").read_text(encoding="utf-8"))["no"]
    server = {f"server:{k}": v for k, v in _UI_STRINGS["no"].items()}
    return {k: v for k, v in (ui | server).items() if isinstance(v, str)}


def test_no_dashes_in_norwegian_text():
    dashed = sorted(k for k, v in _norwegian().items() if "\N{EM DASH}" in v or "\N{EN DASH}" in v)
    assert not dashed, f"Norwegian strings with an em or en dash: {dashed}"


def _norwegian_in(node, path=""):
    """Every "no" string in a bilingual data file, with where it sits."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "no" and isinstance(value, str):
                yield f"{path}/no", value
            else:
                yield from _norwegian_in(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _norwegian_in(value, f"{path}[{i}]")


@pytest.mark.parametrize("folder", ["app/baselines", "app/policy_templates"])
def test_no_dashes_in_norwegian_data(folder):
    # The frameworks on the Vurderinger tab and the policy standards carry
    # their own Norwegian text, which the copy pass never read: "CIS 1.1.1 —
    # Ingen bruker står helt uten MFA". Policy display names are English and
    # matched by name in the tenant, so only the "no" fields are held here.
    dashed = [
        f"{path.name}{where}"
        for path in sorted((ROOT / folder).glob("*.json"))
        for where, text in _norwegian_in(json.loads(path.read_text(encoding="utf-8")))
        if "\N{EM DASH}" in text or "\N{EN DASH}" in text
    ]
    assert not dashed, f"Norwegian text with an em or en dash: {dashed}"


@pytest.mark.parametrize(
    ("pattern", "use"),
    [
        (r"\bFjernaksess\b", "Fjerntilgang"),
        (r"\bAzure AD\b", "Entra ID"),
        (r"\bRemediering\b", "Utbedring"),
        (r"\b[Rr]isikoscore\b", "Sikkerhetsscore (100 is best)"),
        (r"\bLagringmappe\b", "Lagringsmappe"),
        # Words typed without æ, ø or å
        (r"\b(?:enna|Hoy|for a)\b|\bpa tvers\b", "the spelling with æ, ø or å"),
    ],
)
def test_the_glossary_holds(pattern, use):
    hits = sorted(k for k, v in _norwegian().items() if re.search(pattern, v))
    assert not hits, f"{hits} use {pattern!r}; write {use}"
