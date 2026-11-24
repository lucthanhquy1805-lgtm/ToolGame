"""Hotbar crop and buff-bar icon template matching.

Pack SpellIcons (brown fill + coloured art) do **not** look like the live buff
HUD (dark fill, white glyph + thin border). Matching therefore:

1. Resizes oversized pack templates to fit the buff-bar ROI / ``icon_size``.
2. Converts both haystack and needle to a bright-glyph plane so brown pack
   backgrounds do not dominate ``matchTemplate``.
"""

import json

import cv2
import numpy as np

from ..characters.base import HOTKEYS

_DEFAULT_HOTBAR = {
    key: {"cx_frac": 0.28 + i * 0.055, "cy_from_bottom": 52}
    for i, key in enumerate(HOTKEYS)
}

_MATCH_SCALES = (0.7, 0.85, 1.0, 1.15, 1.25, 1.4, 1.55)

DEFAULT_BUFF_VISION = {
    "buff_bar": {"right": 2, "top": 28, "width": 72, "height": 380},
    "icon_size": 36,
    "match_threshold": 0.5,
    "glyph_threshold": 150,
    "miss_needed": 2,
    "hotbar": dict(_DEFAULT_HOTBAR),
}


def merge_buff_vision(override):
    cfg = json.loads(json.dumps(DEFAULT_BUFF_VISION))
    if not override:
        return cfg
    cfg.update({k: v for k, v in override.items() if k != "buff_bar" and k != "hotbar"})
    if "buff_bar" in override:
        cfg["buff_bar"] = {**cfg["buff_bar"], **override["buff_bar"]}
    if "hotbar" in override:
        for key, slot in override["hotbar"].items():
            cfg["hotbar"][key] = {**cfg["hotbar"].get(key, {}), **slot}
    return cfg


def _clip_rect(x0, y0, x1, y1, width, height):
    x0 = max(0, min(x0, width))
    y0 = max(0, min(y0, height))
    x1 = max(0, min(x1, width))
    y1 = max(0, min(y1, height))
    return x0, y0, x1, y1


def buff_bar_roi(frame, cfg):
    h, w = frame.shape[:2]
    bar = cfg["buff_bar"]
    x1 = w - bar["right"]
    x0 = x1 - bar["width"]
    y0 = bar["top"]
    y1 = y0 + bar["height"]
    return _clip_rect(x0, y0, x1, y1, w, h)


def hotbar_slot_rect(frame, key, cfg):
    h, w = frame.shape[:2]
    slot = cfg["hotbar"].get(key)
    if not slot:
        return 0, 0, 0, 0
    icon_size = cfg["icon_size"]
    cx = int(w * slot["cx_frac"])
    cy = h - slot["cy_from_bottom"]
    half = icon_size // 2
    x0 = cx - half
    y0 = cy - half
    x1 = x0 + icon_size
    y1 = y0 + icon_size
    return _clip_rect(x0, y0, x1, y1, w, h)


def crop_hotbar_icon(frame, key, cfg):
    x0, y0, x1, y1 = hotbar_slot_rect(frame, key, cfg)
    icon_size = cfg["icon_size"]
    if x1 - x0 < icon_size or y1 - y0 < icon_size:
        return None
    return frame[y0:y1, x0:x1].copy()


def glyph_plane(bgr, threshold=150):
    """White-on-black map of bright glyph pixels (pack fill / HUD glow)."""
    if bgr is None or bgr.size == 0:
        return None
    if len(bgr.shape) == 2:
        gray = bgr
    else:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, int(threshold), 255, cv2.THRESH_BINARY)
    return binary


def _resize_to(bgr, size):
    size = max(8, int(size))
    if bgr.shape[0] == size and bgr.shape[1] == size:
        return bgr
    return cv2.resize(bgr, (size, size), interpolation=cv2.INTER_AREA)


def _template_score(haystack_gray, needle_gray):
    if haystack_gray is None or needle_gray is None:
        return 0.0
    if haystack_gray.size == 0 or needle_gray.size == 0:
        return 0.0
    nh, nw = needle_gray.shape[:2]
    hh, hw = haystack_gray.shape[:2]
    if nh > hh or nw > hw or nh <= 0 or nw <= 0:
        return 0.0

    if float(np.max(needle_gray)) < 1.0 and float(np.max(haystack_gray)) < 1.0:
        return 0.0

    if float(np.std(needle_gray)) < 1e-06:
        # Flat needle: CCOEFF is undefined, fall back to squared difference.
        result = cv2.matchTemplate(haystack_gray, needle_gray, cv2.TM_SQDIFF_NORMED)
        score = float(1.0 - result.min())
        return 0.0 if score != score else score
    result = cv2.matchTemplate(haystack_gray, needle_gray, cv2.TM_CCOEFF_NORMED)
    score = float(result.max())
    return 0.0 if score != score else score


def best_match_score(haystack_bgr, needle_bgr, cfg=None):
    """Best glyph-plane match, trying a few sizes around ``icon_size``."""
    if haystack_bgr is None or needle_bgr is None:
        return 0.0
    if haystack_bgr.size == 0 or needle_bgr.size == 0:
        return 0.0

    cfg = cfg or DEFAULT_BUFF_VISION
    glyph_thr = cfg.get("glyph_threshold", 150)
    base = int(cfg.get("icon_size", 36))
    hay_g = glyph_plane(haystack_bgr, glyph_thr)
    if hay_g is None:
        return 0.0

    best = 0.0
    hh, hw = hay_g.shape[:2]
    for scale in _MATCH_SCALES:
        size = max(8, int(round(base * scale)))
        if size > hh or size > hw:
            continue
        needle = glyph_plane(_resize_to(needle_bgr, size), glyph_thr)
        best = max(best, _template_score(hay_g, needle))

    nh, nw = needle_bgr.shape[:2]
    if nh <= hh and nw <= hw:
        needle = glyph_plane(needle_bgr, glyph_thr)
        best = max(best, _template_score(hay_g, needle))
    return best


def icon_present_in_buff_bar(frame, template_bgr, cfg):
    x0, y0, x1, y1 = buff_bar_roi(frame, cfg)
    if x1 <= x0 or y1 <= y0:
        return False
    haystack = frame[y0:y1, x0:x1]
    score = best_match_score(haystack, template_bgr, cfg)
    return score >= cfg["match_threshold"]


class MissStreak:
    def __init__(self, needed=None):
        self.needed = needed if needed is not None else DEFAULT_BUFF_VISION["miss_needed"]
        self._count = 0

    def reset(self):
        self._count = 0

    def observe(self, missing):
        if missing:
            self._count += 1
            if self._count >= self.needed:
                return True
            return False
        self.reset()
        return False
