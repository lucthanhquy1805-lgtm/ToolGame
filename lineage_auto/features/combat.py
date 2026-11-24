"""Fight a confirmed target.

Hold left + drag like v1.5 to arm continuous auto-attack. Stay on this mob
until the corpse (X) cursor, or the sword is gone and YOLOX no longer sees
the lock. A one-frame box miss while the sword is still up must not leave
and acquire a neighbor — hitting every surrounder pulls the whole pack.
"""

import math
import time

from ..skills.policy import is_auto_enabled
from ..vision.geometry import blocking_figure, detour_point, park_point
from ..vision.motion_watch import DeathWatch
from ..winapi.cursor import CursorProbe
from ..winapi.hotkeys import poll_escape
from .base import Feature
from .targeting import LOCK_FOLLOW_RADIUS, MELEE_LOCK_DIST

DRAG_OFFSET = 15
BURST_INTERVAL = 0.1
NAMEPLATE_BODY_DROP = 25
# Pauses inside hold+drag so the client registers each step.
HOLD_MOVE_SETTLE = 0.02
HOLD_DOWN_SETTLE = 0.04
# Consecutive beats without the lock in view before giving up on it.
LOST_NAME_STREAK = 2
MAX_COMBAT_BURSTS = 150  # safety net; MAX_FIGHT_SEC is the real cap (PLAN 0.28)
# Wait after a detour click before re-arming the attack.
DETOUR_SETTLE = 0.12
# PLAN 0.4: a YOLOX "die" box this close to the lost lock means the mob died there.
DIE_NEAR_RADIUS = 40
# engage() exits that count as a kill (vs lost / gone / unreachable / cap / stopped / char_dead / town).
# PLAN 0.27: chat_kill = a new "아데나 (n) 획득: <name>" line during the fight; vanished = the box left the lock
# and stayed away VANISH_CONFIRM s while the cursor there was not a sword (zones whose chat cannot be read).
KILL_OUTCOMES = ("corpse_cursor", "die_box", "frozen", "chat_kill", "vanished")
VANISH_CONFIRM = 1.5
# A kill line this soon after a fight that ended without a kill belongs to that fight.
LATE_KILL_SEC = 3.0
# PLAN 0.27 / 3: no step closer for this long (beyond melee) = the target cannot be reached (wall, fence).
UNREACH_SEC = 2.5
DETOUR_AFTER = 1.2  # s without progress before walking to the minimap gap once
PROGRESS_PX = 16
MAX_DETOURS = 2
DETOUR_WALK = 0.6  # s given to the walk to the gap before re-arming
# PLAN 0.28 (190646: one orc in tall grass held 54 s with the sword up, no kill): progress = a kill line or the
# character getting closer. Being in melee is not progress. No progress for NO_PROGRESS_SEC (sword or not) -> leave
# and blacklist the spot; one side step at SIDESTEP_AFTER first. No fight lasts longer than MAX_FIGHT_SEC.
# (No monster HP bar to read: the red bar over the head in the recordings is the character's own, it follows HUD HP.)
NO_PROGRESS_SEC = 8.0
SIDESTEP_AFTER = 5.0
SIDESTEP_PX = 60
SIDESTEP_WALK = 0.5
MAX_FIGHT_SEC = 15.0


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

    def _cast_at_target(self, key, rect, char, anchor):
        self.input.release_left()
        time.sleep(0.05)

        target = self.targeting.reacquire_near(rect, char, anchor) if self.targeting else None
        if target is None:
            self.log(f"no nameplate for {key}, skipping this beat")
            return anchor, False

        screen_x = target.screen_x
        screen_y = target.screen_y + NAMEPLATE_BODY_DROP
        self.input.move(screen_x, screen_y)
        time.sleep(0.02)
        self.input.press(key)
        time.sleep(0.05)
        self.input.click_at(screen_x, screen_y)
        self.log(f"skill {key} on nameplate {target.local}")
        return (target.local_x, target.local_y), True

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

    def _finish(self, target, outcome, anchor=None, detail=""):
        """Leave the fight; record why (kills feed stats, loot and the field log)."""
        self.last_outcome = outcome
        self._ended_at = time.time()
        seconds = self._ended_at - self._fight_start
        if anchor is not None:
            self.last_anchor = anchor
            self.last_world = self.targeting.world(anchor) if self.targeting is not None else None
        self._clear_lock()
        note = f" ({detail})" if detail else ""
        if outcome in KILL_OUTCOMES:
            self.ctx.state["kills"] = self.ctx.state.get("kills", 0) + 1
            if outcome == "chat_kill":
                self.ctx.state["kills_chat"] = self.ctx.state.get("kills_chat", 0) + 1
            self.log(f"monster dead ({outcome}){note}")
        else:
            self.log({"lost": "lost target", "cap": f"fight cap {seconds:.0f}s, leaving lock",
                      "gone": "target gone, no kill line", "unreachable": "target unreachable, blacklisted",
                      "no_progress": "no progress, blacklisted"}
                     .get(outcome, outcome) + note)
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.count(f"end_{outcome}")
            if outcome in KILL_OUTCOMES:
                rec.count("kills")
            rec.event("fight_end", outcome=outcome, detail=detail, seconds=round(seconds, 1),
                      anchor=list(anchor) if anchor is not None else None)
            rec.fight(outcome, seconds, outcome in KILL_OUTCOMES)
        return target

    def _late_kills(self):
        """Kill lines that arrived after the last fight ended without a kill: that fight was a kill (PLAN 0.27)."""
        if self.targeting is None:
            return
        late = self.targeting.pop_kills()
        if not late or self.last_outcome in KILL_OUTCOMES or time.time() - self._ended_at > LATE_KILL_SEC:
            return
        self.ctx.state["kills"] = self.ctx.state.get("kills", 0) + 1
        self.ctx.state["kills_chat"] = self.ctx.state.get("kills_chat", 0) + 1
        self.log(f"late kill line {late[-1][1]} -> previous fight ({self.last_outcome}) was a kill")
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.count("kills")
            rec.count("late_chat_kill")
        self.last_outcome = "chat_kill"

    def _chat_readable(self):
        watch = getattr(self.targeting, "kill_watch", None)
        return watch is not None and watch.last_lines > 0

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

    def engage(self, target, rect, char):
        """Attack until death/lost/stop. Always hold+drag on entry."""
        self.last_outcome = None
        watch = DeathWatch()
        skills = self.active_skills()
        interval = self.character.skill_interval
        anchor = target.local
        screen_x, screen_y = target.screen
        self._note_lock(anchor)

        self._late_kills()
        # PLAN 0.29 / 1: the chat kill line names the monster; compare with the one we lock (when readable).
        locked_name = self.targeting.read_name(anchor) if self.targeting is not None else None
        self._detour_if_blocked(rect, char, target)
        self._hold_and_drag(screen_x, screen_y)

        last_skill = 0.0
        bursts = 0
        lost = 0
        # PLAN 0.27: progress toward the lock (unreachable) and how long the box has been gone (kill vs gone).
        progress_t = time.time()
        best = math.hypot(char[0] - anchor[0], char[1] - anchor[1])
        detours = 0
        gone_since = None
        self._fight_start = started = fight_progress_t = time.time()
        sidestepped = False
        try:
            while self.ctx.running and bursts < MAX_COMBAT_BURSTS and time.time() - started < MAX_FIGHT_SEC:
                poll_escape(self.ctx)
                if not self.ctx.running:
                    break
                rect = self.ctx.rect()
                char = self.ctx.char_pos(rect)
                if self.cure and self.cure.tick(rect):
                    self._rearm(screen_x, screen_y)
                if self.health and self.health.check_death(rect):
                    return self._finish(None, "town" if getattr(self.health, "returned", False) else "char_dead")

                if self.health and getattr(self.health, "just_acted", False):
                    self._rearm(screen_x, screen_y)

                time.sleep(BURST_INTERVAL)
                cursor = CursorProbe.current_hash()

                sword = self.ctx.cursors.is_attack(cursor)
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
                        lost = 0
                        gone_since = None

                kills = self.targeting.pop_kills() if self.targeting is not None else []
                if kills:
                    killed = kills[-1][1] or ""
                    match = "" if not locked_name else (" = locked" if killed == locked_name else
                                                         f" != locked {locked_name}")
                    return self._finish(target, "chat_kill", anchor, killed + match)

                # Body stopped moving under the lock and the sword is gone: dead.
                crop = self.targeting.crop_gray_at(rect, anchor) if self.targeting is not None else None
                if watch.observe(crop) == "dead" and not sword:
                    return self._finish(target, "frozen", anchor)

                now = time.time()
                if updated is not None:
                    dist = math.hypot(char[0] - anchor[0], char[1] - anchor[1])
                    if dist < best - PROGRESS_PX:
                        fight_progress_t = now  # closer = progress; melee alone is not (PLAN 0.28)
                    if dist <= MELEE_LOCK_DIST or dist < best - PROGRESS_PX:
                        best, progress_t = min(best, dist), now
                    elif now - progress_t > UNREACH_SEC and dist > best + 4 * PROGRESS_PX:
                        return self._finish(target, "lost", anchor, f"ran off to {dist:.0f}px")
                    elif now - progress_t > UNREACH_SEC:
                        if self.targeting is not None:
                            self.targeting.block(anchor)
                        return self._finish(target, "unreachable", anchor,
                                            f"{dist:.0f}px away for {now - progress_t:.1f}s")
                    elif now - progress_t > DETOUR_AFTER and detours < MAX_DETOURS and self._try_detour(rect, anchor):
                        detours += 1
                        progress_t = time.time()
                        self._hold_and_drag(screen_x, screen_y)

                if now - fight_progress_t > NO_PROGRESS_SEC:
                    if self.targeting is not None:
                        self.targeting.block(anchor)
                    return self._finish(target, "no_progress", anchor,
                                        f"{now - fight_progress_t:.1f}s, sword={'yes' if sword else 'no'}")
                if now - fight_progress_t > SIDESTEP_AFTER and not sidestepped:
                    sidestepped = True
                    self._sidestep(rect, char, anchor)
                    self._hold_and_drag(screen_x, screen_y)

                if updated is None:
                    if self._die_near(anchor):
                        return self._finish(target, "die_box", anchor)
                    if sword:
                        # PLAN 0.27: most "lost target" of the first orc hunt were a box missing for two beats
                        # while the monster stood under the mouse; the sword says it is still there.
                        lost = 0
                        gone_since = None
                    else:
                        lost += 1
                        if lost >= LOST_NAME_STREAK:
                            gone_since = gone_since or now
                            if now - gone_since >= VANISH_CONFIRM:
                                # Auto-to-bag server with a readable chat: every kill writes a kill line, none
                                # came -> it walked off. Drop servers write no kill line: the fall IS the kill
                                # (its place feeds the loot walk, PLAN 0.30 / 3).
                                gone = self._chat_readable() and self.account.loot.mode == "auto"
                                return self._finish(target, "gone" if gone else "vanished",
                                                    anchor, f"box gone {now - gone_since:.1f}s")
                        self._refresh_hold(screen_x, screen_y)

                now = time.time()
                paused = now < self.ctx.state.get("skill_pause_until", 0.0)  # PLAN 0.29: "마법 사용: 실패"
                if skills and not paused and now - last_skill >= interval:
                    key = skills[bursts % len(skills)]
                    skill_id = self.account.attack(key).skill_id
                    last_skill = now
                    if self.ctx.can_cast(skill_id, rect):
                        anchor, fired = self._cast_at_target(key, rect, char, anchor)
                        if fired:
                            screen_x, screen_y = rect.to_screen(anchor[0], anchor[1] + NAMEPLATE_BODY_DROP)
                        self._note_lock(anchor)
                        self._hold_and_drag(screen_x, screen_y)

                bursts += 1

            return self._finish(target, "cap" if self.ctx.running else "stopped")
        finally:
            self.input.release_left()
        return target

    def park(self, rect, char):
        px, py = park_point(char[0], char[1])
        self.input.move(*rect.to_screen(px, py))
