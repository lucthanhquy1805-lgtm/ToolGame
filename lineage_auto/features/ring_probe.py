"""PLAN 0.46 B2.3: find a monster the detector cannot see, with the mouse cursor.

Measured on the records (tests/eval_near_recall.py, input 416 = the game PC): even with the native-resolution
near crop, ~5% of the monsters the sword cursor confirms within 150 px have no detection box, and at night the
zone within 100 px was the worst (80% before the crop). The cursor is the only sensor that never misses them.

Two triggers, both rare: HP falling with no box next to us, and standing with no target for a while. One ring
is 8 directions x 2 radii, read like the label grid sweep (ONE cursor read per point, ~0.05 s) and the first
sword point is then confirmed by the full probe before anything is attacked.
"""
import math
import time

from ..vision.geometry import BOTTOM_MARGIN, EDGE_MARGIN
from ..winapi.cursor import CursorProbe
from ..winapi.hotkeys import poll_escape
from .base import Feature

DIRECTIONS = 8
RADII = (45, 90)
# One ring at most this often (the user: max 1 ring / 2 s).
COOLDOWN = 2.0


def ring_points(cx, cy, gw, gh, radii=RADII, directions=DIRECTIONS):
    """Points on circles around the character, nearest radius first, inside the play area."""
    points = []
    for r in radii:
        for i in range(directions):
            angle = 2 * math.pi * i / directions
            x, y = int(cx + r * math.cos(angle)), int(cy + r * math.sin(angle))
            if EDGE_MARGIN < x < gw - EDGE_MARGIN and EDGE_MARGIN < y < gh - BOTTOM_MARGIN:
                points.append((x, y))
    return points


class RingProbeFeature(Feature):
    key = "ring"

    def __init__(self, ctx, clock=time.monotonic):
        super().__init__(ctx)
        self.clock = clock
        self._last = 0.0
        self.targeting = None  # set by the session (probe + hard cases live there)

    def ready(self):
        return self.clock() - self._last >= COOLDOWN

    def sweep(self, rect, char, why):
        """Hover a ring around the character; returns a confirmed Target or None.

        The quick pass reads the cursor once per point (the full probe is ~0.2 s per miss, which is far too
        slow while something is hitting us); the first sword point is then re-read by targeting.probe, which
        is what every other attack path uses, so nothing is ever attacked on one cursor read alone."""
        if self.targeting is None or not self.ready():
            return None
        self._last = self.clock()
        points = ring_points(char[0], char[1], rect.w, rect.h)
        settle = self.account.scan.hover_settle
        self.input.release_left()
        found = None
        for x, y in points:
            poll_escape(self.ctx)
            if not self.ctx.running:
                break
            self.input.move(*rect.to_screen(x, y))
            time.sleep(settle)
            if self.ctx.cursors.is_attack(CursorProbe.current_hash()):
                found = (x, y)
                break
        self._event("ring_probe", why=why, points=len(points), found=bool(found))
        if found is None:
            return None
        target = self.targeting.probe([found], rect)
        if target is None:
            return None
        dist = math.hypot(found[0] - char[0], found[1] - char[1])
        self.log(f"cursor ring found a monster at {found} ({dist:.0f}px, {why})")
        self._event("ring_hit", point=list(found), dist=round(dist), why=why)
        hard = getattr(self.ctx, "hard_case", None)
        if hard is not None:
            hard(rect, found, kind="ring", src=why)
        return target

    def _event(self, kind, **data):
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.count(kind)
            rec.event(kind, **data)
