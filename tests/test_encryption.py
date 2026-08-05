"""Tests for app.core.encryption — AES-256-GCM encrypt/decrypt."""

from __future__ import annotations

import json

from app.core.encryption import (
    _MAGIC,
    _MAGIC_V2,
    decrypt_bytes,
    decrypt_text,
    encrypt_bytes,
    encrypt_text,
    is_encrypted,
)


class TestIsEncrypted:
    def test_detects_encrypted_data(self):
        ct = encrypt_bytes(b"hello")
        assert is_encrypted(ct) is True

    def test_rejects_plaintext(self):
        assert is_encrypted(b"just plain bytes") is False

    def test_rejects_empty(self):
        assert is_encrypted(b"") is False

    def test_rejects_short_data(self):
        assert is_encrypted(b"MSP") is False


class TestBytesRoundtrip:
    def test_encrypt_decrypt_roundtrip(self):
        original = b"some binary data \x00\xff"
        ct = encrypt_bytes(original)
        assert decrypt_bytes(ct) == original

    def test_encrypted_starts_with_magic(self):
        ct = encrypt_bytes(b"test")
        assert ct[:len(_MAGIC_V2)] == _MAGIC_V2

    def test_encrypted_differs_from_plaintext(self):
        original = b"secret"
        ct = encrypt_bytes(original)
        assert ct != original

    def test_empty_bytes_roundtrip(self):
        ct = encrypt_bytes(b"")
        assert decrypt_bytes(ct) == b""


class TestTextRoundtrip:
    def test_encrypt_decrypt_text(self):
        original = "Hello, world!"
        ct = encrypt_text(original)
        assert decrypt_text(ct) == original

    def test_unicode_roundtrip(self):
        original = "Norsk tekst: blåbærsyltetøy"
        ct = encrypt_text(original)
        assert decrypt_text(ct) == original


class TestJsonRoundtrip:
    def test_json_via_text(self):
        data = {"tenant": "contoso.com", "score": 42, "items": [1, 2, 3]}
        text = json.dumps(data, indent=2, ensure_ascii=False)
        ct = encrypt_text(text)
        result = json.loads(decrypt_text(ct))
        assert result == data


class TestEmptyJsonFile:
    """Regression: a fresh install creates settings.json before writing
    to it. A live-server smoke test caught that encrypted_read_json on
    a 0-byte file raised JSONDecodeError and crashed every code path
    that reads settings (build_report_context, the web UI, the CLI).
    Empty file should be treated as {}."""

    def test_empty_file_returns_empty_dict(self, tmp_path):
        from app.core.encryption import encrypted_read_json
        p = tmp_path / "settings.json"
        p.write_text("")
        assert encrypted_read_json(p) == {}

    def test_whitespace_only_file_returns_empty_dict(self, tmp_path):
        from app.core.encryption import encrypted_read_json
        p = tmp_path / "settings.json"
        p.write_text("\n  \t\n")
        assert encrypted_read_json(p) == {}


class TestPlaintextFallback:
    def test_decrypt_plaintext_bytes(self):
        """Unencrypted data should pass through decrypt_bytes unchanged."""
        raw = b"legacy plaintext content"
        assert decrypt_bytes(raw) == raw

    def test_decrypt_plaintext_text(self):
        """Unencrypted UTF-8 text should pass through decrypt_text unchanged."""
        raw = "legacy plaintext".encode("utf-8")
        assert decrypt_text(raw) == "legacy plaintext"


# ── Headless Linux: no Secret Service ─────────────────────────────────────────


def _isolate_key_store(tmp_path, monkeypatch):
    """Point the key backups at tmp_path and kill the keyring.

    Patching ``enc.DATA_DIR`` does nothing: ``_backup_locations()`` imports the
    directories from ``app.core.config`` on every call, and ``enc`` has no such
    attribute — so ``raising=False`` silently made the patch a no-op and these
    tests wrote real master-key backups into the developer's data dir and home
    directory. Patch the function that produces the paths instead, which cannot
    fail quietly.
    """
    import keyring.errors

    import app.core.encryption as enc

    def _boom(*a, **k):
        raise keyring.errors.NoKeyringError("no backend")

    monkeypatch.setattr("keyring.get_password", _boom)
    monkeypatch.setattr("keyring.set_password", _boom)
    monkeypatch.setattr(enc, "_cached_key", None)
    monkeypatch.delenv(enc._ENV_MASTER_KEY, raising=False)
    monkeypatch.delenv(enc._ENV_MASTER_KEY_FILE, raising=False)

    locations = [tmp_path / "data" / ".key", tmp_path / "conf" / ".key"]
    monkeypatch.setattr(enc, "_backup_locations", lambda: list(locations))
    return enc, locations


