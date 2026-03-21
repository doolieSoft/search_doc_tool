import os
import time

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QFileDialog,
    QTableView, QHeaderView, QAbstractItemView, QStatusBar,
    QSizePolicy, QFrame, QProgressBar,
)
from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtGui import QColor

from ..core.config import load_config, save_config, load_favorites, save_favorites
from ..core.index import get_db, is_indexed
from ..core.search import parse_query, collect_files
from ..core.extractor import HAS_DOCX, HAS_PDF
from .styles import (
    ICON_PNG_B64, TEXT_MUTED, TEXT_PRIMARY, HIGHLIGHT, GREEN, RED,
    BG_INPUT, BG_PANEL, BG_ROW_SEL, BORDER, ACCENT, ACCENT_DARK
)
from .model import ResultsModel, ContextDelegate
from .workers import IndexWorker, SearchWorker


class SearchApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Recherche dans Word / PDF")
        self.resize(1200, 750)
        self._worker: SearchWorker | None = None
        self._idx_worker: IndexWorker | None = None
        self._model = ResultsModel()
        self._build_ui()
        self._load_config()
        self._update_index_label()
        self._set_icon()
        self.inp_terms.setFocus()

    def _set_icon(self):
        import base64
        from PyQt6.QtGui import QPixmap, QIcon
        from PyQt6.QtCore import QByteArray
        data = QByteArray(base64.b64decode(ICON_PNG_B64))
        pix = QPixmap()
        pix.loadFromData(data, "PNG")
        self.setWindowIcon(QIcon(pix))
        QApplication.instance().setWindowIcon(QIcon(pix))

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # ── Dossier ──────────────────────────────────────────────────────────
        row_folder = QHBoxLayout()
        row_folder.setSpacing(8)
        lbl_folder = QLabel("Dossier")
        lbl_folder.setFixedWidth(56)
        lbl_folder.setStyleSheet(f"color:{TEXT_MUTED}; font-size:12px;")
        self.inp_folder = QLineEdit()
        self.inp_folder.setPlaceholderText("Chemin du dossier à analyser…")
        btn_browse = QPushButton("Parcourir")
        btn_browse.setObjectName("btn_browse")
        btn_browse.setFixedWidth(100)
        btn_browse.clicked.connect(self._browse)
        row_folder.addWidget(lbl_folder)
        row_folder.addWidget(self.inp_folder)
        row_folder.addWidget(btn_browse)
        btn_add_fav = QPushButton("★")
        btn_add_fav.setToolTip("Ajouter ce dossier aux favoris")
        btn_add_fav.setFixedWidth(32)
        btn_add_fav.setStyleSheet(
            f"color: {HIGHLIGHT}; font-size:16px; border:1px solid {BORDER}; "
            f"border-radius:6px; background:{BG_INPUT};"
        )
        btn_add_fav.clicked.connect(self._add_favorite)
        row_folder.addWidget(btn_add_fav)
        root.addLayout(row_folder)

        # ── Favoris ───────────────────────────────────────────────────────────
        self.fav_frame = QWidget()
        self.fav_frame.setStyleSheet("background: transparent;")
        self.fav_layout = QHBoxLayout(self.fav_frame)
        self.fav_layout.setContentsMargins(0, 0, 0, 0)
        self.fav_layout.setSpacing(6)
        fav_label = QLabel("Favoris :")
        fav_label.setStyleSheet(f"color:{TEXT_MUTED}; font-size:12px;")
        fav_label.setFixedWidth(56)
        self.fav_layout.addWidget(fav_label)
        self.fav_layout.addStretch()
        root.addWidget(self.fav_frame)
        self._refresh_favorites()

        # ── Termes ───────────────────────────────────────────────────────────
        row_terms = QHBoxLayout()
        row_terms.setSpacing(8)
        lbl_terms = QLabel("Termes")
        lbl_terms.setFixedWidth(56)
        lbl_terms.setStyleSheet(f"color:{TEXT_MUTED}; font-size:12px;")
        self.inp_terms = QLineEdit()
        self.inp_terms.setPlaceholderText('espace = OR   +  = AND   "..." = expression exacte')
        self.inp_terms.returnPressed.connect(self._start_search)
        hint = QLabel('espace=OR  +  =AND  "…"=exact')
        hint.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
        hint.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row_terms.addWidget(lbl_terms)
        row_terms.addWidget(self.inp_terms)
        row_terms.addWidget(hint)
        root.addLayout(row_terms)

        # ── Options ───────────────────────────────────────────────────────────
        row_opts = QHBoxLayout()
        row_opts.setSpacing(20)
        self.chk_case    = QCheckBox("Respecter la casse")
        self.chk_word    = QCheckBox("Mot entier")
        self.chk_recurse = QCheckBox("Sous-dossiers")
        self.chk_recurse.setChecked(True)
        for chk in (self.chk_case, self.chk_word, self.chk_recurse):
            row_opts.addWidget(chk)
        row_opts.addStretch()
        root.addLayout(row_opts)

        # ── Boutons ───────────────────────────────────────────────────────────
        row_btns = QHBoxLayout()
        row_btns.setSpacing(10)
        self.btn_search = QPushButton("🔍  Lancer la recherche")
        self.btn_search.setObjectName("btn_search")
        self.btn_search.clicked.connect(self._start_search)
        self.btn_stop = QPushButton("⏹  Stopper")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_search)
        self.btn_index = QPushButton("⚙  Indexer le dossier")
        self.btn_index.setStyleSheet(f"""
            QPushButton {{
                background:{BG_INPUT}; border:1px solid {BORDER};
                border-radius:6px; padding:8px 16px; color:{TEXT_MUTED};
            }}
            QPushButton:hover {{ background:{BORDER}; color:{TEXT_PRIMARY}; }}
            QPushButton:disabled {{ color:#444; }}
        """)
        self.btn_index.clicked.connect(self._start_index)
        btn_clear = QPushButton("Effacer")
        btn_clear.clicked.connect(self._clear)
        btn_export = QPushButton("Exporter CSV")
        btn_export.clicked.connect(self._export_csv)
        for b in (self.btn_search, self.btn_stop, self.btn_index, btn_clear, btn_export):
            row_btns.addWidget(b)
        self.lbl_index = QLabel("")
        self.lbl_index.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px; padding-left:8px;")
        row_btns.addWidget(self.lbl_index)
        row_btns.addStretch()
        root.addLayout(row_btns)

        # ── Barre de progression ──────────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.hide()
        root.addWidget(self.progress)

        # ── Séparateur ────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # ── Tableau ───────────────────────────────────────────────────────────
        self.table = QTableView()
        self.table.setModel(self._model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 130)
        self.table.setItemDelegateForColumn(2, ContextDelegate())
        self.table.doubleClicked.connect(self._open_file)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table)

        # ── Status bar ────────────────────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Prêt.")

    # ── Config ───────────────────────────────────────────────────────────────
    def _load_config(self):
        cfg = load_config()
        if cfg.get("folder"):
            self.inp_folder.setText(cfg["folder"])

    # ── Favoris ──────────────────────────────────────────────────────────────
    def _add_favorite(self):
        folder = self.inp_folder.text().strip()
        if not folder or not os.path.isdir(folder):
            self.status.showMessage("⚠  Dossier invalide.")
            return
        favs = load_favorites()
        if not any(f["path"] == folder for f in favs):
            name = os.path.basename(folder) or folder
            favs.append({"path": folder, "name": name})
            save_favorites(favs)
            self._refresh_favorites()
            self.status.showMessage(f"Favori ajouté : {name}")
        else:
            self.status.showMessage("Ce dossier est déjà dans les favoris.")

    def _refresh_favorites(self):
        while self.fav_layout.count() > 2:
            item = self.fav_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        favs = load_favorites()
        for fav in favs:
            name = fav["name"]
            path = fav["path"]
            btn = QPushButton(f"📁 {name}")
            btn.setToolTip(path)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {BG_INPUT}; border: 1px solid {BORDER};
                    border-radius: 5px; padding: 3px 10px;
                    color: {TEXT_PRIMARY}; font-size: 12px;
                }}
                QPushButton:hover {{ background: {BORDER}; }}
            """)
            btn.clicked.connect(lambda checked, p=path: self._use_favorite(p))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, f=fav, b=btn: self._fav_context_menu(f, b))
            self.fav_layout.insertWidget(self.fav_layout.count() - 1, btn)
        self.fav_frame.setVisible(bool(favs))

    def _use_favorite(self, path: str):
        self.inp_folder.setText(path)
        cfg = load_config()
        cfg["folder"] = path
        save_config(cfg)
        self.status.showMessage(f"Dossier : {path}")
        self._update_index_label()

    def _fav_context_menu(self, fav: dict, btn):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background:{BG_PANEL}; border:1px solid {BORDER}; color:{TEXT_PRIMARY}; }}
            QMenu::item:selected {{ background:{BG_ROW_SEL}; }}
            QMenu::item {{ padding: 5px 20px; }}
        """)
        menu.addAction("✏️  Renommer").triggered.connect(lambda: self._rename_favorite(fav))
        menu.addAction("🗑  Supprimer").triggered.connect(lambda: self._remove_favorite(fav))
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _rename_favorite(self, fav: dict):
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "Renommer le favori", "Nouveau nom :", text=fav["name"])
        if ok and new_name.strip():
            favs = load_favorites()
            for f in favs:
                if f["path"] == fav["path"]:
                    f["name"] = new_name.strip()
                    break
            save_favorites(favs)
            self._refresh_favorites()
            self.status.showMessage(f"Favori renommé : {new_name.strip()}")

    def _remove_favorite(self, fav: dict):
        favs = [f for f in load_favorites() if f["path"] != fav["path"]]
        save_favorites(favs)
        self._refresh_favorites()
        self.status.showMessage("Favori supprimé.")

    # ── Actions ───────────────────────────────────────────────────────────────
    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier")
        if folder:
            self.inp_folder.setText(folder)
            cfg = load_config()
            cfg["folder"] = folder
            save_config(cfg)

    def _clear(self):
        self._model.clear()
        self.status.showMessage("Prêt.")

    def _start_search(self):
        folder = self.inp_folder.text().strip()
        terms_raw = self.inp_terms.text().strip()

        if not folder or not os.path.isdir(folder):
            self.status.showMessage("⚠  Dossier invalide.")
            return
        if not terms_raw:
            self.status.showMessage("⚠  Entrez au moins un terme.")
            return
        if not HAS_DOCX and not HAS_PDF:
            self.status.showMessage("⚠  Installez python-docx et pymupdf.")
            return

        terms, mode = parse_query(terms_raw)
        if not terms:
            return
        short = [t for t in terms if len(t) < 3]
        if short:
            self.status.showMessage(
                f"⚠  Terme trop court (3 caractères minimum) : {', '.join(short)}")
            return

        cfg = load_config()
        cfg["folder"] = folder
        save_config(cfg)
        self._clear()
        self._search_start = time.perf_counter()
        self.btn_search.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.show()
        self.progress.setRange(0, 0)

        self._worker = SearchWorker(
            folder, terms,
            self.chk_case.isChecked(),
            self.chk_word.isChecked(),
            self.chk_recurse.isChecked(),
            mode,
        )
        self._worker.result_found.connect(self._on_result)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _stop_search(self):
        if self._worker:
            self._worker.stop()
        self.status.showMessage("Arrêt en cours…")

    def _start_index(self):
        folder = self.inp_folder.text().strip()
        if not folder or not os.path.isdir(folder):
            self.status.showMessage("⚠  Dossier invalide.")
            return
        self.btn_index.setEnabled(False)
        self.btn_search.setEnabled(False)
        self.progress.show()
        self.progress.setRange(0, 0)
        self._idx_worker = IndexWorker(folder, self.chk_recurse.isChecked())
        self._idx_worker.progress.connect(self._on_index_progress)
        self._idx_worker.finished.connect(self._on_index_finished)
        self._idx_worker.start()
        self.status.showMessage("Indexation en cours…")

    def _on_index_progress(self, done: int, total: int, filename: str):
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.status.showMessage(f"Indexation {done}/{total} : {filename}")

    def _on_index_finished(self, indexed: int, total: int, total_indexed: int):
        self.btn_index.setEnabled(True)
        self.btn_search.setEnabled(True)
        self.progress.hide()
        self.progress.setRange(0, 0)
        if indexed == 0:
            self.status.showMessage(f"Index à jour — {total} fichier(s) déjà indexé(s).")
        else:
            self.status.showMessage(f"{indexed} fichier(s) indexé(s) sur {total}.")
        if total_indexed == total:
            self.lbl_index.setText(f"✅ Index à jour ({total} fichiers)")
            self.lbl_index.setStyleSheet(f"color:{GREEN}; font-size:11px; padding-left:8px;")
        else:
            self.lbl_index.setText(f"⚠ {total_indexed}/{total} indexés")
            self.lbl_index.setStyleSheet(f"color:{HIGHLIGHT}; font-size:11px; padding-left:8px;")

    def _update_index_label(self):
        folder = self.inp_folder.text().strip()
        if not folder or not os.path.isdir(folder):
            self.lbl_index.setText("")
            return
        files = collect_files(folder, self.chk_recurse.isChecked())
        if not files:
            self.lbl_index.setText("")
            return
        conn = get_db()
        indexed = sum(1 for f in files if is_indexed(conn, f))
        conn.close()
        total = len(files)
        if indexed == total:
            self.lbl_index.setText(f"✅ Index à jour ({total} fichiers)")
            self.lbl_index.setStyleSheet(f"color:{GREEN}; font-size:11px; padding-left:8px;")
        else:
            self.lbl_index.setText(f"⚠ {indexed}/{total} indexés")
            self.lbl_index.setStyleSheet(f"color:{HIGHLIGHT}; font-size:11px; padding-left:8px;")

    def _on_result(self, r: dict):
        self._model.add_result(r)

    def _on_progress(self, idx: int, total: int, filename: str):
        self.status.showMessage(f"Analyse {idx}/{total} : {filename}")

    def _on_finished(self, count: int, total: int):
        self.btn_search.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.hide()
        elapsed = time.perf_counter() - getattr(self, "_search_start", 0)
        elapsed_str = f"{elapsed:.2f}s" if elapsed >= 1 else f"{elapsed*1000:.0f}ms"
        self.status.showMessage(
            f"{count} occurrence(s) trouvée(s) dans {total} fichier(s) — {elapsed_str}")

    def _open_file(self, index: QModelIndex):
        r = self._model.get_row(index.row())
        path = r.get("file", "")
        page = r.get("page")
        ext = os.path.splitext(path)[1].lower()
        if not os.path.exists(path):
            return
        if ext == ".pdf" and page is not None:
            self._open_pdf_at_page(path, page)
        else:
            to_copy = r.get("ctrlf") or r.get("term", "").split(" + ")[0]
            if to_copy and r.get("term") != "ERREUR":
                QApplication.clipboard().setText(to_copy)
                self.status.showMessage("Extrait copié — faites Ctrl+F dans Word puis Ctrl+V")
            if os.name == "nt":
                os.startfile(path)
            else:
                os.system(f'xdg-open "{path}"')

    def _open_pdf_at_page(self, path: str, page: int):
        if os.name == "nt":
            import subprocess
            sumatra_paths = [
                r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
                r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
                os.path.expanduser(r"~\AppData\Local\SumatraPDF\SumatraPDF.exe"),
            ]
            for sumatra in sumatra_paths:
                if os.path.exists(sumatra):
                    subprocess.Popen([sumatra, "-page", str(page), path])
                    self.status.showMessage(f"PDF ouvert page {page}")
                    return
            acrobat_paths = [
                r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
                r"C:\Program Files (x86)\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
                r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
                r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
            ]
            for acrobat in acrobat_paths:
                if os.path.exists(acrobat):
                    subprocess.Popen([acrobat, "/A", f"page={page}", path])
                    self.status.showMessage(f"PDF ouvert page {page}")
                    return
            os.startfile(path)
            self.status.showMessage(
                f"Page {page} — installez SumatraPDF pour l'ouverture directe à la page")
        else:
            import subprocess
            for reader, arg in [("evince", f"--page-label={page}"),
                                 ("okular", f"--page={page - 1}"),
                                 ("zathura", f"-P {page}")]:
                if subprocess.run(["which", reader], capture_output=True).returncode == 0:
                    subprocess.Popen([reader, arg, path])
                    self.status.showMessage(f"PDF ouvert page {page}")
                    return
            os.system(f'xdg-open "{path}"')

    def _export_csv(self):
        results = self._model.all_results()
        if not results:
            self.status.showMessage("Aucun résultat à exporter.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer", "", "CSV (*.csv);;Tous (*.*)")
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["file", "term", "context"])
            writer.writeheader()
            writer.writerows(results)
        self.status.showMessage(f"Exporté : {path}")
