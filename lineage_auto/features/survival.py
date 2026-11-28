"""Keep the character alive: heal skill, potion, death detection."""
import math
import time

from .. import hunt_maps
from ..runtime.stats import bump
from ..skills.policy import HEAL_SKILL_ID
from ..vision import hotbar
from .base import Feature

SKILL_COOLDOWN = 3.0
POTION_COOLDOWN = 1.5
# Give a heal skill time to land before also drinking a potion.
SKILL_SETTLE = 0.8
# Consecutive 0% bar reads before the character counts as dead.
DEATH_CONFIRMATIONS = 3
# Exact "HP:0/x" HUD text is trusted sooner (PLAN 0.3).
HUD_DEATH_CONFIRMATIONS = 2
# Consecutive reads under return_pct before using the return scroll (PLAN 1.3).
RETURN_CONFIRMATIONS = 2
# PLAN 0.3: the death window covers the HUD, so HP numbers vanish while HP was already low - but so do a
# loading / teleport screen and any dialog drawn over the HUD (user 26/11). Missing numbers are therefore never
# called a death: the hunt stops safely as "HUD lost" instead, and only "HP:0" is death. Loading screens are
# ruled out first: the 83 night frames of 20261126_101941_hunt have a mean brightness of 54-62, a loading
# screen is nearly black, so under LOADING_DARK the timer just starts over.
LOW_FOR_DEATH_PCT = 50
HUD_GONE_DEAD_SEC = 2.0
LOADING_DARK = 30
DEATH_SNAPSHOTS = 3
# PLAN 0.40 (20261126_101941_hunt: HP 90 -> 46 % in 2 s at the end, MP down to 2 % so no heal spell was left):
# a burst of damage or a crowd next to the character is an emergency - heal / drink at once whatever
# threshold_pct says, step back out of the crowd, and use the return scroll while HP is still high when nothing
# can heal any more. Measured: >= 3 boxes within MELEE_DIST happened in 0 of the 412 frames of that hunt and in
# 24 of the 736 frames of 20261126_090350_hunt (the good run at 오크의 땅), so the crowd rule is rare but not free:
# user 26/11, it must not cost that run its 5.25 kills/min -> the crowd rule only runs on an `mp_hungry` ground
# (fallen_blessed), everywhere else only the HP burst counts.
DANGER_DROP_PCT = 20
DANGER_WINDOW = 2.0
DANGER_MOBS = 3
DANGER_HOLD = 3.0  # the emergency stays on this long after the last burst
DANGER_HEAL_PCT = 90  # healing at (nearly) full HP only burns the MP this ground is short of
DANGER_RETURN_PCT = 80  # danger + nothing left to heal with = return scroll now, before HP < 50 %
RETREAT_PX = 120
RETREAT_COOLDOWN = 1.5
# PLAN 1.4b (20261127_003555_hunt: F1+F6 held 2 mana potions, both gone at 137 s, then pressed every 1.5 s for
# 12 minutes): an extra potion whose hotbar slot reads empty on EMPTY_READS pictures EMPTY_READ_SEC apart is
# marked out and never pressed again until the slot shows an item (looked at every RECHECK_SEC) or the next start.
EMPTY_READS = 2
EMPTY_READ_SEC = 1.0
RECHECK_SEC = 180.0


