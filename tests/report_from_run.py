"""Build the report context from a run the collector rig left on disk.

The tests built on tests/collector_rig.py read a run back as files. These two
helpers take it the rest of the way, through build_report_context, so a test
asserts on what the report itself concludes: a reader that stops preferring a
sidecar fails the test even when the parser underneath still could.
"""

from __future__ import annotations

from pathlib import Path

from app.core.encryption import encrypted_read_text, encrypted_write_text
from app.reports.generator import build_report_context


def report(out_dir: Path, *, sidecars: bool = True) -> dict:
    """The report context for the run in out_dir, built as a reader builds it.

    sidecars=False deletes the run's .json sidecars first, which is what a run
    recorded before the collectors wrote them looks like.
    """
    if not sidecars:
        for path in out_dir.glob("*.json"):
            path.unlink()
    return build_report_context(
        "Acme AS", "acme.example", out_dir, [], lang="en", persist_metrics=False
    )


def relabel(path: Path) -> None:
    """Rewrite every "Label: value" in a text file, as a layout change would.

    A reader that prefers the sidecar gives the same answer afterwards; one that
    still reads the text no longer finds its labels.
    """
    encrypted_write_text(path, encrypted_read_text(path).replace(":", " ="))
