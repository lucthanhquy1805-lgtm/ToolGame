"""Keep the character alive: heal skill, potion, death detection."""
import time

from ..skills.policy import HEAL_SKILL_ID
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


class HealthFeature(Feature):
    key = "health"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.last_hp = 100
        self.last_mp = None
        self._last_skill = 0.0
        self._last_potion = 0.0
        self._extra_used = {}
        self._zero_reads = 0
        self.dead = False
        self._low_reads = 0
        # True once the return scroll was used: the session stops (PLAN 1.3).
        self.returned = False
        # True when this tick pressed a heal/potion (combat re-arms afterwards).
        self.just_acted = False

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
        if self.active and hp < self.settings.threshold_pct:
            self._recover(hp)
        if not self.just_acted:
            self._extra_potions(hp)
        return hp

    def _extra_potions(self, hp):
        """PLAN 1.4: drink the first due extra potion (slot order = priority), one per tick."""
        now = time.time()
        for i, potion in enumerate(self.settings.potions):
            if not potion.enabled:
                continue
            value = hp if potion.stat == "hp" else self.last_mp
            # hp 0 is death (check_death), mp None = unreadable
            if value is None or (potion.stat == "hp" and not value) or value >= potion.pct:
                continue
            if now - self._extra_used.get(i, 0.0) < potion.cooldown:
                continue
            self.log(f"{value}% {potion.stat} -> potion {potion.page}+{potion.key}")
            self.ctx.press_slot(potion.page, potion.key)
            self._extra_used[i] = now
            self.just_acted = True
            return

    def _recover(self, hp):
        now = time.time()
        can_heal = self.ctx.can_cast(HEAL_SKILL_ID)
        if self.settings.use_skill and now - self._last_skill > SKILL_COOLDOWN and can_heal:
            self.log(f"{hp}% hp -> heal skill {self.settings.skill_page}+{self.settings.skill_key}")
            self.ctx.press_slot(self.settings.skill_page, self.settings.skill_key, double=True)
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
        hp = self.tick(rect)
        if self._should_return(hp):
            self._go_town(hp)
            return True
        from_hud = self.ctx.state.get("hp_source") == "hud"
        if hp == 0 and (self.active or from_hud):
            self._zero_reads += 1
            needed = HUD_DEATH_CONFIRMATIONS if from_hud else DEATH_CONFIRMATIONS
            if self._zero_reads >= needed:
                self.dead = True
                self.log(f"character is dead ({'hud HP:0' if from_hud else 'bar 0%'}), stopping")
                self._snapshot_death(rect)
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

    def _go_town(self, hp):
        self.input.release_left()
        self.log(f"{hp}% hp < {self.settings.return_pct}% -> return scroll "
                 f"{self.settings.return_page}+{self.settings.return_key}, stopping")
        self.ctx.press_slot(self.settings.return_page, self.settings.return_key)
        self.returned = True

    def _snapshot_death(self, rect):
        """Keep the death screen (records/deaths/) to teach the restart-window check later."""
        try:
            from ..runtime.recorder import save_snapshot

            path = save_snapshot(self.ctx.grabber.grab_bgr(rect), "deaths")
            self.log(f"death screen saved: {path}")
        except Exception as exc:
            self.log(f"death screen not saved: {exc}")

    def on_start(self):
        self.dead = False
        self.returned = False
        self._zero_reads = 0
        self._low_reads = 0
