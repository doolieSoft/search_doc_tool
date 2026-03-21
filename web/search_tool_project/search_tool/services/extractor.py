try:
    import fitz  # pymupdf
    HAS_PDF = True
except ImportError:
    HAS_PDF = False


def extract_text_pdf(path: str) -> list[tuple[int, str]]:
    """Return list of (page_number, text) tuples (1-indexed). Page-aware."""
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
