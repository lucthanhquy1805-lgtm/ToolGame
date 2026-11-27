"""Move on when the whole screen holds no monster.

PLAN 0.27 (first orc hunt: 560 wanders round 4 fixed points, 209/654 frames without a monster): with the game
minimap on, every walk is scored over the eight directions in "world" minimap coordinates (vision.minimap
odometry):
  heat     monsters seen there in the last minutes (each YOLOX box of every scan is remembered)
  frontier the walk lands where the character has not been recently
  inner    toward the middle of the walkable area on the minimap (into the hunting ground, not to its edge)
  blocked  the straight walk crosses a fence / tree on the minimap  -> skipped
  radius   beyond MAX_RADIUS_MM from where the hunt started        -> penalised (PLAN 1.2 will make it a setting)
Without the minimap (turned off in game, PLAN 0.32: all 849 frames of 092741) one direction is held for
DWELL_SEC, toward the last target first; it changes when the picture stops changing for BLOCK_SEC (the walk is
blocked) and then takes the direction blocked longest ago. v14 rotated at every walk (~0.3 s apart), which only
turned the character on the spot. Each walk logs the chosen direction and why (field log + events.jsonl).
After the walk click the session returns to the mouse scan at once — short walks, then a new scan.
PLAN 0.39 (233615: 138 direction changes in 358 walks, 10.7/min, up and down over the same ground): a direction
picked on the minimap is kept for a random HOLD_MIN..HOLD_MAX s while its straight walk stays clear (the clicks
follow one line), and a walk that ends where the character was RETURN_MIN..RETURN_SEC s ago scores W_BACK less.
Each click lands a few px off the line and the pause after it varies, like a hand.
"""
import math
import random
import time

import cv2

from ..vision.geometry import WALK_DIRECTIONS, direction_index, walk_point
from ..vision.motion_watch import roi_motion_score
from .base import Feature
from .targeting import MELEE_DIST

CLICK_SETTLE = 0.05
DIRECTION_STEP = 2
# Empty-screen walks spent heading toward the last target before rotating.
PURSUE_CLICKS = 3
NAMES = ("E", "SE", "S", "SW", "W", "NW", "N", "NE")
HEAT_TTL = 180.0  # s a seen monster counts
HEAT_HALF = 60.0  # s: weight halves every ...
VISIT_TTL = 120.0  # s a visited spot counts as explored
VISIT_R = 6.0  # minimap px around a visited spot
LOOK = (8, 16, 24)  # minimap px sampled along a direction for frontier
MAX_RADIUS_MM = 120  # ~1200 client px from the start position (PLAN 1.2: scan.hunt_range when set)
# PLAN 0.44: 20261127_101929_hunt walked "home" 113 times, alternating N and S, while the odometry reading of
# the distance to the start wandered between 3.3 and 7 steps - that was noise, not the character moving. So a
# dead zone of 2 walk clicks before the first step home, and then keep going until nearly home (hysteresis).
GO_HOME_START = 4  # steps (2 walk clicks)
GO_HOME_STOP = 1
WALK_PX = 160  # client px of one walk click
W_HEAT, W_FRONTIER, W_INNER, W_OUT = 1.5, 1.0, 0.6, 2.0
# PLAN 0.32, no minimap: hold one direction this long, call it blocked when the screen changed less than
# BLOCK_MOTION (mean gray difference of a 64x48 thumbnail) over the last BLOCK_SEC, and avoid a blocked
# direction for BLOCK_TTL. On the 092741 night frames standing still scores < 1 and walking > 1.
DWELL_SEC = 4.0  # shortest hold without the minimap (random up to HOLD_MAX)
BLOCK_SEC = 2.5
BLOCK_MOTION = 1.0
BLOCK_TTL = 30.0
SHOT_SIZE = (64, 48)
SHOT_KEEP = 0.8  # drop the bottom fifth (chat lines change on their own)
HOLD_MIN, HOLD_MAX = 4.0, 8.0  # PLAN 0.39: s one walk direction is kept
RETURN_MIN, RETURN_SEC = 8.0, 90.0  # PLAN 0.39: ground left this long ago is not walked back to
W_BACK = 2.0
JITTER_PX = 10
SETTLE_MAX = 0.15


