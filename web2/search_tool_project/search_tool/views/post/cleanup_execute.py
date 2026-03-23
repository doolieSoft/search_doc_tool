import shutil

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from .._helpers import orphaned_dirs


class CleanupExecuteView(LoginRequiredMixin, View):
    def post(self, request):
        if not request.user.is_superuser:
            return JsonResponse({"error": "Accès refusé"}, status=403)
        deleted = []
        for item in orphaned_dirs():
            try:
                shutil.rmtree(item["path"])
                deleted.append(item["name"])
            except Exception:
                pass
        return JsonResponse({"deleted": deleted, "count": len(deleted)})
