"""Everything one account's features need, in one object.

Features receive a context instead of reaching for globals, which is what makes
running several accounts at once possible.
"""

import os
import threading
import time

from .. import app_paths
from ..control.controller import InputController
from ..vision.geometry import char_anchor
from ..vision.hud_numbers import HudNumberReader, percent
from ..vision.nameplate import NameplateScanner
from ..vision.stat_bar import BarColor, StatBarReader
from ..winapi.window import GameWindow
from .cursor_collection import CursorCollection
from .cursor_profile import CursorProfile


class BotContext:
    def __init__(self, account, backend, grabber, arbiter, window=None):
        self.account = account
        self.window = window or GameWindow()
        self.input = InputController(backend)
        self.grabber = grabber
        self.arbiter = arbiter
        self.cursors = CursorProfile(account.cursor_hashes)
        # Every cursor shape seen inside the game window while recording / collecting (PLAN 0.11 v5).
        self.seen = CursorCollection(app_paths.data_path(os.path.join("cursors", f"seen_{account.id}")))
        clash = self.cursors.duplicate_kinds()
        if clash:
            # PLAN 0.11: the game PC config had attack/corpse/ground on one hash.
            self.log(f"WARNING: cursors {'/'.join(sorted(clash))} share the same hash -> re-register them")
        self.nameplates = NameplateScanner()
        self.hp_reader = StatBarReader(app_paths.asset_path(app_paths.HP_TEMPLATE), BarColor.RED, "HP")
        # MP drains right-to-left on this HUD.
        self.mp_reader = StatBarReader(
            app_paths.asset_path(app_paths.MP_TEMPLATE), BarColor.BLUE, "MP", from_right=True
        )
        self.hud = HudNumberReader()
        self._hud_cache = (0.0, None)
        self.stop_event = threading.Event()
        # Scratch values shared between features (e.g. last MP reading).
        self.state = {}
        # runtime.recorder.Recorder while recording field data, else None.
        self.recorder = None

    @property
    def character(self):
        return self.account.character

    @property
    def running(self):
        return not self.stop_event.is_set()

    def request_stop(self):
        self.stop_event.set()

    def reset_stop(self):
        self.stop_event.clear()

    def sleep(self, seconds):
        """Interruptible wait. False means a stop was requested."""
        return not self.stop_event.wait(seconds)

    def rect(self):
        return self.window.client_rect()

    def char_pos(self, rect):
        return char_anchor(rect.w, rect.h)

    def log(self, message):
        print(f"[{self.account.name}] {message}")

    def read_hud(self, rect, max_age=0.05):
        """{"hp": (cur, max)|None, "mp": ...} from the HUD text; one grab serves HP and MP."""
        if not self.account.health.read_hud_numbers or not self.hud.available:
            return {"hp": None, "mp": None}
        stamp, values = self._hud_cache
        now = time.monotonic()
        if values is None or now - stamp > max_age:
            values = self.hud.read(self.grabber.grab_bgr(rect))
            self._hud_cache = (now, values)
            self.state["hp_abs"], self.state["mp_abs"] = values["hp"], values["mp"]
        return values

    def read_hp(self, rect):
        """HP 0-100: HUD text first, bar fill as fallback. Sets state["hp_source"]."""
        value = percent(self.read_hud(rect)["hp"])
        self.state["hp_source"] = "hud" if value is not None else "bar"
        if value is None:
            value = self.hp_reader.read_percent(self.grabber, rect)
        return value

    def read_mp(self, rect):
        """MP 0-100 from the HUD text, else the bar (None without ``mp_template.png``)."""
        value = percent(self.read_hud(rect)["mp"])
        if value is not None:
            self.state["mp"] = value
            return value
        if not self.mp_reader.available:
            self.state["mp"] = None
            return None
        value = self.mp_reader.read_percent(self.grabber, rect)
        self.state["mp"] = value
        return value

    def can_cast(self, skill_id, rect=None):
        """False when the skill costs MP and the MP bar is empty."""
        from ..skills.catalog import can_afford_mp, get_catalog

        cost = get_catalog().mp_cost(skill_id)
        if rect is not None and self.mp_reader.available:
            self.read_mp(rect)
        return can_afford_mp(self.state.get("mp"), cost)
