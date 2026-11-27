"""Fight a confirmed target.

Hold left + drag like v1.5 to arm continuous auto-attack. Stay on this mob
until the corpse (X) cursor, or the sword is gone and YOLOX no longer sees
the lock. A one-frame box miss while the sword is still up must not leave
and acquire a neighbor — hitting every surrounder pulls the whole pack.
"""

import math
import time
import types

from ..runtime.stats import bump, kill_name
from ..skills.policy import is_auto_enabled
from ..vision.geometry import blocking_figure, detour_point, park_point
from ..vision.motion_watch import DeathWatch
from ..winapi.cursor import CursorProbe
from ..winapi.hotkeys import poll_escape
from .base import Feature
from .targeting import IN_PLACE_SHOT_PX, LOCK_FOLLOW_RADIUS, MELEE_DIST, MELEE_LOCK_DIST
from .targeting import SELF_R as SELF_BOX_R

DRAG_OFFSET = 15
BURST_INTERVAL = 0.1
NAMEPLATE_BODY_DROP = 25
# Pauses inside hold+drag so the client registers each step.
HOLD_MOVE_SETTLE = 0.02
HOLD_DOWN_SETTLE = 0.04
# PLAN 0.32: the lock must still be in the newest detection. Gone this long -> leave at once (092741: 16 fights
# stood 25 s on a box that was no longer there while the cursor still read "attack").
BOX_GONE_SEC = 1.0
# PLAN 0.32: in melee range without an attack cursor this long -> we are not hitting anything, leave.
NO_SWORD_SEC = 1.0
MAX_COMBAT_BURSTS = 400  # safety net; MAX_FIGHT_SEC / scan.melee_max_sec are the real caps (PLAN 0.28 / 0.31)
# Wait after a detour click before re-arming the attack.
DETOUR_SETTLE = 0.12
# PLAN 0.4: a YOLOX "die" box this close to the lost lock means the mob died there.
DIE_NEAR_RADIUS = 40
# engage() exits that count as a kill (vs lost / gone / unreachable / cap / stopped / char_dead / town).
# PLAN 0.27: chat_kill = a new "아데나 (n) 획득: <name>" line during the fight; vanished = the box left the lock
# and stayed away BOX_GONE_SEC s (zones whose chat cannot be read).
KILL_OUTCOMES = ("corpse_cursor", "die_box", "frozen", "chat_kill", "vanished")
# PLAN 0.31 / 3: the backup kill signals (body / cursor), used when no kill line confirms the fight.
CORPSE_OUTCOMES = ("corpse_cursor", "die_box", "frozen", "vanished")
# A kill line this soon after a fight that ended without a kill belongs to that fight.
LATE_KILL_SEC = 3.0
# PLAN 0.27 / 3: no step closer for this long (beyond melee) = the target cannot be reached (wall, fence).
# PLAN 0.39: 2.5 -> 1.5 (233615: 20 unreachable fights stood 2.8-7.4 s hitting a fence).
UNREACH_SEC = 1.5
# PLAN 0.40: the minimap cannot see a fence closer than ~7 of its pixels, and 70 client px are 7 minimap px inside
# the character arrow (forced walkable) - so near a monster there is no wall signal at all. 44 of the 55
# "unreachable" fights of 20261126_101941_hunt stood 70-92 px away with the attack cursor on a live box and were
# dropped after 1.8 s, while a kill by hand takes 3.8 s on that ground (5 of its 6 kill lines arrived just AFTER
# such a fight was left). Within NEAR_FIGHT_DIST the fight gets NEAR_UNREACH_SEC instead of UNREACH_SEC.
NEAR_FIGHT_DIST = 100
# PLAN 0.42: a monster this close is always tried, whatever the minimap route says (no 'wall' ending); a real
# fence still ends it as unreachable / cap.
WALL_MIN_DIST = 250
NEAR_UNREACH_SEC = 4.0
DETOUR_AFTER = 0.8  # s without progress before walking to the minimap gap once
PROGRESS_PX = 16
MAX_DETOURS = 2
DETOUR_WALK = 0.6  # s given to the walk to the gap before re-arming
# PLAN 0.28: progress = a kill line or the character getting closer. No progress for NO_PROGRESS_SEC -> leave and
# blacklist the spot; one side step at SIDESTEP_AFTER first. No fight lasts longer than MAX_FIGHT_SEC.
# PLAN 0.31 (223510: 40/51 no_progress were < 66 px from the character, 66 side steps pulled it off the monster it was
# hitting): MELEE = lock within MELEE_DIST + attack cursor -> no side step, no no_progress, no blacklist; it ends on
# the kill / the box gone, or after scan.melee_max_sec (25 s). The 0.28 rules are only for a lock still far away.
# (No monster HP bar to read: the red bar over the head in the recordings is the character's own, it follows HUD HP.)
NO_PROGRESS_SEC = 8.0
SIDESTEP_AFTER = 5.0
SIDESTEP_PX = 60
SIDESTEP_WALK = 0.5
MAX_FIGHT_SEC = 15.0
# PLAN 0.33: how long after the last fight beat the detector still treats the hunt as "fighting".
FIGHT_HINT_SEC = 1.0
# PLAN 0.35: the client arms a targeted spell by turning the cursor into an aiming ellipse, and the game PC
# measured that taking a good SECOND. v16 waited 0.3 s, gave up and fell back to the hand attack, which is why
# 144/144 casts of 145650 logged "no_target_cursor" while the chat showed 45 "마법 사용: 실패(취소함)" lines -
# the spell HAD armed and was cancelled because nobody clicked. So: poll the cursor every AIM_POLL for up to
# AccountSettings.aim_wait_sec, do nothing else while waiting (any other click / key / step cancels the spell),
# then click the monster's NEWEST box. No ellipse by the deadline = click once anyway (a click on a monster
# with no spell armed is only a hand attack) and log it.
AIM_POLL = 0.1
# PLAN 0.39: after a cast the cursor is not the sword for a moment (the client fires, the hold restarts); 233615
# ended 15 fights "lost, no attack cursor" right after a spell on a monster still alive.
CAST_GRACE = 1.0
MP_SETTLE = 0.8  # s after the click before the MP read that shows what the cast cost (spell_mp event)
# PLAN 0.39: MP% the heal skill keeps; attack spells stop below it (233615 cast down to 20 %, MP fell to 2 %).
HEAL_MP_RESERVE = 25
# PLAN 0.41: 20261126_101941_hunt cast 0 spells in 8.6 min (798 "low_mp" skips): the slot's min_mp was 65% and MP
# sat at 30-45% the whole hunt, so a wizard fought crowds by hand. With CROWD_SPELL_N boxes within CROWD_SPELL_PX
# the slot's min_mp is ignored; MP must still stay at CROWD_MP_FLOOR (the heal reserve) or above.
CROWD_SPELL_N = 2
CROWD_SPELL_PX = 200
CROWD_MP_FLOOR = HEAL_MP_RESERVE


