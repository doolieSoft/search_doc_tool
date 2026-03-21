import hashlib
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import zipfile

logger = logging.getLogger(__name__)


def _soffice_executable() -> str:
    """Find the LibreOffice soffice executable for the current platform."""
    if platform.system() == "Windows":
        candidates = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return "soffice"
    else:
        return "libreoffice"


def get_pdf_cache_path(original_path: str, cache_dir: str) -> str:
    """Content-addressed path: same DOCX always maps to same cached PDF."""
    h = hashlib.md5(original_path.encode("utf-8")).hexdigest()
    return os.path.join(cache_dir, f"{h}.pdf")


def get_docx_copy_path(original_path: str, docx_copy_dir: str) -> str:
    """Content-addressed local copy path for a DOCX (same hash as its PDF cache)."""
    h = hashlib.md5(original_path.encode("utf-8")).hexdigest()
    return os.path.join(docx_copy_dir, f"{h}.docx")


def is_cache_fresh(original_path: str, pdf_cache_path: str) -> bool:
    if not os.path.exists(pdf_cache_path):
        return False
    try:
        return os.path.getmtime(original_path) <= os.path.getmtime(pdf_cache_path)
    except OSError:
        return False


def is_encrypted_docx(docx_path: str) -> bool:
    """Return True if the DOCX is password-protected (not a valid ZIP = OLE-encrypted)."""
    try:
        with zipfile.ZipFile(docx_path):
            return False
    except zipfile.BadZipFile:
        return True
    except Exception:
        return False


def convert_docx_to_pdf(docx_path: str, cache_dir: str,
                        docx_copy_dir: str | None = None) -> str | None:
    """
    Convert a DOCX to PDF via LibreOffice headless.
    Returns the cached PDF path, or None on failure.
    Skips conversion if the cache is already fresh.

    If docx_copy_dir is provided, the DOCX is copied there first (persistent local
    copy on a local drive) so LibreOffice can access it even on mapped network drives.
    """
    os.makedirs(cache_dir, exist_ok=True)
    pdf_cache_path = get_pdf_cache_path(docx_path, cache_dir)

    if is_cache_fresh(docx_path, pdf_cache_path):
        return pdf_cache_path

    exe = _soffice_executable()
    docx_path = os.path.normpath(docx_path)

    # ── Get a local copy of the DOCX ─────────────────────────────────────────
    # LibreOffice subprocesses may not inherit access to mapped network drives.
    if docx_copy_dir:
        os.makedirs(docx_copy_dir, exist_ok=True)
        local_docx = get_docx_copy_path(docx_path, docx_copy_dir)
    else:
        local_docx = None  # will be set inside the temp dir block

    with tempfile.TemporaryDirectory() as tmp_dir:
        if local_docx is None:
            local_docx = os.path.join(tmp_dir, os.path.basename(docx_path))

        try:
            shutil.copy2(docx_path, local_docx)
        except OSError as e:
            logger.warning("Cannot copy %s locally: %s", docx_path, e)
            return None

        # Each conversion gets its own LO profile dir to allow safe parallelism.
        # Must be pre-created: LibreOffice fails silently if UserInstallation doesn't exist.
        lo_profile = os.path.join(tmp_dir, "lo_profile")
        os.makedirs(lo_profile, exist_ok=True)
        user_install = "file:///" + lo_profile.replace("\\", "/")

        try:
            result = subprocess.run(
                [exe,
                 f"-env:UserInstallation={user_install}",
                 "--headless", "--convert-to", "pdf",
                 "--outdir", tmp_dir, local_docx],
                capture_output=True,
                timeout=120,
                check=False,
            )
            base = os.path.splitext(os.path.basename(local_docx))[0]
            tmp_pdf = os.path.join(tmp_dir, f"{base}.pdf")
            if os.path.exists(tmp_pdf):
                shutil.move(tmp_pdf, pdf_cache_path)
                return pdf_cache_path
            if is_encrypted_docx(local_docx):
                logger.warning("Skipping encrypted (password-protected) DOCX: %s", docx_path)
            else:
                logger.warning(
                    "LibreOffice failed to convert %s (rc=%s)\nstdout: %s\nstderr: %s",
                    docx_path,
                    result.returncode,
                    result.stdout.decode("utf-8", errors="replace").strip(),
                    result.stderr.decode("utf-8", errors="replace").strip(),
                )
        except FileNotFoundError:
            raise RuntimeError(
                f"LibreOffice introuvable ({exe}). "
                "Vérifiez l'installation ou ajoutez soffice.exe au PATH."
            )
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

    return None


def get_pdf_path(original_path: str, cache_dir: str,
                 docx_copy_dir: str | None = None) -> str | None:
    """
    For .pdf files, return the path as-is.
    For .docx files, convert and return the cached PDF path.
    """
    ext = os.path.splitext(original_path)[1].lower()
    if ext == ".pdf":
        return original_path
    if ext == ".docx":
        return convert_docx_to_pdf(original_path, cache_dir, docx_copy_dir)
    return None
