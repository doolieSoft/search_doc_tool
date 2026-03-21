import base64
import hashlib
import io
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fitz  # PyMuPDF
from django.conf import settings
from django.http import FileResponse, HttpResponse, HttpResponseNotFound, JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import Favorite, FavoriteGroup, IndexingStatus
from .services.config import load_config, save_config
from .services.converter import get_pdf_cache_path
from .services.index import fts_search, get_db, index_file, is_indexed
from .services.search import collect_files, parse_query, search_file

# ── IndexingStatus DB helpers ─────────────────────────────────────────────────

def _persist_status(**kwargs):
    """Write key fields to the DB singleton (pk=1). Non-blocking best-effort."""
    try:
        IndexingStatus.objects.update_or_create(pk=1, defaults=kwargs)
    except Exception:
        pass  # never crash the indexing thread over a DB write


def _reset_running_on_startup():
    """Called at module load: if DB says running=True, the thread is dead — fix it."""
    try:
        IndexingStatus.objects.filter(pk=1, running=True).update(
            running=False, error="Interrompu (redémarrage serveur)"
        )
    except Exception:
        pass


_reset_running_on_startup()

# ── Per-user per-folder DB path ───────────────────────────────────────────────

def _get_folder_paths(folder: str) -> dict:
    """Return all per-folder data paths (db, pdf_cache, docx_copy), creating dirs as needed."""
    normalized = os.path.normpath(folder).lower()
    folder_hash = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:10]
    folder_name = re.sub(r"[^\w\-]", "_", os.path.basename(normalized) or "root")
    base_dir = Path(settings.DATA_DIR) / "folders" / f"{folder_name}_{folder_hash}"
    base_dir.mkdir(parents=True, exist_ok=True)
    return {
        "db":         str(base_dir / "index.db"),
        "pdf_cache":  str(base_dir / "pdf_cache"),
        "docx_copy":  str(base_dir / "docx_copy"),
    }


# ── Background indexing state ────────────────────────────────────────────────

_index_state: dict = {
    "running": False,
    "phase": "",       # "converting" | "indexing"
    "conv_done": 0,
    "conv_total": 0,
    "done": 0,
    "total": 0,
    "current": "",
    "newly_indexed": 0,
    "failed": 0,
    "error": None,
    "folder": "",
}
_index_lock = threading.Lock()


