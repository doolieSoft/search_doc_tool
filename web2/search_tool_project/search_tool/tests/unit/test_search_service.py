"""Unit tests for SearchService."""
import os

import pytest

from search_tool.services.search_service import SearchService

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
SAMPLE_PDF = os.path.join(FIXTURES_DIR, "sample.pdf")


@pytest.fixture
def svc():
    return SearchService()


class TestParseQuery:
    def test_single_term_or_mode(self):
        terms, mode = SearchService.parse_query("hello")
        assert terms == ["hello"]
        assert mode == "OR"

    def test_two_terms_comma_or_mode(self):
        terms, mode = SearchService.parse_query("hello, world")
        assert "hello" in terms
        assert "world" in terms
        assert mode == "OR"

    def test_two_terms_plus_and_mode(self):
        terms, mode = SearchService.parse_query("hello + world")
        assert "hello" in terms
        assert "world" in terms
        assert mode == "AND"

    def test_quoted_phrase(self):
        terms, mode = SearchService.parse_query('"search tool"')
        assert terms == ["search tool"]

    def test_quoted_phrase_with_plus_context(self):
        terms, mode = SearchService.parse_query('"search tool" + word')
        assert "search tool" in terms
        assert "word" in terms
        assert mode == "AND"

    def test_empty_string(self):
        terms, mode = SearchService.parse_query("")
        assert terms == []

    def test_spaces_only(self):
        terms, mode = SearchService.parse_query("   ")
        assert terms == []


class TestBuildPattern:
    def test_case_insensitive_match(self):
        pat = SearchService.build_pattern("hello", case_sensitive=False, whole_word=False)
        assert pat.search("HELLO WORLD")

    def test_case_sensitive_no_match(self):
        pat = SearchService.build_pattern("hello", case_sensitive=True, whole_word=False)
        assert not pat.search("HELLO")

    def test_whole_word_boundary(self):
        pat = SearchService.build_pattern("fix", case_sensitive=False, whole_word=True)
        assert not pat.search("fixture")
        assert pat.search("fix it")

    def test_multi_word_term(self):
        pat = SearchService.build_pattern("search tool", case_sensitive=False, whole_word=False)
        assert pat.search("search   tool")

    def test_accents_normalized(self):
        pat = SearchService.build_pattern("cafe", case_sensitive=False, whole_word=False)
        # "café" normalized becomes "cafe"
        from search_tool.services.config_service import remove_accents
        assert pat.search(remove_accents("café"))


class TestCollectFiles:
    def test_collects_pdf_files(self, tmp_path):
        (tmp_path / "a.pdf").write_bytes(b"fake")
        (tmp_path / "b.docx").write_bytes(b"fake")
        (tmp_path / "c.txt").write_bytes(b"fake")
        files = SearchService.collect_files(str(tmp_path), recurse=False)
        basenames = [os.path.basename(f) for f in files]
        assert "a.pdf" in basenames
        assert "b.docx" in basenames
        assert "c.txt" not in basenames

    def test_skips_temp_files(self, tmp_path):
        (tmp_path / "~$temp.docx").write_bytes(b"fake")
        (tmp_path / "real.docx").write_bytes(b"fake")
        files = SearchService.collect_files(str(tmp_path), recurse=False)
        basenames = [os.path.basename(f) for f in files]
        assert "~$temp.docx" not in basenames
        assert "real.docx" in basenames

    def test_recurse_true_finds_nested(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "nested.pdf").write_bytes(b"fake")
        files = SearchService.collect_files(str(tmp_path), recurse=True)
        basenames = [os.path.basename(f) for f in files]
        assert "nested.pdf" in basenames

    def test_recurse_false_ignores_nested(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "nested.pdf").write_bytes(b"fake")
        files = SearchService.collect_files(str(tmp_path), recurse=False)
        basenames = [os.path.basename(f) for f in files]
        assert "nested.pdf" not in basenames


class TestSearchFile:
    def test_search_pdf_finds_term(self, svc):
        results = svc.search_file(
            SAMPLE_PDF, ["FIXTURE_TERM_ONE"],
            case_sensitive=False, whole_word=False, mode="OR",
            pdf_cache_dir="/nonexistent/cache"
        )
        assert len(results) > 0
        terms_found = {r["term"] for r in results}
        assert "FIXTURE_TERM_ONE" in terms_found

    def test_search_pdf_and_mode_both_terms_same_page(self, svc):
        results = svc.search_file(
            SAMPLE_PDF, ["FIXTURE_TERM_ONE", "FIXTURE_TERM_TWO"],
            case_sensitive=False, whole_word=False, mode="AND",
            pdf_cache_dir="/nonexistent/cache"
        )
        # Page 3 has both terms
        assert len(results) > 0

    def test_search_pdf_no_match_returns_empty(self, svc):
        results = svc.search_file(
            SAMPLE_PDF, ["ZZZZ_NONEXISTENT_ZZZ"],
            case_sensitive=False, whole_word=False, mode="OR",
            pdf_cache_dir="/nonexistent/cache"
        )
        assert results == []

    def test_search_nonexistent_file_returns_empty(self, svc):
        results = svc.search_file(
            "/nonexistent/file.pdf", ["hello"],
            case_sensitive=False, whole_word=False, mode="OR",
            pdf_cache_dir="/nonexistent/cache"
        )
        assert results == []

    def test_result_has_required_keys(self, svc):
        results = svc.search_file(
            SAMPLE_PDF, ["FIXTURE_TERM_ONE"],
            case_sensitive=False, whole_word=False, mode="OR",
            pdf_cache_dir="/nonexistent/cache"
        )
        for r in results:
            assert "file" in r
            assert "term" in r
            assert "context" in r
            assert "page" in r

    def test_result_page_is_int(self, svc):
        results = svc.search_file(
            SAMPLE_PDF, ["FIXTURE_TERM_ONE"],
            case_sensitive=False, whole_word=False, mode="OR",
            pdf_cache_dir="/nonexistent/cache"
        )
        for r in results:
            assert isinstance(r["page"], int)

    def test_context_contains_marker(self, svc):
        results = svc.search_file(
            SAMPLE_PDF, ["FIXTURE_TERM_ONE"],
            case_sensitive=False, whole_word=False, mode="OR",
            pdf_cache_dir="/nonexistent/cache"
        )
        for r in results:
            # context should have [...] marker around matched term
            assert "[" in r["context"] and "]" in r["context"]


class TestGetContext:
    def test_basic_context(self):
        text = "The quick brown fox jumps over the lazy dog"
        import re
        m = re.search("fox", text)
        ctx = SearchService.get_context(text, m)
        assert "[fox]" in ctx

    def test_context_truncated_at_start(self):
        text = "A" * 200 + " fox " + "B" * 200
        import re
        m = re.search("fox", text)
        ctx = SearchService.get_context(text, m)
        assert ctx.startswith("…")

    def test_context_truncated_at_end(self):
        text = "start fox " + "B" * 200
        import re
        m = re.search("fox", text)
        ctx = SearchService.get_context(text, m)
        assert ctx.endswith("…")
