"""ctypes structures and prototypes for cursor inspection.

Explicit argtypes matter here: without them the 64-bit HBITMAP handles
overflow and GetObjectW/GetBitmapBits silently fail.
"""

import ctypes
from ctypes import wintypes

_windll = getattr(ctypes, "windll", None)  # None off Windows: offline tools only use the pure helpers
user32 = _windll.user32 if _windll else None
gdi32 = _windll.gdi32 if _windll else None

HCURSOR = wintypes.HANDLE


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", HCURSOR),
        ("ptScreenPos", wintypes.POINT),
    ]


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


if _windll:
    user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
    user32.GetIconInfo.argtypes = [HCURSOR, ctypes.POINTER(ICONINFO)]
    gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
    gdi32.GetBitmapBits.argtypes = [wintypes.HBITMAP, ctypes.c_long, ctypes.c_void_p]
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
