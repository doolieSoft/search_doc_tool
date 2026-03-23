import os

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View

from ...models import Favorite


class AddFavoriteView(LoginRequiredMixin, View):
    def post(self, request):
        folder = request.POST.get("folder", "").strip()
        if not folder or not os.path.isdir(folder):
            return redirect("index")
        name = os.path.basename(folder) or folder
        Favorite.objects.get_or_create(user=request.user, path=folder,
                                       defaults={"name": name})
        return redirect("index")
