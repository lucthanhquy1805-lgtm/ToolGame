"""PLAN 0.50 / 3.0-L: a knight / prince with pull_mode GATHERS monsters and walks them home to the group.

Out on a trip: one walk click at a time in one of the 8 directions (+1 each trip); every new monster gets combat's
pull hits (PULL_HITS, never killed) so it follows. Following = boxes within targeting.FOLLOW_PX of the character,
the smaller count of the last two new pictures (state["follow_counts"], written by targeting._detect).
Home (walking, no fight on the way) when following >= scan.lure_mobs, past scan.lure_steps, after
scan.lure_max_sec, or HP < scan.pull_abort_hp - whatever follows comes along. At home the knight guards
(scan.guard_steps around the start) and only goes out again once <= IDLE_MOBS boxes stood around it for
scan.lure_idle_sec. 3.0-L v2: "the start" is the party leader's crown when it is seen (features/leader.py), and
a trip turns back as "leader_range" past lure_steps from it or when the crown leaves the minimap. Nobody runs away any more: danger = heal / potion and keep fighting (survival).

shortcut: the walk out does not check the minimap for fences; lure_max_sec bounds a trip stuck on one. Upgrade to
exploration.score_directions if trips keep ending as "time".
"""
import math
import time

from ..characters import CombatStyle
from ..vision import party_minimap
from ..vision.geometry import walk_point
from .base import Feature
from .exploration import GO_HOME_STOP, HOME_CLICK_SEC, NAMES, WALK_PX
from .leader import EDGE_MM, home_stop

IDLE_MOBS = 2
# 3.0-L v2: one walk click every WALK_WAIT s at least - clicks every 0.18 s each counted 2 steps that were never
# walked (r232815: home_dist 31.5 -> 0 in 3 s, the leader still ~22 steps away).
WALK_WAIT = HOME_CLICK_SEC


class LureFeature(Feature):
    key = "lure"

    def __init__(self, ctx, exploration=None, clock=time.monotonic):
        super().__init__(ctx)
        self.exploration = exploration
        self.clock = clock
        self.on_start()

    def on_start(self):
        self.active = False  # out on a trip
        self.returning = None  # the lure_return why while walking home
        self._t0 = 0.0
        self._dir = -1
        self._busy_t = None  # last time more than IDLE_MOBS boxes stood around us at home
        self._click_t = None  # last walk-out click

    def enabled(self):
        scan = self.account.scan
        return bool(scan.pull_mode and scan.hunt_range) and self.character.style == CombatStyle.MELEE

    def range_steps(self):
        """Steps from the start a melee target may stand at: lure_steps on a trip, guard_steps at home."""
        if not self.enabled():
            return None
        return self.account.scan.lure_steps if self.active else self.account.scan.guard_steps

    def following(self):
        counts = self.ctx.state.get("follow_counts") or ()
        return min(counts) if len(counts) >= 2 else 0

    def steps(self):
        return math.hypot(*self.ctx.offset()) / self.ctx.step_px()

    def _event(self, kind, **data):
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.event(kind, **data)
            rec.count(kind)

    def return_why(self, hp):
        scan = self.account.scan
        if self.following() >= scan.lure_mobs:
            return "count"
        if hp and hp < scan.pull_abort_hp:
            return "hp"
        if self.ctx.state.get("leader_mode"):
            # 3.0-L v2: the caster (leader) sees lure_steps around it; past that, or the crown leaving the
            # minimap, the monsters we bring would never reach it
            vec = self.ctx.state.get("leader")
            if vec is None or self.steps() >= scan.lure_steps or party_minimap.edge_room(vec) < EDGE_MM:
                return "leader_range"
        if self.steps() >= scan.lure_steps:
            return "steps"
        if self.clock() - self._t0 >= scan.lure_max_sec:
            return "time"
        return None

    def go_home(self, why):
        self.log(f"lure: back to the start ({why}), {self.following()} following")
        self._event("lure_return", why=why, mobs_following=self.following(), steps=round(self.steps(), 1))
        self.active, self.returning = False, why
        self.ctx.state["go_home"] = True

    def after_hit(self, hp):
        """Combat: a monster got its pull hits. True = walk home now (go_home is set)."""
        if not self.active:  # a pull from the guard spot (guard_steps set wide): just go back, as in 1.7
            self.ctx.state["go_home"] = True
            return True
        self._event("lure_hit", mobs_following=self.following())
        why = self.return_why(hp)
        if why:
            self.go_home(why)
            return True
        return False

    def observe(self):
        """Every beat: remember when the start was last crowded (the next trip waits for it to be quiet)."""
        counts = self.ctx.state.get("follow_counts") or ()
        if not self.active and (self._busy_t is None or (counts and counts[-1] > IDLE_MOBS)):
            self._busy_t = self.clock()

    def tick(self, rect, char, hp):
        """No target this beat. True = it handled the beat (walked out / set go_home), the session skips wander."""
        if not self.enabled():
            return False
        if self.active:
            why = self.return_why(hp)
            if why:
                self.go_home(why)
                return True
            self._walk_out(rect, char)
            return True
        if self.steps() > home_stop(self.ctx, GO_HOME_STOP):
            return False  # not at the start yet: wander walks home
        now = self.clock()
        if (self._busy_t is not None and now - self._busy_t < self.account.scan.lure_idle_sec) or (
                hp and hp < self.account.scan.pull_abort_hp):
            return False
        self.active, self._t0, self._dir = True, now, (self._dir + 1) % len(NAMES)
        self.log(f"lure: going out {NAMES[self._dir]}")
        self._event("lure_start", dir=NAMES[self._dir], idle_s=round(now - (self._busy_t or now), 1))
        self._walk_out(rect, char)
        return True

    def _walk_out(self, rect, char):
        now = self.clock()
        if self._click_t is not None and now - self._click_t < WALK_WAIT:
            return  # still walking the last click: no stacked clicks (the beat rescans instead)
        self._click_t = now
        point = walk_point(char[0], char[1], rect.w, rect.h, self._dir, WALK_PX)
        name = NAMES[self._dir]
        self.exploration._walk_click(rect, char, point, name, "lure", f"{name} luring, {self.following()} follow")

    def home(self):
        """Session: the walk home is over."""
        if self.returning is not None and self.steps() <= GO_HOME_STOP + 1:
            vec = self.ctx.state.get("leader")
            self._event("lure_home", why=self.returning, mobs_following=self.following(),
                        leader_steps=round(self.steps(), 1) if vec else None)  # offset = the leader
            self.returning, self._busy_t = None, self.clock()
