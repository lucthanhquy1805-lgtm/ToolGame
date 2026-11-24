"""Locate monster nameplates.

Korean Lineage Classic draws monster names in white text, so a white-text mask
gives cheap candidate positions. These are hints only: a candidate is confirmed
by hovering it and reading the mouse cursor.
"""

import math
from dataclasses import dataclass

import cv2
import numpy as np

WHITE_MIN_VALUE = 210
WHITE_MAX_SATURATION = 80
NAME_TO_BODY_OFFSET = 28
MIN_DISTANCE_FROM_CHAR = 22


@dataclass(frozen=True)
class Nameplate:
    x: int
    y: int
    dist: int

    def as_point(self):
        return self.x, self.y


class NameplateScanner:
    """Bottom UI, minimap and top-left panel are blanked before analysis."""

    def __init__(self, hud_bottom_ratio=0.78, hud_right_ratio=0.82, panel_w=230, panel_h=140, char_mask_radius=18):
        self.hud_bottom_ratio = hud_bottom_ratio
        self.hud_right_ratio = hud_right_ratio
        self.panel_w = panel_w
        self.panel_h = panel_h
        self.char_mask_radius = char_mask_radius

    def _blank_hud(self, img, cx, cy, gw, gh):
        out = img.copy()
        out[int(gh * self.hud_bottom_ratio):gh, :] = 0
        out[0:self.panel_h, 0:self.panel_w] = 0
        out[:, int(gw * self.hud_right_ratio):gw] = 0
        cv2.circle(out, (cx, cy), self.char_mask_radius, 0, -1)
        return out

    @staticmethod
    def _text_blobs(binary, cx, cy, gh, radius, min_h=4, max_h=26, min_w=16, max_w=240, min_aspect=1.6):
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (22, 3))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        closed = cv2.dilate(closed, cv2.getStructuringElement(cv2.MORPH_RECT, (8, 2)), iterations=1)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        hits = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < min_w or w > max_w or h < min_h or h > max_h:
                continue
            if w / max(h, 1) < min_aspect:
                continue
            tx = x + w // 2
            ty = min(gh - 220, y + h + NAME_TO_BODY_OFFSET)
            dist = int(math.hypot(tx - cx, ty - cy))
            if dist < MIN_DISTANCE_FROM_CHAR or dist > radius:
                continue
            hits.append(Nameplate(tx, ty, dist))
        return hits

    def find(self, frame_bgr, cx, cy, gw, gh, radius=400, max_n=5, merge_gap=22):
        """Nameplate hints sorted nearest first."""
        masked = self._blank_hud(frame_bgr, cx, cy, gw, gh)
        hsv = cv2.cvtColor(masked, cv2.COLOR_BGR2HSV)
        value, saturation = hsv[:, :, 2], hsv[:, :, 1]
        white = ((value >= WHITE_MIN_VALUE) & (saturation <= WHITE_MAX_SATURATION)).astype(np.uint8) * 255

        hits = self._text_blobs(white, cx, cy, gh, radius)
        hits.sort(key=lambda p: p.dist)

        merged = []
        for hit in hits:
            if any(math.hypot(hit.x - kept.x, hit.y - kept.y) < merge_gap for kept in merged):
                continue
            merged.append(hit)
            if len(merged) >= max_n:
                break
        return merged
