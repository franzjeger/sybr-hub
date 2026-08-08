"""The CI file is part of the repository's security boundary."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")


def test_external_actions_are_pinned_to_full_commits():
    uses = re.findall(r"^\s*- uses:\s*([^\s#]+)", WORKFLOW, flags=re.MULTILINE)
    assert uses, "CI no longer invokes any actions"

    mutable = []
    for use in uses:
        _, separator, revision = use.rpartition("@")
        if not separator or not re.fullmatch(r"[0-9a-f]{40}", revision):
            mutable.append(use)
    assert not mutable, f"mutable or unpinned actions: {mutable}"


def test_checkout_never_persists_a_push_credential():
    checkout_count = WORKFLOW.count("uses: actions/checkout@")
    disabled_count = WORKFLOW.count("persist-credentials: false")
    assert checkout_count > 0
    assert disabled_count == checkout_count


def test_ci_covers_merge_queue_and_manual_recovery():
    assert "  merge_group:" in WORKFLOW
    assert "  workflow_dispatch:" in WORKFLOW


def test_security_jobs_have_timeouts_and_read_only_default_permissions():
    assert "permissions:\n  contents: read" in WORKFLOW
    assert WORKFLOW.count("timeout-minutes:") >= 3


def test_test_matrix_installs_the_async_test_plugin():
    """Installing only the production package silently disables async tests."""
    assert "python -m pip install '.[dev]' pytest-timeout" in WORKFLOW
