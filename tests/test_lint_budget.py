"""The lint debt is one-way.

`ruff check` reports about a thousand findings here, nearly all inherited, and
CI runs it non-blocking for a stated reason: the alternative was a lockstep
reformat burying every real change under whitespace. That reasoning is sound,
and its consequence was that nothing stopped the number growing.

The budget records two things and lets neither get worse: the total, and the
files that are already clean. The second is what matters — a single total lets
a new file arrive with twenty findings as long as somebody fixed twenty
elsewhere, which is how a ratchet stops ratcheting.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "lint_budget", pathlib.Path("scripts/lint_budget.py")
)
lint_budget = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint_budget)

BUDGET = pathlib.Path("lint_budget.json")


def test_the_budget_is_recorded():
    data = json.loads(BUDGET.read_text(encoding="utf-8"))

    assert data["total"] > 0, "a zero total would silently pass everything"
    assert len(data["clean_files"]) > 50


def test_the_files_written_since_the_budget_existed_are_clean():
    """The point of tracking clean files rather than only a total."""
    clean = set(json.loads(BUDGET.read_text(encoding="utf-8"))["clean_files"])

    for name in (
        "app/core/policy_templates.py",
        "app/core/policy_drift.py",
        "app/core/baseline.py",
        "app/web/middleware/write_guard.py",
        "app/modules/m365_audit/policy_deploy.py",
        "app/web/routes/policy_deploy.py",
    ):
        assert name in clean, f"{name} is new code and should be lint-clean"


def test_dirtying_a_clean_file_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        lint_budget, "current", lambda: (5, {"app/core/policy_drift.py": 1})
    )
    monkeypatch.setattr(lint_budget, "_tracked_files", lambda: {"app/core/policy_drift.py"})
    monkeypatch.setattr(
        lint_budget, "load_budget",
        lambda: {"total": 9, "clean_files": ["app/core/policy_drift.py"]},
    )

    assert lint_budget.check() == 1
    assert "no longer are" in capsys.readouterr().out


def test_a_rising_total_fails_even_when_no_clean_file_moved(monkeypatch, capsys):
    monkeypatch.setattr(lint_budget, "current", lambda: (10, {"app/legacy.py": 10}))
    monkeypatch.setattr(lint_budget, "_tracked_files", lambda: {"app/legacy.py"})
    monkeypatch.setattr(lint_budget, "load_budget", lambda: {"total": 9, "clean_files": []})

    assert lint_budget.check() == 1
    assert "rose from 9 to 10" in capsys.readouterr().out


def test_an_improvement_passes_and_says_so(monkeypatch, capsys):
    monkeypatch.setattr(lint_budget, "current", lambda: (3, {"app/legacy.py": 3}))
    monkeypatch.setattr(lint_budget, "_tracked_files", lambda: {"app/legacy.py"})
    monkeypatch.setattr(lint_budget, "load_budget", lambda: {"total": 9, "clean_files": []})

    assert lint_budget.check() == 0
    assert "improved" in capsys.readouterr().out


def test_a_deleted_file_does_not_count_as_a_regression(monkeypatch, capsys):
    """A clean file that no longer exists cannot have been dirtied."""
    monkeypatch.setattr(lint_budget, "current", lambda: (0, {}))
    monkeypatch.setattr(lint_budget, "_tracked_files", lambda: set())
    monkeypatch.setattr(
        lint_budget, "load_budget", lambda: {"total": 9, "clean_files": ["app/gone.py"]}
    )

    assert lint_budget.check() == 0


def test_ci_blocks_on_it():
    """Non-blocking is how the previous gate stopped being one."""
    ci = pathlib.Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    step = ci.split("Lint budget")[1]

    assert "lint_budget.py" in step
    assert "continue-on-error" not in step.split("- name:")[0]


def test_it_does_not_claim_an_improvement_that_did_not_happen(monkeypatch, capsys):
    """It reported "improved: 1140 -> 1140" on an unchanged tree.

    A message that says improvement when nothing improved is the noise that
    teaches people to stop reading the output — which is most of what a budget
    is for.
    """
    monkeypatch.setattr(lint_budget, "current", lambda: (9, {"app/legacy.py": 9}))
    monkeypatch.setattr(
        lint_budget, "_tracked_files", lambda: {"app/legacy.py", "app/clean.py"}
    )
    monkeypatch.setattr(
        lint_budget, "load_budget",
        lambda: {"total": 9, "clean_files": ["app/clean.py"]},
    )

    assert lint_budget.check() == 0
    assert "unchanged" in capsys.readouterr().out


def test_a_newly_clean_file_counts_as_an_improvement(monkeypatch, capsys):
    monkeypatch.setattr(lint_budget, "current", lambda: (9, {"app/legacy.py": 9}))
    monkeypatch.setattr(
        lint_budget, "_tracked_files", lambda: {"app/legacy.py", "app/fixed.py"}
    )
    monkeypatch.setattr(lint_budget, "load_budget", lambda: {"total": 9, "clean_files": []})

    assert lint_budget.check() == 0
    assert "1 newly clean" in capsys.readouterr().out


def test_update_refuses_to_record_a_regression(monkeypatch, capsys, tmp_path):
    """The command that maintains the ratchet must not be the one that undoes it.

    It was: running --update after dirtying a file made the new, worse state
    the baseline. That happened within an hour of the budget existing, to me.
    """
    monkeypatch.setattr(lint_budget, "current", lambda: (10, {"app/clean.py": 1}))
    monkeypatch.setattr(lint_budget, "_tracked_files", lambda: {"app/clean.py"})
    monkeypatch.setattr(
        lint_budget, "load_budget", lambda: {"total": 9, "clean_files": ["app/clean.py"]}
    )
    target = tmp_path / "lint_budget.json"
    monkeypatch.setattr(lint_budget, "BUDGET_FILE", target)

    assert lint_budget.update() == 1
    assert not target.exists(), "a worse state was recorded"
    assert "Refusing to record" in capsys.readouterr().out
