import os
import re

from .config import remove_accents
from .extractor import extract_text_pdf
from .converter import get_pdf_path


def parse_query(raw: str):
    raw_no_quotes = re.sub(r'"[^"]+"', "", raw)
    mode = "AND" if "+" in raw_no_quotes else "OR"
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
        elif raw[i] in ("+", ",", " "):
            i += 1
        else:
            end = i
            while end < len(raw) and raw[end] not in ('"', "+", ",", " "):
                end += 1
            word = raw[i:end].strip()
            if word:
                term_list.append(word)
            i = end
    return term_list, mode


def _word_span(text: str, ts: int, te: int) -> tuple[int, int]:
    while te < len(text) and (text[te].isalnum() or text[te] in "_-"):
        te += 1
    return ts, te


def get_context(text: str, match, window: int = 100) -> str:
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    snippet = text[start:end].replace("\n", " ").strip()
    ts = match.start() - start
    te = match.end() - start
    ts, te = _word_span(snippet, ts, te)
    snippet = snippet[:ts] + "[" + snippet[ts:te] + "]" + snippet[te:]
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


def get_combined_context(text: str, matches: list, window: int = 100,
                         proximity_words: int = 30) -> str:
    if not matches:
        return ""
    if len(matches) == 1:
        return get_context(text, matches[0], window)
    matches = sorted(matches, key=lambda m: m.start())
    between = text[matches[0].end():matches[-1].start()]
    if len(between.split()) <= proximity_words:
        start = max(0, matches[0].start() - window)
        end = min(len(text), matches[-1].end() + window)
        snippet = text[start:end].replace("\n", " ").strip()
        offset = start
        for m in reversed(matches):
            ts = m.start() - offset
            te = m.end() - offset
            ts, te = _word_span(snippet, ts, te)
            snippet = snippet[:ts] + "[" + snippet[ts:te] + "]" + snippet[te:]
        return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")
    else:
        return " | ".join(get_context(text, m, window) for m in matches)


def build_pattern(term: str, case_sensitive: bool, whole_word: bool):
    norm = remove_accents(term) if not case_sensitive else term
    words = re.split(r"\s+", norm.strip())
    escaped = [re.escape(w) for w in words]
    pattern_str = r"[\s\W]*".join(escaped)
    if whole_word:
        pattern_str = r"\b" + pattern_str + r"\b"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(pattern_str, flags)


def search_file(path: str, terms: list, case_sensitive: bool,
                whole_word: bool, mode: str, pdf_cache_dir: str) -> list[dict]:
    """
    Search a file for terms.
    DOCX files are searched via their cached PDF conversion.
    Returns list of result dicts with keys: file, term, context, page.
    """
    pdf_path = get_pdf_path(path, pdf_cache_dir)
    if not pdf_path or not os.path.exists(pdf_path):
        return []

    try:
        pages = extract_text_pdf(pdf_path)
    except Exception as e:
        return [{"file": path, "term": "ERREUR", "context": str(e), "page": None}]

    if not pages:
        return []

    results = []

    if mode == "AND":
        for page_num, raw_text in pages:
            search_text = remove_accents(raw_text) if not case_sensitive else raw_text
            patterns = {}
            for term in terms:
                try:
                    patterns[term] = build_pattern(term, case_sensitive, whole_word)
                except re.error:
                    return []
            page_matches = {}
            all_found = True
            for term, pat in patterns.items():
                ms = list(pat.finditer(search_text))
                if not ms:
                    all_found = False
                    break
                page_matches[term] = ms
            if all_found:
                best = [ms[0] for ms in page_matches.values()]
                results.append({
                    "file": path,
                    "term": " + ".join(terms),
                    "context": get_combined_context(raw_text, best),
                    "page": page_num,
                })
    else:
        for page_num, raw_text in pages:
            search_text = remove_accents(raw_text) if not case_sensitive else raw_text
            for term in terms:
                try:
                    pat = build_pattern(term, case_sensitive, whole_word)
                except re.error:
                    continue
                for match in pat.finditer(search_text):
                    results.append({
                        "file": path,
                        "term": term,
                        "context": get_context(raw_text, match),
                        "page": page_num,
                    })

    return results


def collect_files(folder: str, recurse: bool) -> list:
    exts = {".docx", ".pdf"}
    files = []
    if recurse:
        for root, _, filenames in os.walk(folder):
            for f in filenames:
                if (os.path.splitext(f)[1].lower() in exts
                        and not f.startswith(("~$", "._", ".~"))):
                    files.append(os.path.join(root, f))
    else:
        for f in os.listdir(folder):
            if (os.path.splitext(f)[1].lower() in exts
                    and not f.startswith(("~$", "._", ".~"))):
                files.append(os.path.join(folder, f))
    return files
