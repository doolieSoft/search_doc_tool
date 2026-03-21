import os
import sqlite3

from .config import remove_accents
from .extractor import extract_text_pdf
from .converter import get_pdf_path


def get_db(db_file: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_file, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            path    TEXT PRIMARY KEY,
            mtime   REAL,
            indexed INTEGER DEFAULT 0
        )
    """)
    # One row per page — stores file path and page number as unindexed columns.
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS fts
        USING fts5(file UNINDEXED, page UNINDEXED, content, tokenize='trigram')
    """)
    conn.commit()
    return conn


def is_indexed(conn: sqlite3.Connection, path: str) -> bool:
    row = conn.execute(
        "SELECT mtime, indexed FROM files WHERE path=?", (path,)
    ).fetchone()
    if not row:
        return False
    mtime, indexed = row
    if not indexed:
        return False
    try:
        return abs(mtime - os.path.getmtime(path)) < 1.0
    except OSError:
        return False


def index_file(path: str, db_file: str, pdf_cache_dir: str) -> bool:
    """
    Index a file (PDF or DOCX→PDF).
    Returns True if text was extracted and indexed successfully.
    """
    pdf_path = get_pdf_path(path, pdf_cache_dir)
    if not pdf_path or not os.path.exists(pdf_path):
        return False

    pages = extract_text_pdf(pdf_path)
    if not pages:
        return False

    conn = get_db(db_file)
    try:
        conn.execute("DELETE FROM fts WHERE file=?", (path,))
        for page_num, text in pages:
            conn.execute(
                "INSERT INTO fts(file, page, content) VALUES (?,?,?)",
                (path, page_num, remove_accents(text)),
            )
        conn.execute(
            """
            INSERT INTO files(path, mtime, indexed) VALUES (?,?,1)
            ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, indexed=1
            """,
            (path, os.path.getmtime(path)),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def fts_search(terms: list, mode: str, case_sensitive: bool,
               db_file: str) -> list[dict]:
    """FTS5 pre-filter. Returns list of {'file': path} dicts."""
    if not terms:
        return []

    def fts_term(t: str) -> str:
        return f'"{remove_accents(t)}"' if " " in t else remove_accents(t)

    if mode == "AND":
        query = " AND ".join(fts_term(t) for t in terms)
    else:
        query = " OR ".join(fts_term(t) for t in terms)

    conn = get_db(db_file)
    try:
        rows = conn.execute(
            "SELECT DISTINCT file FROM fts WHERE content MATCH ?", (query,)
        ).fetchall()
        return [{"file": row[0]} for row in rows if os.path.exists(row[0])]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
