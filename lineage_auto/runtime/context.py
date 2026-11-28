"""Everything one account's features need, in one object.

Features receive a context instead of reaching for globals, which is what makes
running several accounts at once possible.
"""

import math
import os
import threading
import time

from .. import app_paths
from ..config.models import HOTBAR_PAGES, hotbar_page
from ..control.controller import InputController
from ..vision import minimap
from ..vision.geometry import char_anchor
from ..vision.hud_numbers import HudNumberReader, percent
from ..vision.nameplate import NameplateScanner
from ..vision.stat_bar import BarColor, StatBarReader
from ..winapi.window import GameWindow
from .cursor_collection import CursorCollection
from .cursor_profile import CursorProfile
from .hard_cases import DEDUPE_PX, HardCases
from .stats import Stats, bump


# PLAN 0.34: the client needs a moment to redraw the hotbar after a page key (F1/F2/F3).
PAGE_SETTLE = 0.1
# PLAN 1.7: one walk click moves two game cells (measured on the game PC).
CLICK_STEPS = 2


class HotbarPages:
    """Which hotbar page the game is showing, and how to press a slot on another one.

    PLAN 0.34: page F1 is full (heal, potions, return scroll, buffs), so attack spells sit on F2. A slot is
    (page, key): the bot presses the page key, waits for the client to redraw, then the slot key. Kept as a
    mixin so the offline tests drive the real page logic instead of a copy of it.
    """

    def goto_page(self, page):
        """Make ``page`` the open hotbar page. True when a page key was actually pressed."""
        page = hotbar_page(page, "")
        # No key at all = the game is on the home page (nothing has switched it yet). An explicit None means
        # "unknown", which the session sets at start so the first press really happens.
        was = self.state.get("hotbar_page", HOTBAR_PAGES[0])
        if not page or page == was:
            return False
        self.input.press(page)
        time.sleep(PAGE_SETTLE)
        self.state["hotbar_page"] = page
        self.log(f"hotbar page {was or '?'} -> {page}")
        rec = getattr(self, "recorder", None)
        if rec is not None:
            rec.count("page_switch")
            rec.event("page_switch", from_page=was or "?", to_page=page)
        return True

    def press_slot(self, page, key, double=False):
        """Press hotbar slot (page, key), switching page first when the game shows another one."""
        self.goto_page(page)
        (self.input.double_press if double else self.input.press)(key)


class WalkOffset:
    """PLAN 1.7: where the hunt start is, in client pixels, without needing the minimap.

    The camera keeps the character in the middle of the screen, so the only thing that moves is the world: a
    walk click shifts it by up to CLICK_STEPS steps, and walking all the way to a monster shifts it by exactly
    the monster's screen offset. Kept as a mixin so the offline tests drive the real arithmetic.
    """

    def step_px(self, rect=None):
        """PLAN 1.7: client px of one character step, measured value (scan.step_mm) or the default."""
        rect = rect or self.rect()
        return minimap.step_px(rect.w, self.account.scan.step_mm)

    def offset(self):
        """Client px from the hunt start to the character (the camera centres the character, so the start
        itself is at char - offset on screen). (0, 0) before the hunt begins."""
        return self.state.get("offset") or (0.0, 0.0)

    def note_walk(self, char, point, rect=None, steps=CLICK_STEPS):
        """PLAN 1.7: a walk click moves the character up to CLICK_STEPS steps toward ``point``; add that to
        the offset so the way back to the hunt start is known without the minimap.

        PLAN 1.11: ``steps`` is how far it really went when that is known - the drift the picture shows while a
        hand attack walks us to the monster (20261128_142729: ~69 such steps, none of them counted, so the elf
        read 0 steps from home and never walked back)."""
        dx, dy = point[0] - char[0], point[1] - char[1]
        dist = math.hypot(dx, dy)
        if dist < 1 or steps <= 0:
            return
        moved = min(steps * self.step_px(rect), dist)
        ox, oy = self.offset()
        self.state["offset"] = (ox + moved * dx / dist, oy + moved * dy / dist)

    def note_arrival(self, char, point):
        """PLAN 1.7: the character walked all the way to ``point`` (a fight reached melee), so the world
        moved by exactly that much - no guessing per beat."""
        ox, oy = self.offset()
        self.state["offset"] = (ox + point[0] - char[0], oy + point[1] - char[1])


class BotContext(HotbarPages, WalkOffset):
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
        # PLAN 4.1: hunt statistics (Statistics tab + records/stats_<date>.json).
        self.stats = Stats()
        # PLAN 0.46 / 5: frames where a monster was proven without a box. Independent of the recording
        # setting - this is the training set for the next model.
        self.hard_cases = HardCases()

    def hard_case(self, rect, point, kind="cursor", src=""):
        """PLAN 0.46 / 5: save this frame if the detector really has no box at ``point``. Never raises."""
        point = (int(point[0]), int(point[1]))
        boxes = self.state.get("mobs_seen") or ()
        if any(math.hypot(b[0] - point[0], b[1] - point[1]) <= DEDUPE_PX for b in boxes):
            return None  # the model did see it: not a hard case
        try:
            path = self.hard_cases.save(self.grabber.grab_bgr(rect), point, kind=kind, src=src,
                                        map_key=self.account.hunt_map)
        except Exception as exc:  # a full disk must never stop a hunt
            self.log(f"hard case not saved: {exc}")
            return None
        if path:
            bump(self, "hard_case")
            rec = self.recorder
            if rec:
                rec.count("hard_case")
                rec.event("hard_case", point=list(point), hc_kind=kind, src=src)  # "kind" is the event's own name
        return path

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
        if rect is not None:
            # PLAN 1.6: the HUD numbers are the MP source; mp_template (the bar fallback) was never shipped, so
            # gating on mp_reader.available meant MP was never read during a fight.
            self.read_mp(rect)
        return can_afford_mp(self.state.get("mp"), cost)
