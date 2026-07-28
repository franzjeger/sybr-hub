"""Secure credential storage using OS keyring + local config JSON."""

from __future__ import annotations

import json
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

import keyring

from app.core.config import DATA_DIR

log = logging.getLogger(__name__)

_SERVICE = "MSPToolkit"

# Where secrets go when there is no OS keyring. This is the normal state on a
# headless Linux host: no Secret Service provider, and none at all under the
# systemd unit, which runs as a system user with ProtectHome=yes and no D-Bus
# session. Unguarded, keyring *raises* there — which is how customer setup
# failed at "Generating self-signed certificate" with NoKeyringError.
#
# The file is written through the same AES-GCM layer as everything else in
# MSP_DATA_DIR, so these are encrypted at rest under the master key rather
# than sitting in plaintext JSON.
_FALLBACK_PATH = DATA_DIR / "secrets.enc"


# ── Keyring helpers ───────────────────────────────────────────────────────────

def _key(tenant_id: str, name: str) -> str:
    return f"{tenant_id}:{name}"


def _fallback_load() -> dict[str, str]:
    from app.core.encryption import encrypted_read_json

    if not _FALLBACK_PATH.exists():
        return {}
    try:
        return encrypted_read_json(_FALLBACK_PATH) or {}
    except Exception as e:
        log.error("Could not read the secret fallback store: %s", e)
        return {}


def _fallback_save(data: dict[str, str]) -> None:
    from app.core.encryption import encrypted_write_json

    _FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    encrypted_write_json(_FALLBACK_PATH, data)
    try:
        os.chmod(_FALLBACK_PATH, 0o600)
    except OSError:
        pass


def _keyring_stored(k: str, value: str) -> bool:
    """Write to the OS keyring and confirm the value is actually retrievable.

    Trusting set_password to raise on failure is not enough. keyring's *null*
    backend accepts writes and discards them silently, so a store looks like
    it worked and the secret is gone at the next restart — no exception, no
    log line, nothing until an audit fails to authenticate. The installer
    shipped exactly that (PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring,
    added to dodge NoKeyringError), which quietly dropped every client secret
    and certificate password.

    Reading it back costs one call and covers the silent case as well as the
    loud one, so the fallback engages for any keyring that does not actually
    persist — not just the ones that admit it.
    """
    try:
        keyring.set_password(_SERVICE, k, value)
        return keyring.get_password(_SERVICE, k) == value
    except Exception as e:
        log.warning("OS keyring unavailable (%s) — using %s", e, _FALLBACK_PATH.name)
        return False


def store_secret(tenant_id: str, name: str, value: str) -> None:
    k = _key(tenant_id, name)
    if not _keyring_stored(k, value):
        log.info("Storing secret %r in the encrypted fallback store", name)
        data = _fallback_load()
        data[k] = value
        _fallback_save(data)
    _secret_cache[k] = value


_secret_cache: dict[str, Optional[str]] = {}


def get_secret(tenant_id: str, name: str) -> Optional[str]:
    k = _key(tenant_id, name)
    if k in _secret_cache and _secret_cache[k] is not None:
        return _secret_cache[k]

    try:
        val = keyring.get_password(_SERVICE, k)
    except Exception as e:
        log.debug("OS keyring unavailable (%s) — reading from fallback store", e)
        val = None
    if val is None:
        # Also covers the case where a keyring exists but the secret was
        # written before one did, so the fallback is the only copy.
        val = _fallback_load().get(k)

    if val is not None:
        _secret_cache[k] = val
    else:
        _secret_cache.pop(k, None)
    return val


def delete_secret(tenant_id: str, name: str) -> None:
    k = _key(tenant_id, name)
    _secret_cache.pop(k, None)
    try:
        keyring.delete_password(_SERVICE, k)
    except Exception:
        # Includes PasswordDeleteError (not stored) and NoKeyringError.
        pass
    data = _fallback_load()
    if data.pop(k, None) is not None:
        _fallback_save(data)


def delete_all_secrets(tenant_id: str) -> None:
    for name in ("client_secret", "cert_password"):
        delete_secret(tenant_id, name)


def clear_secret_cache() -> None:
    """Clear the in-memory secret cache (e.g. after renew)."""
    _secret_cache.clear()


