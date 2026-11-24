"""Load skill pack icons for Tkinter widgets."""

from __future__ import annotations

import os

import cv2

try:
    import tkinter as tk
except ImportError:
    tk = None


def load_photo_icon(path, size=32):
    """Load a PNG icon as ``tk.PhotoImage`` via OpenCV resize and in-memory PPM.

    Requires a Tk root to exist before ``PhotoImage`` can be constructed. The
    caller may invoke this before showing a window; unit tests can skip
    ``PhotoImage`` creation or use a withdrawn ``Tk()`` root.

    Returns ``None`` when the path is missing, unreadable, or conversion fails.
    """
    if tk is None:
        return None
    if not path or not os.path.isfile(path):
        return None

    bgr = cv2.imread(path)
    if bgr is None:
        return None

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    if width != size or height != size:
        rgb = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_AREA)

    header = f"P6 {size} {size} 255 ".encode("ascii")
    ppm = header + rgb.tobytes()
    try:
        return tk.PhotoImage(data=ppm, format="ppm")
    except tk.TclError:
        return None
