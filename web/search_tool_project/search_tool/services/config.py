import json
import os
import unicodedata

CONFIG_FILE = os.path.expanduser("~/.search_tool_config.json")


def remove_accents(s: str) -> str:
    s = s.replace("\u2018", "'").replace("\u2019", "'").replace("\u02bc", "'")
    s = s.replace("\u00a0", " ").replace("\u202f", " ")
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_favorites() -> list:
    return load_config().get("favorites", [])


def save_favorites(favs: list):
    cfg = load_config()
    cfg["favorites"] = favs
    save_config(cfg)
