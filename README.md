# Quick Image Editor

*[Read this in English](README.en.md)*

Éditeur d'images GTK4/Python à calques multiples, conçu à l'origine comme
application compagnon de l'extension GNOME Shell « image-editor » (ouverture
directe d'une capture d'écran pour l'annoter), mais parfaitement utilisable
comme éditeur d'images autonome.

Un seul fichier (`image-editor.py`), pas de dépendance en dehors de ce qui
est déjà installé sur une distribution GNOME standard.

## Fonctionnalités

**Image et calques**
- Ouvrir une image / partir d'un canevas vierge / enregistrer / enregistrer sous
- Canevas multi-calques : chaque image ajoutée (bouton « Superposer une
  image », collage presse-papiers simple ou multiple, glisser-déposer depuis
  un gestionnaire de fichiers) devient un calque déplaçable, redimensionnable
  (poignées haut-gauche **et** bas-droite), avec opacité réglable
- Le canevas s'agrandit automatiquement si l'image ajoutée est plus grande
  que lui, pour l'accueillir à sa taille d'origine plutôt que de la réduire
- **Calques liés** : cliquer sur l'icône maillon de deux calques les lie —
  ils se déplacent ensemble (souris ou clavier) ; contour pointillé coloré
  + badge sur le canevas et icône colorée dans le panneau pour les repérer
- Recadrage (rectangle déplaçable et redimensionnable par ses 4 coins avant
  validation), retournement horizontal/vertical, rotation 90°
- Redimensionnement du canevas (avec choix d'un point d'ancrage)

**Annotations**
- Flèches, lignes, rectangles, cercles/ovales, polygones, texte
- Couleur, épaisseur de trait, remplissage
- Bordure numérique (image ou texte) : 0 = aucune, toute valeur > 0 dessine
  une bordure de cette épaisseur — pas de case à cocher séparée
- Flou et pixellisation d'une zone, **non destructifs** : la zone reste un
  calque à part entière (déplaçable, réglable en intensité), et la supprimer
  révèle l'image d'origine en dessous
- Retour automatique à l'outil Sélection une fois une forme/texte/recadrage/
  flou terminé

**Sélection et interaction**
- Panneau des calques (sections « Objets » et « Calques ») : visibilité,
  réorganisation, suppression, miniatures
- Sélectionner un calque via le panneau redonne le focus clavier au canevas
  (flèches, Suppr, Échap fonctionnent immédiatement)
- Clic droit sur un calque image : petit menu Copier / Coller / Dupliquer
- Double-clic sur un texte (outil Sélection) : modifier son contenu
- Déplacement au clavier (flèches, Maj = pas de 10 px), Suppr, Échap
- Annuler / rétablir (pile de snapshots), zoom (molette ou pavé tactile,
  Maj = défilement horizontal), ajustement automatique au redimensionnement
  de la fenêtre

**Fiabilité et confort**
- Onglets multiples, un par image ouverte, avertissement avant fermeture
  si modifications non enregistrées
- Sauvegarde automatique en arrière-plan + proposition de récupération après
  un arrêt inattendu (plantage, coupure de courant)
- Bouton d'aide (« ? ») : raccourcis clavier, fonction du clic droit,
  subtilités de l'application
- Interface entièrement traduite en 6 langues (français, anglais, espagnol,
  allemand, italien, portugais), détectée automatiquement depuis la langue
  du système (repli sur l'anglais)

## Dépendances

- Python 3
- PyGObject (`gi`) avec GTK 4, GDK, GdkPixbuf, Pango
- pycairo

Le tout est préinstallé sur une session GNOME standard (Ubuntu/Fedora/etc.).
Rien à installer via pip dans le cas normal.

## Utilisation

```bash
python3 image-editor.py [chemin_image] [--blank] [--from-screenshot]
```

- Sans argument : écran vide avec un bouton « Ouvrir une image… »
- `chemin_image` : ouvre directement ce fichier dans un nouvel onglet
- `--blank` : ouvre un canevas vierge (1200×800 par défaut)
- `--from-screenshot` : utilisé par l'extension GNOME Shell lors d'un
  lancement depuis une capture d'écran — le fichier source est supprimé une
  fois son contenu chargé en mémoire, et l'onglet reste « Sans titre » pour
  éviter d'écraser silencieusement ce fichier temporaire

L'application est mono-instance : la relancer alors qu'elle tourne déjà
ramène simplement la fenêtre existante au premier plan (les arguments
passés à ce second lancement, ex. une nouvelle image, sont quand même pris
en compte).

**Formats**
- Ouverture : PNG, JPEG, BMP, TIFF, WEBP, GIF
- Enregistrement : PNG, JPEG, BMP, TIFF (déduit de l'extension du fichier ;
  PNG par défaut si l'extension est absente ou inconnue)

## Emplacement des données

- Sauvegarde automatique / récupération après plantage :
  `~/.cache/image-editor-loko/autosave/`
- Préférences (dernier dossier d'enregistrement utilisé) :
  `~/.config/image-editor-loko/prefs.json`

## Icônes

Les icônes de la barre d'outils sont attendues dans un dossier `icons/` à
côté du script (`icons/<nom>.png`). Si une icône est absente, un caractère
de repli s'affiche à la place — l'application ne plante pas pour autant.

## Localisation

Toutes les chaînes visibles par l'utilisateur (libellés, infobulles,
dialogues, messages de statut) passent par la fonction `tt(clé)`, qui
cherche la traduction dans le dictionnaire `UI_STRINGS` (en tête de
fichier) pour la langue détectée (`UI_LANG`, déduite de la locale système
via `detect_ui_lang()`), avec repli sur l'anglais puis sur la clé brute si
rien ne correspond.

Pour ajouter ou modifier un texte : ajouter/éditer l'entrée correspondante
dans `UI_STRINGS` (une entrée par clé, une traduction par langue parmi
`fr/en/es/de/it/pt`), puis l'utiliser via `tt('ma_cle')` dans le code —
jamais de chaîne codée en dur pour un texte destiné à l'utilisateur.

## Structure du code (repères pour s'y retrouver)

- `UI_STRINGS` / `tt()` — dictionnaire de traductions et fonction de lookup
- `Canvas` — une image ouverte : ses calques, ses annotations, sa pile
  d'annulation, son niveau de zoom ; un `Canvas` par onglet
- `EditorWindow` — fenêtre principale : onglets, barre d'en-tête, barre
  d'options contextuelle à l'outil/la sélection, panneau des calques,
  dialogues (taille du canevas, texte, aide, presse-papiers…)
- `LayersPanel` — liste de droite (sections Objets/Calques) ; `refresh()`
  reconstruit les lignes à partir de l'état du `Canvas` à chaque changement
- Sauvegarde automatique : `autosave_dir()`, `list_leftover_autosaves()`,
  format JSON interne (pas destiné à être ouvert manuellement)

## Statut

Projet personnel, en évolution continue au fil des besoins — pas de
versionnage formel ni de suite de tests automatisés à ce jour.
