"""Customer secrets must survive a host with no OS keyring.

Setting up a customer failed on a real CachyOS install at "Generating
self-signed certificate" with NoKeyringError. store_secret called
keyring.set_password unguarded, and keyring *raises* when no Secret Service
provider exists — the normal state on a headless Linux host, and guaranteed
under the systemd unit (system user, ProtectHome=yes, no D-Bus session).

The fallback writes through the same AES-GCM layer as the rest of
MSP_DATA_DIR, so these stay encrypted at rest rather than becoming plaintext
JSON — which would be a poor trade for a file holding client secrets and
certificate passwords.
"""

from __future__ import annotations

import keyring.errors
import pytest


@pytest.fixture
def headless(tmp_path, monkeypatch):
    """A dead keyring and an isolated data dir."""
    def _boom(*a, **k):
        raise keyring.errors.NoKeyringError("no backend")

    monkeypatch.setattr("keyring.set_password", _boom)
    monkeypatch.setattr("keyring.get_password", _boom)
    monkeypatch.setattr("keyring.delete_password", _boom)

    import app.core.credentials as creds

    monkeypatch.setattr(creds, "_FALLBACK_PATH", tmp_path / "secrets.enc")
    creds.clear_secret_cache()
    yield creds
    creds.clear_secret_cache()


def test_a_secret_round_trips_without_a_keyring(headless):
    headless.store_secret("acme", "cert_password", "s3cret-pw")
    headless.clear_secret_cache()          # force a read from disk
    assert headless.get_secret("acme", "cert_password") == "s3cret-pw"


def test_an_absent_secret_is_none_not_an_error(headless):
    assert headless.get_secret("acme", "never-stored") is None


def test_secrets_are_kept_apart_per_tenant(headless):
    headless.store_secret("acme", "client_secret", "aaa")
    headless.store_secret("globex", "client_secret", "bbb")
    headless.clear_secret_cache()
    assert headless.get_secret("acme", "client_secret") == "aaa"
    assert headless.get_secret("globex", "client_secret") == "bbb"


def test_deleting_removes_it_from_the_fallback_too(headless):
    headless.store_secret("acme", "client_secret", "aaa")
    headless.delete_secret("acme", "client_secret")
    headless.clear_secret_cache()
    assert headless.get_secret("acme", "client_secret") is None


def test_deleting_one_tenant_leaves_the_others(headless):
    headless.store_secret("acme", "client_secret", "aaa")
    headless.store_secret("globex", "client_secret", "bbb")
    headless.delete_all_secrets("acme")
    headless.clear_secret_cache()
    assert headless.get_secret("acme", "client_secret") is None
    assert headless.get_secret("globex", "client_secret") == "bbb"


def test_the_fallback_store_is_encrypted_and_private(headless):
    """A plaintext file of client secrets would be a bad trade for uptime."""
    headless.store_secret("acme", "client_secret", "hemmelig-verdi")
    path = headless._FALLBACK_PATH

    raw = path.read_bytes()
    assert b"hemmelig-verdi" not in raw, "secret written in the clear"
    assert raw.startswith(b"MSPTK"), "not written through the encryption layer"
    assert path.stat().st_mode & 0o077 == 0, "readable by group or other"


def test_a_working_keyring_is_still_preferred(tmp_path, monkeypatch):
    """The fallback is for hosts without one — it must not take over where a
    keyring exists, or secrets would silently stop going to the OS store."""
    store: dict = {}
    monkeypatch.setattr("keyring.set_password",
                        lambda s, k, v: store.__setitem__((s, k), v))
    monkeypatch.setattr("keyring.get_password", lambda s, k: store.get((s, k)))

    import app.core.credentials as creds

    monkeypatch.setattr(creds, "_FALLBACK_PATH", tmp_path / "secrets.enc")
    creds.clear_secret_cache()

    creds.store_secret("acme", "client_secret", "via-keyring")
    assert store == {("MSPToolkit", "acme:client_secret"): "via-keyring"}
    assert not (tmp_path / "secrets.enc").exists(), "wrote a fallback file needlessly"
    creds.clear_secret_cache()
