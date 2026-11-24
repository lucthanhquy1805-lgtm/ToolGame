"""Cure Poison utility feature.

Poison shows as a green HP bar in the bottom status frame, which is the one
signal the client always renders. Buff-bar debuff icons are too small and
blurry to match reliably, so they are not used here.
"""

import time

from ..characters.base import HOTKEYS
from ..vision.poison import PresentStreak
from .base import Feature

CURE_SKILL_ID = "388"
CAST_COOLDOWN = 2.5
PRESENT_NEEDED = 2


class CurePoisonFeature(Feature):
    key = "cure_poison"

    def __init__(self, ctx, clock=time.time):
        super().__init__(ctx)
        self.clock = clock
        self._present = PresentStreak(PRESENT_NEEDED)
        self.last_cast = None

    def enabled_key(self) -> str | None:
        for key in HOTKEYS:
            setting = self.account.utility(key)
            if setting.enabled and setting.skill_id == CURE_SKILL_ID:
                return key
        return None

    def tick(self, rect):
        key = self.enabled_key()
        if key is None:
            return False

        self.ctx.hp_reader.read_percent(self.ctx.grabber, rect)
        hp_green = bool(self.ctx.hp_reader.last_fill_is_green)

        if not self._present.observe(hp_green):
            return False

        now = self.clock()
        if self.last_cast is not None and now - self.last_cast < CAST_COOLDOWN:
            return False

        if not self.ctx.can_cast(CURE_SKILL_ID, rect):
            return False

        # A held attack button would turn the self-cast into a target cast.
        self.input.release_left()
        self.input.double_press(key)
        self.last_cast = now
        self.log(f"{key} cure poison (self-cast)")
        return True

    def on_start(self):
        self._reset()

    def on_stop(self):
        self._reset()

    def _reset(self):
        self._present.reset()
        self.last_cast = None
