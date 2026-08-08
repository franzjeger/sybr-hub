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


def test_installer_fetches_tags_so_the_deployed_version_resolves():
    # app/core/version.py derives the displayed version from `git describe
    # --tags` and silently falls back to __version__ when no tag is reachable.
    # Both the --depth 1 clone and the single-branch fetch omit tag refs, so
    # without an explicit tag fetch every deployment reported the hardcoded
    # fallback regardless of which release was actually running.
    assert "fetch --tags" in INSTALLER
