#!/usr/bin/env bash
# Install Sybr HUB on CachyOS / Arch, behind Tailscale.
#
# Idempotent — safe to re-run to upgrade an existing install.
#
#   curl -fsSL https://raw.githubusercontent.com/franzjeger/sybr-hub/main/scripts/install-cachyos.sh | sudo bash
#
# Afterwards the app is reachable on your tailnet at
#   https://<this-host>.<tailnet>.ts.net/
# and bound to loopback only, so it is not exposed on any other interface.

set -euo pipefail

REPO="${SYBR_HUB_REPO:-https://github.com/franzjeger/sybr-hub}"
BRANCH="${SYBR_HUB_BRANCH:-main}"
PREFIX=/opt/sybr-hub
DATA_DIR=/var/lib/sybr-hub
CONF_DIR=/etc/sybr-hub
SECRET_DIR=/etc/sybr-hub-secrets
WRAP_SECRET="$SECRET_DIR/key-wrap.secret"
SVC_USER=sybrhub
PORT="${SYBR_HUB_PORT:-8099}"

log() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run with sudo"

# Piped from curl, so the working directory is the invoker's home — which the
# service user cannot enter. Anything run as $SVC_USER from here would fail on
# a directory it has no business being in. Every path below is absolute.
cd /

# ── System packages ───────────────────────────────────────────────────────────
# pango/cairo/gdk-pixbuf2 are WeasyPrint's runtime libraries. It fails on a
# missing .so at PDF time, not at pip install time, so leaving them out gives
# you an app that works until the first report.
log "Installing system packages"
pacman -Sy --needed --noconfirm git python python-pip pango cairo gdk-pixbuf2 libffi
# The first-run wizard and Exchange Online collection shell out to pwsh.
# powershell-bin lives in the AUR, so it needs an AUR helper; without it the
# wizard stops at [PwshInstall].
if ! command -v pwsh &>/dev/null; then
    for helper in paru yay; do
        if command -v $helper &>/dev/null; then
            sudo -u "${SUDO_USER:-nobody}" $helper -S --needed --noconfirm powershell-bin || true
            break
        fi
    done
fi
command -v pwsh &>/dev/null || echo "    WARNING: pwsh not found — install it with: paru -S powershell-bin"

# ── Service account and directories ───────────────────────────────────────────
log "Creating service account and directories"
id -u "$SVC_USER" &>/dev/null || useradd --system --home-dir "$PREFIX" --shell /usr/bin/nologin "$SVC_USER"
install -d -o "$SVC_USER" -g "$SVC_USER" -m 750 "$PREFIX" "$DATA_DIR" "$CONF_DIR"

# The local recovery copy of the encryption master key must survive a host
# rebuild without being derivable from public machine identifiers. Keep its
# independent wrapping secret root-owned and let systemd copy it into the
# service's private credential directory at start. Never rotate this file
# without first exporting the master key through the authenticated UI.
install -d -o root -g root -m 700 "$SECRET_DIR"
if [[ ! -s "$WRAP_SECRET" ]]; then
    WRAP_TMP="$(mktemp "$SECRET_DIR/.key-wrap.secret.XXXXXX")"
    python -c 'import secrets; print(secrets.token_urlsafe(48))' > "$WRAP_TMP"
    chown root:root "$WRAP_TMP"
    chmod 600 "$WRAP_TMP"
    mv -f "$WRAP_TMP" "$WRAP_SECRET"
fi
chown root:root "$WRAP_SECRET"
chmod 600 "$WRAP_SECRET"

# ── Source ────────────────────────────────────────────────────────────────────
if [[ -d "$PREFIX/.git" ]]; then
    log "Updating existing checkout"
    sudo -u "$SVC_USER" git -C "$PREFIX" fetch --depth 1 origin "$BRANCH"
    sudo -u "$SVC_USER" git -C "$PREFIX" reset --hard "origin/$BRANCH"
else
    log "Cloning $REPO ($BRANCH)"
    sudo -u "$SVC_USER" git clone --depth 1 --branch "$BRANCH" "$REPO" "$PREFIX"
fi

