"""PLAN 0.47 + 1.9, offline: near crop schedule, danger once per burst, max_probe_points, hand attack first.

- screen drift / steps on records_game/20261126_192615_observe (10 walk clicks = 20 steps; skipped without frames)
- config: attack_range / spell_min_mp_pct defaults, class defaults (wizard 1, knight 1, elf 15), max_probe_points 5
- elf (bow) range 15 / 25 on the real 300-550 px boxes of 20261127_191624_hunt: in reach = held from where it
  stands, out of reach = no click at all; 25 steps cover the play area
- targeting.in_hand_reach (melee rule at 1 step, isometric steps for a bow)
- combat._spell_why: MP >= spell_min_mp_pct / danger / crowd / out of the hand reach, else the hand attack only
- engage_ranged (wizard standing at the start): a monster next to it is hit by hand, no spell under 70 % MP, a spell
  at 80 %; a hand attack that walks (the picture moves 2 steps) ends as range_walk and blacklists the spot
- range_probe.measure: farthest monster hit without walking
- detector.near_due: fight every NEAR_EVERY_SEC, searching only while HP falls
- survival: one "danger" event per burst, state["hp_falling"]
Run: python tests/test_attack_range.py
"""
import glob
import json
import os
import sys
import tempfile
import threading
import time
import types

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lineage_auto.characters import get as get_class  # noqa: E402
from lineage_auto.config.models import AccountSettings, ScanSettings  # noqa: E402
from lineage_auto.features import combat as cb  # noqa: E402
from lineage_auto.features import range_probe  # noqa: E402
from lineage_auto.features.survival import HealthFeature  # noqa: E402
from lineage_auto.features.targeting import MELEE_DIST, TargetingFeature  # noqa: E402
from lineage_auto.runtime import detector as det  # noqa: E402
from lineage_auto.runtime.context import HotbarPages  # noqa: E402
from lineage_auto.vision import drift  # noqa: E402
from lineage_auto.winapi.window import ClientRect  # noqa: E402

CHAR = (640, 380)
REC_WALK = os.path.join(ROOT, "records_game", "20261126_192615_observe")


def texture(seed=1):
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (960, 1280, 3), dtype=np.uint8)
    return cv2.GaussianBlur(img, (9, 9), 3)


def shifted(img, dx, dy):
    return np.roll(np.roll(img, dy, axis=0), dx, axis=1)


class Rec:
    def __init__(self):
        self.events = []

    def event(self, kind, **data):
        self.events.append(dict(data, kind=kind))

    def count(self, *a, **k):
        pass

    def timing(self, *a, **k):
        pass

    def fight(self, *a, **k):
        pass

    def kinds(self, kind):
        return [e for e in self.events if e["kind"] == kind]


class In:
    def __init__(self):
        self.log = []

    def move(self, x, y):
        self.log.append(("move", x, y))

    def click_at(self, x, y, settle=0.0):
        self.log.append(("click", x, y))

    def press(self, k):
        self.log.append(("press", k))

    def hold_left(self):
        self.log.append(("hold",))

    def __getattr__(self, name):
        return lambda *a, **k: None


class Cursors:
    def is_attack(self, h):
        return h == "sword"

    def is_corpse(self, h):
        return h == "corpse"

    def classify(self, h):
        return {"sword": "attack", "ell": "cast"}.get(h, "ground")


class Ctx(HotbarPages):
    def __init__(self, cls="wizard"):
        self.account = AccountSettings()
        self.account.character_class = cls
        self.character = get_class(cls)
        self.running = True
        self.state = {"hotbar_page": "F1"}
        self.input = In()
        self.cursors = Cursors()
        self.recorder = Rec()
        self.frames = []  # grab_bgr pops these (the last one repeats)
        self.grabber = types.SimpleNamespace(grab_bgr=self._grab, close_thread=lambda: None)
        self.mp = 50

    def _grab(self, rect):
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]

    def rect(self):
        return ClientRect(0, 0, 1280, 960)

    def char_pos(self, rect):
        return CHAR

    def log(self, m):
        pass

    def sleep(self, t):
        return self.running

    def read_mp(self, rect):
        return self.mp

    def can_cast(self, *a, **k):
        return True

    def offset(self):
        return (0.0, 0.0)