def score_directions(pos, now, heat, visited, inner, clear, start, walk_mm, max_r=MAX_RADIUS_MM):
    """[(score, idx, parts)] best first. Pure so tests can drive it.

    pos: character world position; heat: [(x, y, t)] monsters; visited: [(x, y, t)]; inner: unit vector or None;
    clear(idx) -> straight walk free on the minimap; start: world start or None; walk_mm: walk length."""
    out = []
    for idx, (dx, dy) in enumerate(WALK_DIRECTIONS):
        n = math.hypot(dx, dy)
        ux, uy = dx / n, dy / n
        h = 0.0
        for x, y, t in heat:
            vx, vy = x - pos[0], y - pos[1]
            d = math.hypot(vx, vy)
            if d < 1:
                continue
            cos = (vx * ux + vy * uy) / d
            if cos > 0.3:
                h += cos * 0.5 ** ((now - t) / HEAT_HALF) / (1 + d / 30)
        fresh = 0
        for k in LOOK:
            px, py = pos[0] + ux * k, pos[1] + uy * k
            fresh += not any(math.hypot(px - x, py - y) < VISIT_R for x, y, _t in visited)
        frontier = fresh / len(LOOK)
        inward = (ux * inner[0] + uy * inner[1]) if inner else 0.0
        end = (pos[0] + ux * walk_mm, pos[1] + uy * walk_mm)
        out_r = start is not None and math.hypot(end[0] - start[0], end[1] - start[1]) > max_r
        back = any(RETURN_MIN <= now - t <= RETURN_SEC and math.hypot(end[0] - x, end[1] - y) < 2 * VISIT_R
                   for x, y, t in visited)
        ok = clear(idx)
        score = (W_HEAT * min(h, 2.0) + W_FRONTIER * frontier + W_INNER * inward - W_OUT * out_r - W_BACK * back
                 - 10 * (not ok))
        out.append((score, idx, {"heat": round(h, 2), "new": round(frontier, 2), "in": round(float(inward), 2),
                                 "out": out_r, "back": back, "clear": ok}))
    out.sort(key=lambda o: -o[0])
    return out


