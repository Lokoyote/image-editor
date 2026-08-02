# Quick Image Editor

*[Lire en français](README.md)*

A multi-layer GTK4/Python image editor, originally built as a companion app
for the "image-editor" GNOME Shell extension (opening a screenshot directly
for annotation), but perfectly usable as a standalone image editor.

A single file (`image-editor.py`), no dependency beyond what's already
installed on a standard GNOME distribution.

## Features

**Image and layers**
- Open an image / start from a blank canvas / save / save as
- Multi-layer canvas: every image you add (the "Overlay an image" button,
  a single or multi-image clipboard paste, drag-and-drop from a file
  manager) becomes a movable, resizable layer (handles at both the
  top-left **and** bottom-right corners), with adjustable opacity
- The canvas automatically grows if the added image is larger than it, to
  fit it at its original size instead of shrinking it down
- **Linked layers**: clicking the chain icon on two layers links them —
  they move together (mouse or keyboard); a colored dashed outline +
  badge on the canvas, and a colored icon in the panel, mark them
- Crop (rectangle that can be moved and resized from its 4 corners before
  confirming), horizontal/vertical flip, 90° rotation
- Canvas resize (with a choice of anchor point)

**Annotations**
- Arrows, lines, rectangles, circles/ovals, polygons, text
- Color, stroke width, fill
- Numeric border (image or text): 0 = none, any value above draws a
  border of that thickness — no separate on/off checkbox
- Blur and pixelate an area, **non-destructive**: the area stays a full
  layer (movable, adjustable intensity), and deleting it reveals the
  original image underneath
- Automatically switches back to the Select tool once a shape/text/crop/
  blur is finished

**Selection and interaction**
- Layers panel ("Objects" and "Layers" sections): visibility, reordering,
  deletion, thumbnails
- Selecting a layer via the panel gives keyboard focus back to the canvas
  right away (arrow keys, Delete, Escape all work immediately)
- Right-click an image layer for a small Copy / Paste / Duplicate menu
- Double-click a text object (with the Select tool) to edit its content
- Keyboard movement (arrow keys, Shift = 10px steps), Delete, Escape
- Undo/redo (snapshot stack), zoom (mouse wheel or trackpad, Shift =
  horizontal scroll), auto-fit on window resize

**Reliability and comfort**
- Multiple tabs, one per open image, with a warning before closing a tab
  that has unsaved changes
- Background autosave + an offer to recover after an unexpected shutdown
  (crash, power loss)
- Help button ("?"): keyboard shortcuts, what right-click does, and other
  good-to-know details
- Interface fully translated into 6 languages (French, English, Spanish,
  German, Italian, Portuguese), auto-detected from the system language

## Dependencies

- Python 3
- PyGObject (`gi`) with GTK 4, GDK, GdkPixbuf, Pango
- pycairo

All of this ships preinstalled with a standard GNOME session (Ubuntu,
Fedora, etc.). Nothing to install via pip in the normal case.

## Usage

```bash
python3 image-editor.py [image_path] [--blank] [--from-screenshot]
```

- No argument: empty state with an "Open an image…" button
- `image_path`: opens that file directly in a new tab
- `--blank`: opens a blank canvas (1200×800 by default)
- `--from-screenshot`: used by the GNOME Shell extension when launching
  from a screenshot — the source file is deleted once its content is
  loaded into memory, and the tab stays "Untitled" to avoid silently
  overwriting that temporary file

The app is single-instance: launching it again while it's already running
just brings the existing window to the front (arguments passed to that
second launch, e.g. a new image, are still taken into account).

**Formats**
- Open: PNG, JPEG, BMP, TIFF, WEBP, GIF
- Save: PNG, JPEG, BMP, TIFF (inferred from the file extension; PNG by
  default if the extension is missing or unrecognized)

## Data locations

- Autosave / crash recovery: `~/.cache/image-editor-loko/autosave/`
- Preferences (last save folder used): `~/.config/image-editor-loko/prefs.json`

## Icons

Toolbar icons are expected in an `icons/` folder next to the script
(`icons/<name>.png`). If an icon is missing, a fallback character is shown
instead — the app doesn't crash over it.

## Localization

Every user-facing string (labels, tooltips, dialogs, status messages)
goes through the `tt(key)` function, which looks up the translation in
the `UI_STRINGS` dictionary (near the top of the file) for the detected
language (`UI_LANG`, derived from the system locale via
`detect_ui_lang()`), falling back to English and then to the raw key if
nothing matches.

To add or change a piece of text: add/edit the corresponding entry in
`UI_STRINGS` (one entry per key, one translation per language among
`fr/en/es/de/it/pt`), then use it via `tt('my_key')` in the code — never
a hardcoded string for anything user-facing.

## Code structure (a map for future reference)

- `UI_STRINGS` / `tt()` — the translation dictionary and its lookup function
- `Canvas` — one open image: its layers, its annotations, its own undo
  stack, its zoom level; one `Canvas` per tab
- `EditorWindow` — the main window: tabs, header bar, options bar
  (contextual to the active tool/selection), layers panel, dialogs
  (canvas size, text, help, clipboard...)
- `LayersPanel` — the right-hand list (Objects/Layers sections);
  `refresh()` rebuilds the rows from the `Canvas` state on every change
- Autosave: `autosave_dir()`, `list_leftover_autosaves()`, an internal
  JSON format (not meant to be opened by hand)

## Status

Personal project, evolving continuously as needs come up — no formal
versioning or automated test suite at this point.
