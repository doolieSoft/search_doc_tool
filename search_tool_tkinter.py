"""
Outil de recherche de termes dans fichiers Word (.docx) et PDF
Auteur : généré avec Claude
Usage  : python search_tool.py
Dépendances : pip install python-docx pymupdf
"""

import os
import re
import unicodedata
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".search_tool_config.json")

def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(data: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ── Imports optionnels ──────────────────────────────────────────────────────
try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import fitz  # PyMuPDF
    HAS_PDF = True
except ImportError:
    HAS_PDF = False


# ── Normalisation ──────────────────────────────────────────────────────────

def remove_accents(s: str) -> str:
    """Supprime les accents pour une comparaison insensible aux diacritiques."""
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')


# ── Parser de requête ────────────────────────────────────────────────────────

def parse_query(raw: str):
    """
    Syntaxe supportée :
      mot1 mot2            → OR sur chaque mot
      "expression exacte"  → recherche de l'expression complète (OR)
      mot1 + mot2          → AND (tous les termes doivent être présents)
      "expr" + mot         → AND avec expression exacte
    Retourne (terms: list[str], mode: str)  où mode = "OR" | "AND_DOC"
    """
    # Détecter AND : présence de "+" hors guillemets
    raw_no_quotes = re.sub(r'"[^"]+"', '', raw)
    mode = "AND_DOC" if '+' in raw_no_quotes else "OR"

    # Parser dans l'ordre d'apparition
    term_list = []
    i = 0
    while i < len(raw):
        if raw[i] == '"':
            end = raw.find('"', i + 1)
            if end != -1:
                phrase = raw[i + 1:end].strip()
                if phrase:
                    term_list.append(phrase)
                i = end + 1
            else:
                i += 1
        elif raw[i] in ('+', ',', ' '):
            i += 1
        else:
            end = i
            while end < len(raw) and raw[end] not in ('"', '+', ',', ' '):
                end += 1
            word = raw[i:end].strip()
            if word:
                term_list.append(word)
            i = end

    return term_list, mode


# ── Extraction de texte ──────────────────────────────────────────────────────

def extract_pages_docx(path: str) -> list[tuple[int, str]]:
    """Retourne le texte complet du document en un seul bloc."""
    doc = docx.Document(path)
    texts = []
    for para in doc.paragraphs:
        parts = [run.text for run in para.runs if run.text]
        full_para = re.sub(r'\s+', ' ', " ".join(parts)).strip()
        if full_para:
            texts.append(full_para)
    return [(1, " ".join(texts))] if texts else [(1, "")]



def extract_pages_pdf(path: str) -> list[tuple[int, str]]:
    """Retourne le texte complet du PDF en un seul bloc."""
    doc = fitz.open(path)
    text = " ".join(page.get_text() for page in doc)
    doc.close()
    return [(1, text)] if text.strip() else [(1, "")]


# ── Recherche ────────────────────────────────────────────────────────────────

def get_context(text: str, match: re.Match, window: int = 80) -> str:
    """Extrait ~window caractères autour du match, nettoyé."""
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    snippet = text[start:end].replace("\n", " ").strip()
    term_start = match.start() - start
    term_end = match.end() - start
    snippet = snippet[:term_start] + "[" + snippet[term_start:term_end] + "]" + snippet[term_end:]
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


def get_combined_context(text: str, matches: list, window: int = 80,
                          proximity_words: int = 30) -> str:
    """Pour AND : snippet englobant si termes proches, sinon snippets séparés par |"""
    if not matches:
        return ""
    if len(matches) == 1:
        return get_context(text, matches[0], window)
    matches = sorted(matches, key=lambda m: m.start())
    between = text[matches[0].end():matches[-1].start()]
    word_distance = len(between.split())
    if word_distance <= proximity_words:
        start = max(0, matches[0].start() - window)
        end = min(len(text), matches[-1].end() + window)
        snippet = text[start:end].replace("\n", " ").strip()
        offset = start
        for m in reversed(matches):
            ts = m.start() - offset
            te = m.end() - offset
            snippet = snippet[:ts] + "[" + snippet[ts:te] + "]" + snippet[te:]
        return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")
    else:
        return " | ".join(get_context(text, m, window) for m in matches)


def search_in_file(path: str, terms: list[str], case_sensitive: bool,
                   whole_word: bool) -> list[dict]:
    """Retourne la liste de résultats pour un fichier donné."""
    ext = os.path.splitext(path)[1].lower()
    results = []

    try:
        if ext == ".docx":
            if not HAS_DOCX:
                return []
            pages = extract_pages_docx(path)
        elif ext == ".pdf":
            if not HAS_PDF:
                return []
            pages = extract_pages_pdf(path)

        else:
            return []
    except Exception as e:
        return [{"file": path, "term": "ERREUR", "page": "-",
                 "context": str(e)}]

    flags = 0 if case_sensitive else re.IGNORECASE

    for term in terms:
        term_norm = remove_accents(term) if not case_sensitive else term
        words = re.split(r"\s+", term_norm.strip())
        escaped_words = [re.escape(w) for w in words]
        punct_gap = r"[\s\W]*"
        pattern_str = punct_gap.join(escaped_words)
        if whole_word:
            pattern_str = r"\b" + pattern_str + r"\b"
        try:
            pattern = re.compile(pattern_str, flags)
        except re.error:
            continue

        for pnum, text in pages:
            search_text = remove_accents(text) if not case_sensitive else text
            for match in pattern.finditer(search_text):
                results.append({
                    "file": path,
                    "term": term,
                                        "context": get_context(text, match),
                })

    return results



def search_in_file_and(path: str, terms: list[str], case_sensitive: bool,
                       whole_word: bool) -> list[dict]:
    """Version AND : une entrée par page où TOUS les termes sont présents, avec contexte combiné."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".docx":
            if not HAS_DOCX:
                return []
            pages = extract_pages_docx(path)
        elif ext == ".pdf":
            if not HAS_PDF:
                return []
            pages = extract_pages_pdf(path)
        else:
            return []
    except Exception as e:
        return [{"file": path, "term": "ERREUR", "page": "-", "context": str(e)}]

    flags = 0 if case_sensitive else re.IGNORECASE
    results = []

    for pnum, text in pages:
        search_text = remove_accents(text) if not case_sensitive else text
        page_matches = {}
        all_found = True
        for term in terms:
            term_norm = remove_accents(term) if not case_sensitive else term
            words = re.split(r"\s+", term_norm.strip())
            escaped_words = [re.escape(w) for w in words]
            pattern_str = r"[\s\W]*".join(escaped_words)
            if whole_word:
                pattern_str = r"\b" + pattern_str + r"\b"
            try:
                pattern = re.compile(pattern_str, flags)
            except re.error:
                all_found = False
                break
            ms = list(pattern.finditer(search_text))
            if not ms:
                all_found = False
                break
            page_matches[term] = ms
        if all_found:
            best_matches = [ms[0] for ms in page_matches.values()]
            results.append({
                "file": path,
                "term": " + ".join(terms),
                                "context": get_combined_context(text, best_matches),
            })

    return results

# ── Interface graphique ──────────────────────────────────────────────────────

class SearchApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Recherche dans Word / PDF")
        self.geometry("1100x700")
        self.minsize(800, 500)
        self.configure(bg="#F0F4F8")
        self._stop_event = threading.Event()
        self._build_ui()

    # ── Construction de l'interface ──────────────────────────────────────────

    def _build_ui(self):
        PAD = {"padx": 10, "pady": 6}

        # ── Cadre supérieur (paramètres) ─────────────────────────────────────
        top = tk.Frame(self, bg="#F0F4F8")
        top.pack(fill="x", **PAD)

        # Dossier
        tk.Label(top, text="Dossier :", bg="#F0F4F8", font=("Segoe UI", 10)
                 ).grid(row=0, column=0, sticky="w")
        self.folder_var = tk.StringVar()
        tk.Entry(top, textvariable=self.folder_var, width=55,
                 font=("Segoe UI", 10)).grid(row=0, column=1, sticky="ew", padx=(4, 4))
        # Charger le dossier sauvegardé
        cfg = load_config()
        if cfg.get("folder"):
            self.folder_var.set(cfg["folder"])
        tk.Button(top, text="Parcourir…", command=self._browse_folder,
                  font=("Segoe UI", 10), bg="#4A90D9", fg="white",
                  relief="flat", padx=8).grid(row=0, column=2)

        # Termes
        tk.Label(top, text="Termes :", bg="#F0F4F8", font=("Segoe UI", 10)
                 ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.terms_var = tk.StringVar()
        terms_entry = tk.Entry(top, textvariable=self.terms_var, width=55,
                 font=("Segoe UI", 10))
        terms_entry.grid(row=1, column=1, sticky="ew", padx=(4, 4), pady=(8, 0))
        terms_entry.bind("<Return>", lambda e: self._start_search())
        tk.Label(top, text='espace=OR  +  =AND  "..."=exact',
                 bg="#F0F4F8", font=("Segoe UI", 9), fg="#666").grid(row=1, column=2,
                                                                      sticky="w", pady=(8, 0))



        # Options
        opts = tk.Frame(self, bg="#F0F4F8")
        opts.pack(fill="x", padx=10, pady=(2, 6))
        self.case_var = tk.BooleanVar(value=False)
        self.word_var = tk.BooleanVar(value=False)
        self.recurse_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text="Respecter la casse", variable=self.case_var,
                       bg="#F0F4F8", font=("Segoe UI", 10)).pack(side="left")
        tk.Checkbutton(opts, text="Mot entier", variable=self.word_var,
                       bg="#F0F4F8", font=("Segoe UI", 10)).pack(side="left", padx=12)
        tk.Checkbutton(opts, text="Inclure les sous-dossiers",
                       variable=self.recurse_var,
                       bg="#F0F4F8", font=("Segoe UI", 10)).pack(side="left", padx=12)



        # Boutons action
        btn_frame = tk.Frame(self, bg="#F0F4F8")
        btn_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.btn_search = tk.Button(btn_frame, text="🔍  Lancer la recherche",
                                    command=self._start_search,
                                    font=("Segoe UI", 11, "bold"),
                                    bg="#2E7D32", fg="white", relief="flat",
                                    padx=14, pady=6)
        self.btn_search.pack(side="left")
        self.btn_stop = tk.Button(btn_frame, text="⏹  Stopper", command=self._stop_search,
                                  font=("Segoe UI", 11, "bold"),
                                  bg="#C62828", fg="white", relief="flat",
                                  padx=14, pady=6, state="disabled")
        self.btn_stop.pack(side="left", padx=8)
        tk.Button(btn_frame, text="Effacer résultats", command=self._clear,
                  font=("Segoe UI", 10), bg="#B0BEC5", relief="flat",
                  padx=10, pady=6).pack(side="left", padx=10)
        tk.Button(btn_frame, text="Exporter CSV", command=self._export_csv,
                  font=("Segoe UI", 10), bg="#1565C0", fg="white",
                  relief="flat", padx=10, pady=6).pack(side="left")

        # Barre de progression + statut
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=(0, 2))
        self.status_var = tk.StringVar(value="Prêt.")
        tk.Label(self, textvariable=self.status_var, bg="#F0F4F8",
                 font=("Segoe UI", 9), fg="#444", anchor="w"
                 ).pack(fill="x", padx=12)

        # ── Tableau de résultats ─────────────────────────────────────────────
        # ── Tableau résultats (sans colonne Contexte) ────────────────────────
        cols = ("Fichier", "Terme", "Contexte")
        frame_tree = tk.Frame(self)
        frame_tree.pack(fill="both", expand=True, padx=10, pady=(4, 0))

        self.tree = ttk.Treeview(frame_tree, columns=cols, show="headings",
                                  selectmode="browse")
        col_widths = {"Fichier": 280, "Terme": 110, "Contexte": 650}
        for c in cols:
            self.tree.heading(c, text=c,
                              command=lambda col=c: self._sort_column(col))
            self.tree.column(c, width=col_widths[c], anchor="w")

        vsb = ttk.Scrollbar(frame_tree, orient="vertical",
                            command=self.tree.yview)
        hsb = ttk.Scrollbar(frame_tree, orient="horizontal",
                            command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        # Style des lignes alternées
        self.tree.tag_configure("odd", background="#FFFFFF")
        self.tree.tag_configure("even", background="#E8F5E9")
        self.tree.tag_configure("error", background="#FFEBEE", foreground="red")

        # Double-clic → ouvrir le fichier
        self.tree.bind("<Double-1>", self._open_file)



        self._results: list[dict] = []
        self._sort_state: dict = {}

    # ── Actions ──────────────────────────────────────────────────────────────

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Sélectionner un dossier")
        if folder:
            self.folder_var.set(folder)
            save_config({"folder": folder})

    def _clear(self):
        self.tree.delete(*self.tree.get_children())
        self._results = []
        self.status_var.set("Prêt.")

    def _start_search(self):
        folder = self.folder_var.get().strip()
        terms_raw = self.terms_var.get().strip()

        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("Dossier invalide",
                                   "Veuillez sélectionner un dossier valide.")
            return
        if not terms_raw:
            messagebox.showwarning("Termes manquants",
                                   "Entrez au moins un terme à rechercher.")
            return

        terms, auto_mode = parse_query(terms_raw)

        if not HAS_DOCX and not HAS_PDF:
            messagebox.showerror(
                "Dépendances manquantes",
                "Installez les librairies requises :\n"
                "  pip install python-docx pymupdf")
            return

        save_config({"folder": folder})
        self._stop_event.clear()
        self._clear()
        self.btn_search.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress.start(10)
        self.status_var.set("Recherche en cours…")

        thread = threading.Thread(
            target=self._run_search,
            args=(folder, terms,
                  self.case_var.get(), self.word_var.get(),
                  self.recurse_var.get(), auto_mode),
            daemon=True)
        thread.start()

    def _stop_search(self):
        self._stop_event.set()
        self.status_var.set("Arrêt en cours…")

    def _run_search(self, folder, terms, case_sensitive, whole_word, recurse, mode):
        """Exécuté dans un thread secondaire."""
        files = self._collect_files(folder, recurse)
        all_results = []
        total = len(files)

        # Avec un seul terme, AND n'a pas de sens → traiter comme OR
        effective_mode = "OR" if len(terms) <= 1 else mode

        # Normaliser les termes pour la comparaison (espaces, apostrophes)
        def normalize(s):
            return re.sub(r"[\s\'\u2019]+", " ", s).strip().lower()

        norm_terms = {normalize(t) for t in terms}

        for idx, path in enumerate(files, start=1):
            if self._stop_event.is_set():
                break
            self.status_var.set(
                f"Analyse {idx}/{total} : {os.path.basename(path)}")
            results = search_in_file(path, terms, case_sensitive, whole_word)

            if effective_mode == "OR":
                all_results.extend(results)

            elif effective_mode == "AND_DOC":
                # Garder uniquement si TOUS les termes sont présents dans le fichier
                found_norm = {normalize(r["term"]) for r in results}
                if all(nt in found_norm for nt in norm_terms):
                    all_results.extend(results)

            elif effective_mode == "AND_PAGE":
                # Garder uniquement les pages où TOUS les termes apparaissent
                from collections import defaultdict
                by_page = defaultdict(list)
                for r in results:
                    by_page[r["page"]].append(r)
                for page_results in by_page.values():
                    found_norm = {normalize(r["term"]) for r in page_results}
                    if all(nt in found_norm for nt in norm_terms):
                        all_results.extend(page_results)

        self.after(0, self._display_results, all_results, total)

    def _collect_files(self, folder: str, recurse: bool) -> list[str]:
        exts = {".docx", ".pdf"}
        files = []
        if recurse:
            for root, _, filenames in os.walk(folder):
                for f in filenames:
                    if os.path.splitext(f)[1].lower() in exts and not f.startswith("~$"):
                        files.append(os.path.join(root, f))
        else:
            for f in os.listdir(folder):
                if os.path.splitext(f)[1].lower() in exts and not f.startswith("~$"):
                    files.append(os.path.join(folder, f))
        return files

    def _display_results(self, results: list[dict], total_files: int):
        self.progress.stop()
        self.btn_search.config(state="normal")
        self.btn_stop.config(state="disabled")
        self._results = results

        for i, r in enumerate(results):
            tag = "error" if r["term"] == "ERREUR" else ("even" if i % 2 == 0 else "odd")
            self.tree.insert("", "end",
                             values=(r["file"], r["term"], r["context"]),
                             tags=(tag,))

        self.status_var.set(
            f"{len(results)} occurrence(s) trouvée(s) dans {total_files} fichier(s) analysé(s).")

    def _export_csv(self):
        if not self._results:
            messagebox.showinfo("Aucun résultat", "Aucun résultat à exporter.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Tous", "*.*")],
            title="Enregistrer les résultats")
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["file", "term", "page", "context"])
            writer.writeheader()
            writer.writerows(self._results)
        messagebox.showinfo("Export réussi", f"Résultats exportés dans :\n{path}")

    def _open_file(self, event):
        item = self.tree.focus()
        if not item:
            return
        values = self.tree.item(item, "values")
        if values:
            filepath = values[0]
            if os.path.exists(filepath):
                os.startfile(filepath) if os.name == "nt" else os.system(
                    f'xdg-open "{filepath}"')

    def _sort_column(self, col):
        """Tri croissant/décroissant sur une colonne."""
        col_map = {"Fichier": "file", "Terme": "term", "Contexte": "context"}
        key = col_map[col]
        reverse = self._sort_state.get(col, False)
        self._sort_state[col] = not reverse

        sorted_results = sorted(
            self._results,
            key=lambda r: (int(r[key]) if key == "page" and r[key].isdigit()
                           else r[key].lower()),
            reverse=reverse)
        self._results = sorted_results

        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(sorted_results):
            tag = "error" if r["term"] == "ERREUR" else ("even" if i % 2 == 0 else "odd")
            self.tree.insert("", "end",
                             values=(r["file"], r["term"], r["context"]),
                             tags=(tag,))


# ── Vérification des dépendances au démarrage ────────────────────────────────

def check_dependencies():
    missing = []
    if not HAS_DOCX:
        missing.append("python-docx  →  pip install python-docx")
    if not HAS_PDF:
        missing.append("PyMuPDF      →  pip install pymupdf")
    if missing:
        root = tk.Tk()
        root.withdraw()
        msg = ("Certaines librairies sont manquantes.\n"
               "L'outil fonctionnera partiellement.\n\n"
               + "\n".join(missing))
        messagebox.showwarning("Dépendances", msg)
        root.destroy()


# ── Point d'entrée ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    check_dependencies()
    app = SearchApp()
    app.mainloop()
