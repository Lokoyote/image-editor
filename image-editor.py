#!/usr/bin/env python3
"""
Quick Image Editor - companion app for the "image-editor" GNOME Shell extension.

What it does:
  - Open / blank canvas / save / save as
  - Crop, flip horizontal/vertical, rotate 90°
  - Arrows, lines, rectangles, circles, polygons, text
  - Blur and pixelate an area
  - Stack multiple images as layers (movable, resizable, adjustable opacity)
  - Select, move, delete and edit annotations
  - Undo/redo, zoom, copy/paste through the clipboard

Only needs PyGObject + pycairo, which ship with any standard GNOME install.
"""
import sys
import os
import math
import copy
import json
import base64
import uuid
import time
from io import BytesIO
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Pango', '1.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio, GObject, Pango
import cairo

APP_ID = "org.loko.ImageEditor"

# Tool icons: PNG files shipped in the icons/ folder next to this script.
ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')

# Language detection for icon tooltips. The rest of the UI is plain English

def detect_ui_lang():
    """Look at the system locale (LANGUAGE/LC_ALL/LC_MESSAGES/LANG via GLib)
    and return a short language code we have tooltips for, defaulting to
    English if nothing matches."""
    supported = ('fr', 'en', 'es', 'de', 'it', 'pt')
    try:
        for lang in GLib.get_language_names():
            code = lang.split('_')[0].split('.')[0].lower()
            if code in supported:
                return code
    except Exception:
        pass
    return 'en'


UI_LANG = detect_ui_lang()

# key -> {lang_code: text}. English is the fallback when a translation is
# missing for the detected language.
ICON_TOOLTIPS = {
    'open': {
        'fr': "Ouvrir une image (nouvel onglet)", 'en': "Open an image (new tab)",
        'es': "Abrir una imagen (nueva pestaña)", 'de': "Bild öffnen (neuer Tab)",
        'it': "Apri un'immagine (nuova scheda)", 'pt': "Abrir uma imagem (novo separador)",
    },
    'undo': {
        'fr': "Annuler (Ctrl+Z)", 'en': "Undo (Ctrl+Z)", 'es': "Deshacer (Ctrl+Z)",
        'de': "Rückgängig (Strg+Z)", 'it': "Annulla (Ctrl+Z)", 'pt': "Desfazer (Ctrl+Z)",
    },
    'redo': {
        'fr': "Rétablir (Ctrl+Y)", 'en': "Redo (Ctrl+Y)", 'es': "Rehacer (Ctrl+Y)",
        'de': "Wiederholen (Strg+Y)", 'it': "Ripeti (Ctrl+Y)", 'pt': "Refazer (Ctrl+Y)",
    },
    'save_menu': {
        'fr': "Enregistrer…", 'en': "Save…", 'es': "Guardar…",
        'de': "Speichern…", 'it': "Salva…", 'pt': "Guardar…",
    },
    'save': {
        'fr': "Enregistrer", 'en': "Save", 'es': "Guardar",
        'de': "Speichern", 'it': "Salva", 'pt': "Guardar",
    },
    'save_as': {
        'fr': "Enregistrer sous…", 'en': "Save as…", 'es': "Guardar como…",
        'de': "Speichern unter…", 'it': "Salva con nome…", 'pt': "Guardar como…",
    },
    'copy': {
        'fr': "Copier le résultat dans le presse-papiers", 'en': "Copy the result to the clipboard",
        'es': "Copiar el resultado al portapapeles", 'de': "Ergebnis in die Zwischenablage kopieren",
        'it': "Copia il risultato negli appunti", 'pt': "Copiar o resultado para a área de transferência",
    },
    'select': {
        'fr': "Sélection : sélectionner, déplacer, redimensionner",
        'en': "Select: select, move, resize",
        'es': "Selección: seleccionar, mover, redimensionar",
        'de': "Auswahl: auswählen, verschieben, Größe ändern",
        'it': "Selezione: seleziona, sposta, ridimensiona",
        'pt': "Seleção: selecionar, mover, redimensionar",
    },
    'crop': {
        'fr': "Recadrer : tracer une zone, puis Entrée pour valider ou Échap pour annuler",
        'en': "Crop: drag an area, then Enter to confirm or Esc to cancel",
        'es': "Recortar: trace un área, luego Intro para confirmar o Esc para cancelar",
        'de': "Zuschneiden: Bereich ziehen, dann Enter zum Bestätigen oder Esc zum Abbrechen",
        'it': "Ritaglia: traccia un'area, poi Invio per confermare o Esc per annullare",
        'pt': "Recortar: trace uma área, depois Enter para confirmar ou Esc para cancelar",
    },
    'flip_h': {
        'fr': "Retourner horizontalement", 'en': "Flip horizontally", 'es': "Voltear horizontalmente",
        'de': "Horizontal spiegeln", 'it': "Capovolgi orizzontalmente", 'pt': "Inverter horizontalmente",
    },
    'flip_v': {
        'fr': "Retourner verticalement", 'en': "Flip vertically", 'es': "Voltear verticalmente",
        'de': "Vertikal spiegeln", 'it': "Capovolgi verticalmente", 'pt': "Inverter verticalmente",
    },
    'rotate90': {
        'fr': "Pivoter à 90°", 'en': "Rotate 90°", 'es': "Girar 90°",
        'de': "Um 90° drehen", 'it': "Ruota di 90°", 'pt': "Rodar 90°",
    },
    'canvas_size': {
        'fr': "Taille du canevas… (agrandir/réduire l'espace de travail sans redimensionner l'image)",
        'en': "Canvas size… (enlarge/shrink the workspace without resizing the image)",
        'es': "Tamaño del lienzo… (ampliar/reducir el espacio de trabajo sin redimensionar la imagen)",
        'de': "Leinwandgröße… (Arbeitsbereich vergrößern/verkleinern, ohne das Bild zu skalieren)",
        'it': "Dimensione della tela… (ingrandire/ridurre l'area di lavoro senza ridimensionare l'immagine)",
        'pt': "Tamanho da tela… (aumentar/reduzir a área de trabalho sem redimensionar a imagem)",
    },
    'arrow': {
        'fr': "Flèche", 'en': "Arrow", 'es': "Flecha", 'de': "Pfeil", 'it': "Freccia", 'pt': "Seta",
    },
    'line': {
        'fr': "Ligne", 'en': "Line", 'es': "Línea", 'de': "Linie", 'it': "Linea", 'pt': "Linha",
    },
    'shape_menu': {
        'fr': "Formes : rectangle, cercle ou polygone", 'en': "Shapes: rectangle, circle or polygon",
        'es': "Formas: rectángulo, círculo o polígono", 'de': "Formen: Rechteck, Kreis oder Vieleck",
        'it': "Forme: rettangolo, cerchio o poligono", 'pt': "Formas: retângulo, círculo ou polígono",
    },
    'shape_rect': {
        'fr': "Rectangle / cadre", 'en': "Rectangle / frame", 'es': "Rectángulo / marco",
        'de': "Rechteck / Rahmen", 'it': "Rettangolo / cornice", 'pt': "Retângulo / moldura",
    },
    'shape_rect_label': {
        'fr': "Rectangle", 'en': "Rectangle", 'es': "Rectángulo",
        'de': "Rechteck", 'it': "Rettangolo", 'pt': "Retângulo",
    },
    'shape_circle': {
        'fr': "Cercle / ovale", 'en': "Circle / oval", 'es': "Círculo / óvalo",
        'de': "Kreis / Oval", 'it': "Cerchio / ovale", 'pt': "Círculo / oval",
    },
    'shape_circle_label': {
        'fr': "Cercle / ovale", 'en': "Circle / oval", 'es': "Círculo / óvalo",
        'de': "Kreis / Oval", 'it': "Cerchio / ovale", 'pt': "Círculo / oval",
    },
    'shape_polygon': {
        'fr': "Polygone : cliquer pour placer les points, Entrée pour fermer et remplir",
        'en': "Polygon: click to place points, Enter to close and fill",
        'es': "Polígono: clic para colocar puntos, Intro para cerrar y rellenar",
        'de': "Vieleck: Klicken, um Punkte zu setzen, Enter zum Schließen und Füllen",
        'it': "Poligono: clic per posizionare i punti, Invio per chiudere e riempire",
        'pt': "Polígono: clique para colocar pontos, Enter para fechar e preencher",
    },
    'shape_polygon_label': {
        'fr': "Polygone", 'en': "Polygon", 'es': "Polígono",
        'de': "Vieleck", 'it': "Poligono", 'pt': "Polígono",
    },
    'text': {
        'fr': "Texte : cliquer pour ajouter, double-clic pour modifier",
        'en': "Text: click to add, double-click to edit",
        'es': "Texto: clic para añadir, doble clic para editar",
        'de': "Text: Klicken zum Hinzufügen, Doppelklick zum Bearbeiten",
        'it': "Testo: clic per aggiungere, doppio clic per modificare",
        'pt': "Texto: clique para adicionar, duplo clique para editar",
    },
    'blur': {
        'fr': "Flouter une zone (visage, plaque…)", 'en': "Blur an area (face, plate…)",
        'es': "Difuminar una zona (cara, matrícula…)", 'de': "Bereich weichzeichnen (Gesicht, Kennzeichen…)",
        'it': "Sfoca un'area (volto, targa…)", 'pt': "Desfocar uma área (rosto, matrícula…)",
    },
    'pixelate': {
        'fr': "Pixelliser une zone", 'en': "Pixelate an area", 'es': "Pixelar una zona",
        'de': "Bereich verpixeln", 'it': "Pixela un'area", 'pt': "Pixelizar uma área",
    },
    'add_image': {
        'fr': "Superposer une image (nouveau calque)", 'en': "Overlay an image (new layer)",
        'es': "Superponer una imagen (nueva capa)", 'de': "Bild überlagern (neue Ebene)",
        'it': "Sovrapponi un'immagine (nuovo livello)", 'pt': "Sobrepor uma imagem (nova camada)",
    },
    'paste_layer': {
        'fr': "Coller depuis le presse-papiers comme calque",
        'en': "Paste from clipboard as a layer",
        'es': "Pegar desde el portapapeles como capa",
        'de': "Aus der Zwischenablage als Ebene einfügen",
        'it': "Incolla dagli appunti come livello",
        'pt': "Colar da área de transferência como camada",
    },
}


def tt(key):
    """Look up an icon tooltip for the detected UI language, falling back
    to English and then to the raw key if nothing else matches."""
    entry = ICON_TOOLTIPS.get(key)
    if not entry:
        return key
    return entry.get(UI_LANG) or entry.get('en') or key


# Low-level helpers (cairo surfaces)

def clone_surface(surf):
    new = cairo.ImageSurface(surf.get_format(), surf.get_width(), surf.get_height())
    cr = cairo.Context(new)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_surface(surf, 0, 0)
    cr.paint()
    return new


def surface_from_pixbuf(pixbuf):
    w, h = pixbuf.get_width(), pixbuf.get_height()
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
    cr.paint()
    return surf


def blank_surface(w, h, rgb=(1, 1, 1)):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    cr.set_source_rgb(*rgb)
    cr.paint()
    return surf


def next_id_counter():
    n = 0
    while True:
        n += 1
        yield n


_ID_GEN = next_id_counter()


# Temporary autosave (crash recovery)

def autosave_dir():
    d = os.path.join(GLib.get_user_cache_dir(), 'image-editor-loko', 'autosave')
    os.makedirs(d, exist_ok=True)
    return d


# Lightweight preferences (last save folder)

def _prefs_path():
    d = os.path.join(GLib.get_user_config_dir(), 'image-editor-loko')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'prefs.json')