class Tg:
    """Targeting double: one monster at ``point`` (or None = gone), real in_hand_reach / attack_steps."""

    def __init__(self, ctx, point, kill_after=None):
        self.ctx, self.point, self.kill_after, self.pops = ctx, point, kill_after, 0
        self.scan, self.character = ctx.account.scan, ctx.character
        self.char, self.blocked, self.kill_watch, self.last_monsters = CHAR, [], None, [point]

    attack_steps = TargetingFeature.attack_steps
    in_hand_reach = TargetingFeature.in_hand_reach

    def in_place(self):
        return True

    def ranged(self):
        return True

    def out_of_range(self, local, char=None):
        return False

    def track_current(self, rect, anchor, char=None):
        return types.SimpleNamespace(local=self.point, local_x=self.point[0], local_y=self.point[1])

    def reacquire_near(self, rect, char, anchor):
        x, y = rect.to_screen(*self.point)
        return types.SimpleNamespace(screen_x=x, screen_y=y, local=self.point,
                                     local_x=self.point[0], local_y=self.point[1])

    def pop_kills(self):
        self.pops += 1
        return [(time.time(), "orc")] if self.kill_after and self.pops > self.kill_after else []

    def block(self, xy):
        self.blocked.append(xy)

    def __getattr__(self, name):
        return lambda *a, **k: None


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok", msg)


def test_drift_192615():
    files = sorted(glob.glob(os.path.join(REC_WALK, "f_*.jpg")))
    if not files:
        print("skipped: 192615 frames not on this machine")
        return
    frames = [cv2.imread(f) for f in files]
    steps = [drift.drift_steps(a, b) for a, b in zip(frames, frames[1:])]
    check(abs(sum(steps) - 20) <= 1, f"192615: 10 walk clicks = {sum(steps):.1f} steps (20)")
    standing = [s for s in steps if s < 0.5]
    check(len(standing) >= 8 and max(standing) < 0.1, "standing frames drift < 0.1 step")


def test_steps_and_config():
    check(abs(drift.screen_steps(20, 10) - 1) < 1e-9 and drift.screen_steps(40, 0) == 1
          and drift.screen_steps(0, 20) == 1, "one step = (20,10) / (40,0) / (0,20) px at 1280")
    img = texture()
    check(abs(drift.drift_steps(img, shifted(img, 40, -20)) - 2) < 0.1, "a 2-step shift reads 2 steps")
    s = ScanSettings.from_dict({})
    check(s.attack_range == 0 and s.spell_min_mp_pct == 70, "defaults: attack_range 0 (class), spell MP 70 %")
    check(ScanSettings.from_dict({"max_probe_points": 5}).max_probe_points == 5, "max_probe_points 5 is kept")
    check([get_class(k).attack_range for k in ("wizard", "knight", "prince", "elf")] == [1, 1, 1, 15],
          "class defaults: wizard 1, knight 1, prince 1, elf 15")
    acc = AccountSettings.from_dict(json.loads(json.dumps(AccountSettings().to_dict())))
    check(acc.scan.attack_range == 0 and acc.scan.spell_min_mp_pct == 70, "config round trip")


def test_in_hand_reach():
    ctx = Ctx("wizard")
    tg = Tg(ctx, (700, 400))
    check(tg.attack_steps() == 1 and tg.in_hand_reach((640 + MELEE_DIST - 1, 380))
          and not tg.in_hand_reach((640 + MELEE_DIST + 5, 380)), "wizard: hand reach = MELEE_DIST")
    elf = Tg(Ctx("elf"), (700, 400))
    check(elf.attack_steps() == 15 and elf.in_hand_reach((640 + 15 * 40, 380))
          and not elf.in_hand_reach((640 + 15 * 40 + 30, 380)) and elf.in_hand_reach((640, 380 - 15 * 20))
          and not elf.in_hand_reach((640, 380 - 16 * 20 - 15)), "elf: 15 steps, isometric (40 px across, 20 down)")
    ctx.account.scan.attack_range = 3
    check(tg.attack_steps() == 3, "scan.attack_range overrides the class")


