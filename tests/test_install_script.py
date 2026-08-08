"""Production installer invariants which are too important for shell review alone."""

from __future__ import annotations

from pathlib import Path

INSTALLER = Path("scripts/install-cachyos.sh").read_text(encoding="utf-8")


def test_installer_creates_the_required_key_wrap_credential():
    assert "SECRET_DIR=/etc/sybr-hub-secrets" in INSTALLER
    assert 'if [[ ! -s "$WRAP_SECRET" ]]' in INSTALLER
    assert "secrets.token_urlsafe(48)" in INSTALLER
    assert 'chmod 600 "$WRAP_SECRET"' in INSTALLER


def test_installer_does_not_rotate_an_existing_wrap_secret():
    guard = INSTALLER.index('if [[ ! -s "$WRAP_SECRET" ]]')
    creation = INSTALLER.index("secrets.token_urlsafe(48)")
    end = INSTALLER.index("\nfi", creation)
    assert guard < creation < end
