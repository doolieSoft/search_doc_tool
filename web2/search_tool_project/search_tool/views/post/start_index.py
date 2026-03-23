import os
import threading

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...indexing_state import (
    _index_lock,
    _index_state,
    get_folder_paths,
    is_stale,
    run_indexing,
)


class StartIndexView(LoginRequiredMixin, View):
    def post(self, request):
        global _index_state
        folder = request.POST.get("folder", "").strip()
        recurse = request.POST.get("recurse", "true") == "true"

        if not folder or not os.path.isdir(folder):
            return JsonResponse({"error": "Dossier invalide."}, status=400)

        db_file = get_folder_paths(folder, settings.DATA_DIR)["db"]

        with _index_lock:
            if _index_state["running"]:
                if is_stale():
                    # Thread mort sans cleanup — on réinitialise
                    _index_state["running"] = False
                else:
                    return JsonResponse({"error": "Indexation déjà en cours."}, status=409)
            _index_state.update({
                "running": True,
                "phase": "",
                "conv_done": 0,
                "conv_total": 0,
                "done": 0,
                "total": 0,
                "current": "",
                "newly_indexed": 0,
                "failed": 0,
                "error": None,
                "folder": folder,
            })

        thread = threading.Thread(
            target=run_indexing,
            args=(folder, recurse, db_file, settings.DATA_DIR),
            daemon=True,
        )
        thread.start()
        return JsonResponse({"started": True})
