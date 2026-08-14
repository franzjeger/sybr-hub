"""AES-256-GCM encryption at rest for all customer data.

Master key is stored in the OS keyring (macOS Keychain / Windows Credential
Manager / Linux SecretService). All files are encrypted transparently — the
magic header allows mixed encrypted/plaintext states for seamless migration.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from contextlib import suppress
from pathlib import Path

import keyring
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)

_KEYRING_SERVICE = "MSPToolkit"
_KEYRING_KEY = "master_encryption_key"
_MAGIC = b"MSPTK\x01"  # 6-byte header to identify encrypted files (v1, no AAD)
_MAGIC_V2 = b"MSPTK\x02"  # v2 header: includes AAD for integrity binding
_NONCE_LEN = 12  # 96-bit nonce for AES-GCM
_AAD = b"MSPToolkit-v2"  # Associated authenticated data — prevents ciphertext swapping

_cached_key: bytes | None = None

# Operator-supplied key, in the style of the MSP_DATA_DIR / MSP_CONFIG_DIR
# overrides in config.py. This is the escape hatch from host-identity binding:
# _machine_passphrase() ties the file backups to hostname + machine-id, so a
# VM clone, a reimage or a restore-to-new-host — the documented DR procedure —
# leaves them unreadable. Point one of these at a key held in your secret
# manager and the box can be rebuilt from scratch.
_ENV_MASTER_KEY = "SYBR_MASTER_KEY"           # base64 key, directly
_ENV_MASTER_KEY_FILE = "SYBR_MASTER_KEY_FILE"  # path to a file holding one
_ENV_KEY_WRAP_SECRET = "SYBR_KEY_WRAP_SECRET"
_ENV_KEY_WRAP_SECRET_FILE = "SYBR_KEY_WRAP_SECRET_FILE"
_BACKUP_AAD_V3 = b"Sybr-HUB-master-key-backup-v3"
_MIN_WRAP_SECRET_BYTES = 32


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
    """Derive the legacy v2 wrapping input from public machine identity.

    This is retained solely to read and migrate existing backups. Hostname and
    machine-id are not secrets, so v2 prevents accidental disclosure but does
    not provide meaningful protection to an attacker who can copy the file.
    """
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


def _key_wrap_secret() -> bytes | None:
    """Return an operator-managed secret used to wrap local key backups.

    The file form is preferred for services because it avoids placing the
    secret directly in the unit definition. A configured-but-unreadable or
    weak secret is an error: silently falling back to public machine identity
    would create backups with much weaker protection than the operator asked
    for.
    """
    value = os.environ.get(_ENV_KEY_WRAP_SECRET)
    source = _ENV_KEY_WRAP_SECRET
    if value is not None:
        secret = value.encode("utf-8")
    else:
        secret_file = os.environ.get(_ENV_KEY_WRAP_SECRET_FILE)
        if not secret_file:
            return None
        source = f"{_ENV_KEY_WRAP_SECRET_FILE}={secret_file}"
        try:
            secret = Path(secret_file).read_bytes().strip()
        except Exception as e:
            raise MasterKeyUnavailableError(
                f"{source} is set but the key-wrapping secret could not be read: {e}"
            ) from e

    if len(secret) < _MIN_WRAP_SECRET_BYTES:
        raise MasterKeyUnavailableError(
            f"{source} must contain at least {_MIN_WRAP_SECRET_BYTES} bytes"
        )
    return secret


def _atomic_private_write(path: Path, data: bytes) -> None:
    """Atomically replace ``path`` with a private, fully flushed file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        path.chmod(0o600)
    except Exception:
        if fd >= 0:
            os.close(fd)
        tmp_path.unlink(missing_ok=True)
        raise


def _backup_is_readable(path: Path) -> bool:
    """Whether the backup at ``path`` unwraps with this host's passphrase."""
    return _read_one_backup(path) is not None


