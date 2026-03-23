from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from ...indexing_state import _index_lock, _index_state


class IndexStatusView(LoginRequiredMixin, View):
    def get(self, request):
        with _index_lock:
            state = dict(_index_state)
        return JsonResponse(state)
