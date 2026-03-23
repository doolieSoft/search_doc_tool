from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.shortcuts import render
from django.views import View

from ...models import Favorite, FavoriteGroup
from ...services.config_service import ConfigService


class IndexView(LoginRequiredMixin, View):
    def get(self, request):
        cfg_svc = ConfigService()
        cfg = cfg_svc.load()
        recurse = cfg.get("recurse", True)

        groups = (
            FavoriteGroup.objects
            .filter(user=request.user)
            .prefetch_related(
                Prefetch("favorites", queryset=Favorite.objects.filter(user=request.user))
            )
        )
        ungrouped = Favorite.objects.filter(user=request.user, group=None)

        return render(request, "search_tool/index.html", {
            "config": {"recurse": recurse},
            "groups": groups,
            "ungrouped_favorites": ungrouped,
            "index_summary": {},
        })
