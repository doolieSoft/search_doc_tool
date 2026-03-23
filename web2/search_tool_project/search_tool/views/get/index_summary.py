import os

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...indexing_state import get_folder_paths, get_index_summary
from ...services.index_service import IndexService
from ...services.search_service import SearchService


class IndexSummaryView(LoginRequiredMixin, View):
    def get(self, request):
        folder = request.GET.get("folder", "").strip()
        recurse = request.GET.get("recurse", "true") == "true"
        if not folder or not os.path.isdir(folder):
            return JsonResponse({"total": 0, "indexed": 0})
        db_file = get_folder_paths(folder, settings.DATA_DIR)["db"]
        index_svc = IndexService(db_file=db_file)
        search_svc = SearchService()
        summary = get_index_summary(folder, recurse, db_file,
                                    search_svc.collect_files, index_svc)
        return JsonResponse(summary)
