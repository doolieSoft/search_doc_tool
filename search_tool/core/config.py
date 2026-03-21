import os
import json
import unicodedata

# config.py est dans search_tool/core/ — remonter 3 niveaux pour atteindre search_doc_tool/
_APP_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR = os.path.join(_APP_DIR, ".data")
os.makedirs(_DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".search_tool_config.json")
DB_FILE     = os.path.join(_DATA_DIR, "search_tool_index.db")


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


def load_favorites() -> list:
    """Retourne liste de dicts {path, name}."""
    favs = load_config().get("favorites", [])
    return [f if isinstance(f, dict) else {"path": f, "name": os.path.basename(f)}
            for f in favs]


def save_favorites(favs: list):
    cfg = load_config()
    cfg["favorites"] = favs
    save_config(cfg)


def remove_accents(s: str) -> str:
    s = s.replace('\u2018', "'").replace('\u2019', "'").replace('\u02bc', "'")
    s = s.replace('\u00a0', ' ').replace('\u202f', ' ')
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')
