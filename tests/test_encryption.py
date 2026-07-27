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


def test_master_key_survives_a_keyring_that_raises(tmp_path, monkeypatch):
    """keyring raises NoKeyringError when no Secret Service provider exists —
    the normal state on a headless box, and guaranteed under the systemd unit
    (system user, ProtectHome=yes, no D-Bus session). That exception used to
    escape _get_or_create_master_key and take the process with it, leaving the
    file-backup recovery chain below it unreachable.
    """
    import keyring.errors

    import app.core.encryption as enc

    def _boom(*a, **k):
        raise keyring.errors.NoKeyringError("no backend")

    monkeypatch.setattr("keyring.get_password", _boom)
    monkeypatch.setattr("keyring.set_password", _boom)
    monkeypatch.setattr(enc, "_cached_key", None)
    monkeypatch.setattr(enc, "DATA_DIR", tmp_path / "data", raising=False)
    monkeypatch.setattr(enc, "CONFIG_DIR", tmp_path / "conf", raising=False)

    blob = enc.encrypt_text("hemmelig")
    assert blob.startswith(enc._MAGIC_V2)
    assert enc.decrypt_bytes(blob).decode() == "hemmelig"


def test_the_key_persists_across_a_restart_without_a_keyring(tmp_path, monkeypatch):
    """Second boot must recover the same key from the file backups, or every
    previously encrypted audit becomes unreadable."""
    import keyring.errors

    import app.core.encryption as enc

    def _boom(*a, **k):
        raise keyring.errors.NoKeyringError("no backend")

    monkeypatch.setattr("keyring.get_password", _boom)
    monkeypatch.setattr("keyring.set_password", _boom)
    monkeypatch.setattr(enc, "DATA_DIR", tmp_path / "data", raising=False)
    monkeypatch.setattr(enc, "CONFIG_DIR", tmp_path / "conf", raising=False)

    monkeypatch.setattr(enc, "_cached_key", None)
    blob = enc.encrypt_text("hemmelig")

    monkeypatch.setattr(enc, "_cached_key", None)   # simulate a restart
    assert enc.decrypt_bytes(blob).decode() == "hemmelig"
