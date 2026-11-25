"""Which map the character is on: the map name the game prints bottom-left, just above the HUD (PLAN 1.3b).

"타락한 축복의 땅의 봄", "오염된 축복의 땅" (no sub-area there), ... The band is brought to 1187 px wide like the
chat (CHAT_BASE_W), turned into whiteness and matched against the templates in ``data/map_names/`` (cut from
real frames with tests/build_map_names.py; ``index.json`` maps file -> name).
"""
import json
import os

import cv2
import numpy as np

from ..app_paths import asset_path
from .name_reader import CHAT_BASE_W, text_lines, whiteness

ROI = (0.0, 0.70, 0.189, 0.80)  # share of the client area: above the HUD frame, left of its ornament (x 227/1187)
WHITE = 150  # the label is grey-white, not pure white
MIN_SCORE = 0.7  # TM_CCOEFF_NORMED, of the whole label and of its last TAIL_PX columns
TAIL_PX = 40  # the season word (봄 / 여름 / 가을 / 겨울)
FOLDER = os.path.join("lineage_auto", "data", "map_names")


def band(frame_bgr):
    """Whiteness of the map-name area at 1187-wide scale."""
    h, w = frame_bgr.shape[:2]
    x0, y0, x1, y1 = int(ROI[0] * w), int(ROI[1] * h), int(ROI[2] * w), int(ROI[3] * h)
    roi = frame_bgr[y0:y1, x0:x1]
    if w != CHAT_BASE_W and roi.size:
        roi = cv2.resize(roi, None, fx=CHAT_BASE_W / w, fy=CHAT_BASE_W / w, interpolation=cv2.INTER_AREA)
    return whiteness(roi, WHITE)


def cut_label(frame_bgr):
    """uint8 template of the widest text line in the band, or None (for tests/build_map_names.py)."""
    white = band(frame_bgr)
    lines = text_lines(white, min_w=60, max_w=320)
    if not lines:
        return None
    x0, y0, x1, y1 = max(lines, key=lambda b: b[2] - b[0])
    return (white[max(0, y0 - 1):y1 + 1, max(0, x0 - 1):x1 + 1] * 255).astype(np.uint8)


class MapNameReader:
    def __init__(self, folder=None):
        self.folder = folder or asset_path(FOLDER)
        self.templates = []  # [(name, float32 whiteness)]
        index = os.path.join(self.folder, "index.json")
        if os.path.exists(index):
            for file, name in json.load(open(index, encoding="utf-8")).items():
                img = cv2.imdecode(np.fromfile(os.path.join(self.folder, file), np.uint8), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    self.templates.append((name, img.astype(np.float32) / 255))

    @property
    def available(self):
        return bool(self.templates)

    def read(self, frame_bgr):
        """(name, score) of the best template, name None when below MIN_SCORE."""
        white = band(frame_bgr)
        best, best_score = None, 0.0
        for name, tpl in self.templates:
            if tpl.shape[0] > white.shape[0] or tpl.shape[1] > white.shape[1]:
                continue
            _lo, full, _lo_at, (x, y) = cv2.minMaxLoc(cv2.matchTemplate(white, tpl, cv2.TM_CCOEFF_NORMED))
            # "타락한 축복의 땅의" is shared by the 4 seasons: the season word at the end must match too
            t = tpl[:, -TAIL_PX:]
            region = white[y:y + tpl.shape[0], x + tpl.shape[1] - TAIL_PX:x + tpl.shape[1]]
            tail = float(cv2.matchTemplate(region, t, cv2.TM_CCOEFF_NORMED).max()) if region.shape == t.shape else 0.0
            score = min(float(full), tail)
            if score > best_score:
                best, best_score = name, score
        return (best if best_score >= MIN_SCORE else None), round(best_score, 3)
