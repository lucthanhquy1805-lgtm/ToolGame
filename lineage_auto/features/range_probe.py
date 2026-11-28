"""PLAN 1.9: the Hunt tab's "measure attack range" button.

Hit monsters by hand from near to far and keep the farthest one that was hit WITHOUT the character walking:
hover a box, attack cursor -> click once, then watch HIT_WATCH_SEC. The picture moving more than
combat.RANGE_WALK_STEPS (vision/drift) = the character walked = out of reach: stop it and stop measuring there
(farther boxes are farther still). Standing still with the attack cursor on a box that is still there after
HIT_WATCH_SEC = in reach (the weak rule the user chose; the monster HP bar is not read).
The result is in steps (PLAN 1.11: the measured px / vision/drift.reach_px(1)), rounded, at least 1,
plus the px it was measured at (kept in scan.attack_range_px and shown on the UI).
"""

import math
import time

from ..vision import yolox_mobs
from ..vision.drift import drift_steps, reach_px
from ..vision.geometry import play_max_radius
from ..winapi.cursor import CursorProbe
from .combat import RANGE_WALK_STEPS
from .targeting import SELF_R

MAX_BOXES = 8
HOVER_SETTLE = 0.08
HIT_WATCH_SEC = 1.5
WATCH_TICK = 0.25
STILL_THERE_PX = 60  # a box this close to the clicked one after HIT_WATCH_SEC = the same monster


def _near_box(hits, point, radius=STILL_THERE_PX):
    near = [h for h in hits if math.hypot(h[0] - point[0], h[1] - point[1]) <= radius]
    return min(near, key=lambda h: math.hypot(h[0] - point[0], h[1] - point[1])) if near else None


def measure(ctx, stop=None, log=print, detect=None, sleep=time.sleep):
    """-> (steps or None, px or None, reason, rows). ``px`` (PLAN 1.11) is how far that farthest hit monster
    really was on screen, which the UI shows and the config keeps (scan.attack_range_px).
    ``stop`` = a threading.Event to cancel; ``detect(frame, char)`` -> hits (default: the hunt map's YOLOX)."""
    if detect is None:
        map_key, conf = ctx.account.hunt_map, ctx.account.scan.conf_for(ctx.account.hunt_map)

        def detect(frame, char):
            h, w = frame.shape[:2]
            return yolox_mobs.detect(frame, char[0], char[1], play_max_radius(w, h, char[0], char[1]),
                                     map_key=map_key, conf=conf)[0]

    rect = ctx.rect()
    char = ctx.char_pos(rect)
    frame = ctx.grabber.grab_bgr(rect)
    hits = [h for h in detect(frame, char) if math.hypot(h[0] - char[0], h[1] - char[1]) > SELF_R]
    hits.sort(key=lambda h: math.hypot(h[0] - char[0], h[1] - char[1]))
    one_step = reach_px(1, rect.w)  # PLAN 1.11: the reach is a px circle, so the result is px / one step
    if not hits:
        return None, None, "no_monster", []
    best, best_px, rows = None, None, []
    for point in hits[:MAX_BOXES]:
        if stop is not None and stop.is_set():
            return None, None, "cancelled", rows
        dist = math.hypot(point[0] - char[0], point[1] - char[1])  # PLAN 1.11: the measured px, for the UI
        steps = dist / one_step
        sx, sy = rect.to_screen(*point)
        ctx.input.move(sx, sy)
        sleep(HOVER_SETTLE)
        if not ctx.cursors.is_attack(CursorProbe.current_hash()):
            rows.append({"steps": round(steps, 1), "px": round(dist), "result": "no_attack_cursor"})
            continue
        before = ctx.grabber.grab_bgr(rect)
        ctx.input.click_at(sx, sy)
        walked, waited, last = 0.0, 0.0, point
        while waited < HIT_WATCH_SEC:
            sleep(WATCH_TICK)
            waited += WATCH_TICK
            now = ctx.grabber.grab_bgr(rect)
            walked = max(walked, drift_steps(before, now) or 0.0)
            if walked > RANGE_WALK_STEPS:
                break
        if walked > RANGE_WALK_STEPS:
            ctx.input.click_at(*rect.to_screen(*char))  # a click where we stand ends the walk
            rows.append({"steps": round(steps, 1), "px": round(dist), "result": "walked",
                         "drift": round(walked, 1)})
            log(f"[RANGE] {steps:.1f} steps: the character walked {walked:.1f} steps -> out of reach, stop")
            break
        now = ctx.grabber.grab_bgr(rect)
        box = _near_box(detect(now, char), last)
        sword = ctx.cursors.is_attack(CursorProbe.current_hash())
        hit = box is not None and sword
        rows.append({"steps": round(steps, 1), "px": round(dist), "result": "hit" if hit else "unclear"})
        log(f"[RANGE] {steps:.1f} steps: {'hit, standing still' if hit else 'stood still, no attack seen'}")
        if hit and steps >= (best or 0.0):
            best, best_px = steps, round(dist)
    ctx.input.release_left()
    if best is None:
        return None, None, "no_hit", rows
    return max(1, int(best + 0.5)), best_px, "ok", rows
