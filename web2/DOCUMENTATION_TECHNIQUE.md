# Documentation technique — Search Doc Tool (web2)

## Vue d'ensemble

Search Doc Tool est une application Django multi-utilisateurs permettant de rechercher du texte dans des fichiers Word (.docx) et PDF stockés sur le serveur. La recherche s'appuie sur un index SQLite FTS5 pour être quasi-instantanée sur les dossiers déjà indexés.

---

## Architecture générale

```
┌─────────────────────────────────────────────────────────────┐
│                        Navigateur                           │
│   HTML/JS (HTMX pour la recherche, fetch() pour le reste)  │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP
┌────────────────────────────▼────────────────────────────────┐
│                    Waitress (WSGI)                           │
│                  1 processus, 8 threads                     │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                      Django                                 │
│                                                             │
│  Middleware                                                 │
│  ┌──────────────────┐                                       │
│  │ StartupMiddleware│ reset du flag "running" au 1er appel  │
│  └──────────────────┘                                       │
│                                                             │
│  Views (LoginRequiredMixin + View)                          │
│  ┌─────────────┐  ┌─────────────┐                          │
│  │  views/get/ │  │ views/post/ │                          │
│  └──────┬──────┘  └──────┬──────┘                          │
│         │                │                                  │
│  Services                │                                  │
│  ┌───────────────────────▼───────────────────────────┐     │
│  │ ConfigService  SearchService  IndexService        │     │
│  │ ConverterService  ExtractorService                │     │
│  └───────────────────────────────────────────────────┘     │
│                                                             │
│  État global d'indexation                                   │
│  ┌──────────────────────────────┐                          │
│  │ indexing_state.py            │                          │
│  │ _index_state (dict)          │                          │
│  │ _index_lock  (threading.Lock)│                          │
│  └──────────────────────────────┘                          │
└─────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                     Stockage                                │
│                                                             │
│  Django DB (SQLite)          Filesystem                     │
│  ┌───────────────────┐       ┌──────────────────────────┐  │
│  │ User              │       │ .data/folders/           │  │
│  │ Favorite          │       │   <nom>_<hash>/          │  │
│  │ FavoriteGroup     │       │     index.db  (FTS5)     │  │
│  │ BrowseRoot        │       │     pdf_cache/           │  │
│  │ IndexingStatus    │       │     docx_copy/           │  │
│  └───────────────────┘       └──────────────────────────┘  │
│                              ┌──────────────────────────┐  │
│                              │ ~/.search_tool_config.json│  │
│                              │ (partagé desktop/web)    │  │
│                              └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Flux de données — Indexation

L'indexation est déclenchée manuellement par l'utilisateur (bouton "Indexer"). Elle se déroule en arrière-plan dans un thread daemon.

```
Utilisateur clique "Indexer"
        │
        ▼
