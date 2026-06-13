#!/bin/bash
#
# Install (or reinstall) the Vox Biblios poller as a per-user launchd agent.
# Idempotent: re-running re-renders the plist and reloads the service.
#
# Usage:
#   poller/install.sh            # install + start
#   poller/install.sh uninstall  # stop + remove
#
set -euo pipefail

LABEL="com.voxbiblios.poller"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

# launchd agents get no TCC consent, so a script under a protected folder
# (~/Desktop, ~/Documents, ~/Downloads) hangs at startup when the interpreter
# tries to read it. Copy the self-contained poller to a non-protected location
# and run it from there. (It only needs the stdlib, ~/.config, and the
# globally installed `vox-biblios` binary — none of which live under Desktop.)
INSTALL_DIR="$HOME/.local/share/vox-biblios"
INSTALLED_SCRIPT="$INSTALL_DIR/voxbiblios_poller.py"

uninstall() {
    echo "Stopping and removing $LABEL …"
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST_DEST" "$INSTALLED_SCRIPT"
    echo "Removed $PLIST_DEST and $INSTALLED_SCRIPT"
}

if [[ "${1:-}" == "uninstall" ]]; then
    uninstall
    exit 0
fi

# Resolve a Python 3 interpreter (only the stdlib is needed).
PYTHON="$(command -v python3 || true)"
if [[ -z "$PYTHON" ]]; then
    echo "error: python3 not found on PATH" >&2
    exit 1
fi

# Sanity-check that the token the poller needs is reachable.
CONFIG_ENV="$HOME/.config/vox-biblios/config.env"
if ! { [[ -n "${CONTROL_PLANE_TOKEN:-}" ]] || grep -q '^[[:space:]]*\(export[[:space:]]\+\)\?CONTROL_PLANE_TOKEN=' "$CONFIG_ENV" 2>/dev/null; }; then
    echo "warning: CONTROL_PLANE_TOKEN not found in env or $CONFIG_ENV" >&2
    echo "         the poller will exit until it is set." >&2
fi

LOG="$HOME/Library/Logs/voxbiblios-poller.log"
ERR="$HOME/Library/Logs/voxbiblios-poller.err"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs" "$INSTALL_DIR"

# Copy the poller out of the (possibly TCC-protected) repo into a stable location.
cp "$SCRIPT_DIR/voxbiblios_poller.py" "$INSTALLED_SCRIPT"
echo "Installed poller to $INSTALLED_SCRIPT"

sed -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__SCRIPT__|$INSTALLED_SCRIPT|g" \
    -e "s|__WORKDIR__|$INSTALL_DIR|g" \
    -e "s|__LOG__|$LOG|g" \
    -e "s|__ERR__|$ERR|g" \
    "$SCRIPT_DIR/com.voxbiblios.poller.plist.template" > "$PLIST_DEST"

echo "Wrote $PLIST_DEST"

# Reload cleanly (bootout is a no-op if not loaded). The short sleep lets an
# existing instance fully unload before bootstrap, avoiding a load race.
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
sleep 2
launchctl bootstrap "$DOMAIN" "$PLIST_DEST"
launchctl enable "$DOMAIN/$LABEL"
# RunAtLoad does not reliably fire when bootstrapped from an SSH session, so
# start the service explicitly.
launchctl kickstart "$DOMAIN/$LABEL" 2>/dev/null || true

echo "Loaded $LABEL."
echo "  logs:   $LOG"
echo "  errors: $ERR"
echo "  status: launchctl print $DOMAIN/$LABEL | grep state"
echo "  stop:   poller/install.sh uninstall"
