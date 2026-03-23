from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...models import Favorite


class RenameFavoriteView(LoginRequiredMixin, View):
    def post(self, request):
        path = request.POST.get("path", "").strip()
        name = request.POST.get("name", "").strip()
        if not path or not name:
            return JsonResponse({"error": "invalid"}, status=400)
        Favorite.objects.filter(user=request.user, path=path).update(name=name)
        return JsonResponse({"ok": True})
