"""Find something worth attacking.

Acquire is YOLOX box centers (one frame), then the sword cursor confirms.
While fighting, track_current follows the locked YOLOX box. Far from the
character it prefers the box that slid toward the character over one sitting
on the stale last-hover pixel. In melee it only follows a 32px wobble.
"""

import math
import os
import time
from dataclasses import dataclass

import cv2

from .. import hunt_maps
from ..vision.geometry import DEFENSE_RADIUS, play_max_radius
from ..vision.motion_watch import roi_motion_score
from ..vision import minimap, yolox_mobs
from ..vision.yolox_mobs import detect_centers
from ..winapi.cursor import CursorProbe
from ..winapi.hotkeys import poll_escape
from .base import Feature

MOTION_SETTLE = 0.05
# Gap between the two frames of the (legacy) motion grab.
FRAME_GAP = 0.08
MOVE_THRESHOLD = 4.0
CROP_HALF = 40
# Radius around the current corpse skipped by find_alternate.
EXCLUDE_CURRENT_RADIUS = 48
MOTION_DEDUPE = 18
# While locked in melee the box may only wobble this far before the lock is
# considered to have jumped to a neighbour.
LOCK_FOLLOW_RADIUS = 32
# How far along the char<-lock lane a chased box may be.
CHASE_RADIUS = 180
# Lock closer than this to the character counts as melee.
MELEE_LOCK_DIST = 64
# Max sideways distance from the lane for a chased box.
LANE_PERP_MAX = 28
# A box slightly behind the last lock (away from the character) is still ok.
ALONG_BACK = -24
# Boxes that advanced less than this toward the character are "stale".
STALE_ALONG = 20
# A missed hover point skips new candidates within this many pixels.
MISS_RADIUS = 24
# PLAN 0.27: a target the character could not walk to is skipped this long / this close.
BLOCK_TTL_WORLD = 60.0  # s, position kept in minimap odometry coordinates (PLAN 0.39: 40 -> 60)
BLOCK_TTL_LOCAL = 8.0  # s, no minimap: client coordinates, dropped as soon as the bot walks
BLOCK_RADIUS = 48  # client px
# A YOLOX "die" box this close to a detection = the corpse itself, never a target (PLAN 0.27 / 7).
CORPSE_SKIP_RADIUS = 20
# PLAN 0.29: a "마법 사용: 실패" chat line pauses the attack skills this long.
SKILL_PAUSE_SEC = 5.0
# PLAN 0.35: that many chat failures -> the click order is wrong for this client, so try the other one once
# (hover_key_click puts the mouse on the body before the key, which selects the target first).
SPELL_FAIL_STRIKES = 3
# PLAN 0.31: a box centred this close to the character is the character itself (223510: 22 fights "sword=no" there).
# PLAN 0.33: 30, not 25 — 112040 switched 4 times to a box 26 px from the character (its own sprite).
SELF_R = 30
# Monsters this close to the character are never skipped (miss / blacklist) and come first, whatever the minimap says.
NEAR_KEEP = 100
# Extra rescans (instead of wandering off) while something stays detected within NEAR_KEEP.
NEAR_RESCANS = 3
# Another monster under this share of the lock's distance, inside MELEE_DIST, is fought first (combat switches).
SWITCH_SHARE = 0.5
MELEE_DIST = 70
# Longest wait in a fight beat for the detector thread's next result.
DETECT_WAIT = 0.3
CHAT_FAIL_LOG = 10.0  # s between two "chat not read" log lines
CHAT_FAIL_PNGS = 3


