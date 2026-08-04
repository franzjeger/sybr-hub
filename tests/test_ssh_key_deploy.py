"""Key push and key revoke — the parts that run on the customer's machine.

Two classes of defect are covered here, both of which shipped:

* ``ssh_manager`` called four methods on ``SshSession`` that the class does not
  define. Every non-sudo push and revoke raised ``AttributeError`` in the SFTP
  strategy, fell through to the exec strategy, and raised it again on its very
  first line — so the feature could not work, and the per-host result reported
  the ``AttributeError`` as if it were the host's fault.
* The revoke one-liner failed on the most ordinary revoke there is (the key was
  the only one in the file), and its sudo variant handed an unprivileged
  account ownership of ``/root/.ssh/authorized_keys``.

The shell here is exercised against real files through a real ``sh``, because
the failure was in the shell, not in Python.
"""

from __future__ import annotations

import inspect
import re
import subprocess
from pathlib import Path

import pytest

from app.services import ssh_manager
from app.services.ssh_connection import SshSession

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDoomedKeyMaterial hub@sybr"
OTHER = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQother other@example"


class TestTheSessionHasEveryMethodTheManagerCalls:
    """The structural guard. ``push_key`` swallows the strategy-1 exception and
    falls through, so a missing method looked exactly like an unsupported
    device — which is why this went unnoticed."""

    def test_no_call_on_a_session_object_is_missing(self):
        source = inspect.getsource(ssh_manager)
        called = set(re.findall(r"\bsession\.([a-z_][a-z0-9_]*)\(", source))
        assert called, "the scan found no session calls at all — has the name changed?"
        missing = sorted(n for n in called if not hasattr(SshSession, n))
        assert not missing, f"ssh_manager calls SshSession.{missing} which do not exist"

    @pytest.mark.parametrize("name", ["get_home", "sftp_mkdir", "sftp_read", "sftp_write"])
    def test_the_filesystem_helpers_exist(self, name):
        assert hasattr(SshSession, name)


def _run_revoke(tmp_path: Path, contents: str, mode: int = 0o600):
    ak = tmp_path / "authorized_keys"
    ak.write_text(contents)
    ak.chmod(mode)
    cmd = ssh_manager._sh_script_command(ssh_manager._revoke_script(str(ak), KEY))
    proc = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True)
    leftovers = sorted(p.name for p in tmp_path.iterdir() if p.name != "authorized_keys")
    return proc, ak, leftovers


class TestRevokingTheLastKeyIsNotAnError:
    """``grep -vF`` exits 1 when nothing matches. Chained with ``&&`` that
    skipped the replacement entirely and raised "Revoke failed" — on a file
    holding only the key the operator asked to remove."""

    def test_the_only_key_in_the_file_is_removed(self, tmp_path):
        proc, ak, leftovers = _run_revoke(tmp_path, KEY + "\n")
        assert proc.returncode == 0, proc.stderr
        assert ak.read_text().strip() == ""
        assert not leftovers, f"staging file left behind: {leftovers}"

    def test_a_key_among_others_is_removed_and_the_rest_kept(self, tmp_path):
        proc, ak, _ = _run_revoke(tmp_path, OTHER + "\n" + KEY + "\n")
        assert proc.returncode == 0, proc.stderr
        assert ak.read_text().splitlines() == [OTHER]

    def test_a_key_that_is_not_there_is_a_no_op_not_a_failure(self, tmp_path):
        proc, ak, _ = _run_revoke(tmp_path, OTHER + "\n")
        assert proc.returncode == 0, proc.stderr
        assert ak.read_text().splitlines() == [OTHER]

    def test_the_file_keeps_its_0600_mode(self, tmp_path):
        _, ak, _ = _run_revoke(tmp_path, OTHER + "\n" + KEY + "\n")
        assert ak.stat().st_mode & 0o777 == 0o600

    def test_the_old_one_liner_really_did_fail_here(self, tmp_path):
        """Pin the defect itself, so the fix cannot be quietly reverted."""
        import base64
        import shlex

        ak = tmp_path / "authorized_keys"
        ak.write_text(KEY + "\n")
        b64 = base64.b64encode(KEY.encode()).decode()
        old = (
            f'tmp=$(mktemp /tmp/.ak_revoke_XXXXXX) && '
            f'grep -vF "$(printf \'%s\' {b64} | base64 -d)" {shlex.quote(str(ak))} > "$tmp" '
            f'&& mv "$tmp" {shlex.quote(str(ak))}'
        )
        proc = subprocess.run(["sh", "-c", old], capture_output=True, text=True)
        assert proc.returncode == 1
        assert ak.read_text().strip() == KEY, "the key survived the revoke"


class TestTheStagingFileNeverLeavesTheTargetDirectory:
    """``mktemp /tmp/...`` plus ``sudo mv`` transferred ownership of root's
    authorized_keys to the login user — an account that could then authorise
    any key it liked, and whose ownership makes sshd's StrictModes refuse the
    file outright."""

    def test_the_script_stages_beside_the_target(self):
        script = ssh_manager._revoke_script("/root/.ssh/authorized_keys", KEY)
        assert "/root/.ssh/authorized_keys.revoke." in script
        assert "mktemp" not in script
        assert "/tmp/" not in script

    def test_the_sudo_variant_runs_the_whole_script_as_root(self):
        """Staging under sudo is what keeps the file root-owned; a sudo applied
        only to the final move is the bug."""
        cmd = ssh_manager._sh_script_command(
            ssh_manager._revoke_script("/root/.ssh/authorized_keys", KEY), sudo=True
        )
        assert cmd.endswith("| sudo sh")
        assert cmd.count("sudo") == 1
