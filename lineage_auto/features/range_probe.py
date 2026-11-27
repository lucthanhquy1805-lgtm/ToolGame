"""PLAN 1.9: the Hunt tab's "measure attack range" button.

Hit monsters by hand from near to far and keep the farthest one that was hit WITHOUT the character walking:
hover a box, attack cursor -> click once, then watch HIT_WATCH_SEC. The picture moving more than
combat.RANGE_WALK_STEPS (vision/drift) = the character walked = out of reach: stop it and stop measuring there
(farther boxes are farther still). Standing still with the attack cursor on a box that is still there after
HIT_WATCH_SEC = in reach (the weak rule the user chose; the monster HP bar is not read).
The result is in game steps (vision/drift.screen_steps), rounded, at least 1.
"""

import math
import time

from ..vision import yolox_mobs
from ..vision.drift import drift_steps, screen_steps
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
    """-> (steps or None, reason, rows). ``stop`` = a threading.Event to cancel; ``detect(frame, char)`` -> hits
    (default: the hunt map's YOLOX)."""
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
    hits.sort(key=lambda h: screen_steps(h[0] - char[0], h[1] - char[1], rect.w))
    if not hits:
        return None, "no_monster", []
    best, rows = None, []
    for point in hits[:MAX_BOXES]:
        if stop is not None and stop.is_set():
            return None, "cancelled", rows
        steps = screen_steps(point[0] - char[0], point[1] - char[1], rect.w)
        sx, sy = rect.to_screen(*point)
        ctx.input.move(sx, sy)
        sleep(HOVER_SETTLE)
        if not ctx.cursors.is_attack(CursorProbe.current_hash()):
            rows.append({"steps": round(steps, 1), "result": "no_attack_cursor"})
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
            rows.append({"steps": round(steps, 1), "result": "walked", "drift": round(walked, 1)})
            log(f"[RANGE] {steps:.1f} steps: the character walked {walked:.1f} steps -> out of reach, stop")
            break
        now = ctx.grabber.grab_bgr(rect)
        box = _near_box(detect(now, char), last)
        sword = ctx.cursors.is_attack(CursorProbe.current_hash())
        hit = box is not None and sword
        rows.append({"steps": round(steps, 1), "result": "hit" if hit else "unclear"})
        log(f"[RANGE] {steps:.1f} steps: {'hit, standing still' if hit else 'stood still, no attack seen'}")
        if hit:
            best = max(best or 0.0, steps)
    ctx.input.release_left()
    if best is None:
        return None, "no_hit", rows
    return max(1, int(best + 0.5)), "ok", rows
