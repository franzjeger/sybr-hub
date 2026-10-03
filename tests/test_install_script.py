"""Production installer invariants which are too important for shell review alone."""

from __future__ import annotations

from pathlib import Path

INSTALLER = Path("scripts/install-cachyos.sh").read_text(encoding="utf-8")

# The commands alone, with comment lines dropped. An invariant phrased as "this
# flag must be absent" is otherwise broken by the comment that explains why it
# was removed — naming a flag in prose is not using it.
INSTALLER_COMMANDS = "\n".join(
    line for line in INSTALLER.splitlines() if not line.lstrip().startswith("#")
)


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


def test_installer_only_clones_a_new_release():
    assert 'git clone --branch "$BRANCH" "$REPO" "$PREFIX"' in INSTALLER_COMMANDS
    assert "git -C" not in INSTALLER_COMMANDS
    assert "reset --hard" not in INSTALLER_COMMANDS
    guard = INSTALLER.index('[[ ! -e "$PREFIX/.git"')
    assert guard < INSTALLER.index("pacman -Syu")


def test_installer_keeps_full_history_and_avoids_partial_arch_upgrades():
    assert "--depth" not in INSTALLER_COMMANDS
    assert "pacman -Sy " not in INSTALLER_COMMANDS
    assert "pacman -Syu --needed" in INSTALLER_COMMANDS
