"""File-only logging so the packaged tool never needs a console.
PLAN 0.38 (24/7): the log rotates past MAX_BYTES (session_log.txt -> session_log.1.txt -> .2, KEEP files)."""
import ctypes
import os
import sys
import threading
import time

from . import app_paths

MAX_BYTES = 20 * 1024 * 1024
KEEP = 3  # files in all: the live one + KEEP - 1 old ones
CHECK_EVERY = 200  # writes between two size checks


class FileLogger:
    def __init__(self, filename=None):
        self.filename = filename or app_paths.data_path(app_paths.LOG_FILE)
        self._lock = threading.Lock()
        self._writes = 0
        self._rotate_if_big()
        self._write_raw(
            "\n==========================================================================="
            + f"\n--- SESSION: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            + "==========================================================================="
            + "\n"
        )

    def _write_raw(self, text):
        try:
            with self._lock:
                self._writes += 1
                if self._writes % CHECK_EVERY == 0:
                    self._rotate_if_big()
                with open(self.filename, "a", encoding="utf-8") as f:
                    f.write(text)
        except Exception:
            return

    def _rotate_if_big(self):
        try:
            if os.path.getsize(self.filename) < MAX_BYTES:
                return
        except OSError:
            return
        root, ext = os.path.splitext(self.filename)
        names = [self.filename] + [f"{root}.{i}{ext}" for i in range(1, KEEP)]
        for i in range(KEEP - 1, 0, -1):
            try:
                if os.path.exists(names[i - 1]):
                    os.replace(names[i - 1], names[i])  # the oldest is overwritten
            except OSError:
                return

    def write(self, message):
        if not message or not message.strip():
            return
        self._write_raw(time.strftime("[%H:%M:%S] ") + message.strip() + "\n")

    def flush(self):
        pass


_logger = None


def rss_mb():
    """This process's resident memory (MB) on Windows, None elsewhere (PLAN 0.38)."""
    if not hasattr(ctypes, "windll"):
        return None

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    try:
        c = Counters()
        c.cb = ctypes.sizeof(c)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p  # a 64-bit pseudo handle, not an int
        k32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if not k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return None
        return c.WorkingSetSize / (1024 * 1024)
    except (AttributeError, OSError):
        return None


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
