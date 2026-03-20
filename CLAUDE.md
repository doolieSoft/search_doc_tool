# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Activate virtual environment (Windows)
venv\Scripts\activate

# Run the primary PyQt6 application
python search_tool_qt.py

# Run the alternative Tkinter application
python search_tool_tkinter.py
```

**Python version:** 3.12.10 (see `.python-version`)

**Dependencies** (install into venv if missing):
```bash
pip install PyQt6 python-docx pymupdf
```

## Architecture

This is a single-file desktop application for searching terms across `.docx` and `.pdf` files. There are two independent UI implementations:
- **[search_tool_qt.py](search_tool_qt.py)** — Primary implementation, PyQt6 with dark mode
- **[search_tool_tkinter.py](search_tool_tkinter.py)** — Alternative Tkinter implementation

### Data flow

1. **File collection** (`collect_files`) — scans a folder recursively for `.docx`/`.pdf`, skipping `~$` temp files
2. **Text extraction** — `extract_text_docx` (python-docx) or `extract_text_pdf` (pymupdf/fitz), page-aware for PDFs
3. **Query parsing** (`parse_query`) — spaces = OR mode, `+` = AND mode, `"quoted"` = phrase; returns `(terms, mode)`
4. **Pattern building** (`build_pattern`) — compiles regex with optional case-sensitivity and whole-word flags
5. **Search** (`search_file`) — called concurrently via `ThreadPoolExecutor` (8 workers) inside `SearchWorker(QThread)` to keep UI responsive
6. **Context extraction** (`get_context`, `get_combined_context`) — 100-char windows around matches, merged when within 30 words
7. **Display** — `ResultsModel(QAbstractTableModel)` + `ContextDelegate` renders HTML-highlighted results (matched terms in orange `#FFB347`)

### Configuration

Persisted to `~/.search_tool_config.json`:
- Last used folder path
- Favorites list (folder paths with optional custom display names)

### Key design notes

- `remove_accents()` normalizes Unicode before matching (accent-insensitive search)
- AND mode requires all terms present in the same file; OR mode reports per-term matches
- PDF results include page numbers; DOCX results copy context to clipboard for use with Ctrl+F
- `SearchWorker` has a `_stop` flag checked between files for cancellation support
- Opening a result double-clicks: DOCX copies context to clipboard, PDF tries SumatraPDF/Adobe Reader with page argument