POST /index/start/
        │
        ├─ Vérifie : dossier valide ?
        ├─ Vérifie : job déjà en cours ? (stale detection via last_ping)
        └─ Lance run_indexing() dans un thread daemon
                │
                ├─ Démarre ping_thread (met à jour last_ping toutes les 5s en DB)
                │
                ├── PHASE 1 : Conversion DOCX → PDF ──────────────────────────┐
                │                                                              │
                │   Pour chaque .docx non indexé (ou mtime changé) :          │
                │                                                              │
                │   Word COM disponible ?                                      │
                │   ┌──YES──┐              ┌──NO──┐                           │
                │   │WordConverter         │LibreOffice headless               │
                │   │(séquentiel,          │(2 workers en parallèle,           │
                │   │1 instance Word       │1 profil LO par conversion)        │
                │   │réutilisée)           │                                   │
                │   └───────┘              └──────┘                           │
                │                                                              │
                │   Résultat : PDF mis en cache dans                           │
                │   .data/folders/<hash>/pdf_cache/<md5_path>.pdf              │
                │   (invalidé si mtime du .docx > mtime du PDF)               │
                │                                                              │
                └── PHASE 2 : Extraction texte + FTS5 ──────────────────────┐ │
                                                                             │ │
                    Pour chaque fichier prêt (PDF natif ou PDF converti) :   │ │
                    ThreadPoolExecutor (jusqu'à 8 workers)                   │ │
                                                                             │ │
                    IndexService.index_file(path, pdf_cache_dir)             │ │
                        │                                                    │ │
                        ├─ PyMuPDF : extrait le texte page par page          │ │
                        ├─ remove_accents() sur le texte                     │ │
                        ├─ DELETE FROM fts WHERE file=?  (réindexation)      │ │
                        ├─ INSERT INTO fts(file, page, content) par page     │ │
                        └─ UPDATE files SET mtime=..., indexed=1             │ │
                                                                             │ │
                    finally (garantie même en cas d'exception) :             │ │
                        ping_stop.set()                                      │ │
                        _index_state["running"] = False                      │ │
                        persist_status() → IndexingStatus (pk=1) en DB      │ │
                                                                          ───┘ │
                                                                          ─────┘
```

**Polling côté client** : le JS interroge `/index/status/` toutes les 500ms pour mettre à jour la barre de progression.

---

## Flux de données — Recherche

```
Utilisateur saisit des termes et clique "Lancer"
        │
        ▼
POST /search/  (HTMX → remplace #results dans la page)
        │
        ▼
SearchView.post()
        │
        ├─ parse_query(raw) → terms[], mode (AND|OR)
        │
        ├─ collect_files(folder, recurse) → liste tous .docx et .pdf
        │
        ├─ Séparation : fichiers indexés vs non indexés
        │   IndexService.is_indexed() vérifie mtime en DB
        │
        ├── PRÉ-FILTRE FTS5 (sur les fichiers indexés) ──────────────────────┐
        │   IndexService.fts_search(terms, mode)                              │
        │   → requête FTS5 : "term1 AND term2" ou "term1 OR term2"            │
        │   → retourne la liste des fichiers candidats (vite, ~ms)            │
        │                                                                     │
        └── RECHERCHE REGEX (sur candidats FTS5 + non indexés) ─────────────┐│
            ThreadPoolExecutor (jusqu'à 8 workers)                           ││
                                                                             ││
            SearchService.search_file(path, terms, ...)                      ││
                │                                                            ││
                ├─ get_pdf_path() : PDF natif ou PDF en cache                ││
                ├─ ExtractorService.extract_text_pdf() : texte par page      ││
                └─ Pour chaque page :                                        ││
                   Mode OR : regex par terme, 1 résultat par match           ││
                   Mode AND : tous les termes doivent matcher sur la page    ││
                              → 1 résultat avec contexte combiné             ││
                                                                          ───┘│
                                                                          ────┘
        ▼
Rendu _results.html → injecté dans la page via HTMX
        │
        └─ Chaque résultat contient :
           - nom du fichier (lien vers /serve/)
           - terme(s) trouvé(s)
           - contexte avec [terme] marqué
           - numéro de page

Clic sur un résultat → GET /serve/?path=<b64>&page=N&term=<terme>
        │
        ├─ PyMuPDF : ouvre le PDF, surligne le terme sur toutes les pages
        ├─ Mode AND : split sur " + " pour surligner chaque terme séparément
        └─ Retourne le PDF en mémoire avec annotations → ouvert dans l'onglet
```

---

## Structure des services

| Classe | Fichier | Responsabilité |
|---|---|---|
| `ConfigService` | `services/config_service.py` | Lecture/écriture `~/.search_tool_config.json`. `remove_accents()` accessible en statique. |
| `ExtractorService` | `services/extractor_service.py` | Extraction de texte depuis un PDF page par page (PyMuPDF). |
| `ConverterService` | `services/converter_service.py` | Conversion DOCX→PDF. Détecte Word COM au démarrage (cache le résultat). `WordConverter` context manager pour batch Word COM. |
| `IndexService` | `services/index_service.py` | Gestion de l'index FTS5 SQLite : création, vérification `mtime`, indexation, recherche FTS5. |
| `SearchService` | `services/search_service.py` | Parsing de requête, collecte de fichiers, regex sur texte extrait, extraction de contexte. |

**Principe d'injection** : chaque service reçoit ses dépendances via `__init__`. Les vues instancient les services avec les valeurs de `django.conf.settings` (chemins de fichiers). Pas d'accès à `settings` dans les méthodes de service.

---

## Structure des vues

```
views/
├── get/
│   ├── index.py          IndexView       — page principale
│   ├── search.py         SearchView      — résultats (HTMX, méthode POST)
│   ├── serve_pdf.py      ServePdfView    — PDF avec surlignage
│   ├── browse_dir.py     BrowseDirView   — navigateur de dossiers
│   ├── index_status.py   IndexStatusView — polling JSON état indexation
│   ├── index_summary.py  IndexSummaryView— badge indexé/total
│   ├── index_unindexed.py                — liste fichiers non indexés
│   ├── cleanup_preview.py                — (superuser) aperçu données orphelines
│   └── get_browse_roots.py               — (superuser) liste racines autorisées
└── post/
    ├── start_index.py    StartIndexView  — lance l'indexation
    ├── stop_index.py     StopIndexView   — arrête l'indexation
    ├── add_favorite.py                   — gestion favoris
    ├── remove_favorite.py
    ├── rename_favorite.py
    ├── move_favorite.py                  — déplacement entre groupes
    ├── create_group.py                   — gestion groupes de favoris
    ├── delete_group.py
    ├── rename_group.py
    ├── add_browse_root.py                — (superuser) racines navigateur
    ├── remove_browse_root.py
    └── cleanup_execute.py                — (superuser) supprime données orphelines
```

Toutes les vues héritent de `LoginRequiredMixin` et `View`. Les vues superuser vérifient `request.user.is_superuser` et retournent 403 sinon.

---

## Modèle de données (Django DB)

```
User (Django natif)
 │
 ├─< FavoriteGroup
 │    ├── user (FK)
 │    └── name
 │
 ├─< Favorite
 │    ├── user (FK)
 │    ├── path  (chemin du dossier)
 │    ├── name  (libellé affiché)
 │    └── group (FK → FavoriteGroup, nullable)
 │
IndexingStatus (singleton pk=1)
 ├── folder, running, done, total, current
 ├── newly_indexed, failed, error
 ├── started_at, finished_at
 └── last_ping  (mis à jour toutes les 5s pendant l'indexation)

BrowseRoot
 ├── label  (nom affiché)
 └── path   (chemin filesystem)
```

---

## Stockage filesystem

```
.data/
└── folders/
    └── <nom_dossier>_<md5(normpath)[:10]>/
        ├── index.db          Index FTS5 SQLite
        │   ├── TABLE files   (path, mtime, indexed)
        │   └── VTABLE fts    (file UNINDEXED, page UNINDEXED, content)
        │                     tokenize='trigram' — minimum 3 caractères
        ├── pdf_cache/        PDFs convertis depuis DOCX
        │   └── <md5(path)>.pdf
        └── docx_copy/        Copies locales des DOCX (accès réseau)
            └── <md5(path)>.docx

~/.search_tool_config.json    Dernier dossier, option récursif
                              Partagé entre app desktop et web
```

---

## Modèle de concurrence

```
Thread principal Waitress (requêtes HTTP)
        │
        ├─ Lit _index_state (sans lock, lecture seule)
        ├─ Écrit sur _index_state via _index_lock
        │
Thread background run_indexing()  (daemon)
        │
        ├─ Écrit sur _index_state via _index_lock
        └─ Lance ping_thread
                │
                └─ Thread ping_db() (daemon)
                   Met à jour IndexingStatus.last_ping en DB toutes les 5s
```

**Garanties :**
- `threading.Lock()` suffisant car Waitress = 1 processus Python
- `try/finally` dans `run_indexing` garantit `running=False` même en cas d'exception
- Si `last_ping` > 30s (thread mort sans `finally`) → `is_stale()` retourne `True` → `StartIndexView` réinitialise l'état au prochain démarrage
- `StartupMiddleware` réinitialise `running=True` en DB au premier appel HTTP après redémarrage

---

## Détection d'accents et normalisation

Toutes les chaînes passent par `remove_accents()` avant indexation FTS5 et avant comparaison regex :

```
"prénom" → "prenom"   (NFD + suppression des diacritiques Mn)
" "      → " "        (espace insécable → espace)
"'"      → "'"        (apostrophe typographique → apostrophe simple)
```

La recherche est donc insensible aux accents par défaut. L'option "sensible à la casse" (`case_sensitive`) désactive uniquement la casse, pas la normalisation des accents.

---

## Navigateur de dossiers (BrowseDirView)

```
BrowseRoot configurés ?
    │
   NON ──► Superuser ?
    │           │
    │          OUI ──► Affiche les lecteurs Windows (C:\, I:\, ...)
    │           │
    │          NON ──► 503 "Aucun dossier autorisé configuré"
    │
   OUI ──► path vide ?
                │
               OUI ──► Affiche la liste des BrowseRoot (label + chemin)
                │
               NON ──► path sous une des racines ?
                            │
                           NON ──► 403 Accès refusé
                            │
                           OUI ──► Navigation libre sous cette racine
                                   (pas de remontée au-dessus)
```

---

## Tests

```
search_tool/tests/
├── fixtures/
│   ├── sample.pdf              PDF 3 pages avec texte connu
│   ├── sample.docx             DOCX avec texte connu
│   └── sample_encrypted.docx  DOCX protégé par mot de passe
│
├── unit/                       Tests des services en isolation
│   ├── test_config_service.py  (17 tests)
│   ├── test_extractor_service.py (7 tests)
│   ├── test_converter_service.py (14 tests)
│   ├── test_index_service.py   (15 tests)
│   └── test_search_service.py  (26 tests)
│
└── functional/                 Tests des vues (Django Client)
    ├── test_index_view.py      (6 tests)
    ├── test_search_view.py     (7 tests)
    ├── test_index_api.py       (13 tests)
    ├── test_favorites_views.py (14 tests)
    └── test_browse_views.py    (13 tests)

Total : 132 tests
```

**Lancer les tests :**
```bash
cd web2/search_tool_project
python -m pytest                        # tous
python -m pytest search_tool/tests/unit/       # unitaires (rapide, ~1s)
python -m pytest search_tool/tests/functional/ # fonctionnels (~3min, recherche réelle)
python -m pytest -k test_index_service         # un seul fichier
```
