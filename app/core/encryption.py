"""AES-256-GCM encryption at rest for all customer data.

Master key is stored in the OS keyring (macOS Keychain / Windows Credential
Manager / Linux SecretService). All files are encrypted transparently — the
magic header allows mixed encrypted/plaintext states for seamless migration.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import keyring

log = logging.getLogger(__name__)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEYRING_SERVICE = "MSPToolkit"
_KEYRING_KEY = "master_encryption_key"
_MAGIC = b"MSPTK\x01"  # 6-byte header to identify encrypted files (v1, no AAD)
_MAGIC_V2 = b"MSPTK\x02"  # v2 header: includes AAD for integrity binding
_NONCE_LEN = 12  # 96-bit nonce for AES-GCM
_AAD = b"MSPToolkit-v2"  # Associated authenticated data — prevents ciphertext swapping

_cached_key: Optional[bytes] = None

# Operator-supplied key, in the style of the MSP_DATA_DIR / MSP_CONFIG_DIR
# overrides in config.py. This is the escape hatch from host-identity binding:
# _machine_passphrase() ties the file backups to hostname + machine-id, so a
# VM clone, a reimage or a restore-to-new-host — the documented DR procedure —
# leaves them unreadable. Point one of these at a key held in your secret
# manager and the box can be rebuilt from scratch.
_ENV_MASTER_KEY = "SYBR_MASTER_KEY"           # base64 key, directly
_ENV_MASTER_KEY_FILE = "SYBR_MASTER_KEY_FILE"  # path to a file holding one


class MasterKeyUnavailableError(Exception):
    """A key backup exists but could not be unwrapped on this host.

    Deliberately not a ToolkitError: this must never be mapped to an HTTP
    status and answered politely. It means the data on disk is encrypted with
    a key we cannot currently derive, and the only safe move is to refuse to
    start rather than mint a replacement and overwrite the evidence.
    """


def _backup_locations() -> list:
    """Return all locations where the master key backup should be stored."""
    from pathlib import Path

    from app.core.config import CONFIG_DIR, DATA_DIR
    return [
        DATA_DIR / ".master_key_backup",
        CONFIG_DIR / ".master_key_backup",
        Path.home() / ".msp_toolkit_key_backup",
    ]


def _machine_passphrase() -> str:
    """Derive a machine-specific passphrase for encrypting key backups."""
    import hashlib
    import platform
    import socket
    parts = [socket.gethostname(), platform.node()]
    # Try machine-id on Linux
    try:
        mid = Path("/etc/machine-id").read_text().strip()
        parts.append(mid)
    except Exception:
        pass
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _backup_is_readable(path: Path) -> bool:
    """Whether the backup at ``path`` unwraps with this host's passphrase."""
    return _read_one_backup(path) is not None


def _save_key_backups(b64_key: str, *, force: bool = False) -> None:
    """Save master key to multiple backup locations, encrypted with machine passphrase.

    A backup we cannot currently unwrap is never overwritten unless ``force``
    is set. That file may be the last copy of a key that is still recoverable
    — restore the old hostname or /etc/machine-id and it unwraps again — so
    writing a freshly minted key over it turns a recoverable state into
    permanent data loss. ``force=True`` is for the deliberate act of importing
    a known-good key, where replacing the stale blob is the whole point.
    """
    import json

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    passphrase = _machine_passphrase().encode()
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    wrap_key = kdf.derive(passphrase)
    nonce = os.urandom(12)
    aesgcm = AESGCM(wrap_key)
    ct = aesgcm.encrypt(nonce, b64_key.encode(), None)
    # Store salt + nonce + ciphertext as hex
    blob = json.dumps({"v": 2, "s": salt.hex(), "n": nonce.hex(), "ct": ct.hex()})

    for path in _backup_locations():
        try:
            if not force and path.exists() and not _backup_is_readable(path):
                log.error(
                    "Refusing to overwrite the unreadable key backup at %s — it may "
                    "still hold a recoverable key for this data. Restore the original "
                    "hostname/machine-id, or import the key deliberately.", path,
                )
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(blob)
            path.chmod(0o600)
        except Exception as e:
            log.warning("Failed to save key backup to %s: %s", path, e)


