"""Auto buff upkeep: start casts, timer rebuff, and an instant recast when the chat says a buff ran out.

A press always starts the duration timer. The buff-bar icon is only used
to wait out the ~1s hotbar spin before the next F-key, so F11 is not eaten
by F10's cast. Icon match can fail on scaled HUDs; that must not unblock
mid-fight recasts every 8s. Rebuff is countdown-only.

Cast times survive Stop/Start: the clock is wall time and the table is not
cleared, so restarting the session does not recast buffs that are still up.
Entries are keyed by (F-key, skill_id) so reassigning a slot starts fresh.
"""

import time

from ..characters.base import HOTKEYS
from ..skills.catalog import get_catalog
from ..skills.policy import is_auto_enabled, use_mechanism
from ..vision.buff_icons import icon_present_in_buff_bar, merge_buff_vision
from ..winapi.hotkeys import poll_escape
from .base import Feature

# Longest wait for the buff icon after a press (hotbar spin is ~1s).
CAST_WAIT_SEC = 2.5
CAST_POLL = 0.15
# Kept for callers that used the old name.
CAST_SETTLE = CAST_WAIT_SEC
# Never retry the same slot faster than this, even if its timer says expired.
REBUFF_FLOOR_SEC = 8.0
# Minimum spacing between two buff presses so the next F-key is not eaten.
CAST_GAP_SEC = 1.2


class BuffFeature(Feature):
    key = "buff"

    def __init__(
        self,
        ctx,
        health=None,
        clock=time.time,
        catalog=None,
        icon_present=None,
        cast_wait=None,
        cast_gap=None,
    ):
        super().__init__(ctx)
        self.health = health
        self.clock = clock
        self.catalog = catalog
        self._icon_present = icon_present
        self._cast_wait = CAST_WAIT_SEC if cast_wait is None else float(cast_wait)
        self._cast_gap = CAST_GAP_SEC if cast_gap is None else float(cast_gap)
        # (key, skill_id) -> clock() of the last completed cast.
        self.last_cast = {}
        self._last_attempt = {}

    def enabled_keys(self):
        """F-keys with maintain_buff skills allowed in the current product phase."""
        keys = []
        for key in HOTKEYS:
            setting = self.account.buff(key)
            if not setting.enabled or not setting.skill_id:
                continue
            if not is_auto_enabled(setting.skill_id):
                continue
            if use_mechanism(setting.skill_id).get("kind") != "maintain_buff":
                continue
            keys.append(key)
        return sorted(keys)

    def _slot(self, key):
        return key, self.account.buff(key).skill_id

    def elapsed(self, key, now=None):
        """Seconds since this slot's current skill was last cast."""
        last = self.last_cast.get(self._slot(key))
        if last is None:
            return None
        return (self.clock() if now is None else now) - last

    def remaining(self, key, now=None):
        """Seconds of buff left, or 0 when expired / never cast."""
        elapsed = self.elapsed(key, now)
        if elapsed is None:
            return 0.0
        duration_sec = self.account.buff(key).duration_min * 60
        return max(0.0, duration_sec - elapsed)

    def _mark_cast(self, key):
        self.last_cast[self._slot(key)] = self.clock()

    def _icon_up(self, key):
        skill_id = self.account.buff(key).skill_id
        if self._icon_present is not None:
            return bool(self._icon_present(skill_id))
        try:
            frame = self.ctx.grabber.grab_bgr(self.ctx.rect())
            catalog = self.catalog if self.catalog is not None else get_catalog()
            template = catalog.load_icon_bgr(skill_id)
            if frame is None or template is None:
                return False
            cfg = merge_buff_vision(self.account.buff_vision)
            return icon_present_in_buff_bar(frame, template, cfg)
        except Exception:
            return False

    def _still_running(self):
        return bool(getattr(self.ctx, "running", True))

    def _try_cast(self, key):
        if not self._still_running():
            return False
        skill_id = self.account.buff(key).skill_id
        if not self.ctx.can_cast(skill_id, self.ctx.rect()):
            self.log(f"{key} skip buff {skill_id} (no MP)")
            return False

        self.ctx.press_slot(self.account.buff(key).page, key, double=True)
        pressed_at = time.monotonic()
        self._last_attempt[self._slot(key)] = self.clock()
        self.log(f"{key} buff {self.account.buff(key).skill_id} (self-cast)")
        self.cancel_aim(f"buff {skill_id}")  # PLAN 1.10
        deadline = pressed_at + self._cast_wait
        while self._still_running():
            poll_escape(self.ctx)
            if not self._still_running():
                return False
            if self._icon_up(key):
                break
            if time.monotonic() >= deadline:
                self.log(f"{key} icon not seen, timer started anyway")
                break
            time.sleep(CAST_POLL)
        gap_left = self._cast_gap - (time.monotonic() - pressed_at)
        if gap_left > 0 and self._still_running():
            time.sleep(gap_left)
        self._mark_cast(key)
        return True

    def on_start(self):
        """Cast buffs whose duration timer is not still running."""
        for key in self.enabled_keys():
            if not self._still_running():
                self.log("buff cast aborted")
                return
            left = self.remaining(key)
            if left > 0:
                self.log(f"{key} still buffed ({int(left)}s left)")
                continue
            self._try_cast(key)

    def expired_from_chat(self):
        """PLAN 2.1b: a "<buff> ran out" chat line clears that slot's timer, so tick recasts it now.

        The ids come from vision/name_reader.buff_gone_skill (ctx.state["buff_gone"], filled by targeting.see).
        A line for a skill no slot is set to is only logged - the picture is there but nobody casts it."""
        gone = self.ctx.state.get("buff_gone") or []
        if not gone:
            return
        self.ctx.state["buff_gone"] = []
        keys = {self.account.buff(key).skill_id: key for key in self.enabled_keys()}
        for skill_id in gone:
            key = keys.get(skill_id)
            if key is None:
                self.log(f"chat: buff {skill_id} ran out but no slot is set to it")
                continue
            self.last_cast.pop(self._slot(key), None)
            self._last_attempt.pop(self._slot(key), None)
            self.log(f"chat: buff {skill_id} ran out -> recast {key} now")

    def tick(self, rect):
        if self.health is not None and self.health.active and self.health.last_hp < self.health.settings.threshold_pct:
            # Healing has priority; do not spend a turn on buffs at low HP (the chat lines wait in the state).
            return
        self.expired_from_chat()
        now = self.clock()
        for key in self.enabled_keys():
            if self.remaining(key, now) > 0:
                continue
            last_try = self._last_attempt.get(self._slot(key))
            if last_try is not None and now - last_try < REBUFF_FLOOR_SEC:
                continue
            self._try_cast(key)

    def on_stop(self):
        """Keep cast times: buffs keep running while the session is stopped."""
        pass
