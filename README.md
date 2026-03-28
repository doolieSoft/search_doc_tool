# Search Doc Tool

*[Lire en français](README.fr.md)*

A tool for searching terms across Word (.docx) and PDF files. Available as a desktop app (PyQt6) and a web app (Django).

### Web app

| Dark mode | Light mode |
|---|---|
| ![Web dark mode](screenshots/search_doc_tool_web_dark_mode.png) | ![Web light mode](screenshots/search_doc_tool_web_light_mode.png) |

## Features

- Search through `.docx` and `.pdf` files (recursively or not)
- Advanced query syntax:
  - Space-separated words → **OR** mode (at least one term)
  - `+` operator → **AND** mode (all terms must be present)
  - `"exact phrase"` → literal phrase search
- Accent-insensitive search by default
- Options: case sensitivity, whole-word matching
- Context display around each match (highlighted term)
- Page number with direct link to the matching page in the PDF viewer
- Favorites sidebar for frequently used folders (per user, resizable)
- SQLite FTS5 index for near-instant searches on already-indexed folders
- Background indexing with progress bar and stop button
- Light/dark mode toggle

## Web app — additional features

- Multi-user: Django authentication (login required)
- Per-folder shared index: one index per folder path, shared across all users
- DOCX → PDF conversion via LibreOffice at indexing time
- PDF served inline with highlighted search terms
- Indexing status persisted in database (survives server restarts)
- Robust background indexing: stale job detection, automatic recovery after unexpected shutdown
- Favorites organized into named groups (create, rename, delete, drag & drop between groups)
- Favorite aliases: set a custom display name per folder (path shown by default)
- Non-indexable file tracking: files that fail indexing (password-protected, read errors) are flagged separately and displayed in the badge (e.g. "392 indexed • 6 non-indexable")
- Optimized search on large folders: indexed files are searched directly from the FTS5 database (no disk I/O), unindexed files fall back to PDF reading
- **Superuser tools:**
  - Configure allowed root directories for the file browser (users cannot navigate outside these paths)
  - Orphaned data cleanup: remove `.data/folders/` directories no longer referenced by any favorite

## Requirements

- Python 3.12+
- **Web app only:** LibreOffice installed (DOCX → PDF conversion at indexing time)
- **Web app — strongly recommended:** Microsoft Word installed on the server. Word COM automation is used as the primary converter (faster and higher fidelity); LibreOffice is the fallback when Word is unavailable or fails.

## Setup & Running

### Desktop (PyQt6)

```bash
cd desktop
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m search_tool
```

### Web (Django) — development

```bash
cd web2
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cd search_tool_project
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Then open `http://127.0.0.1:8000` in your browser.

### Web (Django) — production (Waitress)

```bash
cd web2/search_tool_project
python manage.py collectstatic
DJANGO_DEBUG=false python run.py --host 0.0.0.0 --port 8000
```

## Usage

1. Select a folder from the favorites sidebar or type/browse a path
2. Click **Indexer** to build the FTS5 index (first time or after adding files)
3. Enter one or more terms and click **Lancer**
4. Click a result to open the PDF at the matching page, with the term highlighted

## Index & data storage

- Per-folder data stored in `.data/folders/<folder_name>_<hash>/`:
  - `index.db` — FTS5 SQLite index (one row per page)
  - `pdf_cache/` — converted PDFs (content-addressed, invalidated on file change)
  - `docx_copy/` — local DOCX copies (network drive workaround)
- Indexing status (start time, counts, errors) persisted in the Django database

## Configuration

Last folder and recurse setting saved automatically to `~/.search_tool_config.json`. Favorites are stored per user in the Django database.