def test_spell_why():
    ctx = Ctx("wizard")
    cf = cb.CombatFeature(ctx, targeting=Tg(ctx, (700, 400)))
    check(cf._spell_why(50, True) is None, "MP 50 %, monster in reach: hand only")
    check(cf._spell_why(70, True) == "mp_high", "MP 70 %: spells allowed")
    check(cf._spell_why(20, False) == "out_of_reach", "out of the hand reach: spell")
    ctx.state["mobs_near"] = [(1, 1)] * 3
    check(cf._spell_why(20, True) == "crowd", "3 monsters next to us: spell")
    ctx.state["mobs_near"] = []
    cf.health = types.SimpleNamespace(danger=True)
    check(cf._spell_why(20, True) == "danger", "danger: spell")
    cf.health = None
    check(cf._spell_why(None, True) == "mp_unread", "MP unreadable does not block")


def _wizard_fight(mp, frames=None, kill_after=8):
    ctx = Ctx("wizard")
    ctx.account.scan.hunt_range = 10
    ctx.account.aim_wait_sec = 0
    ctx.account.health.use_skill = False
    f5 = ctx.account.attack("F5")
    f5.enabled, f5.skill_id, f5.page = True, "386", "F2"
    ctx.account.scan.melee_max_sec = 5.0
    ctx.mp = mp
    ctx.frames = frames or [texture()]
    tg = Tg(ctx, (680, 400), kill_after=kill_after)
    cf = cb.CombatFeature(ctx, targeting=tg)
    target = types.SimpleNamespace(local=(680, 400), screen=ctx.rect().to_screen(680, 400))
    cb.CursorProbe.current_hash = staticmethod(lambda: "sword")
    cf.engage(target, ctx.rect(), CHAR)
    return ctx, cf, tg


def test_engage_hand_first():
    ctx, cf, _tg = _wizard_fight(mp=50)
    presses = [x for x in ctx.input.log if x[0] == "press" and x[1] == "F5"]
    check(cf.last_outcome == "chat_kill" and ctx.recorder.kinds("melee_attack") and not presses
          and ("hold",) in ctx.input.log, "MP 50 %: monster next to the wizard killed by hand, no spell")
    check(cf._skipped.get("hand_first", 0) >= 1, "the ready spell was held back (skipped hand_first)")
    ctx, cf, _tg = _wizard_fight(mp=80)
    casts = ctx.recorder.kinds("spell_cast")
    check(casts and casts[0]["why"] == "mp_high", "MP 80 %: the spell joins the hand attack (why mp_high)")


def test_range_walk():
    img = texture()
    frames = [img, img, shifted(img, 40, -20)]  # the hand attack moved the picture 2 steps
    ctx, cf, tg = _wizard_fight(mp=50, frames=frames, kill_after=None)
    rw = ctx.recorder.kinds("range_walk")
    check(cf.last_outcome == "range_walk" and rw and rw[0]["drift_steps"] >= 1.5 and tg.blocked == [(680, 400)],
          "a hand attack that walks ends as range_walk, spot blacklisted")


def test_elf_far_boxes():
    """PLAN 1.9 (user 27/11): a bow reaches 10-25 steps. Real boxes 300-550 px from the character."""
    path = os.path.join(ROOT, "records_game", "20261127_191624_hunt", "frames.jsonl")
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    far = [tuple(h) for r in rows for h in r.get("hits", [])
           if 300 <= ((h[0] - CHAR[0]) ** 2 + (h[1] - CHAR[1]) ** 2) ** 0.5 <= 550]
    check(len(far) >= 40, f"{len(far)} real boxes 300-550 px from the character")
    for steps in (15, 25):
        ctx = Ctx("elf")
        ctx.account.scan.attack_range = steps
        tg = Tg(ctx, far[0])
        inside = [p for p in far if tg.in_hand_reach(p, CHAR, ctx.rect())]
        want = [p for p in far if drift.screen_steps(p[0] - CHAR[0], p[1] - CHAR[1]) <= steps + 0.5]
        check(inside == want, f"range {steps}: {len(inside)}/{len(far)} in reach")
        if steps == 25:
            corner = [p for p in far if p not in inside]  # (1083, 691) / (225, 62): 26.6 / 26.3 steps
            check(len(corner) <= 2 and all(drift.screen_steps(p[0] - 640, p[1] - 380) > 26 for p in corner),
                  f"range 25: all but the screen-corner boxes {corner} (> 26 steps)")
        cases = [inside[0]] + [p for p in far if p not in inside][:1]
        for point in cases:
            fctx = Ctx("elf")
            fctx.account.scan.attack_range, fctx.account.scan.hunt_range = steps, 10
            fctx.account.scan.melee_max_sec = 1.0
            fctx.frames = [texture()]
            ftg = Tg(fctx, point, kill_after=3)
            cf = cb.CombatFeature(fctx, targeting=ftg)  # no attack spell: the bow alone
            cb.CursorProbe.current_hash = staticmethod(lambda: "sword")
            cf.engage(types.SimpleNamespace(local=point, screen=fctx.rect().to_screen(*point)), fctx.rect(), CHAR)
            clicks = [x for x in fctx.input.log if x[0] == "click"]
            held = ("hold",) in fctx.input.log
            if point in inside:
                check(held and not clicks and cf.last_outcome == "chat_kill"
                      and fctx.recorder.kinds("melee_attack"),
                      f"range {steps}: box {point} ({drift.screen_steps(point[0] - 640, point[1] - 380):.1f} steps) "
                      f"shot from where it stands, no walk click")
            else:
                check(not held and not clicks and cf.last_outcome == "no_spell",
                      f"range {steps}: box {point} ({drift.screen_steps(point[0] - 640, point[1] - 380):.1f} steps) "
                      f"out of reach: no click at all")