def pick_chase_center(last_xy, hits, char_xy=None, chase_radius=None):
    """Pick the locked monster center from YOLOX hits, or None."""
    if not hits:
        return None
    if chase_radius is None:
        chase_radius = CHASE_RADIUS
    lx, ly = int(last_xy[0]), int(last_xy[1])
    if char_xy is None:
        return hits[0]

    cx, cy = int(char_xy[0]), int(char_xy[1])
    to_char = math.hypot(cx - lx, cy - ly)
    if to_char <= MELEE_LOCK_DIST:
        for x, y in hits:
            if math.hypot(x - lx, y - ly) <= LOCK_FOLLOW_RADIUS:
                return int(x), int(y)
        return None

    inv = 1.0 / to_char
    ux, uy = (cx - lx) * inv, (cy - ly) * inv
    accepted = []
    for x, y in hits:
        dx, dy = x - lx, y - ly
        along = dx * ux + dy * uy
        perp = abs(dx * uy - dy * ux)
        if perp <= LANE_PERP_MAX and ALONG_BACK <= along <= chase_radius:
            accepted.append((along, perp, int(x), int(y)))
    if not accepted:
        return None
    moving = [item for item in accepted if item[0] > STALE_ALONG]
    pool = moving if moving else accepted
    pool.sort(key=lambda item: (item[1], item[0]))
    return pool[0][2], pool[0][3]


def pick_retarget_stage(near_hit, full_hit):
    """Prefer a near living hit; otherwise use the full-window living hit."""
    return near_hit if near_hit is not None else full_hit


@dataclass(frozen=True)
class Target:
    """A confirmed monster position, in both local and screen coordinates."""

    local_x: int
    local_y: int
    screen_x: int
    screen_y: int

    @property
    def local(self):
        return self.local_x, self.local_y

    @property
    def screen(self):
        return self.screen_x, self.screen_y

    def distance_to(self, point):
        return math.hypot(self.local_x - point[0], self.local_y - point[1])


