"""Shared view helpers (path encoding, HTML highlighting, cleanup utilities)."""
import base64
import hashlib
import os
import re
import string
from pathlib import Path

from django.conf import settings

from ..models import Favorite


def encode_path(path: str) -> str:
    return base64.urlsafe_b64encode(path.encode("utf-8")).decode()


def decode_path(encoded: str) -> str:
    return base64.urlsafe_b64decode(encoded.encode()).decode("utf-8")


def highlight_context(context: str) -> str:
    """Replace [term] markers with <mark> tags for HTML display."""
    safe = context.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\[([^\]]+)\]", r'<mark>\1</mark>', safe)


def list_drives() -> list[str]:
    """Return available Windows drive letters (e.g. ['C:\\', 'I:\\'])."""
    return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]


def is_under_root(path: str, root: str) -> bool:
    """Return True if path is equal to or inside root (case-insensitive)."""
    p = os.path.normcase(os.path.normpath(path))
    r = os.path.normcase(os.path.normpath(root))
    return p == r or p.startswith(r + os.sep)


def referenced_hashes() -> set[str]:
    """Hashes of all folder paths referenced by any user's favorites."""
    hashes = set()
    for path in Favorite.objects.values_list("path", flat=True).distinct():
        normalized = os.path.normpath(path).lower()
        hashes.add(hashlib.md5(normalized.encode("utf-8")).hexdigest()[:10])
    return hashes


def folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def human_size(n: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} To"


def orphaned_dirs() -> list[dict]:
    folders_dir = Path(settings.DATA_DIR) / "folders"
    if not folders_dir.exists():
        return []
    referenced = referenced_hashes()
    result = []
    for d in sorted(folders_dir.iterdir()):
        if not d.is_dir():
            continue
        parts = d.name.rsplit("_", 1)
        if len(parts) != 2 or not re.match(r"^[0-9a-f]{10}$", parts[1]):
            continue
        if parts[1] not in referenced:
            size = folder_size(d)
            result.append({"name": d.name, "path": str(d), "size_human": human_size(size)})
    return result