def test_master_key_survives_a_keyring_that_raises(tmp_path, monkeypatch):
    """keyring raises NoKeyringError when no Secret Service provider exists —
    the normal state on a headless box, and guaranteed under the systemd unit
    (system user, ProtectHome=yes, no D-Bus session). That exception used to
    escape _get_or_create_master_key and take the process with it, leaving the
    file-backup recovery chain below it unreachable.
    """
    enc, _ = _isolate_key_store(tmp_path, monkeypatch)

    blob = enc.encrypt_text("hemmelig")
    assert blob.startswith(enc._MAGIC_V2)
    assert enc.decrypt_bytes(blob).decode() == "hemmelig"


def test_the_key_persists_across_a_restart_without_a_keyring(tmp_path, monkeypatch):
    """Second boot must recover the same key from the file backups, or every
    previously encrypted audit becomes unreadable."""
    enc, _ = _isolate_key_store(tmp_path, monkeypatch)

    blob = enc.encrypt_text("hemmelig")

    monkeypatch.setattr(enc, "_cached_key", None)   # simulate a restart
    assert enc.decrypt_bytes(blob).decode() == "hemmelig"


# ── Host identity changes under encrypted data ───────────────────────────────


def test_a_hostname_change_refuses_to_mint_a_new_key(tmp_path, monkeypatch):
    """The DR procedure in the installer is restore-to-a-new-host.

    The backups are wrapped with a passphrase derived from hostname and
    /etc/machine-id, so on the new host they no longer unwrap. Minting a
    replacement there is silent one-way data loss: every customer credential
    and audit archive stays encrypted under a key nobody holds. Refuse instead.
    """
    import pytest

    enc, locations = _isolate_key_store(tmp_path, monkeypatch)

    monkeypatch.setattr(enc, "_machine_passphrase", lambda: "host-AAAA")
    blob = enc.encrypt_text("kundehemmelighet")
    before = {p: p.read_text() for p in locations if p.exists()}
    assert before, "the first boot should have written key backups"

    # Reboot as a different machine.
    monkeypatch.setattr(enc, "_cached_key", None)
    monkeypatch.setattr(enc, "_machine_passphrase", lambda: "host-BBBB")

    with pytest.raises(enc.MasterKeyUnavailableError) as exc:
        enc.decrypt_bytes(blob)
    assert "hostname" in str(exc.value).lower()

    # And crucially, it must not have overwritten the only copies of the key.
    after = {p: p.read_text() for p in locations if p.exists()}
    assert after == before, "an unreadable backup must never be overwritten"

    # Restoring the old identity restores access — which is only true because
    # the blobs above survived.
    monkeypatch.setattr(enc, "_cached_key", None)
    monkeypatch.setattr(enc, "_machine_passphrase", lambda: "host-AAAA")
    assert enc.decrypt_bytes(blob).decode() == "kundehemmelighet"


def test_importing_a_key_works_without_a_keyring(tmp_path, monkeypatch):
    """The Settings "restore key" flow is the recovery path for the case above.

    It called keyring.set_password() before adopting the key, and
    NoKeyringError subclasses KeyringError — so on precisely the headless hosts
    that need recovery it returned False having done nothing.
    """
    import base64

    enc, locations = _isolate_key_store(tmp_path, monkeypatch)
    monkeypatch.setattr(enc, "_machine_passphrase", lambda: "host-AAAA")

    # Data encrypted by the old host, whose key we still hold out of band.
    original = enc._get_or_create_master_key()
    blob = enc.encrypt_text("kundehemmelighet")
    exported = base64.urlsafe_b64encode(original).decode()

    # New host: different passphrase, backups unreadable, cache cold.
    monkeypatch.setattr(enc, "_cached_key", None)
    monkeypatch.setattr(enc, "_machine_passphrase", lambda: "host-BBBB")

    assert enc.import_master_key(exported) is True
    assert enc.decrypt_bytes(blob).decode() == "kundehemmelighet"

    # And it persisted, so the next boot on this host needs no second import.
    monkeypatch.setattr(enc, "_cached_key", None)
    assert enc.decrypt_bytes(blob).decode() == "kundehemmelighet"
    assert any(p.exists() for p in locations)


