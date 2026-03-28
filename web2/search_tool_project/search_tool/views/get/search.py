"""
SearchView handles POST (HTMX search form submission).
It is placed in views/get/ because its purpose is to return a read-only search results partial.
The HTTP method is POST (due to HTMX form), but there is no side-effect beyond config persistence.
"""
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View

from .._helpers import encode_path, highlight_context
from ...indexing_state import get_folder_paths
from ...services.config_service import ConfigService
from ...services.index_service import IndexService
from ...services.search_service import SearchService


class SearchView(LoginRequiredMixin, View):
    """
    POST: Run a search and return the _results.html partial (used by HTMX).
    """

    def post(self, request):
        folder = request.POST.get("folder", "").strip()
        terms_raw = request.POST.get("terms", "").strip()
        case_sensitive = request.POST.get("case_sensitive") == "on"
        whole_word = request.POST.get("whole_word") == "on"
        recurse = request.POST.get("recurse", "on") == "on"

        def error(msg):
            return render(request, "search_tool/_results.html",
                          {"error": msg, "results": []})

        if not folder or not os.path.isdir(folder):
            return error("Dossier invalide.")
        if not terms_raw:
            return error("Entrez au moins un terme.")

        search_svc = SearchService()
        terms, mode = search_svc.parse_query(terms_raw)
        if not terms:
            return render(request, "search_tool/_results.html", {"results": []})

        short = [t for t in terms if len(t) < 3]
        if short:
            return error(f"Terme trop court (3 caractères minimum) : {', '.join(short)}")

        cfg_svc = ConfigService()
        cfg = cfg_svc.load()
        cfg["folder"] = folder
        cfg["recurse"] = recurse
        cfg_svc.save(cfg)

        files = search_svc.collect_files(folder, recurse)

        # FTS5 pre-filter
        fpaths = get_folder_paths(folder, settings.DATA_DIR)
        db_file = fpaths["db"]
        index_svc = IndexService(db_file=db_file)
        conn = index_svc.get_db()
        indexed_set = {f for f in files if index_svc.is_indexed(conn, f)}
        conn.close()

        # ── Fichiers indexés : lecture depuis FTS5 (zéro I/O disque) ─────────
        fts_with_content = index_svc.fts_search_with_content(terms, mode, case_sensitive)
        pages_by_file = defaultdict(list)
        for row in fts_with_content:
            if row["file"] in indexed_set:
                pages_by_file[row["file"]].append(
                    {"page": row["page"], "content": row["content"]}
                )

        all_results = []
        for path, pages in pages_by_file.items():
            all_results.extend(
                search_svc.search_from_db_content(
                    path, pages, terms, case_sensitive, whole_word, mode
                )
            )

        # ── Fichiers non indexés : lecture PDF (comportement actuel) ─────────
        not_indexed = [f for f in files if f not in indexed_set]
        if not_indexed:
            workers = min(8, os.cpu_count() or 4, max(1, len(not_indexed)))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        search_svc.search_file, path, terms,
                        case_sensitive, whole_word, mode,
                        fpaths["pdf_cache"],
                    ): path
                    for path in not_indexed
                }
                for future in as_completed(futures):
                    path = futures[future]
                    try:
                        results = future.result()
                    except Exception as e:
                        results = [{"file": path, "term": "ERREUR",
                                    "context": str(e), "page": None}]
                    all_results.extend(results)

        # Enrich results for template
        folder_encoded = encode_path(folder)
        for r in all_results:
            r["filename"] = os.path.basename(r["file"])
            r["file_encoded"] = encode_path(r["file"])
            r["folder_encoded"] = folder_encoded
            r["context_html"] = highlight_context(r["context"])

        matched_files = len({r["file"] for r in all_results if r["term"] != "ERREUR"})

        return render(request, "search_tool/_results.html", {
            "results": all_results,
            "matched_files": matched_files,
            "total_files": len(files),
        })
