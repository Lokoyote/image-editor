#!/usr/bin/env bash
# Quick Image Editor — one-shot installer.
#
# Downloads the app straight from GitHub and installs it as a plain
# standalone application (NOT as a GNOME Shell extension — no top-panel
# icon): app grid entry, Nautilus "Open With" + right-click script, and
# a background checker that offers to update it whenever a newer
# version is pushed to the repo.
#
# Usage:
#   bash <(curl -fsSL https://raw.githubusercontent.com/Lokoyote/image-editor/main/install.sh)
#
# Re-running this script (or its --update mode, wired up automatically
# below) is always safe.
#
# Everything is installed under $HOME — no sudo, except if you opt in
# to auto-installing missing system packages.

set -uo pipefail

REPO_OWNER="Lokoyote"
REPO_NAME="image-editor"
BRANCH="main"
REPO_URL="https://github.com/$REPO_OWNER/$REPO_NAME"
APP_ID="org.loko.ImageEditor"
EXT_UUID="image-editor@loko.gnome"

INSTALL_DIR="$HOME/.local/share/loko-image-editor"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/loko-image-editor"
STATE_DIR="$HOME/.cache/loko-image-editor"
AUTOSTART_DIR="$HOME/.config/autostart"
ICON_BASE="$HOME/.local/share/icons/hicolor"
APPS_DIR="$HOME/.local/share/applications"
NAUTILUS_SCRIPTS_DIR="$HOME/.local/share/nautilus/scripts"
DESKTOP_FILE="$APPS_DIR/${APP_ID}.desktop"
NAUTILUS_SCRIPT="$NAUTILUS_SCRIPTS_DIR/Modifier avec l'éditeur d'image"

MODE="install"
[ "${1:-}" = "--update" ] && MODE="update"

log() { echo "$@"; }

# ---------------------------------------------------------------------
# 1. Dependencies (install mode only — update mode assumes they're
#    already there since the app already ran before).
# ---------------------------------------------------------------------
check_dependencies() {
    local missing=()
    command -v python3 >/dev/null 2>&1 || missing+=("python3")
    python3 -c "import gi" >/dev/null 2>&1 || missing+=("python3-gi")
    python3 -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk" \
        >/dev/null 2>&1 || missing+=("gir1.2-gtk-4.0")
    command -v zenity >/dev/null 2>&1 || missing+=("zenity")
    if ! command -v git >/dev/null 2>&1 && ! command -v curl >/dev/null 2>&1; then
        missing+=("git-or-curl")
    fi

    [ ${#missing[@]} -eq 0 ] && return 0

    log "Missing dependencies: ${missing[*]}"
    if command -v apt-get >/dev/null 2>&1; then
        read -r -p "Install them now with apt (needs sudo)? [O/n] " reply
        case "$reply" in
            [nN]*) log "Continuing without them — the app may fail to start." ;;
            *)
                sudo apt-get update && sudo apt-get install -y \
                    python3-gi python3-gi-cairo gir1.2-gtk-4.0 git curl zenity libnotify-bin
                ;;
        esac
    else
        log "Please install the equivalent packages for your distribution (python3-gi / PyGObject, GTK4 typelib, git or curl, zenity) and re-run this script."
    fi
}

# ---------------------------------------------------------------------
# 2. Fetch the repository into a temp dir.
# ---------------------------------------------------------------------
fetch_source() {
    local dest="$1"
    rm -rf "$dest"
    mkdir -p "$dest"

    if command -v git >/dev/null 2>&1; then
        log "Downloading via git..."
        if git clone --depth 1 --branch "$BRANCH" "$REPO_URL.git" "$dest" >/dev/null 2>&1; then
            return 0
        fi
        log "git clone failed, falling back to a tarball download..."
    fi

    if command -v curl >/dev/null 2>&1; then
        local tmp_tar
        tmp_tar="$(mktemp)"
        if curl -fsSL "$REPO_URL/archive/refs/heads/$BRANCH.tar.gz" -o "$tmp_tar"; then
            tar -xzf "$tmp_tar" -C "$dest" --strip-components=1
            rm -f "$tmp_tar"
            return 0
        fi
        rm -f "$tmp_tar"
    fi

    log "Error: could not download the repository (need git or curl + network access)." >&2
    exit 1
}