def load_last_save_folder():
    """Last folder used to save an image, persisted across sessions so the
    file picker opens there instead of the home directory every time."""
    try:
        with open(_prefs_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        folder = data.get('last_save_folder')
        if folder and os.path.isdir(folder):
            return folder
    except (OSError, ValueError):
        pass
    return None


def save_last_save_folder(folder):
    try:
        with open(_prefs_path(), 'w', encoding='utf-8') as f:
            json.dump({'last_save_folder': folder}, f)
    except OSError:
        pass


def autosave_path(autosave_id):
    return os.path.join(autosave_dir(), f"{autosave_id}.json")


def write_autosave(canvas):
    """Dump the full document state if needed. Must never raise — a broken
    autosave shouldn't be able to crash the editor."""
    if not canvas.width or not canvas.dirty:
        return
    path = autosave_path(canvas.autosave_id)
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(canvas.autosave_dict(), f)
        os.replace(tmp, path)
    except Exception:
        pass


def delete_autosave(canvas):
    try:
        os.remove(autosave_path(canvas.autosave_id))
    except OSError:
        pass


def list_leftover_autosaves():
    """Autosave files left behind by a session that didn't shut down
    cleanly (crash, kill -9, power loss...)."""
    d = autosave_dir()
    try:
        names = os.listdir(d)
    except OSError:
        return []
    return sorted(os.path.join(d, n) for n in names if n.endswith('.json'))


# The editing canvas

def cleanup_stray_screenshots(max_age_seconds=15):
    """Safety net: if GNOME Shell (or some Ubuntu variant) still drops a
    copy in a standard screenshot folder despite the low-level D-Bus call
    the extension uses, remove it — but only if it was just created (a few
    seconds ago), so we never touch an unrelated screenshot taken earlier.
    but only if it was created moments ago."""
    now = time.time()
    folders = set()
    pictures_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    home = os.path.expanduser('~')
    if pictures_dir:
        folders.add(os.path.join(pictures_dir, 'Screenshots'))
        folders.add(os.path.join(pictures_dir, "Captures d'écran"))
    folders.add(os.path.join(home, 'Images', "Captures d'écran"))
    folders.add(os.path.join(home, 'Pictures', 'Screenshots'))
    name_hints = ('screenshot', 'capture')
    for folder in folders:
        try:
            if not os.path.isdir(folder):
                continue
            for fname in os.listdir(folder):
                if not any(h in fname.lower() for h in name_hints):
                    continue
                fpath = os.path.join(folder, fname)
                try:
                    if now - os.path.getmtime(fpath) <= max_age_seconds:
                        os.remove(fpath)
                except OSError:
                    pass
        except OSError:
            pass


class Canvas(Gtk.DrawingArea):
    """The editing widget: owns the base image, layers, annotations, the
    undo/redo history, and all mouse/keyboard interaction."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.set_focusable(True)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)

        self.surface = None
        self.width = 0
        self.height = 0
        self.img_rect = None      # {x, y, w, h} bounds of the base image within the canvas

        self.layers = []          # stacked images, each movable/resizable
        self.annotations = []     # arrows / shapes / text

        self.current_path = None  # associated file (None if never saved)
        self.dirty = False        # unsaved changes?
        self.autosave_id = uuid.uuid4().hex

        self.tool = 'select'
        self.color = (0.92, 0.13, 0.13, 1.0)
        self.fill_enabled = False
        self.fill_color = (1.0, 1.0, 1.0, 1.0)
        self.stroke_width = 4.0
        self.font_size = 28.0
        self.arrow_head_style = 'end'   # 'end' | 'start' | 'both' | 'none'
        self.blur_level = 22            # higher = blurrier
        self.pixelate_level = 12        # higher = chunkier blocks
        self.zoom = 1.0
        self.polygon_points = None      # points of the polygon being drawn
        self._mouse_pos = (0.0, 0.0)    # last known cursor position (image coords)
        self._constrain_active = False  # aspect ratio locked (Ctrl/Shift) during a resize

        self.selected = None      # ('annotation'|'layer', obj)
        self.draft = None         # shape currently being drawn
        self.pending_crop = None
        self.pending_effect = None
        self._mode = None
        self._drag_start_img = (0, 0)
        self._orig_geom = None
        self._active_handle = None

        self.undo_stack = []
        self.redo_stack = []

        self.set_draw_func(self._on_draw)

        drag = Gtk.GestureDrag()
        drag.connect('drag-begin', self._on_drag_begin)
        drag.connect('drag-update', self._on_drag_update)
        drag.connect('drag-end', self._on_drag_end)
        self.add_controller(drag)

        click = Gtk.GestureClick()
        click.connect('pressed', self._on_click)
        self.add_controller(click)

        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._on_key)
        self.add_controller(keys)

        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect('scroll', self._on_scroll)
        self.add_controller(scroll)

        motion = Gtk.EventControllerMotion()
        motion.connect('motion', self._on_motion)
        self.add_controller(motion)

    # ---- document ----------------------------------------------------

    def next_id(self):
        return next(_ID_GEN)

    def load_pixbuf(self, pixbuf):
        self.surface = surface_from_pixbuf(pixbuf)
        self.width = pixbuf.get_width()
        self.height = pixbuf.get_height()
        self.img_rect = {'x': 0.0, 'y': 0.0, 'w': float(self.width), 'h': float(self.height)}
        self.layers = []
        self.annotations = []
        self.selected = None
        self.undo_stack = []
        self.redo_stack = []
        self.dirty = False
        self.update_content_size()

    def new_blank(self, w=1200, h=800):
        self.surface = blank_surface(w, h)
        self.width, self.height = w, h
        self.img_rect = {'x': 0.0, 'y': 0.0, 'w': float(w), 'h': float(h)}
        self.layers = []
        self.annotations = []
        self.selected = None
        self.undo_stack = []
        self.redo_stack = []
        self.current_path = None
        self.dirty = False
        self.update_content_size()

    def update_content_size(self):
        self.set_content_width(max(1, int(self.width * self.zoom)))
        self.set_content_height(max(1, int(self.height * self.zoom)))
        self.queue_draw()
        self.app.update_status()

    def set_zoom(self, zoom):
        self.zoom = max(0.1, min(6.0, zoom))
        self.update_content_size()

    def _on_scroll(self, controller, dx, dy):
        """Ctrl + mouse wheel, or Ctrl + two-finger scroll on a trackpad,
        zooms in/out. Without Ctrl we let normal scrolling do its job."""
        state = controller.get_current_event_state()
        if not (state & Gdk.ModifierType.CONTROL_MASK):
            return False
        if dy == 0:
            return False
        step = 1.1
        factor = step if dy < 0 else 1.0 / step
        self.set_zoom(self.zoom * factor)
        return True

    def _on_motion(self, controller, x, y):
        self._mouse_pos = (x / self.zoom, y / self.zoom)
        if self.tool == 'polygon' and self.polygon_points:
            self.queue_draw()

    # ---- history ----------------------------------------------------

    def snapshot(self):
        return {
            'surface': clone_surface(self.surface),
            'width': self.width,
            'height': self.height,
            'img_rect': dict(self.img_rect) if self.img_rect else None,
            'layers': [dict(l, surface=clone_surface(l['surface'])) for l in self.layers],
            'annotations': copy.deepcopy(self.annotations),
        }

    def restore(self, state):
        self.surface = state['surface']
        self.width = state['width']
        self.height = state['height']
        self.img_rect = dict(state['img_rect']) if state.get('img_rect') else None
        self.layers = state['layers']
        self.annotations = state['annotations']
        self.selected = None
        self.dirty = True
        self.update_content_size()

    def push_undo(self):
        self.redo_stack.clear()
        self.undo_stack.append(self.snapshot())
        if len(self.undo_stack) > 25:
            self.undo_stack.pop(0)
        self.dirty = True
        self.app.update_undo_redo()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.snapshot())
        self.restore(self.undo_stack.pop())
        self.app.update_undo_redo()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.snapshot())
        self.restore(self.redo_stack.pop())
        self.app.update_undo_redo()

    # ---- rendering ----------------------------------------------------

    def render_composite(self):
        """Flatten the base image + layers + annotations into one surface."""
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        cr = cairo.Context(surf)
        if self.surface:
            cr.set_source_surface(self.surface, 0, 0)
            cr.paint()
        for layer in self.layers:
            cr.save()
            cr.translate(layer['x'], layer['y'])
            cr.scale(layer['w'] / layer['orig_w'], layer['h'] / layer['orig_h'])
            cr.set_source_surface(layer['surface'], 0, 0)
            cr.paint_with_alpha(layer['opacity'])
            cr.restore()
        for ann in self.annotations:
            self._draw_annotation(cr, ann, selected=False)
        return surf

    def _ensure_checker_surface(self):
        """The checkerboard is rendered once into a cached surface (only
        rebuilt if the canvas dimensions change) and then just blitted every
        frame — much faster than recomputing a repeating pattern on every
        redraw, which used to cause visible lag."""
        w, h = max(1, int(self.width)), max(1, int(self.height))
        cached = getattr(self, '_checker_surface', None)
        if cached is not None and getattr(self, '_checker_surface_size', None) == (w, h):
            return cached

        size = 16
        tile = getattr(self, '_checker_tile', None)
        if tile is None:
            tile = cairo.ImageSurface(cairo.FORMAT_ARGB32, size * 2, size * 2)
            tcr = cairo.Context(tile)
            tcr.set_source_rgb(0.87, 0.87, 0.87)
            tcr.paint()
            tcr.set_source_rgb(0.80, 0.80, 0.80)
            tcr.rectangle(0, 0, size, size)
            tcr.rectangle(size, size, size, size)
            tcr.fill()
            self._checker_tile = tile

        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        scr = cairo.Context(surf)
        pattern = cairo.SurfacePattern(tile)
        pattern.set_extend(cairo.EXTEND_REPEAT)
        scr.set_source(pattern)
        scr.paint()

        self._checker_surface = surf
        self._checker_surface_size = (w, h)
        return surf

    def _draw_checkerboard(self, cr, x, y, w, h):
        """Low-contrast checkerboard background standing in for the
        workspace (shows through transparent areas and any space added
        around the base image)."""
        cr.save()
        cr.rectangle(x, y, w, h)
        cr.clip()
        cr.set_source_surface(self._ensure_checker_surface(), x, y)
        cr.paint()
        cr.restore()

    def _draw_image_bounds(self, cr):
        """Faint dashed outline marking the base image, useful once the
        canvas has been enlarged beyond the image's own dimensions."""
        r = self.img_rect
        if not r:
            return
        cr.save()
        cr.set_source_rgba(0.3, 0.55, 0.85, 0.55)
        cr.set_line_width(1.2 / self.zoom)
        cr.set_dash([5.0 / self.zoom, 4.0 / self.zoom])
        inset = 0.6 / self.zoom
        cr.rectangle(r['x'] + inset, r['y'] + inset,
                     max(0.0, r['w'] - 2 * inset), max(0.0, r['h'] - 2 * inset))
        cr.stroke()
        cr.restore()

    def _on_draw(self, area, cr, width, height):
        cr.save()
        cr.set_source_rgb(0.15, 0.15, 0.17)
        cr.paint()
        cr.scale(self.zoom, self.zoom)

        self._draw_checkerboard(cr, 0, 0, self.width, self.height)

        if self.surface:
            cr.set_source_surface(self.surface, 0, 0)
            cr.paint()

        self._draw_image_bounds(cr)

        for layer in self.layers:
            cr.save()
            cr.translate(layer['x'], layer['y'])
            cr.scale(layer['w'] / layer['orig_w'], layer['h'] / layer['orig_h'])
            cr.set_source_surface(layer['surface'], 0, 0)
            cr.paint_with_alpha(layer['opacity'])
            cr.restore()
            if self.selected == ('layer', layer):
                self._draw_layer_selection(cr, layer)

        for ann in self.annotations:
            self._draw_annotation(cr, ann, selected=(self.selected == ('annotation', ann)))

        if self.draft:
            self._draw_annotation(cr, self.draft, selected=False)

        if self.tool == 'polygon' and self.polygon_points:
            self._draw_polygon_progress(cr)

        if self.pending_crop:
            self._draw_crop_overlay(cr, self.pending_crop)

        if self.pending_effect:
            r = self.pending_effect
            cr.set_source_rgba(1.0, 0.55, 0.0, 0.95)
            cr.set_line_width(2.0 / self.zoom)
            cr.set_dash([6.0 / self.zoom, 4.0 / self.zoom])
            cr.rectangle(r['x'], r['y'], r['w'], r['h'])
            cr.stroke()

        cr.restore()

    def _draw_layer_selection(self, cr, layer):
        cr.save()
        cr.set_source_rgba(0.2, 0.6, 1.0, 0.9)
        cr.set_line_width(2.0 / self.zoom)
        cr.set_dash([6.0 / self.zoom, 4.0 / self.zoom])
        cr.rectangle(layer['x'], layer['y'], layer['w'], layer['h'])
        cr.stroke()
        cr.set_dash([])
        hs = self._handle_size()
        cr.rectangle(layer['x'] + layer['w'] - hs / 2, layer['y'] + layer['h'] - hs / 2, hs, hs)
        cr.fill()
        cr.restore()

    def _handle_size(self):
        return 12.0 / self.zoom

    def _draw_crop_overlay(self, cr, r):
        cr.save()
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.rectangle(0, 0, self.width, self.height)
        cr.rectangle(r['x'], r['y'], r['w'], r['h'])
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.set_line_width(1.5 / self.zoom)
        cr.rectangle(r['x'], r['y'], r['w'], r['h'])
        cr.stroke()
        cr.restore()

    def _draw_polygon_progress(self, cr):
        """Draw the points placed so far, the segments already traced, and a
        dashed preview of the segment that will connect the current mouse
        position back to the very first point once Enter is pressed."""
        pts = self.polygon_points
        cr.save()
        r, g, b, a = self.color
        cr.set_source_rgba(r, g, b, a)
        cr.set_line_width(self.stroke_width)
        cr.move_to(*pts[0])
        for p in pts[1:]:
            cr.line_to(*p)
        mx, my = self._mouse_pos
        cr.line_to(mx, my)
        cr.stroke()

        cr.set_source_rgba(0.2, 0.6, 1.0, 0.65)
        cr.set_line_width(1.5 / self.zoom)
        cr.set_dash([5.0 / self.zoom, 3.0 / self.zoom])
        cr.move_to(mx, my)
        cr.line_to(*pts[0])
        cr.stroke()
        cr.set_dash([])

        cr.set_source_rgba(0.2, 0.6, 1.0, 0.95)
        hs = self._handle_size()
        for p in pts:
            cr.rectangle(p[0] - hs / 2, p[1] - hs / 2, hs, hs)
            cr.fill()
        cr.restore()

    @staticmethod
    def _norm_rect(ann):
        return ann['x'], ann['y'], ann['w'], ann['h']

    def _draw_annotation(self, cr, ann, selected):
        cr.save()
        r, g, b, a = ann['color']
        t = ann['type']
        fill = ann.get('fill')
        bbox = None
        if t == 'rect':
            x, y, w, h = self._norm_rect(ann)
            if fill:
                cr.set_source_rgba(*fill)
                cr.rectangle(x, y, w, h)
                cr.fill()
            if ann['width'] > 0:
                cr.set_source_rgba(r, g, b, a)
                cr.set_line_width(ann['width'])
                cr.rectangle(x, y, w, h)
                cr.stroke()
            bbox = (x, y, w, h)
        elif t == 'circle':
            x, y, w, h = self._norm_rect(ann)
            if fill:
                cr.save()
                cr.translate(x + w / 2, y + h / 2)
                cr.scale(max(w / 2, 0.001), max(h / 2, 0.001))
                cr.arc(0, 0, 1, 0, 2 * math.pi)
                cr.restore()
                cr.set_source_rgba(*fill)
                cr.fill()
            if ann['width'] > 0:
                cr.save()
                cr.translate(x + w / 2, y + h / 2)
                cr.scale(max(w / 2, 0.001), max(h / 2, 0.001))
                cr.arc(0, 0, 1, 0, 2 * math.pi)
                cr.restore()
                cr.set_source_rgba(r, g, b, a)
                cr.set_line_width(ann['width'])
                cr.stroke()
            bbox = (x, y, w, h)
        elif t == 'line':
            if ann['width'] > 0:
                cr.set_source_rgba(r, g, b, a)
                cr.set_line_width(ann['width'])
                cr.move_to(ann['x1'], ann['y1'])
                cr.line_to(ann['x2'], ann['y2'])
                cr.stroke()
            bbox = self._segment_bbox(ann)
        elif t == 'arrow':
            if ann['width'] > 0:
                cr.set_source_rgba(r, g, b, a)
                cr.set_line_width(ann['width'])
                self._draw_arrow(cr, ann)
            bbox = self._segment_bbox(ann)
        elif t == 'text':
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(ann['font_size'])
            ext = cr.text_extents(ann['text'])
            pad = max(3.0, ann['font_size'] * 0.12)
            bg_x = ann['x'] + ext.x_bearing - pad
            bg_y = ann['y'] + ext.y_bearing - pad
            bg_w = ext.width + 2 * pad
            bg_h = ext.height + 2 * pad
            if fill:
                cr.set_source_rgba(*fill)
                cr.rectangle(bg_x, bg_y, bg_w, bg_h)
                cr.fill()
            cr.set_source_rgba(r, g, b, a)
            cr.move_to(ann['x'], ann['y'])
            cr.show_text(ann['text'])
            bbox = (bg_x, bg_y, bg_w, bg_h) if fill else \
                (ann['x'] + ext.x_bearing, ann['y'] + ext.y_bearing, ext.width, ext.height)
        elif t == 'polygon':
            pts = ann['points']
            if len(pts) >= 2:
                if fill:
                    cr.move_to(*pts[0])
                    for p in pts[1:]:
                        cr.line_to(*p)
                    cr.close_path()
                    cr.set_source_rgba(*fill)
                    cr.fill()
                if ann['width'] > 0:
                    cr.move_to(*pts[0])
                    for p in pts[1:]:
                        cr.line_to(*p)
                    cr.close_path()
                    cr.set_source_rgba(r, g, b, a)
                    cr.set_line_width(ann['width'])
                    cr.stroke()
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            bbox = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        cr.restore()

        if selected and bbox:
            cr.save()
            cr.set_source_rgba(0.2, 0.6, 1.0, 0.9)
            cr.set_line_width(1.5 / self.zoom)
            cr.set_dash([5.0 / self.zoom, 3.0 / self.zoom])
            pad = 4.0 / self.zoom
            cr.rectangle(bbox[0] - pad, bbox[1] - pad, bbox[2] + 2 * pad, bbox[3] + 2 * pad)
            cr.stroke()
            cr.restore()

        if selected:
            handles = self._annotation_handles(ann)
            if handles:
                cr.save()
                cr.set_source_rgba(0.2, 0.6, 1.0, 0.95)
                hs = self._handle_size()
                for _hid, hx, hy in handles:
                    cr.rectangle(hx - hs / 2, hy - hs / 2, hs, hs)
                    cr.fill()
                cr.restore()

    def _draw_arrow(self, cr, ann):
        x1, y1, x2, y2 = ann['x1'], ann['y1'], ann['x2'], ann['y2']
        cr.move_to(x1, y1)
        cr.line_to(x2, y2)
        cr.stroke()
        style = ann.get('head_style', 'end')
        head = max(12.0, ann['width'] * 4.0)
        if style in ('end', 'both'):
            self._draw_arrow_head(cr, x1, y1, x2, y2, head)
        if style in ('start', 'both'):
            self._draw_arrow_head(cr, x2, y2, x1, y1, head)

    @staticmethod
    def _draw_arrow_head(cr, from_x, from_y, tip_x, tip_y, head):
        angle = math.atan2(tip_y - from_y, tip_x - from_x)
        p1 = (tip_x - head * math.cos(angle - 0.45), tip_y - head * math.sin(angle - 0.45))
        p2 = (tip_x - head * math.cos(angle + 0.45), tip_y - head * math.sin(angle + 0.45))
        cr.move_to(tip_x, tip_y)
        cr.line_to(*p1)
        cr.line_to(*p2)
        cr.close_path()
        cr.fill()

    @staticmethod
    def _segment_bbox(ann):
        x1, y1, x2, y2 = ann['x1'], ann['y1'], ann['x2'], ann['y2']
        return min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)

    # ---- hit-testing / selection ----------------------------------------------------

    def _point_in_layer_handle(self, layer, x, y):
        hs = self._handle_size()
        hx, hy = layer['x'] + layer['w'], layer['y'] + layer['h']
        return abs(x - hx) <= hs and abs(y - hy) <= hs

    def _annotation_handles(self, ann):
        """Selection handles: bottom-right corner for rectangles/circles
        (resize), endpoints for lines/arrows (length + direction)."""
        t = ann['type']
        if t in ('rect', 'circle'):
            x, y, w, h = self._norm_rect(ann)
            return [('br', x + w, y + h)]
        if t in ('line', 'arrow'):
            return [('p1', ann['x1'], ann['y1']), ('p2', ann['x2'], ann['y2'])]
        return []

    def _point_in_annotation_handle(self, ann, x, y):
        hs = self._handle_size()
        for hid, hx, hy in self._annotation_handles(ann):
            if abs(x - hx) <= hs and abs(y - hy) <= hs:
                return hid
        return None

    def _point_in_annotation(self, ann, x, y):
        t = ann['type']
        tol = max(6.0, ann['width'])
        if t == 'polygon':
            pts = ann['points']
            if ann.get('fill') is not None and self._point_in_polygon(x, y, pts):
                return True
            n = len(pts)
            for i in range(n):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % n]
                if self._dist_point_segment(x, y, x1, y1, x2, y2) <= tol:
                    return True
            return False
        if t in ('rect', 'circle', 'text'):
            bx, by, bw, bh = self._norm_rect(ann) if t != 'text' else \
                (ann['x'] - 4, ann['y'] - ann['font_size'], len(ann['text']) * ann['font_size'] * 0.6,
                 ann['font_size'] * 1.3)
            return (bx - tol) <= x <= (bx + bw + tol) and (by - tol) <= y <= (by + bh + tol)
        else:
            x1, y1, x2, y2 = ann['x1'], ann['y1'], ann['x2'], ann['y2']
            return self._dist_point_segment(x, y, x1, y1, x2, y2) <= tol

    @staticmethod
    def _point_in_polygon(x, y, pts):
        inside = False
        n = len(pts)
        j = n - 1
        for i in range(n):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > y) != (yj > y):
                x_at_y = (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
                if x < x_at_y:
                    inside = not inside
            j = i
        return inside

    @staticmethod
    def _dist_point_segment(px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0, min(1, t))
        cx, cy = x1 + t * dx, y1 + t * dy
        return math.hypot(px - cx, py - cy)

    def hit_test(self, x, y):
        for ann in reversed(self.annotations):
            if self._point_in_annotation(ann, x, y):
                return ('annotation', ann)
        for layer in reversed(self.layers):
            if layer['x'] <= x <= layer['x'] + layer['w'] and layer['y'] <= y <= layer['y'] + layer['h']:
                return ('layer', layer)
        return None

    def delete_selected(self):
        if not self.selected:
            return
        self.push_undo()
        kind, obj = self.selected
        if kind == 'annotation' and obj in self.annotations:
            self.annotations.remove(obj)
        elif kind == 'layer' and obj in self.layers:
            self.layers.remove(obj)
        self.selected = None
        self.queue_draw()
        self.app.update_status()

    # ---- interaction ----------------------------------------------------

    def _on_click(self, gesture, n_press, x, y):
        self.grab_focus()
        ix, iy = x / self.zoom, y / self.zoom
        if self.tool == 'text':
            self.app.prompt_text(ix, iy)
            return
        if self.tool == 'polygon':
            if self.polygon_points is None:
                self.polygon_points = []
            self.polygon_points.append((ix, iy))
            self.queue_draw()
            self.app.set_status(
                f"Polygon: {len(self.polygon_points)} point(s) placed — "
                f"Enter to close and fill, Esc to cancel.")
            return
        if self.tool == 'select' and n_press == 2:
            hit = self.hit_test(ix, iy)
            if hit and hit[0] == 'annotation' and hit[1]['type'] == 'text':
                self.app.prompt_text(None, None, edit=hit[1])

    def _on_drag_begin(self, gesture, start_x, start_y):
        self.grab_focus()
        ix, iy = start_x / self.zoom, start_y / self.zoom
        self._drag_start_img = (ix, iy)

        if self.tool == 'select':
            handle_id = None
            if self.selected and self.selected[0] == 'layer' and \
                    self._point_in_layer_handle(self.selected[1], ix, iy):
                self.push_undo()
                self._mode = 'resize-layer'
                self._orig_geom = dict(self.selected[1])
                self._constrain_active = False
                self.app._show_hint("Hold Ctrl or Shift to keep the aspect ratio", seconds=10)
            elif self.selected and self.selected[0] == 'annotation' and \
                    (handle_id := self._point_in_annotation_handle(self.selected[1], ix, iy)):
                self.push_undo()
                self._mode = 'annotation-handle'
                self._active_handle = handle_id
                self._orig_geom = dict(self.selected[1])
                if self.selected[1]['type'] in ('rect', 'circle'):
                    self._constrain_active = False
                    self.app._show_hint("Hold Ctrl or Shift to keep the aspect ratio", seconds=10)
            else:
                hit = self.hit_test(ix, iy)
                if hit:
                    self.selected = hit
                    self.push_undo()
                    self._mode = 'move'
                    self._orig_geom = dict(hit[1])
                    if hit[1].get('type') == 'polygon':
                        self._orig_geom['points'] = [tuple(p) for p in hit[1]['points']]
                else:
                    self.selected = None
                    self._mode = None
        elif self.tool == 'crop':
            self.pending_crop = {'x': ix, 'y': iy, 'w': 0, 'h': 0}
            self._mode = 'crop'
        elif self.tool in ('rect', 'circle'):
            self.draft = {'id': None, 'type': self.tool, 'x': ix, 'y': iy, 'w': 0, 'h': 0,
                          'color': self.color, 'width': self.stroke_width,
                          'fill': self.fill_color if self.fill_enabled else None}
            self._mode = 'draw'
        elif self.tool in ('arrow', 'line'):
            self.draft = {'id': None, 'type': self.tool, 'x1': ix, 'y1': iy, 'x2': ix, 'y2': iy,
                          'color': self.color, 'width': self.stroke_width}
            if self.tool == 'arrow':
                self.draft['head_style'] = self.arrow_head_style
            self._mode = 'draw'
        elif self.tool in ('blur', 'pixelate'):
            self.pending_effect = {'x': ix, 'y': iy, 'w': 0, 'h': 0}
            self._mode = 'effect'
        else:
            self._mode = None
        self.queue_draw()
        self.app.update_status()

    def _resize_constrain_active(self, gesture):
        """True if Ctrl or Shift is held during a resize (layer or shape),
        which locks the original width/height ratio. Also updates the hint
        bubble to reflect the current state."""
        state = gesture.get_current_event_state()
        constrain = bool(state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK))
        if constrain != self._constrain_active:
            self._constrain_active = constrain
            if constrain:
                self.app._show_hint("🔒 Aspect ratio locked (Ctrl/Shift held)", seconds=10)
            else:
                self.app._show_hint("Hold Ctrl or Shift to keep the aspect ratio", seconds=10)
        return constrain

    def _on_drag_update(self, gesture, offset_x, offset_y):
        if not self._mode:
            return
        sx, sy = self._drag_start_img
        ix2 = sx + offset_x / self.zoom
        iy2 = sy + offset_y / self.zoom

        if self._mode == 'crop':
            self.pending_crop = {'x': min(sx, ix2), 'y': min(sy, iy2),
                                  'w': abs(ix2 - sx), 'h': abs(iy2 - sy)}
        elif self._mode == 'effect':
            self.pending_effect = {'x': min(sx, ix2), 'y': min(sy, iy2),
                                    'w': abs(ix2 - sx), 'h': abs(iy2 - sy)}
        elif self._mode == 'draw':
            t = self.draft['type']
            if t in ('rect', 'circle'):
                self.draft.update({'x': min(sx, ix2), 'y': min(sy, iy2),
                                    'w': abs(ix2 - sx), 'h': abs(iy2 - sy)})
            else:
                self.draft.update({'x2': ix2, 'y2': iy2})
        elif self._mode == 'move':
            dx, dy = offset_x / self.zoom, offset_y / self.zoom
            kind, obj = self.selected
            orig = self._orig_geom
            if kind == 'layer' or obj['type'] in ('rect', 'circle', 'text'):
                obj['x'] = orig['x'] + dx
                obj['y'] = orig['y'] + dy
            elif obj['type'] == 'polygon':
                obj['points'] = [[ox + dx, oy + dy] for ox, oy in orig['points']]
            else:
                obj['x1'] = orig['x1'] + dx
                obj['y1'] = orig['y1'] + dy
                obj['x2'] = orig['x2'] + dx
                obj['y2'] = orig['y2'] + dy
        elif self._mode == 'resize-layer':
            dx, dy = offset_x / self.zoom, offset_y / self.zoom
            _, obj = self.selected
            orig = self._orig_geom
            constrain = self._resize_constrain_active(gesture)
            new_w = max(15, orig['w'] + dx)
            new_h = max(15, orig['h'] + dy)
            if constrain and orig['w'] and orig['h']:
                ratio = orig['w'] / orig['h']
                if abs(dx) >= abs(dy):
                    new_h = max(15, new_w / ratio)
                else:
                    new_w = max(15, new_h * ratio)
            obj['w'], obj['h'] = new_w, new_h
        elif self._mode == 'annotation-handle':
            _, obj = self.selected
            if obj['type'] in ('rect', 'circle'):
                orig = self._orig_geom
                raw_w = ix2 - orig['x']
                raw_h = iy2 - orig['y']
                constrain = self._resize_constrain_active(gesture)
                new_w = max(4, raw_w)
                new_h = max(4, raw_h)
                if constrain and orig['w'] and orig['h']:
                    ratio = orig['w'] / orig['h']
                    if abs(raw_w) >= abs(raw_h):
                        new_h = max(4, new_w / ratio)
                    else:
                        new_w = max(4, new_h * ratio)
                obj['w'], obj['h'] = new_w, new_h
            elif obj['type'] in ('line', 'arrow'):
                if self._active_handle == 'p1':
                    obj['x1'] = ix2
                    obj['y1'] = iy2
                else:
                    obj['x2'] = ix2
                    obj['y2'] = iy2
        self.queue_draw()

    def _on_drag_end(self, gesture, offset_x, offset_y):
        if self._mode in ('resize-layer', 'annotation-handle'):
            self.app._hide_hint_now()
        if self._mode == 'effect':
            r = self.pending_effect
            if r['w'] > 2 and r['h'] > 2:
                self.apply_effect(self.tool, r)
            self.pending_effect = None
        elif self._mode == 'draw':
            d = self.draft
            valid = True
            if d['type'] in ('rect', 'circle') and (d['w'] < 2 or d['h'] < 2):
                valid = False
            if d['type'] in ('line', 'arrow') and math.hypot(
                    d['x2'] - d['x1'], d['y2'] - d['y1']) < 2:
                valid = False
            if valid:
                self.push_undo()
                d['id'] = self.next_id()
                self.annotations.append(d)
                self.selected = ('annotation', d)
            self.draft = None
        self._mode = None
        self.queue_draw()
        self.app.update_status()

    _ARROW_DELTAS = {
        Gdk.KEY_Left: (-1, 0), Gdk.KEY_Right: (1, 0),
        Gdk.KEY_Up: (0, -1), Gdk.KEY_Down: (0, 1),
    }

    def move_selected_by(self, dx, dy):
        """Move the selected object (layer or annotation) by a given delta.
        Used both for mouse dragging and for the arrow-key nudging below."""
        if not self.selected:
            return False
        kind, obj = self.selected
        if kind == 'layer':
            obj['x'] += dx
            obj['y'] += dy
        else:
            self._shift_annotation(obj, dx, dy)
        self.queue_draw()
        return True

    def _on_key(self, controller, keyval, keycode, state):
        if self.tool == 'crop' and keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.apply_crop()
            return True
        if self.tool == 'polygon' and keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.finish_polygon()
            return True
        if keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            self.delete_selected()
            return True
        if keyval in self._ARROW_DELTAS and self.tool == 'select' and self.selected:
            dx, dy = self._ARROW_DELTAS[keyval]
            step = 10 if (state & Gdk.ModifierType.SHIFT_MASK) else 1
            now = time.monotonic()
            if now - getattr(self, '_last_arrow_move_time', 0) > 0.6:
                self.push_undo()
            self._last_arrow_move_time = now
            self.move_selected_by(dx * step, dy * step)
            self.app.update_status()
            return True
        if keyval == Gdk.KEY_Escape:
            if self.tool == 'crop' and self.pending_crop:
                self.cancel_crop()
            else:
                self.draft = None
                self.pending_crop = None
                self.pending_effect = None
                self.polygon_points = None
                self.queue_draw()
            self.app.set_active_tool('select')
            return True
        return False

    # ---- destructive actions --------------

    def apply_crop(self):
        r = self.pending_crop
        if not r or r['w'] < 2 or r['h'] < 2:
            self.pending_crop = None
            self.queue_draw()
            return
        self.push_undo()
        x, y = max(0, int(r['x'])), max(0, int(r['y']))
        w = min(int(r['w']), self.width - x)
        h = min(int(r['h']), self.height - y)
        new_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(new_surf)
        cr.set_source_surface(self.surface, -x, -y)
        cr.paint()
        self.surface = new_surf
        self.width, self.height = w, h
        self.img_rect = {'x': 0.0, 'y': 0.0, 'w': float(w), 'h': float(h)}
        for layer in self.layers:
            layer['x'] -= x
            layer['y'] -= y
        for ann in self.annotations:
            self._shift_annotation(ann, -x, -y)
        self.selected = None
        self.pending_crop = None
        self.update_content_size()
        self.app.set_status(f"Image cropped: {w}×{h} px.")

    def cancel_crop(self):
        self.pending_crop = None
        self.queue_draw()

    @staticmethod
    def _shift_annotation(ann, dx, dy):
        if ann['type'] in ('rect', 'circle', 'text'):
            ann['x'] += dx
            ann['y'] += dy
        elif ann['type'] == 'polygon':
            ann['points'] = [[px + dx, py + dy] for px, py in ann['points']]
        else:
            ann['x1'] += dx
            ann['y1'] += dy
            ann['x2'] += dx
            ann['y2'] += dy

    def _flatten_and_transform(self, transform_fn, new_w, new_h, message):
        """Flatten the image (layers + annotations) then apply a cairo
        transform (flip, rotate). This keeps those operations simple and
        reliable: layers and annotations get merged into the base image."""
        self.push_undo()
        composite = self.render_composite()
        new_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, new_w, new_h)
        cr = cairo.Context(new_surf)
        transform_fn(cr)
        cr.set_source_surface(composite, 0, 0)
        cr.paint()
        self.surface = new_surf
        self.width, self.height = new_w, new_h
        self.img_rect = {'x': 0.0, 'y': 0.0, 'w': float(new_w), 'h': float(new_h)}
        self.layers = []
        self.annotations = []
        self.selected = None
        self.update_content_size()
        self.app.set_status(message)

    def flip_horizontal(self):
        def t(cr):
            cr.translate(self.width, 0)
            cr.scale(-1, 1)
        self._flatten_and_transform(t, self.width, self.height,
                                     "Image flipped horizontally (layers and annotations merged).")

    def flip_vertical(self):
        def t(cr):
            cr.translate(0, self.height)
            cr.scale(1, -1)
        self._flatten_and_transform(t, self.width, self.height,
                                     "Image flipped vertically (layers and annotations merged).")

    def rotate90(self):
        old_h = self.height

        def t(cr):
            cr.translate(old_h, 0)
            cr.rotate(math.pi / 2)
        self._flatten_and_transform(t, self.height, self.width,
                                     "Image rotated 90° (layers and annotations merged).")

    _ANCHORS = {
        'top-left': (0.0, 0.0), 'top-center': (0.5, 0.0), 'top-right': (1.0, 0.0),
        'middle-left': (0.0, 0.5), 'center': (0.5, 0.5), 'middle-right': (1.0, 0.5),
        'bottom-left': (0.0, 1.0), 'bottom-center': (0.5, 1.0), 'bottom-right': (1.0, 1.0),
    }

    def resize_canvas(self, new_w, new_h, anchor='top-left'):
        """Change the canvas size WITHOUT resampling the base image: this
        adds or removes workspace around it, positioned according to the
        chosen anchor. The image, layers and annotations keep their size
        and shift together."""
        new_w = max(1, int(new_w))
        new_h = max(1, int(new_h))
        if new_w == self.width and new_h == self.height:
            return
        fx, fy = self._ANCHORS.get(anchor, (0.0, 0.0))
        dx = round((new_w - self.width) * fx)
        dy = round((new_h - self.height) * fy)

        self.push_undo()

        new_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, new_w, new_h)
        cr = cairo.Context(new_surf)
        if self.surface:
            cr.set_source_surface(self.surface, dx, dy)
            cr.paint()
        self.surface = new_surf

        for layer in self.layers:
            layer['x'] += dx
            layer['y'] += dy
        for ann in self.annotations:
            self._shift_annotation(ann, dx, dy)
        if self.img_rect:
            self.img_rect = {'x': self.img_rect['x'] + dx, 'y': self.img_rect['y'] + dy,
                              'w': self.img_rect['w'], 'h': self.img_rect['h']}
        else:
            self.img_rect = {'x': float(dx), 'y': float(dy),
                              'w': float(self.width), 'h': float(self.height)}

        self.width, self.height = new_w, new_h
        self.selected = None
        self.update_content_size()
        self.app.set_status(f"Canvas size: {new_w}×{new_h} px "
                             "(the base image kept its original size).")

    def apply_effect(self, kind, rect):
        x, y = max(0, int(rect['x'])), max(0, int(rect['y']))
        w = min(int(rect['w']), self.width - x)
        h = min(int(rect['h']), self.height - y)
        if w < 2 or h < 2:
            return
        self.push_undo()
        composite = self.render_composite()

        region = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        rc = cairo.Context(region)
        rc.set_source_surface(composite, -x, -y)
        rc.paint()

        factor = max(2, int(self.pixelate_level if kind == 'pixelate' else self.blur_level))
        sw, sh = max(1, w // factor), max(1, h // factor)
        small = cairo.ImageSurface(cairo.FORMAT_ARGB32, sw, sh)
        sc = cairo.Context(small)
        sc.scale(sw / w, sh / h)
        sc.set_source_surface(region, 0, 0)
        sc.get_source().set_filter(cairo.FILTER_BILINEAR if kind == 'blur' else cairo.FILTER_NEAREST)
        sc.paint()

        result = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        rc2 = cairo.Context(result)
        rc2.scale(w / sw, h / sh)
        rc2.set_source_surface(small, 0, 0)
        rc2.get_source().set_filter(cairo.FILTER_NEAREST if kind == 'pixelate' else cairo.FILTER_BILINEAR)
        rc2.paint()

        self.surface = composite
        cr3 = cairo.Context(self.surface)
        cr3.rectangle(x, y, w, h)
        cr3.clip()
        cr3.set_source_surface(result, x, y)
        cr3.paint()

        self.layers = []
        self.annotations = []
        self.selected = None
        self.queue_draw()
        label = "blurred" if kind == 'blur' else "pixelated"
        self.app.set_status(f"Area {label} (layers and annotations merged).")

    def finish_polygon(self):
        """Auto-connect the last point back to the first one (Enter) and
        turn the placed points into a solid polygon, filled with the
        current fill color."""
        pts = self.polygon_points
        if not pts or len(pts) < 3:
            self.app.set_status("Add at least 3 points before closing the polygon (Enter).")
            return
        self.push_undo()
        ann = {'id': self.next_id(), 'type': 'polygon',
               'points': [list(p) for p in pts],
               'color': self.color, 'width': self.stroke_width,
               'fill': self.fill_color}
        self.annotations.append(ann)
        self.selected = ('annotation', ann)
        self.polygon_points = None
        self.queue_draw()
        self.app.set_status("Polygon created (closed and filled).")

    # ---- layers ----------------------------------------------------

    def add_layer_from_path(self, path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        except GLib.Error as e:
            self.app.set_status(f"Couldn't open image: {e.message}")
            return
        self._add_layer_from_pixbuf(pixbuf, os.path.basename(path))

    def _add_layer_from_pixbuf(self, pixbuf, name):
        self.push_undo()
        surf = surface_from_pixbuf(pixbuf)
        w, h = pixbuf.get_width(), pixbuf.get_height()
        maxw = self.width * 0.6 if self.width else w
        scale = min(1.0, maxw / w) if w > maxw else 1.0
        dw, dh = w * scale, h * scale
        layer = {
            'id': self.next_id(), 'surface': surf, 'orig_w': w, 'orig_h': h,
            'x': (self.width - dw) / 2, 'y': (self.height - dh) / 2,
            'w': dw, 'h': dh, 'opacity': 1.0, 'name': name,
        }
        self.layers.append(layer)
        self.selected = ('layer', layer)
        self.app.set_active_tool('select')
        self.queue_draw()
        self.app.set_status(f"Layer \u201c{name}\u201d added — drag to move it, "
                             f"bottom-right corner to resize it.")

    def paste_as_layer(self):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.read_texture_async(None, self._on_paste_texture)

    def _on_paste_texture(self, clipboard, result):
        try:
            texture = clipboard.read_texture_finish(result)
        except GLib.Error:
            texture = None
        if texture is None:
            self.app.set_status("No image in the clipboard.")
            return
        try:
            png_bytes = texture.save_to_png_bytes()
            loader = GdkPixbuf.PixbufLoader()
            loader.write(png_bytes.get_data())
            loader.close()
            pixbuf = loader.get_pixbuf()
        except Exception:
            self.app.set_status("Couldn't paste the image from the clipboard.")
            return
        self._add_layer_from_pixbuf(pixbuf, "Clipboard")

    def copy_to_clipboard(self):
        composite = self.render_composite()
        tmp = GLib.build_filenamev([GLib.get_tmp_dir(), f"ie-clip-{next(_ID_GEN)}.png"])
        composite.write_to_png(tmp)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(tmp)
        os.remove(tmp)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        Gdk.Display.get_default().get_clipboard().set_texture(texture)
        self.app.set_status("Image copied to clipboard.")

    # ---- text ----------------------------------------------------

    def add_text(self, x, y, text):
        if not text:
            return
        self.push_undo()
        ann = {'id': self.next_id(), 'type': 'text', 'x': x, 'y': y, 'text': text,
               'font_size': self.font_size, 'color': self.color, 'width': 1.0,
               'fill': self.fill_color if self.fill_enabled else None}
        self.annotations.append(ann)
        self.selected = ('annotation', ann)
        self.queue_draw()
        self.app.update_status()

    def edit_text(self, ann, text):
        if not text:
            return
        self.push_undo()
        ann['text'] = text
        self.selected = ('annotation', ann)
        self.queue_draw()
        self.app.update_status()

    # ---- temporary autosave (crash recovery) ------------------

    @staticmethod
    def _surface_to_b64(surf):
        buf = BytesIO()
        surf.write_to_png(buf)
        return base64.b64encode(buf.getvalue()).decode('ascii')

    @staticmethod
    def _b64_to_surface(b64):
        raw = base64.b64decode(b64)
        return cairo.ImageSurface.create_from_png(BytesIO(raw))

    @staticmethod
    def _ann_to_json(ann):
        d = dict(ann)
        if d.get('color') is not None:
            d['color'] = list(d['color'])
        if d.get('fill') is not None:
            d['fill'] = list(d['fill'])
        return d

    @staticmethod
    def _ann_from_json(d):
        d = dict(d)
        if d.get('color') is not None:
            d['color'] = tuple(d['color'])
        if d.get('fill') is not None:
            d['fill'] = tuple(d['fill'])
        return d

    def autosave_dict(self):
        """Serialize the full, editable document state (base image, layers,
        annotations) so a crash can be recovered faithfully instead of just
        restoring a flattened image."""
        return {
            'version': 1,
            'saved_at': time.time(),
            'original_path': self.current_path,
            'width': self.width,
            'height': self.height,
            'img_rect': dict(self.img_rect) if self.img_rect else None,
            'base_png_b64': self._surface_to_b64(self.surface) if self.surface else None,
            'layers': [
                {'x': l['x'], 'y': l['y'], 'w': l['w'], 'h': l['h'],
                 'orig_w': l['orig_w'], 'orig_h': l['orig_h'],
                 'opacity': l.get('opacity', 1.0), 'name': l.get('name', ''),
                 'png_b64': self._surface_to_b64(l['surface'])}
                for l in self.layers
            ],
            'annotations': [self._ann_to_json(a) for a in self.annotations],
        }

    def load_autosave_dict(self, data):
        self.surface = self._b64_to_surface(data['base_png_b64']) if data.get('base_png_b64') else None
        self.width = data.get('width', 0)
        self.height = data.get('height', 0)
        self.img_rect = dict(data['img_rect']) if data.get('img_rect') else \
            {'x': 0.0, 'y': 0.0, 'w': float(self.width), 'h': float(self.height)}
        self.layers = []
        for l in data.get('layers', []):
            self.layers.append({
                'id': self.next_id(),
                'surface': self._b64_to_surface(l['png_b64']),
                'x': l['x'], 'y': l['y'], 'w': l['w'], 'h': l['h'],
                'orig_w': l.get('orig_w', l['w']), 'orig_h': l.get('orig_h', l['h']),
                'opacity': l.get('opacity', 1.0), 'name': l.get('name', ''),
            })
        self.annotations = [self._ann_from_json(a) for a in data.get('annotations', [])]
        self.current_path = data.get('original_path')
        self.selected = None
        self.undo_stack = []
        self.redo_stack = []
        self.dirty = True   # recovered content hasn't been saved back yet
        self.update_content_size()

    # ---- export / saving ----------------------------------------------------

    def save_to_file(self, path):
        composite = self.render_composite()
        ext = os.path.splitext(path)[1].lower()
        if ext in ('', '.png'):
            composite.write_to_png(path)
            return
        tmp = path + '.tmp.png'
        composite.write_to_png(tmp)
        fmt = {'.jpg': 'jpeg', '.jpeg': 'jpeg', '.bmp': 'bmp',
               '.tiff': 'tiff', '.tif': 'tiff'}.get(ext, 'png')
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(tmp)
            pixbuf.savev(path, fmt, [], [])
        finally:
            os.remove(tmp)


# Main window

class EditorWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Quick Image Editor",
                          default_width=980, default_height=680)
        self.tool_buttons = {}
        self._locked_widgets = []
        self._tabs = []             # one entry per open tab
        self._tab_by_canvas = {}    # Canvas -> tab info
        self._current_canvas = None
        self._closing = False       # avoids re-asking for confirmation in a loop
        self.last_save_folder = load_last_save_folder()

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        header.pack_start(self._icon_header_button("document-open-symbolic",
                                                     tt('open'), self.choose_open))
        self.undo_btn = self._icon_header_button(
            "edit-undo-symbolic", tt('undo'), lambda: self.canvas and self.canvas.undo())
        header.pack_start(self.undo_btn)
        self.redo_btn = self._icon_header_button(
            "edit-redo-symbolic", tt('redo'), lambda: self.canvas and self.canvas.redo())
        header.pack_start(self.redo_btn)
        self.save_menu_btn = self._build_save_menu_button()
        header.pack_start(self.save_menu_btn)
        self.copy_btn = self._icon_header_button(
            "edit-copy-symbolic", tt('copy'),
            lambda: self.canvas.copy_to_clipboard() if self.canvas else None)
        header.pack_end(self.copy_btn)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hbox.set_margin_top(6)
        hbox.set_margin_bottom(6)
        hbox.set_margin_start(6)
        hbox.set_margin_end(6)
        self.set_child(hbox)

        sidebar_scroller = Gtk.ScrolledWindow(vexpand=True)
        sidebar_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroller.set_child(self._build_tools_column())
        hbox.append(sidebar_scroller)
        hbox.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True, vexpand=True)
        right.append(self._build_options_row())

        self.notebook = Gtk.Notebook()
        self.notebook.set_hexpand(True)
        self.notebook.set_vexpand(True)
        self.notebook.set_scrollable(True)
        self.notebook.connect('switch-page', self._on_switch_page)
        new_tab_btn = Gtk.Button()
        new_tab_btn.set_icon_name('list-add-symbolic')
        new_tab_btn.add_css_class('flat')
        new_tab_btn.set_tooltip_text("Open an image in a new tab")
        new_tab_btn.connect('clicked', lambda b: self.choose_open())
        self.notebook.set_action_widget(new_tab_btn, Gtk.PackType.END)
        new_tab_btn.set_visible(True)

        self.canvas_stack = Gtk.Stack()
        self.canvas_stack.set_hexpand(True)
        self.canvas_stack.set_vexpand(True)
        self.canvas_stack.add_named(self._build_empty_state(), 'empty')
        self.canvas_stack.add_named(self.notebook, 'canvas')
        self.canvas_stack.set_visible_child_name('empty')
        right.append(self.canvas_stack)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.add_css_class("dim-label")
        right.append(self.status_label)

        hbox.append(right)

        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._on_window_key)
        self.add_controller(keys)

        self._locked_widgets = [
            self.save_menu_btn, self.copy_btn, self.undo_btn, self.redo_btn,
            *self.tool_buttons.values(), self.shape_button, self.canvas_size_btn,
            self.flip_h_btn, self.flip_v_btn, self.rotate_btn,
            self.add_layer_btn, self.paste_layer_btn,
            self.color_btn, self.width_spin, self.fill_check, self.fill_color_btn,
            self.arrow_head_combo, self.font_spin, self.opacity_spin, self.zoom_combo,
            self.effect_spin,
        ]

        self.connect('close-request', self._on_close_request)

        self.set_active_tool('select')
        self.update_undo_redo()
        self.show_empty_state()

        # Periodically autosave every modified tab, so work can be
        # recovered after a crash.
        GLib.timeout_add_seconds(20, self._autosave_tick)

    # ---- current-tab access ----------------------------------------------------

    @property
    def canvas(self):
        return self._current_canvas

    @canvas.setter
    def canvas(self, value):
        self._current_canvas = value

    # ---- toolbar construction ----------------------------------------------------

    _ICON_CSS = b"""
    .icon-btn { font-size: 20px; min-width: 20px; min-height: 20px; }
    .hint-bubble {
        background-color: rgba(20, 20, 22, 0.85);
        color: #ffffff;
        padding: 8px 16px;
        border-radius: 14px;
        font-size: 13px;
    }
    /* Bigger tabs, so the file name is always readable */
    notebook > header.top > tabs > tab {
        padding: 8px 16px;
        min-height: 38px;
    }
    .ie-tab-label { min-width: 90px; font-size: 13.5px; }
    /* Workspace area: square corners, no rounding */
    .ie-workspace-frame, .ie-workspace-frame > * {
        border-radius: 0;
    }
    """

    def _ensure_icon_css(self):
        if getattr(EditorWindow, '_css_loaded', False):
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(self._ICON_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        EditorWindow._css_loaded = True

    def _icon_header_button(self, icon_name, tooltip, callback):
        b = Gtk.Button()
        b.set_icon_name(icon_name)
        b.set_tooltip_text(tooltip)
        b.connect('clicked', lambda btn: callback())
        return b

    def _make_icon_image(self, source, size=26, fallback_char='?'):
        """Turn an icon (an SVG string, or the name of a PNG file in icons/)
        into a Gtk.Image. Falls back to a plain text glyph if anything goes
        wrong (missing file, no SVG loader, etc.) instead of crashing.

        Important: we do NOT shrink the image down to its display size
        (26px) at load time. We load a much larger texture and only set the
        logical display size via set_pixel_size() — GTK resamples it at
        render time with good filtering, including on HiDPI screens (2x/3x
        scale factor), where a texture pre-shrunk to 26px would come out
        blurry once the compositor scales it back up."""
        try:
            if source.startswith('<svg'):
                data = source.encode('utf-8')
                stream = Gio.MemoryInputStream.new_from_data(data, None)
                render_size = max(size * 4, 96)
                pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                    stream, render_size, render_size, True, None)
            else:
                path = os.path.join(ICONS_DIR, f'{source}.png')
                # Native file resolution (already reasonable, ~160px):
                # no downscaling here.
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            img = Gtk.Image.new_from_paintable(texture)
            img.set_pixel_size(size)
            return img
        except (GLib.Error, Exception):
            lbl = Gtk.Label(label=fallback_char)
            lbl.add_css_class('icon-btn')
            return lbl

    def _tool_button(self, icon, tool, tooltip):
        b = Gtk.Button()
        if icon.startswith('icon:'):
            b.set_icon_name(icon[len('icon:'):])
        elif icon.startswith('file:'):
            b.set_child(self._make_icon_image(icon[len('file:'):]))
        elif icon.startswith('<svg'):
            b.set_child(self._make_icon_image(icon))
        else:
            b.set_label(icon)
            b.add_css_class('icon-btn')
        b.set_tooltip_text(tooltip)
        b.set_size_request(56, 50)
        b.connect('clicked', lambda btn: self.set_active_tool(tool))
        self.tool_buttons[tool] = b
        return b

    def _icon_action_button(self, icon, tooltip, callback, css_class=None):
        if icon.startswith('file:'):
            b = Gtk.Button()
            b.set_child(self._make_icon_image(icon[len('file:'):]))
        elif icon.startswith('<svg'):
            b = Gtk.Button()
            b.set_child(self._make_icon_image(icon))
        else:
            b = Gtk.Button(label=icon)
            b.add_css_class('icon-btn')
        b.set_tooltip_text(tooltip)
        if css_class:
            b.add_css_class(css_class)
        b.set_size_request(56, 50)
        b.connect('clicked', lambda btn: callback())
        return b

    # A single "Save" button (instead of two separate icons): clicking it opens a choice between a quick save and "Save As...".
    def _build_save_menu_button(self):
        btn = Gtk.MenuButton()
        btn.set_icon_name("document-save-symbolic")
        btn.set_tooltip_text(tt('save_menu'))

        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        def make_row(icon_name, label_text, callback):
            row_btn = Gtk.Button()
            row_btn.add_css_class('flat')
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row_box.append(Gtk.Image.new_from_icon_name(icon_name))
            row_box.append(Gtk.Label(label=label_text, xalign=0))
            row_btn.set_child(row_box)
            row_btn.connect('clicked', lambda b: (popover.popdown(), callback()))
            box.append(row_btn)

        make_row("document-save-symbolic", tt('save'), self.save)
        make_row("document-save-as-symbolic", tt('save_as'), self.choose_save_as)

        popover.set_child(box)
        btn.set_popover(popover)
        return btn

    # A single "Shapes" button for rectangle / circle / polygon
    _SHAPE_TOOLS = [
        ('rect', '▭', tt('shape_rect_label'), tt('shape_rect')),
        ('circle', '◯', tt('shape_circle_label'), tt('shape_circle')),
        ('polygon', '⬠', tt('shape_polygon_label'), tt('shape_polygon')),
    ]

    def _build_shape_menu_button(self):
        btn = Gtk.MenuButton()
        btn.set_child(self._make_icon_image('shape'))
        btn.set_size_request(56, 50)
        btn.set_tooltip_text(tt('shape_menu'))

        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        for tool_name, icon, short_label, tooltip in self._SHAPE_TOOLS:
            row_btn = Gtk.Button()
            row_btn.add_css_class('flat')
            row_btn.set_tooltip_text(tooltip)
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            icon_lbl = Gtk.Label(label=icon)
            icon_lbl.add_css_class('icon-btn')
            icon_lbl.set_size_request(24, -1)
            row_box.append(icon_lbl)
            row_box.append(Gtk.Label(label=short_label, xalign=0))
            row_btn.set_child(row_box)
            row_btn.connect('clicked', lambda b, t=tool_name: self._on_shape_chosen(t))
            box.append(row_btn)
        popover.set_child(box)
        btn.set_popover(popover)
        self._shape_popover = popover
        return btn

    def _on_shape_chosen(self, tool_name):
        self._shape_popover.popdown()
        self.set_active_tool(tool_name)

    def _build_tools_column(self):
        self._ensure_icon_css()
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        col.set_margin_top(4)
        col.set_margin_bottom(4)
        col.set_margin_start(4)
        col.set_margin_end(4)

        col.append(self._tool_button('file:select', 'select', tt('select')))
        col.append(self._tool_button('file:crop', 'crop', tt('crop')))

        col.append(Gtk.Separator())

        self.flip_h_btn = self._icon_action_button(
            'file:flip_h', tt('flip_h'), lambda: self.canvas and self.canvas.flip_horizontal())
        col.append(self.flip_h_btn)
        self.flip_v_btn = self._icon_action_button(
            'file:flip_v', tt('flip_v'), lambda: self.canvas and self.canvas.flip_vertical())
        col.append(self.flip_v_btn)
        self.rotate_btn = self._icon_action_button(
            'file:rotate90', tt('rotate90'), lambda: self.canvas and self.canvas.rotate90())
        col.append(self.rotate_btn)
        self.canvas_size_btn = self._icon_action_button(
            'file:canvas_size', tt('canvas_size'), self.open_canvas_size_dialog)
        col.append(self.canvas_size_btn)

        col.append(Gtk.Separator())

        col.append(self._tool_button('file:arrow', 'arrow', tt('arrow')))
        col.append(self._tool_button('file:line', 'line', tt('line')))
        self.shape_button = self._build_shape_menu_button()
        col.append(self.shape_button)
        col.append(self._tool_button('file:text', 'text', tt('text')))

        col.append(Gtk.Separator())

        col.append(self._tool_button('file:blur', 'blur', tt('blur')))
        col.append(self._tool_button('file:pixelate', 'pixelate', tt('pixelate')))

        col.append(Gtk.Separator())

        self.add_layer_btn = self._icon_action_button(
            'file:add_image', tt('add_image'), self.choose_add_layer)
        col.append(self.add_layer_btn)
        self.paste_layer_btn = self._icon_action_button(
            'file:paste_layer', tt('paste_layer'), lambda: self.canvas and self.canvas.paste_as_layer())
        col.append(self.paste_layer_btn)

        return col

    def _build_options_row(self):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.color_btn = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.parse("rgba(235,33,33,1)")
        self.color_btn.set_rgba(rgba)
        self.color_btn.connect('color-set', self._on_color_set)
        self.color_group = self._options_group(Gtk.Label(label="Color:"), self.color_btn)
        row.append(self.color_group)

        self.width_spin = Gtk.SpinButton.new_with_range(0, 40, 1)
        self.width_spin.set_value(4)
        self.width_spin.set_tooltip_text("Stroke width — 0 = no visible border")
        self.width_spin.connect('value-changed', self._on_width_changed)
        self.width_group = self._options_group(Gtk.Label(label="Width:"), self.width_spin)
        row.append(self.width_group)

        self.fill_check = Gtk.CheckButton(label="Fill")
        self.fill_check.set_tooltip_text(
            "Fill the inside of drawn shapes, or add a background behind text")
        self.fill_check.connect('toggled', self._on_fill_toggled)
        self.fill_color_btn = Gtk.ColorButton()
        fill_rgba = Gdk.RGBA()
        fill_rgba.parse("rgba(255,255,255,1)")
        self.fill_color_btn.set_rgba(fill_rgba)
        self.fill_color_btn.set_tooltip_text("Fill color")
        self.fill_color_btn.connect('color-set', self._on_fill_color_set)
        self.fill_group = self._options_group(self.fill_check, self.fill_color_btn)
        row.append(self.fill_group)

        self.arrow_head_combo = Gtk.DropDown.new_from_strings(self._ARROW_HEAD_LABELS)
        self.arrow_head_combo.set_selected(0)
        self.arrow_head_combo.connect('notify::selected', self._on_arrow_head_changed)
        self.arrow_head_group = self._options_group(Gtk.Label(label="Head:"), self.arrow_head_combo)
        row.append(self.arrow_head_group)

        self.font_spin = Gtk.SpinButton.new_with_range(8, 120, 1)
        self.font_spin.set_value(28)
        self.font_spin.connect('value-changed', self._on_font_changed)
        self.font_group = self._options_group(Gtk.Label(label="Text size:"), self.font_spin)
        row.append(self.font_group)

        self.effect_spin = Gtk.SpinButton.new_with_range(2, 60, 1)
        self.effect_spin.set_value(22)
        self.effect_spin.set_tooltip_text("Higher = stronger effect")
        self.effect_spin.connect('value-changed', self._on_effect_level_changed)
        self.effect_group = self._options_group(Gtk.Label(label="Intensity:"), self.effect_spin)
        row.append(self.effect_group)

        self.opacity_spin = Gtk.SpinButton.new_with_range(0, 100, 5)
        self.opacity_spin.set_value(100)
        self.opacity_spin.connect('value-changed', self._on_opacity_changed)
        self.opacity_group = self._options_group(
            Gtk.Label(label="Selected layer opacity:"), self.opacity_spin)
        row.append(self.opacity_group)

        row.append(Gtk.Separator())
        zoom_label = Gtk.Label(label="Zoom:")
        zoom_label.set_tooltip_text(
            "Tip: Ctrl + mouse wheel, or Ctrl + trackpad scroll, "
            "zooms in/out right on the canvas.")
        row.append(zoom_label)
        self.zoom_combo = Gtk.DropDown.new_from_strings(
            ["50%", "75%", "100%", "150%", "200%", "300%", "Fit"])
        self.zoom_combo.set_selected(2)
        self.zoom_combo.connect('notify::selected', self._on_zoom_changed)
        row.append(self.zoom_combo)

        return row

    @staticmethod
    def _options_group(*widgets):
        """Group a label/control (preceded by a separator) so they can be
        shown or hidden together depending on the active tool/selection."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.append(Gtk.Separator())
        for w in widgets:
            box.append(w)
        return box

    # ---- callbacks ----------------------------------------------------

    _ARROW_HEAD_VALUES = ['end', 'start', 'both', 'none']
    _ARROW_HEAD_LABELS = ["End", "Start", "Both", "None"]

    def _on_color_set(self, btn):
        rgba = btn.get_rgba()
        color = (rgba.red, rgba.green, rgba.blue, rgba.alpha)
        self.canvas.color = color
        sel = self.canvas.selected
        if sel and sel[0] == 'annotation' and sel[1]['type'] in ('arrow', 'line', 'rect', 'circle', 'text', 'polygon'):
            sel[1]['color'] = color
            self.canvas.queue_draw()

    def _on_fill_toggled(self, check):
        enabled = check.get_active()
        self.canvas.fill_enabled = enabled
        sel = self.canvas.selected
        if sel and sel[0] == 'annotation' and sel[1]['type'] in ('rect', 'circle', 'polygon', 'text'):
            sel[1]['fill'] = self.canvas.fill_color if enabled else None
            self.canvas.queue_draw()

    def _on_fill_color_set(self, btn):
        rgba = btn.get_rgba()
        color = (rgba.red, rgba.green, rgba.blue, rgba.alpha)
        self.canvas.fill_color = color
        sel = self.canvas.selected
        if sel and sel[0] == 'annotation' and sel[1]['type'] in ('rect', 'circle', 'polygon', 'text') \
                and sel[1].get('fill') is not None:
            sel[1]['fill'] = color
            self.canvas.queue_draw()

    def _on_width_changed(self, spin):
        value = spin.get_value()
        self.canvas.stroke_width = value
        sel = self.canvas.selected
        if sel and sel[0] == 'annotation' and sel[1]['type'] in ('arrow', 'line', 'rect', 'circle', 'polygon'):
            sel[1]['width'] = value
            self.canvas.queue_draw()

    def _on_font_changed(self, spin):
        value = spin.get_value()
        self.canvas.font_size = value
        sel = self.canvas.selected
        if sel and sel[0] == 'annotation' and sel[1]['type'] == 'text':
            sel[1]['font_size'] = value
            self.canvas.queue_draw()

    def _on_arrow_head_changed(self, dropdown, _pspec=None):
        value = self._ARROW_HEAD_VALUES[dropdown.get_selected()]
        self.canvas.arrow_head_style = value
        sel = self.canvas.selected
        if sel and sel[0] == 'annotation' and sel[1]['type'] == 'arrow':
            sel[1]['head_style'] = value
            self.canvas.queue_draw()

    def _on_effect_level_changed(self, spin):
        if not self.canvas:
            return
        value = int(spin.get_value())
        if self.canvas.tool == 'pixelate':
            self.canvas.pixelate_level = value
        else:
            self.canvas.blur_level = value

    def _on_opacity_changed(self, spin):
        if self.canvas.selected and self.canvas.selected[0] == 'layer':
            self.canvas.selected[1]['opacity'] = spin.get_value() / 100.0
            self.canvas.queue_draw()

    def _on_zoom_changed(self, dropdown, _pspec):
        if not self.canvas:
            return
        idx = dropdown.get_selected()
        values = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, None]
        v = values[idx]
        if v is None:
            parent_w = self.canvas.get_parent().get_width() or 900
            v = max(0.1, min(1.0, (parent_w - 20) / max(1, self.canvas.width)))
        self.canvas.set_zoom(v)

    def _on_window_key(self, controller, keyval, keycode, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            if self.canvas:
                self.canvas.undo()
            return True
        if ctrl and keyval in (Gdk.KEY_y, Gdk.KEY_Y):
            if self.canvas:
                self.canvas.redo()
            return True
        if ctrl and keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self.save()
            return True
        if ctrl and keyval in (Gdk.KEY_o, Gdk.KEY_O):
            self.choose_open()
            return True
        return False

    def set_active_tool(self, tool):
        for name, btn in self.tool_buttons.items():
            if name == tool:
                btn.add_css_class('suggested-action')
            else:
                btn.remove_css_class('suggested-action')
        if tool in ('rect', 'circle', 'polygon'):
            self.shape_button.add_css_class('suggested-action')
        else:
            self.shape_button.remove_css_class('suggested-action')
        if not self.canvas:
            return
        self.canvas.tool = tool
        self.canvas.draft = None
        self.canvas.polygon_points = None
        if tool == 'crop':
            self._show_hint("↵ Enter: confirm the crop  ·  Esc: cancel")
        elif tool == 'polygon':
            self._show_hint("Click to place points  ·  ↵ Enter: close and fill  ·  "
                             "Esc: cancel", seconds=6)
        else:
            self.canvas.pending_crop = None
            self._hide_hint_now()
        self.canvas.queue_draw()
        self.update_status()

    def _show_hint(self, text, seconds=4):
        """Show a transient info bubble above the canvas (crop, polygon,
        proportional resize...)."""
        tab = self._tab_by_canvas.get(self.canvas)
        if not tab:
            return
        bubble = tab['hint_bubble']
        bubble.set_text(text)
        bubble.set_visible(True)
        if tab['hint_timeout']:
            GLib.source_remove(tab['hint_timeout'])
        tab['hint_timeout'] = GLib.timeout_add_seconds(seconds, self._hide_hint, tab)

    def _hide_hint(self, tab=None):
        if tab is None:
            tab = self._tab_by_canvas.get(self.canvas)
        if not tab:
            return False
        tab['hint_bubble'].set_visible(False)
        tab['hint_timeout'] = None
        return False

    def _hide_hint_now(self):
        tab = self._tab_by_canvas.get(self.canvas)
        if not tab:
            return
        if tab['hint_timeout']:
            GLib.source_remove(tab['hint_timeout'])
            tab['hint_timeout'] = None
        tab['hint_bubble'].set_visible(False)

    # ---- empty state / button locking ----------------------------------------------------

    def _build_empty_state(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_hexpand(True)
        box.set_vexpand(True)

        icon = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
        icon.set_pixel_size(64)
        icon.add_css_class("dim-label")
        box.append(icon)

        title = Gtk.Label(label="No image open")
        title.add_css_class("title-2")
        box.append(title)

        subtitle = Gtk.Label(label="Open an image to start editing. Each image you open "
                                    "is added as a new tab.")
        subtitle.add_css_class("dim-label")
        box.append(subtitle)

        open_btn = Gtk.Button(label="Open an image…")
        open_btn.add_css_class("suggested-action")
        open_btn.set_halign(Gtk.Align.CENTER)
        open_btn.connect('clicked', lambda b: self.choose_open())
        box.append(open_btn)

        return box

    def show_empty_state(self):
        """No tab open: no blank canvas shown, and every button disabled
        except the ones that let you open an image."""
        self.canvas_stack.set_visible_child_name('empty')
        for w in self._locked_widgets:
            w.set_sensitive(False)
        self._update_window_title()

    def show_canvas(self):
        """At least one tab is open: show the tab strip and re-enable
        the buttons."""
        self.canvas_stack.set_visible_child_name('canvas')
        for w in self._locked_widgets:
            w.set_sensitive(True)
        self.update_undo_redo()

    def update_undo_redo(self):
        if not self.canvas:
            self.undo_btn.set_sensitive(False)
            self.redo_btn.set_sensitive(False)
            return
        self.undo_btn.set_sensitive(bool(self.canvas.undo_stack))
        self.redo_btn.set_sensitive(bool(self.canvas.redo_stack))

    def update_status(self):
        if not self.canvas:
            self.status_label.set_text("")
            self.update_undo_redo()
            self.update_options_visibility()
            self._update_window_title()
            return
        tab = self._tab_by_canvas.get(self.canvas)
        if tab:
            self._update_tab_label(tab)
        self._update_window_title()
        if self.canvas.width:
            zoom_pct = int(round(self.canvas.zoom * 100))
            self.status_label.set_text(
                f"{self.canvas.width}×{self.canvas.height} px — zoom {zoom_pct}% — "
                f"tool: {self.canvas.tool}")
        self.update_undo_redo()
        self.update_options_visibility()
        self.sync_selection_controls()

    def update_options_visibility(self):
        """Only show the color / fill / width / text / arrowhead / opacity
        controls when they're relevant to the active tool or to whatever
        is currently selected."""
        if not self.canvas:
            for grp in (self.color_group, self.width_group, self.fill_group,
                        self.arrow_head_group, self.font_group, self.opacity_group,
                        self.effect_group):
                grp.set_visible(False)
            return

        tool = self.canvas.tool
        sel = self.canvas.selected
        sel_type = sel[1]['type'] if sel and sel[0] == 'annotation' else None
        sel_is_layer = bool(sel and sel[0] == 'layer')

        color_types = ('arrow', 'line', 'rect', 'circle', 'text', 'polygon')
        width_types = ('arrow', 'line', 'rect', 'circle', 'polygon')
        fill_types = ('rect', 'circle', 'polygon', 'text')

        self.color_group.set_visible(tool in color_types or sel_type in color_types)
        self.width_group.set_visible(tool in width_types or sel_type in width_types)
        self.fill_group.set_visible(tool in fill_types or sel_type in fill_types)
        self.arrow_head_group.set_visible(tool == 'arrow' or sel_type == 'arrow')
        self.font_group.set_visible(tool == 'text' or sel_type == 'text')
        self.opacity_group.set_visible(sel_is_layer)

        self.effect_group.set_visible(tool in ('blur', 'pixelate'))
        if tool == 'pixelate':
            self.effect_spin.set_value(self.canvas.pixelate_level)
        elif tool == 'blur':
            self.effect_spin.set_value(self.canvas.blur_level)

    def sync_selection_controls(self):
        """Make the controls (color, width, fill, text size, arrowhead)
        reflect the currently selected object's values, so they can be
        edited live."""
        if not self.canvas:
            return
        sel = self.canvas.selected
        if not (sel and sel[0] == 'annotation'):
            return
        ann = sel[1]
        t = ann['type']

        if 'color' in ann:
            r, g, b, a = ann['color']
            rgba = Gdk.RGBA()
            rgba.red, rgba.green, rgba.blue, rgba.alpha = r, g, b, a
            self.color_btn.set_rgba(rgba)

        if t in ('arrow', 'line', 'rect', 'circle', 'polygon'):
            self.width_spin.set_value(ann['width'])

        if t in ('rect', 'circle', 'polygon', 'text'):
            fill = ann.get('fill')
            self.fill_check.set_active(fill is not None)
            if fill is not None:
                r, g, b, a = fill
                rgba = Gdk.RGBA()
                rgba.red, rgba.green, rgba.blue, rgba.alpha = r, g, b, a
                self.fill_color_btn.set_rgba(rgba)

        if t == 'text':
            self.font_spin.set_value(ann['font_size'])

        if t == 'arrow':
            style = ann.get('head_style', 'end')
            idx = self._ARROW_HEAD_VALUES.index(style) if style in self._ARROW_HEAD_VALUES else 0
            self.arrow_head_combo.set_selected(idx)

    # ---- tabs ----------------------------------------------------------------------------

    def _tab_display_name(self, tab):
        path = tab['canvas'].current_path
        return os.path.basename(path) if path else "Untitled"

    def _update_tab_label(self, tab):
        name = self._tab_display_name(tab)
        marker = "● " if tab['canvas'].dirty else ""
        tab['label'].set_text(f"{marker}{name}")
        tab['label'].set_tooltip_text(tab['canvas'].current_path or "Never saved")

    def _update_window_title(self):
        if not self.canvas:
            self.set_title("Quick Image Editor")
            return
        tab = self._tab_by_canvas.get(self.canvas)
        name = self._tab_display_name(tab) if tab else "Untitled"
        marker = "● " if self.canvas.dirty else ""
        self.set_title(f"{marker}{name} — Quick Image Editor")

    def _add_tab(self, canvas):
        """Add a new tab holding `canvas` and make it active."""
        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroller.set_child(canvas)
        frame = Gtk.Frame(hexpand=True, vexpand=True)
        frame.set_child(scroller)
        frame.add_css_class('ie-workspace-frame')

        overlay = Gtk.Overlay()
        overlay.set_child(frame)
        hint_bubble = Gtk.Label(label="")
        hint_bubble.add_css_class('hint-bubble')
        hint_bubble.set_halign(Gtk.Align.CENTER)
        hint_bubble.set_valign(Gtk.Align.START)
        hint_bubble.set_margin_top(14)
        hint_bubble.set_visible(False)
        hint_bubble.set_can_target(False)
        overlay.add_overlay(hint_bubble)

        label = Gtk.Label()
        label.add_css_class('ie-tab-label')
        label.set_width_chars(8)
        label.set_max_width_chars(24)
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        close_btn = Gtk.Button()
        close_btn.set_icon_name('window-close-symbolic')
        close_btn.add_css_class('flat')
        close_btn.set_tooltip_text("Close tab")
        tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tab_box.append(label)
        tab_box.append(close_btn)

        tab = {
            'canvas': canvas, 'page': overlay, 'tab_box': tab_box, 'label': label,
            'hint_bubble': hint_bubble, 'hint_timeout': None,
        }
        close_btn.connect('clicked', lambda b: self._request_close_tab(tab))

        self._tabs.append(tab)
        self._tab_by_canvas[canvas] = tab
        page_num = self.notebook.append_page(overlay, tab_box)
        self.notebook.set_tab_reorderable(overlay, True)
        self._update_tab_label(tab)
        self.show_canvas()
        self.notebook.set_current_page(page_num)
        # set_current_page only fires 'switch-page' if the page actually changes
        self.canvas = canvas
        self.set_active_tool('select')
        return tab

    def _on_switch_page(self, notebook, page_widget, page_num):
        for tab in self._tabs:
            if tab['page'] is page_widget:
                self.canvas = tab['canvas']
                self.set_active_tool(tab['canvas'].tool)
                return

    def _request_close_tab(self, tab):
        if tab['canvas'].dirty:
            self._confirm_close_tab(tab)
        else:
            self._close_tab(tab)

    def _confirm_close_tab(self, tab):
        name = self._tab_display_name(tab)
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
            text="Unsaved changes",
            secondary_text=f"\u201c{name}\u201d has unsaved changes. "
                           f"Do you want to save them before closing this tab?")
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL,
                            "Don't Save", Gtk.ResponseType.NO,
                            "Save", Gtk.ResponseType.YES)
        dialog.set_default_response(Gtk.ResponseType.YES)
        dialog.connect('response', self._on_confirm_close_tab_response, tab)
        dialog.present()

    def _on_confirm_close_tab_response(self, dialog, response, tab):
        dialog.destroy()
        if response == Gtk.ResponseType.CANCEL:
            return
        if response == Gtk.ResponseType.YES:
            self._save_tab_then(tab, lambda ok: self._close_tab(tab) if ok else None)
        else:
            self._close_tab(tab)

    def _close_tab(self, tab):
        canvas = tab['canvas']
        delete_autosave(canvas)
        if tab['hint_timeout']:
            GLib.source_remove(tab['hint_timeout'])
        page_num = self.notebook.page_num(tab['page'])
        if page_num != -1:
            self.notebook.remove_page(page_num)
        if tab in self._tabs:
            self._tabs.remove(tab)
        self._tab_by_canvas.pop(canvas, None)
        if not self._tabs:
            self.canvas = None
            self.show_empty_state()
            self.update_status()

    def _save_tab_then(self, tab, callback):
        """Save `tab` (to its existing path, or through a "Save As" dialog
        if it doesn't have one yet), then call callback(success: bool).
        Never shows the same dialog twice."""
        canvas = tab['canvas']
        if canvas.current_path:
            try:
                canvas.save_to_file(canvas.current_path)
                canvas.dirty = False
                self._update_tab_label(tab)
                self._update_window_title()
                delete_autosave(canvas)
                self.set_status(f"Saved: {canvas.current_path}")
                callback(True)
            except Exception as e:
                self.set_status(f"Save failed: {e}")
                callback(False)
            return

        dialog = Gtk.FileDialog()
        dialog.set_title("Save As")
        dialog.set_initial_name("edited-image.png")
        self._apply_last_save_folder(dialog)

        def on_done(d, result):
            try:
                file = d.save_finish(result)
            except GLib.Error:
                callback(False)
                return
            if not file:
                callback(False)
                return
            path = file.get_path()
            canvas.current_path = path
            canvas.save_to_file(path)
            canvas.dirty = False
            self._update_tab_label(tab)
            self._update_window_title()
            delete_autosave(canvas)
            self._remember_save_folder(path)
            self.set_status(f"Saved: {path}")
            callback(True)

        dialog.save(self, None, on_done)

    # ---- autosave & crash recovery -------------------------------

    def _autosave_tick(self):
        for tab in self._tabs:
            write_autosave(tab['canvas'])
        return True  # keep the timer running indefinitely

    def _cleanup_all_autosaves(self):
        for tab in self._tabs:
            delete_autosave(tab['canvas'])

    def offer_recovery(self, paths):
        n = len(paths)
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
            text="Recover from an unexpected shutdown",
            secondary_text=(
                f"{n} image{'s' if n > 1 else ''} weren't closed normally in the last "
                f"session (crash, power loss...). Do you want to recover "
                f"{'them' if n > 1 else 'it'}?"))
        dialog.add_buttons("Discard", Gtk.ResponseType.NO,
                            "Recover", Gtk.ResponseType.YES)
        dialog.set_default_response(Gtk.ResponseType.YES)
        dialog.connect('response', self._on_recovery_response, paths)
        dialog.present()

    def _on_recovery_response(self, dialog, response, paths):
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            recovered = 0
            for p in paths:
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    canvas = Canvas(self)
                    canvas.load_autosave_dict(data)
                    # Reuse the same id so future autosaves overwrite this same file instead of creating another one.
                    canvas.autosave_id = os.path.splitext(os.path.basename(p))[0]
                    self._add_tab(canvas)
                    recovered += 1
                except Exception:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            if recovered:
                GLib.idle_add(self.fit_to_window)
                self.set_status(f"{recovered} image(s) recovered from autosave.")
        else:
            for p in paths:
                try:
                    os.remove(p)
                except OSError:
                    pass

    # ---- window closing --------------------------------------------------------------

    def _on_close_request(self, *_a):
        if self._closing:
            return False
        dirty_tabs = [t for t in self._tabs if t['canvas'].dirty]
        if not dirty_tabs:
            self._cleanup_all_autosaves()
            return False
        self._confirm_quit(dirty_tabs)
        return True

    def _confirm_quit(self, dirty_tabs):
        names = ", ".join(f"\u201c{self._tab_display_name(t)}\u201d" for t in dirty_tabs)
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
            text="Unsaved changes",
            secondary_text=f"You have unsaved changes in: {names}.\n"
                           f"Do you want to save them before closing?")
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL,
                            "Don't Save", Gtk.ResponseType.NO,
                            "Save All and Close", Gtk.ResponseType.YES)
        dialog.set_default_response(Gtk.ResponseType.YES)
        dialog.connect('response', self._on_confirm_quit_response, list(dirty_tabs))
        dialog.present()

    def _on_confirm_quit_response(self, dialog, response, dirty_tabs):
        dialog.destroy()
        if response == Gtk.ResponseType.CANCEL:
            return
        if response == Gtk.ResponseType.NO:
            self._cleanup_all_autosaves()
            self._closing = True
            self.close()
            return

        remaining = list(dirty_tabs)

        def step(ok=True):
            if not ok:
                return  # save cancelled/failed: don't push further, don't close
            if not remaining:
                self._cleanup_all_autosaves()
                self._closing = True
                self.close()
                return
            self._save_tab_then(remaining.pop(0), step)

        step()

    def set_status(self, text):
        self.status_label.set_text(text)
        GLib.timeout_add_seconds(4, self._restore_status)

    def _restore_status(self):
        self.update_status()
        return False

    # ---- dialogs ----------------------------------------------------

    def open_canvas_size_dialog(self):
        if not self.canvas:
            return
        dialog = Gtk.Dialog(title="Canvas Size", transient_for=self, modal=True)
        dialog.set_default_size(380, -1)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)
        box.set_spacing(10)

        info = Gtk.Label(
            label="Enlarge or shrink the workspace: the base image keeps its "
                  "original size, it's only repositioned.",
            wrap=True, xalign=0)
        box.append(info)

        img_rect = self.canvas.img_rect
        img_w = int(img_rect['w']) if img_rect else int(self.canvas.width)
        img_h = int(img_rect['h']) if img_rect else int(self.canvas.height)
        size_hint = f"Loaded image size: {img_w} × {img_h} px"
        if (img_w, img_h) != (int(self.canvas.width), int(self.canvas.height)):
            size_hint += f"  (current canvas: {int(self.canvas.width)} × {int(self.canvas.height)} px)"

        hint_label = Gtk.Label(label=size_hint, xalign=0, wrap=True)
        hint_label.add_css_class('dim-label')
        hint_label.set_tooltip_text(
            "A reference for how much bigger to make the canvas compared "
            "to the currently loaded image.")
        box.append(hint_label)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        w_spin = Gtk.SpinButton.new_with_range(1, 20000, 10)
        w_spin.set_value(self.canvas.width)
        w_spin.set_tooltip_text(size_hint)
        h_spin = Gtk.SpinButton.new_with_range(1, 20000, 10)
        h_spin.set_value(self.canvas.height)
        h_spin.set_tooltip_text(size_hint)
        grid.attach(Gtk.Label(label="Width:", xalign=0), 0, 0, 1, 1)
        grid.attach(w_spin, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Height:", xalign=0), 0, 1, 1, 1)
        grid.attach(h_spin, 1, 1, 1, 1)
        box.append(grid)

        link_check = Gtk.CheckButton(label="Link width and height (scale up proportionally)")
        link_check.set_tooltip_text(
            "When checked, changing one dimension automatically adjusts "
            "the other to keep the same width/height ratio.")
        link_check.set_active(True)
        box.append(link_check)

        link_state = {
            'ratio': (self.canvas.width / self.canvas.height) if self.canvas.height else 1.0,
            'updating': False,
        }

        def on_w_changed(spin):
            if link_state['updating'] or not link_check.get_active():
                return
            link_state['updating'] = True
            h_spin.set_value(max(1, round(spin.get_value() / link_state['ratio'])))
            link_state['updating'] = False

        def on_h_changed(spin):
            if link_state['updating'] or not link_check.get_active():
                return
            link_state['updating'] = True
            w_spin.set_value(max(1, round(spin.get_value() * link_state['ratio'])))
            link_state['updating'] = False

        def on_link_toggled(check):
            if check.get_active() and h_spin.get_value():
                link_state['ratio'] = w_spin.get_value() / h_spin.get_value()

        w_spin.connect('value-changed', on_w_changed)
        h_spin.connect('value-changed', on_h_changed)
        link_check.connect('toggled', on_link_toggled)

        box.append(Gtk.Label(label="Image position in the new canvas:", xalign=0))

        anchor_order = [
            'top-left', 'top-center', 'top-right',
            'middle-left', 'center', 'middle-right',
            'bottom-left', 'bottom-center', 'bottom-right',
        ]
        anchor_state = {'value': 'top-left'}
        anchor_btns = {}

        def pick(anchor):
            anchor_state['value'] = anchor
            for a, b in anchor_btns.items():
                b.set_active(a == anchor)

        def on_toggle(btn, anchor):
            if btn.get_active():
                pick(anchor)
            elif anchor_state['value'] == anchor:
                btn.set_active(True)

        anchor_grid = Gtk.Grid(column_spacing=4, row_spacing=4)
        anchor_grid.set_halign(Gtk.Align.CENTER)
        for i, anchor in enumerate(anchor_order):
            btn = Gtk.ToggleButton()
            btn.set_size_request(34, 34)
            btn.connect('toggled', on_toggle, anchor)
            anchor_btns[anchor] = btn
            anchor_grid.attach(btn, i % 3, i // 3, 1, 1)
        anchor_btns['top-left'].set_active(True)
        box.append(anchor_grid)

        dialog.set_default_response(Gtk.ResponseType.OK)

        def on_response(d, resp):
            if resp == Gtk.ResponseType.OK:
                self.canvas.resize_canvas(w_spin.get_value(), h_spin.get_value(), anchor_state['value'])
            d.destroy()

        dialog.connect('response', on_response)
        dialog.present()

    def prompt_text(self, x, y, edit=None):
        dialog = Gtk.Dialog(title="Edit Text" if edit else "Add Text",
                             transient_for=self, modal=True)
        dialog.set_default_size(360, -1)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        entry.set_text(edit['text'] if edit else "")
        entry.set_activates_default(True)
        entry.set_hexpand(True)
        box = dialog.get_content_area()
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)
        box.set_spacing(8)
        box.append(entry)
        dialog.set_default_response(Gtk.ResponseType.OK)

        def on_response(d, resp):
            if resp == Gtk.ResponseType.OK:
                text = entry.get_text().strip()
                if edit:
                    self.canvas.edit_text(edit, text)
                else:
                    self.canvas.add_text(x, y, text)
            d.destroy()

        dialog.connect('response', on_response)
        dialog.present()

    # ---- files ----------------------------------------------------

    def _apply_last_save_folder(self, dialog):
        if self.last_save_folder and os.path.isdir(self.last_save_folder):
            dialog.set_initial_folder(Gio.File.new_for_path(self.last_save_folder))

    def _remember_save_folder(self, path):
        folder = os.path.dirname(path)
        if folder and os.path.isdir(folder) and folder != self.last_save_folder:
            self.last_save_folder = folder
            save_last_save_folder(folder)

    def choose_open(self):
        dialog = Gtk.FileDialog()
        dialog.set_title("Open an Image")
        filters = Gio.ListStore(item_type=Gtk.FileFilter)
        f = Gtk.FileFilter()
        f.set_name("Images")
        for m in ("image/png", "image/jpeg", "image/bmp", "image/tiff", "image/webp"):
            f.add_mime_type(m)
        filters.append(f)
        dialog.set_filters(filters)

        def on_done(d, result):
            try:
                file = d.open_finish(result)
            except GLib.Error:
                return
            if file:
                self.open_path(file.get_path())

        dialog.open(self, None, on_done)

    def choose_add_layer(self):
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose an Image to Overlay")
        filters = Gio.ListStore(item_type=Gtk.FileFilter)
        f = Gtk.FileFilter()
        f.set_name("Images")
        for m in ("image/png", "image/jpeg"):
            f.add_mime_type(m)
        filters.append(f)
        dialog.set_filters(filters)

        def on_done(d, result):
            try:
                file = d.open_finish(result)
            except GLib.Error:
                return
            if file and self.canvas:
                self.canvas.add_layer_from_path(file.get_path())

        dialog.open(self, None, on_done)

    def choose_save_as(self):
        """"Save As" always asks for a new location, even if the active
        tab already has an associated file — unlike `save()`."""
        canvas = self.canvas
        if not canvas:
            return
        tab = self._tab_by_canvas.get(canvas)
        dialog = Gtk.FileDialog()
        dialog.set_title("Save As")
        dialog.set_initial_name(
            os.path.basename(canvas.current_path) if canvas.current_path else "edited-image.png")
        self._apply_last_save_folder(dialog)

        def on_done(d, result):
            try:
                file = d.save_finish(result)
            except GLib.Error:
                return
            if file:
                path = file.get_path()
                canvas.current_path = path
                canvas.save_to_file(path)
                canvas.dirty = False
                if tab:
                    self._update_tab_label(tab)
                self._update_window_title()
                delete_autosave(canvas)
                self._remember_save_folder(path)
                self.set_status(f"Saved: {path}")

        dialog.save(self, None, on_done)

    def open_path(self, path, delete_after_load=False):
        """Open an image in a new tab (doesn't touch tabs already open).
        If delete_after_load is true (an ephemeral screenshot launched
        from the extension), the source file is deleted once its content
        is loaded into memory, and the tab stays "Untitled": this avoids
        silently overwriting that temporary file if the user then clicks
        "Save"."""
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        except GLib.Error as e:
            self.set_status(f"Couldn't open: {e.message}")
            return
        canvas = Canvas(self)
        canvas.load_pixbuf(pixbuf)
        if delete_after_load:
            try:
                os.remove(path)
            except OSError:
                pass
            cleanup_stray_screenshots()
        else:
            canvas.current_path = path
        self._add_tab(canvas)
        self.update_status()
        GLib.idle_add(self.fit_to_window)

    def new_blank_tab(self):
        """Open a blank canvas in a new tab (explicit request via the
        --blank command-line flag)."""
        canvas = Canvas(self)
        canvas.new_blank()
        self._add_tab(canvas)
        GLib.idle_add(self.fit_to_window)

    def fit_to_window(self, attempts=0):
        """Adjust the zoom so the image fits in the window. On the very
        first display, the window sometimes doesn't have its real size
        yet (get_width/get_height return 0 or 1): retry a few times before
        computing, which avoids the tiny-canvas-in-the-corner glitch."""
        if not self.canvas or not self.canvas.width or not self.canvas.height:
            return False
        w, h = self.get_width(), self.get_height()
        if (w <= 1 or h <= 1) and attempts < 20:
            GLib.timeout_add(30, self.fit_to_window, attempts + 1)
            return False
        if w <= 1 or h <= 1:
            w, h = self.get_default_size()
        avail_w = max(200, w - 90)
        avail_h = max(200, h - 140)
        zoom = min(1.0, avail_w / self.canvas.width, avail_h / self.canvas.height)
        self.canvas.set_zoom(max(0.05, zoom))
        return False

    def save(self):
        """"Save": writes directly to the active tab's existing file, or
        asks for a location if it doesn't have one yet."""
        if not self.canvas:
            return
        tab = self._tab_by_canvas.get(self.canvas)
        if tab:
            self._save_tab_then(tab, lambda ok: None)


# Entry point

def main():
    args = sys.argv[1:]
    blank = '--blank' in args
    from_screenshot = '--from-screenshot' in args
    path = None
    for a in args:
        if a not in ('--blank', '--from-screenshot') and not a.startswith('-'):
            path = a
            break

    # No Gio.ApplicationFlags.NON_UNIQUE: the app is a single instance
    app = Gtk.Application(application_id=APP_ID)

    def on_activate(a):
        existing_windows = a.get_windows()
        if existing_windows:
            # Already running: bring its window to the front instead of pening a second one.
            win = existing_windows[0]
            win.present()
        else:
            win = EditorWindow(a)
            win.present()

            leftovers = list_leftover_autosaves()
            if leftovers:
                win.offer_recovery(leftovers)

        if path and os.path.isfile(path):
            win.open_path(path, delete_after_load=from_screenshot)
        elif blank:
            win.new_blank_tab()
        # Otherwise: nothing to show yet, stay on the default empty state

    app.connect('activate', on_activate)
    app.run([sys.argv[0]])


if __name__ == '__main__':
    main()
