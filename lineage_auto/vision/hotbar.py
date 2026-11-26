"""Hotbar bottom-right: which page is open and whether an item slot is empty (PLAN 1.4b).

Measured on records_game/20261127_003555_hunt (1280x960) and the 1302x976 observe recordings (the HUD scales with
the client width): page tabs F1/F2/F3 above two rows of 4 slots, F5-F8 then F9-F12, 66 x 64 px apart.
An item slot whose stack ran out is drawn dark with only a faint key label: the 99th percentile of its brightness
is 55 (F6 after the 2 mana potions of 003555 were drunk at 137 s) against 255 while the potion and its count are
there. Skill slots dimmed by a cooldown read 60-62, so this test is for ITEM slots (potions), not skills.
"""
import cv2
import numpy as np

BASE_W = 1280
SLOT_RIGHT, SLOT_BOTTOM = 279, 189  # top-left corner of F5 from the client's bottom-right corner, at 1280
PITCH_X, PITCH_Y = 66, 64
INSET, INNER = 6, 52  # the icon inside a slot frame
TAB_RIGHT, TAB_BOTTOM, TAB_W, TAB_H, TAB_PITCH = 277, 208, 36, 18, 40
EMPTY_V = 90  # 99th percentile brightness under this = the slot holds nothing
SLOT_KEYS = ("F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12")
PAGES = ("F1", "F2", "F3")


def _scale(frame):
    h, w = frame.shape[:2]
    return w, h, w / BASE_W


def slot_icon(frame, key):
    """BGR picture inside hotbar slot ``key`` (F5-F12), or None for another key."""
    if key not in SLOT_KEYS:
        return None
    w, h, f = _scale(frame)
    i = SLOT_KEYS.index(key)
    x = round(w - (SLOT_RIGHT - PITCH_X * (i % 4) - INSET) * f)
    y = round(h - (SLOT_BOTTOM - PITCH_Y * (i // 4) - INSET) * f)
    n = round(INNER * f)
    return frame[y:y + n, x:x + n]


def open_page(frame):
    """The page tab drawn brightest (F1/F2/F3)."""
    w, h, f = _scale(frame)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    y0, y1 = round(h - TAB_BOTTOM * f), round(h - (TAB_BOTTOM - TAB_H) * f)
    means = [float(gray[y0:y1, round(w - (TAB_RIGHT - TAB_PITCH * i) * f):
                         round(w - (TAB_RIGHT - TAB_PITCH * i - TAB_W) * f)].mean()) for i in range(3)]
    return PAGES[int(np.argmax(means))]


def slot_empty(frame, key):
    """True when item slot ``key`` shows nothing, None when it cannot be read."""
    icon = slot_icon(frame, key)
    if icon is None or icon.size == 0:
        return None
    return float(np.percentile(cv2.cvtColor(icon, cv2.COLOR_BGR2HSV)[..., 2], 99)) < EMPTY_V
