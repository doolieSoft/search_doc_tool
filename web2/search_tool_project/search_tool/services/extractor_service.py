try:
    import fitz  # pymupdf
    HAS_PDF = True
except ImportError:
    HAS_PDF = False


class ExtractorService:
    """Extracts text from PDF files page by page."""

    def extract_text_pdf(self, path: str) -> list[tuple[int, str]]:
        """
        Return list of (page_number, text) tuples (1-indexed). Page-aware.
        Returns an empty list if pymupdf is unavailable or the file cannot be read.
        """
        if not HAS_PDF:
            return []
        try:
            doc = fitz.open(path)
            pages = []
            for i, page in enumerate(doc, start=1):
                text = page.get_text("text")
                if text.strip():
                    pages.append((i, text))
            doc.close()
            return pages
        except Exception:
            return []
