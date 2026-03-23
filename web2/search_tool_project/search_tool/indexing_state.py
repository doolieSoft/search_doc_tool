"""
Global indexing state shared between StartIndexView, StopIndexView, and IndexStatusView.

The in-memory dict _index_state is intentionally module-level (global) because:
- Django runs in a single process with multiple threads
- The background thread needs to update it while request threads read it
- A per-request object would not work for this use case

The DB singleton (IndexingStatus pk=1) persists state across server restarts.
"""
import hashlib
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


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

_STALE_SECONDS = 30  # job with last_ping older than this is considered dead
_summary_cache: dict = {}  # (folder, recurse, db_file) → (timestamp, result)
_SUMMARY_TTL = 30  # seconds


# ── DB persistence helpers ────────────────────────────────────────────────────

def persist_status(**kwargs) -> None:
    """Write key fields to the DB singleton (pk=1). Non-blocking best-effort."""
    try:
        from .models import IndexingStatus
        IndexingStatus.objects.update_or_create(pk=1, defaults=kwargs)
    except Exception:
        pass  # never crash the indexing thread over a DB write


def ping_db(stop_event: threading.Event, interval: int = 5) -> None:
    """Keep last_ping fresh while indexing. Runs in a daemon thread."""
    from django.utils import timezone
    while not stop_event.wait(interval):
        try:
            from .models import IndexingStatus
            IndexingStatus.objects.filter(pk=1).update(last_ping=timezone.now())
        except Exception:
            pass


def is_stale() -> bool:
    """Return True if the DB shows running=True but last_ping is too old."""
    try:
        from django.utils import timezone
        from .models import IndexingStatus
        status = IndexingStatus.objects.filter(pk=1).first()
        if not status or not status.running:
            return True
        if status.last_ping is None:
            return True
        return (timezone.now() - status.last_ping).total_seconds() > _STALE_SECONDS
    except Exception:
        return False


def reset_running_on_startup() -> None:
    """Called at module load: any running=True in DB means the thread is dead."""
    try:
        from .models import IndexingStatus
        IndexingStatus.objects.filter(pk=1, running=True).update(
            running=False, error="Interrompu (redémarrage serveur)"
        )
    except Exception:
        pass


# ── Folder path helpers ───────────────────────────────────────────────────────

def get_folder_paths(folder: str, data_dir: str) -> dict:
    """Return all per-folder data paths (db, pdf_cache, docx_copy), creating dirs as needed."""
    normalized = os.path.normpath(folder).lower()
    folder_hash = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:10]
    folder_name = re.sub(r"[^\w\-]", "_", os.path.basename(normalized) or "root")
    base_dir = Path(data_dir) / "folders" / f"{folder_name}_{folder_hash}"
    base_dir.mkdir(parents=True, exist_ok=True)
    return {
        "db":         str(base_dir / "index.db"),
        "pdf_cache":  str(base_dir / "pdf_cache"),
        "docx_copy":  str(base_dir / "docx_copy"),
    }


# ── Index summary cache ───────────────────────────────────────────────────────

def get_index_summary(folder: str, recurse: bool, db_file: str,
                      collect_files_fn, index_service) -> dict:
    key = (folder, recurse, db_file)
    now = time.monotonic()
    cached = _summary_cache.get(key)
    if cached and now - cached[0] < _SUMMARY_TTL:
        return cached[1]
    files = collect_files_fn(folder, recurse)
    if not files:
        result = {"total": 0, "indexed": 0}
    else:
        conn = index_service.get_db()
        indexed = sum(1 for f in files if index_service.is_indexed(conn, f))
        conn.close()
        result = {"total": len(files), "indexed": indexed}
    _summary_cache[key] = (now, result)
    return result


# ── Background indexing ───────────────────────────────────────────────────────

def run_indexing(folder: str, recurse: bool, db_file: str, data_dir: str) -> None:
    """
    Two-phase indexing:
    1. Convert DOCX → PDF (Word COM if available, else LibreOffice)
    2. Extract text + insert into FTS5 in parallel

    A ping thread keeps last_ping fresh every 5 s so stale detection works.
    A try/finally guarantees running=False even on unexpected exceptions.
    """
    global _index_state
    from django.utils import timezone
    from .services.converter_service import ConverterService
    from .services.index_service import IndexService
    from .services.search_service import SearchService

    converter = ConverterService()
    index_svc = IndexService(db_file)
    search_svc = SearchService(converter=converter)

    ping_stop = threading.Event()
    ping_thread = threading.Thread(target=ping_db, args=(ping_stop,), daemon=True)
    ping_thread.start()

    try:
        files = search_svc.collect_files(folder, recurse)
        conn = index_svc.get_db()
        to_index = [f for f in files if not index_svc.is_indexed(conn, f)]
        conn.close()

        docx_to_convert = [p for p in to_index if p.lower().endswith(".docx")]
        pdf_direct = [p for p in to_index if not p.lower().endswith(".docx")]
        total = len(to_index)

        with _index_lock:
            _index_state.update({
                "total": total, "done": 0, "newly_indexed": 0, "failed": 0,
                "current": "", "phase": "converting" if docx_to_convert else "indexing",
                "conv_done": 0, "conv_total": len(docx_to_convert),
            })
        persist_status(folder=folder, running=True, total=total, done=0,
                       newly_indexed=0, failed=0, current="", error=None,
                       started_at=timezone.now(), finished_at=None)

        if not to_index:
            return  # finally handles cleanup

        # ── Phase 1 : DOCX → PDF ─────────────────────────────────────────────
        pdf_ready = []

        if docx_to_convert:
            folder_paths = get_folder_paths(folder, data_dir)
            pdf_cache = folder_paths["pdf_cache"]
            docx_copy = folder_paths["docx_copy"]

            if ConverterService.is_word_available():
                with ConverterService.WordConverter() as wc:
                    for path in docx_to_convert:
                        if not _index_state["running"]:
                            return
                        wc.convert(path, pdf_cache, docx_copy)
                        with _index_lock:
                            _index_state["conv_done"] += 1
                            _index_state["current"] = os.path.basename(path)
                        pdf_ready.append(path)
            else:
                lo_workers = min(2, len(docx_to_convert))

                def _convert(path):
                    return path, converter.convert_docx_to_pdf(path, pdf_cache, docx_copy)

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
                            executor.shutdown(wait=False, cancel_futures=True)
                            return  # finally handles cleanup
                        except Exception:
                            pass
                        with _index_lock:
                            _index_state["conv_done"] += 1
                            _index_state["current"] = os.path.basename(path)
                        pdf_ready.append(path)

        pdf_ready.extend(pdf_direct)

        with _index_lock:
            _index_state["phase"] = "indexing"

        # ── Phase 2 : FTS5 indexing ───────────────────────────────────────────
        workers = min(8, os.cpu_count() or 4, max(1, len(pdf_ready)))
        folder_paths = get_folder_paths(folder, data_dir)

        def index_one(path):
            svc = IndexService(db_file)
            return svc.index_file(path, folder_paths["pdf_cache"])

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

    except Exception as e:
        with _index_lock:
            if not _index_state.get("error"):
                _index_state["error"] = str(e)

    finally:
        ping_stop.set()
        with _index_lock:
            _index_state["running"] = False
        _summary_cache.clear()
        try:
            from django.utils import timezone
            persist_status(
                running=False,
                done=_index_state["done"],
                newly_indexed=_index_state["newly_indexed"],
                failed=_index_state["failed"],
                current=_index_state.get("current", ""),
                error=_index_state.get("error"),
                finished_at=timezone.now(),
            )
        except Exception:
            pass
