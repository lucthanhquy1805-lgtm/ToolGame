"""Screen capture.

mss handles are not thread-safe, so each thread gets its own. That keeps one
shared ScreenGrabber usable by every account session.
"""

import threading

import cv2
import mss
import numpy as np


class ScreenGrabber:
    def __init__(self):
        self._local = threading.local()

    @property
    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = mss.MSS()
            self._local.sct = sct
        return sct

    def grab_bgra(self, rect):
        return np.array(self._sct.grab(rect.to_monitor()))

    def grab_bgr(self, rect):
        return cv2.cvtColor(self.grab_bgra(rect), cv2.COLOR_BGRA2BGR)

    def grab_gray(self, rect):
        return cv2.cvtColor(self.grab_bgra(rect), cv2.COLOR_BGRA2GRAY)

    def close_thread(self):
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            try:
                sct.close()
            except Exception:
                pass
            self._local.sct = None
