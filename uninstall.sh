#!/usr/bin/env bash
# Removes everything installed by install.sh: the app copy, the
# launcher, the icon, the .desktop entry, the Nautilus script, and the
# update checker (including its autostart entry). Nothing system-wide
# is touched — this only ever removes files under $HOME.

set -uo pipefail

APP_ID="org.loko.ImageEditor"
INSTALL_DIR="$HOME/.local/share/loko-image-editor"
LAUNCHER="$HOME/.local/bin/loko-image-editor"
DESKTOP_FILE="$HOME/.local/share/applications/${APP_ID}.desktop"
NAUTILUS_SCRIPT="$HOME/.local/share/nautilus/scripts/Modifier avec l'éditeur d'image"
AUTOSTART_FILE="$HOME/.config/autostart/${APP_ID}.updater.desktop"
STAMP_DIR="$HOME/.cache/loko-image-editor"
ICON_BASE="$HOME/.local/share/icons/hicolor"

removed=0
remove() {
    if [ -e "$1" ]; then
        rm -rf -- "$1"
        echo "Removed: $1"
        removed=1
    fi
}

remove "$INSTALL_DIR"
remove "$LAUNCHER"
remove "$DESKTOP_FILE"
remove "$NAUTILUS_SCRIPT"
remove "$AUTOSTART_FILE"
remove "$STAMP_DIR"

for size in 48 64 128 256 512; do
    remove "$ICON_BASE/${size}x${size}/apps/${APP_ID}.png"
done

if [ "$removed" -eq 0 ]; then
    echo "Nothing found to remove — it doesn't look like this was installed."
    exit 0
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi
if command -v gtk4-update-icon-cache >/dev/null 2>&1; then
    gtk4-update-icon-cache -f -t "$ICON_BASE" 2>/dev/null || true
elif command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$ICON_BASE" 2>/dev/null || true
fi

echo
echo "Done. Quick Image Editor is fully uninstalled (any window still open"
echo "right now stays open, but nothing will relaunch it)."