def _read_one_backup(path: Path) -> bytes | None:
    """Unwrap a single key backup, or None if absent/corrupt/wrong host."""
    import base64
    import json

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if data.get("v") == 2:
            # New encrypted format
            salt = bytes.fromhex(data["s"])
            nonce = bytes.fromhex(data["n"])
            ct = bytes.fromhex(data["ct"])
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
            wrap_key = kdf.derive(_machine_passphrase().encode())
            aesgcm = AESGCM(wrap_key)
            b64_key = aesgcm.decrypt(nonce, ct, None).decode()
            key = base64.urlsafe_b64decode(b64_key)
        else:
            # Legacy plaintext format
            key = base64.urlsafe_b64decode(data["key"])
        return key if len(key) == 32 else None
    except Exception as e:
        log.debug("Key backup at %s unreadable: %s", path, e)
        return None


def _try_restore_from_backup() -> bytes | None:
    """Try to restore master key from any backup location."""
    for path in _backup_locations():
        key = _read_one_backup(path)
        if key is not None:
            # Routine on a headless install — the backups are the primary
            # store there, not a fallback from a bad state.
            log.debug("Master key read from backup: %s", path)
            return key
    return None


def _unreadable_backups() -> list:
    """Backup files that exist but do not unwrap on this host.

    The difference between this being empty and non-empty is the difference
    between a first run (safe to mint a key) and a host whose identity changed
    under encrypted data (never safe to mint a key).
    """
    return [p for p in _backup_locations() if p.exists() and _read_one_backup(p) is None]


def _key_from_env() -> bytes | None:
    """Master key supplied by the operator, if any. Highest precedence."""
    import base64

    b64 = os.environ.get(_ENV_MASTER_KEY)
    src = _ENV_MASTER_KEY
    if not b64:
        key_file = os.environ.get(_ENV_MASTER_KEY_FILE)
        if not key_file:
            return None
        src = f"{_ENV_MASTER_KEY_FILE}={key_file}"
        try:
            b64 = Path(key_file).read_text().strip()
        except Exception as e:
            raise MasterKeyUnavailableError(
                f"{src} is set but the file could not be read: {e}"
            ) from e
    try:
        raw = base64.urlsafe_b64decode(b64.strip())
    except Exception as e:
        raise MasterKeyUnavailableError(f"{src} is not valid base64: {e}") from e
    if len(raw) != 32:
        raise MasterKeyUnavailableError(
            f"{src} decoded to {len(raw)} bytes, expected 32"
        )
    log.info("Master key taken from %s", src)
    return raw


def _log_keyring_absence(action: str, exc: Exception) -> None:
    """Log a keyring failure at a level that matches what it means.

    On a headless install there is no Secret Service provider, so every call
    raises and the file backups are the key's real home. Logging that at
    warning or error made four lines of alarm on every single startup for the
    designed behaviour — and the text is identical to the message from a real
    failure, so it trained the operator to read past exactly the thing that
    would matter. A keyring that exists and then misbehaves is different: that
    one is worth seeing.
    """
    if isinstance(exc, keyring.errors.NoKeyringError):
        log.debug("No OS keyring on this host, so could not %s; using file backups", action)
    else:
        log.warning("OS keyring present but failed to %s (%s)", action, exc)


