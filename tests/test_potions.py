"""Extra potions (PLAN 1.4b): long waits, and a slot that ran out is not pressed again.

records_game/20261127_003555_hunt (1280x960, wizard, F1+F6 = 2 mana potions, wait 1.5 s): both potions were gone at
137 s (MP under 50 %), then F6 was pressed every 1.5 s for 12 minutes. f_00001 shows F6 with the potion, f_00111
the empty slot, f_00013 page F2 (F6 there is another slot, so nothing can be said about the potion).
Run: python tests/test_potions.py   (the picture checks are skipped when the frames are not on this machine)
"""
import json
import os
import sys
import types

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lineage_auto.config.models import AccountSettings, PotionSetting  # noqa: E402
from lineage_auto.features import survival  # noqa: E402
from lineage_auto.runtime.context import HotbarPages  # noqa: E402
from lineage_auto.vision import hotbar  # noqa: E402

REC = os.path.join(ROOT, "records_game", "20261127_003555_hunt")
FULL, EMPTY, PAGE_F2 = "f_00001.jpg", "f_00111.jpg", "f_00013.jpg"


def test_settings():
    assert PotionSetting.from_dict({"cooldown": 600}).cooldown == 600
    assert PotionSetting.from_dict({"cooldown": 3600}).cooldown == 3600
    assert PotionSetting.from_dict({"cooldown": 99999}).cooldown == PotionSetting.COOLDOWN_MAX
    assert PotionSetting.from_dict({"cooldown": 0}).cooldown == 0.2


def test_hotbar():
    """Every frame of 003555: page F1 + F6 empty exactly after 137 s."""
    wrong = []
    for line in open(os.path.join(REC, "frames.jsonl"), encoding="utf-8"):
        f = json.loads(line)
        img = cv2.imread(os.path.join(REC, f["file"]))
        if hotbar.open_page(img) == "F1" and hotbar.slot_empty(img, "F6") != (f["t"] > 137):
            wrong.append(f["file"])
    print(f"   hotbar: F6 read right on every page-F1 frame, wrong {wrong[:5]}")
    assert not wrong


class Clock:
    now = 1000.0

    def time(self):
        return self.now


class In:
    def __init__(self):
        self.log = []

    def press(self, key):
        self.log.append(key)

    double_press = press


class Rec:
    def __init__(self):
        self.events = []

    def event(self, kind, **data):
        self.events.append((kind, data))

    def count(self, *a, **k):
        pass


class Ctx(HotbarPages):
    def __init__(self, account, frame):
        self.account, self.input, self.state, self.running = account, In(), {"hotbar_page": "F1"}, True
        self.frame, self.recorder, self.mp = frame, Rec(), 40
        self.grabber = types.SimpleNamespace(grab_bgr=lambda rect: self.frame)

    def read_hp(self, rect):
        self.state["hp_source"] = "hud"
        return 100

    def read_mp(self, rect):
        return self.mp

    def can_cast(self, *a):
        return True

    def log(self, message):
        print("   log:", message)


def test_empty_slot():
    full, empty, page2 = (cv2.imread(os.path.join(REC, n)) for n in (FULL, EMPTY, PAGE_F2))
    acc = AccountSettings()
    acc.health.use_skill = acc.health.use_potion = False
    p = acc.health.potions[0]
    p.enabled, p.stat, p.page, p.key, p.pct, p.cooldown = True, "mp", "F1", "F6", 50, 1.5
    clock, old = Clock(), survival.time
    survival.time = clock
    try:
        ctx = Ctx(acc, full)
        h = survival.HealthFeature(ctx)
        h.on_start()
        rect = object()

        def presses():
            return ctx.input.log.count("F6")

        h.tick(rect)
        assert presses() == 1, ctx.input.log  # potion there: drunk
        ctx.frame = page2
        clock.now += 2
        h.tick(rect)
        assert presses() == 2  # page F2 open: the slot cannot be read, pressed as before
        ctx.frame = empty
        clock.now += 2
        h.tick(rect)
        assert presses() == 3  # one empty picture is not enough (a redraw, a dialog)
        for _ in range(20):  # the 003555 run: a press every 1.5 s on the empty slot
            clock.now += 1.6
            h.tick(rect)
        assert presses() == 3, ctx.input.log
        assert ctx.state["potion_empty"] == ["F1+F6"]
        assert [e for e in ctx.recorder.events if e[0] == "potion_empty"] == [
            ("potion_empty", {"slot": "F1+F6", "stat": "mp"})]
        clock.now += survival.RECHECK_SEC + 1  # still empty after a few minutes: still not pressed
        h.tick(rect)
        assert presses() == 3 and ctx.state["potion_empty"] == ["F1+F6"]
        ctx.frame = full  # restocked
        clock.now += survival.RECHECK_SEC + 1
        h.tick(rect)
        assert presses() == 4 and ctx.state["potion_empty"] == []
        ctx.frame = empty
        for _ in range(3):
            clock.now += 1.6
            h.tick(rect)
        assert ctx.state["potion_empty"] == ["F1+F6"]
        h.on_start()  # Start again: tried at once
        assert ctx.state["potion_empty"] == [] and not h._empty
        # A 10-minute mana potion: one press, then nothing for 600 s.
        p.cooldown = 600
        h = survival.HealthFeature(ctx)  # a fresh run, nothing drunk yet
        ctx.frame, n = full, presses()
        for _ in range(100):
            clock.now += 1.5
            h.tick(rect)
        assert presses() == n + 1, presses() - n
        clock.now += 600
        h.tick(rect)
        assert presses() == n + 2
        print(f"   empty slot: 3 presses then none (20 more due), event + warning; back after a restock; "
              f"600 s wait = 1 press in 150 s")
    finally:
        survival.time = old


if __name__ == "__main__":
    test_settings()
    if not os.path.isfile(os.path.join(REC, EMPTY)):  # frames are not in git (.gitignore)
        print(f"SKIP: the frames of {REC} are not on this machine")
    else:
        test_hotbar()
        test_empty_slot()
    print("potion tests OK")
