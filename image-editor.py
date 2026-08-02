#!/usr/bin/env python3
"""
Quick Image Editor - companion app for the "image-editor" GNOME Shell extension.

What it does:
  - Open / blank canvas / save / save as
  - Crop, flip horizontal/vertical, rotate 90°
  - Arrows, lines, rectangles, circles, polygons, text
  - Blur and pixelate an area (non-destructive: each stays its own movable
    layer, erasable at any time to reveal the original pixels again)
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
import threading
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

# Language detection for the whole UI (tooltips, labels, dialogs, status
# messages...).

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
UI_STRINGS = {
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
    'context_copy': {
        'fr': "Copier", 'en': "Copy", 'es': "Copiar", 'de': "Kopieren", 'it': "Copia", 'pt': "Copiar",
    },
    'context_paste': {
        'fr': "Coller", 'en': "Paste", 'es': "Pegar", 'de': "Einfügen", 'it': "Incolla", 'pt': "Colar",
    },
    'context_duplicate': {
        'fr': "Dupliquer", 'en': "Duplicate", 'es': "Duplicar",
        'de': "Duplizieren", 'it': "Duplica", 'pt': "Duplicar",
    },
    'status_layer_duplicated': {
        'fr': "Calque « {name} » dupliqué.", 'en': "Layer \u201c{name}\u201d duplicated.",
        'es': "Capa «{name}» duplicada.", 'de': "Ebene „{name}“ dupliziert.",
        'it': "Livello «{name}» duplicato.", 'pt': "Camada «{name}» duplicada.",
    },
    'status_layer_copy_unsupported': {
        'fr': "Cette zone (flou/pixellisation) n'a pas d'image propre à copier.",
        'en': "This area (blur/pixelate) has no image of its own to copy.",
        'es': "Esta zona (difuminado/pixelado) no tiene una imagen propia para copiar.",
        'de': "Dieser Bereich (Weichzeichnen/Pixelieren) hat kein eigenes Bild zum Kopieren.",
        'it': "Quest'area (sfocatura/pixelizzazione) non ha un'immagine propria da copiare.",
        'pt': "Esta área (desfoque/pixelização) não tem uma imagem própria para copiar.",
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
    'effect_blur_name': {
        'fr': "Flou", 'en': "Blur", 'es': "Desenfoque",
        'de': "Weichzeichner", 'it': "Sfocatura", 'pt': "Desfoque",
    },
    'effect_pixelate_name': {
        'fr': "Pixellisation", 'en': "Pixelate", 'es': "Pixelado",
        'de': "Verpixelung", 'it': "Pixelizzazione", 'pt': "Pixelização",
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
    # Layers panel (right-hand sidebar)
    'layers_panel_title': {
        'fr': "Calques", 'en': "Layers", 'es': "Capas",
        'de': "Ebenen", 'it': "Livelli", 'pt': "Camadas",
    },
    'layers_empty': {
        'fr': "Rien ici pour l'instant.\nAjoutez une image, collez-en une\ncopiée depuis votre gestionnaire de"
              " fichiers, ou dessinez\nune forme/flèche/texte.",
        'en': "Nothing here yet.\nAdd an image, paste one copied\nfrom your file manager, or draw"
              " a shape/arrow/text.",
        'es': "Nada por aquí todavía.\nAñade una imagen, pega una\ncopiada desde tu gestor de"
              " archivos, o dibuja\nuna forma/flecha/texto.",
        'de': "Hier ist noch nichts.\nFügen Sie ein Bild hinzu, fügen Sie eines\naus Ihrem Dateimanager ein,"
              " oder zeichnen Sie\neine Form/einen Pfeil/Text.",
        'it': "Ancora nulla qui.\nAggiungi un'immagine, incollane una\ncopiata dal gestore file,"
              " oppure disegna\nuna forma/freccia/testo.",
        'pt': "Ainda não há nada aqui.\nAdicione uma imagem, cole uma\ncopiada do seu gestor de"
              " ficheiros, ou desenhe\numa forma/seta/texto.",
    },
    'layers_section_objects': {
        'fr': "Objets", 'en': "Objects", 'es': "Objetos",
        'de': "Objekte", 'it': "Oggetti", 'pt': "Objetos",
    },
    'layers_section_layers': {
        'fr': "Calques", 'en': "Layers", 'es': "Capas",
        'de': "Ebenen", 'it': "Livelli", 'pt': "Camadas",
    },
    'layers_section_image': {
        'fr': "Image", 'en': "Image", 'es': "Imagen",
        'de': "Bild", 'it': "Immagine", 'pt': "Imagem",
    },
    'layers_base_image': {
        'fr': "Image de base", 'en': "Base image", 'es': "Imagen base",
        'de': "Basisbild", 'it': "Immagine di base", 'pt': "Imagem base",
    },
    'layer_bring_forward': {
        'fr': "Monter au premier plan", 'en': "Bring forward", 'es': "Traer al frente",
        'de': "Nach vorne bringen", 'it': "Porta in primo piano", 'pt': "Trazer para a frente",
    },
    'layer_send_backward': {
        'fr': "Envoyer à l'arrière-plan", 'en': "Send backward", 'es': "Enviar atrás",
        'de': "Nach hinten senden", 'it': "Manda in secondo piano", 'pt': "Enviar para trás",
    },
    'layer_toggle_visible': {
        'fr': "Afficher/masquer ce calque", 'en': "Show/hide this layer",
        'es': "Mostrar/ocultar esta capa", 'de': "Diese Ebene ein-/ausblenden",
        'it': "Mostra/nascondi questo livello", 'pt': "Mostrar/ocultar esta camada",
    },
    'layer_remove': {
        'fr': "Supprimer ce calque", 'en': "Remove this layer", 'es': "Eliminar esta capa",
        'de': "Diese Ebene entfernen", 'it': "Rimuovi questo livello", 'pt': "Remover esta camada",
    },
    'layer_link_tooltip': {
        'fr': "Lier ce calque à un autre pour les déplacer ensemble",
        'en': "Link this layer to another one, to move them together",
        'es': "Vincular esta capa a otra, para moverlas juntas",
        'de': "Diese Ebene mit einer anderen verknüpfen, um sie gemeinsam zu verschieben",
        'it': "Collega questo livello a un altro, per spostarli insieme",
        'pt': "Ligar esta camada a outra, para as mover juntas",
    },
    'layer_unlink_tooltip': {
        'fr': "Ce calque est lié — cliquer pour le délier",
        'en': "This layer is linked — click to unlink it",
        'es': "Esta capa está vinculada — clic para desvincularla",
        'de': "Diese Ebene ist verknüpft — klicken, um sie zu lösen",
        'it': "Questo livello è collegato — clic per scollegarlo",
        'pt': "Esta camada está ligada — clique para a desligar",
    },
    'layer_link_cancel_tooltip': {
        'fr': "En attente d'un second calque à lier — cliquer pour annuler",
        'en': "Waiting for a second layer to link with — click to cancel",
        'es': "Esperando una segunda capa para vincular — clic para cancelar",
        'de': "Wartet auf eine zweite Ebene zum Verknüpfen — klicken zum Abbrechen",
        'it': "In attesa di un secondo livello da collegare — clic per annullare",
        'pt': "À espera de uma segunda camada para ligar — clique para cancelar",
    },
    'status_link_pending': {
        'fr': "Calque prêt à être lié — cliquez sur le maillon d'un autre calque pour les lier.",
        'en': "Layer armed for linking — click another layer's link icon to link them together.",
        'es': "Capa lista para vincular — haz clic en el icono de enlace de otra capa para vincularlas.",
        'de': "Ebene bereit zum Verknüpfen — klicken Sie auf das Verknüpfungssymbol einer anderen Ebene.",
        'it': "Livello pronto per il collegamento — clicca sull'icona di collegamento di un altro livello.",
        'pt': "Camada pronta para ligar — clique no ícone de ligação de outra camada para as ligar.",
    },
    'status_layers_linked': {
        'fr': "Calques liés — ils se déplaceront désormais ensemble.",
        'en': "Layers linked — they'll now move together.",
        'es': "Capas vinculadas — ahora se moverán juntas.",
        'de': "Ebenen verknüpft — sie bewegen sich jetzt gemeinsam.",
        'it': "Livelli collegati — ora si sposteranno insieme.",
        'pt': "Camadas ligadas — agora vão mover-se juntas.",
    },
    'status_layer_unlinked': {
        'fr': "Calque délié.", 'en': "Layer unlinked.", 'es': "Capa desvinculada.",
        'de': "Ebene gelöst.", 'it': "Livello scollegato.", 'pt': "Camada desligada.",
    },
    'object_remove': {
        'fr': "Supprimer cet objet", 'en': "Remove this object", 'es': "Eliminar este objeto",
        'de': "Dieses Objekt entfernen", 'it': "Rimuovi questo oggetto", 'pt': "Remover este objeto",
    },
    # Clipboard paste-selection dialog
    'clipboard_select_all': {
        'fr': "Sélectionner tout", 'en': "Select All", 'es': "Seleccionar todo",
        'de': "Alles auswählen", 'it': "Seleziona tutto", 'pt': "Selecionar tudo",
    },
    'dialog_cancel': {
        'fr': "Annuler", 'en': "Cancel", 'es': "Cancelar",
        'de': "Abbrechen", 'it': "Annulla", 'pt': "Cancelar",
    },
    'clipboard_add': {
        'fr': "Ajouter", 'en': "Add", 'es': "Añadir",
        'de': "Hinzufügen", 'it': "Aggiungi", 'pt': "Adicionar",
    },

    # --- Options bar labels & tooltips ---
    'color_label': {
        'fr': "Couleur :", 'en': "Color:", 'es': "Color:",
        'de': "Farbe:", 'it': "Colore:", 'pt': "Cor:",
    },
    'width_label': {
        'fr': "Largeur :", 'en': "Width:", 'es': "Ancho:",
        'de': "Breite:", 'it': "Larghezza:", 'pt': "Largura:",
    },
    'border_width_label': {
        'fr': "Épaisseur de bordure :", 'en': "Border width:", 'es': "Grosor del borde:",
        'de': "Rahmenbreite:", 'it': "Spessore bordo:", 'pt': "Espessura da borda:",
    },
    'width_spin_tooltip': {
        'fr': "Épaisseur du trait pour les formes, ou épaisseur de bordure pour l'image/texte sélectionné — 0 = aucune",
        'en': "Stroke width for shapes, or border thickness for the selected image/text — 0 = none",
        'es': "Grosor del trazo para las formas, o grosor del borde para la imagen/texto seleccionado — 0 = ninguno",
        'de': "Strichstärke für Formen oder Rahmenbreite für das ausgewählte Bild/Text — 0 = keine",
        'it': "Spessore del tratto per le forme, o spessore del bordo per l'immagine/testo selezionato — 0 = nessuno",
        'pt': "Espessura do traço para formas, ou espessura da borda para a imagem/texto selecionado — 0 = nenhuma",
    },
    'fill_check_label': {
        'fr': "Remplir", 'en': "Fill", 'es': "Rellenar",
        'de': "Füllen", 'it': "Riempi", 'pt': "Preencher",
    },
    'fill_check_tooltip': {
        'fr': "Remplir l'intérieur de la forme, ou ajouter un fond derrière le texte",
        'en': "Fill the inside of the shape, or add a background behind the text",
        'es': "Rellenar el interior de la forma, o añadir un fondo detrás del texto",
        'de': "Das Innere der Form füllen oder einen Hintergrund hinter dem Text hinzufügen",
        'it': "Riempi l'interno della forma, oppure aggiungi uno sfondo dietro il testo",
        'pt': "Preencher o interior da forma, ou adicionar um fundo atrás do texto",
    },
    'fill_color_tooltip': {
        'fr': "Couleur de remplissage", 'en': "Fill color", 'es': "Color de relleno",
        'de': "Füllfarbe", 'it': "Colore di riempimento", 'pt': "Cor de preenchimento",
    },
    'border_label': {
        'fr': "Bordure :", 'en': "Border:", 'es': "Borde:",
        'de': "Rahmen:", 'it': "Bordo:", 'pt': "Borda:",
    },
    'border_color_tooltip': {
        'fr': "Couleur de bordure", 'en': "Border color", 'es': "Color del borde",
        'de': "Rahmenfarbe", 'it': "Colore del bordo", 'pt': "Cor da borda",
    },
    'head_label': {
        'fr': "Pointe :", 'en': "Head:", 'es': "Punta:",
        'de': "Spitze:", 'it': "Punta:", 'pt': "Ponta:",
    },
    'text_size_label': {
        'fr': "Taille du texte :", 'en': "Text size:", 'es': "Tamaño del texto:",
        'de': "Textgröße:", 'it': "Dimensione testo:", 'pt': "Tamanho do texto:",
    },
    'intensity_label': {
        'fr': "Intensité :", 'en': "Intensity:", 'es': "Intensidad:",
        'de': "Intensität:", 'it': "Intensità:", 'pt': "Intensidade:",
    },
    'intensity_tooltip': {
        'fr': "Plus la valeur est élevée, plus l'effet est fort",
        'en': "Higher = stronger effect", 'es': "Más alto = efecto más fuerte",
        'de': "Höher = stärkerer Effekt", 'it': "Più alto = effetto più forte",
        'pt': "Mais alto = efeito mais forte",
    },
    'opacity_label': {
        'fr': "Opacité du calque sélectionné :", 'en': "Selected layer opacity:",
        'es': "Opacidad de la capa seleccionada:", 'de': "Deckkraft der ausgewählten Ebene:",
        'it': "Opacità del livello selezionato:", 'pt': "Opacidade da camada selecionada:",
    },
    'zoom_label': {
        'fr': "Zoom :", 'en': "Zoom:", 'es': "Zoom:",
        'de': "Zoom:", 'it': "Zoom:", 'pt': "Zoom:",
    },
    'zoom_fit_label': {
        'fr': "Ajuster", 'en': "Fit", 'es': "Ajustar",
        'de': "Anpassen", 'it': "Adatta", 'pt': "Ajustar",
    },
    'zoom_tooltip': {
        'fr': "Astuce : la molette de la souris (ou le défilement à deux doigts du pavé tactile) zoome directement sur le canevas. Maj + molette : défilement horizontal.",
        'en': "Tip: the mouse wheel (or two-finger trackpad scroll) zooms in/out right on the canvas. Shift + wheel: horizontal scroll.",
        'es': "Consejo: la rueda del ratón (o el desplazamiento con dos dedos en el panel táctil) hace zoom directamente en el lienzo. Mayús + rueda: desplazamiento horizontal.",
        'de': "Tipp: Das Mausrad (oder Zweifinger-Scrollen auf dem Trackpad) zoomt direkt auf der Leinwand. Umschalt + Mausrad: horizontales Scrollen.",
        'it': "Suggerimento: la rotellina del mouse (o lo scorrimento a due dita sul trackpad) esegue lo zoom direttamente sulla tela. Maiusc + rotellina: scorrimento orizzontale.",
        'pt': "Dica: a roda do rato (ou deslizar com dois dedos no trackpad) faz zoom diretamente na tela. Shift + roda: deslocamento horizontal.",
    },

    # --- Tabs / empty state ---
    'new_tab_tooltip': {
        'fr': "Ouvrir une image dans un nouvel onglet", 'en': "Open an image in a new tab",
        'es': "Abrir una imagen en una nueva pestaña", 'de': "Ein Bild in einem neuen Tab öffnen",
        'it': "Apri un'immagine in una nuova scheda", 'pt': "Abrir uma imagem num novo separador",
    },
    'close_tab_tooltip': {
        'fr': "Fermer l'onglet", 'en': "Close tab", 'es': "Cerrar pestaña",
        'de': "Tab schließen", 'it': "Chiudi scheda", 'pt': "Fechar separador",
    },
    'never_saved': {
        'fr': "Jamais enregistré", 'en': "Never saved", 'es': "Nunca guardado",
        'de': "Nie gespeichert", 'it': "Mai salvato", 'pt': "Nunca guardado",
    },
    'untitled': {
        'fr': "Sans titre", 'en': "Untitled", 'es': "Sin título",
        'de': "Unbenannt", 'it': "Senza titolo", 'pt': "Sem título",
    },
    'empty_state_title': {
        'fr': "Aucune image ouverte", 'en': "No image open", 'es': "Ninguna imagen abierta",
        'de': "Kein Bild geöffnet", 'it': "Nessuna immagine aperta", 'pt': "Nenhuma imagem aberta",
    },
    'empty_state_subtitle': {
        'fr': "Ouvrez une image pour commencer à l'éditer. Chaque image ouverte est ajoutée dans un nouvel onglet.",
        'en': "Open an image to start editing. Each image you open is added as a new tab.",
        'es': "Abre una imagen para empezar a editar. Cada imagen que abras se añade como una nueva pestaña.",
        'de': "Öffnen Sie ein Bild, um mit der Bearbeitung zu beginnen. Jedes geöffnete Bild wird als neuer Tab hinzugefügt.",
        'it': "Apri un'immagine per iniziare a modificarla. Ogni immagine aperta viene aggiunta come nuova scheda.",
        'pt': "Abra uma imagem para começar a editar. Cada imagem aberta é adicionada como um novo separador.",
    },
    'empty_state_button': {
        'fr': "Ouvrir une image…", 'en': "Open an image…", 'es': "Abrir una imagen…",
        'de': "Bild öffnen…", 'it': "Apri un'immagine…", 'pt': "Abrir uma imagem…",
    },

    # --- Default/fallback names ---
    'default_layer_name': {
        'fr': "Calque", 'en': "Layer", 'es': "Capa",
        'de': "Ebene", 'it': "Livello", 'pt': "Camada",
    },
    'default_object_name': {
        'fr': "Objet", 'en': "Object", 'es': "Objeto",
        'de': "Objekt", 'it': "Oggetto", 'pt': "Objeto",
    },
    'clipboard_layer_name': {
        'fr': "Presse-papiers", 'en': "Clipboard", 'es': "Portapapeles",
        'de': "Zwischenablage", 'it': "Appunti", 'pt': "Área de transferência",
    },
    'annotation_text_with_content': {
        'fr': "Texte : {text}", 'en': "Text: {text}", 'es': "Texto: {text}",
        'de': "Text: {text}", 'it': "Testo: {text}", 'pt': "Texto: {text}",
    },
    'tool_select_short': {
        'fr': "Sélection", 'en': "Select", 'es': "Selección",
        'de': "Auswahl", 'it': "Selezione", 'pt': "Seleção",
    },
    'tool_crop_short': {
        'fr': "Recadrage", 'en': "Crop", 'es': "Recorte",
        'de': "Zuschneiden", 'it': "Ritaglio", 'pt': "Recorte",
    },
    'tool_text_short': {
        'fr': "Texte", 'en': "Text", 'es': "Texto",
        'de': "Text", 'it': "Testo", 'pt': "Texto",
    },

    # --- Hints ---
    'hint_keep_aspect_ratio': {
        'fr': "Maintenez Ctrl ou Maj pour conserver les proportions",
        'en': "Hold Ctrl or Shift to keep the aspect ratio",
        'es': "Mantén Ctrl o Mayús para conservar las proporciones",
        'de': "Strg oder Umschalt gedrückt halten, um das Seitenverhältnis beizubehalten",
        'it': "Tieni premuto Ctrl o Maiusc per mantenere le proporzioni",
        'pt': "Mantenha Ctrl ou Shift para manter as proporções",
    },
    'hint_aspect_ratio_locked': {
        'fr': "🔒 Proportions verrouillées (Ctrl/Maj maintenu)",
        'en': "🔒 Aspect ratio locked (Ctrl/Shift held)",
        'es': "🔒 Proporciones bloqueadas (Ctrl/Mayús mantenido)",
        'de': "🔒 Seitenverhältnis gesperrt (Strg/Umschalt gehalten)",
        'it': "🔒 Proporzioni bloccate (Ctrl/Maiusc premuto)",
        'pt': "🔒 Proporções bloqueadas (Ctrl/Shift mantido)",
    },
    'crop_hint': {
        'fr': "↵ Entrée : valider le recadrage · Échap : annuler",
        'en': "↵ Enter: confirm the crop · Esc: cancel",
        'es': "↵ Intro: confirmar el recorte · Esc: cancelar",
        'de': "↵ Eingabe: Zuschnitt bestätigen · Esc: abbrechen",
        'it': "↵ Invio: conferma il ritaglio · Esc: annulla",
        'pt': "↵ Enter: confirmar o recorte · Esc: cancelar",
    },
    'polygon_hint': {
        'fr': "Cliquez pour placer les points · ↵ Entrée : fermer et remplir · Échap : annuler",
        'en': "Click to place points · ↵ Enter: close and fill · Esc: cancel",
        'es': "Haz clic para colocar puntos · ↵ Intro: cerrar y rellenar · Esc: cancelar",
        'de': "Klicken, um Punkte zu setzen · ↵ Eingabe: schließen und füllen · Esc: abbrechen",
        'it': "Clicca per posizionare i punti · ↵ Invio: chiudi e riempi · Esc: annulla",
        'pt': "Clique para colocar pontos · ↵ Enter: fechar e preencher · Esc: cancelar",
    },

    # --- Status bar ---
    'status_bar_template': {
        'fr': "{w}×{h} px — zoom {zoom}% — outil : {tool}",
        'en': "{w}×{h} px — zoom {zoom}% — tool: {tool}",
        'es': "{w}×{h} px — zoom {zoom}% — herramienta: {tool}",
        'de': "{w}×{h} px — Zoom {zoom}% — Werkzeug: {tool}",
        'it': "{w}×{h} px — zoom {zoom}% — strumento: {tool}",
        'pt': "{w}×{h} px — zoom {zoom}% — ferramenta: {tool}",
    },
    'status_cropped': {
        'fr': "Image recadrée : {w}×{h} px.", 'en': "Image cropped: {w}×{h} px.",
        'es': "Imagen recortada: {w}×{h} px.", 'de': "Bild zugeschnitten: {w}×{h} px.",
        'it': "Immagine ritagliata: {w}×{h} px.", 'pt': "Imagem recortada: {w}×{h} px.",
    },
    'status_flip_h': {
        'fr': "Image retournée horizontalement (calques et annotations fusionnés).",
        'en': "Image flipped horizontally (layers and annotations merged).",
        'es': "Imagen volteada horizontalmente (capas y anotaciones fusionadas).",
        'de': "Bild horizontal gespiegelt (Ebenen und Anmerkungen zusammengeführt).",
        'it': "Immagine capovolta orizzontalmente (livelli e annotazioni uniti).",
        'pt': "Imagem invertida horizontalmente (camadas e anotações fundidas).",
    },
    'status_flip_v': {
        'fr': "Image retournée verticalement (calques et annotations fusionnés).",
        'en': "Image flipped vertically (layers and annotations merged).",
        'es': "Imagen volteada verticalmente (capas y anotaciones fusionadas).",
        'de': "Bild vertikal gespiegelt (Ebenen und Anmerkungen zusammengeführt).",
        'it': "Immagine capovolta verticalmente (livelli e annotazioni uniti).",
        'pt': "Imagem invertida verticalmente (camadas e anotações fundidas).",
    },
    'status_rotate90': {
        'fr': "Image pivotée de 90° (calques et annotations fusionnés).",
        'en': "Image rotated 90° (layers and annotations merged).",
        'es': "Imagen girada 90° (capas y anotaciones fusionadas).",
        'de': "Bild um 90° gedreht (Ebenen und Anmerkungen zusammengeführt).",
        'it': "Immagine ruotata di 90° (livelli e annotazioni uniti).",
        'pt': "Imagem rodada 90° (camadas e anotações fundidas).",
    },
    'status_canvas_resized': {
        'fr': "Taille du canevas : {w}×{h} px (l'image de base a conservé sa taille d'origine).",
        'en': "Canvas size: {w}×{h} px (the base image kept its original size).",
        'es': "Tamaño del lienzo: {w}×{h} px (la imagen base mantuvo su tamaño original).",
        'de': "Leinwandgröße: {w}×{h} px (das Basisbild hat seine ursprüngliche Größe behalten).",
        'it': "Dimensione tela: {w}×{h} px (l'immagine di base ha mantenuto le sue dimensioni originali).",
        'pt': "Tamanho da tela: {w}×{h} px (a imagem base manteve o seu tamanho original).",
    },
    'status_effect_attached': {
        'fr': "Zone {effect} — associée à {n} image(s) en dessous. Sélectionnez-la et ajustez l'intensité, ou supprimez-la pour restaurer l'original.",
        'en': "Area {effect} — attached to {n} image(s) below it. Select it and adjust Intensity, or delete it to restore the original.",
        'es': "Zona {effect} — asociada a {n} imagen(es) debajo. Selecciónala y ajusta la intensidad, o elimínala para restaurar el original.",
        'de': "Bereich {effect} — mit {n} Bild(ern) darunter verknüpft. Wählen Sie ihn aus und passen Sie die Intensität an, oder löschen Sie ihn, um das Original wiederherzustellen.",
        'it': "Area {effect} — collegata a {n} immagine/i sottostante/i. Selezionala e regola l'intensità, oppure eliminala per ripristinare l'originale.",
        'pt': "Área {effect} — associada a {n} imagem(ns) abaixo. Selecione-a e ajuste a intensidade, ou elimine-a para restaurar o original.",
    },
    'status_effect_standalone': {
        'fr': "Zone {effect}. Sélectionnez-la et ajustez l'intensité, ou supprimez-la pour restaurer l'original.",
        'en': "Area {effect}. Select it and adjust Intensity, or delete it to restore the original.",
        'es': "Zona {effect}. Selecciónala y ajusta la intensidad, o elimínala para restaurar el original.",
        'de': "Bereich {effect}. Wählen Sie ihn aus und passen Sie die Intensität an, oder löschen Sie ihn, um das Original wiederherzustellen.",
        'it': "Area {effect}. Selezionala e regola l'intensità, oppure eliminala per ripristinare l'originale.",
        'pt': "Área {effect}. Selecione-a e ajuste a intensidade, ou elimine-a para restaurar o original.",
    },
    'effect_blurred_participle': {
        'fr': "floutée", 'en': "blurred", 'es': "difuminada",
        'de': "weichgezeichnet", 'it': "sfocata", 'pt': "desfocada",
    },
    'effect_pixelated_participle': {
        'fr': "pixellisée", 'en': "pixelated", 'es': "pixelada",
        'de': "pixeliert", 'it': "pixelata", 'pt': "pixelizada",
    },
    'status_polygon_progress': {
        'fr': "Polygone : {n} point(s) placé(s) — Entrée pour fermer et remplir, Échap pour annuler.",
        'en': "Polygon: {n} point(s) placed — Enter to close and fill, Esc to cancel.",
        'es': "Polígono: {n} punto(s) colocado(s) — Intro para cerrar y rellenar, Esc para cancelar.",
        'de': "Polygon: {n} Punkt(e) gesetzt — Eingabe zum Schließen und Füllen, Esc zum Abbrechen.",
        'it': "Poligono: {n} punto/i posizionato/i — Invio per chiudere e riempire, Esc per annullare.",
        'pt': "Polígono: {n} ponto(s) colocado(s) — Enter para fechar e preencher, Esc para cancelar.",
    },
    'status_polygon_min_points': {
        'fr': "Ajoutez au moins 3 points avant de fermer le polygone (Entrée).",
        'en': "Add at least 3 points before closing the polygon (Enter).",
        'es': "Añade al menos 3 puntos antes de cerrar el polígono (Intro).",
        'de': "Fügen Sie mindestens 3 Punkte hinzu, bevor Sie das Polygon schließen (Eingabe).",
        'it': "Aggiungi almeno 3 punti prima di chiudere il poligono (Invio).",
        'pt': "Adicione pelo menos 3 pontos antes de fechar o polígono (Enter).",
    },
    'status_polygon_created': {
        'fr': "Polygone créé (fermé et rempli).", 'en': "Polygon created (closed and filled).",
        'es': "Polígono creado (cerrado y rellenado).", 'de': "Polygon erstellt (geschlossen und gefüllt).",
        'it': "Poligono creato (chiuso e riempito).", 'pt': "Polígono criado (fechado e preenchido).",
    },
    'status_open_image_failed': {
        'fr': "Impossible d'ouvrir l'image : {error}", 'en': "Couldn't open image: {error}",
        'es': "No se pudo abrir la imagen: {error}", 'de': "Bild konnte nicht geöffnet werden: {error}",
        'it': "Impossibile aprire l'immagine: {error}", 'pt': "Não foi possível abrir a imagem: {error}",
    },
    'status_layers_added': {
        'fr': "{n} calque(s) ajouté(s) depuis le presse-papiers.", 'en': "{n} layer(s) added from the clipboard.",
        'es': "{n} capa(s) añadida(s) desde el portapapeles.", 'de': "{n} Ebene(n) aus der Zwischenablage hinzugefügt.",
        'it': "{n} livello/i aggiunto/i dagli appunti.", 'pt': "{n} camada(s) adicionada(s) da área de transferência.",
    },
    'status_clipboard_open_failed': {
        'fr': "Impossible d'ouvrir la ou les images copiées.", 'en': "Couldn't open the copied image(s).",
        'es': "No se pudieron abrir la(s) imagen(es) copiada(s).", 'de': "Die kopierten Bilder konnten nicht geöffnet werden.",
        'it': "Impossibile aprire l'immagine/le immagini copiata/e.", 'pt': "Não foi possível abrir a(s) imagem(ns) copiada(s).",
    },
    'status_clipboard_empty': {
        'fr': "Aucune image dans le presse-papiers.", 'en': "No image in the clipboard.",
        'es': "No hay ninguna imagen en el portapapeles.", 'de': "Kein Bild in der Zwischenablage.",
        'it': "Nessuna immagine negli appunti.", 'pt': "Nenhuma imagem na área de transferência.",
    },
    'status_clipboard_paste_failed': {
        'fr': "Impossible de coller l'image depuis le presse-papiers.", 'en': "Couldn't paste the image from the clipboard.",
        'es': "No se pudo pegar la imagen desde el portapapeles.", 'de': "Das Bild konnte nicht aus der Zwischenablage eingefügt werden.",
        'it': "Impossibile incollare l'immagine dagli appunti.", 'pt': "Não foi possível colar a imagem da área de transferência.",
    },
    'status_image_copied': {
        'fr': "Image copiée dans le presse-papiers.", 'en': "Image copied to clipboard.",
        'es': "Imagen copiada al portapapeles.", 'de': "Bild in die Zwischenablage kopiert.",
        'it': "Immagine copiata negli appunti.", 'pt': "Imagem copiada para a área de transferência.",
    },
    'status_layer_added': {
        'fr': "Calque « {name} » ajouté — glissez pour le déplacer, coin en bas à droite pour le redimensionner.",
        'en': "Layer \u201c{name}\u201d added — drag to move it, bottom-right corner to resize it.",
        'es': "Capa «{name}» añadida — arrastra para moverla, esquina inferior derecha para redimensionarla.",
        'de': "Ebene „{name}“ hinzugefügt — ziehen zum Verschieben, untere rechte Ecke zum Vergrößern/Verkleinern.",
        'it': "Livello «{name}» aggiunto — trascina per spostarlo, angolo in basso a destra per ridimensionarlo.",
        'pt': "Camada «{name}» adicionada — arraste para mover, canto inferior direito para redimensionar.",
    },
    'status_layer_added_grown': {
        'fr': "Canevas agrandi à {w}×{h} px pour accueillir « {name} » à sa taille d'origine — glissez pour le déplacer.",
        'en': "Canvas grown to {w}×{h} px to fit \u201c{name}\u201d at its original size — drag to move it.",
        'es': "Lienzo ampliado a {w}×{h} px para encajar «{name}» a su tamaño original — arrastra para moverla.",
        'de': "Leinwand auf {w}×{h} px vergrößert, um „{name}“ in Originalgröße einzupassen — ziehen zum Verschieben.",
        'it': "Tela ingrandita a {w}×{h} px per adattare «{name}» alla sua dimensione originale — trascina per spostarlo.",
        'pt': "Tela ampliada para {w}×{h} px para encaixar «{name}» no seu tamanho original — arraste para mover.",
    },
    'status_saved': {
        'fr': "Enregistré : {path}", 'en': "Saved: {path}", 'es': "Guardado: {path}",
        'de': "Gespeichert: {path}", 'it': "Salvato: {path}", 'pt': "Guardado: {path}",
    },
    'status_save_failed': {
        'fr': "Échec de l'enregistrement : {error}", 'en': "Save failed: {error}",
        'es': "Error al guardar: {error}", 'de': "Speichern fehlgeschlagen: {error}",
        'it': "Salvataggio non riuscito: {error}", 'pt': "Falha ao guardar: {error}",
    },
    'status_recovered': {
        'fr': "{n} image(s) récupérée(s) depuis la sauvegarde automatique.",
        'en': "{n} image(s) recovered from autosave.",
        'es': "{n} imagen(es) recuperada(s) desde el guardado automático.",
        'de': "{n} Bild(er) aus der automatischen Sicherung wiederhergestellt.",
        'it': "{n} immagine/i recuperata/e dal salvataggio automatico.",
        'pt': "{n} imagem(ns) recuperada(s) da gravação automática.",
    },
    'status_open_failed': {
        'fr': "Impossible d'ouvrir : {error}", 'en': "Couldn't open: {error}",
        'es': "No se pudo abrir: {error}", 'de': "Öffnen nicht möglich: {error}",
        'it': "Impossibile aprire: {error}", 'pt': "Não foi possível abrir: {error}",
    },

    # --- Generic dialog buttons ---
    'dialog_ok': {
        'fr': "OK", 'en': "OK", 'es': "OK", 'de': "OK", 'it': "OK", 'pt': "OK",
    },
    'dialog_dont_save': {
        'fr': "Ne pas enregistrer", 'en': "Don't Save", 'es': "No guardar",
        'de': "Nicht speichern", 'it': "Non salvare", 'pt': "Não guardar",
    },
    'dialog_save': {
        'fr': "Enregistrer", 'en': "Save", 'es': "Guardar",
        'de': "Speichern", 'it': "Salva", 'pt': "Guardar",
    },
    'dialog_save_all_close': {
        'fr': "Tout enregistrer et fermer", 'en': "Save All and Close", 'es': "Guardar todo y cerrar",
        'de': "Alles speichern und schließen", 'it': "Salva tutto e chiudi", 'pt': "Guardar tudo e fechar",
    },
    'dialog_discard': {
        'fr': "Ne pas tenir compte", 'en': "Discard", 'es': "Descartar",
        'de': "Verwerfen", 'it': "Ignora", 'pt': "Descartar",
    },
    'dialog_recover': {
        'fr': "Récupérer", 'en': "Recover", 'es': "Recuperar",
        'de': "Wiederherstellen", 'it': "Recupera", 'pt': "Recuperar",
    },

    # --- Unsaved-changes dialogs ---
    'unsaved_changes_title': {
        'fr': "Modifications non enregistrées", 'en': "Unsaved changes", 'es': "Cambios sin guardar",
        'de': "Nicht gespeicherte Änderungen", 'it': "Modifiche non salvate", 'pt': "Alterações não guardadas",
    },
    'unsaved_changes_tab_body': {
        'fr': "« {name} » contient des modifications non enregistrées. Voulez-vous les enregistrer avant de fermer cet onglet ?",
        'en': "\u201c{name}\u201d has unsaved changes. Do you want to save them before closing this tab?",
        'es': "«{name}» tiene cambios sin guardar. ¿Quieres guardarlos antes de cerrar esta pestaña?",
        'de': "„{name}“ enthält nicht gespeicherte Änderungen. Möchten Sie sie speichern, bevor Sie diesen Tab schließen?",
        'it': "«{name}» contiene modifiche non salvate. Vuoi salvarle prima di chiudere questa scheda?",
        'pt': "«{name}» tem alterações não guardadas. Quer guardá-las antes de fechar este separador?",
    },
    'unsaved_changes_quit_body': {
        'fr': "Vous avez des modifications non enregistrées dans : {names}.\nVoulez-vous les enregistrer avant de fermer ?",
        'en': "You have unsaved changes in: {names}.\nDo you want to save them before closing?",
        'es': "Tienes cambios sin guardar en: {names}.\n¿Quieres guardarlos antes de cerrar?",
        'de': "Sie haben nicht gespeicherte Änderungen in: {names}.\nMöchten Sie sie vor dem Schließen speichern?",
        'it': "Hai modifiche non salvate in: {names}.\nVuoi salvarle prima di chiudere?",
        'pt': "Tem alterações não guardadas em: {names}.\nQuer guardá-las antes de fechar?",
    },

    # --- Crash-recovery dialog ---
    'recovery_title': {
        'fr': "Récupération après un arrêt inattendu", 'en': "Recover from an unexpected shutdown",
        'es': "Recuperación tras un cierre inesperado", 'de': "Wiederherstellung nach unerwartetem Beenden",
        'it': "Ripristino dopo una chiusura imprevista", 'pt': "Recuperação após um encerramento inesperado",
    },
    'recovery_body': {
        'fr': "{n} image(s) n'ont pas été fermée(s) normalement lors de la dernière session (plantage, coupure de courant…). Voulez-vous les récupérer ?",
        'en': "{n} image(s) weren't closed normally in the last session (crash, power loss...). Do you want to recover them?",
        'es': "{n} imagen(es) no se cerraron normalmente en la última sesión (fallo, corte de energía...). ¿Quieres recuperarlas?",
        'de': "{n} Bild(er) wurden in der letzten Sitzung nicht normal geschlossen (Absturz, Stromausfall...). Möchten Sie sie wiederherstellen?",
        'it': "{n} immagine/i non è/sono stata/e chiusa/e normalmente nell'ultima sessione (crash, interruzione di corrente...). Vuoi recuperarle?",
        'pt': "{n} imagem(ns) não foram fechadas normalmente na última sessão (falha, corte de energia...). Quer recuperá-las?",
    },

    # --- Canvas Size dialog ---
    'canvas_size_title': {
        'fr': "Taille du canevas", 'en': "Canvas Size", 'es': "Tamaño del lienzo",
        'de': "Leinwandgröße", 'it': "Dimensione tela", 'pt': "Tamanho da tela",
    },
    'canvas_size_info': {
        'fr': "Agrandir ou réduire l'espace de travail : l'image de base garde sa taille d'origine, elle est seulement repositionnée.",
        'en': "Enlarge or shrink the workspace: the base image keeps its original size, it's only repositioned.",
        'es': "Agranda o reduce el espacio de trabajo: la imagen base mantiene su tamaño original, solo se reposiciona.",
        'de': "Arbeitsfläche vergrößern oder verkleinern: Das Basisbild behält seine ursprüngliche Größe, es wird nur neu positioniert.",
        'it': "Ingrandisci o riduci l'area di lavoro: l'immagine di base mantiene le sue dimensioni originali, viene solo riposizionata.",
        'pt': "Aumente ou reduza o espaço de trabalho: a imagem base mantém o seu tamanho original, é apenas reposicionada.",
    },
    'canvas_size_hint_template': {
        'fr': "Taille de l'image chargée : {w} × {h} px",
        'en': "Loaded image size: {w} × {h} px",
        'es': "Tamaño de la imagen cargada: {w} × {h} px",
        'de': "Größe des geladenen Bilds: {w} × {h} px",
        'it': "Dimensione immagine caricata: {w} × {h} px",
        'pt': "Tamanho da imagem carregada: {w} × {h} px",
    },
    'canvas_size_hint_current': {
        'fr': " (canevas actuel : {w} × {h} px)", 'en': " (current canvas: {w} × {h} px)",
        'es': " (lienzo actual: {w} × {h} px)", 'de': " (aktuelle Leinwand: {w} × {h} px)",
        'it': " (tela attuale: {w} × {h} px)", 'pt': " (tela atual: {w} × {h} px)",
    },
    'canvas_size_hint_tooltip': {
        'fr': "Repère utile pour savoir de combien agrandir le canevas par rapport à l'image actuellement chargée.",
        'en': "A reference for how much bigger to make the canvas compared to the currently loaded image.",
        'es': "Una referencia de cuánto agrandar el lienzo en comparación con la imagen actualmente cargada.",
        'de': "Ein Anhaltspunkt dafür, wie viel größer die Leinwand im Vergleich zum aktuell geladenen Bild sein soll.",
        'it': "Un riferimento per capire quanto ingrandire la tela rispetto all'immagine attualmente caricata.",
        'pt': "Uma referência para saber quanto aumentar a tela em relação à imagem atualmente carregada.",
    },
    'canvas_width_label': {
        'fr': "Largeur :", 'en': "Width:", 'es': "Ancho:",
        'de': "Breite:", 'it': "Larghezza:", 'pt': "Largura:",
    },
    'canvas_height_label': {
        'fr': "Hauteur :", 'en': "Height:", 'es': "Alto:",
        'de': "Höhe:", 'it': "Altezza:", 'pt': "Altura:",
    },
    'canvas_link_checkbox': {
        'fr': "Lier largeur et hauteur (mise à l'échelle proportionnelle)",
        'en': "Link width and height (scale up proportionally)",
        'es': "Vincular ancho y alto (escalar proporcionalmente)",
        'de': "Breite und Höhe verknüpfen (proportional skalieren)",
        'it': "Collega larghezza e altezza (scala proporzionalmente)",
        'pt': "Ligar largura e altura (escalar proporcionalmente)",
    },
    'canvas_link_tooltip': {
        'fr': "Quand cette option est activée, modifier la largeur ou la hauteur ajuste automatiquement l'autre valeur pour garder les proportions.",
        'en': "When enabled, changing width or height automatically adjusts the other value to keep proportions.",
        'es': "Cuando está activado, cambiar el ancho o el alto ajusta automáticamente el otro valor para mantener las proporciones.",
        'de': "Wenn aktiviert, wird beim Ändern von Breite oder Höhe der andere Wert automatisch angepasst, um die Proportionen beizubehalten.",
        'it': "Quando è attivo, modificare la larghezza o l'altezza regola automaticamente l'altro valore per mantenere le proporzioni.",
        'pt': "Quando ativado, alterar a largura ou a altura ajusta automaticamente o outro valor para manter as proporções.",
    },
    'canvas_position_label': {
        'fr': "Position de l'image dans le nouveau canevas :", 'en': "Image position in the new canvas:",
        'es': "Posición de la imagen en el nuevo lienzo:", 'de': "Bildposition in der neuen Leinwand:",
        'it': "Posizione dell'immagine nella nuova tela:", 'pt': "Posição da imagem na nova tela:",
    },

    # --- Text dialog ---
    'text_dialog_edit_title': {
        'fr': "Modifier le texte", 'en': "Edit Text", 'es': "Editar texto",
        'de': "Text bearbeiten", 'it': "Modifica testo", 'pt': "Editar texto",
    },
    'text_dialog_add_title': {
        'fr': "Ajouter du texte", 'en': "Add Text", 'es': "Añadir texto",
        'de': "Text hinzufügen", 'it': "Aggiungi testo", 'pt': "Adicionar texto",
    },

    # --- Clipboard paste-selection dialog ---
    'clipboard_dialog_title': {
        'fr': "Images trouvées dans le presse-papiers", 'en': "Images Found on the Clipboard",
        'es': "Imágenes encontradas en el portapapeles", 'de': "Im Zwischenspeicher gefundene Bilder",
        'it': "Immagini trovate negli appunti", 'pt': "Imagens encontradas na área de transferência",
    },
    'clipboard_dialog_intro': {
        'fr': "{n} image(s) copiée(s) — choisissez celles à ajouter comme calques.",
        'en': "{n} image(s) copied — choose which ones to add as layers.",
        'es': "{n} imagen(es) copiada(s) — elige cuáles añadir como capas.",
        'de': "{n} Bild(er) kopiert — wählen Sie aus, welche als Ebenen hinzugefügt werden sollen.",
        'it': "{n} immagine/i copiata/e — scegli quali aggiungere come livelli.",
        'pt': "{n} imagem(ns) copiada(s) — escolha quais adicionar como camadas.",
    },

    # --- File choosers ---
    'file_filter_images': {
        'fr': "Images", 'en': "Images", 'es': "Imágenes",
        'de': "Bilder", 'it': "Immagini", 'pt': "Imagens",
    },
    'open_image_dialog_title': {
        'fr': "Ouvrir une image", 'en': "Open an Image", 'es': "Abrir una imagen",
        'de': "Bild öffnen", 'it': "Apri un'immagine", 'pt': "Abrir uma imagem",
    },
    'choose_overlay_dialog_title': {
        'fr': "Choisir une image à superposer", 'en': "Choose an Image to Overlay",
        'es': "Elegir una imagen para superponer", 'de': "Ein Bild zum Überlagern wählen",
        'it': "Scegli un'immagine da sovrapporre", 'pt': "Escolher uma imagem para sobrepor",
    },
    'save_as_dialog_title': {
        'fr': "Enregistrer sous", 'en': "Save As", 'es': "Guardar como",
        'de': "Speichern unter", 'it': "Salva con nome", 'pt': "Guardar como",
    },

    # --- Help dialog ---
    'help_button_tooltip': {
        'fr': "Aide — raccourcis et astuces", 'en': "Help — shortcuts and tips",
        'es': "Ayuda — atajos y consejos", 'de': "Hilfe — Tastenkürzel und Tipps",
        'it': "Aiuto — scorciatoie e consigli", 'pt': "Ajuda — atalhos e dicas",
    },
    'help_dialog_title': {
        'fr': "Aide", 'en': "Help", 'es': "Ayuda",
        'de': "Hilfe", 'it': "Aiuto", 'pt': "Ajuda",
    },
    'help_section_shortcuts': {
        'fr': "Raccourcis clavier", 'en': "Keyboard shortcuts", 'es': "Atajos de teclado",
        'de': "Tastenkürzel", 'it': "Scorciatoie da tastiera", 'pt': "Atalhos de teclado",
    },
    'help_section_right_click': {
        'fr': "Clic droit", 'en': "Right-click", 'es': "Clic derecho",
        'de': "Rechtsklick", 'it': "Clic destro", 'pt': "Clique direito",
    },
    'help_section_tips': {
        'fr': "Subtilités", 'en': "Good to know", 'es': "Cosas a tener en cuenta",
        'de': "Wissenswertes", 'it': "Da sapere", 'pt': "Boas práticas",
    },

    # Key labels (shown as small pills next to each shortcut)
    'key_ctrl_z': {'fr': "Ctrl+Z", 'en': "Ctrl+Z", 'es': "Ctrl+Z", 'de': "Strg+Z", 'it': "Ctrl+Z", 'pt': "Ctrl+Z"},
    'key_ctrl_y': {'fr': "Ctrl+Y", 'en': "Ctrl+Y", 'es': "Ctrl+Y", 'de': "Strg+Y", 'it': "Ctrl+Y", 'pt': "Ctrl+Y"},
    'key_ctrl_s': {'fr': "Ctrl+S", 'en': "Ctrl+S", 'es': "Ctrl+S", 'de': "Strg+S", 'it': "Ctrl+S", 'pt': "Ctrl+S"},
    'key_ctrl_o': {'fr': "Ctrl+O", 'en': "Ctrl+O", 'es': "Ctrl+O", 'de': "Strg+O", 'it': "Ctrl+O", 'pt': "Ctrl+O"},
    'key_delete': {
        'fr': "Suppr", 'en': "Delete", 'es': "Supr", 'de': "Entf", 'it': "Canc", 'pt': "Delete",
    },
    'key_arrows': {
        'fr': "Flèches", 'en': "Arrow keys", 'es': "Flechas",
        'de': "Pfeiltasten", 'it': "Frecce", 'pt': "Setas",
    },
    'key_escape': {
        'fr': "Échap", 'en': "Esc", 'es': "Esc", 'de': "Esc", 'it': "Esc", 'pt': "Esc",
    },
    'key_enter': {
        'fr': "Entrée", 'en': "Enter", 'es': "Intro", 'de': "Eingabe", 'it': "Invio", 'pt': "Enter",
    },
    'key_wheel': {
        'fr': "Molette", 'en': "Mouse wheel", 'es': "Rueda del ratón",
        'de': "Mausrad", 'it': "Rotellina", 'pt': "Roda do rato",
    },
    'key_shift_wheel': {
        'fr': "Maj + molette", 'en': "Shift + wheel", 'es': "Mayús + rueda",
        'de': "Umschalt + Mausrad", 'it': "Maiusc + rotellina", 'pt': "Shift + roda",
    },
    'key_right_click': {
        'fr': "Clic droit", 'en': "Right-click", 'es': "Clic derecho",
        'de': "Rechtsklick", 'it': "Clic destro", 'pt': "Clique direito",
    },
    'key_double_click': {
        'fr': "Double-clic", 'en': "Double-click", 'es': "Doble clic",
        'de': "Doppelklick", 'it': "Doppio clic", 'pt': "Duplo clique",
    },

    # Shortcut descriptions
    'help_shortcut_undo': {
        'fr': "Annuler la dernière action", 'en': "Undo the last action",
        'es': "Deshacer la última acción", 'de': "Letzte Aktion rückgängig machen",
        'it': "Annulla l'ultima azione", 'pt': "Anular a última ação",
    },
    'help_shortcut_redo': {
        'fr': "Rétablir l'action annulée", 'en': "Redo the undone action",
        'es': "Rehacer la acción deshecha", 'de': "Rückgängig gemachte Aktion wiederholen",
        'it': "Ripeti l'azione annullata", 'pt': "Refazer a ação anulada",
    },
    'help_shortcut_save': {
        'fr': "Enregistrer l'image", 'en': "Save the image", 'es': "Guardar la imagen",
        'de': "Bild speichern", 'it': "Salva l'immagine", 'pt': "Guardar a imagem",
    },
    'help_shortcut_open': {
        'fr': "Ouvrir une image dans un nouvel onglet", 'en': "Open an image in a new tab",
        'es': "Abrir una imagen en una nueva pestaña", 'de': "Ein Bild in einem neuen Tab öffnen",
        'it': "Apri un'immagine in una nuova scheda", 'pt': "Abrir uma imagem num novo separador",
    },
    'help_shortcut_delete': {
        'fr': "Supprimer le calque ou l'objet sélectionné",
        'en': "Delete the selected layer or object",
        'es': "Eliminar la capa u objeto seleccionado",
        'de': "Ausgewählte Ebene oder ausgewähltes Objekt löschen",
        'it': "Elimina il livello o l'oggetto selezionato",
        'pt': "Eliminar a camada ou objeto selecionado",
    },
    'help_shortcut_nudge': {
        'fr': "Déplacer la sélection de 1 px (Maj : 10 px). Si le calque déplacé est lié à d'autres, ils suivent.",
        'en': "Nudge the selection by 1 px (Shift: 10 px). If the moved layer is linked to others, they follow.",
        'es': "Mover la selección 1 px (Mayús: 10 px). Si la capa movida está vinculada a otras, la siguen.",
        'de': "Auswahl um 1 px verschieben (Umschalt: 10 px). Verknüpfte Ebenen folgen automatisch.",
        'it': "Sposta la selezione di 1 px (Maiusc: 10 px). I livelli collegati seguono automaticamente.",
        'pt': "Mover a seleção 1 px (Shift: 10 px). As camadas ligadas seguem automaticamente.",
    },
    'help_shortcut_escape': {
        'fr': "Annuler l'outil en cours (recadrage, forme, polygone…) et revenir à Sélection",
        'en': "Cancel the current tool (crop, shape, polygon…) and go back to Select",
        'es': "Cancelar la herramienta actual (recorte, forma, polígono…) y volver a Selección",
        'de': "Aktuelles Werkzeug abbrechen (Zuschneiden, Form, Polygon…) und zu Auswahl zurückkehren",
        'it': "Annulla lo strumento corrente (ritaglio, forma, poligono…) e torna a Selezione",
        'pt': "Cancelar a ferramenta atual (recorte, forma, polígono…) e voltar a Seleção",
    },
    'help_shortcut_enter': {
        'fr': "Valider le recadrage en cours, ou fermer et remplir le polygone en cours",
        'en': "Confirm the current crop, or close and fill the current polygon",
        'es': "Confirmar el recorte actual, o cerrar y rellenar el polígono actual",
        'de': "Aktuellen Zuschnitt bestätigen, oder aktuelles Polygon schließen und füllen",
        'it': "Conferma il ritaglio corrente, oppure chiudi e riempi il poligono corrente",
        'pt': "Confirmar o recorte atual, ou fechar e preencher o polígono atual",
    },
    'help_shortcut_zoom': {
        'fr': "Zoomer / dézoomer, centré sur le canevas", 'en': "Zoom in/out, centered on the canvas",
        'es': "Acercar / alejar, centrado en el lienzo", 'de': "Vergrößern/Verkleinern, zentriert auf der Leinwand",
        'it': "Ingrandisci/riduci, centrato sulla tela", 'pt': "Aumentar/diminuir zoom, centrado na tela",
    },
    'help_shortcut_pan': {
        'fr': "Défiler horizontalement dans le canevas",
        'en': "Scroll the canvas horizontally", 'es': "Desplazarse horizontalmente por el lienzo",
        'de': "Horizontal durch die Leinwand scrollen", 'it': "Scorri orizzontalmente sulla tela",
        'pt': "Deslocar a tela horizontalmente",
    },
    'help_shortcut_right_click_cancel': {
        'fr': "Sur un calque image : ouvre un petit menu (copier, coller, dupliquer)",
        'en': "On an image layer: opens a small menu (copy, paste, duplicate)",
        'es': "Sobre una capa de imagen: abre un pequeño menú (copiar, pegar, duplicar)",
        'de': "Auf einer Bildebene: öffnet ein kleines Menü (kopieren, einfügen, duplizieren)",
        'it': "Su un livello immagine: apre un piccolo menu (copia, incolla, duplica)",
        'pt': "Numa camada de imagem: abre um pequeno menu (copiar, colar, duplicar)",
    },
    'help_shortcut_double_click_text': {
        'fr': "Sur un texte, avec l'outil Sélection : modifier son contenu",
        'en': "On a text object, with the Select tool: edit its content",
        'es': "Sobre un texto, con la herramienta Selección: editar su contenido",
        'de': "Auf einem Textobjekt, mit dem Auswahlwerkzeug: dessen Inhalt bearbeiten",
        'it': "Su un testo, con lo strumento Selezione: modificane il contenuto",
        'pt': "Num texto, com a ferramenta Seleção: editar o seu conteúdo",
    },

    # Right-click section paragraph
    'help_right_click_text': {
        'fr': "Un clic droit sur un calque image ouvre un petit menu contextuel juste à cet endroit, avec trois actions : Copier (ce calque uniquement, vers le presse-papiers), Coller (le contenu du presse-papiers comme nouveau calque) et Dupliquer (une copie légèrement décalée de ce calque).",
        'en': "Right-clicking an image layer opens a small context menu right there, with three actions: Copy (just that layer, to the clipboard), Paste (the clipboard's content as a new layer), and Duplicate (a slightly offset copy of that layer).",
        'es': "Hacer clic derecho en una capa de imagen abre un pequeño menú contextual justo ahí, con tres acciones: Copiar (solo esa capa, al portapapeles), Pegar (el contenido del portapapeles como una nueva capa) y Duplicar (una copia ligeramente desplazada de esa capa).",
        'de': "Ein Rechtsklick auf eine Bildebene öffnet dort ein kleines Kontextmenü mit drei Aktionen: Kopieren (nur diese Ebene, in die Zwischenablage), Einfügen (den Inhalt der Zwischenablage als neue Ebene) und Duplizieren (eine leicht versetzte Kopie dieser Ebene).",
        'it': "Un clic destro su un livello immagine apre lì un piccolo menu contestuale con tre azioni: Copia (solo quel livello, negli appunti), Incolla (il contenuto degli appunti come nuovo livello) e Duplica (una copia leggermente spostata di quel livello).",
        'pt': "Clicar com o botão direito numa camada de imagem abre ali um pequeno menu de contexto com três ações: Copiar (apenas essa camada, para a área de transferência), Colar (o conteúdo da área de transferência como nova camada) e Duplicar (uma cópia ligeiramente deslocada dessa camada).",
    },

    # Tips / subtleties (bullet points)
    'help_tip_auto_select': {
        'fr': "Une fois une forme, un texte, un recadrage ou un flou/pixellisation terminé, l'outil Sélection se réactive automatiquement.",
        'en': "Once a shape, text, crop, or blur/pixelate is finished, the Select tool switches back on automatically.",
        'es': "Una vez terminada una forma, un texto, un recorte o un difuminado/pixelado, la herramienta Selección se reactiva automáticamente.",
        'de': "Sobald eine Form, ein Text, ein Zuschnitt oder ein Weichzeichnen/Pixelieren abgeschlossen ist, wird automatisch wieder das Auswahlwerkzeug aktiviert.",
        'it': "Una volta terminata una forma, un testo, un ritaglio o una sfocatura/pixelizzazione, lo strumento Selezione si riattiva automaticamente.",
        'pt': "Assim que uma forma, texto, recorte ou desfoque/pixelização termina, a ferramenta Seleção volta a ativar-se automaticamente.",
    },
    'help_tip_resize_handle': {
        'fr': "Glissez le coin en bas à droite d'un calque ou d'une forme pour le redimensionner (un calque image se redimensionne aussi par son coin en haut à gauche). Maintenez Ctrl ou Maj pendant le geste pour conserver les proportions.",
        'en': "Drag the bottom-right corner of a layer or shape to resize it (an image layer also resizes from its top-left corner). Hold Ctrl or Shift while dragging to keep its proportions.",
        'es': "Arrastra la esquina inferior derecha de una capa o forma para redimensionarla (una capa de imagen también se redimensiona desde su esquina superior izquierda). Mantén Ctrl o Mayús mientras arrastras para conservar las proporciones.",
        'de': "Ziehen Sie an der unteren rechten Ecke einer Ebene oder Form, um sie zu skalieren (eine Bildebene lässt sich auch über die obere linke Ecke skalieren). Halten Sie beim Ziehen Strg oder Umschalt gedrückt, um die Proportionen beizubehalten.",
        'it': "Trascina l'angolo in basso a destra di un livello o di una forma per ridimensionarlo (un livello immagine si ridimensiona anche dall'angolo in alto a sinistra). Tieni premuto Ctrl o Maiusc durante il trascinamento per mantenere le proporzioni.",
        'pt': "Arraste o canto inferior direito de uma camada ou forma para a redimensionar (uma camada de imagem também se redimensiona pelo canto superior esquerdo). Mantenha Ctrl ou Shift enquanto arrasta para manter as proporções.",
    },
    'help_tip_crop_adjust': {
        'fr': "Avant de valider (Entrée), le rectangle de recadrage peut être ajusté : glissez son intérieur pour le déplacer, l'un de ses 4 coins pour le redimensionner.",
        'en': "Before confirming (Enter), the crop rectangle can be adjusted: drag inside it to move it, or any of its 4 corners to resize it.",
        'es': "Antes de confirmar (Intro), el rectángulo de recorte se puede ajustar: arrastra su interior para moverlo, o cualquiera de sus 4 esquinas para redimensionarlo.",
        'de': "Vor dem Bestätigen (Eingabe) lässt sich das Zuschneiderechteck anpassen: Ziehen Sie im Inneren, um es zu verschieben, oder an einer seiner 4 Ecken, um es zu skalieren.",
        'it': "Prima di confermare (Invio), il rettangolo di ritaglio può essere regolato: trascina il suo interno per spostarlo, o uno dei suoi 4 angoli per ridimensionarlo.",
        'pt': "Antes de confirmar (Enter), o retângulo de recorte pode ser ajustado: arraste o seu interior para o mover, ou qualquer um dos seus 4 cantos para o redimensionar.",
    },
    'help_tip_nondestructive_effects': {
        'fr': "Les zones floutées ou pixellisées sont non destructives : elles restent sélectionnables et réglables (intensité, déplacement, redimensionnement), et les supprimer révèle l'image d'origine en dessous.",
        'en': "Blurred or pixelated areas are non-destructive: they stay selectable and adjustable (intensity, position, size), and deleting one reveals the original image underneath.",
        'es': "Las zonas difuminadas o pixeladas son no destructivas: siguen siendo seleccionables y ajustables (intensidad, posición, tamaño), y al eliminarlas se revela la imagen original debajo.",
        'de': "Weichgezeichnete oder pixelierte Bereiche sind nicht-destruktiv: Sie bleiben auswählbar und anpassbar (Intensität, Position, Größe), und beim Löschen erscheint wieder das darunterliegende Originalbild.",
        'it': "Le aree sfocate o pixelizzate non sono distruttive: restano selezionabili e regolabili (intensità, posizione, dimensione), ed eliminandole si rivela l'immagine originale sottostante.",
        'pt': "As áreas desfocadas ou pixelizadas não são destrutivas: continuam selecionáveis e ajustáveis (intensidade, posição, tamanho), e ao eliminá-las revela-se a imagem original por baixo.",
    },
    'help_tip_linked_layers': {
        'fr': "Dans le panneau des calques, cliquez sur l'icône maillon d'un calque puis sur celle d'un autre pour les lier : ils se déplaceront ensemble. Un contour pointillé coloré et un badge sur le canevas indiquent les calques liés ; cliquez à nouveau sur le maillon d'un calque lié pour le délier.",
        'en': "In the layers panel, click a layer's chain icon, then another one's, to link them: they'll now move together. A colored dashed outline and badge on the canvas mark linked layers; click a linked layer's chain icon again to unlink it.",
        'es': "En el panel de capas, haz clic en el icono de enlace de una capa y luego en el de otra para vincularlas: se moverán juntas. Un contorno de puntos de color y una insignia en el lienzo marcan las capas vinculadas; haz clic de nuevo en el icono de una capa vinculada para desvincularla.",
        'de': "Klicken Sie im Ebenenpanel auf das Verknüpfungssymbol einer Ebene und dann auf das einer anderen, um sie zu verknüpfen: Sie bewegen sich jetzt gemeinsam. Ein farbiger gestrichelter Rahmen und ein Abzeichen auf der Leinwand markieren verknüpfte Ebenen; klicken Sie erneut auf das Symbol einer verknüpften Ebene, um sie zu lösen.",
        'it': "Nel pannello dei livelli, clicca sull'icona di collegamento di un livello e poi su quella di un altro per collegarli: ora si sposteranno insieme. Un contorno tratteggiato colorato e un badge sulla tela contrassegnano i livelli collegati; clicca di nuovo sull'icona di un livello collegato per scollegarlo.",
        'pt': "No painel de camadas, clique no ícone de ligação de uma camada e depois no de outra para as ligar: vão mover-se juntas. Um contorno tracejado colorido e um emblema na tela marcam as camadas ligadas; clique novamente no ícone de uma camada ligada para a desligar.",
    },
    'help_tip_paste_clipboard': {
        'fr': "Une image copiée (par exemple depuis Nautilus ou une capture d'écran) peut être collée directement comme nouveau calque via le bouton dédié.",
        'en': "An image copied elsewhere (e.g. from Nautilus, or a screenshot) can be pasted directly as a new layer using the dedicated button.",
        'es': "Una imagen copiada en otro lugar (por ejemplo, desde Nautilus, o una captura de pantalla) se puede pegar directamente como una nueva capa con el botón dedicado.",
        'de': "Ein anderswo kopiertes Bild (z. B. aus Nautilus oder ein Screenshot) kann über die dafür vorgesehene Schaltfläche direkt als neue Ebene eingefügt werden.",
        'it': "Un'immagine copiata altrove (ad esempio da Nautilus, o uno screenshot) può essere incollata direttamente come nuovo livello con il pulsante dedicato.",
        'pt': "Uma imagem copiada noutro local (por exemplo, do Nautilus, ou uma captura de ecrã) pode ser colada diretamente como uma nova camada através do botão dedicado.",
    },
    'help_tip_canvas_autogrow': {
        'fr': "Superposer ou coller une image plus grande que le canevas agrandit automatiquement celui-ci pour l'accueillir à sa taille d'origine, au lieu de la réduire.",
        'en': "Overlaying or pasting an image larger than the canvas automatically grows it to fit that image at full size, instead of shrinking it down.",
        'es': "Superponer o pegar una imagen más grande que el lienzo lo amplía automáticamente para encajarla a tamaño completo, en lugar de reducirla.",
        'de': "Das Überlagern oder Einfügen eines Bilds, das größer als die Leinwand ist, vergrößert diese automatisch, um es in voller Größe aufzunehmen, statt es zu verkleinern.",
        'it': "Sovrapporre o incollare un'immagine più grande della tela la ingrandisce automaticamente per adattarla a piena dimensione, invece di rimpicciolirla.",
        'pt': "Sobrepor ou colar uma imagem maior do que a tela amplia-a automaticamente para a encaixar em tamanho completo, em vez de a reduzir.",
    },
    'help_tip_border_zero': {
        'fr': "Pour les bordures (image ou texte) : la largeur affichée fait tout — 0 signifie « pas de bordure », toute valeur supérieure dessine une bordure de cette épaisseur.",
        'en': "For borders (image or text): the width field does it all — 0 means \"no border\", any value above draws a border of that thickness.",
        'es': "Para los bordes (imagen o texto): el campo de anchura lo hace todo — 0 significa «sin borde», cualquier valor superior dibuja un borde de ese grosor.",
        'de': "Für Rahmen (Bild oder Text): Das Breitenfeld erledigt alles — 0 bedeutet „kein Rahmen“, jeder höhere Wert zeichnet einen Rahmen dieser Stärke.",
        'it': "Per i bordi (immagine o testo): il campo larghezza fa tutto — 0 significa «nessun bordo», qualsiasi valore superiore disegna un bordo di quello spessore.",
        'pt': "Para as bordas (imagem ou texto): o campo de largura faz tudo — 0 significa «sem borda», qualquer valor acima desenha uma borda dessa espessura.",
    },
    'help_tip_tabs': {
        'fr': "Chaque onglet correspond à une image ouverte indépendamment. Fermer un onglet contenant des modifications non enregistrées proposera de les enregistrer d'abord.",
        'en': "Each tab holds an independently open image. Closing a tab with unsaved changes will offer to save them first.",
        'es': "Cada pestaña corresponde a una imagen abierta de forma independiente. Cerrar una pestaña con cambios sin guardar ofrecerá guardarlos primero.",
        'de': "Jeder Tab enthält ein unabhängig geöffnetes Bild. Beim Schließen eines Tabs mit nicht gespeicherten Änderungen wird angeboten, diese zuerst zu speichern.",
        'it': "Ogni scheda corrisponde a un'immagine aperta in modo indipendente. Chiudendo una scheda con modifiche non salvate verrà proposto di salvarle prima.",
        'pt': "Cada separador corresponde a uma imagem aberta de forma independente. Fechar um separador com alterações não guardadas irá propor guardá-las primeiro.",
    },
    'help_tip_crash_recovery': {
        'fr': "En cas de fermeture inattendue (plantage, coupure de courant), l'application propose de récupérer les images non enregistrées au prochain démarrage.",
        'en': "After an unexpected shutdown (crash, power loss), the app offers to recover unsaved images the next time it starts.",
        'es': "Tras un cierre inesperado (fallo, corte de energía), la aplicación ofrece recuperar las imágenes no guardadas la próxima vez que se inicie.",
        'de': "Nach einem unerwarteten Beenden (Absturz, Stromausfall) bietet die App beim nächsten Start an, nicht gespeicherte Bilder wiederherzustellen.",
        'it': "Dopo una chiusura imprevista (crash, interruzione di corrente), l'app propone di recuperare le immagini non salvate al prossimo avvio.",
        'pt': "Após um encerramento inesperado (falha, corte de energia), a aplicação propõe recuperar as imagens não guardadas no próximo arranque.",
    },
}


def tt(key):
    """Look up a UI string for the detected UI language, falling back
    to English and then to the raw key if nothing else matches."""
    entry = UI_STRINGS.get(key)
    if not entry:
        return key
    return entry.get(UI_LANG) or entry.get('en') or key


# Low-level helpers (cairo surfaces)

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


def surface_to_thumb_pixbuf(surf, size=28):
    """Small square thumbnail (letterboxed, transparent padding) for the
    layers panel, built from a layer's cairo surface. Goes through PNG
    bytes rather than raw ARGB32 data, since cairo's premultiplied-alpha
    byte order doesn't map directly onto GdkPixbuf's."""
    w, h = surf.get_width(), surf.get_height()
    if w <= 0 or h <= 0:
        return None
    scale = min(size / w, size / h)
    dw, dh = max(1, round(w * scale)), max(1, round(h * scale))
    thumb = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(thumb)
    cr.translate((size - dw) / 2, (size - dh) / 2)
    cr.scale(scale, scale)
    cr.set_source_surface(surf, 0, 0)
    cr.paint()
    buf = BytesIO()
    thumb.write_to_png(buf)
    buf.seek(0)
    try:
        loader = GdkPixbuf.PixbufLoader()
        loader.write(buf.getvalue())
        loader.close()
        return loader.get_pixbuf()
    except GLib.Error:
        return None


# Image files copied from Nautilus (or another file manager) rather than
# pasted as raw pixel data.
FILE_MANAGER_IMAGE_EXTENSIONS = (
    '.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff', '.tif', '.gif')


def parse_clipboard_file_uris(text):
    """Turn the text payload of a `x-special/gnome-copied-files` (Nautilus,
    Files) or `text/uri-list` (most other file managers) clipboard format
    into a list of local paths, keeping only image files that actually
    exist on disk. `x-special/gnome-copied-files` starts with a `copy`/`cut`
    marker line that we simply ignore — we always copy, never move."""
    if text is None:
        return []
    paths = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line in ('copy', 'cut') or line.startswith('#'):
            continue
        try:
            path, _ = GLib.filename_from_uri(line)
        except GLib.Error:
            continue
        if os.path.isfile(path) and path.lower().endswith(FILE_MANAGER_IMAGE_EXTENSIONS):
            paths.append(path)
    return paths


def read_stream_bytes(stream, chunk_size=65536):
    """Fully drain a Gio.InputStream (small clipboard payloads only) and
    return the raw bytes. Used instead of the higher-level text-reading
    clipboard API below, which can't decode custom mime types like
    `x-special/gnome-copied-files` — see paste_as_layer()."""
    chunks = []
    while True:
        data = stream.read_bytes(chunk_size, None).get_data()
        if not data:
            break
        chunks.append(data)
        if len(data) < chunk_size:
            break
    return b''.join(chunks)


def next_id_counter():
    n = 0
    while True:
        n += 1
        yield n


_ID_GEN = next_id_counter()

# Linked layers ("move together") are marked with a shared small integer
# in layer['link_group']. Each group gets a distinct, stable color from
# this palette (cycling by group id) so the same group always reads as
# the same color in both the layers panel and on the canvas. Blue is
# deliberately left out — it's already the selection accent color.
LINK_GROUP_COLORS = [
    (0.90, 0.32, 0.24),   # red-orange
    (0.18, 0.65, 0.40),   # green
    (0.95, 0.61, 0.07),   # amber
    (0.61, 0.35, 0.86),   # purple
    (0.90, 0.32, 0.68),   # pink
    (0.20, 0.68, 0.68),   # teal
]


def link_group_color(gid):
    """RGB (0-1 floats) for a link-group id, or None if gid is falsy."""
    if not gid:
        return None
    return LINK_GROUP_COLORS[(gid - 1) % len(LINK_GROUP_COLORS)]


def link_group_css_class(gid):
    """CSS class name for a link-group id (see .ie-link-N in _ICON_CSS)."""
    return f"ie-link-{(gid - 1) % len(LINK_GROUP_COLORS)}"


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
    autosave shouldn't be able to crash the editor.

    The actual PNG/base64 encoding of the base image and every layer is
    the expensive part — on a large photo it could take a second or more
    of pure CPU time. This used to run straight on the GTK main loop
    every 20s, which froze the whole UI for that long: input (a drag in
    progress, a click...) kept getting queued up and only appeared once
    the freeze ended, which looked like lag or a memory leak. Only the
    cheap part (grabbing references to the current surfaces/metadata,
    which never happens more than once per tick) runs on the main
    thread; the slow encoding + file write happens in a background
    thread. Surfaces are only ever *replaced*, never painted into in
    place elsewhere in this file, so reading one from a background
    thread while the main thread moves on to a new surface is safe."""
    if not canvas.width or not canvas.dirty:
        return
    if getattr(canvas, '_autosave_inflight', False):
        return  # previous autosave still writing; this tick's data will be picked up next time
    canvas._autosave_inflight = True
    snapshot = {
        'version': 1,
        'saved_at': time.time(),
        'original_path': canvas.current_path,
        'width': canvas.width,
        'height': canvas.height,
        'img_rect': dict(canvas.img_rect) if canvas.img_rect else None,
        'base_surface': canvas.surface,
        'layers': [dict(l) for l in canvas.layers],
        'annotations': [canvas._ann_to_json(a) for a in canvas.annotations],
        'autosave_id': canvas.autosave_id,
    }

    def worker():
        try:
            payload = {
                'version': snapshot['version'],
                'saved_at': snapshot['saved_at'],
                'original_path': snapshot['original_path'],
                'width': snapshot['width'],
                'height': snapshot['height'],
                'img_rect': snapshot['img_rect'],
                'base_png_b64': Canvas._surface_to_b64(snapshot['base_surface'])
                if snapshot['base_surface'] else None,
                'layers': [
                    {'id': l['id'], 'x': l['x'], 'y': l['y'], 'w': l['w'], 'h': l['h'],
                     'orig_w': l.get('orig_w'), 'orig_h': l.get('orig_h'),
                     'opacity': l.get('opacity', 1.0), 'name': l.get('name', ''),
                     'visible': l.get('visible', True),
                     'effect_type': l.get('effect_type'),
                     'level': l.get('level'),
                     'attached_layers': list(l['attached_layers']) if l.get('attached_layers') is not None else None,
                     'hidden_by_source': l.get('hidden_by_source', False),
                     'border_color': list(l['border_color']) if l.get('border_color') is not None else None,
                     'border_width': l.get('border_width', 0),
                     'png_b64': Canvas._surface_to_b64(l['surface']) if not l.get('effect_type') else None}
                    for l in snapshot['layers']
                ],
                'annotations': snapshot['annotations'],
            }
            path = autosave_path(snapshot['autosave_id'])
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(payload, f)
            os.replace(tmp, path)
        except Exception:
            pass
        finally:
            canvas._autosave_inflight = False

    threading.Thread(target=worker, daemon=True).start()


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
        self._autosave_inflight = False

        self.tool = 'select'
        self.color = (0.92, 0.13, 0.13, 1.0)
        self.fill_enabled = False
        self.fill_color = (1.0, 1.0, 1.0, 1.0)
        self.border_color = (0.0, 0.0, 0.0, 1.0)
        self.border_width = 0.0   # for new images/text: 0 = no border, >0 = border drawn
        self.stroke_width = 4.0   # for new shapes (arrow/line/rect/circle/polygon)
        self.next_link_group_id = 1   # linked layers: layer['link_group'] shares this id
        self.font_size = 28.0
        self.arrow_head_style = 'end'   # 'end' | 'start' | 'both' | 'none'
        self.blur_level = 4             # higher = blurrier
        self.pixelate_level = 4         # higher = chunkier blocks
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
        self._linked_move_orig = {}   # sibling layers moving together with the dragged one

        self.undo_stack = []
        self.redo_stack = []

        # Cache of the checkerboard + base image, pre-composited at the
        # current zoom level — see _ensure_static_background(). Avoids
        # cairo having to resample the full-resolution image (and the
        # checker tile) through the zoom transform on every single
        # redraw, which is the main source of lag while dragging or
        # resizing something on top of a large photo.
        self._static_bg = None
        self._static_bg_key = None
        self._static_bg_scale = 1.0

        # Small thumbnail of the base image shown in the layers panel,
        # cached the same way — regenerating it from the full-resolution
        # image on every panel refresh (which happens after almost every
        # action) was itself a source of lag on large photos.
        self._base_thumb = None
        self._base_thumb_key = None

        self.set_draw_func(self._on_draw)

        drag = Gtk.GestureDrag()
        drag.set_button(0)  # any button — GTK defaults to primary-only,
                             # which silently ate right-clicks before.
        drag.connect('drag-begin', self._on_drag_begin)
        drag.connect('drag-update', self._on_drag_update)
        drag.connect('drag-end', self._on_drag_end)
        self.add_controller(drag)

        click = Gtk.GestureClick()
        click.set_button(0)  # same reason
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
        """Mouse wheel (or two-finger scroll on a trackpad) zooms
        in/out. Shift+wheel is left alone so it can still be used to
        pan horizontally in the scrolled view."""
        state = controller.get_current_event_state()
        if state & Gdk.ModifierType.SHIFT_MASK:
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
        """Cheap undo checkpoint. Elsewhere in this file, both the base
        `self.surface` and every `layer['surface']` are only ever
        *replaced* wholesale (crop, flip, flatten, a new layer...) —
        never painted into in place — so it's safe to keep a plain
        reference to them here instead of cloning the pixels. Only the
        small, actually-mutable bits (geometry, the layers list itself,
        the annotation dicts that get edited in place while dragging)
        need real copies.

        This used to clone every layer's full-resolution surface (plus
        the base image) on every single push_undo(), including the one
        at the start of a plain move — the main cause of the stutter
        when starting to drag an image around."""
        return {
            'surface': self.surface,
            'width': self.width,
            'height': self.height,
            'img_rect': dict(self.img_rect) if self.img_rect else None,
            'layers': [dict(l) for l in self.layers],
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
        """Flatten the base image + layers + annotations into one surface.
        Blur/pixelate areas are recomputed live from whatever is currently
        underneath them (see _paint_effect_layer), so this always reflects
        the current state of the document rather than a stale snapshot."""
        surf = self._render_layers_surface()
        if surf is None:
            surf = cairo.ImageSurface(
                cairo.FORMAT_ARGB32, max(1, int(self.width)), max(1, int(self.height)))
        cr = cairo.Context(surf)
        for ann in self.annotations:
            self._draw_annotation(cr, ann, selected=False)
        return surf

    def _render_layers_surface(self, image_filter=cairo.FILTER_GOOD, interacting=False):
        """Base image + all layers (dynamic effects included), no
        annotations. Shared by render_composite() (export/save/copy) and
        the on-screen paint, so both stay in sync."""
        if not self.width or not self.height:
            return None
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(self.width), int(self.height))
        cr = cairo.Context(surf)
        if self.surface:
            cr.set_source_surface(self.surface, 0, 0)
            cr.paint()
        self._paint_layers(cr, surf, image_filter, interacting)
        return surf

    def _paint_layers(self, cr, dst_surface, image_filter=cairo.FILTER_GOOD, interacting=False):
        """Paint every visible layer, front-to-back, into `cr` (whose
        target must be `dst_surface`). Blur/pixelate layers are recomputed
        on the fly from `dst_surface` as it stands at that point in the
        stack — i.e. from exactly what is currently beneath them."""
        for layer in self.layers:
            if not layer.get('visible', True):
                continue
            if layer.get('effect_type'):
                self._paint_effect_layer(cr, dst_surface, layer, interacting)
            else:
                cr.save()
                cr.translate(layer['x'], layer['y'])
                cr.scale(layer['w'] / layer['orig_w'], layer['h'] / layer['orig_h'])
                cr.set_source_surface(layer['surface'], 0, 0)
                cr.get_source().set_filter(image_filter)
                cr.paint_with_alpha(layer['opacity'])
                cr.restore()
            self._draw_layer_border(cr, layer)

    def _paint_effect_layer(self, cr, dst_surface, layer, interacting=False):
        """Blur/pixelate a layer non-destructively and dynamically: the
        result is recomputed every time from whatever is already painted
        into `dst_surface` beneath this point in the stack, using the
        effect's own current rect and intensity (`layer['level']`). Moving
        or changing a layer underneath, or adjusting the intensity, is
        reflected the next time this runs — nothing is ever baked in.

        While the user is actively dragging/resizing anything on the
        canvas (`interacting=True`), the zone is simply left transparent
        instead of recomputing it: recomputing every frame of a drag is
        one of the more expensive parts of a redraw, and painting a
        frozen snapshot there instead was misleading since it didn't
        track the effect's new rect or whatever changed underneath it.
        The real blur/pixelate reappears the instant interaction stops."""
        x = max(0, int(layer['x']))
        y = max(0, int(layer['y']))
        w = min(int(layer['w']), self.width - x)
        h = min(int(layer['h']), self.height - y)
        if w < 1 or h < 1:
            return
        if interacting:
            return

        kind = layer.get('effect_type')
        dst_surface.flush()

        region = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        rc = cairo.Context(region)
        rc.set_source_surface(dst_surface, -x, -y)
        rc.paint()

        factor = max(2, int(layer.get('level', 4)))
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

        cr.save()
        cr.set_source_surface(result, x, y)
        cr.paint_with_alpha(layer.get('opacity', 1.0))
        cr.restore()

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

    def _ensure_static_background(self):
        """Checkerboard + base image, pre-composited into a single
        bitmap — see the module-level notes above for why. Capped at
        the image's own native resolution: when zoomed out we cache it
        at the (smaller) on-screen size as before, but once zoomed in
        past 100% we keep the cache at native size and let cairo's
        transform do the (comparatively cheap) upscaling at paint time,
        instead of allocating and rendering an ever-larger bitmap for
        every zoom level — that unbounded growth was itself a source of
        lag while zooming in on a large photo."""
        cache_scale = min(self.zoom, 1.0)
        key = (id(self.surface), self.width, self.height, round(cache_scale, 4))
        if self._static_bg is not None and self._static_bg_key == key:
            return self._static_bg
        w = max(1, round(self.width * cache_scale))
        h = max(1, round(self.height * cache_scale))
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        scr = cairo.Context(surf)
        scr.scale(cache_scale, cache_scale)
        self._draw_checkerboard(scr, 0, 0, self.width, self.height)
        if self.surface:
            scr.set_source_surface(self.surface, 0, 0)
            scr.paint()
        self._static_bg = surf
        self._static_bg_key = key
        self._static_bg_scale = cache_scale
        return surf

    def ensure_base_thumb(self, size=28):
        """Cached small thumbnail of the base image for the layers
        panel — see the comment on self._base_thumb in __init__."""
        key = id(self.surface)
        if self._base_thumb is not None and self._base_thumb_key == key:
            return self._base_thumb
        thumb = surface_to_thumb_pixbuf(self.surface, size) if self.surface else None
        self._base_thumb = thumb
        self._base_thumb_key = key
        return thumb

    def _draw_layer_border(self, cr, layer):
        """Draw the optional border/frame around an image layer, inset so
        it stays fully inside the layer's own bounds rather than growing
        it. Unlike _draw_effect_marker, this is real content: it's called
        from both the live on-screen paint and render_composite(), so it
        is included in the saved/exported image."""
        bw = layer.get('border_width', 0)
        if bw <= 0:
            return
        w, h = layer['w'], layer['h']
        cr.save()
        cr.set_source_rgba(*layer.get('border_color', (0.0, 0.0, 0.0, 1.0)))
        cr.set_line_width(bw)
        cr.rectangle(layer['x'] + bw / 2, layer['y'] + bw / 2,
                     max(0.01, w - bw), max(0.01, h - bw))
        cr.stroke()
        cr.restore()

    def _draw_effect_marker(self, cr, layer):
        """Minimal, persistent outline around every blur/pixelate area so
        it stays easy to spot in the editor even when not selected — just
        a dashed frame, no filled background. Purely a screen-space aid:
        render_composite() (used for saving, exporting, copying, and for
        capturing pixels when applying a *new* effect) never calls this,
        so it never ends up in the final image."""
        x, y, w, h = layer['x'], layer['y'], layer['w'], layer['h']
        cr.save()
        cr.set_source_rgba(1.0, 0.62, 0.0, 0.85)
        cr.set_line_width(1.4 / self.zoom)
        cr.set_dash([4.0 / self.zoom, 3.0 / self.zoom])
        cr.rectangle(x, y, w, h)
        cr.stroke()
        cr.restore()

    def _draw_link_marker(self, cr, layer, selected=False):
        """Persistent, colour-coded marker for layers that are linked
        together (move as one): a dashed outline in the group's colour
        (skipped on the actively-selected layer, whose blue selection
        outline already stands out on its own) plus a small chain badge
        in the corner — always shown, so the whole linked set is visible
        on the canvas at a glance, not just while one member is selected.
        The same colour is used for this group in the layers panel."""
        color = link_group_color(layer.get('link_group'))
        if not color:
            return
        x, y, w, h = layer['x'], layer['y'], layer['w'], layer['h']
        r, g, b = color
        if not selected:
            cr.save()
            cr.set_source_rgba(r, g, b, 0.85)
            cr.set_line_width(1.6 / self.zoom)
            cr.set_dash([5.0 / self.zoom, 3.5 / self.zoom])
            cr.rectangle(x, y, w, h)
            cr.stroke()
            cr.restore()

        cr.save()
        bx = x + 10.0 / self.zoom
        by = y + 10.0 / self.zoom
        radius = 8.0 / self.zoom
        cr.set_source_rgba(r, g, b, 1.0)
        cr.arc(bx, by, radius, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.set_line_width(1.3 / self.zoom)
        ring_r = radius * 0.34
        off = radius * 0.30
        cr.arc(bx - off, by, ring_r, 0, 2 * math.pi)
        cr.stroke()
        cr.arc(bx + off, by, ring_r, 0, 2 * math.pi)
        cr.stroke()
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

        # Pre-scaled checkerboard + base image. When zoomed out this is
        # cached at exactly the on-screen size, so this is a plain 1:1
        # blit with no resampling cost. When zoomed in past 100% the
        # cache stays at native resolution (see _ensure_static_background)
        # and this extra scale upsamples it — cheaper than re-rendering
        # a full-size bitmap on every zoom change.
        bg = self._ensure_static_background()
        if bg is not None:
            cr.save()
            extra = self.zoom / self._static_bg_scale if self._static_bg_scale else 1.0
            cr.scale(extra, extra)
            cr.set_source_surface(bg, 0, 0)
            cr.paint()
            cr.restore()

        cr.scale(self.zoom, self.zoom)

        self._draw_image_bounds(cr)

        # Nearest-neighbour while a drag is actively in progress (moving,
        # resizing...) is visibly cheaper per frame than the default
        # smooth filter; the last frame after drag-end repaints with the
        # good filter again for a crisp final result.
        interacting = self._mode is not None
        layer_filter = cairo.FILTER_FAST if interacting else cairo.FILTER_GOOD

        content = self._render_layers_surface(layer_filter, interacting=interacting)
        if content is not None:
            cr.save()
            cr.set_source_surface(content, 0, 0)
            cr.get_source().set_filter(layer_filter)
            cr.paint()
            cr.restore()

        for layer in self.layers:
            if layer.get('visible', True) and layer.get('effect_type') \
                    and self.selected != ('layer', layer):
                self._draw_effect_marker(cr, layer)
            if layer.get('visible', True) and layer.get('link_group'):
                self._draw_link_marker(cr, layer, selected=(self.selected == ('layer', layer)))
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

    def _draw_selection_outline(self, cr, x, y, w, h):
        """Prominent selection outline for the currently-selected layer
        or object: a soft white halo behind a solid accent-coloured
        line, so it stands out clearly regardless of what's underneath
        — the old thin single dashed line was easy to miss."""
        cr.save()
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_source_rgba(1, 1, 1, 0.65)
        cr.set_line_width(5.5 / self.zoom)
        cr.rectangle(x, y, w, h)
        cr.stroke()
        cr.set_source_rgba(0.13, 0.55, 1.0, 1.0)
        cr.set_line_width(2.4 / self.zoom)
        cr.rectangle(x, y, w, h)
        cr.stroke()
        cr.restore()

    def _draw_handle(self, cr, hx, hy, hs):
        """A round selection handle: white fill with an accent-coloured
        ring, easier to spot and to grab than a small solid square."""
        cr.save()
        cr.set_source_rgba(0.13, 0.55, 1.0, 1.0)
        cr.arc(hx, hy, hs / 2 + 1.5 / self.zoom, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 1)
        cr.arc(hx, hy, hs / 2, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

    def _draw_layer_selection(self, cr, layer):
        """Selection for an image/effect layer: on top of the shared
        outline+handle, add a light accent-coloured wash over the whole
        layer plus bold corner brackets, so the selected image is obvious
        at a glance even against busy photo content — a thin edge line
        alone is too easy to miss."""
        x, y, w, h = layer['x'], layer['y'], layer['w'], layer['h']
        cr.save()
        cr.set_source_rgba(0.13, 0.55, 1.0, 0.16)
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.restore()

        self._draw_selection_outline(cr, x, y, w, h)
        self._draw_corner_brackets(cr, x, y, w, h)

        hs = self._handle_size()
        self._draw_handle(cr, x + w, y + h, hs)
        self._draw_handle(cr, x, y, hs)

    def _draw_corner_brackets(self, cr, x, y, w, h):
        """Bold accent-coloured L-shaped marks at all four corners of a
        selected layer — mostly decorative, but two of them (top-left and
        bottom-right) also mark the actual draggable resize handles, via
        their round handle."""
        arm = min(w, h) * 0.22
        arm = max(10.0 / self.zoom, min(arm, 26.0 / self.zoom))
        cr.save()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.set_line_width(4.5 / self.zoom)
        for cx, cy, dx, dy in (
                (x, y, 1, 1), (x + w, y, -1, 1),
                (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
            cr.move_to(cx + dx * arm, cy)
            cr.line_to(cx, cy)
            cr.line_to(cx, cy + dy * arm)
        cr.stroke_preserve()
        cr.set_source_rgba(0.13, 0.55, 1.0, 1.0)
        cr.set_line_width(2.2 / self.zoom)
        for cx, cy, dx, dy in (
                (x, y, 1, 1), (x + w, y, -1, 1),
                (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
            cr.move_to(cx + dx * arm, cy)
            cr.line_to(cx, cy)
            cr.line_to(cx, cy + dy * arm)
        cr.stroke()
        cr.restore()

    def _handle_size(self):
        return 14.0 / self.zoom

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
        hs = self._handle_size()
        for _hid, hx, hy in self._crop_handles(r):
            self._draw_handle(cr, hx, hy, hs)

    def _crop_handles(self, r):
        return [
            ('tl', r['x'], r['y']), ('tr', r['x'] + r['w'], r['y']),
            ('bl', r['x'], r['y'] + r['h']), ('br', r['x'] + r['w'], r['y'] + r['h']),
        ]

    def _point_in_crop_handle(self, r, x, y):
        hs = self._handle_size()
        for hid, hx, hy in self._crop_handles(r):
            if abs(x - hx) <= hs and abs(y - hy) <= hs:
                return hid
        return None

    @staticmethod
    def _point_in_crop_body(r, x, y):
        return r['x'] <= x <= r['x'] + r['w'] and r['y'] <= y <= r['y'] + r['h']

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
            text_bw = ann.get('border_width', 0)
            if text_bw > 0:
                cr.set_source_rgba(*ann.get('border_color', (0.0, 0.0, 0.0, 1.0)))
                cr.set_line_width(text_bw)
                cr.rectangle(bg_x + text_bw / 2, bg_y + text_bw / 2,
                             max(0.01, bg_w - text_bw), max(0.01, bg_h - text_bw))
                cr.stroke()
            cr.set_source_rgba(r, g, b, a)
            cr.move_to(ann['x'], ann['y'])
            cr.show_text(ann['text'])
            bbox = (bg_x, bg_y, bg_w, bg_h) if (fill or text_bw > 0) else \
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
            pad = 5.0 / self.zoom
            self._draw_selection_outline(cr, bbox[0] - pad, bbox[1] - pad,
                                          bbox[2] + 2 * pad, bbox[3] + 2 * pad)

        if selected:
            handles = self._annotation_handles(ann)
            if handles:
                hs = self._handle_size()
                for _hid, hx, hy in handles:
                    self._draw_handle(cr, hx, hy, hs)

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
        """Which resize handle (if any) a point falls on for a layer:
        'br' (bottom-right) or 'tl' (top-left)."""
        hs = self._handle_size()
        x0, y0 = layer['x'], layer['y']
        x1, y1 = x0 + layer['w'], y0 + layer['h']
        if abs(x - x1) <= hs and abs(y - y1) <= hs:
            return 'br'
        if abs(x - x0) <= hs and abs(y - y0) <= hs:
            return 'tl'
        return None

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
            # Lines and arrows are thin, so on top of their own stroke
            # width keep a generous minimum click tolerance in *screen*
            # pixels (converted back to image-space units) — otherwise
            # they become very hard to hit once zoomed out on a large
            # image, since the old fixed tolerance shrank along with it.
            tol = max(tol, 16.0 / self.zoom)
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
            if not layer.get('visible', True):
                continue
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
            gid = obj.get('link_group')
            self.layers.remove(obj)
            self._cleanup_effect_attachments(obj)
            if gid:
                self._dissolve_link_group_if_needed(gid)
        self.selected = None
        self.queue_draw()
        self.app.update_status()

    def _dissolve_link_group_if_needed(self, gid):
        """A link group only means something with 2+ members — if removing
        or unlinking a layer leaves a single one behind, clear its group
        too instead of leaving an orphaned, meaningless group of one."""
        members = [l for l in self.layers if l.get('link_group') == gid]
        if len(members) == 1:
            members[0]['link_group'] = None

    def link_layers(self, layer_a, layer_b):
        """Link two layers so they move together from now on. If either
        is already part of a link group, the other joins that group; if
        both already belong to (different) groups, the groups merge."""
        if layer_a is layer_b:
            return
        self.push_undo()
        gid_a = layer_a.get('link_group')
        gid_b = layer_b.get('link_group')
        if gid_a and gid_b:
            if gid_a != gid_b:
                for l in self.layers:
                    if l.get('link_group') == gid_b:
                        l['link_group'] = gid_a
        elif gid_a:
            layer_b['link_group'] = gid_a
        elif gid_b:
            layer_a['link_group'] = gid_b
        else:
            gid = self.next_link_group_id
            self.next_link_group_id += 1
            layer_a['link_group'] = gid
            layer_b['link_group'] = gid
        self.queue_draw()
        self.app.update_status()

    def unlink_layer(self, layer):
        """Remove a single layer from its link group (if any)."""
        gid = layer.get('link_group')
        if not gid:
            return
        self.push_undo()
        layer['link_group'] = None
        self._dissolve_link_group_if_needed(gid)
        self.queue_draw()
        self.app.update_status()

    def layers_in_group(self, gid):
        return [l for l in self.layers if l.get('link_group') == gid] if gid else []

    def _rects_intersect(self, ax, ay, aw, ah, bx, by, bw, bh):
        return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by

    def _cleanup_effect_attachments(self, removed_layer):
        """Drop `removed_layer`'s id from every effect's attached_layers
        list. The effect itself is left alone (still visible or hidden,
        whatever it was) — losing its last attached image just makes it
        an independent effect from then on, nothing is deleted for the
        user implicitly."""
        rid = removed_layer.get('id')
        if rid is None:
            return
        for layer in self.layers:
            attached = layer.get('attached_layers')
            if attached and rid in attached:
                layer['attached_layers'] = [i for i in attached if i != rid]

    def _cascade_layer_visibility(self, layer):
        """When a real image layer's visibility is toggled, automatically
        hide/restore any blur or pixelate effect attached to it — but
        only an effect that this cascade itself hid. An effect the user
        hid by hand (its own eye icon) stays hidden even if the source
        image is shown again, since that was an explicit choice."""
        if layer.get('attached_layers') is not None:
            return  # `layer` is itself an effect: nothing to cascade
        lid = layer.get('id')
        layer_by_id = {l['id']: l for l in self.layers}
        for effect in self.layers:
            attached = effect.get('attached_layers')
            if not attached or lid not in attached:
                continue
            alive = [layer_by_id[i] for i in attached if i in layer_by_id]
            any_visible = any(l.get('visible', True) for l in alive)
            if not any_visible and effect.get('visible', True):
                effect['visible'] = False
                effect['hidden_by_source'] = True
            elif any_visible and effect.get('hidden_by_source'):
                effect['visible'] = True
                effect['hidden_by_source'] = False

    def move_layer(self, layer, direction):
        """Reorder a layer in the stack. direction=+1 brings it forward
        (drawn later, so it appears more on top); direction=-1 sends it
        backward. self.layers is painted front-to-back by index, so
        "forward" means a higher index."""
        if layer not in self.layers:
            return
        idx = self.layers.index(layer)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.layers):
            return
        self.push_undo()
        self.layers[idx], self.layers[new_idx] = self.layers[new_idx], self.layers[idx]
        self.queue_draw()
        self.app.update_status()

    # ---- interaction ----------------------------------------------------

    def _on_click(self, gesture, n_press, x, y):
        self.grab_focus()
        if gesture.get_current_button() == Gdk.BUTTON_SECONDARY:
            return
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
                tt('status_polygon_progress').format(n=len(self.polygon_points)))
            return
        if self.tool == 'select' and n_press == 2:
            hit = self.hit_test(ix, iy)
            if hit and hit[0] == 'annotation' and hit[1]['type'] == 'text':
                self.app.prompt_text(None, None, edit=hit[1])

    def _on_drag_begin(self, gesture, start_x, start_y):
        self.grab_focus()
        ix, iy = start_x / self.zoom, start_y / self.zoom
        self._drag_start_img = (ix, iy)

        if gesture.get_current_button() == Gdk.BUTTON_SECONDARY:
            hit = self.hit_test(ix, iy)
            if hit and hit[0] == 'layer':
                self.selected = hit
                self.queue_draw()
                self.app.update_options_visibility()
                self.app.sync_selection_controls()
                self.show_layer_context_menu(hit[1], start_x, start_y)
            self._mode = None
            return

        if self.tool == 'select':
            handle_id = None
            if self.selected and self.selected[0] == 'layer' and \
                    (handle_id := self._point_in_layer_handle(self.selected[1], ix, iy)):
                self.push_undo()
                self._mode = 'resize-layer'
                self._active_handle = handle_id
                self._orig_geom = dict(self.selected[1])
                self._constrain_active = False
                self.app._show_hint(tt('hint_keep_aspect_ratio'), seconds=10)
            elif self.selected and self.selected[0] == 'annotation' and \
                    (handle_id := self._point_in_annotation_handle(self.selected[1], ix, iy)):
                self.push_undo()
                self._mode = 'annotation-handle'
                self._active_handle = handle_id
                self._orig_geom = dict(self.selected[1])
                if self.selected[1]['type'] in ('rect', 'circle'):
                    self._constrain_active = False
                    self.app._show_hint(tt('hint_keep_aspect_ratio'), seconds=10)
            else:
                hit = self.hit_test(ix, iy)
                if hit:
                    self.selected = hit
                    self.push_undo()
                    self._mode = 'move'
                    self._orig_geom = dict(hit[1])
                    if hit[1].get('type') == 'polygon':
                        self._orig_geom['points'] = [tuple(p) for p in hit[1]['points']]
                    gid = hit[1].get('link_group') if hit[0] == 'layer' else None
                    self._linked_move_orig = {
                        id(l): (l['x'], l['y']) for l in self.layers
                        if gid and l is not hit[1] and l.get('link_group') == gid
                    }
                else:
                    self.selected = None
                    self._mode = None
        elif self.tool == 'crop':
            handle_id = self._point_in_crop_handle(self.pending_crop, ix, iy) \
                if self.pending_crop else None
            if handle_id:
                self._mode = 'crop-resize'
                self._active_handle = handle_id
                self._orig_geom = dict(self.pending_crop)
            elif self.pending_crop and self._point_in_crop_body(self.pending_crop, ix, iy):
                self._mode = 'crop-move'
                self._orig_geom = dict(self.pending_crop)
            else:
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
                self.app._show_hint(tt('hint_aspect_ratio_locked'), seconds=10)
            else:
                self.app._show_hint(tt('hint_keep_aspect_ratio'), seconds=10)
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
        elif self._mode == 'crop-move':
            dx, dy = offset_x / self.zoom, offset_y / self.zoom
            orig = self._orig_geom
            new_x = max(0.0, min(orig['x'] + dx, self.width - orig['w']))
            new_y = max(0.0, min(orig['y'] + dy, self.height - orig['h']))
            self.pending_crop['x'] = new_x
            self.pending_crop['y'] = new_y
        elif self._mode == 'crop-resize':
            orig = self._orig_geom
            cx = max(0.0, min(ix2, self.width))
            cy = max(0.0, min(iy2, self.height))
            x0, y0 = orig['x'], orig['y']
            x1, y1 = orig['x'] + orig['w'], orig['y'] + orig['h']
            if self._active_handle in ('tl', 'bl'):
                x0 = cx
            if self._active_handle in ('tr', 'br'):
                x1 = cx
            if self._active_handle in ('tl', 'tr'):
                y0 = cy
            if self._active_handle in ('bl', 'br'):
                y1 = cy
            self.pending_crop = {'x': min(x0, x1), 'y': min(y0, y1),
                                  'w': abs(x1 - x0), 'h': abs(y1 - y0)}
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
            for l in self.layers:
                start = self._linked_move_orig.get(id(l))
                if start is not None:
                    l['x'] = start[0] + dx
                    l['y'] = start[1] + dy
        elif self._mode == 'resize-layer':
            _, obj = self.selected
            orig = self._orig_geom
            constrain = self._resize_constrain_active(gesture)
            if self._active_handle == 'tl':
                # Anchor: the bottom-right corner stays put; the point
                # under the cursor becomes the new top-left corner.
                anchor_x, anchor_y = orig['x'] + orig['w'], orig['y'] + orig['h']
                raw_w = anchor_x - ix2
                raw_h = anchor_y - iy2
                new_w = max(15, raw_w)
                new_h = max(15, raw_h)
                if constrain and orig['w'] and orig['h']:
                    ratio = orig['w'] / orig['h']
                    if abs(raw_w) >= abs(raw_h):
                        new_h = max(15, new_w / ratio)
                    else:
                        new_w = max(15, new_h * ratio)
                obj['x'] = anchor_x - new_w
                obj['y'] = anchor_y - new_h
                obj['w'], obj['h'] = new_w, new_h
            else:
                dx, dy = offset_x / self.zoom, offset_y / self.zoom
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
                self.app.set_active_tool('select')
            else:
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
                self.app.set_active_tool('select')
            else:
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
        Used both for mouse dragging and for the arrow-key nudging below.
        If the selected object is a layer with linked siblings, they all
        move together by the same amount."""
        if not self.selected:
            return False
        kind, obj = self.selected
        if kind == 'layer':
            obj['x'] += dx
            obj['y'] += dy
            gid = obj.get('link_group')
            if gid:
                for l in self.layers:
                    if l is not obj and l.get('link_group') == gid:
                        l['x'] += dx
                        l['y'] += dy
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
        self.app.set_status(tt('status_cropped').format(w=w, h=h))
        self.app.set_active_tool('select')

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
        self._flatten_and_transform(t, self.width, self.height, tt('status_flip_h'))

    def flip_vertical(self):
        def t(cr):
            cr.translate(0, self.height)
            cr.scale(1, -1)
        self._flatten_and_transform(t, self.width, self.height, tt('status_flip_v'))

    def rotate90(self):
        old_h = self.height

        def t(cr):
            cr.translate(old_h, 0)
            cr.rotate(math.pi / 2)
        self._flatten_and_transform(t, self.height, self.width, tt('status_rotate90'))

    _ANCHORS = {
        'top-left': (0.0, 0.0), 'top-center': (0.5, 0.0), 'top-right': (1.0, 0.0),
        'middle-left': (0.0, 0.5), 'center': (0.5, 0.5), 'middle-right': (1.0, 0.5),
        'bottom-left': (0.0, 1.0), 'bottom-center': (0.5, 1.0), 'bottom-right': (1.0, 1.0),
    }

    def resize_canvas(self, new_w, new_h, anchor='top-left', record_undo=True):
        """Change the canvas size WITHOUT resampling the base image: this
        adds or removes workspace around it, positioned according to the
        chosen anchor. The image, layers and annotations keep their size
        and shift together.

        record_undo=False lets a caller that already pushed its own undo
        snapshot (e.g. _add_layer_from_pixbuf auto-growing the canvas for
        a large incoming image) fold the resize into that same atomic
        undo step, instead of creating a separate, redundant one."""
        new_w = max(1, int(new_w))
        new_h = max(1, int(new_h))
        if new_w == self.width and new_h == self.height:
            return
        fx, fy = self._ANCHORS.get(anchor, (0.0, 0.0))
        dx = round((new_w - self.width) * fx)
        dy = round((new_h - self.height) * fy)

        if record_undo:
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
        self.app.set_status(tt('status_canvas_resized').format(w=new_w, h=new_h))

    def apply_effect(self, kind, rect):
        x, y = max(0, int(rect['x'])), max(0, int(rect['y']))
        w = min(int(rect['w']), self.width - x)
        h = min(int(rect['h']), self.height - y)
        if w < 2 or h < 2:
            return
        self.push_undo()

        # Non-destructive AND dynamic: the blur/pixelate becomes its own
        # "effect layer" sitting on top, storing only its rect and
        # intensity — never baked pixels. Its result is recomputed live
        # from whatever is currently beneath it every time the canvas is
        # drawn or exported (see _paint_effect_layer), so moving/editing a
        # layer underneath, or changing the intensity, updates it
        # instantly. Removing this layer (Select + Delete, or its trash
        # icon in the panel) reveals the original pixels again — no
        # separate "undo" needed for that.
        attached = [
            l['id'] for l in self.layers
            if not l.get('effect_type') and l.get('visible', True)
            and self._rects_intersect(x, y, w, h, l['x'], l['y'], l['w'], l['h'])
        ]
        level = self.pixelate_level if kind == 'pixelate' else self.blur_level
        effect = {
            'id': self.next_id(),
            'x': float(x), 'y': float(y), 'w': float(w), 'h': float(h),
            'level': level, 'opacity': 1.0, 'visible': True,
            'name': tt('effect_blur_name') if kind == 'blur' else tt('effect_pixelate_name'),
            'effect_type': kind, 'attached_layers': attached, 'hidden_by_source': False,
            'border_color': self.border_color, 'border_width': self.border_width,
        }
        self.layers.append(effect)
        self.selected = ('layer', effect)
        self.queue_draw()
        label = tt('effect_blurred_participle') if kind == 'blur' else tt('effect_pixelated_participle')
        if attached:
            self.app.set_status(
                tt('status_effect_attached').format(effect=label, n=len(attached)))
        else:
            self.app.set_status(tt('status_effect_standalone').format(effect=label))

    def finish_polygon(self):
        """Auto-connect the last point back to the first one (Enter) and
        turn the placed points into a solid polygon, filled with the
        current fill color."""
        pts = self.polygon_points
        if not pts or len(pts) < 3:
            self.app.set_status(tt('status_polygon_min_points'))
            return
        self.push_undo()
        ann = {'id': self.next_id(), 'type': 'polygon',
               'points': [list(p) for p in pts],
               'color': self.color, 'width': self.stroke_width,
               'fill': self.fill_color}
        self.annotations.append(ann)
        self.selected = ('annotation', ann)
        self.polygon_points = None
        self.app.set_status(tt('status_polygon_created'))
        self.app.set_active_tool('select')

    # ---- layers ----------------------------------------------------

    def add_layer_from_path(self, path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        except GLib.Error as e:
            self.app.set_status(tt('status_open_image_failed').format(error=e.message))
            return
        self._add_layer_from_pixbuf(pixbuf, os.path.basename(path))

    def add_layers_from_paths(self, paths):
        """Add several images at once as stacked layers — used when
        pasting files copied from a file manager (Nautilus & co). A
        single push_undo covers the whole batch, so Ctrl+Z undoes all of
        them together instead of one at a time."""
        if not paths:
            return
        self.push_undo()
        added = 0
        # Judge "doesn't fit" against the canvas size *before* the batch
        # started, for every image — otherwise only the first oversized
        # one would grow the canvas and come in full-size; later ones,
        # now technically fitting the already-grown canvas, would get
        # needlessly shrunk back down to the 60% overlay size instead.
        base_w, base_h = self.width, self.height
        for i, path in enumerate(paths):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            except GLib.Error:
                continue
            self._add_layer_from_pixbuf(
                pixbuf, os.path.basename(path), record_undo=False, offset=i * 24,
                fit_w=base_w, fit_h=base_h)
            added += 1
        self.app.set_active_tool('select')
        self.queue_draw()
        if added:
            self.app.set_status(tt('status_layers_added').format(n=added))
        else:
            self.app.set_status(tt('status_clipboard_open_failed'))

    def _add_layer_from_pixbuf(self, pixbuf, name, record_undo=True, offset=0,
                                fit_w=None, fit_h=None):
        if record_undo:
            self.push_undo()
        surf = surface_from_pixbuf(pixbuf)
        w, h = pixbuf.get_width(), pixbuf.get_height()
        # fit_w/fit_h let a caller adding several images in one batch pass
        # a fixed baseline to compare each one against (see
        # add_layers_from_paths) instead of the running, possibly
        # already-grown canvas size.
        ref_w = self.width if fit_w is None else fit_w
        ref_h = self.height if fit_h is None else fit_h
        grew = w > ref_w or h > ref_h
        if grew:
            # Doesn't fit at full size: grow the workspace to contain it.
            # The canvas expands evenly around the existing content
            # (anchor='center') — record_undo=False folds the resize
            # into this same atomic undo step (see resize_canvas's
            # docstring).
            new_w, new_h = max(self.width, w), max(self.height, h)
            self.resize_canvas(new_w, new_h, anchor='center', record_undo=False)
        # Always inserted at its true native size (never shrunk down),
        # centered on the canvas.
        dw, dh = float(w), float(h)
        layer = {
            'id': self.next_id(), 'surface': surf, 'orig_w': w, 'orig_h': h,
            'x': (self.width - dw) / 2 + offset, 'y': (self.height - dh) / 2 + offset,
            'w': dw, 'h': dh, 'opacity': 1.0, 'name': name, 'visible': True,
            'border_color': self.border_color, 'border_width': self.border_width,
        }
        self.layers.append(layer)
        self.selected = ('layer', layer)
        if record_undo:
            self.app.set_active_tool('select')
            self.queue_draw()
            if grew:
                self.app.set_status(
                    tt('status_layer_added_grown').format(name=name, w=int(new_w), h=int(new_h)))
            else:
                self.app.set_status(tt('status_layer_added').format(name=name))
        return layer

    def paste_as_layer(self):
        """Paste from the clipboard as a new layer. Checks first whether
        the clipboard holds files copied from a file manager (Nautilus &
        co) — if so, adds them as image layer(s), asking which ones if
        several were copied — and only falls back to pasting raw pixel
        data (a screenshot, a copied region...) when it doesn't.

        Deliberately uses read_async() with the raw mime types rather
        than read_text_async(): GTK only knows how to convert a handful
        of standard text mime types (text/plain and friends) into a
        string, and neither `x-special/gnome-copied-files` (Nautilus)
        nor `text/uri-list` (most other file managers) is one of them —
        read_text_async() would just fail on them even though the data
        is plain UTF-8 text underneath."""
        clipboard = Gdk.Display.get_default().get_clipboard()
        formats = clipboard.get_formats()
        file_mime_types = [m for m in ('x-special/gnome-copied-files', 'text/uri-list')
                            if formats.contain_mime_type(m)]
        if file_mime_types:
            clipboard.read_async(file_mime_types, GLib.PRIORITY_DEFAULT, None,
                                  self._on_paste_clipboard_stream)
        else:
            clipboard.read_texture_async(None, self._on_paste_texture)

    def _on_paste_clipboard_stream(self, clipboard, result):
        try:
            stream, _mime_type = clipboard.read_finish(result)
            text = read_stream_bytes(stream).decode('utf-8', errors='replace') if stream else None
        except GLib.Error:
            text = None
        paths = parse_clipboard_file_uris(text)
        if not paths:
            # Not actually usable file URIs (or none were images) — fall
            # back to treating the clipboard as raw pixel data.
            clipboard.read_texture_async(None, self._on_paste_texture)
            return
        if len(paths) == 1:
            self.add_layers_from_paths(paths)
        else:
            self.app.prompt_image_selection(paths, self.add_layers_from_paths)

    def _on_paste_texture(self, clipboard, result):
        try:
            texture = clipboard.read_texture_finish(result)
        except GLib.Error:
            texture = None
        if texture is None:
            self.app.set_status(tt('status_clipboard_empty'))
            return
        try:
            png_bytes = texture.save_to_png_bytes()
            loader = GdkPixbuf.PixbufLoader()
            loader.write(png_bytes.get_data())
            loader.close()
            pixbuf = loader.get_pixbuf()
        except Exception:
            self.app.set_status(tt('status_clipboard_paste_failed'))
            return
        self._add_layer_from_pixbuf(pixbuf, tt('clipboard_layer_name'))

    def copy_to_clipboard(self):
        composite = self.render_composite()
        tmp = GLib.build_filenamev([GLib.get_tmp_dir(), f"ie-clip-{next(_ID_GEN)}.png"])
        composite.write_to_png(tmp)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(tmp)
        os.remove(tmp)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        Gdk.Display.get_default().get_clipboard().set_texture(texture)
        self.app.set_status(tt('status_image_copied'))

    def copy_layer_to_clipboard(self, layer):
        """Copy just this one layer's own image to the clipboard (as
        opposed to copy_to_clipboard(), which flattens the whole canvas).
        Effect layers (blur/pixelate) have no image of their own to
        copy — nothing to do there."""
        surf = layer.get('surface')
        if surf is None:
            self.app.set_status(tt('status_layer_copy_unsupported'))
            return
        tmp = GLib.build_filenamev([GLib.get_tmp_dir(), f"ie-clip-{next(_ID_GEN)}.png"])
        surf.write_to_png(tmp)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(tmp)
        os.remove(tmp)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        Gdk.Display.get_default().get_clipboard().set_texture(texture)
        self.app.set_status(tt('status_image_copied'))

    def duplicate_layer(self, layer):
        """Add a copy of this layer, slightly offset, and select it."""
        self.push_undo()
        dup = dict(layer)
        dup['id'] = self.next_id()
        dup['x'] = layer['x'] + 24
        dup['y'] = layer['y'] + 24
        # Don't silently pull the duplicate into the original's link
        # group, or share a mutable attached_layers list with it.
        dup['link_group'] = None
        if 'attached_layers' in dup:
            dup['attached_layers'] = list(dup['attached_layers'])
        self.layers.append(dup)
        self.selected = ('layer', dup)
        self.app.set_active_tool('select')
        self.app.set_status(
            tt('status_layer_duplicated').format(name=dup.get('name') or tt('default_layer_name')))

    def show_layer_context_menu(self, layer, sx, sy):
        """Small on-canvas menu opened by right-clicking a layer: copy
        just that layer to the clipboard, paste the clipboard as a new
        layer, or duplicate this one."""
        popover = Gtk.Popover()
        popover.set_parent(self)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(sx), int(sy), 1, 1
        popover.set_pointing_to(rect)
        popover.connect('closed', lambda p: p.unparent())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(4)

        def add_item(label_text, callback):
            btn = Gtk.Button(label=label_text)
            btn.add_css_class('flat')
            child = btn.get_child()
            if isinstance(child, Gtk.Label):
                child.set_xalign(0)

            def on_clicked(_b):
                popover.popdown()
                callback()
            btn.connect('clicked', on_clicked)
            box.append(btn)

        add_item(tt('context_copy'), lambda: self.copy_layer_to_clipboard(layer))
        add_item(tt('context_paste'), lambda: self.paste_as_layer())
        add_item(tt('context_duplicate'), lambda: self.duplicate_layer(layer))

        popover.set_child(box)
        popover.popup()

    # ---- text ----------------------------------------------------

    def add_text(self, x, y, text):
        if not text:
            return
        self.push_undo()
        ann = {'id': self.next_id(), 'type': 'text', 'x': x, 'y': y, 'text': text,
               'font_size': self.font_size, 'color': self.color, 'width': 1.0,
               'fill': self.fill_color if self.fill_enabled else None,
               'border_color': self.border_color, 'border_width': self.border_width}
        self.annotations.append(ann)
        self.selected = ('annotation', ann)
        self.app.set_active_tool('select')

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
        if d.get('border_color') is not None:
            d['border_color'] = list(d['border_color'])
        return d

    @staticmethod
    def _ann_from_json(d):
        d = dict(d)
        if d.get('color') is not None:
            d['color'] = tuple(d['color'])
        if d.get('fill') is not None:
            d['fill'] = tuple(d['fill'])
        if d.get('border_color') is not None:
            d['border_color'] = tuple(d['border_color'])
        # Border thickness is now the only signal (0 = none). Text
        # annotations saved by an older version of the app had a separate
        # on/off flag — honor it if it was explicitly turned off.
        if d.get('type') == 'text' and 'border' in d and not d['border']:
            d['border_width'] = 0
        d.pop('border', None)
        return d

    def load_autosave_dict(self, data):
        self.surface = self._b64_to_surface(data['base_png_b64']) if data.get('base_png_b64') else None
        self.width = data.get('width', 0)
        self.height = data.get('height', 0)
        self.img_rect = dict(data['img_rect']) if data.get('img_rect') else \
            {'x': 0.0, 'y': 0.0, 'w': float(self.width), 'h': float(self.height)}
        self.layers = []
        # Effect layers reference other layers by id (attached_layers), so
        # ids need remapping to the freshly-assigned ones as we rebuild —
        # a plain two-pass: create everything first, then translate.
        id_map = {}
        for l in data.get('layers', []):
            new_id = self.next_id()
            if l.get('id') is not None:
                id_map[l['id']] = new_id
            layer = {
                'id': new_id,
                'x': l['x'], 'y': l['y'], 'w': l['w'], 'h': l['h'],
                'opacity': l.get('opacity', 1.0), 'name': l.get('name', ''),
                'visible': l.get('visible', True),
                'border_color': tuple(l['border_color']) if l.get('border_color') is not None else (0.0, 0.0, 0.0, 1.0),
                # Border thickness is now the only signal (0 = none). Files
                # saved by an older version of the app had a separate on/off
                # flag — honor it if it was explicitly turned off.
                'border_width': l.get('border_width', 0) if l.get('border', True) else 0,
            }
            if l.get('effect_type'):
                # Blur/pixelate areas are dynamic: only geometry + intensity
                # are kept, the result is recomputed from what's beneath.
                layer['effect_type'] = l['effect_type']
                layer['level'] = l.get('level', 4)
                layer['attached_layers'] = list(l.get('attached_layers') or [])
                layer['hidden_by_source'] = l.get('hidden_by_source', False)
            else:
                layer['surface'] = self._b64_to_surface(l['png_b64'])
                layer['orig_w'] = l.get('orig_w', l['w'])
                layer['orig_h'] = l.get('orig_h', l['h'])
            self.layers.append(layer)
        for layer in self.layers:
            if 'attached_layers' in layer:
                layer['attached_layers'] = [id_map[i] for i in layer['attached_layers'] if i in id_map]
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


# Layers panel (right-hand hierarchy of what's stacked on the image)

def annotation_display_name(ann):
    """Short label for an annotation ('object') in the layers panel."""
    t = ann.get('type')
    if t == 'text':
        txt = (ann.get('text') or '').strip().replace('\n', ' ')
        if txt:
            if len(txt) > 20:
                txt = txt[:20] + '\u2026'
            return tt('annotation_text_with_content').format(text=txt)
        return tt('tool_text_short')
    labels = {
        'arrow': tt('arrow'), 'line': tt('line'), 'rect': tt('shape_rect_label'),
        'circle': tt('shape_circle_label'), 'polygon': tt('shape_polygon_label'),
    }
    return labels.get(t, (t or tt('default_object_name')).capitalize())


TOOL_SHORT_KEYS = {
    'select': 'tool_select_short', 'crop': 'tool_crop_short',
    'arrow': 'arrow', 'line': 'line', 'rect': 'shape_rect_label',
    'circle': 'shape_circle_label', 'polygon': 'shape_polygon_label',
    'text': 'tool_text_short', 'blur': 'effect_blur_name', 'pixelate': 'effect_pixelate_name',
}


def tool_short_name(tool):
    """Short, localized name for a tool key, used in the status bar."""
    key = TOOL_SHORT_KEYS.get(tool)
    return tt(key) if key else (tool or "")


class LayersPanel(Gtk.Box):
    """Right-hand hierarchy of everything stacked on the active image:
    the base image, image layers (including ones pasted from a file
    manager), and drawn objects (arrows, shapes, text...). Grouped into
    three simple sections, topmost-first within each. Purely a view onto
    `canvas.layers` / `canvas.annotations`: call refresh() whenever
    either list or the selection may have changed."""

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.app = app
        self.app._ensure_icon_css()
        self._canvas = None
        self._syncing = False
        self._refresh_composite = None  # per-refresh() cache, see _effect_layer_thumb
        self._link_pending = None       # layer armed for linking, waiting for a 2nd click
        self.set_size_request(190, -1)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        title = Gtk.Label(label=tt('layers_panel_title'), xalign=0)
        title.add_css_class('heading')
        self.append(title)

        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.add_css_class('boxed-list')
        self.listbox.connect('row-selected', self._on_row_selected)
        scroller.set_child(self.listbox)
        self.append(scroller)

        self.empty_label = Gtk.Label(
            label=tt('layers_empty'),
            justify=Gtk.Justification.CENTER, wrap=True)
        self.empty_label.add_css_class('dim-label')
        self.empty_label.set_margin_top(12)
        self.append(self.empty_label)

    def refresh(self, canvas):
        self._canvas = canvas
        self._syncing = True
        self._refresh_composite = None  # invalidate: rebuilt lazily, once, if needed below
        try:
            child = self.listbox.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                self.listbox.remove(child)
                child = nxt

            # Topmost-drawn-first within each section, matching the
            # canvas's own paint order (base image, then layers, then
            # annotations on top).
            annotations = list(reversed(canvas.annotations)) if canvas else []
            layers = list(reversed(canvas.layers)) if canvas else []
            has_base_image = bool(canvas and canvas.surface)

            is_empty = not annotations and not layers and not has_base_image
            self.empty_label.set_visible(is_empty)
            self.listbox.set_visible(not is_empty)

            selected_row = None

            if annotations:
                self._append_section_header(tt('layers_section_objects'))
                for ann in annotations:
                    row = self._build_annotation_row(ann)
                    self.listbox.append(row)
                    if canvas and canvas.selected == ('annotation', ann):
                        selected_row = row

            if layers:
                self._append_section_header(tt('layers_section_layers'))
                for i, layer in enumerate(layers):
                    row = self._build_layer_row(layer, is_top=(i == 0), is_bottom=(i == len(layers) - 1))
                    self.listbox.append(row)
                    if canvas and canvas.selected == ('layer', layer):
                        selected_row = row

            if has_base_image:
                self._append_section_header(tt('layers_section_image'))
                self.listbox.append(self._build_base_image_row(canvas))

            self.listbox.select_row(selected_row)
        finally:
            self._syncing = False

    def _append_section_header(self, text):
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class('dim-label')
        label.add_css_class('caption-heading')
        label.set_margin_top(4)
        label.set_margin_start(2)
        row.set_child(label)
        self.listbox.append(row)

    def _build_layer_row(self, layer, is_top=False, is_bottom=False):
        row = Gtk.ListBoxRow()
        row._ref = ('layer', layer)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_top(3)
        box.set_margin_bottom(3)
        box.set_margin_start(4)
        box.set_margin_end(4)

        thumb_pb = self._layer_thumb(layer)
        if thumb_pb is not None:
            picture = Gtk.Picture.new_for_pixbuf(thumb_pb)
            picture.set_size_request(28, 28)
            box.append(picture)

        label = Gtk.Label(label=layer.get('name') or tt('default_layer_name'), xalign=0, hexpand=True)
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        box.append(label)

        link_btn = Gtk.ToggleButton()
        link_btn.set_icon_name('insert-link-symbolic')
        link_btn.add_css_class('flat')
        gid = layer.get('link_group')
        if gid:
            link_btn.set_active(True)
            link_btn.add_css_class(link_group_css_class(gid))
            link_btn.set_tooltip_text(tt('layer_unlink_tooltip'))
        elif layer is self._link_pending:
            link_btn.set_active(True)
            link_btn.add_css_class('ie-link-armed')
            link_btn.set_tooltip_text(tt('layer_link_cancel_tooltip'))
        else:
            link_btn.set_active(False)
            link_btn.set_tooltip_text(tt('layer_link_tooltip'))
        link_btn.connect('toggled', self._on_link_toggled, layer)
        box.append(link_btn)

        up_btn = Gtk.Button()
        up_btn.set_icon_name('go-up-symbolic')
        up_btn.add_css_class('flat')
        up_btn.set_tooltip_text(tt('layer_bring_forward'))
        up_btn.set_sensitive(not is_top)
        up_btn.connect('clicked', self._on_move_layer, layer, 1)
        box.append(up_btn)

        down_btn = Gtk.Button()
        down_btn.set_icon_name('go-down-symbolic')
        down_btn.add_css_class('flat')
        down_btn.set_tooltip_text(tt('layer_send_backward'))
        down_btn.set_sensitive(not is_bottom)
        down_btn.connect('clicked', self._on_move_layer, layer, -1)
        box.append(down_btn)

        vis_btn = Gtk.ToggleButton()
        vis_btn.set_icon_name(
            'view-reveal-symbolic' if layer.get('visible', True) else 'view-conceal-symbolic')
        vis_btn.set_active(layer.get('visible', True))
        vis_btn.add_css_class('flat')
        vis_btn.set_tooltip_text(tt('layer_toggle_visible'))
        vis_btn.connect('toggled', self._on_toggle_visible, layer)
        box.append(vis_btn)

        remove_btn = Gtk.Button()
        remove_btn.set_icon_name('user-trash-symbolic')
        remove_btn.add_css_class('flat')
        remove_btn.set_tooltip_text(tt('layer_remove'))
        remove_btn.connect('clicked', self._on_remove_item, row._ref)
        box.append(remove_btn)

        row.set_child(box)
        return row

    def _layer_thumb(self, layer):
        """Cached per-layer thumbnail, keyed on the layer's own surface
        object — regenerated only when that layer's pixels actually
        change, not every time refresh() runs for an unrelated edit."""
        if layer.get('effect_type'):
            return self._effect_layer_thumb(layer)
        key = id(layer['surface'])
        if layer.get('_thumb_key') == key and layer.get('_thumb_pixbuf') is not None:
            return layer['_thumb_pixbuf']
        pb = surface_to_thumb_pixbuf(layer['surface'], 28)
        layer['_thumb_key'] = key
        layer['_thumb_pixbuf'] = pb
        return pb

    def _effect_layer_thumb(self, layer):
        """Blur/pixelate areas no longer keep baked pixels, so their panel
        thumbnail is cropped live from the current composite (which
        recomputes the effect from whatever is currently beneath it)."""
        canvas = self._canvas
        if not canvas:
            return None
        composite = self._refresh_composite
        if composite is None:
            composite = canvas.render_composite()
            self._refresh_composite = composite
        x, y = max(0, int(layer['x'])), max(0, int(layer['y']))
        w = min(int(layer['w']), canvas.width - x)
        h = min(int(layer['h']), canvas.height - y)
        if w < 1 or h < 1:
            return None
        region = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        rc = cairo.Context(region)
        rc.set_source_surface(composite, -x, -y)
        rc.paint()
        return surface_to_thumb_pixbuf(region, 28)

    def _build_annotation_row(self, ann):
        row = Gtk.ListBoxRow()
        row._ref = ('annotation', ann)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_top(3)
        box.set_margin_bottom(3)
        box.set_margin_start(4)
        box.set_margin_end(4)

        icon = Gtk.Image.new_from_icon_name(
            'insert-text-symbolic' if ann.get('type') == 'text' else 'applications-graphics-symbolic')
        icon.set_pixel_size(16)
        box.append(icon)

        label = Gtk.Label(label=annotation_display_name(ann), xalign=0, hexpand=True)
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        box.append(label)

        remove_btn = Gtk.Button()
        remove_btn.set_icon_name('user-trash-symbolic')
        remove_btn.add_css_class('flat')
        remove_btn.set_tooltip_text(tt('object_remove'))
        remove_btn.connect('clicked', self._on_remove_item, row._ref)
        box.append(remove_btn)

        row.set_child(box)
        return row

    def _build_base_image_row(self, canvas):
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        row._ref = ('base', None)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_top(3)
        box.set_margin_bottom(3)
        box.set_margin_start(4)
        box.set_margin_end(4)

        thumb_pb = canvas.ensure_base_thumb(28) if canvas.surface else None
        if thumb_pb is not None:
            picture = Gtk.Picture.new_for_pixbuf(thumb_pb)
            picture.set_size_request(28, 28)
            box.append(picture)

        label = Gtk.Label(label=tt('layers_base_image'), xalign=0, hexpand=True)
        label.add_css_class('dim-label')
        box.append(label)

        row.set_child(box)
        return row

    def _on_row_selected(self, listbox, row):
        if self._syncing or not self._canvas:
            return
        if row is None or not hasattr(row, '_ref'):
            return
        kind, obj = row._ref
        if kind == 'base':
            # Nothing on the base image is editable: clear the selection
            # and drop back to Select, so a previously active tool's (or
            # a previously selected object's) options don't linger.
            self._canvas.selected = None
            self.app.set_active_tool('select')
            return
        self._canvas.selected = row._ref
        self._canvas.queue_draw()
        self.app.update_options_visibility()
        self.app.sync_selection_controls()
        # Selecting via the panel shouldn't require an extra click on the
        # canvas before arrow keys / Delete / Escape start working on it.
        self._canvas.grab_focus()

    def _on_move_layer(self, btn, layer, direction):
        if self._canvas:
            self._canvas.move_layer(layer, direction)

    def _on_toggle_visible(self, btn, layer):
        if self._syncing:
            return
        layer['visible'] = btn.get_active()
        if layer.get('attached_layers') is not None:
            # The user just toggled a blur/pixelate effect's own eye icon
            # directly: that's an explicit choice, not the automatic
            # cascade below, so it should stick even if its source image
            # gets hidden/shown again later.
            layer['hidden_by_source'] = False
        btn.set_icon_name(
            'view-reveal-symbolic' if layer['visible'] else 'view-conceal-symbolic')
        if self._canvas:
            self._canvas._cascade_layer_visibility(layer)
            self._canvas.dirty = True
            self._canvas.queue_draw()
            self.app._update_tab_label(self.app._tab_by_canvas.get(self._canvas)) \
                if self.app._tab_by_canvas.get(self._canvas) else None
            # A cascade may have changed OTHER rows' visibility (an
            # attached effect following this layer) — refresh so their
            # eye icons stay in sync.
            self.refresh(self._canvas)

    def _on_link_toggled(self, btn, layer):
        if self._syncing:
            return
        canvas = self._canvas
        if not canvas:
            return
        if self._link_pending is layer:
            # Clicked the same armed layer again: cancel, no change.
            self._link_pending = None
            self.refresh(canvas)
            return
        if self._link_pending is not None:
            # Second click, on a different layer: link the two (this may
            # create a new group, join an existing one, or merge two —
            # see Canvas.link_layers).
            other = self._link_pending
            self._link_pending = None
            canvas.link_layers(other, layer)
            self.app.set_status(tt('status_layers_linked'))
            return
        if layer.get('link_group'):
            # No pending layer, and this one is already linked: unlink it.
            canvas.unlink_layer(layer)
            self.app.set_status(tt('status_layer_unlinked'))
            return
        # First click on an unlinked layer: arm it and wait for a second one.
        self._link_pending = layer
        self.app.set_status(tt('status_link_pending'))
        self.refresh(canvas)

    def _on_remove_item(self, btn, ref):
        canvas = self._canvas
        if not canvas:
            return
        kind, obj = ref
        collection = canvas.layers if kind == 'layer' else canvas.annotations
        if obj not in collection:
            return
        canvas.push_undo()
        gid = obj.get('link_group') if kind == 'layer' else None
        collection.remove(obj)
        if kind == 'layer':
            canvas._cleanup_effect_attachments(obj)
            if gid:
                canvas._dissolve_link_group_if_needed(gid)
        if canvas.selected == ref:
            canvas.selected = None
        canvas.queue_draw()
        self.app.update_status()


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
        header.pack_end(self._icon_header_button(
            "help-about-symbolic", tt('help_button_tooltip'), self.open_help_dialog))

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
        options_scroller = Gtk.ScrolledWindow(hexpand=True)
        options_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        options_scroller.set_child(self._build_options_row())
        right.append(options_scroller)

        self.notebook = Gtk.Notebook()
        self.notebook.set_hexpand(True)
        self.notebook.set_vexpand(True)
        self.notebook.set_scrollable(True)
        self.notebook.connect('switch-page', self._on_switch_page)
        new_tab_btn = Gtk.Button()
        new_tab_btn.set_icon_name('list-add-symbolic')
        new_tab_btn.add_css_class('flat')
        new_tab_btn.set_tooltip_text(tt('new_tab_tooltip'))
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

        hbox.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        self.layers_panel = LayersPanel(self)
        hbox.append(self.layers_panel)

        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._on_window_key)
        self.add_controller(keys)

        self._locked_widgets = [
            self.save_menu_btn, self.copy_btn, self.undo_btn, self.redo_btn,
            *self.tool_buttons.values(), self.shape_button, self.canvas_size_btn,
            self.flip_h_btn, self.flip_v_btn, self.rotate_btn,
            self.add_layer_btn, self.paste_layer_btn,
            self.color_btn, self.width_spin, self.fill_check, self.fill_color_btn,
            self.border_color_btn,
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
    /* Clipboard-paste selection dialog */
    .ie-paste-icon {
        background-color: rgba(53, 132, 228, 0.15);
        color: #3584e4;
        border-radius: 999px;
        padding: 10px;
    }
    .ie-thumb-frame {
        border-radius: 10px;
        padding: 4px;
        background-color: rgba(127, 127, 127, 0.08);
    }
    /* Linked-layers chain toggle: pending (armed, waiting for a second
       click on another layer) and one color per link group, matching
       the on-canvas badges (see LINK_GROUP_COLORS). */
    .ie-link-armed {
        background-color: rgba(53, 132, 228, 0.25);
        color: #3584e4;
    }
    .ie-link-0 { color: #e6522d; }
    .ie-link-1 { color: #2ea666; }
    .ie-link-2 { color: #f29c11; }
    .ie-link-3 { color: #9c59dc; }
    .ie-link-4 { color: #e652ad; }
    .ie-link-5 { color: #33ADAD; }
    .ie-link-0:checked, .ie-link-1:checked, .ie-link-2:checked,
    .ie-link-3:checked, .ie-link-4:checked, .ie-link-5:checked {
        background-color: alpha(currentColor, 0.18);
    }
    .ie-key-pill {
        background-color: alpha(currentColor, 0.12);
        border-radius: 6px;
        padding: 2px 8px;
        font-family: monospace;
        font-weight: 600;
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

    _HELP_SHORTCUTS = [
        ('key_ctrl_z', 'help_shortcut_undo'),
        ('key_ctrl_y', 'help_shortcut_redo'),
        ('key_ctrl_s', 'help_shortcut_save'),
        ('key_ctrl_o', 'help_shortcut_open'),
        ('key_delete', 'help_shortcut_delete'),
        ('key_arrows', 'help_shortcut_nudge'),
        ('key_escape', 'help_shortcut_escape'),
        ('key_enter', 'help_shortcut_enter'),
        ('key_wheel', 'help_shortcut_zoom'),
        ('key_shift_wheel', 'help_shortcut_pan'),
        ('key_right_click', 'help_shortcut_right_click_cancel'),
        ('key_double_click', 'help_shortcut_double_click_text'),
    ]
    _HELP_TIPS = [
        'help_tip_auto_select', 'help_tip_resize_handle', 'help_tip_crop_adjust',
        'help_tip_nondestructive_effects', 'help_tip_linked_layers',
        'help_tip_paste_clipboard', 'help_tip_canvas_autogrow',
        'help_tip_border_zero', 'help_tip_tabs', 'help_tip_crash_recovery',
    ]

    def open_help_dialog(self):
        self._ensure_icon_css()
        dialog = Gtk.Dialog(title=tt('help_dialog_title'), transient_for=self, modal=True)
        dialog.set_default_size(560, 640)
        dialog.add_buttons(tt('dialog_ok'), Gtk.ResponseType.OK)
        dialog.connect('response', lambda d, r: d.destroy())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)

        box.append(self._help_heading(tt('help_section_shortcuts')))
        for key_key, desc_key in self._HELP_SHORTCUTS:
            box.append(self._help_shortcut_row(tt(key_key), tt(desc_key)))

        box.append(Gtk.Separator())
        box.append(self._help_heading(tt('help_section_right_click')))
        box.append(Gtk.Label(label=tt('help_right_click_text'), wrap=True, xalign=0))

        box.append(Gtk.Separator())
        box.append(self._help_heading(tt('help_section_tips')))
        for tip_key in self._HELP_TIPS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            bullet = Gtk.Label(label="\u2022", xalign=0, yalign=0)
            bullet.add_css_class('dim-label')
            row.append(bullet)
            row.append(Gtk.Label(label=tt(tip_key), wrap=True, xalign=0, hexpand=True))
            box.append(row)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_hexpand(True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(box)
        dialog.get_content_area().append(scroller)
        dialog.present()

    @staticmethod
    def _help_heading(text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.add_css_class('heading')
        lbl.set_margin_top(4)
        return lbl

    @staticmethod
    def _help_shortcut_row(key_text, desc_text):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        pill = Gtk.Label(label=key_text)
        pill.add_css_class('ie-key-pill')
        pill.set_size_request(128, -1)
        row.append(pill)
        row.append(Gtk.Label(label=desc_text, wrap=True, xalign=0, hexpand=True))
        return row

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
        self.color_group = self._options_group(Gtk.Label(label=tt('color_label')), self.color_btn)
        row.append(self.color_group)

        self.width_spin = Gtk.SpinButton.new_with_range(0, 40, 1)
        self.width_spin.set_value(4)
        self.width_spin.set_tooltip_text(tt('width_spin_tooltip'))
        self.width_spin.connect('value-changed', self._on_width_changed)
        self.width_label = Gtk.Label(label=tt('width_label'))
        self.width_group = self._options_group(self.width_label, self.width_spin)
        row.append(self.width_group)

        self.fill_check = Gtk.CheckButton(label=tt('fill_check_label'))
        self.fill_check.set_tooltip_text(tt('fill_check_tooltip'))
        self.fill_check.connect('toggled', self._on_fill_toggled)
        self.fill_color_btn = Gtk.ColorButton()
        fill_rgba = Gdk.RGBA()
        fill_rgba.parse("rgba(255,255,255,1)")
        self.fill_color_btn.set_rgba(fill_rgba)
        self.fill_color_btn.set_tooltip_text(tt('fill_color_tooltip'))
        self.fill_color_btn.connect('color-set', self._on_fill_color_set)
        self.fill_group = self._options_group(self.fill_check, self.fill_color_btn)
        row.append(self.fill_group)

        # Border thickness is entirely driven by width_spin (0 = no border,
        # >0 = border drawn at that thickness) — no separate on/off checkbox.
        self.border_color_btn = Gtk.ColorButton()
        border_rgba = Gdk.RGBA()
        border_rgba.parse("rgba(0,0,0,1)")
        self.border_color_btn.set_rgba(border_rgba)
        self.border_color_btn.set_tooltip_text(tt('border_color_tooltip'))
        self.border_color_btn.connect('color-set', self._on_border_color_set)
        self.border_group = self._options_group(
            Gtk.Label(label=tt('border_label')), self.border_color_btn)
        row.append(self.border_group)

        self.arrow_head_combo = Gtk.DropDown.new_from_strings(self._ARROW_HEAD_LABELS)
        self.arrow_head_combo.set_selected(0)
        self.arrow_head_combo.connect('notify::selected', self._on_arrow_head_changed)
        self.arrow_head_group = self._options_group(Gtk.Label(label=tt('head_label')), self.arrow_head_combo)
        row.append(self.arrow_head_group)

        self.font_spin = Gtk.SpinButton.new_with_range(8, 120, 1)
        self.font_spin.set_value(28)
        self.font_spin.connect('value-changed', self._on_font_changed)
        self.font_group = self._options_group(Gtk.Label(label=tt('text_size_label')), self.font_spin)
        row.append(self.font_group)

        self.effect_spin = Gtk.SpinButton.new_with_range(2, 60, 1)
        self.effect_spin.set_value(4)
        self.effect_spin.set_tooltip_text(tt('intensity_tooltip'))
        self.effect_spin.connect('value-changed', self._on_effect_level_changed)
        self.effect_group = self._options_group(Gtk.Label(label=tt('intensity_label')), self.effect_spin)
        row.append(self.effect_group)

        self.opacity_spin = Gtk.SpinButton.new_with_range(0, 100, 5)
        self.opacity_spin.set_value(100)
        self.opacity_spin.connect('value-changed', self._on_opacity_changed)
        self.opacity_group = self._options_group(
            Gtk.Label(label=tt('opacity_label')), self.opacity_spin)
        row.append(self.opacity_group)

        row.append(Gtk.Separator())
        zoom_label = Gtk.Label(label=tt('zoom_label'))
        zoom_label.set_tooltip_text(tt('zoom_tooltip'))
        row.append(zoom_label)
        self.zoom_combo = Gtk.DropDown.new_from_strings(
            ["50%", "75%", "100%", "150%", "200%", "300%", tt('zoom_fit_label')])
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

    @staticmethod
    def _is_borderable(sel):
        """A border applies to image layers (regular or blur/pixelate
        effect layers) and to text annotations."""
        if not sel:
            return False
        kind, obj = sel
        return kind == 'layer' or (kind == 'annotation' and obj.get('type') == 'text')

    def _on_border_color_set(self, btn):
        rgba = btn.get_rgba()
        color = (rgba.red, rgba.green, rgba.blue, rgba.alpha)
        self.canvas.border_color = color
        sel = self.canvas.selected
        if self._is_borderable(sel):
            sel[1]['border_color'] = color
            self.canvas.queue_draw()

    _WIDTH_TYPES = ('arrow', 'line', 'rect', 'circle', 'polygon')

    def _on_width_changed(self, spin):
        """Width_spin is shared: for shapes (arrow/line/rect/circle/polygon)
        it's the stroke width; for images/text it's the border thickness,
        where 0 simply means no border is drawn — there's no separate
        on/off flag. What the selected object actually is takes priority
        over the active tool."""
        value = spin.get_value()
        sel = self.canvas.selected
        if self._is_borderable(sel):
            self.canvas.border_width = value
            sel[1]['border_width'] = value
            self.canvas.queue_draw()
            return
        if sel and sel[0] == 'annotation' and sel[1]['type'] in self._WIDTH_TYPES:
            self.canvas.stroke_width = value
            sel[1]['width'] = value
            self.canvas.queue_draw()
            return
        # Nothing selected: remember this value against whichever kind of
        # object the active tool will create next.
        if self.canvas.tool in self._WIDTH_TYPES:
            self.canvas.stroke_width = value
        else:
            self.canvas.border_width = value

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
        sel = self.canvas.selected
        if sel and sel[0] == 'layer' and sel[1].get('effect_type'):
            # A blur/pixelate area is selected: adjust its own intensity
            # directly — the effect is recomputed live, no re-drawing needed.
            sel[1]['level'] = value
            self.canvas.dirty = True
            self.canvas.queue_draw()
            return
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
            self._show_hint(tt('crop_hint'))
        elif tool == 'polygon':
            self._show_hint(tt('polygon_hint'), seconds=6)
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

        title = Gtk.Label(label=tt('empty_state_title'))
        title.add_css_class("title-2")
        box.append(title)

        subtitle = Gtk.Label(label=tt('empty_state_subtitle'))
        subtitle.add_css_class("dim-label")
        box.append(subtitle)

        open_btn = Gtk.Button(label=tt('empty_state_button'))
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
            self.layers_panel.refresh(None)
            return
        tab = self._tab_by_canvas.get(self.canvas)
        if tab:
            self._update_tab_label(tab)
        self._update_window_title()
        if self.canvas.width:
            zoom_pct = int(round(self.canvas.zoom * 100))
            self.status_label.set_text(tt('status_bar_template').format(
                w=self.canvas.width, h=self.canvas.height, zoom=zoom_pct,
                tool=tool_short_name(self.canvas.tool)))
        self.update_undo_redo()
        self.update_options_visibility()
        self.sync_selection_controls()
        self.layers_panel.refresh(self.canvas)

    def update_options_visibility(self):
        """Only show the color / fill / border / width / text / arrowhead /
        opacity controls when they're relevant to the active tool or to
        whatever is currently selected."""
        if not self.canvas:
            for grp in (self.color_group, self.width_group, self.fill_group,
                        self.arrow_head_group, self.font_group, self.opacity_group,
                        self.effect_group, self.border_group):
                grp.set_visible(False)
            return

        tool = self.canvas.tool
        sel = self.canvas.selected
        sel_type = sel[1]['type'] if sel and sel[0] == 'annotation' else None
        sel_is_layer = bool(sel and sel[0] == 'layer')

        color_types = ('arrow', 'line', 'rect', 'circle', 'text', 'polygon')
        width_types = ('arrow', 'line', 'rect', 'circle', 'polygon')
        fill_types = ('rect', 'circle', 'polygon', 'text')
        # A border applies to added images (any layer, including a
        # blur/pixelate effect layer) and to text — not to shapes, which
        # already have their own stroke via Width/Color.
        border_relevant = sel_is_layer or tool == 'text' or sel_type == 'text'

        self.color_group.set_visible(tool in color_types or sel_type in color_types)
        self.width_group.set_visible(tool in width_types or sel_type in width_types or border_relevant)
        self.width_label.set_text(
            tt('width_label') if (tool in width_types or sel_type in width_types) else tt('border_width_label'))
        self.fill_group.set_visible(tool in fill_types or sel_type in fill_types)
        self.border_group.set_visible(border_relevant)
        self.arrow_head_group.set_visible(tool == 'arrow' or sel_type == 'arrow')
        self.font_group.set_visible(tool == 'text' or sel_type == 'text')
        self.opacity_group.set_visible(sel_is_layer)

        sel_effect_type = sel[1].get('effect_type') if sel_is_layer else None
        self.effect_group.set_visible(tool in ('blur', 'pixelate') or sel_effect_type is not None)
        if sel_effect_type is not None:
            self.effect_spin.set_value(sel[1].get('level', 4))
        elif tool == 'pixelate':
            self.effect_spin.set_value(self.canvas.pixelate_level)
        elif tool == 'blur':
            self.effect_spin.set_value(self.canvas.blur_level)

    def sync_selection_controls(self):
        """Make the controls (color, width, fill, border, text size,
        arrowhead) reflect the currently selected object's values, so
        they can be edited live."""
        if not self.canvas:
            return
        sel = self.canvas.selected
        if not sel:
            return

        if sel[0] == 'layer':
            layer = sel[1]
            bc = layer.get('border_color')
            if bc is not None:
                r, g, b, a = bc
                rgba = Gdk.RGBA()
                rgba.red, rgba.green, rgba.blue, rgba.alpha = r, g, b, a
                self.border_color_btn.set_rgba(rgba)
            self.width_spin.set_value(layer.get('border_width', self.canvas.border_width))
            return

        if sel[0] != 'annotation':
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
            bc = ann.get('border_color')
            if bc is not None:
                r, g, b, a = bc
                rgba = Gdk.RGBA()
                rgba.red, rgba.green, rgba.blue, rgba.alpha = r, g, b, a
                self.border_color_btn.set_rgba(rgba)
            self.width_spin.set_value(ann.get('border_width', self.canvas.border_width))

        if t == 'arrow':
            style = ann.get('head_style', 'end')
            idx = self._ARROW_HEAD_VALUES.index(style) if style in self._ARROW_HEAD_VALUES else 0
            self.arrow_head_combo.set_selected(idx)

    # ---- tabs ----------------------------------------------------------------------------

    def _tab_display_name(self, tab):
        path = tab['canvas'].current_path
        return os.path.basename(path) if path else tt('untitled')

    def _update_tab_label(self, tab):
        name = self._tab_display_name(tab)
        marker = "● " if tab['canvas'].dirty else ""
        tab['label'].set_text(f"{marker}{name}")
        tab['label'].set_tooltip_text(tab['canvas'].current_path or tt('never_saved'))

    def _update_window_title(self):
        if not self.canvas:
            self.set_title("Quick Image Editor")
            return
        tab = self._tab_by_canvas.get(self.canvas)
        name = self._tab_display_name(tab) if tab else tt('untitled')
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
        close_btn.set_tooltip_text(tt('close_tab_tooltip'))
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
            text=tt('unsaved_changes_title'),
            secondary_text=tt('unsaved_changes_tab_body').format(name=name))
        dialog.add_buttons(tt('dialog_cancel'), Gtk.ResponseType.CANCEL,
                            tt('dialog_dont_save'), Gtk.ResponseType.NO,
                            tt('dialog_save'), Gtk.ResponseType.YES)
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
                self.set_status(tt('status_saved').format(path=canvas.current_path))
                callback(True)
            except Exception as e:
                self.set_status(tt('status_save_failed').format(error=e))
                callback(False)
            return

        dialog = Gtk.FileDialog()
        dialog.set_title(tt('save_as_dialog_title'))
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
            self.set_status(tt('status_saved').format(path=path))
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
            text=tt('recovery_title'),
            secondary_text=tt('recovery_body').format(n=n))
        dialog.add_buttons(tt('dialog_discard'), Gtk.ResponseType.NO,
                            tt('dialog_recover'), Gtk.ResponseType.YES)
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
                self.set_status(tt('status_recovered').format(n=recovered))
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
            text=tt('unsaved_changes_title'),
            secondary_text=tt('unsaved_changes_quit_body').format(names=names))
        dialog.add_buttons(tt('dialog_cancel'), Gtk.ResponseType.CANCEL,
                            tt('dialog_dont_save'), Gtk.ResponseType.NO,
                            tt('dialog_save_all_close'), Gtk.ResponseType.YES)
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
        dialog = Gtk.Dialog(title=tt('canvas_size_title'), transient_for=self, modal=True)
        dialog.set_default_size(380, -1)
        dialog.add_buttons(tt('dialog_cancel'), Gtk.ResponseType.CANCEL,
                            tt('dialog_ok'), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)
        box.set_spacing(10)

        info = Gtk.Label(
            label=tt('canvas_size_info'),
            wrap=True, xalign=0)
        box.append(info)

        img_rect = self.canvas.img_rect
        img_w = int(img_rect['w']) if img_rect else int(self.canvas.width)
        img_h = int(img_rect['h']) if img_rect else int(self.canvas.height)
        size_hint = tt('canvas_size_hint_template').format(w=img_w, h=img_h)
        if (img_w, img_h) != (int(self.canvas.width), int(self.canvas.height)):
            size_hint += tt('canvas_size_hint_current').format(
                w=int(self.canvas.width), h=int(self.canvas.height))

        hint_label = Gtk.Label(label=size_hint, xalign=0, wrap=True)
        hint_label.add_css_class('dim-label')
        hint_label.set_tooltip_text(tt('canvas_size_hint_tooltip'))
        box.append(hint_label)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        w_spin = Gtk.SpinButton.new_with_range(1, 20000, 10)
        w_spin.set_value(self.canvas.width)
        w_spin.set_tooltip_text(size_hint)
        h_spin = Gtk.SpinButton.new_with_range(1, 20000, 10)
        h_spin.set_value(self.canvas.height)
        h_spin.set_tooltip_text(size_hint)
        grid.attach(Gtk.Label(label=tt('canvas_width_label'), xalign=0), 0, 0, 1, 1)
        grid.attach(w_spin, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label=tt('canvas_height_label'), xalign=0), 0, 1, 1, 1)
        grid.attach(h_spin, 1, 1, 1, 1)
        box.append(grid)

        link_check = Gtk.CheckButton(label=tt('canvas_link_checkbox'))
        link_check.set_tooltip_text(tt('canvas_link_tooltip'))
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

        box.append(Gtk.Label(label=tt('canvas_position_label'), xalign=0))

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
        dialog = Gtk.Dialog(title=tt('text_dialog_edit_title') if edit else tt('text_dialog_add_title'),
                             transient_for=self, modal=True)
        dialog.set_default_size(360, -1)
        dialog.add_buttons(tt('dialog_cancel'), Gtk.ResponseType.CANCEL,
                            tt('dialog_ok'), Gtk.ResponseType.OK)
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

    def prompt_image_selection(self, file_paths, on_confirm):
        """Several images were found copied on the clipboard (from a file
        manager like Nautilus). Ask which ones to actually add, in case
        the selection there was wider than intended — all are checked by
        default. `on_confirm(list[str])` is called with the paths that
        stayed checked."""
        self._ensure_icon_css()
        dialog = Gtk.Dialog(title=tt('clipboard_dialog_title'), transient_for=self, modal=True)
        dialog.set_default_size(480, 560)

        # Built by hand rather than dialog.add_button(): GTK's own action
        # area packs its buttons tight against each other and against the
        # window edge, with no way to add breathing room around them.
        box = dialog.get_content_area()
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_spacing(14)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        icon = Gtk.Image.new_from_icon_name('edit-paste-symbolic')
        icon.set_pixel_size(28)
        icon.add_css_class('ie-paste-icon')
        icon.set_valign(Gtk.Align.CENTER)
        header.append(icon)

        header_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        title_label = Gtk.Label(label=tt('clipboard_dialog_title'), xalign=0)
        title_label.add_css_class('heading')
        header_text.append(title_label)
        n = len(file_paths)
        intro = Gtk.Label(
            label=tt('clipboard_dialog_intro').format(n=n),
            xalign=0, wrap=True)
        intro.add_css_class('dim-label')
        header_text.append(intro)
        header.append(header_text)
        box.append(header)

        select_all_check = Gtk.CheckButton(label=tt('clipboard_select_all'), active=True)
        select_all_check.set_halign(Gtk.Align.START)
        box.append(select_all_check)

        scroller = Gtk.ScrolledWindow(min_content_height=320, vexpand=True)
        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.add_css_class('boxed-list')
        scroller.set_child(list_box)
        box.append(scroller)

        checks = []
        for path in file_paths:
            row = Gtk.ListBoxRow()
            row.set_activatable(False)
            rbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            rbox.set_margin_top(8)
            rbox.set_margin_bottom(8)
            rbox.set_margin_start(10)
            rbox.set_margin_end(10)

            check = Gtk.CheckButton(active=True, valign=Gtk.Align.CENTER)
            rbox.append(check)

            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 56, 56, True)
                picture = Gtk.Picture.new_for_pixbuf(pixbuf)
                picture.set_size_request(56, 56)
                thumb_frame = Gtk.Frame()
                thumb_frame.add_css_class('ie-thumb-frame')
                thumb_frame.set_child(picture)
                rbox.append(thumb_frame)
            except GLib.Error:
                pass

            name_label = Gtk.Label(label=os.path.basename(path), xalign=0, hexpand=True,
                                    valign=Gtk.Align.CENTER)
            name_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            rbox.append(name_label)

            row.set_child(rbox)
            list_box.append(row)
            checks.append((check, path))

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                              halign=Gtk.Align.END)
        cancel_btn = Gtk.Button(label=tt('dialog_cancel'))
        add_btn = Gtk.Button(label=tt('clipboard_add'))
        add_btn.add_css_class('suggested-action')
        action_row.append(cancel_btn)
        action_row.append(add_btn)
        box.append(action_row)
        dialog.set_default_widget(add_btn)

        # Keep the "select all" checkbox and the individual rows in sync
        # both ways: toggling it sets every row, and it reflects an
        # all/none/mixed selection (shown as an inconsistent tri-state)
        # if the rows are toggled individually.
        syncing = False

        def on_master_toggled(_check):
            nonlocal syncing
            if syncing:
                return
            syncing = True
            active = select_all_check.get_active()
            for c, _path in checks:
                c.set_active(active)
            syncing = False

        def update_master_from_rows(_check):
            nonlocal syncing
            if syncing:
                return
            syncing = True
            states = [c.get_active() for c, _path in checks]
            all_checked = all(states)
            select_all_check.set_inconsistent(any(states) and not all_checked)
            select_all_check.set_active(all_checked)
            syncing = False

        select_all_check.connect('toggled', on_master_toggled)
        for check, _path in checks:
            check.connect('toggled', update_master_from_rows)

        def on_response(d, resp):
            if resp == Gtk.ResponseType.OK:
                selected = [p for check, p in checks if check.get_active()]
                d.destroy()
                if selected:
                    on_confirm(selected)
            else:
                d.destroy()

        dialog.connect('response', on_response)
        cancel_btn.connect('clicked', lambda b: dialog.response(Gtk.ResponseType.CANCEL))
        add_btn.connect('clicked', lambda b: dialog.response(Gtk.ResponseType.OK))
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
        dialog.set_title(tt('open_image_dialog_title'))
        filters = Gio.ListStore(item_type=Gtk.FileFilter)
        f = Gtk.FileFilter()
        f.set_name(tt('file_filter_images'))
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
        dialog.set_title(tt('choose_overlay_dialog_title'))
        filters = Gio.ListStore(item_type=Gtk.FileFilter)
        f = Gtk.FileFilter()
        f.set_name(tt('file_filter_images'))
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
        dialog.set_title(tt('save_as_dialog_title'))
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
                self.set_status(tt('status_saved').format(path=path))

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
            self.set_status(tt('status_open_failed').format(error=e.message))
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
