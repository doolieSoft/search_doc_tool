"""Unit tests for ConverterService."""
import hashlib
import os

import pytest

from search_tool.services.converter_service import ConverterService

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
SAMPLE_ENCRYPTED_DOCX = os.path.join(FIXTURES_DIR, "sample_encrypted.docx")


class TestConverterServiceStaticHelpers:
    def test_get_pdf_cache_path_deterministic(self):
        path = ConverterService.get_pdf_cache_path("/some/doc.docx", "/cache")
        path2 = ConverterService.get_pdf_cache_path("/some/doc.docx", "/cache")
        assert path == path2

    def test_get_pdf_cache_path_extension(self):
        path = ConverterService.get_pdf_cache_path("/some/doc.docx", "/cache")
        assert path.endswith(".pdf")

    def test_get_pdf_cache_path_uses_md5(self):
        original = "/some/doc.docx"
        expected_hash = hashlib.md5(original.encode("utf-8")).hexdigest()
        path = ConverterService.get_pdf_cache_path(original, "/cache")
        assert expected_hash in path

    def test_get_docx_copy_path_extension(self):
        path = ConverterService.get_docx_copy_path("/some/doc.docx", "/copies")
        assert path.endswith(".docx")

    def test_get_docx_copy_path_same_hash_as_pdf_cache(self):
        original = "/some/doc.docx"
        pdf_path = ConverterService.get_pdf_cache_path(original, "/cache")
        docx_path = ConverterService.get_docx_copy_path(original, "/copies")
        pdf_stem = os.path.splitext(os.path.basename(pdf_path))[0]
        docx_stem = os.path.splitext(os.path.basename(docx_path))[0]
        assert pdf_stem == docx_stem

    def test_is_cache_fresh_missing_pdf(self, tmp_path):
        docx = tmp_path / "doc.docx"
        docx.write_bytes(b"fake")
        assert ConverterService.is_cache_fresh(str(docx), "/nonexistent/cache.pdf") is False

    def test_is_cache_fresh_pdf_newer(self, tmp_path):
        import time
        docx = tmp_path / "doc.docx"
        docx.write_bytes(b"fake")
        time.sleep(0.05)
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"fake pdf")
        assert ConverterService.is_cache_fresh(str(docx), str(pdf)) is True

    def test_is_cache_fresh_pdf_older(self, tmp_path):
        import time
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"fake pdf")
        time.sleep(0.05)
        docx = tmp_path / "doc.docx"
        docx.write_bytes(b"fake")
        assert ConverterService.is_cache_fresh(str(docx), str(pdf)) is False

    def test_is_encrypted_docx_with_ole_file(self):
        assert ConverterService.is_encrypted_docx(SAMPLE_ENCRYPTED_DOCX) is True

    def test_is_encrypted_docx_with_valid_docx(self):
        sample_docx = os.path.join(FIXTURES_DIR, "sample.docx")
        assert ConverterService.is_encrypted_docx(sample_docx) is False

    def test_is_encrypted_docx_nonexistent(self):
        assert ConverterService.is_encrypted_docx("/nonexistent.docx") is False


class TestConverterServiceGetPdfPath:
    @pytest.fixture
    def svc(self):
        return ConverterService()

    @pytest.fixture
    def sample_pdf(self):
        return os.path.join(FIXTURES_DIR, "sample.pdf")

    def test_pdf_returns_original_path(self, svc, sample_pdf):
        result = svc.get_pdf_path(sample_pdf, "/some/cache")
        assert result == sample_pdf

    def test_unknown_extension_returns_none(self, svc):
        result = svc.get_pdf_path("/some/file.txt", "/cache")
        assert result is None

    def test_docx_nonexistent_returns_none(self, svc, tmp_path):
        # Without LibreOffice or Word, conversion of nonexistent file returns None
        result = svc.get_pdf_path("/nonexistent/file.docx", str(tmp_path))
        assert result is None