def _run_indexing(folder: str, recurse: bool, db_file: str):
    """
    Two-phase indexing:
    1. Convert DOCX → PDF sequentially (LibreOffice can't run in parallel safely)
    2. Extract text + insert into FTS5 in parallel (real multithreading benefit)
    """
    global _index_state
    from .services.converter import convert_docx_to_pdf

    files = collect_files(folder, recurse)

    conn = get_db(db_file)
    to_index = [f for f in files if not is_indexed(conn, f)]
    conn.close()

    docx_to_convert = [p for p in to_index if p.lower().endswith(".docx")]
    pdf_direct = [p for p in to_index if not p.lower().endswith(".docx")]

    # Total = number of files to index (each file counted once).
    total = len(to_index)

    from django.utils import timezone
    with _index_lock:
        _index_state.update({
            "total": total, "done": 0, "newly_indexed": 0, "failed": 0,
            "current": "", "phase": "converting" if docx_to_convert else "indexing",
            "conv_done": 0, "conv_total": len(docx_to_convert),
        })
    _persist_status(folder=folder, running=True, total=total, done=0,
                    newly_indexed=0, failed=0, current="", error=None,
                    started_at=timezone.now(), finished_at=None)

    if not to_index:
        with _index_lock:
            _index_state["running"] = False
        _persist_status(running=False, finished_at=timezone.now())
        return

    # ── Phase 1 : convert DOCX → PDF ─────────────────────────────────────────
    pdf_ready = []  # paths ready to index (original PDFs + successfully converted)

    if docx_to_convert:
        from .services.converter import is_word_available, WordConverter

        folder_paths = _get_folder_paths(folder)
        pdf_cache = folder_paths["pdf_cache"]
        docx_copy = folder_paths["docx_copy"]

        if is_word_available():
            # ── Word COM : séquentiel avec instance unique (plus rapide) ──────
            with WordConverter() as wc:
                for path in docx_to_convert:
                    if not _index_state["running"]:
                        return
                    wc.convert(path, pdf_cache, docx_copy)
                    with _index_lock:
                        _index_state["conv_done"] += 1
                        _index_state["current"] = os.path.basename(path)
                    # Always queue for phase 2: index_file will use cached PDF or
                    # fall back to LibreOffice if Word COM failed on this file.
                    pdf_ready.append(path)
        else:
            # ── LibreOffice : parallèle avec profils isolés ───────────────────
            lo_workers = min(2, len(docx_to_convert))

            def _convert(path):
                return path, convert_docx_to_pdf(path, pdf_cache, docx_copy)

            with ThreadPoolExecutor(max_workers=lo_workers) as executor:
                futures = {executor.submit(_convert, p): p for p in docx_to_convert}
                for future in as_completed(futures):
                    if not _index_state["running"]:
                        executor.shutdown(wait=False, cancel_futures=True)
                        return
                    path = futures[future]
                    try:
                        future.result()
                    except RuntimeError as e:
                        with _index_lock:
                            _index_state["error"] = str(e)
                            _index_state["running"] = False
                        _persist_status(running=False, error=str(e), finished_at=timezone.now())
                        executor.shutdown(wait=False, cancel_futures=True)
                        return
                    except Exception:
                        pass
                    with _index_lock:
                        _index_state["conv_done"] += 1
                        _index_state["current"] = os.path.basename(path)
                    # Always queue for phase 2 (same reason as above)
                    pdf_ready.append(path)

    pdf_ready.extend(pdf_direct)

    with _index_lock:
        _index_state["phase"] = "indexing"

    # ── Phase 2 : extract text + FTS5 insert in parallel ─────────────────────
    workers = min(8, os.cpu_count() or 4, max(1, len(pdf_ready)))

    def index_one(path):
        from .services.index import index_file as _index_file
        return _index_file(path, db_file, _get_folder_paths(folder)["pdf_cache"])

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(index_one, p): p for p in pdf_ready}
        for future in as_completed(futures):
            if not _index_state["running"]:
                executor.shutdown(wait=False, cancel_futures=True)
                break
            path = futures[future]
            try:
                success = future.result()
            except Exception:
                success = False
            with _index_lock:
                _index_state["done"] += 1
                _index_state["current"] = os.path.basename(path)
                if success:
                    _index_state["newly_indexed"] += 1
                else:
                    _index_state["failed"] += 1

    with _index_lock:
        _index_state["running"] = False
    # Invalider le cache summary pour ce dossier
    _summary_cache.clear()
    _persist_status(
        running=False,
        done=_index_state["done"],
        newly_indexed=_index_state["newly_indexed"],
        failed=_index_state["failed"],
        current=_index_state["current"],
        finished_at=timezone.now(),
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _encode_path(path: str) -> str:
    return base64.urlsafe_b64encode(path.encode("utf-8")).decode()


def _decode_path(encoded: str) -> str:
    return base64.urlsafe_b64decode(encoded.encode()).decode("utf-8")


def _highlight_context(context: str) -> str:
    """Replace [term] markers with <mark> tags for HTML display."""
    safe = context.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\[([^\]]+)\]", r'<mark>\1</mark>', safe)


_summary_cache: dict = {}  # (folder, recurse, db_file) → (timestamp, result)
_SUMMARY_TTL = 30  # seconds


def _get_index_summary(folder: str, recurse: bool, db_file: str) -> dict:
    import time
    key = (folder, recurse, db_file)
    now = time.monotonic()
    cached = _summary_cache.get(key)
    if cached and now - cached[0] < _SUMMARY_TTL:
        return cached[1]
    files = collect_files(folder, recurse)
    if not files:
        result = {"total": 0, "indexed": 0}
    else:
        conn = get_db(db_file)
        indexed = sum(1 for f in files if is_indexed(conn, f))
        conn.close()
        result = {"total": len(files), "indexed": indexed}
    _summary_cache[key] = (now, result)
    return result


# ── Views ────────────────────────────────────────────────────────────────────

@login_required
def index_view(request):
    cfg = load_config()
    recurse = cfg.get("recurse", True)
    from django.db.models import Prefetch
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