# ── Config file helpers ───────────────────────────────────────────────────────

_DEFAULT_CONFIG_PATH = DATA_DIR / "audit_config.json"
_LEGACY_CONFIG_PATH = Path("audit_config.json")


def config_path() -> Path:
    return _DEFAULT_CONFIG_PATH


def config_exists() -> bool:
    if _DEFAULT_CONFIG_PATH.exists():
        return True
    if _LEGACY_CONFIG_PATH.exists():
        _migrate_legacy_file(_LEGACY_CONFIG_PATH, _DEFAULT_CONFIG_PATH)
        return True
    return False


def load_config() -> Optional[dict]:
    if not _DEFAULT_CONFIG_PATH.exists() and _LEGACY_CONFIG_PATH.exists():
        _migrate_legacy_file(_LEGACY_CONFIG_PATH, _DEFAULT_CONFIG_PATH)
    if not _DEFAULT_CONFIG_PATH.exists():
        return None
    from app.core.encryption import encrypted_read_json
    return encrypted_read_json(_DEFAULT_CONFIG_PATH)


def save_config(data: dict) -> None:
    from app.core.encryption import encrypted_write_json
    encrypted_write_json(_DEFAULT_CONFIG_PATH, data)


def delete_config() -> None:
    if _DEFAULT_CONFIG_PATH.exists():
        _DEFAULT_CONFIG_PATH.unlink()


# ── Cert file helpers ─────────────────────────────────────────────────────────

_DEFAULT_CERT_PATH = DATA_DIR / "audit_cert.pfx"
_LEGACY_CERT_PATH = Path("audit_cert.pfx")


def cert_path() -> Path:
    return _DEFAULT_CERT_PATH


def cert_exists() -> bool:
    if _DEFAULT_CERT_PATH.exists():
        return True
    if _LEGACY_CERT_PATH.exists():
        _migrate_legacy_file(_LEGACY_CERT_PATH, _DEFAULT_CERT_PATH)
        return True
    return False


def save_cert(pfx_bytes: bytes) -> None:
    from app.core.encryption import encrypted_write_bytes
    encrypted_write_bytes(_DEFAULT_CERT_PATH, pfx_bytes)


def load_cert_bytes() -> Optional[bytes]:
    if not _DEFAULT_CERT_PATH.exists() and _LEGACY_CERT_PATH.exists():
        _migrate_legacy_file(_LEGACY_CERT_PATH, _DEFAULT_CERT_PATH)
    if not _DEFAULT_CERT_PATH.exists():
        return None
    from app.core.encryption import encrypted_read_bytes
    return encrypted_read_bytes(_DEFAULT_CERT_PATH)


def delete_cert() -> None:
    if _DEFAULT_CERT_PATH.exists():
        _DEFAULT_CERT_PATH.unlink()


# ── Combined wipe (for "new customer" or "renew") ────────────────────────────

def wipe_customer(tenant_id: str) -> None:
    delete_all_secrets(tenant_id)
    delete_config()
    delete_cert()


# ── Legacy migration ─────────────────────────────────────────────────────────

def _migrate_legacy_file(src: Path, dst: Path) -> None:
    """Move a file from the old CWD-relative path to the new platformdirs path."""
    import shutil
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


# ── Password generation ───────────────────────────────────────────────────────

def generate_cert_password() -> str:
    """Generate a strong random password for PFX encryption."""
    return secrets.token_urlsafe(32)


# ── GDAP / Partner Center config ─────────────────────────────────────────────

_GDAP_CONFIG_PATH = DATA_DIR / "gdap_config.json"


def load_gdap_config() -> Optional[dict]:
    """Load the encrypted GDAP partner configuration."""
    if not _GDAP_CONFIG_PATH.exists():
        return None
    from app.core.encryption import encrypted_read_json
    return encrypted_read_json(_GDAP_CONFIG_PATH)


def save_gdap_config(data: dict) -> None:
    """Persist the GDAP partner configuration (encrypted)."""
    from app.core.encryption import encrypted_write_json
    encrypted_write_json(_GDAP_CONFIG_PATH, data)


def gdap_configured() -> bool:
    """Return True if GDAP partner credentials are fully configured."""
    return _GDAP_CONFIG_PATH.exists() and bool(get_secret("gdap", "partner_client_secret"))
