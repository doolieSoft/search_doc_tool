import json
import os
import unicodedata

CONFIG_FILE = os.path.expanduser("~/.search_tool_config.json")


def remove_accents(s: str) -> str:
    """Normalize Unicode: strip diacritics and normalize common quote/space variants."""
    s = s.replace("\u2018", "'").replace("\u2019", "'").replace("\u02bc", "'")
    s = s.replace("\u00a0", " ").replace("\u202f", " ")
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


class ConfigService:
    """
    Manages persistent configuration stored in ~/.search_tool_config.json.
    Shared between the desktop and web applications.
    """

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file

    # ── Static utility ────────────────────────────────────────────────────────

    @staticmethod
    def remove_accents(s: str) -> str:
        return remove_accents(s)

    # ── Config persistence ────────────────────────────────────────────────────

    def load(self) -> dict:
        try:
            with open(self.config_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save(self, cfg: dict) -> None:
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_favorites(self) -> list:
        return self.load().get("favorites", [])

    def save_favorites(self, favs: list) -> None:
        cfg = self.load()
        cfg["favorites"] = favs
        self.save(cfg)
