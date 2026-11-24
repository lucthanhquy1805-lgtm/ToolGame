"""Turn-taking for the physical mouse.

Several accounts can run at once, but there is only one real cursor. Each
session must hold this lock while it drives the mouse, so sessions interleave
instead of fighting. Sessions that cannot get the lock simply skip their turn.
"""

import threading
from contextlib import contextmanager


class InputArbiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._owner = None

    @property
    def owner(self):
        return self._owner

    @contextmanager
    def hold(self, owner, timeout=5.0):
        """Yield True when the caller owns the mouse, False when it timed out."""
        acquired = self._lock.acquire(timeout=timeout)
        if acquired:
            self._owner = owner
        try:
            yield acquired
        finally:
            if acquired:
                self._owner = None
                self._lock.release()