def test_the_env_override_frees_the_key_from_host_identity(tmp_path, monkeypatch):
    """So a box can be rebuilt from scratch with the key held in a secret manager."""
    import base64

    enc, _ = _isolate_key_store(tmp_path, monkeypatch)
    key = base64.urlsafe_b64encode(bytes(range(32))).decode()

    monkeypatch.setenv(enc._ENV_MASTER_KEY, key)
    blob = enc.encrypt_text("kundehemmelighet")

    # A totally different host, no backups at all — still readable.
    monkeypatch.setattr(enc, "_cached_key", None)
    monkeypatch.setattr(enc, "_machine_passphrase", lambda: "somewhere-else")
    monkeypatch.setattr(enc, "_backup_locations", list)
    assert enc.decrypt_bytes(blob).decode() == "kundehemmelighet"


def test_a_key_file_override_is_read_from_disk(tmp_path, monkeypatch):
    import base64

    enc, _ = _isolate_key_store(tmp_path, monkeypatch)
    key_file = tmp_path / "master.key"
    key_file.write_text(base64.urlsafe_b64encode(bytes(range(32))).decode() + "\n")

    monkeypatch.setenv(enc._ENV_MASTER_KEY_FILE, str(key_file))
    assert enc._get_or_create_master_key() == bytes(range(32))


def test_a_malformed_env_key_fails_loudly_rather_than_minting(tmp_path, monkeypatch):
    """A typo'd override must not silently fall through to a brand-new key."""
    import pytest

    enc, _ = _isolate_key_store(tmp_path, monkeypatch)
    monkeypatch.setenv(enc._ENV_MASTER_KEY, "not-valid-base64!!")

    with pytest.raises(enc.MasterKeyUnavailableError):
        enc._get_or_create_master_key()


def test_absent_keyring_is_not_logged_as_a_problem(caplog):
    """A headless host has no keyring; saying so four times per boot is noise.

    The messages were warning and error level, and their text was identical to
    what a genuine keyring failure produces — so the operator learned to read
    past the one line that would have mattered. Absence is debug; a keyring
    that exists and then misbehaves is still a warning.
    """
    import logging

    import keyring.errors

    from app.core.encryption import _log_keyring_absence

    with caplog.at_level(logging.DEBUG, logger="app.core.encryption"):
        _log_keyring_absence("read the master key", keyring.errors.NoKeyringError("none"))
    assert [r.levelno for r in caplog.records] == [logging.DEBUG]

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="app.core.encryption"):
        _log_keyring_absence("read the master key", keyring.errors.KeyringError("locked"))
    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_the_suite_never_writes_the_operators_real_key_backups():
    """A guard on the test harness itself.

    Mocking the keyring left _save_key_backups writing to DATA_DIR,
    CONFIG_DIR and ~/.msp_toolkit_key_backup, so simply running the suite
    replaced the operator's master key with a throwaway one — silently, since
    the replacement is wrapped under the same host passphrase and reads back
    fine. The next real start then adopts it and every stored credential
    fails with InvalidTag.
    """
    from pathlib import Path

    import app.core.encryption as enc

    real = {
        Path.home() / ".msp_toolkit_key_backup",
    }
    locations = set(enc._backup_locations())
    assert locations, "the autouse fixture must supply a redirected location"
    assert not (locations & real), f"the suite writes real key backups: {locations & real}"

    # Resolving a key must not create the real one either.
    before = (Path.home() / ".msp_toolkit_key_backup").exists()
    enc._get_or_create_master_key()
    after_mtime = None
    if before:
        after_mtime = (Path.home() / ".msp_toolkit_key_backup").stat().st_mtime
    enc._get_or_create_master_key()
    if before:
        assert (Path.home() / ".msp_toolkit_key_backup").stat().st_mtime == after_mtime
