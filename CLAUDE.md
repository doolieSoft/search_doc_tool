# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository structure

```
desktop/          PyQt6 desktop application
web/              Django web application (version originale)
web2/             Django web application (version refactorisée — active)
  CLAUDE.md                   Règles de refactoring web2
  DOCUMENTATION_TECHNIQUE.md  Documentation technique complète
  search_tool_project/
    manage.py
    run.py                    Serveur Waitress (production)
    pytest.ini
    requirements.txt
    project/                  Django settings (DJANGO_SETTINGS_MODULE=project.settings)
    search_tool/              Django app
      services/               Logique métier en classes Python
      views/get/              Vues GET (1 fichier = 1 vue)
      views/post/             Vues POST (1 fichier = 1 vue)
      views/_helpers.py       Utilitaires partagés entre vues
      indexing_state.py       État global d'indexation + background thread
      middleware.py           StartupMiddleware (reset stale state)
      models.py               Favorite, FavoriteGroup, BrowseRoot, IndexingStatus
      tests/unit/             Tests unitaires des services
      tests/functional/       Tests fonctionnels des vues
      tests/fixtures/         Fichiers PDF/DOCX de test
```

---

## Desktop app

```bash
cd desktop
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m search_tool
```

### Architecture (desktop)

Package `desktop/search_tool/`:
- `core/config.py` — `remove_accents`, config/favorites persistence (`~/.search_tool_config.json`)
- `core/extractor.py` — `extract_text_docx` (python-docx), `extract_text_pdf` (pymupdf)
- `core/search.py` — `parse_query`, `build_pattern`, `search_file`, `collect_files`
- `core/index.py` — SQLite FTS5 index, `get_db`, `index_file`, `fts_search`
- `ui/workers.py` — `IndexWorker`, `SearchWorker` (QThread + ThreadPoolExecutor)
- `ui/app.py` — `SearchApp(QMainWindow)`

---

## Web app — web2 (version active)

```bash
cd web2
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cd search_tool_project
python manage.py migrate
python manage.py runserver         # développement
python run.py --threads 8          # production (Waitress)
```

Requires LibreOffice installed on the system (DOCX → PDF fallback conversion).
Microsoft Word strongly recommended (faster DOCX → PDF via COM automation).

### Services

`web2/search_tool_project/search_tool/services/` — classes Python, dépendances injectées via `__init__` :

| Classe | Fichier | Rôle |
|---|---|---|
| `ConfigService` | `config_service.py` | `~/.search_tool_config.json` (partagé desktop/web). `remove_accents()` accessible en statique. |
| `ExtractorService` | `extractor_service.py` | Extraction texte PDF page par page (PyMuPDF). |
| `ConverterService` | `converter_service.py` | DOCX→PDF. Détecte Word COM au démarrage. `WordConverter` context manager pour batch Word COM. Fallback LibreOffice. |
| `IndexService` | `index_service.py` | FTS5 SQLite per-folder. `STATUS_PENDING=0`, `STATUS_OK=1`, `STATUS_FAILED=-1`. `fts_search_with_content()` retourne file+page+content depuis DB (zéro I/O disque). |
| `SearchService` | `search_service.py` | Parsing requête, collecte fichiers, regex matching, extraction contexte. `search_from_db_content()` pour fichiers indexés (lecture FTS5), `search_file()` pour non-indexés (lecture PDF). |

### Views

Toutes héritent de `LoginRequiredMixin` + `View`. Vues superuser vérifient `request.user.is_superuser` → 403.

**GET** (`views/get/`) :

| Classe | URL | Rôle |
|---|---|---|
| `IndexView` | `/` | Page principale : config, favoris groupés, résumé index |
| `SearchView` | `/search/` | HTMX POST : FTS5 pré-filter → regex → `_results.html` |
| `ServePdfView` | `/serve/` | PDF avec surbrillance (split sur ` + ` pour mode AND) |
| `BrowseDirView` | `/browse/` | Navigation dossiers (drives / BrowseRoots / chemin) |
| `IndexStatusView` | `/index/status/` | JSON statut indexation (polled 500ms par JS) |
| `IndexSummaryView` | `/index/summary/` | JSON `{total, indexed, failed}` pour badge |
| `IndexUnindexedView` | `/index/unindexed/` | JSON fichiers non indexés `{name, path, status}` |
| `CleanupPreviewView` | `/admin/cleanup/preview/` | JSON dossiers orphelins `.data/folders/` (superuser) |
| `GetBrowseRootsView` | `/admin/browse-roots/` | JSON liste BrowseRoot (superuser) |

**POST** (`views/post/`) :

