from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...models import BrowseRoot


class RemoveBrowseRootView(LoginRequiredMixin, View):
    def post(self, request):
        if not request.user.is_superuser:
            return JsonResponse({"error": "Réservé aux superutilisateurs"}, status=403)
        root_id = request.POST.get("id", "")
        BrowseRoot.objects.filter(pk=root_id).delete()
        return JsonResponse({"ok": True})
