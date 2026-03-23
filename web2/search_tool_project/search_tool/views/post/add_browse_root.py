import os

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...models import BrowseRoot


class AddBrowseRootView(LoginRequiredMixin, View):
    def post(self, request):
        if not request.user.is_superuser:
            return JsonResponse({"error": "Réservé aux superutilisateurs"}, status=403)
        path = request.POST.get("path", "").strip()
        label = request.POST.get("label", "").strip()
        if not path or not label:
            return JsonResponse({"error": "Libellé et chemin requis."}, status=400)
        path = os.path.normpath(path)
        if not os.path.isdir(path):
            return JsonResponse({"error": "Ce chemin n'existe pas ou n'est pas un dossier."}, status=400)
        if BrowseRoot.objects.filter(path=path).exists():
            return JsonResponse({"error": "Ce chemin est déjà dans la liste."}, status=400)
        root = BrowseRoot.objects.create(path=path, label=label)
        return JsonResponse({"ok": True, "id": root.id, "label": root.label, "path": root.path})