class CombatFeature(Feature):
    key = "combat"

    def __init__(self, ctx, health=None, targeting=None, buff=None, cure=None):
        super().__init__(ctx)
        self.health = health
        self.targeting = targeting
        self.buff = buff
        self.cure = cure
        self.last_outcome = None
        self.last_anchor = None  # client point of the lock when the fight ended (the corpse for loot)
        self.last_world = None
        self._ended_at = 0.0
        self._fight_start = 0.0
        self._last_source = "none"  # kill source of the last fight: chat / corpse / none
        self._prev_outcome = None  # last_outcome is reset when a fight starts; this one is not
        self._dist = None
        self._melee = False
        self._box_gone = None  # s since the lock's box was last in a detection (PLAN 0.32)
        self._cursor_last = None
        self._slot_used = {}  # PLAN 1.6: per-slot cooldown clock
        self._slot_turn = 0
        self._spells = 0  # spells cast in the fight under way
        self._skipped = {}  # why a slot was skipped, for the recording
        self._no_skill_said = False  # PLAN 0.44: the "no attack skill" warning is logged once
        self._mp_pending = None  # (time, key, mp_before) of the last cast, read again after MP_SETTLE

    def active_skills(self):
        keys = []
        for key in sorted(self.account.attack_skills, key=lambda k: int(k[1:])):
            setting = self.account.attack(key)
            if not setting.enabled or not setting.skill_id:
                continue
            if not is_auto_enabled(setting.skill_id):
                continue
            keys.append(key)
        return keys

    def _slot_ready(self, key, dist, now, mp):
        """PLAN 1.6 gates for one attack slot: own cooldown, max distance, min MP%. -> (reason, ok)."""
        setting = self.account.attack(key)
        wait = setting.cooldown if setting.cooldown > 0 else self.character.skill_interval
        if now - self._slot_used.get(key, 0.0) < wait:
            return "cooldown", False
        if setting.range_px and dist is not None and dist > setting.range_px:
            return "out_of_range", False
        crowd = False
        if setting.min_mp and mp is not None and mp < setting.min_mp:
            crowd = self._crowd() and mp >= CROWD_MP_FLOOR
            if not crowd:
                return "low_mp", False
        if mp is not None and mp < self._mp_reserve():
            return "heal_reserve", False
        return "crowd" if crowd else "", True

    def _crowd(self):
        """PLAN 0.41: at least CROWD_SPELL_N boxes within CROWD_SPELL_PX in the newest detection."""
        char = self.ctx.state.get("char")
        boxes = self.ctx.state.get("mobs_seen") or []
        return char is not None and sum(
            math.hypot(x - char[0], y - char[1]) <= CROWD_SPELL_PX for x, y in boxes) >= CROWD_SPELL_N

    def _mp_reserve(self):
        return HEAL_MP_RESERVE if self.account.health.use_skill else 0

    def _pick_skill(self, skills, rect, dist, now):
        """The next attack slot to fire -> (key or None, mp%). Rotates so several slots share the beats."""
        need = self._mp_reserve() or any(self.account.attack(k).min_mp for k in skills)
        mp = self.ctx.read_mp(rect) if need else None
        turn = self._slot_turn % len(skills)
        for key in skills[turn:] + skills[:turn]:
            reason, ok = self._slot_ready(key, dist, now, mp)
            if ok:
                self._slot_turn += 1
                if reason == "crowd":  # PLAN 0.41: under the slot's min_mp, allowed by the crowd rule
                    self._skipped["crowd_cast"] = self._skipped.get("crowd_cast", 0) + 1
                return key, mp
            self._skipped[reason] = self._skipped.get(reason, 0) + 1
        return None, mp

    def _wait_aim_cursor(self, before=None):
        """Poll the cursor until the aiming ellipse shows. -> (aim_delay or None, [{at, hash, md5, kind}]).

        PLAN 0.35: the reads are kept (one per distinct picture) so the game PC can see what the ellipse over
        a monster really looks like - the registered "cast" picture was captured over the ground. Nothing but
        reading happens here: a click, a key or a step would cancel the spell the client is arming.
        PLAN 0.39: ``before`` = the cursor read just before the slot key. An ellipse that was already there
        (233615: 94/94 "ellipse" at 0.0 s, always fc92) is not this key's ellipse - only a change counts."""
        stale = before if before and self.ctx.cursors.classify(before) == "cast" else None
        reads, seen, start = [], set(), time.time()
        deadline = start + max(0.0, float(getattr(self.account, "aim_wait_sec", 1.8)))
        while True:
            cursor_hash = CursorProbe.current_hash()
            kind = self.ctx.cursors.classify(cursor_hash) or "unknown"
            if cursor_hash not in seen:
                seen.add(cursor_hash)
                reads.append({"at": round(time.time() - start, 2), "hash": cursor_hash,
                              "md5": getattr(CursorProbe, "last_legacy", None), "kind": kind})
            if kind == "cast" and cursor_hash != stale:
                return round(time.time() - start, 2), reads
            if time.time() >= deadline or not self.ctx.running:
                return None, reads
            poll_escape(self.ctx)
            time.sleep(AIM_POLL)

    def _aim_point(self, rect, char, anchor):
        """Where to click once the spell is armed: the lock's newest box, else the nearest other monster.

        PLAN 0.35: the monster walks on while the spell arms, and it may well die in that second - the spell is
        still in hand then, so spend it on the closest neighbour instead of cancelling."""
        if self.targeting is None:
            return anchor
        updated = self.targeting.track_current(rect, anchor, char=char)
        if updated is not None:
            return (updated.local_x, updated.local_y)
        others = [(x, y) for x, y in self.targeting.last_monsters
                  if math.hypot(x - char[0], y - char[1]) > SELF_BOX_R]
        if not others:
            return None
        return min(others, key=lambda p: math.hypot(p[0] - char[0], p[1] - char[1]))

    def _cast_at_target(self, key, rect, char, anchor, mp_before=None):
        """Use the spell on the locked monster, in the order the client wants (AccountSettings.cast_order).

        PLAN 0.35: key_click (the default) presses the slot key - after switching hotbar page - waits up to
        AccountSettings.aim_wait_sec for the aiming ellipse, then clicks the monster's newest box. The ellipse
        is no longer a condition: without it the click is a plain hand attack, so it costs nothing. A lock that
        died while the spell armed hands it to the nearest neighbour; nothing near = right-click to cancel.
        hover_key_click hovers the body first; click_key clicks to select and presses the key after. The order
        stays a setting (targeting flips it after SPELL_FAIL_STRIKES chat failures)."""
        setting = self.account.attack(key)
        self.input.release_left()
        time.sleep(0.05)

        target = self.targeting.reacquire_near(rect, char, anchor) if self.targeting else None
        if target is None:
            self.log(f"no nameplate for {key}, skipping this beat")
            self._skipped["no_nameplate"] = self._skipped.get("no_nameplate", 0) + 1
            return anchor, False, None

        screen_x = target.screen_x
        screen_y = target.screen_y + NAMEPLATE_BODY_DROP
        order = self.account.cast_order
        # PLAN 1.2c: standing still, a click on the monster before the key would walk to it -> key first.
        still = self._shoot_only()
        if still and order == "click_key":
            order = "key_click"
        reads, aim_delay = [], None
        before = CursorProbe.current_hash()
        if order == "click_key":
            self.input.click_at(screen_x, screen_y)
            time.sleep(0.05)
            self.ctx.press_slot(setting.page, key)
        else:
            if order == "hover_key_click":
                self.input.move(screen_x, screen_y)
                time.sleep(0.02)
            self.ctx.press_slot(setting.page, key)
            aim_delay, reads = self._wait_aim_cursor(before)
            point = self._aim_point(rect, char, anchor)
            if point is None:
                # An armed spell with nothing left to throw it at: right-click cancels it (ESC is the stop key).
                self.input.click_right()
                self.log(f"skill {key}: the target died while the spell armed and nothing else is near, "
                         f"cancelled with a right click (ellipse after {aim_delay}s)")
                self._skipped["no_target_left"] = self._skipped.get("no_target_left", 0) + 1
                self._record_cast(key, setting, order, None, rect, mp_before, aim_delay, reads,
                                  ok=False, reason="no_target_left", before=before)
                return anchor, False, None
            # PLAN 0.39: a box centre is the body already; the nameplate drop put the click (and the hold after
            # it) on the ground - 233615: 15 fights "lost" with the ground cursor right after a spell.
            screen_x, screen_y = rect.to_screen(point[0], point[1])
            target = types.SimpleNamespace(local=(int(point[0]), int(point[1])),
                                           local_x=int(point[0]), local_y=int(point[1]))
            if aim_delay is None and still:
                # PLAN 1.2c: no ellipse = the spell did not arm; a click now is a walk toward the monster.
                self.input.click_right()
                self.log(f"skill {key}: no aiming ellipse, not clicking (stay put)")
                self._skipped["no_ellipse"] = self._skipped.get("no_ellipse", 0) + 1
                self._record_cast(key, setting, order, None, rect, mp_before, aim_delay, reads,
                                  ok=False, reason="no_ellipse", before=before)
                return anchor, False, None
            if aim_delay is None:
                wait_for = float(getattr(self.account, "aim_wait_sec", 1.8))
                self.log(f"skill {key}: no aiming ellipse within {wait_for:.1f}s, clicking anyway")
            self.input.click_at(screen_x, screen_y)
        now = time.time()
        self._slot_used[key] = now
        self._spells += 1
        self.log(f"skill {setting.page}+{key} ({order}) on {target.local}"
                 + (f", ellipse after {aim_delay}s" if aim_delay is not None else ""))
        self._record_cast(key, setting, order, target, rect, mp_before, aim_delay, reads, before=before)
        return (target.local_x, target.local_y), True, (screen_x, screen_y)

    def _record_cast(self, key, setting, order, target, rect, mp_before, aim_delay, reads,
                     ok=True, reason=None, before=None):
        """One spell_cast event. PLAN 0.35: aim_delay_s = slot key -> ellipse, so analyze_records can average
        it and the "aim wait" default can be tuned; cursor_after_key holds every picture seen while waiting.
        PLAN 0.39: MP read right after the click never moved (93/94 equal); the cost comes MP_SETTLE later as a
        spell_mp event (engage)."""
        if ok:
            self._mp_pending = (time.time(), key, mp_before)
        bump(self.ctx, "spell_cast" if ok else "spell_no_cast")  # PLAN 4.1
        rec = getattr(self.ctx, "recorder", None)
        if rec is None:
            return
        rec.count("spell_cast" if ok else "spell_no_target")
        if ok:
            rec.count(f"spell_{key}")
        if aim_delay is None:
            rec.count("spell_no_ellipse")
        rec.event("spell_cast", ok=ok, reason=reason, key=key, page=setting.page, skill_id=setting.skill_id,
                  order=order, target=list(target.local) if target is not None else None,
                  mp_before=mp_before, aim_delay_s=aim_delay, cursor_before_key=before,
                  cursor_after_key=reads, fight_sec=round(time.time() - self._fight_start, 1))

    def _check_mp_pending(self, rect):
        """PLAN 0.39: MP_SETTLE after a cast, read MP once more: what the spell really cost."""
        pending = self._mp_pending
        if pending is None or time.time() - pending[0] < MP_SETTLE:
            return
        self._mp_pending = None
        rec = getattr(self.ctx, "recorder", None)
        if rec is not None:
            rec.event("spell_mp", key=pending[1], mp_before=pending[2], mp_after=self.ctx.read_mp(rect),
                      after_s=round(time.time() - pending[0], 1))

    def _hold_and_drag(self, screen_x, screen_y):
        """Arm auto-attack: move, hold left, pull down. Never a click."""
        self.input.move(screen_x, screen_y)
        time.sleep(HOLD_MOVE_SETTLE)
        self.input.hold_left()
        time.sleep(HOLD_DOWN_SETTLE)
        self.input.drag_nudge(screen_x, screen_y, DRAG_OFFSET)

    def _rearm(self, screen_x, screen_y):
        """Release then hold+drag again after a skill or cancelled auto-attack."""
        self.input.release_left()
        self._hold_and_drag(screen_x, screen_y)

    def _refresh_hold(self, screen_x, screen_y):
        """Keep/restore AA: sit on the hover, then pull down. Never a click."""
        self._hold_and_drag(screen_x, screen_y)

    def _resume_hold(self, screen_x, screen_y):
        self._hold_and_drag(screen_x, screen_y)

    def _note_lock(self, local_xy):
        if self.targeting is not None:
            self.targeting.note_lock(local_xy)

    def _clear_lock(self):
        if self.targeting is not None:
            self.targeting.clear_lock()

    def _scan_figures(self):
        if self.targeting is None:
            return []
        figures = getattr(self.targeting, "last_figures", None)
        if not isinstance(figures, (list, tuple)):
            return []
        return list(figures)

    def _detour_if_blocked(self, rect, char, target):
        """Click beside a standing figure on the walk line, then resume the mob."""
        blocker = blocking_figure(char, target.local, self._scan_figures())
        if blocker is None:
            return
        waypoint = detour_point(char, target.local, blocker, rect.w, rect.h)
        if waypoint is None:
            return
        self.log(f"figure blocking path, walk around {waypoint}")
        self.input.release_left()
        self.input.click_at(*rect.to_screen(*waypoint))
        time.sleep(DETOUR_SETTLE)

    def _die_near(self, anchor):
        dies = getattr(self.targeting, "last_dies", None) or []
        return any(math.hypot(x - anchor[0], y - anchor[1]) <= DIE_NEAR_RADIUS for x, y in dies)

    def _tally(self, key, n=1):
        """PLAN 0.31 / 3: kills = kills_chat (one per kill line) + kills_corpse_only (body/cursor, no line)."""
        state = self.ctx.state
        state[key] = state.get(key, 0) + n
        state["kills"] = state.get("kills_chat", 0) + state.get("kills_corpse_only", 0)
        bump(self.ctx, key, n)  # PLAN 4.1
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.count(key, n)

    def _finish(self, target, outcome, anchor=None, detail="", lines=1):
        """Leave the fight; record why (kills feed stats, loot and the field log).

        A chat_kill counts its ``lines`` kill lines (a splash can kill two), a body/cursor ending counts 1 until a
        kill line within LATE_KILL_SEC turns it into a chat kill (never 2 for one monster), the rest count 0."""
        self.last_outcome = outcome
        self._ended_at = time.time()
        seconds = self._ended_at - self._fight_start
        if anchor is not None:
            self.last_anchor = anchor
            self.last_world = self.targeting.world(anchor) if self.targeting is not None else None
        self._clear_lock()
        self.ctx.state["fight_until"] = 0.0  # PLAN 0.40: the fight is over now (health may step back at once)
        # PLAN 0.35: no return to the home page here - 145650 spent 101 of its 202 page switches on a return
        # that the very next fight undid. session._run goes home once the hunt runs dry (HOME_IDLE_SEC).
        note = f" ({detail})" if detail else ""
        source = "chat" if outcome == "chat_kill" else "corpse" if outcome in CORPSE_OUTCOMES else "none"
        self._last_source, self._prev_outcome = source, outcome
        if source == "chat":
            self._tally("kills_chat", lines)
        elif source == "corpse":
            self._tally("kills_corpse_only")
        if outcome in KILL_OUTCOMES:
            self.log(f"monster dead ({outcome}){note}")
        else:
            self.log({"lost": "lost target", "cap": f"fight cap {seconds:.0f}s, leaving lock",
                      "gone": "target gone, no kill line", "unreachable": "target unreachable, blacklisted",
                      "no_progress": "no progress, blacklisted", "switch": "closer monster, switching",
                      "wall": "no way on the minimap, blacklisted",
                      "danger": "danger, leaving the fight",
                      "no_spell": "no attack skill enabled, nothing to shoot with"}
                     .get(outcome, outcome) + note)
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.count(f"end_{outcome}")
            rec.event("fight_end", outcome=outcome, detail=detail, seconds=round(seconds, 1),
                      anchor=list(anchor) if anchor is not None else None,
                      dist=round(self._dist) if self._dist is not None else None, melee=self._melee,
                      kill_source=source, box_seen_last_s=self._box_gone, cursor_last=self._cursor_last,
                      spells=self._spells, skipped=dict(self._skipped))
            rec.fight(outcome, seconds, outcome in KILL_OUTCOMES)
            if outcome in KILL_OUTCOMES:
                # PLAN 1.6: how long a kill takes with spells against bare hands.
                rec.timing("kill_sec_spell" if self._spells else "kill_sec_hand", seconds)
        return target

    def _kill_lines(self, during=True):
        """New kill lines that belong to the fight under way; the others are counted here (PLAN 0.31 / 3).

        A line within LATE_KILL_SEC of the end of a fight that had no kill line belongs to that fight (the bot left
        before the line came): the first one turns its body/cursor kill into a chat kill (counted once), the
        others / a non-kill ending count +1 each. A line older than that (seen while wandering) counts +1.
        ``during`` False (fight start): no line belongs to the new fight yet."""
        lines = self.targeting.pop_kills() if self.targeting is not None else []
        mine = []
        for t, name in lines:
            late = bool(self._prev_outcome) and t - self._ended_at <= LATE_KILL_SEC and self._last_source != "chat"
            if during and not late and t >= self._fight_start:
                mine.append((t, name))
                continue
            if late and self._last_source == "corpse":
                self._tally("kills_corpse_only", -1)
            self._tally("kills_chat")
            what = f"previous fight ({self._prev_outcome})" if late else "no fight"
            self.log(f"kill line {name} -> {what}")
            rec = getattr(self.ctx, "recorder", None)
            if rec:
                rec.count("late_chat_kill" if late else "chat_kill_outside")
                rec.event("kill_line", name=name, fight=self._prev_outcome if late else None)
            if late:
                self._last_source = "chat"
            kill_name(self.ctx, name)  # PLAN 4.1
        return mine

    def on_stop(self):
        self._kill_lines()  # lines of the last fight still waiting

    def _chat_readable(self):
        watch = getattr(self.targeting, "kill_watch", None)
        return watch is not None and watch.readable

    def _try_detour(self, rect, anchor):
        """No progress toward the lock: walk to the minimap gap once. True when it clicked."""
        kind, waypoint = self.targeting.route(anchor) if self.targeting is not None else (None, None)
        if kind != "detour":
            return False
        self.log(f"no progress, minimap way round via {waypoint}")
        self.input.release_left()
        self.input.click_at(*rect.to_screen(*waypoint))
        self.ctx.sleep(DETOUR_WALK)
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.count("detour_minimap")
        return True

    def _sidestep(self, rect, char, anchor):
        """One step across the char->monster line (grass / a trunk in the way), then hit again (PLAN 0.28)."""
        dx, dy = anchor[0] - char[0], anchor[1] - char[1]
        n = math.hypot(dx, dy) or 1.0
        sides = [(int(char[0] - dy / n * SIDESTEP_PX), int(char[1] + dx / n * SIDESTEP_PX)),
                 (int(char[0] + dy / n * SIDESTEP_PX), int(char[1] - dx / n * SIDESTEP_PX))]
        if self.targeting is not None:
            sides.sort(key=lambda p: self.targeting.route(p)[0] not in (None, "clear"))
        self.log(f"no progress, side step to {sides[0]}")
        self.input.release_left()
        self.input.click_at(*rect.to_screen(*sides[0]))
        self.ctx.sleep(SIDESTEP_WALK)
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.count("sidestep")

    def _confirm_switch(self, rect, point):
        """PLAN 0.32: hover the nearer box before leaving the lock for it.

        092741 switched 17 times to a box 26-62 px from the character (its own sprite / a pet / another player);
        the fight that followed stood still until the melee cap. Only an attack cursor there is a monster."""
        if self.targeting is None:
            return False
        self.input.release_left()
        if self.targeting.probe([point], rect) is not None:
            return True
        self.log(f"nearer box {point} is not attackable, staying on the lock")
        return False

    def _shoot_only(self):
        """PLAN 1.2c: "stay put" with a ranged class - spells only, never a click that walks."""
        tg = self.targeting
        return getattr(tg, "in_place", None) is not None and tg.in_place() and tg.ranged()

    def engage_ranged(self, target, rect, char):
        """PLAN 1.2c: shoot the lock from where we stand. No hold, no click on the monster: attack spells only
        (the aiming ellipse is required); none ready (MP, cooldown) = wait. Ends on a kill line, the box gone,
        the lock out of IN_PLACE_SHOT_PX or the fight cap."""
        self.last_outcome = None
        skills, interval = self.active_skills(), self.character.skill_interval
        anchor = target.local
        if not skills:
            # PLAN 0.44: no enabled attack skill = a caster standing still can do NOTHING to this monster.
            # v21rc5 aimed in silence for the whole cap (20261127_101929_hunt: 68 fights, 0 spells, no record of
            # why). Say it once, hit by hand what is already next to us, and leave the rest alone.
            return self._no_spell(target, rect, char, anchor)
        self._note_lock(anchor)
        self._fight_start = started = box_t = time.time()
        self._kill_lines(during=False)
        self._dist, self._melee = math.hypot(char[0] - anchor[0], char[1] - anchor[1]), False
        self._box_gone, self._cursor_last = 0.0, None
        self._spells, self._skipped = 0, {}
        last_skill = 0.0
        self.input.release_left()
        while self.ctx.running and time.time() - started < self.account.scan.melee_max_sec:
            poll_escape(self.ctx)
            if not self.ctx.running:
                break
            rect = self.ctx.rect()
            char = self.ctx.char_pos(rect)
            self.ctx.state["fight_until"] = time.monotonic() + FIGHT_HINT_SEC
            if self.cure:
                self.cure.tick(rect)
            if self.health and self.health.check_death(rect):
                return self._finish(None, "town" if getattr(self.health, "returned", False) else "char_dead")
            if self.health is not None and getattr(self.health, "danger", False):
                return self._finish(target, "danger", anchor)
            time.sleep(BURST_INTERVAL)
            self._check_mp_pending(rect)
            updated = self.targeting.track_current(rect, anchor, char=char) if self.targeting else None
            now = time.time()
            if updated is not None:
                anchor, box_t = updated.local, now
                self._note_lock(anchor)
            self._dist = math.hypot(char[0] - anchor[0], char[1] - anchor[1])
            self._box_gone = round(now - box_t, 1)
            kills = self._kill_lines()
            if kills:
                kill_name(self.ctx, kills[-1][1] or "")
                return self._finish(target, "chat_kill", anchor, kills[-1][1] or "", lines=len(kills))
            if updated is None and now - box_t >= BOX_GONE_SEC:
                gone = self._chat_readable() and self.account.loot.mode == "auto"
                return self._finish(target, "gone" if gone else "vanished", anchor, f"box gone {now - box_t:.1f}s")
            if self._dist > IN_PLACE_SHOT_PX:
                return self._finish(target, "lost", anchor, f"out of reach at {self._dist:.0f}px")
            paused = now < self.ctx.state.get("skill_pause_until", 0.0)
            if paused:
                self._skipped["paused"] = self._skipped.get("paused", 0) + 1
            if paused or now - last_skill < interval:
                continue
            key, mp = self._pick_skill(skills, rect, self._dist, now)
            if key is None:
                continue  # nothing castable now: stand and wait
            last_skill = now
            if not self.ctx.can_cast(self.account.attack(key).skill_id, rect):
                self._skipped["mp_empty"] = self._skipped.get("mp_empty", 0) + 1
                continue
            anchor, _fired, _hold = self._cast_at_target(key, rect, char, anchor, mp_before=mp)
            self._note_lock(anchor)
        return self._finish(target, "cap" if self.ctx.running else "stopped", anchor if self.ctx.running else None)

    def _no_spell(self, target, rect, char, anchor):
        """PLAN 0.44: "stay put" without a usable attack spell. Warn once, fight by hand what stands next to us
        (a caster still swings), otherwise end the fight at once instead of aiming at nothing for 10 s."""
        self.ctx.state["no_attack_skill"] = True
        if not self._no_skill_said:
            self._no_skill_said = True
            self.log("WARNING: stay-put hunting but no attack skill is enabled - assign one in the skill setup "
                     "(only monsters next to the character can be fought by hand)")
        self._dist = math.hypot(char[0] - anchor[0], char[1] - anchor[1])
        self._skipped = {"no_skill": 1}
        if self._dist <= MELEE_DIST:
            return self.engage(target, rect, char, force_melee=True)
        self._melee, self._box_gone, self._spells = False, 0.0, 0
        self._fight_start = time.time()
        return self._finish(target, "no_spell", anchor, f"{self._dist:.0f}px, no attack skill enabled")

    def engage(self, target, rect, char, force_melee=False):
        """Attack until death/lost/stop. Always hold+drag on entry."""
        if self._shoot_only() and not force_melee:
            return self.engage_ranged(target, rect, char)
        self.last_outcome = None
        watch = DeathWatch()
        skills = self.active_skills()
        interval = self.character.skill_interval
        anchor = target.local
        screen_x, screen_y = target.screen
        self._note_lock(anchor)

        self._fight_start = time.time()
        self._kill_lines(during=False)
        self._dist, self._melee = math.hypot(char[0] - anchor[0], char[1] - anchor[1]), False
        self._box_gone, self._cursor_last = 0.0, None
        melee_seen = False
        melee_max = self.account.scan.melee_max_sec
        # PLAN 0.29 / 1: the chat kill line names the monster; compare with the one we lock (when readable).
        locked_name = self.targeting.read_name(anchor) if self.targeting is not None else None
        # PLAN 0.40: the minimap says there is no way to this monster (behind a fence / hut / watchtower) ->
        # never click: blacklist the spot (60 s, minimap coordinates) and look for another target.
        if (self.targeting is not None and self._dist >= WALL_MIN_DIST
                and self.targeting.route(anchor)[0] == "blocked"):
            self.targeting.block(anchor)
            return self._finish(target, "wall", anchor, f"{self._dist:.0f}px, no way on the minimap")
        if self.health is not None and getattr(self.health, "danger", False):
            return self._finish(target, "danger", anchor, "not starting a fight")  # PLAN 0.40
        self._detour_if_blocked(rect, char, target)
        self._hold_and_drag(screen_x, screen_y)

        last_skill = 0.0
        self._spells, self._skipped = 0, {}
        bursts = 0
        # PLAN 0.27: progress toward the lock (unreachable) and how long the box has been gone (kill vs gone).
        progress_t = time.time()
        best = math.hypot(char[0] - anchor[0], char[1] - anchor[1])
        detours = 0
        started = fight_progress_t = box_t = sword_t = self._fight_start
        sidestepped = False
        try:
            while self.ctx.running and bursts < MAX_COMBAT_BURSTS:
                if time.time() - started >= (melee_max if melee_seen else MAX_FIGHT_SEC):
                    break
                poll_escape(self.ctx)
                if not self.ctx.running:
                    break
                rect = self.ctx.rect()
                char = self.ctx.char_pos(rect)
                # PLAN 0.33: tells the detector thread a fight is running (play-area crop, lower rate).
                self.ctx.state["fight_until"] = time.monotonic() + FIGHT_HINT_SEC
                if self.cure and self.cure.tick(rect):
                    self._rearm(screen_x, screen_y)
                if self.health and self.health.check_death(rect):
                    return self._finish(None, "town" if getattr(self.health, "returned", False) else "char_dead")

                if self.health and getattr(self.health, "just_acted", False):
                    self._rearm(screen_x, screen_y)
                # PLAN 0.40: a damage burst / a crowd next to us: leave the fight so health can step back.
                if self.health is not None and getattr(self.health, "danger", False):
                    return self._finish(target, "danger", anchor)

                time.sleep(BURST_INTERVAL)
                self._check_mp_pending(rect)
                cursor = CursorProbe.current_hash()

                sword = self.ctx.cursors.is_attack(cursor)
                classify = getattr(self.ctx.cursors, "classify", None)
                self._cursor_last = (classify(cursor) if callable(classify) else None) or "unknown"
                if not sword and self.ctx.cursors.is_corpse(cursor):
                    return self._finish(target, "corpse_cursor", anchor)

                updated = None
                if self.targeting is not None:
                    try:
                        updated = self.targeting.track_current(rect, anchor, char=char)
                    except Exception:
                        updated = None

                if updated is not None:
                    slide = math.hypot(updated.local_x - anchor[0], updated.local_y - anchor[1])
                    # In melee the lock should barely move; a big jump means
                    # the tracker hopped to a neighbour.
                    in_melee = math.hypot(char[0] - anchor[0], char[1] - anchor[1]) <= MELEE_LOCK_DIST
                    if in_melee and slide > LOCK_FOLLOW_RADIUS:
                        updated = None
                    else:
                        anchor = updated.local
                        screen_x, screen_y = updated.screen
                        self._note_lock(anchor)
                        if sword and slide <= LOCK_FOLLOW_RADIUS:
                            if slide > 0:
                                self.input.move(screen_x, screen_y)
                        else:
                            self._refresh_hold(screen_x, screen_y)
                        box_t = time.time()

                dist = math.hypot(char[0] - anchor[0], char[1] - anchor[1])
                # PLAN 0.43: a lock held on a remembered point (the detector missed it, see targeting.lock_live)
                # keeps the fight, but only a REAL box counts as melee or as progress - a remembered point must
                # not change when a fight is written off (that is 0.40 / 0.42 wall territory).
                live = updated is not None and getattr(self.targeting, "lock_live", True)
                # PLAN 0.32: melee only while the box is in the newest detection; a stale anchor (own sprite, a pet)
                # used to hold the fight for the whole melee cap.
                melee = sword and dist <= MELEE_DIST and live
                melee_seen = melee_seen or melee
                self._dist, self._melee = dist, melee

                kills = self._kill_lines()
                if kills:
                    killed = kills[-1][1] or ""
                    match = "" if not locked_name else (" = locked" if killed == locked_name else
                                                         f" != locked {locked_name}")
                    kill_name(self.ctx, killed)  # PLAN 4.1: kills per monster
                    return self._finish(target, "chat_kill", anchor, killed + match, lines=len(kills))

                # Body stopped moving under the lock and the sword is gone: dead.
                crop = self.targeting.crop_gray_at(rect, anchor) if self.targeting is not None else None
                if watch.observe(crop) == "dead" and not sword:
                    return self._finish(target, "frozen", anchor)

                now = time.time()
                self._box_gone = round(now - box_t, 1)
                if sword:
                    sword_t = now
                elif dist <= MELEE_DIST and now - sword_t >= NO_SWORD_SEC:
                    return self._finish(target, "lost", anchor, f"no attack cursor for {now - sword_t:.1f}s")
                # PLAN 0.39 / 6: leave a living lock only for a monster hitting us while the lock is not next to us
                # PLAN 0.43: being hit switches to anything within NEAR_KEEP, not only to a much nearer box.
                hurt = self.health is not None and getattr(self.health, "hp_falling", bool)()
                closer = (self.targeting.closer_than(anchor, char, hurt=hurt)
                          if self.targeting is not None and dist > MELEE_DIST else None)
                if closer is not None and self._confirm_switch(rect, closer):
                    # PLAN 0.31 / 2: always the nearest -> fight the one next to us; rehover_last confirms it.
                    self._finish(target, "switch", anchor, f"{closer} at "
                                 f"{math.hypot(closer[0] - char[0], closer[1] - char[1]):.0f}px, lock {dist:.0f}px")
                    self._note_lock(closer)
                    return target
                if closer is not None:
                    self._hold_and_drag(screen_x, screen_y)  # the hover said no monster there: stay on the lock
                if melee:
                    fight_progress_t = progress_t = now  # hitting it: never no_progress / side step / unreachable
                if live:
                    if dist < best - PROGRESS_PX:
                        fight_progress_t = now  # closer = progress
                    if dist <= MELEE_DIST or dist < best - PROGRESS_PX:
                        best, progress_t = min(best, dist), now
                    elif now - progress_t > UNREACH_SEC and dist > best + 4 * PROGRESS_PX:
                        return self._finish(target, "lost", anchor, f"ran off to {dist:.0f}px")
                    elif now - progress_t > (NEAR_UNREACH_SEC if sword and dist <= NEAR_FIGHT_DIST
                                             else UNREACH_SEC):
                        if self.targeting is not None:
                            self.targeting.block(anchor)
                        return self._finish(target, "unreachable", anchor,
                                            f"{dist:.0f}px away for {now - progress_t:.1f}s")
                    elif now - progress_t > DETOUR_AFTER and detours < MAX_DETOURS and self._try_detour(rect, anchor):
                        detours += 1
                        progress_t = time.time()
                        self._hold_and_drag(screen_x, screen_y)

                if dist > MELEE_DIST and now - fight_progress_t > NO_PROGRESS_SEC:
                    if self.targeting is not None:
                        self.targeting.block(anchor)
                    return self._finish(target, "no_progress", anchor,
                                        f"{now - fight_progress_t:.1f}s, sword={'yes' if sword else 'no'}")
                if dist > MELEE_DIST and now - fight_progress_t > SIDESTEP_AFTER and not sidestepped:
                    sidestepped = True
                    self._sidestep(rect, char, anchor)
                    self._hold_and_drag(screen_x, screen_y)

                if updated is None:
                    if self._die_near(anchor):
                        return self._finish(target, "die_box", anchor)
                    if now - box_t >= BOX_GONE_SEC:
                        # PLAN 0.32: no box for a second ends the fight even with the sword up (a stale attack
                        # cursor kept 16 fights of 092741 standing for 25 s). Auto-to-bag server with a readable
                        # chat: every kill writes a kill line, none came -> it walked off. Drop servers write no
                        # kill line: the fall IS the kill (its place feeds the loot walk, PLAN 0.30 / 3).
                        gone = self._chat_readable() and self.account.loot.mode == "auto"
                        return self._finish(target, "gone" if gone else "vanished",
                                            anchor, f"box gone {now - box_t:.1f}s")
                    self._refresh_hold(screen_x, screen_y)

                now = time.time()
                paused = now < self.ctx.state.get("skill_pause_until", 0.0)  # PLAN 0.29: "마법 사용: 실패"
                if skills and not paused and now - last_skill >= interval:
                    key, mp = self._pick_skill(skills, rect, self._dist, now)
                    if key is not None:
                        last_skill = now
                        if self.ctx.can_cast(self.account.attack(key).skill_id, rect):
                            anchor, fired, hold = self._cast_at_target(key, rect, char, anchor, mp_before=mp)
                            if fired:
                                screen_x, screen_y = hold
                                # the same monster again (hand or the next spell); no "lost" while the hold restarts
                                sword_t = max(sword_t, time.time() + CAST_GRACE)
                            self._note_lock(anchor)
                            self._hold_and_drag(screen_x, screen_y)
                        else:
                            self._skipped["mp_empty"] = self._skipped.get("mp_empty", 0) + 1

                bursts += 1

            if self.ctx.running and not melee_seen and self.targeting is not None:
                self.targeting.block(anchor)  # PLAN 0.40: 10 s next to it without ever touching it = a wall
            return self._finish(target, "cap" if self.ctx.running else "stopped",
                                anchor if self.ctx.running else None)
        finally:
            self.input.release_left()
        return target

    def park(self, rect, char):
        px, py = park_point(char[0], char[1])
        self.input.move(*rect.to_screen(px, py))
