import io
import os

import fitz
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, HttpResponse, HttpResponseNotFound
from django.views import View

from .._helpers import decode_path
from ...indexing_state import get_folder_paths
from ...services.converter_service import ConverterService


class ServePdfView(LoginRequiredMixin, View):
    def get(self, request):
        encoded = request.GET.get("path", "")
        folder_encoded = request.GET.get("folder", "")
        term = request.GET.get("term", "").strip()
        try:
            page_num = int(request.GET.get("page", 1))
        except ValueError:
            page_num = 1

        try:
            original_path = decode_path(encoded)
            folder = decode_path(folder_encoded) if folder_encoded else ""
        except Exception:
            return HttpResponseNotFound()

        pdf_cache_dir = (
            get_folder_paths(folder, settings.DATA_DIR)["pdf_cache"]
            if folder
            else settings.PDF_CACHE_DIR
        )

        converter = ConverterService()
        ext = os.path.splitext(original_path)[1].lower()
        if ext == ".pdf":
            serve_path = original_path
        elif ext == ".docx":
            serve_path = converter.get_pdf_cache_path(original_path, pdf_cache_dir)
        else:
            return HttpResponseNotFound()

        if not os.path.exists(serve_path):
            return HttpResponseNotFound("Fichier non trouvé. Indexez le dossier d'abord.")

        if not term:
            return FileResponse(open(serve_path, "rb"), content_type="application/pdf")

        # AND mode produces "mot1 + mot2" — split to highlight each term individually.
        highlight_terms = [t.strip() for t in term.split(" + ") if t.strip()]

        # Annotate highlights in memory, then redirect browser to the right page.
        doc = fitz.open(serve_path)
        page_idx = max(0, page_num - 1)
        for idx in range(len(doc)):
            page = doc[idx]
            for ht in highlight_terms:
                for rect in page.search_for(ht, quads=False):
                    annot = page.add_highlight_annot(rect)
                    annot.set_colors(stroke=(1, 0.85, 0))  # yellow
                    annot.update()

        buf = io.BytesIO()
        doc.save(buf, garbage=4, deflate=True)
        doc.close()
        buf.seek(0)

        response = HttpResponse(buf.read(), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="{os.path.basename(serve_path)}"'
        )
        return response
