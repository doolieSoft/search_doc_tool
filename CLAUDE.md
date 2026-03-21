# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository structure

```
desktop/          PyQt6 desktop application (python -m search_tool)
web/              Django web application
  search_tool_project/
    manage.py
    project/      Django settings (DJANGO_SETTINGS_MODULE=project.settings)
    search_tool/  Django app (views, services, templates, static)
```

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

## Web app (Django)

```bash
cd web
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cd search_tool_project
python manage.py runserver
```

Requires LibreOffice installed on the system (DOCX → PDF conversion).

### Architecture (web)

`web/search_tool_project/search_tool/services/`:
- `config.py` — same `remove_accents`, config/favorites (shared with desktop via `~/.search_tool_config.json`)
- `extractor.py` — PDF-only via pymupdf (no python-docx)
- `converter.py` — `convert_docx_to_pdf` via LibreOffice headless, content-addressed cache in `.data/pdf_cache/`
- `index.py` — FTS5 per-page schema (`file UNINDEXED, page UNINDEXED, content`), stored in `.data/search_tool_index.db`
- `search.py` — same logic as desktop but DOCX files are searched via their cached PDF

Data flow:
1. Indexing: DOCX → LibreOffice → PDF (cached) → pymupdf → FTS5 per-page rows
2. Search: FTS5 pre-filter (file candidates) → regex on PDF pages → results with page numbers
3. Display: results link to `/serve/?path=<b64>#page=N` — browser PDF viewer opens at correct page

Settings: `project/settings.py` — `DB_FILE`, `PDF_CACHE_DIR` point to `web/search_tool_project/.data/`

Background indexing runs in a daemon thread; `/index/status/` returns JSON polled by JS.

### Key design notes

- `remove_accents()` normalizes Unicode before FTS5 and regex matching (accent-insensitive)
- FTS5 uses `tokenize='trigram'` — minimum 3-character terms
- AND mode requires all terms present on the same page; OR mode reports per-term matches
- `get_pdf_path()` transparently returns original path for `.pdf` or cached PDF path for `.docx`
- Config/favorites in `~/.search_tool_config.json` is shared between desktop and web apps