# ---------------------------------------------------------------------
# 3. Ask GitHub what the latest commit on the branch is, so we can
#    track versions without relying on formal releases/tags.
# ---------------------------------------------------------------------
get_remote_sha() {
    command -v curl >/dev/null 2>&1 || { echo ""; return; }
    curl -fsSL -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/$REPO_OWNER/$REPO_NAME/commits/$BRANCH" 2>/dev/null \
        | grep -m1 '"sha"' | sed -E 's/.*"sha"[[:space:]]*:[[:space:]]*"([a-f0-9]+)".*/\1/'
}

# ---------------------------------------------------------------------
# 4. Deploy the app files (no extension.js / metadata.json — those
#    belong to the old top-bar-icon extension, which we deliberately
#    don't install here).
# ---------------------------------------------------------------------
deploy_app() {
    local src="$1"
    mkdir -p "$INSTALL_DIR"
    cp -f "$src/image-editor.py" "$INSTALL_DIR/"
    rm -rf "$INSTALL_DIR/icons" "$INSTALL_DIR/appicon"
    cp -r "$src/icons" "$INSTALL_DIR/icons"
    [ -d "$src/appicon" ] && cp -r "$src/appicon" "$INSTALL_DIR/appicon"
    chmod +x "$INSTALL_DIR/image-editor.py"
}

# ---------------------------------------------------------------------
# 5. Launcher on the PATH — also kicks off a throttled background
#    update check every time the app is opened.
# ---------------------------------------------------------------------
install_launcher() {
    mkdir -p "$BIN_DIR"
    cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
INSTALL_DIR="$INSTALL_DIR"
if [ -x "\$INSTALL_DIR/check-update.sh" ]; then
    nohup "\$INSTALL_DIR/check-update.sh" >/dev/null 2>&1 &
    disown 2>/dev/null || true
fi
exec python3 "\$INSTALL_DIR/image-editor.py" "\$@"
EOF
    chmod +x "$LAUNCHER"

    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) log "Note: $BIN_DIR isn't on your PATH in this shell — it usually is after logging out/in." ;;
    esac
}