# ── Python environment ────────────────────────────────────────────────────────
# Arch/CachyOS ships whatever Python is newest (3.14 at time of writing).
# CI covers 3.11-3.14; the version is reported rather than blocked, since
# the test run below is the real check.
PYVER="$(python -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
log "Building virtualenv (Python $PYVER)"
[[ -x "$PREFIX/.venv/bin/python" ]] || sudo -u "$SVC_USER" python -m venv "$PREFIX/.venv"
sudo -u "$SVC_USER" "$PREFIX/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$SVC_USER" "$PREFIX/.venv/bin/pip" install --quiet -r "$PREFIX/requirements.txt"

# Run it *from* $PREFIX. pytest chdirs back to its start directory during
# teardown, so with the invoker's home as cwd the suite passes and then dies
# with PermissionError on the way out.
log "Running the test suite"
if (cd "$PREFIX" && sudo -u "$SVC_USER" "$PREFIX/.venv/bin/python" -m pytest -q -m "not slow"); then
    echo "    suite green on Python $PYVER"
else
    die "tests failed on Python $PYVER — install python312 from the AUR, then:
       sudo rm -rf $PREFIX/.venv && sudo -u $SVC_USER python3.12 -m venv $PREFIX/.venv
       and re-run this script"
fi

# ── systemd unit ──────────────────────────────────────────────────────────────
# There is no Secret Service under a system unit with ProtectHome=yes and no
# D-Bus session, so the app falls back to its own encrypted key/secret store.
# Both live under $DATA_DIR / $CONF_DIR (0750, owned by the service user)
# rather than in an OS keyring — back those two directories up.
log "Installing systemd unit"
sed -e "s#^Environment=SYBR_HUB_PORT=.*#Environment=SYBR_HUB_PORT=${PORT}#" \
    "$PREFIX/scripts/sybr-hub.service" > /etc/systemd/system/sybr-hub.service
# scripts/sybr-hub.service is the source of truth and already carries the
# correct MemoryDenyWriteExecute, HOME and hardening settings. The only thing
# to patch is removing a setting an *earlier* version of this script added:
# PYTHON_KEYRING_BACKEND=null does not raise, it discards, so every stored
# secret vanished at restart with no error. credentials.py now verifies its
# writes, which handles a keyring that raises properly; this setting is pure
# harm and must not survive an upgrade.
sed -i '/^Environment=PYTHON_KEYRING_BACKEND=/d' /etc/systemd/system/sybr-hub.service

# HOME must exist and be writable before pwsh starts, or it fails creating
# ~/.cache/powershell before it has even read its arguments.
install -d -o "$SVC_USER" -g "$SVC_USER" -m 750 "$DATA_DIR/home"

systemctl daemon-reload
systemctl enable sybr-hub.service
# restart, not `enable --now`: --now only *starts* a stopped unit, so on every
# upgrade of an already-running install the new code sat on disk while the old
# process kept serving. The script said "Sybr HUB is running" and it was — the
# previous version. restart also starts it if it is stopped, so this covers the
# first install too.
systemctl restart sybr-hub.service

# ── Tailscale ─────────────────────────────────────────────────────────────────
# `tailscale serve` terminates TLS with a real cert for the MagicDNS name and
# proxies to loopback, so the app is never bound to a public interface.
if command -v tailscale &>/dev/null; then
    log "Publishing on the tailnet"
    tailscale serve --bg --https 443 "http://127.0.0.1:${PORT}" || \
        echo "    'tailscale serve' failed — run it by hand once tailscaled is up"
    URL="https://$(tailscale status --json | python -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || echo '<host>.<tailnet>.ts.net')/"
else
    URL="http://127.0.0.1:${PORT}/  (tailscale not installed)"
fi

# ── Report ────────────────────────────────────────────────────────────────────
sleep 2
if systemctl is-active --quiet sybr-hub.service; then
    log "Sybr HUB is running"
    echo "    $URL"
    echo
    echo "    Open it and create the first admin account — until one exists,"
    echo "    every route except /api/auth/status and /api/auth/setup returns 401."
    echo
    echo "    logs:    journalctl -u sybr-hub -f"
    echo "    restart: systemctl restart sybr-hub"
else
    systemctl status sybr-hub.service --no-pager -l || true
    die "service failed to start — see the status output above"
fi
