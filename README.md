<div align="center">

# 🖼️ Quick Image Editor

**A GNOME Shell panel icon for fast, no-fuss image edits.**

Crop · Flip · Rotate · Annotate · Blur/Pixelate · Layers · Text

![GNOME Shell](https://img.shields.io/badge/GNOME%20Shell-45%20%7C%2046%20%7C%2047%20%7C%2048-4A90D9)
![License](https://img.shields.io/badge/license-TBD-lightgrey)
![Python](https://img.shields.io/badge/python-3-3776AB)

</div>

![Screenshot](https://github.com/Lokoyote/image-editor/blob/main/image-editor%20screenshot.png "image-editor screenshot")

## Why

Sometimes you don't need GIMP — you need to blur a phone number in a
screenshot, draw an arrow at something, or crop a photo before sending
it. **Quick Image Editor** adds one icon to your GNOME top panel that
opens a small, focused editor for exactly that.

The extension itself is just a launcher. The actual editing happens in a
companion GTK4 application (`image-editor.py`) shipped alongside it.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
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
- Resize the canvas independently of the base image (with anchor point)
- Undo/redo, zoom, copy/paste through the system clipboard
- Tabs: multiple images open in a single window
- Autosave with crash recovery
- Single-instance app: re-launching brings the existing window forward
  instead of opening a duplicate
- Icon tooltips localized into French, English, Spanish, German, Italian
  and Portuguese based on your system locale

## Installation

```bash
git clone <this-repo-url>
cp -r image-editor@loko.gnome ~/.local/share/gnome-shell/extensions/
```

Then:

1. Install the dependencies (see below) if they aren't already present.
2. Restart GNOME Shell — log out/in on Wayland, or `Alt+F2` → `r` on X11.
3. Enable the extension:
   ```bash
   gnome-extensions enable image-editor@loko.gnome
   ```
   or use the **Extensions** app.

### Dependencies

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0
```

(PyGObject + pycairo — already installed on most stock GNOME systems.)

## Usage

Click the panel icon → **Open an Image to Edit…**. In the window that
opens, use the header bar's open button (or `Ctrl+O`) to load an image
into a new tab.

Re-clicking the panel icon while the editor is already running just
brings that window to the front — it won't spawn a second one.

## Tools

| Tool | Description |
|---|---|
| Select | Select, move, resize (layers and shapes) |
| Crop | Drag an area, `Enter` to confirm, `Esc` to cancel |
| Flip horizontal / vertical | Mirror the image |
| Rotate 90° | Rotate the image |
| Canvas Size | Grow/shrink the workspace without resampling the base image; choose the anchor point |
| Arrow / Line | Drag endpoint handles to change length/angle once selected |
| Shapes | Rectangle, circle, or polygon (click to place points, `Enter` to close and fill) from one button |
| Text | Click to place, double-click to edit, optional background fill |
| Blur / Pixelate | Obscure a region, adjustable intensity |
| Add Image | Add another image as a layer |
| Paste as Layer | Paste from the clipboard as a new layer |

## Keyboard Shortcuts

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

## Autosave & Crash Recovery

Open tabs are periodically autosaved to
`~/.cache/image-editor-loko/autosave/`. If the app didn't exit cleanly,
you'll be offered to recover them on the next launch.

## Localization

Icon tooltips follow your system locale (French, English, Spanish,
German, Italian, Portuguese; falls back to English). The rest of the UI
is in English.

## Troubleshooting

If nothing happens when you click the panel icon, run the editor
directly to see the actual error:

```bash
python3 ~/.local/share/gnome-shell/extensions/image-editor@loko.gnome/image-editor.py --blank
```

Usual causes: missing PyGObject/pycairo, or GNOME Shell not having
reloaded the extension yet (see [Installation](#installation)).

## Uninstalling

```bash
gnome-extensions uninstall image-editor@loko.gnome
```

## Contributing

Issues and pull requests welcome. Since this is a two-file project
(`extension.js` for the Shell integration, `image-editor.py` for the
actual editor), most contributions will only touch one of the two.

## License

GNU General Public License v3.0.
