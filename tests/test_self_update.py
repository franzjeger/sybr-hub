"""The self-update pulls origin and prepares a restart — and refuses when it
should.

These drive the real git plumbing against a throwaway origin + deployment pair,
so a change to the git arguments is caught, not mocked away. The one thing not
exercised here is ``schedule_reexec`` itself: it ``os.execv``s the test runner,
so it is only asserted to be *wired* (in the route test), never called.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from app.core import self_update as su
from app.core.self_update import SelfUpdateError

pytestmark = pytest.mark.asyncio

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
}


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, env=_ENV)


def _sha(cwd) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(cwd), text=True).strip()


@pytest.fixture()
def deploy(tmp_path, monkeypatch):
    """A bare origin, a seed clone that pushes commits, and the deployment.

    ``self_update.REPO_ROOT`` is pointed at the deployment, so perform_self_update
    fast-forwards *it* to whatever the seed has pushed to origin.
    """
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))

    seed = tmp_path / "seed"
    _git(tmp_path, "clone", str(origin), str(seed))
    (seed / "requirements.txt").write_text("httpx\n")
    (seed / "app.py").write_text("# v1\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-m", "init")
    _git(seed, "push", "origin", "main")

    dep = tmp_path / "deploy"
    _git(tmp_path, "clone", str(origin), str(dep))

    monkeypatch.setattr(su, "REPO_ROOT", dep)

    # Never let a test actually re-install deps: record the call instead.
    async def _no_pip(_requirements):
        _no_pip.called = True
    _no_pip.called = False
    monkeypatch.setattr(su, "_pip_install_text", _no_pip)

    # The boot-smoke imports the real app package from the throwaway checkout,
    # which has none — so it always "fails". Neutralise it to a no-op by default;
    # the rollback test overrides this to make it raise on cue.
    async def _import_ok():
        _import_ok.called = True
    _import_ok.called = False
    monkeypatch.setattr(su, "_import_check", _import_ok)

    return {"origin": origin, "seed": seed, "deploy": dep,
            "pip": _no_pip, "import_check": _import_ok, "monkeypatch": monkeypatch}


def _push_new_commit(deploy_env, *, touch_requirements=False):
    seed = deploy_env["seed"]
    (seed / "app.py").write_text("# v2\n")
    if touch_requirements:
        (seed / "requirements.txt").write_text("httpx\nrich\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-m", "change")
    _git(seed, "push", "origin", "main")


async def test_up_to_date_does_not_update(deploy):
    out = await su.perform_self_update()
    assert out["updated"] is False
    assert out["already_current"] is True
    assert deploy["pip"].called is False


async def test_a_new_commit_is_pulled_and_reported(deploy):
    before = _sha(deploy["deploy"])
    _push_new_commit(deploy)

    out = await su.perform_self_update()

    assert out["updated"] is True
    assert out["from"] == before[:12]
    assert out["to"] != out["from"]
    # The deployment now actually points at origin/main.
    assert _sha(deploy["deploy"]) == _sha(deploy["seed"])
    assert out["deps_changed"] is False
    assert deploy["pip"].called is False


async def test_a_dependency_change_triggers_pip(deploy):
    _push_new_commit(deploy, touch_requirements=True)

    out = await su.perform_self_update()

    assert out["updated"] is True
    assert out["deps_changed"] is True
    assert deploy["pip"].called is True, "requirements changed but pip did not run"


async def test_a_modified_tracked_file_is_refused(deploy):
    _push_new_commit(deploy)
    # Local edit to a tracked file that reset --hard would clobber.
    (deploy["deploy"] / "app.py").write_text("# local edit\n")

    with pytest.raises(SelfUpdateError, match="local changes"):
        await su.perform_self_update()


async def test_an_untracked_file_does_not_block(deploy):
    _push_new_commit(deploy)
    # An untracked file (cache/log) is left alone by reset and must not block.
    (deploy["deploy"] / "scratch.log").write_text("noise\n")

    out = await su.perform_self_update()
    assert out["updated"] is True


async def test_import_failure_rolls_back_and_refuses(deploy):
    """If the pulled code fails the boot-smoke, HEAD returns to where it was.

    This is the load-bearing safety property: a bad deploy must not advance the
    working tree, or the re-exec would restart into a crash loop on a box that is
    hard to reach by hand.
    """
    before = _sha(deploy["deploy"])
    _push_new_commit(deploy)

    async def _import_boom():
        raise SelfUpdateError("the updated code failed to import: SyntaxError")
    deploy["monkeypatch"].setattr(su, "_import_check", _import_boom)

    with pytest.raises(SelfUpdateError, match="failed to import"):
        await su.perform_self_update()

    # Rolled back: the deployment still points at the pre-update commit.
    assert _sha(deploy["deploy"]) == before


async def test_a_local_commit_ahead_of_origin_is_refused(deploy):
    """A commit made on the box but not pushed is not silently discarded.

    A fast-forward is impossible when HEAD is ahead of origin; rather than let
    git's --ff-only fail cryptically (or worse, lose the commit), we name it.
    """
    _push_new_commit(deploy)  # origin moves ahead too, so histories diverge
    # A local, unpushed commit on the deployment.
    (deploy["deploy"] / "hotfix.py").write_text("# emergency fix\n")
    _git(deploy["deploy"], "add", "-A")
    _git(deploy["deploy"], "commit", "-m", "local hotfix")

    with pytest.raises(SelfUpdateError, match="local commit"):
        await su.perform_self_update()


async def test_a_detached_head_is_refused(deploy):
    _git(deploy["deploy"], "checkout", "--detach", "HEAD")
    with pytest.raises(SelfUpdateError, match="detached HEAD"):
        await su.perform_self_update()


async def test_a_non_git_checkout_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(su, "REPO_ROOT", tmp_path)  # no .git here
    with pytest.raises(SelfUpdateError, match="not a git checkout"):
        await su.perform_self_update()

    state = await su.get_update_state()
    assert state["is_git"] is False
    assert state["updatable"] is False


async def test_get_update_state_reports_branch_and_commit(deploy):
    state = await su.get_update_state()
    assert state["is_git"] is True
    assert state["branch"] == "main"
    assert state["updatable"] is True
    assert state["commit"] and _sha(deploy["deploy"]).startswith(state["commit"])
