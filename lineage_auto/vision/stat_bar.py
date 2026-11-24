"""Read a coloured status bar (HP, MP, ...) by template matching its frame.

The template locates the bar; the fill percentage comes from scanning several
horizontal lines and measuring how far the coloured pixels extend. Multiple
lines make the reading robust against the bar's gloss and border pixels.

Location follows v1 first: one native-size ``matchTemplate`` over the whole
client. If that score is weak (live log: ~42% at 0.80 HUD scale, ~56% at 1.50),
a second pass searches nearby scales **only in the bottom status HUD** so a
resized template cannot lock onto a look-alike in the play area.

HP fill is red or poison-green only. Gray / petrify is not a fill.
Green-dominant fill sets ``last_fill_is_green`` for Cure Poison 388.
"""

import os
import time
from enum import Enum

import cv2
import numpy as np


class BarColor(Enum):
    RED = "red"
    BLUE = "blue"


SCAN_LINES = (0.4, 0.45, 0.5, 0.55, 0.6)
MATCH_THRESHOLD = 0.6
# A native-size score at or above this is trusted without the multi-scale pass.
NATIVE_LOCK = 0.75
BORDER_PADDING = 16
# Multi-scale search only looks at the bottom part of the client (status HUD).
HUD_TOP_FRAC = 0.68
MATCH_SCALES = (
    0.62, 0.66, 0.72, 0.8, 0.88, 0.94, 1.0, 1.06,
    1.12, 1.18, 1.25, 1.35, 1.45, 1.5, 1.55, 1.65,
)


def _red_fill_mask(line_bgr):
    b = line_bgr[:, 0].astype(int)
    g = line_bgr[:, 1].astype(int)
    r = line_bgr[:, 2].astype(int)
    return (r > 130) & (r > g * 1.8) & (r > b * 1.8)


def _green_fill_mask(line_bgr):
    b = line_bgr[:, 0].astype(int)
    g = line_bgr[:, 1].astype(int)
    r = line_bgr[:, 2].astype(int)
    return (g > 130) & (g > r * 1.5) & (g > b * 1.3)


def _blue_fill_mask(line_bgr):
    """Lineage MP is muted periwinkle (B slightly above G), not saturated blue."""
    b = line_bgr[:, 0].astype(int)
    g = line_bgr[:, 1].astype(int)
    r = line_bgr[:, 2].astype(int)
    return (b > 90) & (b >= g) & (b + 12 >= r) & (b - g >= 8)


def _fill_mask(line_bgr, color):
    if color is BarColor.BLUE:
        return _blue_fill_mask(line_bgr)
    red = _red_fill_mask(line_bgr)
    if color is BarColor.RED:
        return red | _green_fill_mask(line_bgr)
    return red


def _fill_width(filled, tw, from_right):
    """Remaining fill in pixels along one scan line.

    HP grows left-to-right, so remaining is the span of coloured pixels.
    MP drains right-to-left (remaining packed against the right edge), so
    remaining is from the leftmost coloured pixel to the template's right.
    """
    if from_right:
        return max(0, int(tw) - 1 - int(filled[0]))
    return int(filled[-1] - filled[0])


def _match(gray, template):
    """Return (score, loc_xy). Score is -1 when the template cannot fit."""
    th, tw = template.shape[:2]
    if gray.shape[0] < th or gray.shape[1] < tw:
        return -1.0, (0, 0)
    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    _, best, _, loc = cv2.minMaxLoc(result)
    if not np.isfinite(best):
        return -1.0, (0, 0)
    return float(best), (int(loc[0]), int(loc[1]))


class StatBarReader:
    def __init__(self, template_path, color=BarColor.RED, label="HP", log_every=2.0, from_right=False):
        self.label = label
        self.color = color
        self.from_right = bool(from_right)
        self.log_every = log_every
        self.template = None
        self._last_log = 0.0
        self.last_fill_is_green = False
        self.last_match = 0.0
        self.last_scale = 1.0
        if template_path and os.path.exists(template_path):
            self.template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
            print(f"[{label}] template loaded: {os.path.basename(template_path)}")
        else:
            print(f"[{label}] template missing: {template_path}")

    @property
    def available(self):
        return self.template is not None

    def _log(self, message):
        now = time.time()
        if now - self._last_log > self.log_every:
            print(message)
            self._last_log = now

    def _locate(self, gray):
        """Return (score, loc_xy, scale, height, width) for the HP/MP frame."""
        th, tw = self.template.shape
        score, loc = _match(gray, self.template)
        if score >= NATIVE_LOCK:
            return score, loc, 1.0, th, tw

        y0 = int(gray.shape[0] * HUD_TOP_FRAC)
        y0 = max(0, min(y0, gray.shape[0] - 1))
        hud = gray[y0:]
        best_score = score
        best = (score, loc, 1.0, th, tw)
        for scale in MATCH_SCALES:
            tws = max(1, int(round(tw * scale)))
            ths = max(1, int(round(th * scale)))
            if ths > hud.shape[0] or tws > hud.shape[1]:
                continue
            if scale == 1.0:
                scaled = self.template
            else:
                interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                scaled = cv2.resize(self.template, (tws, ths), interpolation=interp)
            hud_score, hud_loc = _match(hud, scaled)
            if hud_score > best_score:
                best_score = hud_score
                best = (hud_score, (hud_loc[0], hud_loc[1] + y0), scale, ths, tws)
        return best

    def read_percent(self, grabber, rect):
        """Fill percentage 0-100. Returns 100 when the bar cannot be read."""
        if self.template is None:
            self.last_fill_is_green = False
            self.last_match = 0.0
            self.last_scale = 1.0
            return 100
        try:
            frame = grabber.grab_bgra(rect)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
            score, loc, scale, th, tw = self._locate(gray)
            self.last_match = score
            self.last_scale = scale
            if score < MATCH_THRESHOLD:
                self.last_fill_is_green = False
                self._log(f"[{self.label}] bar not found ({score * 100:.1f}%)")
                return 100

            roi = frame[loc[1]:loc[1] + th, loc[0]:loc[0] + tw]
            pad = max(int(round(BORDER_PADDING * scale)), 1)
            span = max(tw - pad, 1)
            readings = []
            green_count = 0
            red_count = 0
            for ratio in SCAN_LINES:
                line = roi[int(th * ratio), :, :]
                fill = _fill_mask(line, self.color)
                filled = np.where(fill)[0]
                if len(filled):
                    width = _fill_width(filled, tw, self.from_right)
                    readings.append(int(width / span * 100))
                if self.color is BarColor.RED:
                    green_count += int(np.count_nonzero(_green_fill_mask(line)))
                    red_count += int(np.count_nonzero(_red_fill_mask(line)))

            self.last_fill_is_green = green_count > red_count and green_count > 0
            value = max(readings) if readings else 0
            value = min(max(value, 0), 100)
            if value >= 95:
                value = 100
            extra = f" scale {scale:.2f}" if abs(scale - 1.0) > 1e-06 else ""
            self._log(f"[{self.label}] {value}% (match {score * 100:.1f}%{extra})")
            return value
        except Exception as exc:
            self.last_fill_is_green = False
            self.last_match = 0.0
            self.last_scale = 1.0
            self._log(f"[{self.label}] read error: {exc}")
            return 100
