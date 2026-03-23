import threading

_startup_done = False
_startup_lock = threading.Lock()


class StartupMiddleware:
    """
    Resets stale indexing state (running=True from a previous crash) on the
    first HTTP request, once the database is guaranteed to be ready.
    Much safer than AppConfig.ready() which runs before migrations complete.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        global _startup_done
        if not _startup_done:
            with _startup_lock:
                if not _startup_done:
                    try:
                        from .indexing_state import reset_running_on_startup
                        reset_running_on_startup()
                    except Exception:
                        pass
                    _startup_done = True
        return self.get_response(request)
