"""Reading an audit run must leave it exactly as it was.

build_report_context ends by saving _audit_metrics.json and inserting a trend
row. That is right when an audit has just produced the run, and wrong for
everybody else — and everybody else grew quietly: the baselines endpoint builds
a context to *read* one.

Left alone it meant a customer card rewrote that run's stored metrics on every
open, stamping a months-old audit with the current time, and a maintenance
script that walked every run to inspect it rewrote all of them and left
twenty-one duplicate trend rows in a single second.

These tests are the ones I did not have. The dry-run test I *did* have passed
throughout, because it stubbed out the rebuild — it tested the wrapper and
mocked away the thing that did the damage.
"""

from __future__ import annotations

from app.reports.generator import build_report_context


def _run(tmp_path):
    d = tmp_path / "Acme" / "2026-01-01_0000"
    d.mkdir(parents=True)
    return d


def test_persist_metrics_false_writes_nothing_at_all(tmp_path):
    run = _run(tmp_path)

    build_report_context("Acme", "", run, [], persist_metrics=False)

    assert list(run.iterdir()) == [], f"reading the run created {list(run.iterdir())}"


def test_the_default_still_records_the_run(tmp_path):
    """An audit that has just finished must keep recording itself."""
    run = _run(tmp_path)

    build_report_context("Acme", "", run, [])

    assert (run / "_audit_metrics.json").exists()


def test_reading_twice_does_not_touch_an_existing_record(tmp_path):
    """The shape of the bug: open the card, and the stored run moves."""
    run = _run(tmp_path)
    build_report_context("Acme", "", run, [])
    before = (run / "_audit_metrics.json").read_bytes()

    build_report_context("Acme", "", run, [], persist_metrics=False)

    assert (run / "_audit_metrics.json").read_bytes() == before


def test_the_baselines_route_reads_without_writing():
    """Named explicitly, because this is the caller that caused it.

    Asserting on the source rather than the behaviour is crude, but the
    alternative needs the whole route stack; this at least fails loudly if the
    argument is dropped.
    """
    import pathlib

    src = pathlib.Path("app/web/routes/baselines.py").read_text(encoding="utf-8")

    assert "build_report_context(" in src
    assert "persist_metrics=False" in src, (
        "the baselines endpoint builds a context to read one — without "
        "persist_metrics=False it rewrites the run on every card open"
    )
