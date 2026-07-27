"""Shared fixtures for the test suite."""

from __future__ import annotations

import base64
import os
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _mock_keyring():
    """Replace keyring with an in-memory dict so tests never touch the real OS keyring."""
    store: dict[tuple[str, str], str] = {}

    # Pre-seed a deterministic 256-bit key so encrypt/decrypt are reproducible
    test_key = os.urandom(32)
    b64_key = base64.urlsafe_b64encode(test_key).decode()
    store[("MSPToolkit", "master_encryption_key")] = b64_key

    def _get(service: str, key: str) -> str | None:
        return store.get((service, key))

    def _set(service: str, key: str, value: str) -> None:
        store[(service, key)] = value

    with patch("keyring.get_password", side_effect=_get), \
         patch("keyring.set_password", side_effect=_set):
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
