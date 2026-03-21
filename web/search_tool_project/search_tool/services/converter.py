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


_word_available: bool | None = None


def is_word_available() -> bool:
    """Check once if Microsoft Word COM automation is available on this machine."""
    global _word_available
    if _word_available is not None:
        return _word_available
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Quit()
        pythoncom.CoUninitialize()
        _word_available = True
        logger.info("Microsoft Word disponible — conversion DOCX→PDF via Word COM")
    except Exception:
        _word_available = False
        logger.info("Microsoft Word non disponible — conversion via LibreOffice")
    return _word_available


_WORD_RESTART_EVERY = 50  # restart Word instance every N files to prevent memory buildup


class WordConverter:
    """
    Context manager for batch DOCX→PDF conversion using a single Word instance.
    Much faster than LibreOffice: no per-file startup cost.
    Auto-restarts on error or every WORD_RESTART_EVERY files.
    Usage:
        with WordConverter() as wc:
            pdf_path = wc.convert(docx_path, cache_dir, docx_copy_dir)
    """

    def __enter__(self):
        import pythoncom
        pythoncom.CoInitialize()
        self._count = 0
        self._word = self._new_instance()
        return self

    def __exit__(self, *args):
        self._quit()
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass

    def _new_instance(self):
        import win32com.client
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0  # wdAlertsNone
        return word

    def _quit(self):
        try:
            self._word.Quit()
        except Exception:
            pass

    def _restart(self):
        self._quit()
        self._word = self._new_instance()
        self._count = 0
        logger.info("Instance Word redémarrée")

    def convert(self, docx_path: str, cache_dir: str,
                docx_copy_dir: str | None = None) -> str | None:
        """Convert one DOCX to PDF. Returns cached PDF path or None on failure."""
        os.makedirs(cache_dir, exist_ok=True)
        pdf_cache_path = get_pdf_cache_path(docx_path, cache_dir)

        if is_cache_fresh(docx_path, pdf_cache_path):
            return pdf_cache_path

        # Periodic restart to prevent memory buildup
        if self._count > 0 and self._count % _WORD_RESTART_EVERY == 0:
            self._restart()

        docx_path = os.path.normpath(docx_path)

        if docx_copy_dir:
            os.makedirs(docx_copy_dir, exist_ok=True)
            local_docx = get_docx_copy_path(docx_path, docx_copy_dir)
        else:
            local_docx = None

        with tempfile.TemporaryDirectory() as tmp_dir:
            if local_docx is None:
                local_docx = os.path.join(tmp_dir, os.path.basename(docx_path))
            try:
                shutil.copy2(docx_path, local_docx)
            except OSError as e:
                logger.warning("Cannot copy %s locally: %s", docx_path, e)
                return None

            try:
                doc = self._word.Documents.Open(
                    os.path.abspath(local_docx),
                    ReadOnly=True,
                    AddToRecentFiles=False,
                )
                try:
                    doc.SaveAs2(os.path.abspath(pdf_cache_path), FileFormat=17)
                finally:
                    try:
                        doc.Close(SaveChanges=False)
                    except Exception:
                        pass
                self._count += 1
                return pdf_cache_path
            except Exception as e:
                if is_encrypted_docx(local_docx):
                    logger.warning("Skipping encrypted DOCX: %s", docx_path)
                else:
                    logger.warning("Word COM échec pour %s : %s — redémarrage Word", docx_path, e)
                    self._restart()
                return None


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
        except subprocess.TimeoutExpired as e:
            e.process.kill()
            logger.warning("LibreOffice timeout (>120s) pour %s", docx_path)
        except Exception as e:
            logger.warning("Erreur conversion %s : %s", docx_path, e)

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