def test_range_probe():
    img = texture()

    class PCtx(Ctx):
        def __init__(self):
            super().__init__("elf")
            self.clicked = None

    ctx = PCtx()
    boxes = [(640 + 40 * n, 380) for n in (1, 3, 6, 8)]  # 1, 3, 6, 8 steps to the right

    def click(x, y, settle=0.0):
        ctx.clicked = (x, y)

    ctx.input.click_at = click

    def grab(rect):
        # standing for clicks up to 6 steps, walking for anything farther
        far = ctx.clicked is not None and drift.screen_steps(ctx.clicked[0] - CHAR[0], 0) > 6.5
        return shifted(img, 80, 0) if far else img  # 2 steps

    ctx.grabber = types.SimpleNamespace(grab_bgr=grab)
    range_probe.CursorProbe.current_hash = staticmethod(lambda: "sword")
    steps, why, rows = range_probe.measure(ctx, detect=lambda f, c: list(boxes), sleep=lambda t: None)
    check(steps == 6 and why == "ok" and rows[-1]["result"] == "walked",
          f"measure: hits at 1/3/6 steps, walks at 8 -> 6 ({rows})")
    steps, why, _ = range_probe.measure(ctx, detect=lambda f, c: [], sleep=lambda t: None)
    check(steps is None and why == "no_monster", "no monster: nothing measured")
    stop = threading.Event()
    stop.set()
    steps, why, _ = range_probe.measure(ctx, stop, detect=lambda f, c: list(boxes), sleep=lambda t: None)
    check(steps is None and why == "cancelled", "cancel")


def test_near_due():
    d = object.__new__(det.DetectorThread)
    d.near, d._near_t, d.ctx = True, float("-inf"), types.SimpleNamespace(state={})
    check(not d.near_due("search", 100.0), "searching: no near crop")
    check(d.near_due("fight", 100.0) and not d.near_due("fight", 101.0) and d.near_due("fight", 102.1),
          f"fight: at most once per {det.NEAR_EVERY_SEC:.0f} s")
    d.ctx.state["hp_falling"] = True
    check(d.near_due("search", 102.2) and d.near_due("search", 102.3), "HP falling: at once, searching too")
    d.near = False
    check(not d.near_due("fight", 200.0), "near_conf 0: never")


def test_danger_once():
    ctx = Ctx("wizard")
    hf = HealthFeature(ctx)
    for hp in (100, 95, 75, 70, 65, 60):  # -40 % within the window: one burst
        hf._danger_now(hp)
    check(len(ctx.recorder.kinds("danger")) == 1 and hf.danger and ctx.state["hp_falling"],
          "one danger event per burst, hp_falling set")
    src = open(os.path.join(ROOT, "lineage_auto", "runtime", "session.py"), encoding="utf-8").read()
    check('if getattr(self.health, "danger", False):' in src.split("def _run(self)")[1].split("acquire")[0],
          "session: no target taken while the danger flag holds")


def main():
    tempfile.tempdir = tempfile.mkdtemp()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"== {name}")
            fn()
    print("attack range tests OK")


if __name__ == "__main__":
    main()
