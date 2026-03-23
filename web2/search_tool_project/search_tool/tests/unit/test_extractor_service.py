"""Unit tests for ExtractorService."""
import os

import pytest

from search_tool.services.extractor_service import ExtractorService

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
SAMPLE_PDF = os.path.join(FIXTURES_DIR, "sample.pdf")


class TestExtractorService:
    @pytest.fixture
    def svc(self):
        return ExtractorService()

    def test_extract_sample_pdf_returns_pages(self, svc):
        pages = svc.extract_text_pdf(SAMPLE_PDF)
        assert len(pages) == 3

    def test_extract_page_numbers_are_1_indexed(self, svc):
        pages = svc.extract_text_pdf(SAMPLE_PDF)
        nums = [p[0] for p in pages]
        assert nums == [1, 2, 3]

    def test_extract_page_content(self, svc):
        pages = svc.extract_text_pdf(SAMPLE_PDF)
        texts = [p[1] for p in pages]
        assert any("FIXTURE_TERM_ONE" in t for t in texts)
        assert any("FIXTURE_TERM_TWO" in t for t in texts)

    def test_extract_nonexistent_file_returns_empty(self, svc):
        result = svc.extract_text_pdf("/nonexistent/path/to/file.pdf")
        assert result == []

    def test_extract_returns_tuples(self, svc):
        pages = svc.extract_text_pdf(SAMPLE_PDF)
        for page_num, text in pages:
            assert isinstance(page_num, int)
            assert isinstance(text, str)

    def test_extract_empty_pages_are_skipped(self, svc, tmp_path):
        """A PDF with blank pages should not return entries for blank pages."""
        import fitz
        doc = fitz.open()
        doc.new_page()  # blank page
        page2 = doc.new_page()
        page2.insert_text((72, 100), "Hello", fontsize=12)
        path = str(tmp_path / "test.pdf")
        doc.save(path)
        doc.close()
        pages = svc.extract_text_pdf(path)
        assert len(pages) == 1
        assert pages[0][0] == 2  # page number is 2 (blank page 1 is skipped)
