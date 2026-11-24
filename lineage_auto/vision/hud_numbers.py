"""Read the exact "HP:356/432" / "MP:36/221" text on the HUD (PLAN 0.3 / 2.2).

The HUD font is monospaced (10 px pitch, 12 px tall). Find the "HP:" / "MP:"
prefix by template, then match each 10 px cell against digit templates with a
1 px shift. Templates live in data/hud_glyphs/ (tests/build_hud_glyphs.py).
Returns None whenever anything looks unsure, so callers fall back to the bar.
"""

import os

import cv2
import numpy as np

from .. import app_paths

PITCH = 10
HEIGHT = 12
CHARS = "0123456789/"
GLYPH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "hud_glyphs")
# Search areas as fractions of the client (1280x960: HP prefix at 438,765, MP at 686,765).
# PLAN 0.18/0.19: the bar moves up when the player makes the chat box taller (1302x976 record: y ~0.70),
# so search most of the lower half; the row of the last good read is tried first (NEAR_PX) to keep reads cheap.
BAND_Y = (0.5, 0.92)
NEAR_PX = 8
PREFIX_X = {"hp": (0.25, 0.50), "mp": (0.50, 0.72)}
PREFIX_MIN = 0.6
CHAR_MIN = 0.7
MAX_CELLS = 11  # "65535/65535"
BASE_W = 1280  # client width the glyphs were cut from


def glyph_file(ch):
    return "slash.png" if ch == "/" else f"d{ch}.png"


def _glyph_dir():
    """Frozen build: the data folder is bundled under _MEIPASS."""
    packaged = os.path.join(app_paths.asset_dir(), "lineage_auto", "data", "hud_glyphs")
    return packaged if os.path.isdir(packaged) else GLYPH_DIR


def find_prefix(gray, template, kind, band=None):
    """(score, (x, y)) of the "HP:"/"MP:" prefix in a full client gray frame, or None."""
    h, w = gray.shape[:2]
    y0, y1 = band or (int(h * BAND_Y[0]), int(h * BAND_Y[1]))
    x0, x1 = (int(w * f) for f in PREFIX_X[kind])
    roi = gray[y0:y1, x0:x1]
    if roi.shape[0] < template.shape[0] or roi.shape[1] < template.shape[1]:
        return None
    res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    return float(score), (loc[0] + x0, loc[1] + y0)


class HudNumberReader:
    def __init__(self, glyph_dir=None):
        folder = glyph_dir or _glyph_dir()
        self.prefixes = {}
        self.glyphs = {}
        for kind in ("hp", "mp"):
            img = cv2.imread(os.path.join(folder, f"{kind}.png"), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                self.prefixes[kind] = img.astype(np.float32)
        for ch in CHARS:
            img = cv2.imread(os.path.join(folder, glyph_file(ch)), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                self.glyphs[ch] = img.astype(np.float32)
        self.last_score = {}
        self._last_y = {}  # 1280-scale row of the prefix at the last good read

    @property
    def available(self):
        return len(self.prefixes) == 2 and len(self.glyphs) == len(CHARS)

    def read(self, frame_bgr):
        """{"hp": (cur, max) or None, "mp": (cur, max) or None}."""
        out = {"hp": None, "mp": None}
        if not self.available or frame_bgr is None or frame_bgr.size == 0:
            return out
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if gray.shape[1] != BASE_W:
            # The client scales the HUD with the window (game PC: 1187x890); glyphs are 1280-wide pixels.
            h, w = gray.shape[:2]
            gray = cv2.resize(gray, (BASE_W, round(h * BASE_W / w)), interpolation=cv2.INTER_LINEAR)
        gray = gray.astype(np.float32)
        for kind in ("hp", "mp"):
            out[kind] = self._read_one(gray, kind)
        return out

    def _read_one(self, gray, kind):
        found = None
        y = self._last_y.get(kind)
        if y is not None:
            found = find_prefix(gray, self.prefixes[kind], kind, band=(max(0, y - NEAR_PX), y + HEIGHT + NEAR_PX))
        if found is None or found[0] < PREFIX_MIN:
            found = find_prefix(gray, self.prefixes[kind], kind)
        if found is None or found[0] < PREFIX_MIN:
            self.last_score[kind] = found[0] if found else 0.0
            return None
        x0, y0 = found[1]
        text, worst = "", 1.0
        for k in range(MAX_CELLS):
            x = x0 + 3 * PITCH + k * PITCH
            cell = gray[y0 - 1:y0 + HEIGHT + 1, x - 1:x + PITCH + 1]
            if cell.shape != (HEIGHT + 2, PITCH + 2):
                break
            ch, score = max(
                ((c, float(cv2.matchTemplate(cell, g, cv2.TM_CCOEFF_NORMED).max())) for c, g in self.glyphs.items()),
                key=lambda item: item[1],
            )
            if score < CHAR_MIN:
                break  # end of text (bar background) or an unsure glyph
            text += ch
            worst = min(worst, score)
        self.last_score[kind] = worst
        pair = parse_pair(text)
        if pair is not None:
            self._last_y[kind] = y0
        return pair


CHAT_BELOW = 27  # 1280-scale px: the chat text starts this far below the "HP:" prefix row
_shared = None


def chat_top(frame_bgr):
    """Top of the chat text as a share of the client height, from where the HP/MP bar is (PLAN 0.19:
    a taller chat box pushes the bar up). None when the "HP:" prefix is not found."""
    global _shared
    if _shared is None:
        _shared = HudNumberReader()
    if _shared.prefixes.get("hp") is None or frame_bgr is None or frame_bgr.size == 0:
        return None
    h, w = frame_bgr.shape[:2]
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    if w != BASE_W:
        gray = cv2.resize(gray, (BASE_W, round(h * BASE_W / w)), interpolation=cv2.INTER_LINEAR)
    gray = gray.astype(np.float32)
    template = _shared.prefixes["hp"]
    y = _shared._last_y.get("chat")
    found = find_prefix(gray, template, "hp", band=(max(0, y - NEAR_PX), y + HEIGHT + NEAR_PX)) if y else None
    if found is None or found[0] < PREFIX_MIN:
        found = find_prefix(gray, template, "hp")
    if found is None or found[0] < PREFIX_MIN:
        return None
    _shared._last_y["chat"] = found[1][1]
    return (found[1][1] + CHAT_BELOW) / gray.shape[0]


def parse_pair(text):
    """"356/432" -> (356, 432); anything odd -> None."""
    parts = text.split("/")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    cur, top = int(parts[0]), int(parts[1])
    if top <= 0 or cur > top:
        return None
    return cur, top


def percent(pair):
    """0 only when the HUD really says 0 (1/432 rounds up to 1%: alive)."""
    if pair is None:
        return None
    value = int(round(100 * pair[0] / pair[1]))
    return max(1, value) if pair[0] > 0 else 0
