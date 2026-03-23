from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...models import FavoriteGroup


class DeleteGroupView(LoginRequiredMixin, View):
    def post(self, request):
        group_id = request.POST.get("group_id", "").strip()
        FavoriteGroup.objects.filter(user=request.user, pk=group_id).delete()
        return JsonResponse({"ok": True})
