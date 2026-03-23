from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View

from ...models import Favorite


class RemoveFavoriteView(LoginRequiredMixin, View):
    def post(self, request):
        path = request.POST.get("path", "").strip()
        Favorite.objects.filter(user=request.user, path=path).delete()
        return redirect("index")
