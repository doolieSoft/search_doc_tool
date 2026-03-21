import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QThread, pyqtSignal

from ..core.index import get_db, is_indexed, index_file, fts_search
from ..core.search import collect_files, search_file


class IndexWorker(QThread):
    """Thread d'indexation en arrière-plan."""
    progress = pyqtSignal(int, int, str)   # (done, total, filename)
    finished = pyqtSignal(int, int, int)   # (newly_indexed, total, total_indexed)

    def __init__(self, folder, recurse):
        super().__init__()
        self.folder = folder
        self.recurse = recurse
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        files = collect_files(self.folder, self.recurse)
        total = len(files)
        conn = get_db()
        to_index = [f for f in files if not is_indexed(conn, f)]
        conn.close()

        if not to_index:
            self.finished.emit(0, total, total)
            return

        done = 0
        indexed = 0
        workers = min(8, os.cpu_count() or 4, max(1, len(to_index)))

        def index_one(path):
            local_conn = get_db()
            result = False
            try:
                result = index_file(local_conn, path)
                if not result:
                    local_conn.execute("""
                        INSERT INTO files(path, mtime, indexed) VALUES (?,?,0)
                        ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime
                    """, (path, os.path.getmtime(path)))
                local_conn.commit()
            except Exception:
                pass
            finally:
                local_conn.close()
            return result

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(index_one, p): p for p in to_index}
            for future in as_completed(futures):
                if self._stop:
                    break
                done += 1
                path = futures[future]
                try:
                    if future.result():
                        indexed += 1
                except Exception:
                    pass
                self.progress.emit(done, len(to_index), os.path.basename(path))

        already_indexed = total - len(to_index)
        self.finished.emit(indexed, total, already_indexed + indexed)


class SearchWorker(QThread):
    result_found = pyqtSignal(dict)
    progress     = pyqtSignal(int, int, str)
    finished     = pyqtSignal(int, int)

    def __init__(self, folder, terms, case_sensitive, whole_word, recurse, mode):
        super().__init__()
        self.folder = folder
        self.terms = terms
        self.case_sensitive = case_sensitive
        self.whole_word = whole_word
        self.recurse = recurse
        self.mode = mode
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        files = collect_files(self.folder, self.recurse)
        total = len(files)
        count = 0

        conn = get_db()
        indexed_files = [f for f in files if is_indexed(conn, f)]
        not_indexed   = [f for f in files if f not in set(indexed_files)]
        conn.close()

        # ── 1. FTS5 : identifier rapidement quels fichiers indexés matchent ──
        fts_matched = set()
        if indexed_files:
            self.progress.emit(0, 1, "Recherche dans l'index FTS…")
            conn = get_db()
            fts_results = fts_search(conn, self.terms, self.mode, self.case_sensitive)
            conn.close()
            indexed_set = set(indexed_files)
            fts_matched = {r["file"] for r in fts_results if r["file"] in indexed_set}

        # ── 2. Regex sur les fichiers matchés + non indexés ──────────────────
        to_search = [f for f in indexed_files if f in fts_matched] + not_indexed
        if to_search and not self._stop:
            workers = min(8, os.cpu_count() or 4, max(1, len(to_search)))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        search_file, path, self.terms,
                        self.case_sensitive, self.whole_word, self.mode
                    ): path
                    for path in to_search
                }
                done = 0
                for future in as_completed(futures):
                    if self._stop:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    done += 1
                    path = futures[future]
                    self.progress.emit(done, len(to_search), os.path.basename(path))
                    try:
                        results = future.result()
                    except Exception as e:
                        results = [{"file": path, "term": "ERREUR",
                                    "context": str(e), "page": None, "ctrlf": ""}]
                    for r in results:
                        count += 1
                        self.result_found.emit(r)

        self.finished.emit(count, total)
