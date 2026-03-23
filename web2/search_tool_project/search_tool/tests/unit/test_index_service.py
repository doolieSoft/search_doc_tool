"""Unit tests for IndexService (uses real in-memory/tmp SQLite)."""
import os
import sqlite3

import pytest

from search_tool.services.index_service import IndexService

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
SAMPLE_PDF = os.path.join(FIXTURES_DIR, "sample.pdf")


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_index.db")


@pytest.fixture
def svc(tmp_db):
    return IndexService(db_file=tmp_db)


class TestIndexServiceGetDb:
    def test_creates_files_table(self, svc):
        conn = svc.get_db()
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "files" in tables
        conn.close()

    def test_creates_fts_virtual_table(self, svc):
        conn = svc.get_db()
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "fts" in tables
        conn.close()

    def test_idempotent_multiple_calls(self, svc):
        conn1 = svc.get_db()
        conn1.close()
        conn2 = svc.get_db()
        conn2.close()


class TestIndexServiceIsIndexed:
    def test_not_indexed_when_empty(self, svc):
        conn = svc.get_db()
        assert svc.is_indexed(conn, "/nonexistent/path.pdf") is False
        conn.close()

    def test_not_indexed_when_row_exists_but_indexed_false(self, svc):
        conn = svc.get_db()
        conn.execute("INSERT INTO files(path, mtime, indexed) VALUES (?, ?, 0)", ("/some/file.pdf", 0.0))
        conn.commit()
        assert svc.is_indexed(conn, "/some/file.pdf") is False
        conn.close()

    def test_indexed_sample_pdf(self, svc):
        svc.index_file(SAMPLE_PDF, "/nonexistent/cache")
        conn = svc.get_db()
        result = svc.is_indexed(conn, SAMPLE_PDF)
        conn.close()
        assert result is True

    def test_not_indexed_when_mtime_differs(self, svc, tmp_path):
        """File with stale mtime is considered not indexed."""
        import fitz
        pdf = tmp_path / "test.pdf"
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((72, 100), "Test content", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        svc2 = IndexService(db_file=str(tmp_path / "idx.db"))
        svc2.index_file(str(pdf), str(tmp_path / "cache"))

        # Manually set a wrong mtime in the DB
        conn = svc2.get_db()
        conn.execute("UPDATE files SET mtime=0 WHERE path=?", (str(pdf),))
        conn.commit()
        result = svc2.is_indexed(conn, str(pdf))
        conn.close()
        assert result is False


class TestIndexServiceIndexFile:
    def test_index_pdf_returns_true(self, svc):
        result = svc.index_file(SAMPLE_PDF, "/nonexistent/cache")
        assert result is True

    def test_index_nonexistent_file_returns_false(self, svc):
        result = svc.index_file("/nonexistent/file.pdf", "/nonexistent/cache")
        assert result is False

    def test_index_inserts_fts_rows(self, svc):
        svc.index_file(SAMPLE_PDF, "/nonexistent/cache")
        conn = svc.get_db()
        rows = conn.execute("SELECT DISTINCT file FROM fts").fetchall()
        conn.close()
        assert any(SAMPLE_PDF in r[0] for r in rows)

    def test_index_stores_page_numbers(self, svc):
        svc.index_file(SAMPLE_PDF, "/nonexistent/cache")
        conn = svc.get_db()
        pages = conn.execute("SELECT page FROM fts WHERE file=? ORDER BY page", (SAMPLE_PDF,)).fetchall()
        conn.close()
        page_nums = [r[0] for r in pages]
        assert 1 in page_nums
        assert 2 in page_nums
        assert 3 in page_nums


class TestIndexServiceFtsSearch:
    def test_fts_search_finds_term(self, svc):
        svc.index_file(SAMPLE_PDF, "/nonexistent/cache")
        results = svc.fts_search(["FIXTURE_TERM_ONE"], "OR", False)
        assert any(r["file"] == SAMPLE_PDF for r in results)

    def test_fts_search_and_mode_both_terms(self, svc):
        svc.index_file(SAMPLE_PDF, "/nonexistent/cache")
        results = svc.fts_search(["FIXTURE_TERM_ONE", "FIXTURE_TERM_TWO"], "AND", False)
        # Page 3 has both terms
        assert any(r["file"] == SAMPLE_PDF for r in results)

    def test_fts_search_empty_terms_returns_empty(self, svc):
        results = svc.fts_search([], "OR", False)
        assert results == []

    def test_fts_search_no_match_returns_empty(self, svc):
        svc.index_file(SAMPLE_PDF, "/nonexistent/cache")
        results = svc.fts_search(["ZZZZ_NONEXISTENT_ZZZ"], "OR", False)
        assert results == []

    def test_fts_search_returns_file_dict(self, svc):
        svc.index_file(SAMPLE_PDF, "/nonexistent/cache")
        results = svc.fts_search(["FIXTURE"], "OR", False)
        for r in results:
            assert "file" in r