def _get_or_create_master_key() -> bytes:
    """Get or create a 256-bit master encryption key from the OS keyring.

    Recovery chain:
    1. OS keyring (primary)
    2. Local file backups (3 locations: DATA_DIR, CONFIG_DIR, ~/.msp_toolkit_key_backup)
    3. Create new key ONLY if no backups exist (last resort)

    On every successful retrieval, all backups are updated.
    """
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    import base64

    # 0. Operator-supplied key wins over everything. This is what makes the
    #    install portable: nothing below survives a change of hostname or
    #    machine-id, and this does.
    from_env = _key_from_env()
    if from_env is not None:
        _cached_key = from_env
        return _cached_key

    # 1. Try OS keyring.
    #
    # Guarded, because keyring *raises* NoKeyringError when no Secret Service
    # provider is present — which is the normal state on a headless Linux box
    # and guaranteed under the systemd unit (system user, ProtectHome=yes, no
    # D-Bus session). Unguarded, that exception escaped and took the whole
    # process with it, and the file-backup recovery below — which exists for
    # exactly this case — was unreachable.
    try:
        stored = keyring.get_password(_KEYRING_SERVICE, _KEYRING_KEY)
    except Exception as e:
        _log_keyring_absence("read the master key", e)
        stored = None
    if stored:
        _cached_key = base64.urlsafe_b64decode(stored)
        # Ensure backups exist
        _save_key_backups(stored)
        return _cached_key

    # 2. No key in the keyring — try the file backups.
    restored = _try_restore_from_backup()
    if restored:
        _cached_key = restored
        b64 = base64.urlsafe_b64encode(restored).decode()
        # Put it back in the keyring if there is one to put it in.
        try:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY, b64)
            log.info("Master key restored to OS keyring from backup")
        except Exception as e:
            _log_keyring_absence("write the master key back", e)
        _save_key_backups(b64)
        return _cached_key

    # 3. Nothing recovered. Before minting, establish which of the two very
    #    different situations this is.
    #
    #    Backups present but unreadable means the host's identity changed under
    #    encrypted data — a VM clone, a reimage, a restore to a new host, or a
    #    plain `hostnamectl set-hostname`. Minting here would be silent,
    #    one-way data loss: every customer credential and audit archive on this
    #    box stays encrypted under a key nobody holds, and the old wrapped key
    #    gets overwritten by the new one. Refuse, and say exactly how to fix it.
    stale = _unreadable_backups()
    if stale:
        raise MasterKeyUnavailableError(
            "Master key backups exist but none could be unwrapped on this host: "
            + ", ".join(str(p) for p in stale)
            + ". The wrapping passphrase is derived from the hostname and "
            "/etc/machine-id, so this normally means one of those changed. "
            "Restore the previous hostname and /etc/machine-id, or supply the "
            f"key directly via {_ENV_MASTER_KEY} / {_ENV_MASTER_KEY_FILE}, or "
            "import it in Settings. Refusing to create a new key, which would "
            "make the existing encrypted data permanently unreadable."
        )

    # 4. No key and no backups anywhere — a genuine first run.
    log.warning("No master key found in the keyring or any backup — creating a NEW key")
    _cached_key = os.urandom(32)
    b64 = base64.urlsafe_b64encode(_cached_key).decode()
    try:
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY, b64)
    except Exception as e:
        # Same reasoning as the read above. The file backups are the key's
        # real home on a headless install; failing to *also* put it in a
        # keyring that does not exist must not lose the key we just made.
        _log_keyring_absence("store the new master key", e)
    _save_key_backups(b64)
    log.info("New master key created and backed up")

    return _cached_key


def verify_master_key_available() -> None:
    """Resolve the master key once at startup.

    Every encrypt/decrypt call resolves the key lazily, so without this a host
    whose identity changed surfaces the problem as a 500 in the middle of
    whichever request happened to touch encrypted data first — long after the
    point where an operator could act on it. Called from the app lifespan so
    the process fails fast and loudly instead.
    """
    _get_or_create_master_key()


def is_encrypted(data: bytes) -> bool:
    """Check if data starts with an encryption magic header (v1 or v2)."""
    return data[:len(_MAGIC)] == _MAGIC or data[:len(_MAGIC_V2)] == _MAGIC_V2


