from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...indexing_state import _index_lock, _index_state


class StopIndexView(LoginRequiredMixin, View):
    def post(self, request):
        with _index_lock:
            if _index_state["running"]:
                _index_state["running"] = False
        return JsonResponse({"stopped": True})
