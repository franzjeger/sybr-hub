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

# ── Service account and directories ───────────────────────────────────────────
log "Creating service account and directories"
id -u "$SVC_USER" &>/dev/null || useradd --system --home-dir "$PREFIX" --shell /usr/bin/nologin "$SVC_USER"
install -d -o "$SVC_USER" -g "$SVC_USER" -m 750 "$PREFIX" "$DATA_DIR" "$CONF_DIR"

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
# CachyOS ships Python 3.13; the project is CI-tested on 3.11 and 3.12. It is
# reported here rather than blocked — the test run below is the real check.
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
# PYTHON_KEYRING_BACKEND matters: there is no Secret Service under a system
# unit with ProtectHome=yes and no D-Bus session. The null backend returns None
# instead of raising, so the app's own file-backup key store is used. The
# master key then lives in $DATA_DIR / $CONF_DIR — both 0750, owned by the
# service user — rather than in an OS keyring.
log "Installing systemd unit"
sed -e "s#^Environment=SYBR_HUB_PORT=.*#Environment=SYBR_HUB_PORT=${PORT}#" \
    "$PREFIX/scripts/sybr-hub.service" > /etc/systemd/system/sybr-hub.service
grep -q PYTHON_KEYRING_BACKEND /etc/systemd/system/sybr-hub.service || \
    sed -i '/^Environment=MSP_CONFIG_DIR=/a Environment=PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring' \
        /etc/systemd/system/sybr-hub.service

systemctl daemon-reload
systemctl enable --now sybr-hub.service

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
