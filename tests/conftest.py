"""Shared fixtures for the test suite."""

from __future__ import annotations

import base64
import os
from unittest.mock import patch

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_master_key_store(tmp_path_factory):
    """Session-scoped so higher-scoped fixtures are covered too.

    This has to outlive the per-test fixture below. pytest builds a
    module-scoped fixture *before* entering any function-scoped one, so a
    module fixture that renders a report — tests/test_report_golden.py does
    exactly that — ran with no patch active and wrote the operator's real key
    backups. Found by md5-diffing ~/.msp_toolkit_key_backup across the suite
    file by file.
    """
    key_dir = tmp_path_factory.mktemp("keybackups")
    with patch("app.core.encryption._backup_locations",
               return_value=[key_dir / ".master_key_backup"]):
        yield


@pytest.fixture(autouse=True)
def _mock_keyring(tmp_path_factory):
    """Isolate the master key: in-memory keyring AND redirected file backups.

    Mocking the keyring alone was not enough. Every successful key lookup ends
    in ``_save_key_backups``, and ``_backup_locations()`` reads DATA_DIR,
    CONFIG_DIR and ``Path.home()`` on each call — so a plain test run rewrote
    the operator's real ``~/.msp_toolkit_key_backup`` with a throwaway key.
    Verified by md5 before and after a single test file. Because that key is
    wrapped under the current host's passphrase it reads back cleanly, so
    nothing complains: the next real start simply adopts it and every stored
    credential fails to decrypt.

    Redirect the backup paths for the whole suite. ``_backup_locations`` is
    the function that produces them, so patching it cannot silently no-op the
    way patching a module attribute the module does not have did.
    """
    store: dict[tuple[str, str], str] = {}

    # Pre-seed a deterministic 256-bit key so encrypt/decrypt are reproducible
    test_key = os.urandom(32)
    b64_key = base64.urlsafe_b64encode(test_key).decode()
    store[("MSPToolkit", "master_encryption_key")] = b64_key

    def _get(service: str, key: str) -> str | None:
        return store.get((service, key))

    def _set(service: str, key: str, value: str) -> None:
        store[(service, key)] = value

    key_dir = tmp_path_factory.mktemp("keybackups")

    with patch("keyring.get_password", side_effect=_get), \
         patch("keyring.set_password", side_effect=_set), \
         patch("app.core.encryption._backup_locations",
               return_value=[key_dir / ".master_key_backup"]):
        # Clear the module-level cached key so each test gets a fresh lookup
        import app.core.encryption as enc
        enc._cached_key = None
        yield
        enc._cached_key = None


@pytest.fixture(autouse=True)
def _dispose_db_pool():
    """Terminate pooled connections after every test.

    Each test gets its own event loop and usually its own DB_PATH, so a pooled
    connection cannot be reused across tests anyway. Disposing explicitly stops
    aiosqlite's non-daemon worker threads: left running they accumulate over a
    suite this size and hang interpreter exit, which is precisely how CI got
    wedged once already.
    """
    yield
    from app.core.database import reset_pools_for_tests

    reset_pools_for_tests()
