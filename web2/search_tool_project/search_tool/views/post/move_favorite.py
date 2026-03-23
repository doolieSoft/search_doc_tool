from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from ...models import Favorite, FavoriteGroup


class MoveFavoriteView(LoginRequiredMixin, View):
    def post(self, request):
        path = request.POST.get("path", "").strip()
        group_id = request.POST.get("group_id", "").strip()
        if not path:
            return JsonResponse({"error": "invalid"}, status=400)
        if group_id:
            group = get_object_or_404(FavoriteGroup, user=request.user, pk=group_id)
            Favorite.objects.filter(user=request.user, path=path).update(group=group)
        else:
            Favorite.objects.filter(user=request.user, path=path).update(group=None)
        return JsonResponse({"ok": True})
