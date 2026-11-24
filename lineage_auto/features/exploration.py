"""Move on when the whole screen holds no monster.

PLAN 0.27 (first orc hunt: 560 wanders round 4 fixed points, 209/654 frames without a monster): with the game
minimap on, every walk is scored over the eight directions in "world" minimap coordinates (vision.minimap
odometry):
  heat     monsters seen there in the last minutes (each YOLOX box of every scan is remembered)
  frontier the walk lands where the character has not been recently
  inner    toward the middle of the walkable area on the minimap (into the hunting ground, not to its edge)
  blocked  the straight walk crosses a fence / tree on the minimap  -> skipped
  radius   beyond MAX_RADIUS_MM from where the hunt started        -> penalised (PLAN 1.2 will make it a setting)
Without the minimap (turned off in game) the old behaviour stays: head toward the last target for a few walks,
then rotate by two of the eight directions. Each walk logs the chosen direction and why (field log + events.jsonl).
After the walk click the session returns to the mouse scan at once — short walks, then a new scan.
"""
import math

from ..vision.geometry import WALK_DIRECTIONS, direction_index, walk_point
from .base import Feature

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
MAX_RADIUS_MM = 120  # ~1200 client px from the start position
W_HEAT, W_FRONTIER, W_INNER, W_OUT = 1.5, 1.0, 0.6, 2.0


def score_directions(pos, now, heat, visited, inner, clear, start, walk_mm):
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
        out_r = start is not None and math.hypot(end[0] - start[0], end[1] - start[1]) > MAX_RADIUS_MM
        ok = clear(idx)
        score = W_HEAT * min(h, 2.0) + W_FRONTIER * frontier + W_INNER * inward - W_OUT * out_r - 10 * (not ok)
        out.append((score, idx, {"heat": round(h, 2), "new": round(frontier, 2), "in": round(float(inward), 2),
                                 "out": out_r, "clear": ok}))
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
        self._heat = []  # (x, y, t) world minimap px
        self._visited = []
        self._start = None
        self._epoch = None

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
        self._visited = [v for v in self._visited if now - v[2] < VISIT_TTL]
        if not self._visited or math.hypot(pos[0] - self._visited[-1][0], pos[1] - self._visited[-1][1]) >= 2:
            self._visited.append((pos[0], pos[1], now))
        self._heat = [h for h in self._heat if now - h[2] < HEAT_TTL]
        for p in tg.last_monsters:
            w = tg.world(p)
            if w is not None:
                self._heat.append((w[0], w[1], now))

    def _smart(self, rect, char):
        """(walk point, reason) from the minimap scores, or None without the minimap."""
        tg = self.targeting
        mm = tg.minimap if tg is not None else None
        if mm is None or tg.odo.pos is None:
            return None
        walk_px = 160
        walk_mm = walk_px / mm.scale

        def clear(idx):
            p = walk_point(char[0], char[1], rect.w, rect.h, idx, walk_px)
            return mm.clear_to(char, p)

        now = tg.clock()
        ranked = score_directions(tg.odo.pos, now, self._heat, self._visited, mm.inner_vector(), clear,
                                  self._start, walk_mm)
        score, idx, parts = ranked[0]
        if not parts["clear"]:
            # Every straight walk hits something: take the minimap way toward the best-scored direction.
            p = walk_point(char[0], char[1], rect.w, rect.h, idx, walk_px)
            kind, waypoint = mm.route(char, p)
            if kind != "detour":
                return None
            return waypoint, NAMES[idx], "minimap_gap", f"{NAMES[idx]} via gap {parts}"
        return (walk_point(char[0], char[1], rect.w, rect.h, idx, walk_px), NAMES[idx], "minimap",
                f"{NAMES[idx]} score={score:.2f} {parts}")

    def wander(self, rect, char):
        """Click a nearby walk point, then return so the loop can scan at once."""
        smart = self._smart(rect, char)
        if smart is not None:
            (wx, wy), name, why, reason = smart
        elif self._pursue_left > 0 and self._hunt_dir is not None:
            dir_idx = self._hunt_dir
            self._pursue_left -= 1
            wx, wy = walk_point(char[0], char[1], rect.w, rect.h, dir_idx)
            name, why = NAMES[dir_idx], "pursue"
            reason = f"{name} toward last target (no minimap)"
        else:
            dir_idx = self._direction
            self._direction = (self._direction + DIRECTION_STEP) % 8
            wx, wy = walk_point(char[0], char[1], rect.w, rect.h, dir_idx)
            name, why = NAMES[dir_idx], "rotate"
            reason = f"{name} rotate (no minimap)"
        self.log(f"nothing found, moving to ({wx}, {wy}): {reason}")
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.event("wander", to=[wx, wy], dir=name, why=why, reason=reason)
        self.input.click_at(*rect.to_screen(wx, wy))
        self.ctx.sleep(CLICK_SETTLE)