@login_required
@require_POST
def search_view(request):
    folder = request.POST.get("folder", "").strip()
    terms_raw = request.POST.get("terms", "").strip()
    case_sensitive = request.POST.get("case_sensitive") == "on"
    whole_word = request.POST.get("whole_word") == "on"
    recurse = request.POST.get("recurse", "on") == "on"

    def error(msg):
        return render(request, "search_tool/_results.html",
                      {"error": msg, "results": []})

    if not folder or not os.path.isdir(folder):
        return error("Dossier invalide.")
    if not terms_raw:
        return error("Entrez au moins un terme.")

    terms, mode = parse_query(terms_raw)
    if not terms:
        return render(request, "search_tool/_results.html", {"results": []})

    short = [t for t in terms if len(t) < 3]
    if short:
        return error(f"Terme trop court (3 caractères minimum) : {', '.join(short)}")

    cfg = load_config()
    cfg["folder"] = folder
    cfg["recurse"] = recurse
    save_config(cfg)

    files = collect_files(folder, recurse)

    # FTS5 pre-filter
    fpaths = _get_folder_paths(folder)
    db_file = fpaths["db"]
    conn = get_db(db_file)
    indexed_set = {f for f in files if is_indexed(conn, f)}
    conn.close()

    fts_results = fts_search(terms, mode, case_sensitive, db_file)
    fts_matched = {r["file"] for r in fts_results} & indexed_set
    not_indexed = [f for f in files if f not in indexed_set]
    to_search = [f for f in files if f in fts_matched] + not_indexed

    all_results = []
    if to_search:
        workers = min(8, os.cpu_count() or 4, max(1, len(to_search)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    search_file, path, terms,
                    case_sensitive, whole_word, mode,
                    fpaths["pdf_cache"],
                ): path
                for path in to_search
            }
            for future in as_completed(futures):
                path = futures[future]
                try:
                    results = future.result()
                except Exception as e:
                    results = [{"file": path, "term": "ERREUR",
                                "context": str(e), "page": None}]
                all_results.extend(results)

    # Enrich results for template
    folder_encoded = _encode_path(folder)
    for r in all_results:
        r["filename"] = os.path.basename(r["file"])
        r["file_encoded"] = _encode_path(r["file"])
        r["folder_encoded"] = folder_encoded
        r["context_html"] = _highlight_context(r["context"])

    return render(request, "search_tool/_results.html", {
        "results": all_results,
        "total_files": len(files),
    })


@login_required
@require_POST
def start_index(request):
    global _index_state
    folder = request.POST.get("folder", "").strip()
    recurse = request.POST.get("recurse", "true") == "true"

    if not folder or not os.path.isdir(folder):
        return JsonResponse({"error": "Dossier invalide."}, status=400)

    db_file = _get_folder_paths(folder)["db"]

    with _index_lock:
        if _index_state["running"]:
            return JsonResponse({"error": "Indexation déjà en cours."}, status=409)
        _index_state = {
            "running": True,
            "phase": "",
            "conv_done": 0,
            "conv_total": 0,
            "done": 0,
            "total": 0,
            "current": "",
            "newly_indexed": 0,
            "failed": 0,
            "error": None,
            "folder": folder,
        }

    thread = threading.Thread(target=_run_indexing, args=(folder, recurse, db_file), daemon=True)
    thread.start()
    return JsonResponse({"started": True})


@login_required
@require_POST
def stop_index(request):
    with _index_lock:
        if _index_state["running"]:
            _index_state["running"] = False
    return JsonResponse({"stopped": True})


@login_required
@require_GET
def index_status(request):
    with _index_lock:
        state = dict(_index_state)
    return JsonResponse(state)


@login_required
@require_GET
def index_summary(request):
    """Return current indexed/total counts for a folder (used to refresh the badge)."""
    folder = request.GET.get("folder", "").strip()
    recurse = request.GET.get("recurse", "true") == "true"
    if not folder or not os.path.isdir(folder):
        return JsonResponse({"total": 0, "indexed": 0})
    db_file = _get_folder_paths(folder)["db"]
    summary = _get_index_summary(folder, recurse, db_file)
    return JsonResponse(summary)


@login_required
@require_GET
def index_unindexed(request):
    """Return the list of files that could not be indexed."""
    folder = request.GET.get("folder", "").strip()
    recurse = request.GET.get("recurse", "true") == "true"
    if not folder or not os.path.isdir(folder):
        return JsonResponse({"files": []})
    files = collect_files(folder, recurse)
    db_file = _get_folder_paths(folder)["db"]
    conn = get_db(db_file)
    unindexed = [f for f in files if not is_indexed(conn, f)]
    conn.close()
    return JsonResponse({"files": [os.path.basename(f) for f in unindexed],
                         "paths": unindexed})


