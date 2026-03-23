from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...models import FavoriteGroup


class RenameGroupView(LoginRequiredMixin, View):
    def post(self, request):
        group_id = request.POST.get("group_id", "").strip()
        name = request.POST.get("name", "").strip()
        if not group_id or not name:
            return JsonResponse({"error": "invalid"}, status=400)
        FavoriteGroup.objects.filter(user=request.user, pk=group_id).update(name=name)
        return JsonResponse({"ok": True})