def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt data with AES-256-GCM + AAD. Returns MAGIC_V2 + nonce + ciphertext."""
    key = _get_or_create_master_key()
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, _AAD)
    return _MAGIC_V2 + nonce + ciphertext


def decrypt_bytes(data: bytes) -> bytes:
    """Decrypt data. Supports v2 (AAD), v1 (no AAD), and plaintext fallback."""
    if data[:len(_MAGIC_V2)] == _MAGIC_V2:
        # v2 format with AAD
        key = _get_or_create_master_key()
        nonce = data[len(_MAGIC_V2):len(_MAGIC_V2) + _NONCE_LEN]
        ciphertext = data[len(_MAGIC_V2) + _NONCE_LEN:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, _AAD)
    if data[:len(_MAGIC)] == _MAGIC:
        # v1 format without AAD (backward compat)
        key = _get_or_create_master_key()
        nonce = data[len(_MAGIC):len(_MAGIC) + _NONCE_LEN]
        ciphertext = data[len(_MAGIC) + _NONCE_LEN:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    return data  # plaintext fallback for migration


def encrypt_text(text: str, encoding: str = "utf-8") -> bytes:
    """Encrypt a string."""
    return encrypt_bytes(text.encode(encoding))


def decrypt_text(data: bytes, encoding: str = "utf-8") -> str:
    """Decrypt bytes to string. Handles plaintext fallback."""
    return decrypt_bytes(data).decode(encoding)


# ── File I/O helpers ─────────────────────────────────────────────────────────

def encrypted_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text encrypted to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_text(content, encoding))


def encrypted_read_text(path: Path, encoding: str = "utf-8") -> str:
    """Read text from an encrypted (or plaintext) file."""
    return decrypt_text(path.read_bytes(), encoding)


def encrypted_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes encrypted to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_bytes(data))


def encrypted_read_bytes(path: Path) -> bytes:
    """Read bytes from an encrypted (or plaintext) file."""
    return decrypt_bytes(path.read_bytes())


def encrypted_write_json(path: Path, data: dict) -> None:
    """Write a dict as encrypted JSON."""
    text = json.dumps(data, indent=2, ensure_ascii=False)
    encrypted_write_text(path, text)


def encrypted_read_json(path: Path) -> dict:
    """Read a dict from an encrypted (or plaintext) JSON file.

    Treats an empty file as an empty dict — the audit toolkit's
    ``load_app_settings`` calls this on first run when ``settings.json``
    has been created but never written to, and a JSONDecodeError on an
    empty file would crash anything that reads settings (in our smoke
    test this blocked every report generation against a fresh install).
    """
    text = encrypted_read_text(path)
    if not text.strip():
        return {}
    return json.loads(text)


# ── Migration ────────────────────────────────────────────────────────────────

def migrate_encrypt_directory(directory: Path) -> int:
    """Encrypt all plaintext files in a directory tree. Returns count."""
    count = 0
    if not directory.exists():
        return count
    for file in directory.rglob("*"):
        if not file.is_file():
            continue
        raw = file.read_bytes()
        if not is_encrypted(raw):
            file.write_bytes(encrypt_bytes(raw))
            count += 1
    return count


def export_master_key() -> str:
    """Return the master encryption key as a base64 string (for backup)."""
    import base64
    key = _get_or_create_master_key()
    return base64.urlsafe_b64encode(key).decode()


def import_master_key(b64_key: str) -> bool:
    """Validate and store a base64-encoded master key. Returns True on success.

    Order matters. This used to call keyring.set_password() first and adopt the
    key second, so on a headless host — where the systemd unit guarantees no
    Secret Service — NoKeyringError (a KeyringError subclass) aborted the whole
    function and returned False with nothing adopted. That silently broke the
    product's only recovery path, on exactly the installs that need it: the
    Settings "restore key" flow and the ZIP restore. Adopt the key and write
    the file backups first; the keyring is a bonus, not a precondition.
    """
    import base64
    global _cached_key
    try:
        raw = base64.urlsafe_b64decode(b64_key)
    except (ValueError, TypeError) as e:
        log.warning("import_master_key: base64 decode failed: %s", e)
        return False
    if len(raw) != 32:
        log.warning("import_master_key: decoded key has wrong length (%d, expected 32)", len(raw))
        return False

    _cached_key = raw
    # force=True: replacing a stale, unreadable blob is the point of an import.
    _save_key_backups(b64_key, force=True)
    try:
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY, b64_key)
    except Exception as e:
        _log_keyring_absence("store the imported master key", e)
    log.info("Master key imported and backed up")
    return True


def wrap_master_key(password: str) -> str:
    """Encrypt the master key with a user password for safe inclusion in backups.

    Uses PBKDF2 to derive a wrapping key from the password, then AES-256-GCM
    to encrypt the master key. Returns a base64-encoded bundle of
    salt + nonce + ciphertext.
    """
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    master_key = _get_or_create_master_key()
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=salt, iterations=1_000_000)
    wrapping_key = kdf.derive(password.encode("utf-8"))
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(wrapping_key)
    ciphertext = aesgcm.encrypt(nonce, master_key, None)
    return base64.urlsafe_b64encode(salt + nonce + ciphertext).decode()


def unwrap_master_key(wrapped: str, password: str) -> bool:
    """Decrypt and import a password-wrapped master key from a backup.

    Returns True on success, False if the password is wrong or data is invalid.
    """
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    from cryptography.exceptions import InvalidTag

    try:
        raw = base64.urlsafe_b64decode(wrapped)
        salt = raw[:16]
        nonce = raw[16:16 + _NONCE_LEN]
        ciphertext = raw[16 + _NONCE_LEN:]
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                         salt=salt, iterations=1_000_000)
        wrapping_key = kdf.derive(password.encode("utf-8"))
        aesgcm = AESGCM(wrapping_key)
        master_key = aesgcm.decrypt(nonce, ciphertext, None)
        if len(master_key) != 32:
            log.warning("unwrap_master_key: decrypted key has wrong length (%d, expected 32)", len(master_key))
            return False
        b64_key = base64.urlsafe_b64encode(master_key).decode()
        return import_master_key(b64_key)
    except InvalidTag:
        # Wrong password or tampered bundle — expected failure mode during restore.
        log.warning("unwrap_master_key: authentication tag mismatch (wrong password or tampered bundle)")
        return False
    except (ValueError, TypeError) as e:
        log.warning("unwrap_master_key: malformed input: %s", e)
        return False


def export_decrypted(source_path: Path, dest_path: Path) -> None:
    """Export an encrypted file as plaintext (for user download/IT-Glue)."""
    data = encrypted_read_bytes(source_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(data)