@login_required
def serve_pdf(request):
    encoded = request.GET.get("path", "")
    folder_encoded = request.GET.get("folder", "")
    term = request.GET.get("term", "").strip()
    try:
        page_num = int(request.GET.get("page", 1))
    except ValueError:
        page_num = 1

    try:
        original_path = _decode_path(encoded)
        folder = _decode_path(folder_encoded) if folder_encoded else ""
    except Exception:
        return HttpResponseNotFound()

    pdf_cache_dir = _get_folder_paths(folder)["pdf_cache"] if folder else settings.PDF_CACHE_DIR

    ext = os.path.splitext(original_path)[1].lower()
    if ext == ".pdf":
        serve_path = original_path
    elif ext == ".docx":
        serve_path = get_pdf_cache_path(original_path, pdf_cache_dir)
    else:
        return HttpResponseNotFound()

    if not os.path.exists(serve_path):
        return HttpResponseNotFound("Fichier non trouvé. Indexez le dossier d'abord.")

    if not term:
        return FileResponse(open(serve_path, "rb"), content_type="application/pdf")

    # Annotate highlights in memory, then redirect browser to the right page.
    doc = fitz.open(serve_path)
    page_idx = max(0, page_num - 1)
    for idx in range(len(doc)):
        page = doc[idx]
        areas = page.search_for(term, quads=False)
        for rect in areas:
            annot = page.add_highlight_annot(rect)
            annot.set_colors(stroke=(1, 0.85, 0))  # yellow
            annot.update()

    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True)
    doc.close()
    buf.seek(0)

    response = HttpResponse(buf.read(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="{os.path.basename(serve_path)}"'
    )
    return response


def _list_drives():
    """Return available Windows drive letters (e.g. ['C:\\', 'I:\\'])."""
    import string
    return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]


@login_required
@require_GET
def browse_dir(request):
    path = request.GET.get("path", "").strip()

    # Empty path → show drive list
    if not path:
        drives = _list_drives()
        entries = [{"name": d.rstrip("\\"), "path": d} for d in drives]
        return JsonResponse({"path": "", "entries": entries, "drives": True})

    path = os.path.normpath(path)
    if not os.path.isdir(path):
        drives = _list_drives()
        entries = [{"name": d.rstrip("\\"), "path": d} for d in drives]
        return JsonResponse({"path": "", "entries": entries, "drives": True})

    entries = []
    parent = os.path.dirname(path)
    # At drive root (e.g. C:\), parent == path → go back to drive list
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

    return JsonResponse({"path": path, "entries": entries, "drives": False})


@login_required
@require_POST
def add_favorite(request):
    folder = request.POST.get("folder", "").strip()
    if not folder or not os.path.isdir(folder):
        return redirect("index")
    name = os.path.basename(folder) or folder
    Favorite.objects.get_or_create(user=request.user, path=folder,
                                   defaults={"name": name})
    return redirect("index")


@login_required
@require_POST
def remove_favorite(request):
    path = request.POST.get("path", "").strip()
    Favorite.objects.filter(user=request.user, path=path).delete()
    return redirect("index")


@login_required
@require_POST
def rename_favorite(request):
    path = request.POST.get("path", "").strip()
    name = request.POST.get("name", "").strip()
    if not path or not name:
        return JsonResponse({"error": "invalid"}, status=400)
    Favorite.objects.filter(user=request.user, path=path).update(name=name)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def create_group(request):
    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Nom requis"}, status=400)
    FavoriteGroup.objects.get_or_create(user=request.user, name=name)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def delete_group(request):
    group_id = request.POST.get("group_id", "").strip()
    FavoriteGroup.objects.filter(user=request.user, pk=group_id).delete()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def rename_group(request):
    group_id = request.POST.get("group_id", "").strip()
    name = request.POST.get("name", "").strip()
    if not group_id or not name:
        return JsonResponse({"error": "invalid"}, status=400)
    FavoriteGroup.objects.filter(user=request.user, pk=group_id).update(name=name)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def move_favorite(request):
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
