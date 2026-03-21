import os
import sqlite3

from .config import DB_FILE, remove_accents
from .extractor import HAS_DOCX, HAS_PDF, extract_text_docx, extract_text_pdf


def get_db() -> sqlite3.Connection:
    """Ouvre la connexion à la base d'index."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            path    TEXT PRIMARY KEY,
            mtime   REAL,
            indexed INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS fts
        USING fts5(path UNINDEXED, content, tokenize='trigram')
    """)
    conn.commit()
    return conn


def is_indexed(conn: sqlite3.Connection, path: str) -> bool:
    """Vérifie si le fichier est indexé et à jour."""
    row = conn.execute("SELECT mtime FROM files WHERE path=?", (path,)).fetchone()
    if not row:
        return False
    return abs(row[0] - os.path.getmtime(path)) < 1.0


def index_file(conn: sqlite3.Connection, path: str) -> bool:
    """Extrait et indexe un fichier. Retourne True si succès."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".docx":
            if not HAS_DOCX:
                return False
            text = extract_text_docx(path)
        elif ext == ".pdf":
            if not HAS_PDF:
                return False
            pages = extract_text_pdf(path)
            text = " ".join(t for _, t in pages)
        else:
            return False
    except Exception:
        return False

    if not text.strip():
        return False

    text_norm = remove_accents(text)
    mtime = os.path.getmtime(path)

    conn.execute("DELETE FROM fts WHERE path=?", (path,))
    conn.execute("INSERT INTO fts(path, content) VALUES (?,?)", (path, text_norm))
    conn.execute("""
        INSERT INTO files(path, mtime, indexed) VALUES (?,?,1)
        ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, indexed=1
    """, (path, mtime))
    return True


def fts_search(conn: sqlite3.Connection, terms: list,
               mode: str, case_sensitive: bool) -> list[dict]:
    """Recherche dans l'index FTS5. Retourne liste de résultats."""
    if not terms:
        return []

    def fts_term(t):
        words = t.split()
        if len(words) > 1:
            return f'"{t}"'
        return t

    if mode == "AND":
        fts_query = " AND ".join(fts_term(t) for t in terms)
    else:
        fts_query = " OR ".join(fts_term(t) for t in terms)

    try:
        rows = conn.execute("""
            SELECT path,
                   snippet(fts, 1, '[', ']', '…', 25),
                   snippet(fts, 1, '', '', '', 5)
            FROM fts WHERE fts MATCH ? ORDER BY rank
        """, (fts_query,)).fetchall()
    except sqlite3.OperationalError:
        return []

    results = []
    for path, snippet_display, snippet_ctrlf in rows:
        if not os.path.exists(path):
            continue
        term_label = " + ".join(terms) if mode == "AND" else terms[0]
        results.append({
            "file": path,
            "term": term_label,
            "context": snippet_display,
            "page": None,
            "ctrlf": snippet_ctrlf.strip(),
        })
    return results
