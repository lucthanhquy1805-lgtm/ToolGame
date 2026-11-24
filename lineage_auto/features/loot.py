"""Drops after a kill (PLAN 1.5, A7; PLAN 0.27 / 7: two kinds of server).

* "auto": the server puts the drop straight into the bag; the chat shows "아데나 (n) 획득: <monster>" at the kill.
  Nothing to do (the game PC's orc server: 10 such lines in 20261124_183803_hunt with loot off and no walk).
* "walk_f4" / "walk_click": the drop lies at the corpse. Walk to where the monster died (combat.last_anchor), not
  farther than max_dist and not when the minimap says it is behind a wall, press the pick-up key / click the
  shining items there, then wait up to ``wait`` s for a new chat line. Each try is one "loot" event in the record.
``suggest_mode`` is the "auto-detect" button: after a few kills, kill lines at the kill = auto.
"""
import math
import time

import cv2
import numpy as np

from ..winapi.hotkeys import poll_escape
from .base import Feature
from .combat import KILL_OUTCOMES

WALK_PX_PER_SEC = 250.0  # rough run speed, only to size the wait after the walk click
WALK_WAIT_MAX = 1.5
FEET_DROP = 20  # the box centre is the body; the corpse lies at the feet
ITEM_WINDOW = 110  # px around the corpse searched for shining items
MAX_ITEM_CLICKS = 3
MIN_KILLS_TO_SUGGEST = 5
AUTO_SHARE = 0.5


def suggest_mode(kills, chat_kills, min_kills=MIN_KILLS_TO_SUGGEST):
    """"auto" when most kills came with a kill line, "walk_f4" when they did not, None = not enough kills yet."""
    if kills < min_kills:
        return None
    return "auto" if chat_kills >= AUTO_SHARE * kills else "walk_f4"


def shining_items(frame, center, window=ITEM_WINDOW):
    """Client points of small bright blobs (item sprites / their name labels) near ``center``, nearest first.

    shortcut: brightness only; a light spell or a white name nearby is clicked too (harmless: a walk click).
    Upgrade with a YOLOX "item" class when drops are labelled."""
    h, w = frame.shape[:2]
    x0, y0 = max(0, center[0] - window), max(0, center[1] - window)
    x1, y1 = min(w, center[0] + window), min(h, center[1] + window)
    roi = frame[y0:y1, x0:x1]
    if roi.size == 0:
        return []
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 2] > 200) & (hsv[..., 1] < 90)).astype(np.uint8)
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(mask)
    out = []
    for i in range(1, n):
        if 6 <= stats[i, cv2.CC_STAT_AREA] <= 400:
            out.append((int(x0 + cents[i][0]), int(y0 + cents[i][1])))
    out.sort(key=lambda p: math.hypot(p[0] - center[0], p[1] - center[1]))
    return out


class LootFeature(Feature):
    key = "loot"

    def __init__(self, ctx, targeting=None):
        super().__init__(ctx)
        self.targeting = targeting

    @property
    def settings(self):
        return self.account.loot

    def _event(self, **data):
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.event("loot", mode=self.settings.mode, **data)

    def after_fight(self, outcome, anchor=None):
        """Walk to the corpse and pick up (walk modes only). Returns True when it pressed / clicked."""
        s = self.settings
        if s.mode == "auto" or outcome not in KILL_OUTCOMES:
            return False
        rect = self.ctx.rect()
        t0 = time.time()
        if anchor is not None:
            char = self.ctx.char_pos(rect)
            spot = (int(anchor[0]), int(anchor[1]) + FEET_DROP)
            dist = math.hypot(spot[0] - char[0], spot[1] - char[1])
            if dist > s.max_dist:
                self.log(f"corpse {dist:.0f}px away > {s.max_dist}, not walking")
                self._event(skipped="far", dist=round(dist))
                return False
            kind, waypoint = self.targeting.route(spot) if self.targeting is not None else (None, None)
            if kind == "blocked":
                self.log("corpse behind a wall on the minimap, not walking")
                self._event(skipped="blocked", dist=round(dist))
                return False
            self.input.release_left()
            if kind == "detour":
                self.input.click_at(*rect.to_screen(*waypoint))
                self.ctx.sleep(min(WALK_WAIT_MAX, math.hypot(waypoint[0] - char[0], waypoint[1] - char[1])
                                   / WALK_PX_PER_SEC))
            self.input.click_at(*rect.to_screen(*spot))
            self.ctx.sleep(min(WALK_WAIT_MAX, dist / WALK_PX_PER_SEC))
        else:
            self.input.release_left()
            spot, dist = None, 0.0
        walk_s = time.time() - t0
        watch = getattr(self.targeting, "kill_watch", None)
        if watch is not None:
            watch.new_lines = 0
        acted = self._pick(rect, spot)
        got = self._wait_chat(rect, watch)
        self._event(walk_s=round(walk_s, 2), dist=round(dist), acted=acted, got=got)
        if acted:
            self.ctx.state["loot_presses"] = self.ctx.state.get("loot_presses", 0) + acted
            rec = getattr(self.ctx, "recorder", None)
            if rec:
                rec.count("loot")
        return acted > 0

    def _pick(self, rect, spot):
        s = self.settings
        done = 0
        if s.mode == "walk_click" and spot is not None:
            items = shining_items(self.ctx.grabber.grab_bgr(rect), spot)[:MAX_ITEM_CLICKS]
            for x, y in items:
                poll_escape(self.ctx)
                if not self.ctx.running:
                    break
                self.input.click_at(*rect.to_screen(x, y))
                time.sleep(s.gap)
                done += 1
            if done:
                return done
            # Nothing shining: fall back to the pick-up key.
        for _ in range(s.presses):
            time.sleep(s.gap)  # first gap lets the drop land
            poll_escape(self.ctx)
            if not self.ctx.running:
                break
            self.input.press(s.key)
            done += 1
        return done

    def _wait_chat(self, rect, watch):
        """Up to settings.wait s for a new chat line ("획득"). None when the chat cannot be read."""
        if watch is None:
            return None
        end = time.time() + self.settings.wait
        while time.time() < end and self.ctx.running:
            watch.update(self.ctx.grabber.grab_bgr(rect))
            if watch.new_lines:
                return True
            time.sleep(0.2)
        return False