class HealthFeature(Feature):
    key = "health"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.last_hp = 100
        self.last_mp = None
        self._last_skill = 0.0
        self._last_potion = 0.0
        self._extra_used = {}
        self._empty = {}  # PLAN 1.4b: potion slot index -> when it was last seen empty
        self._empty_reads = {}  # slot index -> (consecutive empty reads, time of the last read)
        self._zero_reads = 0
        self.dead = False
        self._low_reads = 0
        # True once the return scroll was used: the session stops (PLAN 1.3).
        self.returned = False
        # True when this tick pressed a heal/potion (combat re-arms afterwards).
        self.just_acted = False
        # PLAN 0.40: emergency (damage burst / crowd); combat leaves the fight while it is on.
        self.danger = False
        # PLAN 0.3: True when the HUD HP numbers vanished for good - a safe stop, not a death.
        self.hud_lost = False
        self._danger_until = 0.0
        self._hp_log = []
        self._last_retreat = 0.0
        self._hud_t = 0.0  # PLAN 0.3: when the HUD HP numbers were last read, and whether HP was low then
        self._hud_low = False

    @property
    def settings(self):
        return self.account.health

    @property
    def active(self):
        return self.settings.use_skill or self.settings.use_potion

    def read(self, rect):
        self.last_hp = self.ctx.read_hp(rect)
        self.ctx.state["hp"] = self.last_hp
        self.last_mp = self.ctx.read_mp(rect)
        return self.last_hp

    def tick(self, rect):
        """Read HP/MP and recover if needed. Returns the current HP percentage."""
        hp = self.read(rect)
        self.just_acted = False
        if hp == 0 and self.ctx.state.get("hp_source") == "hud":
            return hp  # PLAN 0.3: the HUD says exactly 0 - dead, never press anything (check_death stops)
        if self._danger_now(hp):
            self._emergency(rect, hp)
        elif self.active and hp < self.settings.threshold_pct:
            self._recover(hp)
        if not self.just_acted:
            self._extra_potions(hp, rect)
        return hp

    def hp_falling(self):
        """PLAN 0.43: HP lower now than at some point in the last DANGER_WINDOW s = something is hitting us."""
        return bool(self._hp_log) and self._hp_log[-1][1] < max(e[1] for e in self._hp_log)

    def _danger_now(self, hp):
        """PLAN 0.40: HP falling fast or a crowd next to the character (sticky for DANGER_HOLD s)."""
        now = time.time()
        if hp:
            self._hp_log = [e for e in self._hp_log if now - e[0] <= DANGER_WINDOW] + [(now, hp)]
            drop = max(e[1] for e in self._hp_log) - hp
            crowd = hunt_maps.get(self.account.hunt_map).mp_hungry
            mobs = len(self.ctx.state.get("mobs_near") or ()) if crowd else 0
            if drop >= DANGER_DROP_PCT or mobs >= DANGER_MOBS:
                if now >= self._danger_until:
                    self.log(f"danger: {hp}% hp (-{drop}% in {DANGER_WINDOW:.0f}s), {mobs} monsters next to us")
                    # PLAN 0.47: one event per episode (191624 wrote 11 "danger" fight endings for one burst)
                    rec = getattr(self.ctx, "recorder", None)
                    if rec is not None:
                        rec.event("danger", hp=hp, drop=drop, mobs=mobs)
                self._danger_until = now + DANGER_HOLD
        self.danger = now < self._danger_until
        # PLAN 0.47: the detector runs its near crop at once while we are being hit
        self.ctx.state["hp_falling"] = self.danger or self.hp_falling()
        return self.danger

    def _emergency(self, rect, hp):
        """Heal / drink at once, then back out of the crowd; to town while HP is high if nothing can heal."""
        if hp and hp < DANGER_HEAL_PCT:
            self._recover(hp)
            if self._no_heal_left() and hp < DANGER_RETURN_PCT and self.settings.return_town:
                self._go_town(hp, why="danger, nothing left to heal with")
                return
        self._retreat(rect)

    def _no_heal_left(self):
        """No heal spell castable (MP) and no HP potion configured."""
        if self.settings.use_skill and self.ctx.can_cast(HEAL_SKILL_ID):
            return False
        if self.settings.use_potion:
            return False
        return not any(p.enabled and p.stat == "hp" for p in self.settings.potions)

    def _retreat(self, rect):
        """One step straight away from the monsters next to the character (never while a fight holds the mouse).

        shortcut: the step is only clamped into the client area, not checked against the minimap; upgrade to
        targeting.route() if the character starts backing into fences."""
        mobs = self.ctx.state.get("mobs_near") or ()
        now = time.time()
        if not mobs or now - self._last_retreat < RETREAT_COOLDOWN:
            return
        if time.monotonic() < self.ctx.state.get("fight_until", 0.0):  # combat writes it on the monotonic clock
            return
        char = self.ctx.char_pos(rect)
        mx = sum(p[0] for p in mobs) / len(mobs)
        my = sum(p[1] for p in mobs) / len(mobs)
        dx, dy = char[0] - mx, char[1] - my
        n = math.hypot(dx, dy) or 1.0
        x = min(max(char[0] + dx / n * RETREAT_PX, 40), rect.w - 40)
        y = min(max(char[1] + dy / n * RETREAT_PX, 40), rect.h - 40)
        self.log(f"danger: stepping back from {len(mobs)} monsters to ({x:.0f}, {y:.0f})")
        self._last_retreat = now
        self.input.release_left()
        self.input.click_at(*rect.to_screen(int(x), int(y)))
        bump(self.ctx, "retreat")
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.count("retreat")

    def _extra_potions(self, hp, rect=None):
        """PLAN 1.4: drink the first due extra potion (slot order = priority), one per tick."""
        now = time.time()
        for i, potion in enumerate(self.settings.potions):
            if not potion.enabled:
                continue
            if i in self._empty:
                if now - self._empty[i] < RECHECK_SEC:
                    continue
                self._empty[i] = now
                if self._slot_empty(rect, potion) is not False:
                    continue  # still empty, or its page is not open: look again later
                del self._empty[i]
                self._show_empty()
                self.log(f"potion {potion.page}+{potion.key} is back")
            value = hp if potion.stat == "hp" else self.last_mp
            # hp 0 is death (check_death), mp None = unreadable
            if value is None or (potion.stat == "hp" and not value) or value >= potion.pct:
                continue
            if self._out_of_potions(i, potion, rect, now):
                continue
            if now - self._extra_used.get(i, 0.0) < potion.cooldown:
                continue
            self.log(f"{value}% {potion.stat} -> potion {potion.page}+{potion.key}")
            self.ctx.press_slot(potion.page, potion.key)
            bump(self.ctx, f"potion_{potion.stat}")
            self._extra_used[i] = now
            self.just_acted = True
            return

    def _slot_empty(self, rect, potion):
        """PLAN 1.4b: True / False from the hotbar picture, None when the slot's page is not the open one."""
        if rect is None:
            return None
        try:
            frame = self.ctx.grabber.grab_bgr(rect)
        except Exception:
            return None
        if frame is None or hotbar.open_page(frame) != potion.page:
            return None
        return hotbar.slot_empty(frame, potion.key)

    def _out_of_potions(self, i, potion, rect, now):
        """Read a due potion's slot (at most every EMPTY_READ_SEC); EMPTY_READS empty pictures = mark it out."""
        n, last = self._empty_reads.get(i, (0, -EMPTY_READ_SEC))
        if now - last < EMPTY_READ_SEC:
            return False
        empty = self._slot_empty(rect, potion)
        if empty is None:
            return False
        n = n + 1 if empty else 0
        self._empty_reads[i] = (n, now)
        if n < EMPTY_READS:
            return False
        self._empty[i], self._empty_reads[i] = now, (0, now)
        slot = f"{potion.page}+{potion.key}"
        self.log(f"WARNING: no potion left in {slot} - not pressed again until the slot shows one "
                 f"(checked every {RECHECK_SEC / 60:.0f} min) or the next start")
        self._show_empty()
        bump(self.ctx, "potion_empty")
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.count("potion_empty")
            rec.event("potion_empty", slot=slot, stat=potion.stat)
        return True

    def _show_empty(self):
        """ctx.state["potion_empty"]: the slots the UI warns about."""
        self.ctx.state["potion_empty"] = [f"{p.page}+{p.key}" for i, p in enumerate(self.settings.potions)
                                          if i in self._empty]

    def _recover(self, hp):
        now = time.time()
        can_heal = self.ctx.can_cast(HEAL_SKILL_ID)
        if self.settings.use_skill and now - self._last_skill > SKILL_COOLDOWN and can_heal:
            self.log(f"{hp}% hp -> heal skill {self.settings.skill_page}+{self.settings.skill_key}")
            self.ctx.press_slot(self.settings.skill_page, self.settings.skill_key, double=True)
            self.cancel_aim("heal skill")  # PLAN 1.10
            bump(self.ctx, "heal_skill")
            self._last_skill = now
            self.just_acted = True
        elif (
            self.settings.use_potion
            and now - self._last_potion > POTION_COOLDOWN
            and now - self._last_skill > SKILL_SETTLE
        ):
            mp = self.ctx.state.get("mp")
            extra = f" mp {mp}%" if mp is not None else ""
            self.log(f"{hp}% hp{extra} -> potion {self.settings.potion_page}+{self.settings.potion_key}")
            self.ctx.press_slot(self.settings.potion_page, self.settings.potion_key)
            bump(self.ctx, "potion_hp")
            self._last_potion = now
            self.just_acted = True

    def check_death(self, rect):
        """Tick health and report whether the session must stop (dead or sent to town).

        A bar zero is only trusted when HP monitoring is on, otherwise a missing
        template would read as a permanent zero. The HUD text "HP:0/x" is
        exact, so it counts even with healing off and needs fewer reads.
        Heal skill / potion run first (tick); the return scroll is the last resort.
        """
        if self.returned:
            return True
        why = self._hud_gone(rect)  # PLAN 0.3: checked before the tick, so this beat presses nothing
        if why:
            self._stop_hud_lost(why, rect)
            return True
        hp = self.tick(rect)
        if self._should_return(hp):
            self._go_town(hp)
            return True
        from_hud = self.ctx.state.get("hp_source") == "hud"
        if hp == 0 and (self.active or from_hud):
            self._zero_reads += 1
            needed = HUD_DEATH_CONFIRMATIONS if from_hud else DEATH_CONFIRMATIONS
            if self._zero_reads >= needed:
                self._die("hud HP:0" if from_hud else "bar 0%", rect)
                return True
            return False
        self._zero_reads = 0
        return False

    def _should_return(self, hp):
        s = self.settings
        if not s.return_town or not hp or hp >= s.return_pct:
            self._low_reads = 0
            return False
        self._low_reads += 1
        return self._low_reads >= RETURN_CONFIRMATIONS

    def _go_town(self, hp, why=None):
        self.input.release_left()
        self.log(f"{why or f'{hp}% hp < {self.settings.return_pct}%'} -> return scroll "
                 f"{self.settings.return_page}+{self.settings.return_key}, stopping")
        self.ctx.press_slot(self.settings.return_page, self.settings.return_key)
        bump(self.ctx, "town")
        self.returned = True

    def _hud_gone(self, rect):
        """PLAN 0.3 (user 26/11): the reason for a safe stop when the HUD HP numbers are gone, else None.

        Low HP and then no numbers is NOT read as a death: a loading / teleport screen or a dialog over the
        HUD looks exactly the same. Only "HP:0" (check_death) and the resurrection window are deaths."""
        now = time.time()
        if self.ctx.state.get("hp_abs") is not None:
            self._hud_t, self._hud_low = now, self.last_hp is not None and self.last_hp <= LOW_FOR_DEATH_PCT
            return None
        if not self._hud_low or now - self._hud_t < HUD_GONE_DEAD_SEC:
            return None
        loading = self._loading_screen(rect)
        if loading:
            self._hud_t = now  # start the 2 s over once the ground is back on screen
            self.log(f"HUD HP gone but {loading} - waiting, not a death")
            return None
        return f"HUD HP gone for {HUD_GONE_DEAD_SEC:.0f} s after {self.last_hp}% hp"

    def _loading_screen(self, rect):
        """Why the HUD may be missing without anything being wrong (dark screen / another map), else ""."""
        from .. import monsters
        from ..vision.map_name import MapNameReader

        try:
            frame = self.ctx.grabber.grab_bgr(rect)
            if frame is None:
                return "there is no frame"
            if float(frame[::4, ::4].mean()) < LOADING_DARK:
                return "the whole screen is dark (loading / teleport)"
            zone = self.account.record.real_map
            cat = monsters.for_real_map(zone)
            seen = MapNameReader().read(frame)[0]
            if seen and cat is not None and not monsters.fits_map_name(cat, seen):
                return f"the map on screen is {seen}, not {zone} (teleported)"
        except Exception as exc:
            return f"the screen could not be checked ({exc})"
        return ""

    def _stop_hud_lost(self, why, rect):
        """Safe stop: release everything, keep pictures, but do not count a death (PLAN 0.3, user 26/11)."""
        self.hud_lost = True
        self.input.release_all()
        self.log(f"WARNING: {why} -> safe stop (HUD lost; not counted as a death)")
        self._snapshot_death(rect, "hud_lost")

    def _die(self, why, rect):
        """Stop the hunt: no more clicks or keys, a WARNING in the log, the death screen kept (PLAN 0.3)."""
        self.dead = True
        bump(self.ctx, "death")
        self.input.release_all()
        self.log(f"WARNING: character is dead ({why}), stopping - no more clicks or keys")
        self._snapshot_death(rect)

    def _snapshot_death(self, rect, kind="death"):
        """Keep DEATH_SNAPSHOTS raw screens (records/deaths/<kind>_*.png) for the restart-window check."""
        from ..runtime.recorder import save_snapshot

        for i in range(DEATH_SNAPSHOTS):
            try:
                path = save_snapshot(self.ctx.grabber.grab_bgr(rect), "deaths",
                                     prefix=f"{kind}_{i + 1}_", png=True)
                self.log(f"{kind} screen saved: {path}")
            except Exception as exc:
                self.log(f"{kind} screen not saved: {exc}")
                return

    def on_start(self):
        self.dead = False
        # PLAN 1.4b: potions marked out are tried again (the player may have restocked).
        self._empty, self._empty_reads = {}, {}
        self.ctx.state["potion_empty"] = []
        self.hud_lost = False
        self.returned = False
        self._zero_reads = 0
        self._low_reads = 0
        self._hud_t, self._hud_low = 0.0, False
        self.danger = False
        self._danger_until = 0.0
        self._hp_log = []
