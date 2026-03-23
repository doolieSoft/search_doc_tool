import os

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from .._helpers import is_under_root, list_drives
from ...models import BrowseRoot


class BrowseDirView(LoginRequiredMixin, View):
    def get(self, request):
        roots = list(BrowseRoot.objects.order_by("label"))
        path = request.GET.get("path", "").strip()

        # ── No roots configured → legacy behaviour ────────────────────────────
        if not roots:
            if not request.user.is_superuser:
                return JsonResponse(
                    {"error": "Aucun dossier autorisé configuré. Contactez l'administrateur."},
                    status=503,
                )
            if not path:
                drives = list_drives()
                entries = [{"name": d.rstrip("\\"), "path": d} for d in drives]
                return JsonResponse({"path": "", "entries": entries, "mode": "drives"})
            path = os.path.normpath(path)
            if not os.path.isdir(path):
                drives = list_drives()
                entries = [{"name": d.rstrip("\\"), "path": d} for d in drives]
                return JsonResponse({"path": "", "entries": entries, "mode": "drives"})
            entries = []
            parent = os.path.dirname(path)
            if parent == path:
                entries.append({"name": "← Lecteurs", "path": ""})
            else:
                entries.append({"name": "..", "path": parent})
            try:
                for name in sorted(os.listdir(path)):
                    full = os.path.join(path, name)
                    if os.path.isdir(full) and not name.startswith("."):
                        entries.append({"name": name, "path": full})
            except PermissionError:
                pass
            return JsonResponse({"path": path, "entries": entries, "mode": "dir"})

        # ── Roots configured ──────────────────────────────────────────────────
        if not path:
            entries = [{"name": r.label, "path": r.path, "sub": r.path} for r in roots]
            return JsonResponse({"path": "", "entries": entries, "mode": "roots"})

        path = os.path.normpath(path)

        # Security: path must be under one of the configured roots
        matched_root = next((r for r in roots if is_under_root(path, r.path)), None)
        if not matched_root:
            return JsonResponse({"error": "Accès refusé"}, status=403)

        if not os.path.isdir(path):
            path = os.path.normpath(matched_root.path)

        entries = []
        if (is_under_root(path, matched_root.path) and
                os.path.normcase(os.path.normpath(path)) ==
                os.path.normcase(os.path.normpath(matched_root.path))):
            entries.append({"name": "← Dossiers autorisés", "path": ""})
        else:
            entries.append({"name": "..", "path": os.path.dirname(path)})

        try:
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if os.path.isdir(full) and not name.startswith("."):
                    entries.append({"name": name, "path": full})
        except PermissionError:
            pass

        return JsonResponse({"path": path, "entries": entries, "mode": "dir"})
