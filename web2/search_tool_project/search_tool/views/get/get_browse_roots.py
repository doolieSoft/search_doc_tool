from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...models import BrowseRoot


class GetBrowseRootsView(LoginRequiredMixin, View):
    def get(self, request):
        if not request.user.is_superuser:
            return JsonResponse({"error": "Réservé aux superutilisateurs"}, status=403)
        roots = list(BrowseRoot.objects.order_by("label").values("id", "label", "path"))
        return JsonResponse({"roots": roots})
