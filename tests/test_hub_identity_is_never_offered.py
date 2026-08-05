"""The hub must offer only the credential it resolved for the host.

``client_keys=None`` is the value both SSH call sites pass, and it is load
bearing: asyncssh reads ``None`` as "offer no keys, and no agent either",
while an empty list — or omitting the argument, which is asyncssh's own
default — falls through to ``load_default_keypairs()`` and reads the hub's
``~/.ssh``. That would hand the hub's own identity to every customer device
that happened to trust it, configured by nobody and recorded nowhere.

The distinction is invisible at the call site and looks exactly like sloppy
code, so it is pinned here: both the asyncssh behaviour these call sites rely
on, and the fact that they still pass ``None``.
"""

from __future__ import annotations

import inspect
import os

import asyncssh
import pytest

from app.services import ssh_manager
from app.web.routes import terminal


@pytest.fixture()
def hub_key(tmp_path, monkeypatch):
    """Give the "hub" a private key in ~/.ssh, the way a real host has one."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    key = asyncssh.generate_private_key("ssh-ed25519")
    path = ssh_dir / "id_ed25519"
    path.write_bytes(key.export_private_key())
    os.chmod(path, 0o600)
    return path


def _resolved(client_keys):
    opts = asyncssh.SSHClientConnectionOptions(username="x", client_keys=client_keys)
    return opts.client_keys, opts.agent_path


class TestWhatEachClientKeysValueActuallyMeans:
    def test_none_offers_nothing_and_disables_the_agent(self, hub_key):
        keys, agent = _resolved(None)
        assert keys is None, "None must not load the hub's own keys"
        assert agent is None, "None must not leave the SSH agent reachable either"

    @pytest.mark.parametrize("value", [[], ()])
    def test_an_empty_sequence_loads_the_hubs_own_identity(self, hub_key, value):
        """This is the trap. It is why the call sites may not be "tidied"."""
        keys, agent = _resolved(value)
        assert keys, f"{value!r} silently loaded the hub's ~/.ssh"
        assert agent is not None

    def test_an_explicit_key_is_the_only_one_offered(self, hub_key):
        other = asyncssh.import_private_key(
            asyncssh.generate_private_key("ssh-ed25519").export_private_key()
        )
        keys, _ = _resolved([other])
        assert keys is not None and len(keys) == 1


class TestTheCallSitesStillPassNone:
    """A source-level guard: the runtime path needs a live SSH server to
    exercise, so pin the argument instead."""

    @pytest.mark.parametrize(
        "source",
        [
            inspect.getsource(ssh_manager._connect_to_host),
            inspect.getsource(terminal._handle_ssh_terminal),
        ],
        ids=["ssh_manager._connect_to_host", "terminal._handle_ssh_terminal"],
    )
    def test_no_call_site_passes_an_empty_key_list(self, source):
        assert "client_keys=[]" not in source.replace(" ", "")
        assert "client_keys" in source, "the argument must stay explicit"

    def test_connect_is_never_called_without_the_argument(self):
        """Omitting it is the same failure as passing []: asyncssh's own
        default for client_keys is (), which loads the hub's keys."""
        source = inspect.getsource(ssh_manager._connect_to_host).replace(" ", "")
        assert "client_keys=client_keys" in source


class TestTheHostCredentialIsResolvedBeforeConnecting:
    async def test_a_password_host_sends_its_password_and_no_keys(self, monkeypatch):
        seen = {}

        async def _fake_connect(**kwargs):
            seen.update(kwargs)
            return object()

        monkeypatch.setattr(
            ssh_manager.SshSession, "connect", staticmethod(_fake_connect)
        )
        monkeypatch.setattr(ssh_manager, "_load_host_password", lambda _id: "s3cret")

        from datetime import UTC, datetime

        from app.models.ssh import AuthMethod, DeviceType, SshHost

        host = SshHost(
            id="h1", label="SRV", hostname="10.20.1.10", port=22, username="root",
            group_name="", device_type=DeviceType.linux,
            auth_method=AuthMethod.password, auth_key_id=None, customer_id="acme",
            tags=[], notes="", last_seen=None, is_reachable=None,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC), created_by=None,
        )
        await ssh_manager._connect_to_host(host)

        assert seen["password"] == "s3cret"
        assert seen["client_keys"] is None, "a password host must offer no key at all"


class TestTheTerminalDoesNotConnectWithoutTheStoredCredential:
    """Falling through with neither a password nor a key produced "Permission
    denied" at the far end, which sends the technician to look at the
    customer's host for a fault that is on this one."""

    def test_a_password_that_will_not_load_stops_the_session(self):
        source = inspect.getsource(terminal._handle_ssh_terminal)
        assert "if not password:" in source
        # and it must return rather than continue into the connect
        after = source.split("if not password:", 1)[1]
        assert "return" in after.split("elif")[0]

    def test_an_ad_hoc_address_is_restricted_and_logged(self):
        """An address typed into the query string belongs to no customer, so
        nobody's grant covers it — and it used to be reached with no tenancy
        check and no activity entry."""
        source = inspect.getsource(terminal._handle_ssh_terminal)
        adhoc = source.split("elif host:", 1)
        assert len(adhoc) == 2, "the ad-hoc branch is gone or was renamed"
        branch = adhoc[1].split("if not host:")[0]
        assert "get_accessible_customer_ids" in branch
        assert "log_activity" in branch