| Classe | URL | Rôle |
|---|---|---|
| `StartIndexView` | `/index/start/` | Lance indexation en thread daemon |
| `StopIndexView` | `/index/stop/` | Arrête indexation |
| `AddFavoriteView` | `/favorites/add/` | Ajoute favori (name = path par défaut) |
| `RemoveFavoriteView` | `/favorites/remove/` | Supprime favori |
| `RenameFavoriteView` | `/favorites/rename/` | Renomme favori (alias) |
| `MoveFavoriteView` | `/favorites/move/` | Déplace favori dans un groupe |
| `CreateGroupView` | `/favorites/groups/create/` | Crée groupe de favoris |
| `DeleteGroupView` | `/favorites/groups/delete/` | Supprime groupe |
| `RenameGroupView` | `/favorites/groups/rename/` | Renomme groupe |
| `AddBrowseRootView` | `/admin/browse-roots/add/` | Ajoute dossier autorisé (superuser) |
| `RemoveBrowseRootView` | `/admin/browse-roots/remove/` | Supprime dossier autorisé (superuser) |
| `CleanupExecuteView` | `/admin/cleanup/execute/` | Supprime dossiers orphelins (superuser) |

### Data flow — Indexation (deux phases)

```
POST /index/start/
  └─ run_indexing() [thread daemon]
       ├─ Phase 1 : DOCX → PDF
       │    Word COM disponible → WordConverter (batch, séquentiel, 1 instance Word)
       │    Sinon → LibreOffice headless (2 workers parallèles)
       │    Cache content-addressed : .data/folders/<hash>/pdf_cache/<md5(path)>.pdf
       │    Invalidé si mtime(docx) > mtime(pdf)
       │
       └─ Phase 2 : Extraction + FTS5
            ThreadPoolExecutor (8 workers max)
            ExtractorService.extract_text_pdf() → [(page, text), ...]
            remove_accents(text) → INSERT INTO fts(file, page, content)
            Échec → IndexService.STATUS_FAILED (-1) en DB

Ping thread (5s) → IndexingStatus.last_ping (stale detection > 30s)
try/finally → running=False garanti même en cas d'exception
```

### Data flow — Recherche

```
POST /search/
  ├─ parse_query() → terms[], mode (AND|OR)
  ├─ collect_files() → tous .pdf et .docx du dossier
  ├─ is_indexed() → indexed_set (mtime check)
  │
  ├─ Fichiers indexés : fts_search_with_content()
  │    FTS5 MATCH → [{file, page, content}] directement depuis DB
  │    search_from_db_content() → regex sur content (zéro I/O disque)
  │
  └─ Fichiers non indexés : ThreadPoolExecutor (8 workers)
       search_file() → ouvre PDF → extraction texte → regex
```

### Stockage

```
~/.search_tool_config.json         Dernier dossier, récursif (partagé desktop/web)

web2/search_tool_project/
  db.sqlite3                       Django DB : User, Favorite, FavoriteGroup,
                                               BrowseRoot, IndexingStatus
  .data/
    folders/
      <nom>_<md5(normpath)[:10]>/  Un répertoire par dossier favori
        index.db                   FTS5 SQLite (files + fts tables)
        pdf_cache/                 PDFs convertis depuis DOCX
        docx_copy/                 Copies locales DOCX (accès réseau)
```

### Modèles Django

- `FavoriteGroup(user, name)` — groupe de favoris par utilisateur
- `Favorite(user, path, name, group)` — favori ; `name` = alias (défaut = path)
- `BrowseRoot(label, path)` — dossiers autorisés dans le navigateur (superuser)
- `IndexingStatus(pk=1)` — singleton : `running`, `done`, `total`, `last_ping`, `error`, `started_at`, `finished_at`

### Settings importants

- `DATA_DIR` — `.data/` (index par dossier, cache PDF)
- `PDF_CACHE_DIR` / `DOCX_COPY_DIR` — cache global (legacy, remplacé par per-folder)
- `LOGIN_URL = "/login/"` / `LOGIN_REDIRECT_URL = "/"`
- `StartupMiddleware` — reset `running=True` en DB au 1er appel HTTP après redémarrage

### Tests

```bash
cd web2/search_tool_project
pytest                              # tous (132 tests)
pytest search_tool/tests/unit/      # unitaires (~1s)
pytest search_tool/tests/functional/# fonctionnels (~3min)
pytest -k test_index_service        # un fichier
```

### Key design notes

- `remove_accents()` normalise Unicode avant FTS5 et regex (insensible aux accents)
- FTS5 `tokenize='trigram'` — minimum 3 caractères par terme
- Mode AND : tous les termes sur la même page ; mode OR : par terme
- `BrowseRoot` configurés → navigateur limité à ces dossiers (protection path traversal)
- Sans `BrowseRoot` : superuser voit les lecteurs, autres utilisateurs → 503
- `fts_search_with_content()` retourne le texte stocké en DB (déjà `remove_accents`'d) → contexte sans accents pour les fichiers indexés
- `IndexService.STATUS_FAILED = -1` → fichiers non indexables (protégés, illisibles) trackés en DB, réessayés à chaque indexation
