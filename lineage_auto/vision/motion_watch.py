"""Detect when a fight target has stopped animating (likely dead/fallen)."""
import numpy as np

DEFAULT_MOVE_THRESHOLD = 4.0
DEFAULT_FREEZE_NEEDED = 4


def roi_motion_score(prev_gray, curr_gray):
    """Mean absolute pixel difference between two same-shaped gray crops."""
    if prev_gray is None or curr_gray is None:
        return 0.0
    if prev_gray.shape != curr_gray.shape:
        return 999.0
    return float(np.mean(np.abs(curr_gray.astype(np.int16) - prev_gray.astype(np.int16))))


class DeathWatch:
    """Stateful freeze detector.

    observe() returns:
      - "unknown" — not armed yet, or armed but freeze not long enough
      - "alive"   — saw motion this sample (armed)
      - "dead"    — armed and freeze_needed consecutive still samples
    """

    def __init__(self, move_threshold=DEFAULT_MOVE_THRESHOLD, freeze_needed=DEFAULT_FREEZE_NEEDED, crop_half=40):
        self.move_threshold = float(move_threshold)
        self.freeze_needed = int(freeze_needed)
        self.crop_half = int(crop_half)
        self.reset()

    def reset(self):
        self._prev = None
        self._armed = False
        self._still = 0

    def observe(self, gray_crop):
        if gray_crop is None:
            return "unknown"
        if self._prev is None:
            self._prev = gray_crop.copy()
            return "unknown"

        score = roi_motion_score(self._prev, gray_crop)
        self._prev = gray_crop.copy()

        if score >= self.move_threshold:
            self._armed = True
            self._still = 0
            return "alive"

        if not self._armed:
            return "unknown"

        self._still += 1
        if self._still >= self.freeze_needed:
            return "dead"
        return "unknown"
