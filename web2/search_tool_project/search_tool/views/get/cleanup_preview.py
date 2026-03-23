from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from .._helpers import orphaned_dirs


class CleanupPreviewView(LoginRequiredMixin, View):
    def get(self, request):
        if not request.user.is_superuser:
            return JsonResponse({"error": "Accès refusé"}, status=403)
        return JsonResponse({"orphaned": orphaned_dirs()})
