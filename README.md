# <img width="48" height="48" alt="org loko ImageEditor-48" src="https://github.com/user-attachments/assets/144b3512-fb26-49bc-a15c-bb86934c222f" /> Quick Image Editor

![Python](https://img.shields.io/badge/python-3-3776AB)
![License](https://img.shields.io/badge/license-GPL--3.0-blue)

**A lightweight, no-fuss image editor for GNOME.**

Crop · Flip · Rotate · Annotate · Blur/Pixelate · Layers · Text

Sometimes you don't need GIMP — you need to blur a phone number in a
screenshot, draw an arrow at something, or crop a photo before sending it.
Quick Image Editor is a small GTK4 app that does exactly that, installed
as a normal standalone application with a right-click shortcut in Nautilus.

![Screenshot](https://github.com/Lokoyote/image-editor/blob/main/image-editor-screenshot.png?raw=true "image-editor screenshot")

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Updating](#updating)
- [Alternative: GNOME Shell panel icon](#alternative-gnome-shell-panel-icon)
- [Usage](#usage)
- [Tools](#tools)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Autosave & Crash Recovery](#autosave--crash-recovery)
- [Localization](#localization)
- [Troubleshooting](#troubleshooting)
- [Uninstalling](#uninstalling)
- [Contributing](#contributing)
- [License](#license)

## Features

- Crop, flip horizontal/vertical, rotate 90°
- Arrows, lines, rectangles, circles, polygons, text
  - Adjustable stroke width — down to **0** for no border at all
  - Optional fill / background color for shapes and text
- Blur / pixelate an area, with adjustable intensity
- Stack any number of images as layers — move, resize, adjust opacity
- Keep a simple object hierarchy in the side panel: base image, image layers, and drawn objects/text are listed separately
- Resize the canvas independently of the base image (with anchor point)
- Undo/redo, zoom, copy/paste through the system clipboard
- Tabs: multiple images open in a single window
- Autosave with crash recovery
- Single-instance app: re-launching brings the existing window forward
  instead of opening a duplicate
- Icon tooltips localized into French, English, Spanish, German, Italian
  and Portuguese based on your system locale

## Installation

Run this one-liner — it downloads the app straight from this repo and
sets everything up:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Lokoyote/image-editor/main/install.sh)
```

This installs Quick Image Editor as a **standalone application** — no
GNOME Shell extension, no top-panel icon. You get:

- an entry named "Quick Image Editor" in the applications grid, with the
  proper app icon
- right-click integration in Nautilus: it shows up in **Open With** for
  image files, and adds a one-click **Scripts ▸ Modifier avec l'éditeur
  d'image** entry
- a `loko-image-editor` command on your `PATH`
- automatic checks for new versions on GitHub — see [Updating](#updating)

If you run `install.sh` from a local clone, the installer now uses the
`image-editor.py` next to it first, instead of forcing the GitHub copy.
That keeps local edits and fixes in sync with the installer.

Everything is installed under `$HOME`; no `sudo` is needed except if you
opt in to letting the script install missing system packages for you.

### Dependencies

The editor needs Python 3 with PyGObject and pycairo — both ship by
default on virtually every GNOME desktop. The installer offers to install
them automatically via `apt` if they're missing; to do it yourself:

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 git curl zenity
```

## Updating

The app checks GitHub for a newer commit on `main` — once at login, and
again each time you open the editor (throttled to at most once every 6
hours so it doesn't hammer the network). When an update is found, you're
asked before anything changes:

- **Installer** — downloads and installs it right away
- **Plus tard** — asks again at the next check
- **Ignorer cette version** — stops asking until a further update is
  pushed to the repo

To check manually at any time:

```bash
~/.local/share/loko-image-editor/update.sh
```

## Alternative: GNOME Shell panel icon

Quick Image Editor started life as a GNOME Shell extension that adds a
launcher icon to the top panel instead of installing a standalone app.
`extension.js` and `metadata.json` still provide that, for anyone who
prefers it:

```bash
git clone https://github.com/Lokoyote/image-editor.git
mkdir -p ~/.local/share/gnome-shell/extensions/image-editor@loko.gnome
cp -r image-editor/{extension.js,metadata.json,image-editor.py,icons} \
      ~/.local/share/gnome-shell/extensions/image-editor@loko.gnome/
```

Then restart GNOME Shell (log out/in on Wayland, or `Alt+F2` → `r` on
X11) and enable it with the **Extensions** app, or:

```bash
gnome-extensions enable image-editor@loko.gnome
```

This mode is independent from `install.sh` — the two can coexist, though
there's little reason to run both.

## Usage

Open the editor from the applications grid, the `loko-image-editor`
command, or by right-clicking an image in Nautilus. Use the header bar's
open button (or `Ctrl+O`) to load an image into a new tab.

If the editor is already running, opening it again won't spawn a second
window — it brings the existing one to the front instead. Each image you
open lands in a new tab of that same window.

### Tools

| Tool | Description |
|---|---|
| Select | Select, move, resize (layers and shapes) |
| Crop | Drag an area, then `Enter` to confirm or `Esc` to cancel |
| Flip horizontal / vertical | Mirror the image |
| Rotate 90° | Rotate the image |
| Canvas Size | Enlarge or shrink the workspace *without* resizing the base image — pick new dimensions and where to anchor the image within them |
| Arrow / Line | Endpoint handles let you adjust length and angle once selected |
| Shapes | One button opens a choice: rectangle, circle, or polygon (click to place points, `Enter` to close and fill) |
| Text | Click to place, double-click to edit; optional background fill |
| Blur / Pixelate | Obscure a region (face, license plate, sensitive text…); intensity is adjustable |
| Add Image | Stack another image as a movable, resizable, opacity-adjustable layer |
| Paste as Layer | Paste an image from the clipboard as a new layer — works with copied image data, with images copied in Nautilus or another file manager, and with the usual URI/file clipboard formats. Greyed out automatically when there's nothing pasteable |

Selecting an already-placed shape lets you edit its color, fill, stroke
width (down to 0 — no border) and other properties live from the options
bar, instead of deleting and redrawing it.

**Keeping proportions while resizing:** grab the handle of a layer or a
rectangle/circle and hold `Ctrl` or `Shift` while dragging to scale it
while keeping its original aspect ratio.

Selected objects can also be nudged with the arrow keys (1px, or 10px
with `Shift`), in addition to dragging with the mouse.

### Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open |
| `Ctrl+S` | Save |
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo |
| `Delete` | Remove selection |
| Arrow keys | Nudge selection (`Shift` = 10px) |
| `Ctrl`/`Shift` while resizing | Keep aspect ratio |
| `Esc` | Cancel current crop/shape, switch to Select |
| `Enter` | Confirm crop or close a polygon |

### Autosave & Crash Recovery

Every open tab is autosaved periodically to
`~/.cache/image-editor-loko/autosave/`. If the app didn't close cleanly
last time (crash, power loss…), it offers to recover those tabs on the
next launch.

Thumbnails staying fresh in the file manager: after every save, the
editor also clears any cached thumbnail for that file from
`~/.cache/thumbnails/`, so Nautilus doesn't keep showing a stale preview.

### Localization

Tooltips on the tool icons are shown in French, English, Spanish, German,
Italian or Portuguese depending on your system locale, falling back to
English. The rest of the interface (menus, dialogs, status messages) is
in English.

## Troubleshooting

Run the editor directly from a terminal to see the real error:

```bash
loko-image-editor --blank
```

Common culprits: missing PyGObject/pycairo, or a network hiccup during
install/update (re-run `install.sh`, or `~/.local/share/loko-image-editor/update.sh`).

## Uninstalling

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Lokoyote/image-editor/main/uninstall.sh)
```

Or, if you already have the repo cloned locally: `bash uninstall.sh`.
This removes the app, the launcher, the icon, the `.desktop` entry, the
Nautilus script, and the update checker (including its autostart entry).
Nothing system-wide is ever touched.

If you used the [panel-icon alternative](#alternative-gnome-shell-panel-icon)
instead:

```bash
gnome-extensions uninstall image-editor@loko.gnome
```

## Contributing

Issues and pull requests welcome. Since this is a two-file project
(`extension.js` for the optional Shell integration, `image-editor.py` for
the actual editor), most contributions will only touch one of the two.

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
