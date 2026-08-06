"""Backfilling a recipe must not rewrite what the record says.

An audit run is a record of what we found and said on a day. Giving it the
means to be re-rendered in another language is a repair; rephrasing its
sentences to whatever today's code would say is an edit of the record, and the
two must not be confused.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "backfill", pathlib.Path("scripts/backfill_recommendation_recipes.py")
)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


@pytest.fixture()
def run(tmp_path, monkeypatch):
    from app.core.encryption import encrypted_write_json

    d = tmp_path / "Acme" / "2026-01-01_0000"
    d.mkdir(parents=True)
    encrypted_write_json(d / "_audit_metrics.json", {
        "timestamp": "2026-01-01T00:00:00Z",
        "risk_grade": "B",
        "recommendations": [
            {"priority": "high", "title": "DMARC mangler eller er svak på x.no",
             "detail": "gammel detalj", "effort": "Lav"},
        ],
    })
    monkeypatch.setattr(
        backfill, "_rebuild",
        lambda run_dir, name, lang: [{
            "title": "DMARC mangler eller er svak på x.no",
            "detail": "ny formulering",
            "rec_id": "rec_dmarc_title:x.no",
            "title_key": "rec_dmarc_title", "title_params": {"domain": "x.no"},
            "detail_key": "rec_dmarc_detail", "detail_params": {},
        }],
    )
    return d


def _read(run):
    from app.core.encryption import encrypted_read_json
    return encrypted_read_json(run / "_audit_metrics.json")


def test_a_dry_run_writes_nothing(run):
    before = _read(run)

    result = backfill.backfill_run(run, "Acme", "no", apply=False)

    assert result["matched"] == 1
    assert _read(run) == before


def test_applying_adds_the_recipe(run):
    backfill.backfill_run(run, "Acme", "no", apply=True)

    rec = _read(run)["recommendations"][0]
    assert rec["rec_id"] == "rec_dmarc_title:x.no"
    assert rec["title_key"] == "rec_dmarc_title"
    assert rec["title_params"] == {"domain": "x.no"}


def test_the_stored_wording_is_left_exactly_as_it_was(run):
    """The repair is the recipe. The sentence is the record."""
    backfill.backfill_run(run, "Acme", "no", apply=True)

    rec = _read(run)["recommendations"][0]
    assert rec["detail"] == "gammel detalj", "today's phrasing overwrote the record"
    assert rec["title"] == "DMARC mangler eller er svak på x.no"


def test_nothing_else_in_the_run_is_touched(run):
    """The timestamp especially — a rewritten one moves the run in the trend."""
    before = _read(run)

    backfill.backfill_run(run, "Acme", "no", apply=True)
    after = _read(run)

    assert after["timestamp"] == before["timestamp"]
    assert after["risk_grade"] == before["risk_grade"]
    assert set(after) == set(before)


def test_a_recommendation_that_no_longer_matches_is_left_alone(run, monkeypatch):
    """Guessing is exactly wrong where the titles have diverged."""
    monkeypatch.setattr(backfill, "_rebuild", lambda *a: [{"title": "something else"}])

    result = backfill.backfill_run(run, "Acme", "no", apply=True)

    assert result["matched"] == 0
    assert result["unmatched"] == ["DMARC mangler eller er svak på x.no"]
    assert "title_key" not in _read(run)["recommendations"][0]


def test_a_run_that_already_has_recipes_is_not_rebuilt(run, monkeypatch):
    """Rebuilding costs a full parse of the run; doing it for nothing is waste."""
    from app.core.encryption import encrypted_read_json, encrypted_write_json

    metrics = encrypted_read_json(run / "_audit_metrics.json")
    metrics["recommendations"][0]["title_key"] = "rec_dmarc_title"
    encrypted_write_json(run / "_audit_metrics.json", metrics)

    def _explode(*a):
        raise AssertionError("rebuilt a run that needed nothing")

    monkeypatch.setattr(backfill, "_rebuild", _explode)

    assert backfill.backfill_run(run, "Acme", "no", apply=True)["already"] == 1