class TargetingFeature(Feature):
    key = "targeting"

    def __init__(self, ctx, clock=time.time):
        super().__init__(ctx)
        self.clock = clock
        self.last_scan_points = 0
        self.last_monsters = []
        self.last_figures = []
        self.last_dies = []
        self._corpse = None
        self._last_lock = None
        self.miss_streak = 0
        self.last_skipped = 0
        self._misses = []  # (local_x, local_y, expires_at)
        # PLAN 0.27: what the last grab showed besides boxes.
        self.last_frame = None
        self.minimap = None  # vision.minimap.Minimap or None (minimap turned off in game)
        self.odo = minimap.Odometry()
        self.char = None
        self.kill_watch = None  # vision.name_reader.KillWatcher, set by the session (zones with chat pictures)
        self.name_reader = None  # vision.name_reader.NameReader (names over monsters), set by the session
        self.chat_kills = []  # (time, name) of kill lines seen since the last pop_kills()
        self._blocked = []  # (x, y, expires_at, epoch or None for client coordinates)
        self.detector = None  # runtime.detector.DetectorThread (PLAN 0.31), set by the session; None = detect inline
        self._seen_seq = 0
        self._near_hit = False
        self._chat_fail_t = -CHAT_FAIL_LOG
        self._chat_fail_pngs = 0

    @property
    def scan(self):
        return self.ctx.account.scan

    def _note_miss(self, local_xy):
        """Hovered without an attack cursor: skip this spot for scan.miss_ttl."""
        self._misses.append((int(local_xy[0]), int(local_xy[1]), self.clock() + self.scan.miss_ttl))

    def _recent_miss(self, local_xy):
        now = self.clock()
        self._misses = [m for m in self._misses if m[2] > now]
        return any(
            math.hypot(local_xy[0] - mx, local_xy[1] - my) < MISS_RADIUS
            for mx, my, _ in self._misses
        )

    def should_rescan(self):
        """Detections were seen but none confirmed, fewer than N times in a row (more while one is next to us)."""
        limit = self.scan.misses_before_wander + (NEAR_RESCANS if self._near_hit else 0)
        return 0 < self.miss_streak < limit

    def reset_misses(self):
        """Before wandering: the view shifts, so local miss spots are stale."""
        self.miss_streak = 0
        self._misses = []
        self._blocked = [b for b in self._blocked if b[3] is not None]

    def see(self, frame, char):
        """Everything read from one grab besides the boxes: minimap + odometry, chat kill / buff lines."""
        self.last_frame = frame
        self.char = char
        self.minimap = minimap.read(frame)
        self.odo.update(self.minimap)
        self.ctx.state["minimap"] = self.minimap is not None  # PLAN 0.32: the UI warns while it is off
        watch = self.kill_watch
        if watch is not None and frame is not None:
            names = watch.update(frame)
            for name in names:
                self.chat_kills.append((self.clock(), name))
            rec = self.ctx.recorder
            if rec:
                rec.count("chat_frames")
            if not watch.readable:
                self._chat_fail(frame, watch.fail_reason)
            if names and rec:
                rec.count("chat_kill_lines", len(names))  # every kill line seen, to compare with the fights
            if watch.magic_fail:
                watch.magic_fail = 0
                self._magic_fail()
            # PLAN 2.1b: "<buff>: ... ran out" chat lines; BuffFeature.tick recasts those skills at once.
            gone = watch.pop_buff_gone()
            if gone:
                self.ctx.state.setdefault("buff_gone", []).extend(gone)

    def _chat_fail(self, frame, reason):
        """PLAN 0.31: chat not read -> one log line per CHAT_FAIL_LOG s; the first CHAT_FAIL_PNGS lossless
        chat pictures go to the recording (raw/chat_fail_*.png) to compare with its JPEG frames."""
        rec = self.ctx.recorder
        if rec:
            rec.count("chat_unreadable")
        now = self.clock()
        if now - self._chat_fail_t < CHAT_FAIL_LOG:
            return
        self._chat_fail_t = now
        self.log(f"chat not read: {reason}")
        if rec and self._chat_fail_pngs < CHAT_FAIL_PNGS:
            from ..winapi.cursor import save_png

            self._chat_fail_pngs += 1
            h = frame.shape[0]
            save_png(os.path.join(rec.path, "raw", f"chat_fail_{self._chat_fail_pngs}.png"), frame[int(0.75 * h):])

    def _magic_fail(self):
        """PLAN 0.29: "마법 사용: 실패! 올바른 대상이 아니거나 취소함" in the chat -> pause attack skills, name the key.

        PLAN 0.35: the line proves the spell DID arm and was then cancelled, so it also votes on the click
        order: SPELL_FAIL_STRIKES of them switch the account from key_click to hover_key_click, once."""
        last = getattr(self.input, "last_key", None)
        ago = f"{last[0]} pressed {time.monotonic() - last[1]:.1f}s before" if last else "no key pressed yet"
        self.ctx.state["skill_pause_until"] = self.clock() + SKILL_PAUSE_SEC
        strikes = self.ctx.state.get("spell_fail_strikes", 0) + 1
        self.ctx.state["spell_fail_strikes"] = strikes
        order = self.account.cast_order
        self.log(f"chat: 마법 사용: 실패 ({ago}, #{strikes}) -> attack skills paused {SKILL_PAUSE_SEC:.0f}s")
        switched = ""
        if strikes >= SPELL_FAIL_STRIKES and order == "key_click":
            self.account.cast_order = switched = "hover_key_click"
            self.ctx.state["spell_fail_strikes"] = 0
            self.log(f"{strikes} chat failures: cast order {order} -> {switched}")
        rec = self.ctx.recorder
        if rec:
            rec.count("magic_fail")
            rec.event("spell_fail_chat", last_key=last[0] if last else None, strikes=strikes,
                      order=order, switched_to=switched or None)

    def read_name(self, local):
        """Name over the monster at a client point from the last grab (None when unreadable / no pictures)."""
        reader = self.name_reader
        if reader is None or not reader.available or self.last_frame is None:
            return None
        plate = reader.read_near(self.last_frame, (int(local[0]), int(local[1])))
        return plate["name"] if plate else None

    def pop_kills(self):
        """Kill lines seen since the last call (and forget them)."""
        out, self.chat_kills = self.chat_kills, []
        return out

    def world(self, local):
        """Odometry position of a client point, or None without the minimap."""
        if self.char is None:
            return None
        return self.odo.world(self.minimap, self.char, local)

    def block(self, local):
        """PLAN 0.27: the character could not reach this target -> skip the spot for a while."""
        w = self.world(local)
        if w is not None:
            self._blocked.append((w[0], w[1], self.clock() + BLOCK_TTL_WORLD, self.odo.epoch))
        else:
            self._blocked.append((local[0], local[1], self.clock() + BLOCK_TTL_LOCAL, None))

    def is_blocked(self, local):
        now = self.clock()
        self._blocked = [b for b in self._blocked if b[2] > now and (b[3] is None or b[3] == self.odo.epoch)]
        w = self.world(local)
        for x, y, _t, epoch in self._blocked:
            if epoch is None:
                if math.hypot(local[0] - x, local[1] - y) < BLOCK_RADIUS:
                    return True
            elif w is not None and self.minimap is not None:
                if math.hypot(w[0] - x, w[1] - y) * self.minimap.scale < BLOCK_RADIUS:
                    return True
        return False

    def route(self, local):
        """Minimap route to a client point: "clear" / "detour" / "blocked" (+ waypoint), or (None, None)."""
        if self.minimap is None or self.char is None:
            return None, None
        return self.minimap.route(self.char, local)

    def _rec_extra(self):
        """hp/mp [cur, max] of the last HUD read for frames.jsonl (PLAN 0.27c)."""
        hp, mp = self.ctx.state.get("hp_abs"), self.ctx.state.get("mp_abs")
        return {"hp": list(hp) if hp else None, "mp": list(mp) if mp else None,
                "minimap": self.minimap is not None}

    def note_lock(self, local_xy):
        """Remember the hover we are following (name + body drop)."""
        self._last_lock = (int(local_xy[0]), int(local_xy[1]))

    def clear_lock(self):
        self._last_lock = None

    def on_start(self):
        """Drop leftover lock from a previous run (tool left open overnight)."""
        self.clear_lock()
        self.reset_misses()
        self.last_scan_points = 0
        self.last_monsters = []
        self.last_figures = []

    def on_stop(self):
        self.clear_lock()

    def rehover_last(self, rect):
        """One hover at the last follow point. Sword keeps the mob; else scan."""
        if self._last_lock is None:
            return None
        poll_escape(self.ctx)
        if not self.ctx.running:
            return None
        local_x, local_y = self._last_lock
        screen_x, screen_y = rect.to_screen(local_x, local_y)
        self.input.move(screen_x, screen_y)
        cursor = self._hash_after_hover()
        if self.ctx.cursors.is_attack(cursor):
            return Target(local_x, local_y, screen_x, screen_y)
        self.clear_lock()
        return None

    def mark_corpse(self, local_xy, ttl=None):
        """No-op: corpse despawns with the name ~1.5s. A 48px skip hid live mobs."""
        pass

    def _is_corpse_blob(self, local_xy):
        return False

    def nameplate_hints(self, rect, char, radius):
        frame = self.ctx.grabber.grab_bgr(rect)
        return self.ctx.nameplates.find(frame, char[0], char[1], rect.w, rect.h, radius=radius)

    def nameplate_near(self, rect, char, local_xy, radius=EXCLUDE_CURRENT_RADIUS):
        """True if a white nameplate is still next to this fight hover."""
        max_r = play_max_radius(rect.w, rect.h, char[0], char[1])
        hints = self.nameplate_hints(rect, char, max_r)
        ax, ay = int(local_xy[0]), int(local_xy[1])
        return any(
            math.hypot(hint.x - ax, hint.y - ay) < radius
            for hint in hints
        )

    def _hunt_map_key(self):
        return getattr(self.ctx.account, "hunt_map", None) or hunt_maps.DEFAULT_MAP_KEY

    def _detect(self, rect, char, radius, wait=0.0):
        """(frame, hits, figures, dies, detect_ms) of the newest detection, hits nearest ``char`` within radius.

        PLAN 0.31: from the detector thread when it runs (``wait`` s at most for a result newer than the last one
        used; detect_ms None = already counted by the thread), else grab + detect here. Boxes on the character
        itself are dropped. The chat / minimap are read once per new picture."""
        det = self.detector
        found = det.newest(self._seen_seq, wait) if det is not None else None
        if found is not None:
            new = found.seq != self._seen_seq
            self._seen_seq = found.seq
            frame, figures, dies, detect_ms = found.frame, found.figures, found.dies, None
            hits = [p for p in found.hits if math.hypot(p[0] - char[0], p[1] - char[1]) <= radius]
        else:
            new = True
            frame = self.ctx.grabber.grab_bgr(rect)
            map_key = self._hunt_map_key()
            t0 = time.perf_counter()
            hits = detect_centers(frame, char[0], char[1], radius=radius, map_key=map_key,
                                  conf=self.scan.conf_for(map_key))
            figures, dies = list(yolox_mobs._LAST_FIGURES), list(yolox_mobs._LAST_DIES)
            detect_ms = 1000 * (time.perf_counter() - t0)
        hits = [p for p in hits if math.hypot(p[0] - char[0], p[1] - char[1]) > SELF_R]
        # PLAN 0.40: what HealthFeature uses to see a crowd around the character (and where to step back to).
        self.ctx.state["mobs_near"] = [p for p in hits
                                       if math.hypot(p[0] - char[0], p[1] - char[1]) <= MELEE_DIST]
        if new:
            self.see(frame, char)
        return frame, hits, figures, dies, detect_ms

    def candidates(self, rect, char, max_r=None):
        """YOLOX box centers, nearest first. No spiral, no nameplates."""
        if max_r is None:
            max_r = play_max_radius(rect.w, rect.h, char[0], char[1])
        unique = []
        self.last_skipped = 0
        frame, hits, figures, dies, detect_ms = self._detect(rect, char, max_r)
        rec = self.ctx.recorder
        if rec:
            rec.begin_scan()
            rec.frame(frame, hits, char=char, detect_ms=detect_ms, extra=self._rec_extra())
        near = lambda p: math.hypot(p[0] - char[0], p[1] - char[1]) <= NEAR_KEEP  # noqa: E731
        self._near_hit = any(near(p) for p in hits)
        for tx, ty in hits:
            # Corpse skipping is disabled (see mark_corpse); kept as a hook.
            if self._is_corpse_blob((tx, ty)):
                continue
            # A standing box on a lying ("die") box is the corpse being drawn, not a new monster.
            if any(math.hypot(tx - dx, ty - dy) < CORPSE_SKIP_RADIUS for dx, dy in dies):
                continue
            if not near((tx, ty)) and (self._recent_miss((tx, ty)) or self.is_blocked((tx, ty))):
                self.last_skipped += 1
                continue
            if any(math.hypot(tx - ax, ty - ay) < MOTION_DEDUPE for ax, ay in unique):
                continue
            unique.append((tx, ty))
        if self.minimap is not None:
            # PLAN 0.27: same side of the fence first; only ordering, the walk itself decides "unreachable".
            # Straight-line test only: a BFS per box would cost up to ~30 ms each.
            # PLAN 0.31: never ahead of a monster next to the character.
            unique.sort(key=lambda p: not near(p) and not self.minimap.clear_to(char, p))  # stable: nearest first
        self.last_monsters = list(unique)
        self.last_figures = list(figures)
        self.last_dies = list(dies)
        self.last_scan_points = len(unique)
        return unique[:self.scan.max_probe_points], max_r

    def track_current(self, rect, last_xy, search_radius=None, char=None):
        """Follow the locked YOLOX box. None if it is gone."""
        radius = search_radius if search_radius is not None else CHASE_RADIUS
        origin = char if char is not None else last_xy
        scan_r = play_max_radius(rect.w, rect.h, origin[0], origin[1])
        frame, hits, figures, dies, detect_ms = self._detect(rect, origin, scan_r, wait=DETECT_WAIT)
        if self.ctx.recorder:
            self.ctx.recorder.frame(frame, hits, char=char, detect_ms=detect_ms, extra=self._rec_extra())

        self.last_monsters = list(hits)
        self.last_figures = list(figures)
        self.last_dies = list(dies)
        picked = pick_chase_center(last_xy, hits, char_xy=char, chase_radius=radius)

        if picked is None:
            return None
        tx, ty = picked
        screen_x, screen_y = rect.to_screen(tx, ty)
        return Target(tx, ty, screen_x, screen_y)

    def closer_than(self, anchor, char):
        """PLAN 0.31: a monster of the last detection next to the character (inside MELEE_DIST) and under
        SWITCH_SHARE of the lock's distance -> its point, else None. The lock's own box does not count."""
        lock_d = math.hypot(anchor[0] - char[0], anchor[1] - char[1])
        for x, y in self.last_monsters:  # nearest first
            d = math.hypot(x - char[0], y - char[1])
            if d > MELEE_DIST or d >= SWITCH_SHARE * lock_d:
                return None
            if self._recent_miss((x, y)):
                continue  # PLAN 0.32: hovering it already said "no monster" (own sprite / pet): no switch
            if d > SELF_R and math.hypot(x - anchor[0], y - anchor[1]) > LOCK_FOLLOW_RADIUS:
                return int(x), int(y)
        return None

    def _attack_cursor(self):
        return self.ctx.cursors.is_attack(CursorProbe.current_hash())

    def crop_gray_at(self, rect, local_xy, half=CROP_HALF):
        """Gray crop around a local client point, or None if empty."""
        frame = self.ctx.grabber.grab_bgr(rect)
        x, y = int(local_xy[0]), int(local_xy[1])
        x0, y0 = max(0, x - half), max(0, y - half)
        x1, y1 = min(rect.w, x + half), min(rect.h, y + half)
        crop = frame[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        return cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    def is_roi_moving(self, rect, local_xy, threshold=MOVE_THRESHOLD, half=CROP_HALF):
        """True if two grabs ~MOTION_SETTLE apart differ enough at local_xy."""
        first = self.crop_gray_at(rect, local_xy, half=half)
        if first is None:
            return False
        time.sleep(MOTION_SETTLE)
        second = self.crop_gray_at(rect, local_xy, half=half)
        if second is None:
            return False
        return roi_motion_score(first, second) >= threshold

    def _hash_after_hover(self):
        """Read the cursor a few times; the sword often lands after the first."""
        scan = self.scan
        time.sleep(scan.hover_settle)
        cursor = None
        for attempt in range(scan.hover_reads):
            if attempt:
                time.sleep(scan.hover_retry)
            cursor = CursorProbe.current_hash()
            if self.ctx.cursors.is_attack(cursor) or self.ctx.cursors.is_corpse(cursor):
                return cursor
        return cursor

    def _record_hover(self, local_xy, cursor):
        rec = self.ctx.recorder
        if rec:
            classify = getattr(self.ctx.cursors, "classify", None)
            rec.hover(local_xy, (classify(cursor) if callable(classify) else None) or "unknown", cursor=cursor)
            seen = getattr(self.ctx, "seen", None)
            if seen is not None and cursor and CursorProbe.last_print == cursor:
                seen.add(cursor, CursorProbe.last_legacy, CursorProbe.last_image, local_xy,
                         record=rec.path, frame=rec._scan_frame)

    def probe(self, points, rect):
        """Hover each point until the attack cursor shows up."""
        for local_x, local_y in points:
            poll_escape(self.ctx)
            if not self.ctx.running:
                return None
            if self._is_corpse_blob((local_x, local_y)):
                continue
            screen_x, screen_y = rect.to_screen(local_x, local_y)
            self.input.move(screen_x, screen_y)
            cursor = self._hash_after_hover()
            self._record_hover((local_x, local_y), cursor)
            if self.ctx.cursors.is_attack(cursor):
                return Target(local_x, local_y, screen_x, screen_y)
            self._note_miss((local_x, local_y))
        return None

    def probe_living(self, points, rect):
        """Like probe, but reject attack-cursor hits whose ROI is static (corpse)."""
        for local_x, local_y in points:
            poll_escape(self.ctx)
            if not self.ctx.running:
                return None
            if self._is_corpse_blob((local_x, local_y)):
                continue
            screen_x, screen_y = rect.to_screen(local_x, local_y)
            self.input.move(screen_x, screen_y)
            cursor = self._hash_after_hover()
            self._record_hover((local_x, local_y), cursor)
            if not self.ctx.cursors.is_attack(cursor):
                self._note_miss((local_x, local_y))
                continue
            if not self.is_roi_moving(rect, (local_x, local_y)):
                continue
            return Target(local_x, local_y, screen_x, screen_y)
        return None

    def acquire(self, rect, char):
        """Motion scan, then hover until the attack cursor shows."""
        t0 = time.perf_counter()
        points, _ = self.candidates(rect, char)
        t1 = time.perf_counter()
        target = self.probe(points, rect)
        probe_ms = 1000 * (time.perf_counter() - t1)
        timing = f"detect {1000 * (t1 - t0):.0f}ms probe {probe_ms:.0f}ms"
        if self.ctx.recorder:
            self.ctx.recorder.timing("probe_ms", probe_ms)
        if target:
            self.miss_streak = 0
            self.log(f"target at {target.local} ({len(points)}/{self.last_scan_points} points, {timing})")
            return target
        # Every detection was already a recent miss: same as an unconfirmed scan.
        self.miss_streak = self.miss_streak + 1 if self.last_scan_points or self.last_skipped else 0
        if points:
            stored = ""
            if hasattr(self.ctx.cursors, "get"):
                stored = self.ctx.cursors.get("attack") or ""
            live = CursorProbe.current_hash()
            kind = "unknown"
            classify = getattr(self.ctx.cursors, "classify", None)
            if callable(classify):
                kind = classify(live) or "unknown"
            self.log(
                f"yolox {len(points)}/{self.last_scan_points} points, no attack cursor "
                f"(miss {self.miss_streak}/{self.scan.misses_before_wander}, {timing}, "
                f"map={self._hunt_map_key()} class={kind} {CursorProbe.debug_pair(stored)})"
            )
        else:
            self.log(f"yolox 0 new points (miss {self.miss_streak}, {timing}, map={self._hunt_map_key()})")
        return target

    def acquire_near(self, rect, char, radius=DEFENSE_RADIUS):
        """Near scan without living filter (legacy helper)."""
        points, _ = self.candidates(rect, char, max_r=radius)
        target = self.probe(points, rect)
        if target:
            self.log(f"near target at {target.local} (r<={radius})")
        return target

    def acquire_near_living(self, rect, char, radius=DEFENSE_RADIUS):
        """Near character: attack cursor + moving ROI."""
        points, _ = self.candidates(rect, char, max_r=radius)
        target = self.probe_living(points, rect)
        if target:
            self.log(f"near living at {target.local} (r<={radius})")
        return target

    def acquire_living(self, rect, char):
        """Full window: attack cursor + moving ROI, nearest first."""
        points, _ = self.candidates(rect, char)
        target = self.probe_living(points, rect)
        if target:
            self.log(f"living at {target.local} ({self.last_scan_points} points)")
        return target

    def retarget_after_death(self, rect, char):
        """Near living first, then full living, skipping the marked corpse blob."""
        if self._corpse is not None:
            near = self.find_alternate(rect, char, self._corpse)
            if near is not None:
                return near
            return self.acquire_living(rect, char)
        near = self.acquire_near_living(rect, char)
        if near is not None:
            return near
        return self.acquire_living(rect, char)

    def find_alternate(self, rect, char, current, radius=DEFENSE_RADIUS, exclude_r=EXCLUDE_CURRENT_RADIUS):
        """One-shot near living probe, optionally skipping the current corpse blob."""
        if current is None:
            return self.acquire_near_living(rect, char, radius=radius)

        points, _ = self.candidates(rect, char, max_r=radius)
        filtered = [
            p
            for p in points
            if math.hypot(p[0] - current[0], p[1] - current[1]) >= exclude_r
        ]
        target = self.probe_living(filtered, rect)
        if target:
            self.log(f"alternate living at {target.local} (skipping {current})")
        return target

    def reacquire_near(self, rect, char, anchor, radius=None):
        """Find the nameplate closest to a previous target position."""
        max_r = radius or play_max_radius(rect.w, rect.h, char[0], char[1])
        hints = self.nameplate_hints(rect, char, max_r)
        if not hints:
            return None
        hints.sort(key=lambda h: (h.x - anchor[0]) ** 2 + (h.y - anchor[1]) ** 2)
        best = hints[0]
        screen_x, screen_y = rect.to_screen(best.x, best.y)
        return Target(best.x, best.y, screen_x, screen_y)