class ExplorationFeature(Feature):
    key = "exploration"

    def __init__(self, ctx, health=None, targeting=None):
        super().__init__(ctx)
        self.health = health
        self.targeting = targeting
        self.on_start()

    def on_start(self):
        self._direction = 0
        self._hunt_dir = None
        self._pursue_left = 0
        self._dir_until = 0.0
        self._blocked = {}  # direction index -> when the walk there was last blocked
        self._shot = None  # thumbnail taken when the current direction was chosen
        self._shot_t = 0.0
        self._heat = []  # (x, y, t) world minimap px
        self._visited = []
        self._start = None
        self._epoch = None
        self._keep = None  # (direction index, until) of the minimap walk being held (PLAN 0.39)
        self._homing = False  # PLAN 0.44: walking back to the start, until nearly there

    def on_stop(self):
        self.on_start()

    def remember_hunt(self, char, target_xy):
        """Face the next empty-screen walks toward this target."""
        idx = direction_index(target_xy[0] - char[0], target_xy[1] - char[1])
        if idx is None:
            return
        self._hunt_dir = idx
        self._pursue_left = PURSUE_CLICKS

    def observe(self):
        """After each scan: remember where the character is and every box it saw (world coordinates)."""
        tg = self.targeting
        if tg is None or tg.odo.pos is None:
            return
        if self._epoch != tg.odo.epoch:  # minimap was off: old coordinates mean nothing now
            self._heat, self._visited, self._start, self._epoch = [], [], None, tg.odo.epoch
        now = tg.clock()
        pos = tg.odo.pos
        if self._start is None:
            self._start = pos
        self.ctx.state["home"] = self._start  # PLAN 1.2: the hunt range is measured from here
        self._visited = [v for v in self._visited if now - v[2] < VISIT_TTL]
        if not self._visited or math.hypot(pos[0] - self._visited[-1][0], pos[1] - self._visited[-1][1]) >= 2:
            self._visited.append((pos[0], pos[1], now))
        self._heat = [h for h in self._heat if now - h[2] < HEAT_TTL]
        for p in tg.last_monsters:
            w = tg.world(p)
            if w is not None:
                self._heat.append((w[0], w[1], now))

    def _now(self):
        tg = self.targeting
        return tg.clock() if tg is not None else time.time()

    def _thumb(self, rect):
        """Small gray picture of the play area, or None when the grab fails."""
        try:
            frame = self.ctx.grabber.grab_bgr(rect)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return cv2.resize(gray[:int(gray.shape[0] * SHOT_KEEP)], SHOT_SIZE, interpolation=cv2.INTER_AREA)
        except Exception:
            return None

    def _blind_dir(self, rect):
        """(direction index, why) without the minimap: hold one direction, turn when blocked (PLAN 0.32)."""
        now = self._now()
        shot = self._thumb(rect)
        blocked = (self._shot is not None and shot is not None and now - self._shot_t >= BLOCK_SEC
                   and roi_motion_score(self._shot, shot) < BLOCK_MOTION)
        if not blocked and now < self._dir_until:
            return self._direction, "hold"
        if blocked:
            self._blocked[self._direction] = now
        if self._pursue_left > 0 and self._hunt_dir is not None and not blocked:
            # Monsters were last seen that way: walk there first (PURSUE_CLICKS walks of DWELL_SEC).
            self._pursue_left -= 1
            idx, why = self._hunt_dir, "pursue"
        else:
            free = [i for i in range(8) if now - self._blocked.get(i, -BLOCK_TTL) >= BLOCK_TTL]
            order = [(self._direction + DIRECTION_STEP + k) % 8 for k in range(8)]
            idx = next((i for i in order if i in free), min(order, key=lambda i: self._blocked.get(i, 0.0)))
            why = "turn" if blocked else "rotate"
        self._direction, self._dir_until = idx, now + random.uniform(DWELL_SEC, HOLD_MAX)
        self._shot, self._shot_t = shot, now
        return idx, why

    def _smart(self, rect, char):
        """(walk point, reason) from the minimap scores, or None without the minimap."""
        tg = self.targeting
        mm = tg.minimap if tg is not None else None
        if mm is None or tg.odo.pos is None:
            return None
        walk_px = WALK_PX
        walk_mm = walk_px / mm.scale

        def clear(idx):
            p = walk_point(char[0], char[1], rect.w, rect.h, idx, walk_px)
            return mm.clear_to(char, p)

        now = tg.clock()
        if self._keep is not None and now < self._keep[1] and clear(self._keep[0]):
            idx = self._keep[0]
            return (walk_point(char[0], char[1], rect.w, rect.h, idx, walk_px), NAMES[idx], "minimap_keep",
                    f"{NAMES[idx]} kept {self._keep[1] - now:.1f}s more")
        ranked = score_directions(tg.odo.pos, now, self._heat, self._visited, mm.inner_vector(), clear,
                                  self._start, walk_mm, tg.range_mm() or MAX_RADIUS_MM)
        score, idx, parts = ranked[0]
        if not parts["clear"]:
            # Every straight walk hits something: take the minimap way toward the best-scored direction.
            p = walk_point(char[0], char[1], rect.w, rect.h, idx, walk_px)
            kind, waypoint = mm.route(char, p)
            if kind != "detour":
                return None
            self._keep = None
            return waypoint, NAMES[idx], "minimap_gap", f"{NAMES[idx]} via gap {parts}"
        self._keep = (idx, now + random.uniform(HOLD_MIN, HOLD_MAX))
        return (walk_point(char[0], char[1], rect.w, rect.h, idx, walk_px), NAMES[idx], "minimap",
                f"{NAMES[idx]} score={score:.2f} {parts}")

    def _monster_in_reach(self):
        """PLAN 0.44: a monster of the last detection close enough to shoot / hit from where we stand."""
        tg = self.targeting
        if tg is None or tg.char is None:
            return False
        if tg.ranged() and not tg.has_spell():
            return any(tg.in_hand_reach(p) for p in (tg.last_monsters or ()))
        reach = tg.shot_reach() if tg.ranged() else MELEE_DIST
        return any(math.hypot(x - tg.char[0], y - tg.char[1]) <= reach for x, y in (tg.last_monsters or ()))

    def _home_walk(self, rect, char):
        """PLAN 1.7: one walk click back toward the hunt start, using the accumulated offset (no minimap).

        The start is at ``char - offset`` on screen, so walking home means walking along -offset.
        """
        ox, oy = self.ctx.offset()
        idx = direction_index(-ox, -oy)
        if idx is None:
            return None
        self._keep = None
        return (walk_point(char[0], char[1], rect.w, rect.h, idx, WALK_PX), NAMES[idx], "go_home",
                f"{NAMES[idx]} back to the start")

    def wander(self, rect, char):
        """Click a nearby walk point, then return so the loop can scan at once."""
        tg = self.targeting
        steps = self.ctx.account.scan.hunt_range
        away = tg.steps_from_home() if tg is not None else None
        if steps:
            # PLAN 1.7: a hunt with a range never wanders - it only walks back to the start. A stand-still
            # class simply keeps scanning for monsters that come to it.
            # PLAN 0.44: never a step home while a monster stands in reach - fight it first; and the walk
            # home only starts past GO_HOME_START steps (odometry / click noise alone read 3-7 steps).
            # A monster in reach comes first - but a melee class walking back from a pull must keep going,
            # or the monster it just pulled would hold it in the field forever (PLAN 1.7).
            if away is None or (self.targeting is not None and self.targeting.ranged()
                                and self._monster_in_reach()):
                self._homing = False
            elif self._homing:
                self._homing = away > GO_HOME_STOP
            else:
                self._homing = away > GO_HOME_START
            if not self._homing:
                self.ctx.sleep(CLICK_SETTLE)
                return
            home = self._home_walk(rect, char)
            if home is None:
                self.ctx.sleep(CLICK_SETTLE)  # "stay put" never wanders blindly, not even to get home
                return
        else:
            home = None  # no range = the old free hunt: wander
        smart = None if home is not None else self._smart(rect, char)
        if home is not None:
            (wx, wy), name, why, reason = home
        elif smart is not None:
            (wx, wy), name, why, reason = smart
        else:
            dir_idx, why = self._blind_dir(rect)
            wx, wy = walk_point(char[0], char[1], rect.w, rect.h, dir_idx)
            name = NAMES[dir_idx]
            reason = f"{name} {why} (no minimap, {DWELL_SEC:.0f}s per direction)"
        # PLAN 0.39: a few px off the line, never across a fence the straight point avoided
        jx, jy = wx + random.randint(-JITTER_PX, JITTER_PX), wy + random.randint(-JITTER_PX, JITTER_PX)
        mm = self.targeting.minimap if self.targeting is not None else None
        if mm is None or why == "minimap_gap" or mm.clear_to(char, (jx, jy)):
            wx, wy = jx, jy
        self.log(f"nothing found, moving to ({wx}, {wy}): {reason}")
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            tg = self.targeting
            pos = tg.odo.pos if tg is not None and tg.minimap is not None else None
            rec.event("wander", to=[wx, wy], dir=name, why=why, reason=reason,
                      pos=[round(pos[0], 1), round(pos[1], 1)] if pos is not None else None,
                      home_dist=round(away, 1) if away is not None else None)  # PLAN 1.2, steps
        self.input.click_at(*rect.to_screen(wx, wy))
        self.ctx.note_walk(char, (wx, wy), rect)  # PLAN 1.7: remember the way back to the start
        self.ctx.sleep(random.uniform(CLICK_SETTLE, SETTLE_MAX))
