"""File-only logging so the packaged tool never needs a console."""
import sys
import threading
import time

from . import app_paths


class FileLogger:
    def __init__(self, filename=None):
        self.filename = filename or app_paths.data_path(app_paths.LOG_FILE)
        self._lock = threading.Lock()
        self._write_raw(
            "\n==========================================================================="
            + f"\n--- SESSION: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            + "==========================================================================="
            + "\n"
        )

    def _write_raw(self, text):
        try:
            with self._lock:
                with open(self.filename, "a", encoding="utf-8") as f:
                    f.write(text)
        except Exception:
            return

    def write(self, message):
        if not message or not message.strip():
            return
        self._write_raw(time.strftime("[%H:%M:%S] ") + message.strip() + "\n")

    def flush(self):
        pass


_logger = None


def install():
    """Redirect stdout/stderr into the session log file."""
    global _logger
    if _logger is None:
        _logger = FileLogger()
        sys.stdout = _logger
        sys.stderr = _logger
    return _logger


def get_logger():
    return install()
