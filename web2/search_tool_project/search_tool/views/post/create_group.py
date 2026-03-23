from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...models import FavoriteGroup


class CreateGroupView(LoginRequiredMixin, View):
    def post(self, request):
        name = request.POST.get("name", "").strip()
        if not name:
            return JsonResponse({"error": "Nom requis"}, status=400)
        FavoriteGroup.objects.get_or_create(user=request.user, name=name)
        return JsonResponse({"ok": True})