# ---------------------------------------------------------------------
# 6. App icon.
# ---------------------------------------------------------------------
install_icon() {
    for size in 48 64 128 256 512; do
        local src="$INSTALL_DIR/appicon/${APP_ID}-${size}.png"
        if [ -f "$src" ]; then
            local dest_dir="$ICON_BASE/${size}x${size}/apps"
            mkdir -p "$dest_dir"
            cp -f "$src" "$dest_dir/${APP_ID}.png"
        fi
    done
    if command -v gtk4-update-icon-cache >/dev/null 2>&1; then
        gtk4-update-icon-cache -f -t "$ICON_BASE" 2>/dev/null || true
    elif command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t "$ICON_BASE" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------
# 7. .desktop entry — standalone launch + "Open With" for images.
# ---------------------------------------------------------------------
install_desktop_entry() {
    mkdir -p "$APPS_DIR"
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Quick Image Editor
Comment=Crop, annotate and touch up images quickly
Exec=$LAUNCHER %f
Icon=$APP_ID
Terminal=false
StartupWMClass=$APP_ID
Categories=Graphics;Photography;GTK;
MimeType=image/png;image/jpeg;image/bmp;image/gif;image/tiff;image/webp;
EOF
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APPS_DIR" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------
# 8. Nautilus right-click script.
# ---------------------------------------------------------------------
install_nautilus_script() {
    mkdir -p "$NAUTILUS_SCRIPTS_DIR"
    cat > "$NAUTILUS_SCRIPT" <<EOF
#!/usr/bin/env bash
# Nautilus script: right-click > Scripts. Opens every selected image;
# non-image files are skipped. Guards against Nautilus firing the
# script twice for one click (2s de-dupe window per file).
STAMP_DIR="\$HOME/.cache/loko-image-editor"
mkdir -p "\$STAMP_DIR"
opened=0
while IFS= read -r f; do
    [ -z "\$f" ] && continue
    mime="\$(file --mime-type -b "\$f" 2>/dev/null || true)"
    case "\$mime" in
        image/*)
            key="\$(printf '%s' "\$f" | cksum | cut -d' ' -f1)"
            stamp="\$STAMP_DIR/\$key.stamp"
            lock="\$STAMP_DIR/\$key.lock"
            got_lock=0
            for _ in 1 2 3 4 5 6 7 8 9 10; do
                if mkdir "\$lock" 2>/dev/null; then
                    got_lock=1
                    break
                fi
                sleep 0.1
            done
            if [ "\$got_lock" -eq 1 ]; then
                now=\$(date +%s)
                last=\$(cat "\$stamp" 2>/dev/null || echo 0)
                if [ \$((now - last)) -ge 2 ]; then
                    echo "\$now" > "\$stamp"
                    nohup "$LAUNCHER" "\$f" >/dev/null 2>&1 &
                    opened=1
                fi
                rmdir "\$lock" 2>/dev/null
            else
                nohup "$LAUNCHER" "\$f" >/dev/null 2>&1 &
                opened=1
            fi
            ;;
    esac
done <<< "\$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS"

if [ "\$opened" -eq 0 ] && command -v zenity >/dev/null 2>&1; then
    zenity --warning --text="Sélectionnez au moins une image." 2>/dev/null || true
fi
EOF
    chmod +x "$NAUTILUS_SCRIPT"
}

# ---------------------------------------------------------------------
# 9. Updater: check-update.sh (does the checking + prompting) and
#    update.sh (tiny wrapper always re-pulling the latest install.sh).
# ---------------------------------------------------------------------
install_check_update_script() {
    cat > "$INSTALL_DIR/check-update.sh" <<EOF
#!/usr/bin/env bash
# Checks GitHub for a newer commit on $BRANCH and, if found, asks
# (via zenity) whether to install it. Throttled to once every 6h;
# pass --force to bypass the throttle and any previously dismissed
# version.
set -uo pipefail

REPO_OWNER="$REPO_OWNER"
REPO_NAME="$REPO_NAME"
BRANCH="$BRANCH"
INSTALL_DIR="$INSTALL_DIR"
STATE_DIR="$STATE_DIR"
REF_FILE="\$INSTALL_DIR/.installed_ref"
LAST_CHECK_FILE="\$STATE_DIR/last_check"
DISMISSED_FILE="\$STATE_DIR/dismissed_ref"
MIN_INTERVAL=\$((6 * 3600))

mkdir -p "\$STATE_DIR"

FORCE=0
[ "\${1:-}" = "--force" ] && FORCE=1

now=\$(date +%s)
if [ "\$FORCE" -eq 0 ] && [ -f "\$LAST_CHECK_FILE" ]; then
    last=\$(cat "\$LAST_CHECK_FILE" 2>/dev/null || echo 0)
    if [ \$((now - last)) -lt \$MIN_INTERVAL ]; then
        exit 0
    fi
fi
echo "\$now" > "\$LAST_CHECK_FILE"

command -v curl >/dev/null 2>&1 || exit 0

remote_sha=\$(curl -fsSL -H "Accept: application/vnd.github+json" \\
    "https://api.github.com/repos/\$REPO_OWNER/\$REPO_NAME/commits/\$BRANCH" 2>/dev/null \\
    | grep -m1 '"sha"' | sed -E 's/.*"sha"[[:space:]]*:[[:space:]]*"([a-f0-9]+)".*/\\1/')

[ -z "\$remote_sha" ] && exit 0

installed_sha=\$(cat "\$REF_FILE" 2>/dev/null || echo "")
if [ -z "\$installed_sha" ]; then
    echo "\$remote_sha" > "\$REF_FILE"
    exit 0
fi
[ "\$remote_sha" = "\$installed_sha" ] && exit 0

dismissed=\$(cat "\$DISMISSED_FILE" 2>/dev/null || echo "")
if [ "\$FORCE" -eq 0 ] && [ "\$remote_sha" = "\$dismissed" ]; then
    exit 0
fi

if ! command -v zenity >/dev/null 2>&1; then
    command -v notify-send >/dev/null 2>&1 && \\
        notify-send "Quick Image Editor" "Une nouvelle version est disponible sur GitHub."
    exit 0
fi

choice_out=\$(zenity --question \\
    --title="Quick Image Editor" \\
    --text="Une nouvelle version de Quick Image Editor est disponible sur GitHub.\\n\\nVoulez-vous l'installer maintenant ?" \\
    --ok-label="Installer" \\
    --cancel-label="Plus tard" \\
    --extra-button="Ignorer cette version" 2>/dev/null)
rc=\$?

if [ \$rc -eq 0 ]; then
    "\$INSTALL_DIR/update.sh"
    command -v notify-send >/dev/null 2>&1 && \\
        notify-send "Quick Image Editor" "Mis à jour avec succès." || true
elif [ "\$choice_out" = "Ignorer cette version" ]; then
    echo "\$remote_sha" > "\$DISMISSED_FILE"
fi
exit 0
EOF
    chmod +x "$INSTALL_DIR/check-update.sh"
}

install_update_script() {
    cat > "$INSTALL_DIR/update.sh" <<EOF
#!/usr/bin/env bash
# Always re-pulls the latest install.sh from GitHub before running it
# in --update mode, so improvements to the updater itself apply too.
set -euo pipefail
curl -fsSL "https://raw.githubusercontent.com/$REPO_OWNER/$REPO_NAME/$BRANCH/install.sh" | bash -s -- --update
EOF
    chmod +x "$INSTALL_DIR/update.sh"
}

# ---------------------------------------------------------------------
# 10. Autostart entry: also check for updates once per login.
# ---------------------------------------------------------------------
install_autostart() {
    mkdir -p "$AUTOSTART_DIR"
    cat > "$AUTOSTART_DIR/${APP_ID}.updater.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Quick Image Editor — update check
Exec=$INSTALL_DIR/check-update.sh
X-GNOME-Autostart-Delay=30
NoDisplay=true
Terminal=false
EOF
}

# ---------------------------------------------------------------------
# 11. If the old top-bar extension is enabled, offer to turn it off —
#     install mode only, and only if it's actually there.
# ---------------------------------------------------------------------
maybe_disable_topbar_extension() {
    command -v gnome-extensions >/dev/null 2>&1 || return 0
    if gnome-extensions list --enabled 2>/dev/null | grep -qx "$EXT_UUID"; then
        echo
        echo "The '$EXT_UUID' GNOME Shell extension (top-panel icon) is currently enabled."
        read -r -p "Disable it now, since the standalone app replaces it? [O/n] " reply
        case "$reply" in
            [nN]*) ;;
            *) gnome-extensions disable "$EXT_UUID" 2>/dev/null && echo "Extension disabled." ;;
        esac
    fi
}

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
log "== Quick Image Editor — $([ "$MODE" = "update" ] && echo "update" || echo "installer") =="

[ "$MODE" = "install" ] && check_dependencies

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
fetch_source "$WORKDIR/src"

REMOTE_SHA="$(get_remote_sha)"

deploy_app "$WORKDIR/src"
[ -n "$REMOTE_SHA" ] && echo "$REMOTE_SHA" > "$INSTALL_DIR/.installed_ref"

install_launcher
install_icon
install_desktop_entry
install_nautilus_script
install_update_script
install_check_update_script
install_autostart

if [ "$MODE" = "install" ]; then
    maybe_disable_topbar_extension
    echo
    echo "Done! Quick Image Editor is installed as a standalone app:"
    echo "  - App grid: 'Quick Image Editor'"
    echo "  - Nautilus: right-click an image > Open With, or > Scripts > 'Modifier avec l'éditeur d'image'"
    echo "  - Terminal: loko-image-editor"
    echo
    echo "Updates are checked automatically (at login, and each time you open"
    echo "the app), and you'll be asked before anything is installed."
    echo "To check manually: $INSTALL_DIR/update.sh"
else
    echo "Update complete."
fi
