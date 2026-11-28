"""Cursor grid sweep for training labels (PLAN 0.8c). Data collection only, never clicks.

When YOLOX finds nothing, hover a grid around the character and log what the game
cursor says at each point (sword/bow = monster). One frame is saved right before
the sweep so the hover points label it. Use only on a safe spot: the sweep costs
~2-4 s during which the bot does not fight.
"""
import math
import time

from ..vision.geometry import BOTTOM_MARGIN, EDGE_MARGIN
from ..winapi.cursor import CursorProbe
from ..winapi.hotkeys import poll_escape
from .base import Feature

# PLAN 1.10: "safe spot only" was only a label on the checkbox - nothing checked it. 20261128_121828 swept
# 18 times (80 points, ~0.93 s each) out in the field. Now it needs a quiet moment: nothing detected anywhere,
# HP steady, and at most one sweep per COOLDOWN.
COOLDOWN = 60.0


def grid_points(cx, cy, gw, gh, step, radius):
    """Square grid inside a circle around (cx, cy), play area only, nearest first, centre skipped."""
    points = []
    for dy in range(-radius, radius + 1, step):
        for dx in range(-radius, radius + 1, step):
            d = math.hypot(dx, dy)
            x, y = cx + dx, cy + dy
            if 0 < d <= radius and EDGE_MARGIN < x < gw - EDGE_MARGIN and EDGE_MARGIN < y < gh - BOTTOM_MARGIN:
                points.append((d, x, y))
    return [(x, y) for _, x, y in sorted(points)]


class GridScanFeature(Feature):
    key = "grid"

    def safe(self):
        """PLAN 1.10: a quiet moment - no monster in the last detection, HP steady, and COOLDOWN since the last
        sweep. A sweep is ~1 s of not fighting, so it must never happen while something is around."""
        state = self.ctx.state
        if state.get("hp_falling") or state.get("mobs_seen") or state.get("mobs_near"):
            return False
        now = time.monotonic()
        if now - getattr(self, "_last", -COOLDOWN) < COOLDOWN:
            return False
        self._last = now
        return True

    def sweep(self, rect, char):
        """Hover every grid point once. Returns the number of attack-cursor points (0 when off)."""
        rec = self.ctx.recorder
        cfg = self.account.record
        if rec is None or not cfg.grid_scan:
            return 0
        if not self.safe():
            return 0
        points = grid_points(char[0], char[1], rect.w, rect.h, cfg.grid_step, cfg.grid_radius)
        rec.begin_scan()
        rec.frame(self.ctx.grabber.grab_bgr(rect), [], char=char, force=True, extra={"grid": len(points)})
        settle = self.account.scan.hover_settle
        t0 = time.perf_counter()
        found = done = 0
        for x, y in points:
            poll_escape(self.ctx)
            if not self.ctx.running:
                break
            self.input.move(*rect.to_screen(x, y))
            time.sleep(settle)
            # shortcut: one cursor read per point (probe uses up to hover_reads); add retries if the sword is often late.
            cursor = CursorProbe.current_hash()
            kind = self.ctx.cursors.classify(cursor) or "unknown"
            rec.hover((x, y), kind, src="grid", cursor=cursor)
            found += kind == "attack"
            done += 1
        ms = 1000 * (time.perf_counter() - t0)
        rec.count("grid_sweeps")
        rec.count("grid_points", done)
        rec.timing("grid_ms", ms)
        self.log(f"grid sweep {done}/{len(points)} points, {found} attack, {ms:.0f}ms")
        return found