def _save_key_backups(b64_key: str, *, force: bool = False) -> None:
    """Save the master key to multiple encrypted backup locations.

    A backup we cannot currently unwrap is never overwritten unless ``force``
    is set. That file may be the last copy of a key that is still recoverable
    — restore the old hostname or /etc/machine-id and it unwraps again — so
    writing a freshly minted key over it turns a recoverable state into
    permanent data loss. ``force=True`` is for the deliberate act of importing
    a known-good key, where replacing the stale blob is the whole point.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt = os.urandom(16)
    secret = _key_wrap_secret()
    if secret is not None:
        version = 3
        iterations = 1_000_000
        aad = _BACKUP_AAD_V3
        wrapping_input = secret
    else:
        # Backward-compatible degraded mode for desktop/headless installs that
        # have not configured an external secret yet. Be explicit: machine-id
        # is public metadata, not a cryptographic secret.
        version = 2
        iterations = 100_000
        aad = None
        wrapping_input = _machine_passphrase().encode()
        log.warning(
            "Master-key file backups use legacy machine-identity wrapping, which "
            "does not protect a copied backup. Configure %s (preferred) or %s "
            "to migrate them to password-protected v3 backups.",
            _ENV_KEY_WRAP_SECRET_FILE,
            _ENV_KEY_WRAP_SECRET,
        )

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations,
    )
    wrap_key = kdf.derive(wrapping_input)
    nonce = os.urandom(12)
    aesgcm = AESGCM(wrap_key)
    ct = aesgcm.encrypt(nonce, b64_key.encode(), aad)
    blob_data = {
        "v": version,
        "s": salt.hex(),
        "n": nonce.hex(),
        "ct": ct.hex(),
    }
    if version == 3:
        blob_data.update({"kdf": "pbkdf2-sha256", "i": iterations})
    blob = json.dumps(blob_data, separators=(",", ":")).encode("utf-8")

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
            _atomic_private_write(path, blob)
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
        version = data.get("v")
        if version in (2, 3):
            salt = bytes.fromhex(data["s"])
            nonce = bytes.fromhex(data["n"])
            ct = bytes.fromhex(data["ct"])
            if version == 3:
                secret = _key_wrap_secret()
                if secret is None:
                    return None
                if data.get("kdf") != "pbkdf2-sha256" or data.get("i") != 1_000_000:
                    return None
                wrapping_input = secret
                iterations = 1_000_000
                aad = _BACKUP_AAD_V3
            else:
                wrapping_input = _machine_passphrase().encode()
                iterations = 100_000
                aad = None
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations,
            )
            wrap_key = kdf.derive(wrapping_input)
            aesgcm = AESGCM(wrap_key)
            b64_key = aesgcm.decrypt(nonce, ct, aad).decode()
            key = base64.urlsafe_b64decode(b64_key)
        else:
            # Legacy plaintext format
            key = base64.urlsafe_b64decode(data["key"])
        return key if len(key) == 32 else None
    except MasterKeyUnavailableError:
        raise
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
        has_v3 = False
        for path in stale:
            with suppress(Exception):
                has_v3 = has_v3 or json.loads(path.read_text()).get("v") == 3
        recovery = (
            f"Configure the original {_ENV_KEY_WRAP_SECRET_FILE} / "
            f"{_ENV_KEY_WRAP_SECRET}, or supply the key directly via "
            f"{_ENV_MASTER_KEY} / {_ENV_MASTER_KEY_FILE}"
            if has_v3
            else
            "Restore the previous hostname and /etc/machine-id, or supply the "
            f"key directly via {_ENV_MASTER_KEY} / {_ENV_MASTER_KEY_FILE}"
        )
        raise MasterKeyUnavailableError(
            "Master key backups exist but none could be unwrapped on this host: "
            + ", ".join(str(p) for p in stale)
            + ". " + recovery + ", or import it in Settings. Refusing to create "
            "a new key, which would "
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
    """Write text encrypted to disk.

    Atomic: a crash mid-write leaves the previous file intact rather than a
    half-written one. This is what every settings and customer-config write
    goes through, and a torn settings.json corrupts the whole install.
    """
    _atomic_private_write(path, encrypt_text(content, encoding))


def encrypted_read_text(path: Path, encoding: str = "utf-8") -> str:
    """Read text from an encrypted (or plaintext) file."""
    return decrypt_text(path.read_bytes(), encoding)


def encrypted_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes encrypted to disk (atomic — see encrypted_write_text)."""
    _atomic_private_write(path, encrypt_bytes(data))


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
            # Atomic: this rewrites a customer file in place, and a crash mid-
            # migration must not leave a half-written, non-decryptable file.
            _atomic_private_write(file, encrypt_bytes(raw))
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

    # Preserve any backup that still unwraps here before overwriting it.
    # force=True is needed — replacing a stale blob is the point of an import —
    # but "decodes to 32 bytes" is not evidence that this is the *right* key,
    # and on a headless install these files are the key's only home. A
    # mistyped or wrong-install key would otherwise be accepted silently and
    # take the real one with it, leaving nothing for the startup check to
    # notice because the new blob wraps cleanly under this host's passphrase.
    for path in _backup_locations():
        if path.exists() and _backup_is_readable(path):
            # Never clobber an existing .prev. Retrying with another candidate
            # is the natural response to a bad import, and a second attempt
            # would otherwise overwrite the preserved original with the first
            # wrong key — leaving the real one in none of the files. Written
            # as a sibling name rather than with_suffix(), which on a dotfile
            # like ".master_key_backup" treats the whole name as a suffix.
            prev = path.parent / (path.name + ".prev")
            if prev.exists():
                log.info("Keeping the earlier preserved key at %s", prev)
                continue
            try:
                _atomic_private_write(prev, path.read_bytes())
                log.info("Existing key backup preserved at %s", prev)
            except Exception as e:
                # Refuse rather than proceed: the next step overwrites this
                # file, and without the copy that is one-way.
                log.error("Could not preserve existing key backup %s: %s", path, e)
                raise MasterKeyUnavailableError(
                    f"Refusing to import: the existing key backup at {path} could "
                    f"not be preserved first ({e})."
                ) from e

    _cached_key = raw
    _save_key_backups(b64_key, force=True)
    try:
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY, b64_key)
    except Exception as e:
        _log_keyring_absence("store the imported master key", e)
    log.info("Master key imported and backed up")
    return True


