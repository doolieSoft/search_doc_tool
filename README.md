# Search Doc Tool

*[Lire en français](README.fr.md)*

A tool for searching terms across Word (.docx) and PDF files, with a modern dark-mode GUI.

![Application preview](screenshots/search_doc_tool.png)

## Features

- Search through `.docx` and `.pdf` files (recursively or not)
- Advanced query syntax:
  - Space-separated words → **OR** mode (at least one term)
  - `+` operator → **AND** mode (all terms must be present in the file)
  - `"exact phrase"` → literal phrase search
- Accent-insensitive search by default
- Options: case sensitivity, whole-word matching
- Context display around each match (highlighted term)
- Page number for PDFs
- CSV export
- Favorites system for frequently used folders
- Multi-threaded search (UI stays responsive) — ~500 files / 600 MB processed in about 3 minutes
- SQLite FTS5 index version available for near-instant searches on already-indexed folders

## Requirements

- Python 3.12+
- Dependencies:

```bash
pip install PyQt6 python-docx pymupdf
```

## Running

```bash
# Recommended — Python package (PyQt6 + SQLite FTS5 index)
python -m search_tool

# Legacy standalone scripts
python search_tool_qt_fts.py       # PyQt6 with FTS5 index
python search_tool_qt.py           # PyQt6 without index
python search_tool_tkinter.py      # Tkinter alternative
```

## Usage

1. Select a folder containing the documents to search
2. Enter one or more terms in the search bar
3. Start the search — results appear in real time
4. Double-click a result to open the file:
   - **PDF**: opens at the matching page (SumatraPDF or Adobe Reader)
   - **DOCX**: copies the context to the clipboard for quick Ctrl+F

Frequently used folders can be saved as **favorites** (right-click to rename or delete).

## SQLite FTS5 Index

The FTS5 version maintains a local index to speed up searches on previously browsed folders.

- Click **"Indexer le dossier"** to index the current folder — the indicator shows the number of indexed files (`✅ Index à jour` or `⚠ N/M indexés`)
- Subsequent searches use the FTS5 index for already-indexed files and direct search for the rest
- The index is **global** (shared across all folders) but searches are always filtered to the selected folder
- Files with no extractable text (scanned PDFs, protected files) are marked as processed and not retried
- The index is stored in `.data/search_tool_index.db` in the application folder

## Configuration

Configuration is automatically saved to `~/.search_tool_config.json` (last used folder, favorites).
