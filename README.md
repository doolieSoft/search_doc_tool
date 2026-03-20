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

## Requirements

- Python 3.12+
- Dependencies:

```bash
pip install PyQt6 python-docx pymupdf
```

## Running

```bash
# PyQt6 interface (recommended)
python search_tool_qt.py

# Alternative Tkinter interface
python search_tool_tkinter.py
```

## Usage

1. Select a folder containing the documents to search
2. Enter one or more terms in the search bar
3. Start the search — results appear in real time
4. Double-click a result to open the file:
   - **PDF**: opens at the matching page (SumatraPDF or Adobe Reader)
   - **DOCX**: copies the context to the clipboard for quick Ctrl+F

Frequently used folders can be saved as **favorites** (right-click to rename or delete).

## Configuration

Configuration is automatically saved to `~/.search_tool_config.json` (last used folder, favorites).
