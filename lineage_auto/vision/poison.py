"""Detect poison-green character tint in the center play-area ROI."""
import json

import cv2
import numpy as np

DEFAULT_POISON_VISION = {
    "roi": {"cx_frac": 0.5, "cy_frac": 0.55, "width_frac": 0.18, "height_frac": 0.28},
    "green_ratio_min": 0.04,
    "miss_needed": 2,
    "hsv": {"h_min": 35, "h_max": 85, "s_min": 80, "s_max": 255, "v_min": 150, "v_max": 255},
}


def merge_poison_vision(override):
    cfg = json.loads(json.dumps(DEFAULT_POISON_VISION))
    if not override:
        return cfg
    cfg.update({k: v for k, v in override.items() if k != "roi" and k != "hsv"})
    if "roi" in override:
        cfg["roi"] = {**cfg["roi"], **override["roi"]}
    if "hsv" in override:
        cfg["hsv"] = {**cfg["hsv"], **override["hsv"]}
    return cfg


def _clip_rect(x0, y0, x1, y1, width, height):
    x0 = max(0, min(x0, width))
    y0 = max(0, min(y0, height))
    x1 = max(0, min(x1, width))
    y1 = max(0, min(y1, height))
    return x0, y0, x1, y1


def character_roi(frame, cfg):
    h, w = frame.shape[:2]
    roi = cfg["roi"]
    cx = int(w * roi["cx_frac"])
    cy = int(h * roi["cy_frac"])
    half_w = int(w * roi["width_frac"] / 2)
    half_h = int(h * roi["height_frac"] / 2)
    x0 = cx - half_w
    y0 = cy - half_h
    x1 = cx + half_w
    y1 = cy + half_h
    return _clip_rect(x0, y0, x1, y1, w, h)


def poison_green_ratio(bgr_roi, cfg):
    if bgr_roi is None or bgr_roi.size == 0:
        return 0.0
    hsv = cv2.cvtColor(bgr_roi, cv2.COLOR_BGR2HSV)
    bounds = cfg["hsv"]
    lower = np.array([bounds["h_min"], bounds["s_min"], bounds["v_min"]], dtype=np.uint8)
    upper = np.array([bounds["h_max"], bounds["s_max"], bounds["v_max"]], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    return float(np.count_nonzero(mask)) / mask.size


def sprite_poison_candidate(frame_bgr, cfg):
    x0, y0, x1, y1 = character_roi(frame_bgr, cfg)
    if x1 <= x0 or y1 <= y0:
        return False
    roi = frame_bgr[y0:y1, x0:x1]
    return poison_green_ratio(roi, cfg) >= cfg["green_ratio_min"]


class PresentStreak:
    def __init__(self, needed=2):
        self.needed = needed
        self._count = 0

    def observe(self, present):
        if present:
            self._count += 1
            return self._count >= self.needed
        self._count = 0
        return False

    def reset(self):
        self._count = 0
