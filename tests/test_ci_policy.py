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


def test_test_matrix_keeps_runtime_locked_and_installs_async_and_tui_tests():
    lock = "python -m pip install --require-hashes -r requirements.lock"
    tools = "python -m pip install '.[dev,tui]' pytest-timeout -c /tmp/sybr-runtime-constraints.txt"
    assert lock in WORKFLOW and tools in WORKFLOW
    assert WORKFLOW.index(lock) < WORKFLOW.index(tools)
    assert "python -m pip freeze > /tmp/sybr-runtime-constraints.txt" in WORKFLOW


def test_dead_browser_code_fails_the_javascript_check():
    """As a warning, unused functions and variables were printed and passed:
    sixteen had piled up before anyone removed them. The rule is an error, and
    the check fails on any warning ESLint still reports."""
    config = Path("eslint.config.cjs").read_text(encoding="utf-8")
    assert re.search(r"'no-unused-vars':\s*\['error'", config), "no-unused-vars is not an error"
    check = Path("scripts/check-javascript.cjs").read_text(encoding="utf-8")
    assert "errors || warnings" in check, "ESLint warnings no longer fail npm run check"