def unwrap_master_key_to_bytes(wrapped: str, password: str) -> bytes | None:
    """Decrypt a password-wrapped master key and return the raw 32 bytes.

    Unlike unwrap_master_key, this does NOT import the key — it only validates
    the password and returns the material, so a restore can check the key while
    staging and adopt it only at the atomic commit (SR-003). Returns None on a
    wrong password or malformed bundle.
    """
    import base64

    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    try:
        raw = base64.urlsafe_b64decode(wrapped)
        salt = raw[:16]
        nonce = raw[16:16 + _NONCE_LEN]
        ciphertext = raw[16 + _NONCE_LEN:]
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                         salt=salt, iterations=1_000_000)
        wrapping_key = kdf.derive(password.encode("utf-8"))
        master_key = AESGCM(wrapping_key).decrypt(nonce, ciphertext, None)
        return master_key if len(master_key) == 32 else None
    except InvalidTag:
        log.warning("unwrap_master_key_to_bytes: wrong password or tampered bundle")
        return None
    except (ValueError, TypeError) as e:
        log.warning("unwrap_master_key_to_bytes: malformed input: %s", e)
        return None


def manifest_mac(payload: bytes, key: bytes | None = None) -> str:
    """HMAC-SHA256 of a backup manifest, keyed by the master key.

    Authenticates the manifest (and, through it, the per-file hashes it lists)
    so a restore can detect a manifest that was edited to smuggle in a swapped
    or truncated file. Only a holder of the master key can forge it. *key* lets
    the caller pass the key it already has (e.g. one unwrapped from the backup
    but not yet imported)."""
    import hashlib
    import hmac

    k = key if key is not None else _get_or_create_master_key()
    return hmac.new(k, payload, hashlib.sha256).hexdigest()


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

    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

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
