import os

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...indexing_state import get_folder_paths
from ...services.index_service import IndexService
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
        unindexed = [f for f in files if not index_svc.is_indexed(conn, f)]
        conn.close()
        return JsonResponse({"files": [os.path.basename(f) for f in unindexed],
                             "paths": unindexed})
