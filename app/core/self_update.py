"""Operator-initiated self-update: pull the deployed branch and re-exec.

The service runs from a git checkout under systemd (``python main.py`` in
``/opt/sybr-hub``). This lets an admin update it from inside the app instead of
reaching the host — the box the app runs on sits behind a Tailscale tailnet the
operator's browser can reach but a build environment cannot.

The mechanism is deliberately small and constrained:

* It only ever fast-forwards the **current branch to its ``origin`` counterpart**.
  No ref, remote or URL comes from the request — the worst an attacker who
  reached the endpoint could do is deploy whatever ``origin`` already publishes,
  which is the same trust the host's ``git pull`` already extends.
* A detached HEAD, a dirty tree, or a non-git checkout is refused rather than
  guessed at.
* The restart is an ``os.execv`` in place: the running interpreter replaces its
  own image with a fresh ``python main.py`` on the new code. systemd keeps
  supervising the same PID, migrations re-run at startup, and no privilege is
  needed — the process cannot ``systemctl restart`` itself under
  ``NoNewPrivileges`` and does not have to.

The endpoint that calls this is admin + ``can_write`` gated and unreachable from
scheduled code; see ``app/web/routes/system.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# The repo root is the directory containing main.py — three parents up from this
# file (app/core/self_update.py -> app/core -> app -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]

_GIT_TIMEOUT = 120  # seconds — a fetch/reset on a small repo is quick; a stuck
_PIP_TIMEOUT = 600  # network call must fail rather than hang the request.
_IMPORT_TIMEOUT = 90  # the boot-smoke import of the updated code.
_REEXEC_DELAY = 1.0  # let the HTTP response flush before we replace the process.


def _read_commit_now() -> str | None:
    """The short HEAD commit, read synchronously (used once, at import)."""
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip() or None
    except Exception:
        return None


# The commit THIS process booted with, captured at import — i.e. at process
# start. A post-update poll matches against *this* (see the route's
# running_commit), not a live `rev-parse`, so "restart succeeded" means the new
# process is serving, not merely that the working tree on disk was advanced
# (which happens ~1s before the re-exec, and regardless of whether the new
# process ever comes up healthy).
BOOTED_COMMIT = _read_commit_now()


class SelfUpdateError(RuntimeError):
    """A self-update could not be performed; the message is operator-facing."""


async def _git(*args: str, timeout: int = _GIT_TIMEOUT) -> str:
    """Run a git command in the repo root and return stdout (stripped).

    Raises SelfUpdateError with the stderr on non-zero exit or timeout. The
    arguments are fixed strings from this module — no request data reaches them.
    """
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(REPO_ROOT), *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as exc:
        proc.kill()
        raise SelfUpdateError(f"git {args[0]} timed out after {timeout}s") from exc
    if proc.returncode != 0:
        detail = (err or b"").decode(errors="replace").strip() or f"exit {proc.returncode}"
        raise SelfUpdateError(f"git {args[0]} failed: {detail}")
    return (out or b"").decode(errors="replace").strip()


def _is_git_checkout() -> bool:
    return (REPO_ROOT / ".git").exists()


async def _current_branch() -> str:
    """The checked-out branch, or raise if HEAD is detached.

    A self-update has to know which branch to track. A detached HEAD has no
    upstream to reset to, so we refuse rather than pick one.
    """
    branch = await _git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        raise SelfUpdateError(
            "the deployment is on a detached HEAD, not a branch — cannot update"
        )
    return branch


def _digest_reqs(text: str) -> str:
    """A newline-insensitive digest of a requirements manifest.

    ``git show`` strips the trailing newline that the on-disk file keeps, so
    hashing raw bytes would flag a dependency change on every single update.
    Normalise (strip) both sides before hashing so only real content differs.
    """
    return hashlib.sha256(text.strip().encode()).hexdigest()


def _current_requirements() -> str:
    """The on-disk requirements.txt, or empty string if it is absent."""
    try:
        return (REPO_ROOT / "requirements.txt").read_text()
    except OSError:
        return ""


async def get_update_state() -> dict:
    """Describe the running deployment for the update card, without changing it.

    Returns the current commit, branch and whether this is a git checkout at
    all. It does not contact the network — the button does the fetch — so a card
    render never blocks on ``origin``.
    """
    if not _is_git_checkout():
        return {"is_git": False, "branch": None, "commit": None,
                "updatable": False, "reason": "not a git checkout"}
    try:
        branch = await _current_branch()
        commit = await _git("rev-parse", "--short", "HEAD")
        return {"is_git": True, "branch": branch, "commit": commit, "updatable": True}
    except SelfUpdateError as exc:
        return {"is_git": True, "branch": None, "commit": None,
                "updatable": False, "reason": str(exc)}


async def perform_self_update() -> dict:
    """Fast-forward the current branch to origin and prepare to restart.

    Ordered so a failure at any step leaves the deployment runnable — the whole
    point being a host that cannot easily be reached to fix by hand:

      1. Refuse a dirty tree, a detached HEAD, or local commits not on origin
         (a hotfix made on the box would otherwise be silently discarded).
      2. Install the *target's* dependencies before moving HEAD, so a pip
         failure leaves the working tree and the running process untouched.
      3. Advance with ``merge --ff-only`` — a true fast-forward, never a rewind.
      4. Boot-smoke the new code by importing it in a subprocess; if it cannot
         even import, roll HEAD back to where it was and refuse. This catches
         the common bad deploy (a syntax/import error) before the re-exec would
         put it into a systemd restart loop.

    The re-exec itself is left to the caller (a re-exec here would kill the
    response). Returns {"updated", "already_current", "from", "to", "branch",
    "deps_changed"}; raises SelfUpdateError (operator-facing) on failure.
    """
    if not _is_git_checkout():
        raise SelfUpdateError("this deployment is not a git checkout; update it manually")

    branch = await _current_branch()

    # Modified *tracked* files would be clobbered by the update. Refuse rather
    # than discard a local edit. Untracked files (caches, logs) are left alone.
    dirty = await _git("status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise SelfUpdateError(
            "the checkout has uncommitted local changes to tracked files; "
            "commit or discard them first"
        )

    before = await _git("rev-parse", "HEAD")

    # Fetch only the tracked branch from origin. `origin` and `branch` are the
    # deployment's own configuration, never request input.
    await _git("fetch", "--quiet", "origin", branch)
    target = await _git("rev-parse", f"origin/{branch}")

    if target == before:
        return {"updated": False, "already_current": True,
                "from": before[:12], "to": before[:12],
                "branch": branch, "deps_changed": False}

    # Local commits not on origin mean a fast-forward is impossible; --ff-only
    # would refuse, but naming the reason is friendlier than git's message. This
    # is the hotfix-on-the-box case, and losing it silently is the worst outcome.
    ahead = await _git("rev-list", "--count", f"origin/{branch}..HEAD")
    if ahead != "0":
        raise SelfUpdateError(
            f"the checkout has {ahead} local commit(s) not on origin/{branch}; "
            "push or remove them before updating (refusing to discard them)"
        )

    # Dependencies of the *target*, read from origin without moving HEAD, so a
    # pip failure below happens while the tree is still the running version.
    target_reqs = await _git("show", f"origin/{branch}:requirements.txt")
    deps_changed = _digest_reqs(target_reqs) != _digest_reqs(_current_requirements())
    if deps_changed:
        await _pip_install_text(target_reqs)

    await _git("merge", "--ff-only", f"origin/{branch}")
    after = await _git("rev-parse", "HEAD")

    # Boot-smoke: can the new code even be imported? If not, roll back and
    # refuse rather than re-exec into a crash loop on an unreachable box.
    try:
        await _import_check()
    except SelfUpdateError:
        await _git("reset", "--hard", before)
        log.warning("Self-update rolled back to %s: updated code failed to import", before[:12])
        raise

    log.warning(
        "Self-update applied on branch %s: %s -> %s (deps_changed=%s)",
        branch, before[:12], after[:12], deps_changed,
    )
    return {"updated": True, "already_current": False,
            "from": before[:12], "to": after[:12],
            "branch": branch, "deps_changed": deps_changed}


async def _pip_install_text(requirements: str) -> None:
    """Install *requirements* (the target's requirements.txt content).

    Installs from the target's manifest rather than the working tree, so it can
    run before HEAD moves. Only called when the manifest actually changed.
    """
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(requirements)
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install", "--quiet", "-r", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _out, err = await asyncio.wait_for(proc.communicate(), timeout=_PIP_TIMEOUT)
        except TimeoutError as exc:
            proc.kill()
            raise SelfUpdateError(f"pip install timed out after {_PIP_TIMEOUT}s") from exc
        if proc.returncode != 0:
            detail = (err or b"").decode(errors="replace").strip() or f"exit {proc.returncode}"
            raise SelfUpdateError(f"dependency install failed: {detail}")
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)


async def _import_check() -> None:
    """Import the updated app in a subprocess; raise if it cannot even load.

    Catches the most common bad deploy — a syntax or import error in the pulled
    commit — before the re-exec. It does not catch a *runtime* failure (a bad
    startup migration, a failed key unwrap); the systemd start-limit backstop in
    scripts/sybr-hub.service halts a crash loop into a visible 'failed' state for
    those, and recovery is then manual (documented in docs/UPGRADING.md).
    """
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import app.web.server",
        cwd=str(REPO_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _out, err = await asyncio.wait_for(proc.communicate(), timeout=_IMPORT_TIMEOUT)
    except TimeoutError as exc:
        proc.kill()
        raise SelfUpdateError("the updated code did not finish importing in time") from exc
    if proc.returncode != 0:
        detail = (err or b"").decode(errors="replace").strip()[-600:] or f"exit {proc.returncode}"
        raise SelfUpdateError(f"the updated code failed to import: {detail}")


async def schedule_reexec(delay: float = _REEXEC_DELAY) -> None:
    """Replace this process with a fresh one running the updated code.

    Waits `delay` seconds first so the HTTP response that triggered the update
    has flushed and the browser has started polling for the new version. Then
    ``os.execv`` swaps the interpreter image in place — systemd keeps
    supervising the same PID, and ``main.py`` re-runs migrations on the way up.
    This never returns.
    """
    await asyncio.sleep(delay)
    log.warning("Self-update re-exec: replacing process image with updated code")
    sys.stdout.flush()
    sys.stderr.flush()
    # argv[0] is main.py; re-exec the same interpreter and arguments so the new
    # process is byte-for-byte the systemd ExecStart, now on the new code.
    os.execv(sys.executable, [sys.executable, *sys.argv])
