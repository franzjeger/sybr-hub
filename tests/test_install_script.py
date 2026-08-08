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
    # A single-branch fetch omits tag refs entirely.
    assert "fetch --tags" in INSTALLER


def test_installer_keeps_history_deep_enough_to_reach_a_tag():
    # Fetching the tag ref is not sufficient: `git describe` needs the tagged
    # commit to be reachable from HEAD. A --depth 1 checkout could only
    # describe a tag sitting exactly on HEAD, so the deployed version dropped
    # to the fallback on the first deploy after every release — and a shallow
    # repository stays shallow through an ordinary fetch, so an existing
    # install has to be deepened explicitly.
    assert "--depth 1" not in INSTALLER
    assert "--unshallow" in INSTALLER
