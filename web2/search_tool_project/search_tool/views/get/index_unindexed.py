import os

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...indexing_state import get_folder_paths
from ...services.index_service import IndexService  # noqa: F401 (STATUS_FAILED used below)
from ...services.search_service import SearchService


class IndexUnindexedView(LoginRequiredMixin, View):
    def get(self, request):
        folder = request.GET.get("folder", "").strip()
        recurse = request.GET.get("recurse", "true") == "true"
        if not folder or not os.path.isdir(folder):
            return JsonResponse({"files": []})
        search_svc = SearchService()
        files = search_svc.collect_files(folder, recurse)
        db_file = get_folder_paths(folder, settings.DATA_DIR)["db"]
        index_svc = IndexService(db_file=db_file)
        conn = index_svc.get_db()
        result = []
        for f in files:
            if not index_svc.is_indexed(conn, f):
                row = conn.execute(
                    "SELECT indexed FROM files WHERE path=?", (f,)
                ).fetchone()
                status = "failed" if (row and row[0] == IndexService.STATUS_FAILED) else "pending"
                result.append({"name": os.path.basename(f), "path": f, "status": status})
        conn.close()
        return JsonResponse({"files": result})
