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
PLAN 1.10:
- class fight cap (elf 25 s, the rest 10 s), scan.melee_max_sec 0 = class, the legacy 10.0 / 25.0 read as 0
- characters.get on a display name ("Elf" / "Yêu Tinh" / "요정"), never a silent fall back to the knight
- combat._near_hold: the box gone but the monster next to us with the sword / HP falling keeps the fight
- ring_probe: a sword within NEAR_NOW_PX is attacked on the ring read, farther away still re-probed
- the walk offset: 10 wander clicks = 20 steps, and a hold+drag chase feeds it through ctx.note_arrival
PLAN 1.11 (20261128_142729_hunt, elf):
- the reach is a px CIRCLE, measured on that record (pairs melee_attack -> fight_end: killed standing still out
  to 367 px, "out of range" at 343, walked at 402-445): drift.reach_px = steps * 20 px, the elf class default 17
  steps = 340 px, and that px figure is what the UI shows next to the step count
- engage_ranged clicks the box once per HAND_CLICK_SEC instead of holding the button (a hold drags the character
  after a monster that walks off), and never clicks a box out of the hand reach
- range_walk only past NEAR_KEEP and only on RANGE_WALK_READS drift readings in a row; the walked steps go into
  the walk offset and the fight ends with go_home
- exploration.walk_home walks back even with a monster in reach, which wander refuses to do
- range_probe.measure also returns the measured px (scan.attack_range_px)
Run: python tests/test_attack_range.py
"""
import glob
import json
import math
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
from lineage_auto.features import ring_probe as rp  # noqa: E402
from lineage_auto.features import exploration as ex  # noqa: E402
from lineage_auto.config.models import AccountSettings, ScanSettings  # noqa: E402
from lineage_auto.features import combat as cb  # noqa: E402
from lineage_auto.features import range_probe  # noqa: E402
from lineage_auto.features.survival import HealthFeature  # noqa: E402
from lineage_auto.features.targeting import MELEE_DIST, TargetingFeature  # noqa: E402
from lineage_auto.runtime import detector as det  # noqa: E402
from lineage_auto.runtime.context import HotbarPages, WalkOffset  # noqa: E402
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


class Ctx(HotbarPages, WalkOffset):
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


class Tg:
    """Targeting double: one monster at ``point`` (or None = gone), real in_hand_reach / attack_steps."""

    def __init__(self, ctx, point, kill_after=None):
        self.ctx, self.point, self.kill_after, self.pops = ctx, point, kill_after, 0
        self.scan, self.character = ctx.account.scan, ctx.character
        self.char, self.blocked, self.kill_watch, self.last_monsters = CHAR, [], None, [point]
        self.leader = None  # 3.0-L v2: no crown on these doubles

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
    check([get_class(k).attack_range for k in ("wizard", "knight", "prince", "elf")] == [1, 1, 1, 17],
          "class defaults: wizard 1, knight 1, prince 1, elf 17 (PLAN 1.11: 340 px, measured)")
    acc = AccountSettings.from_dict(json.loads(json.dumps(AccountSettings().to_dict())))
    check(acc.scan.attack_range == 0 and acc.scan.spell_min_mp_pct == 70, "config round trip")


def test_in_hand_reach():
    ctx = Ctx("wizard")
    tg = Tg(ctx, (700, 400))
    check(tg.attack_steps() == 1 and tg.in_hand_reach((640 + MELEE_DIST - 1, 380))
          and not tg.in_hand_reach((640 + MELEE_DIST + 5, 380)), "wizard: hand reach = MELEE_DIST")
    elf = Tg(Ctx("elf"), (700, 400))
    # PLAN 1.11: measured on 20261128_142729 - a circle of steps * 20 px (elf 17 steps = 340 px): killed while
    # standing at 296 / 322 px sideways and 269-284 px down, "out of range" at 343-364, walked at 402-445.
    check(elf.attack_steps() == 17 and drift.reach_px(17) == 340 and drift.reach_px(25) == 500,
          "reach_px (what the UI shows): elf 17 steps = 340 px, the UI maximum 25 = 500 px")
    for dx, dy in ((330, 0), (-330, 0), (0, 330), (233, 233)):
        check(elf.in_hand_reach((640 + dx, 380 + dy)), f"elf: 340 px reaches ({dx}, {dy})")
    for dx, dy in ((350, 0), (0, -350), (260, 260)):
        check(not elf.in_hand_reach((640 + dx, 380 + dy)), f"elf: and not ({dx}, {dy}), past 340 px")
    ctx.account.scan.attack_range = 2  # a melee class that measured 2 steps still hits what stands next to it
    check(tg.in_hand_reach((640 + MELEE_DIST - 1, 380)) and not tg.in_hand_reach((640 + MELEE_DIST + 5, 380)),
          "the reach is never shorter than MELEE_DIST")
    ctx.account.scan.attack_range = 3
    check(tg.attack_steps() == 3 and tg.in_hand_reach((640, 380 + 55)), "scan.attack_range overrides the class")


def test_no_spell_reach():
    """A standing caster with no usable attack spell only takes what its hand reaches (no_spell every beat)."""
    class RealTg(Tg):
        out_of_range, has_spell, shot_reach = (TargetingFeature.out_of_range, TargetingFeature.has_spell,
                                               TargetingFeature.shot_reach)

    tg = RealTg(Ctx("wizard"), (700, 400))
    far, near = (CHAR[0] + 300, CHAR[1]), (CHAR[0] + 40, CHAR[1])
    check(not tg.has_spell() and tg.out_of_range(far) and not tg.out_of_range(near), "no spell: 300 px skipped")
    slot = tg.ctx.account.attack("F5")
    slot.enabled, slot.skill_id = True, "386"
    check(tg.has_spell() and not tg.out_of_range(far), "a spell: 300 px is shot")


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
    box = ctx.rect().to_screen(680, 400)
    # PLAN 1.11: a standing class CLICKS the box (a hold drags the character after a monster that walks off)
    check(cf.last_outcome == "chat_kill" and ctx.recorder.kinds("melee_attack") and not presses
          and ("hold",) not in ctx.input.log and ("click", box[0], box[1]) in ctx.input.log,
          "MP 50 %: monster next to the wizard killed by hand (clicks, never a hold), no spell")
    check(cf._skipped.get("hand_first", 0) >= 1, "the ready spell was held back (skipped hand_first)")
    ctx, cf, _tg = _wizard_fight(mp=80)
    casts = ctx.recorder.kinds("spell_cast")
    check(casts and casts[0]["why"] == "mp_high", "MP 80 %: the spell joins the hand attack (why mp_high)")


def _elf_fight(point, frames=None, kill_after=None, cap=5.0):
    ctx = Ctx("elf")
    ctx.account.scan.hunt_range, ctx.account.scan.melee_max_sec = 10, cap
    ctx.account.health.use_skill = False
    ctx.frames = frames or [texture()]
    tg = Tg(ctx, point, kill_after=kill_after)
    tg.ctx = ctx
    tg.steps_from_home = types.MethodType(TargetingFeature.steps_from_home, tg)
    tg.step_px = types.MethodType(TargetingFeature.step_px, tg)
    cf = cb.CombatFeature(ctx, targeting=tg)
    cb.CursorProbe.current_hash = staticmethod(lambda: "sword")
    cf.engage(types.SimpleNamespace(local=point, screen=ctx.rect().to_screen(*point)), ctx.rect(), CHAR)
    return ctx, cf, tg


def test_range_walk():
    """PLAN 1.11: only a monster past NEAR_KEEP. 3.0-L v2: ONE drift reading of >= 1 step ends it at once."""
    img = texture()
    walk = [img] + [shifted(img, 40 * n, -20 * n) for n in range(1, 8)]  # 2 steps per check, non stop
    far = (CHAR[0] + 200, CHAR[1])
    ctx, cf, tg = _elf_fight(far, frames=list(walk))
    rw = ctx.recorder.kinds("range_walk")
    check(cf.last_outcome == "range_walk" and rw and rw[0]["drift_steps"] >= 1.5 and rw[0]["reads"] == 1
          and tg.blocked == [far], "a hand attack that keeps walking ends as range_walk, spot blacklisted")
    check(ctx.state.get("go_home") and tg.steps_from_home() >= 1.5,
          f"the walked steps feed the offset ({tg.steps_from_home():.1f}) and go_home is set")
    near = (CHAR[0] + 60, CHAR[1])
    ctx, cf, _tg = _elf_fight(near, frames=list(walk))
    check(not ctx.recorder.kinds("range_walk") and cf.last_outcome == "cap",
          "the same drift with the monster 60 px away is not a range_walk")
    once = [img, img, shifted(img, 40, -20)] + [shifted(img, 40, -20)] * 6  # one check walks, then standing
    ctx, cf, _tg = _elf_fight(far, frames=once)
    check(ctx.recorder.kinds("range_walk"), "3.0-L v2: one drift reading of a step is a range_walk already")
    check(ctx.account.scan.attack_range_px_learned == 180 and ctx.recorder.kinds("reach_learned"),
          f"walked at 200 px -> reach learned {ctx.account.scan.attack_range_px_learned} px (0.9 x 200)")


def test_elf_far_boxes():
    """PLAN 1.9 (user 27/11): a bow reaches 10-25 steps. Real boxes 300-550 px from the character.

    PLAN 1.11: the reach is a px circle (17 steps = 340 px, measured), so 17 takes the near half of those boxes
    and 25 (500 px, the UI maximum) takes all but the farthest."""
    path = os.path.join(ROOT, "records_game", "20261127_191624_hunt", "frames.jsonl")
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    far = [tuple(h) for r in rows for h in r.get("hits", [])
           if 300 <= ((h[0] - CHAR[0]) ** 2 + (h[1] - CHAR[1]) ** 2) ** 0.5 <= 550]
    check(len(far) >= 40, f"{len(far)} real boxes 300-550 px from the character")
    for steps in (17, 25):
        ctx = Ctx("elf")
        ctx.account.scan.attack_range = steps
        tg = Tg(ctx, far[0])
        inside = [p for p in far if tg.in_hand_reach(p, CHAR, ctx.rect())]
        want = [p for p in far if math.hypot(p[0] - CHAR[0], p[1] - CHAR[1]) <= drift.reach_px(steps)]
        check(inside == want and inside, f"range {steps}: {len(inside)}/{len(far)} in reach (<= "
              f"{drift.reach_px(steps):.0f} px)")
        if steps == 25:
            out = [p for p in far if p not in inside]
            check(all(math.hypot(p[0] - 640, p[1] - 380) > 500 for p in out),
                  f"range 25 = 500 px: only the {len(out)} boxes past that are out")
        cases = inside[:1] + [p for p in far if p not in inside][:1]
        for point in cases:
            fctx = Ctx("elf")
            fctx.account.scan.attack_range, fctx.account.scan.hunt_range = steps, 10
            fctx.account.scan.melee_max_sec = 1.0
            fctx.frames = [texture()]
            ftg = Tg(fctx, point, kill_after=3)
            cf = cb.CombatFeature(fctx, targeting=ftg)  # no attack spell: the bow alone
            cb.CursorProbe.current_hash = staticmethod(lambda: "sword")
            cf.engage(types.SimpleNamespace(local=point, screen=fctx.rect().to_screen(*point)), fctx.rect(), CHAR)
            box = fctx.rect().to_screen(*point)
            clicks = [x for x in fctx.input.log if x[0] == "click" and x[1:] == box]
            held = ("hold",) in fctx.input.log
            if point in inside:
                check(clicks and not held and cf.last_outcome == "chat_kill"
                      and fctx.recorder.kinds("melee_attack"),
                      f"range {steps}: box {point} ({drift.screen_steps(point[0] - 640, point[1] - 380):.1f} steps) "
                      f"shot from where it stands with clicks, never a hold")
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
    boxes = [(640 + 20 * n, 380) for n in (1, 3, 6, 8)]  # 1, 3, 6, 8 steps to the right (PLAN 1.11: 20 px)

    def click(x, y, settle=0.0):
        ctx.clicked = (x, y)

    ctx.input.click_at = click

    def grab(rect):
        # standing for clicks up to 6 steps, walking for anything farther
        far = ctx.clicked is not None and ctx.clicked[0] - CHAR[0] > drift.reach_px(6.5)
        return shifted(img, 80, 0) if far else img  # 2 steps

    ctx.grabber = types.SimpleNamespace(grab_bgr=grab)
    range_probe.CursorProbe.current_hash = staticmethod(lambda: "sword")
    steps, px, why, rows = range_probe.measure(ctx, detect=lambda f, c: list(boxes), sleep=lambda t: None)
    check(steps == 6 and why == "ok" and rows[-1]["result"] == "walked",
          f"measure: hits at 1/3/6 steps, walks at 8 -> 6 ({rows})")
    # PLAN 1.11: the button keeps what it really measured, in px (scan.attack_range_px, shown next to the steps)
    check(px == round(math.hypot(*(boxes[2][i] - CHAR[i] for i in (0, 1)))) and all("px" in r for r in rows),
          f"measure: the farthest hit was {px} px away")
    steps, px, why, _ = range_probe.measure(ctx, detect=lambda f, c: [], sleep=lambda t: None)
    check(steps is None and px is None and why == "no_monster", "no monster: nothing measured")
    stop = threading.Event()
    stop.set()
    steps, px, why, _ = range_probe.measure(ctx, stop, detect=lambda f, c: list(boxes), sleep=lambda t: None)
    check(steps is None and why == "cancelled", "cancel")
    check(ScanSettings.from_dict({"attack_range_px": 412}).attack_range_px == 412
          and ScanSettings().attack_range_px == 0, "scan.attack_range_px: 0 = never measured")


def test_near_due():
    d = object.__new__(det.DetectorThread)
    d.near, d._near_t, d.ctx, d.gpu = True, float("-inf"), types.SimpleNamespace(state={}), False
    check(not d.near_due("search", 100.0), "searching: no near crop")
    check(d.near_due("fight", 100.0) and not d.near_due("fight", 101.0) and d.near_due("fight", 102.1),
          f"fight: at most once per {det.NEAR_EVERY_SEC:.0f} s")
    d.ctx.state["hp_falling"] = True
    check(d.near_due("search", 102.2) and d.near_due("search", 102.3), "HP falling: at once, searching too")
    d.ctx.state["hp_falling"], d.gpu = False, True
    check(d.near_due("fight", 103.0) and d.near_due("fight", 103.4) and not d.near_due("search", 103.5),
          "DirectML (PLAN 0.48): every fight detect, still not while searching")
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
    check('"danger"' not in src.split("def _run(self)")[1].split("acquire")[0],
          "session: danger no longer pauses the hunt (PLAN 0.50: heal and keep fighting)")


def _crowd(n, dx=50):
    return [(CHAR[0] + dx + 8 * i, CHAR[1] + (-1) ** i * 10 * i) for i in range(n)]


def test_crowd_r195240():
    """PLAN 0.50 (records_game/m6TSP63T/r195240, rc8, elf Lv27, fallen_blessed): `danger` at t=0.1 with hp 100,
    drop 0, mobs 3 -> 11 retreats in 17 s, 0 fights. A crowd is no danger any more and nobody steps back."""
    ctx = Ctx("elf")
    ctx.account.hunt_map, ctx.account.scan.hunt_range = "fallen_blessed", 10
    ctx.account.health.use_skill = False
    ctx.account.scan.melee_max_sec = 5.0
    ctx.frames = [texture()]
    hp = [100]
    ctx.read_hp = lambda rect: hp[0]
    mobs = _crowd(3)
    ctx.state["mobs_near"] = mobs
    hf = HealthFeature(ctx)
    for _ in range(5):
        hf.tick(ctx.rect())
    clicks = lambda: [x for x in ctx.input.log if x[0] == "click"]
    check(not hf.danger and not ctx.recorder.kinds("danger") and not clicks(),
          "HP 100, drop 0, 3 monsters next to the elf: no danger, no step, no move")
    tg = Tg(ctx, mobs[0], kill_after=3)
    cf = cb.CombatFeature(ctx, health=hf, targeting=tg)
    cb.CursorProbe.current_hash = staticmethod(lambda: "sword")
    cf.engage(types.SimpleNamespace(local=mobs[0], screen=ctx.rect().to_screen(*mobs[0])), ctx.rect(), CHAR)
    check(cf.last_outcome == "chat_kill" and ctx.recorder.kinds("melee_attack"),
          f"the elf shoots the crowd from where it stands ({cf.last_outcome})")
    check(cf._spell_why(50, True) == "crowd", "the crowd still unlocks the spells (_spell_why crowd)")
    ctx.input.log.clear()
    for v in (100, 74, 70):  # an HP burst: danger = heal / potion, never a step away
        hp[0] = v
        hf.tick(ctx.rect())
    check(hf.danger and not clicks(), "HP burst -26 %: danger, and still no step away (no _retreat any more)")
    check(not hasattr(hf, "_retreat"), "HealthFeature._retreat is gone for every class")
    tg2 = Tg(ctx, mobs[0], kill_after=3)
    cf2 = cb.CombatFeature(ctx, health=hf, targeting=tg2)
    cf2.engage(types.SimpleNamespace(local=mobs[0], screen=ctx.rect().to_screen(*mobs[0])), ctx.rect(), CHAR)
    check(cf2.last_outcome == "chat_kill", f"danger no longer ends / blocks the fight ({cf2.last_outcome})")


def _lure_ctx(cls="knight", following=(), offset=(0.0, 0.0), **scan):
    from lineage_auto.features.lure import LureFeature
    ctx = Ctx(cls)
    s = ctx.account.scan
    s.hunt_range, s.pull_mode = 10, True
    values = dict(lure_mobs=10, lure_steps=30, lure_max_sec=60.0, pull_abort_hp=50, lure_idle_sec=8.0,
                  guard_steps=4)
    values.update(scan)
    for k, v in values.items():
        setattr(s, k, v)
    ctx.state["offset"] = offset
    ctx.state["follow_counts"] = list(following)
    clock = [1000.0]
    lure = LureFeature(ctx, exploration=ex.ExplorationFeature(ctx), clock=lambda: clock[0])
    return ctx, lure, clock


def _start_trip(ctx, lure, clock):
    keep = ctx.state["follow_counts"]
    ctx.state["follow_counts"] = []
    lure.observe()
    clock[0] += 9  # quiet for more than lure_idle_sec
    check(lure.tick(ctx.rect(), CHAR, 100) and lure.active, "at the start, quiet 9 s -> a lure trip starts")
    check(ctx.recorder.kinds("lure_start"), "lure_start recorded")
    ctx.state["follow_counts"] = keep


def test_pull_crowd_r201820():
    """PLAN 0.50 (records_game/mG1RN30H/r201820, prince, pull_mode, hunt_range 10): danger mobs=3 at HP 50 % ->
    17 retreats in 27 s, never home. Now no retreat: it is gathering, 3 < lure_mobs 10, so it goes on."""
    ctx, lure, clock = _lure_ctx("prince")
    _start_trip(ctx, lure, clock)
    hp = [50]
    ctx.read_hp = lambda rect: hp[0]
    ctx.state["mobs_near"] = _crowd(3)
    ctx.state["follow_counts"] = [3, 3]
    ctx.input.log.clear()
    hf = HealthFeature(ctx)
    hf.tick(ctx.rect())
    check(not [x for x in ctx.input.log if x[0] == "click"], "HP 50 % + 3 monsters: no retreat click")
    check(not lure.after_hit(50) and lure.active and not ctx.state.get("go_home"),
          "3 following < 10, HP 50 % (not under pull_abort_hp 50): the trip goes on")
    check(lure.tick(ctx.rect(), CHAR, 50) and not [x for x in ctx.input.log if x[0] == "click"],
          "3.0-L v2: the last walk-out click was < 0.7 s ago: no stacked click")
    clock[0] += 1
    check(lure.tick(ctx.rect(), CHAR, 50) and [x for x in ctx.input.log if x[0] == "click"]
          and not ctx.recorder.kinds("lure_return"), "no target: one more walk click out, no lure_return")


def test_lure_count():
    """PLAN 0.50: the knight gathers 3 -> 6 -> 10 followers (two scans each) and walks home at lure_mobs."""
    ctx, lure, clock = _lure_ctx()
    _start_trip(ctx, lure, clock)
    for n in (3, 6):
        ctx.state["follow_counts"] = [n, n]
        check(not lure.after_hit(100), f"{n} following: hit it and go on")
    ctx.state["follow_counts"] = [6, 10]
    check(not lure.after_hit(100), "10 on one scan only (6 on the one before) is not 10 yet")
    ctx.state["follow_counts"] = [10, 10]
    check(lure.after_hit(100) and ctx.state.get("go_home") and not lure.active, "10 on two scans -> home")
    ret = ctx.recorder.kinds("lure_return")
    check(ret and ret[-1]["why"] == "count" and ret[-1]["mobs_following"] == 10, f"lure_return {ret[-1:]}")
    hits = ctx.recorder.kinds("lure_hit")
    check([h["mobs_following"] for h in hits] == [3, 6, 6, 10], f"lure_hit mobs_following {hits}")
    # the session's walk home (the real AccountSession._walk_home on doubles)
    from lineage_auto.runtime.session import AccountSession
    tg = Tg(ctx, (CHAR[0] + 60, CHAR[1]))
    tg.ctx = ctx
    tg.steps_from_home = types.MethodType(TargetingFeature.steps_from_home, tg)
    tg.step_px = types.MethodType(TargetingFeature.step_px, tg)
    tg.minimap = None
    ctx.state["offset"] = (12 * ctx.step_px(), 0.0)
    expl = ex.ExplorationFeature(ctx, targeting=tg)
    st = types.SimpleNamespace(ctx=ctx, account=ctx.account, targeting=tg, exploration=expl, lure=lure)
    ctx.input.log.clear()
    AccountSession._walk_home(st, ctx.rect())
    walks = [x for x in ctx.input.log if x[0] == "click"]
    check(len(walks) >= 5 and tg.steps_from_home() <= ex.GO_HOME_STOP and ctx.recorder.kinds("lure_home"),
          f"walk_home: {len(walks)} clicks back, lure_home recorded")
    src = open(os.path.join(ROOT, "lineage_auto", "runtime", "session.py"), encoding="utf-8").read()
    check("if self.lure.tick(rect, char, " in src,
          "the session asks the lure before it wanders")


def test_lure_other_endings():
    """PLAN 0.50: 9 followers at lure_steps -> steps; HP 45 % -> hp; lure_mobs 20 with 15 -> go on; time."""
    ctx, lure, clock = _lure_ctx(following=[9, 9])
    _start_trip(ctx, lure, clock)
    ctx.state["offset"] = (30 * ctx.step_px(), 0.0)
    check(lure.after_hit(100) and ctx.recorder.kinds("lure_return")[-1]["why"] == "steps", "9 at 30 steps: steps")
    ctx, lure, clock = _lure_ctx(following=[4, 4])
    _start_trip(ctx, lure, clock)
    check(lure.after_hit(45) and ctx.recorder.kinds("lure_return")[-1]["why"] == "hp", "HP 45 %: hp")
    ctx, lure, clock = _lure_ctx(following=[15, 15], lure_mobs=20)
    _start_trip(ctx, lure, clock)
    check(not lure.after_hit(100) and lure.active, "lure_mobs 20 with 15 following: keeps gathering")
    clock[0] += 61
    check(lure.tick(ctx.rect(), CHAR, 100) and ctx.recorder.kinds("lure_return")[-1]["why"] == "time",
          "past lure_max_sec: time")
    # at the start: a crowd there keeps the knight home (it guards), and the range is guard_steps
    ctx, lure, clock = _lure_ctx(following=[3, 3])
    lure.observe()
    clock[0] += 9
    lure.observe()
    check(not lure.tick(ctx.rect(), CHAR, 100) and not lure.active, "3 monsters around the start: no new trip")
    check(lure.range_steps() == 4, "at the start the melee range is guard_steps 4")
    _ctx2, lure2, _c = _lure_ctx("elf")
    check(not lure2.enabled() and lure2.range_steps() is None, "an elf never lures")
    tgf = TargetingFeature(ctx)
    tgf.lure, tgf.char = lure, CHAR
    lure.active = True
    check(tgf.out_of_range((CHAR[0] + 80, CHAR[1]), CHAR) and not tgf.out_of_range((CHAR[0] + 200, CHAR[1]), CHAR),
          "on a trip a box within FOLLOW_PX is a follower (skipped), a new one 200 px off is a target")


def test_lure_config():
    """PLAN 0.50: a config saved before 0.50 has no lure keys -> the defaults; typed values are clamped."""
    old = ScanSettings.from_dict({"hunt_range": 10, "pull_mode": True})
    check((old.lure_mobs, old.lure_steps, old.lure_max_sec, old.pull_abort_hp, old.lure_idle_sec, old.guard_steps)
          == (10, 10, 60.0, 50, 8.0, 4), "old config: lure_mobs 10, 10 steps (3.0-L v2), 60 s, HP 50 %, idle 8 s, guard 4")
    check(old.home_mode == "leader" and old.attack_range_px_learned == 0, "3.0-L v2: home_mode leader, nothing learned")
    big = ScanSettings.from_dict({"lure_mobs": 99, "pull_abort_hp": 0, "lure_steps": 30, "home_mode": "x"})
    check(big.lure_mobs == 30 and big.pull_abort_hp == 10 and big.lure_steps == 15 and big.home_mode == "leader",
          "lure_mobs 1-30, pull_abort_hp 10-90, lure_steps 5-15 (the rc9 default 30 reads as 15)")
    acc = AccountSettings()
    acc.scan.lure_mobs, acc.scan.home_mode, acc.scan.attack_range_px_learned = 15, "start", 126
    back = AccountSettings.from_dict(acc.to_dict()).scan
    check((back.lure_mobs, back.home_mode, back.attack_range_px_learned) == (15, "start", 126),
          "lure_mobs / home_mode / learned reach survive a save / load")
    from lineage_auto.ui import i18n
    for lang in ("ko", "en", "vi"):
        check(all(k in i18n.I18N[lang] for k in ("scan_lure_mobs", "scan_lure_steps", "scan_pull_abort_hp",
                                                  "scan_lure_max", "scan_lure_idle", "scan_guard_steps")),
              f"lure labels in {lang}")
    check(i18n.I18N["vi"]["scan_lure_mobs"] == "Số quái gom rồi kéo về", "VI label as asked")


def _lure_engage(following):
    ctx, lure, clock = _lure_ctx(following=following)
    _start_trip(ctx, lure, clock)
    ctx.account.scan.melee_max_sec = 5.0
    ctx.frames = [texture()]
    ctx.state["offset"] = (8 * ctx.step_px(), 0.0)
    p = (CHAR[0] + 40, CHAR[1])
    tg = Tg(ctx, p)
    tg.in_place = tg.ranged = lambda: False
    tg.from_home = types.MethodType(TargetingFeature.from_home, tg)
    tg.step_px = types.MethodType(TargetingFeature.step_px, tg)
    tg.closer_than = lambda *a, **k: None
    tg.track_current = lambda rect, a, char=None: types.SimpleNamespace(
        local=p, local_x=p[0], local_y=p[1], screen=ctx.rect().to_screen(*p))
    cf = cb.CombatFeature(ctx, targeting=tg)
    cf.lure = lure
    cb.CursorProbe.current_hash = staticmethod(lambda: "sword")
    cf.engage(types.SimpleNamespace(local=p, screen=ctx.rect().to_screen(*p)), ctx.rect(), CHAR)
    return ctx, cf, [e["kind"] for e in ctx.recorder.events if e["kind"].startswith(("pull", "lure"))]


def test_lure_engage():
    """PLAN 0.50: a real knight engage on a lure trip - PULL_HITS hits, never killed, then the lure decides."""
    ctx, cf, kinds = _lure_engage([2, 2])
    check(cf.last_outcome == "pulled" and kinds.count("pull_hit") == cb.PULL_HITS and "lure_hit" in kinds
          and not ctx.state.get("go_home") and not ctx.state.get("pull"),
          f"2 following: {cb.PULL_HITS} hits, lure_hit, the trip goes on (no 1.7 follow watch) {kinds}")
    ctx, cf, kinds = _lure_engage([10, 10])
    check(cf.last_outcome == "pulled" and kinds[-1] == "lure_return" and ctx.state.get("go_home"),
          f"10 following: the same hits, then lure_return + go_home {kinds}")


def test_class_cap():
    """PLAN 1.10: the fight cap follows the class unless it was typed by hand."""
    check([get_class(k).melee_max_sec for k in ("wizard", "knight", "prince", "elf")] == [10.0, 20.0, 20.0, 25.0],
          "class caps: elf 25 s (bow 8-9.5 s a kill), melee 20 s, caster 10 s")
    check(ScanSettings.from_dict({}).melee_max_sec == 0.0, "scan.melee_max_sec default 0 = the class")
    check(ScanSettings.from_dict({"melee_max_sec": 10.0}).melee_max_sec == 0.0
          and ScanSettings.from_dict({"melee_max_sec": 25.0}).melee_max_sec == 0.0,
          "legacy 10.0 / 25.0 (never chosen) read as the class default")
    check(ScanSettings.from_dict({"melee_max_sec": 40.0}).melee_max_sec == 40.0, "a typed 40 s is kept")
    acc = AccountSettings()
    acc.character_class = "elf"
    check(acc.melee_cap() == 25.0 and acc.attack_steps() == 17, "elf: 25 s cap, 17 steps (340 px)")
    acc.scan.melee_max_sec = 8.0
    check(acc.melee_cap() == 8.0, "the Advanced tab still wins")
    acc.character_class = "knight"
    acc.scan.melee_max_sec = 0.0
    check(acc.melee_cap() == 20.0 and acc.attack_steps() == 1, "knight: 20 s cap, 1 step")
    # 20261128_001015 had "class": the display name is what the recording and the config carry.
    for name in ("elf", "Elf", "ELF", "Yêu Tinh", "요정"):
        got = get_class(name)
        check(got.key == "elf", f"characters.get(name {len(name)} chars) = elf, not the knight fall back")
    check(get_class("nope").key == "knight" and get_class(None).key == "knight", "unknown still = the default")


def test_near_hold():
    """PLAN 1.10: 21 of 59 fights of 001015 ended "gone" at 45-80 px after 1.2 s while HP fell."""
    ctx = Ctx("elf")
    cf = cb.CombatFeature(ctx)
    cf.targeting = Tg(ctx, (CHAR[0] + 45, CHAR[1]))
    near, far = (CHAR[0] + 45, CHAR[1]), (CHAR[0] + 400, CHAR[1])
    rect = ctx.rect()
    check(cf._near_hold(rect, near, CHAR, 1.2, sword=True), "sword + 45 px + 1.2 s = keep the fight")
    check(not cf._near_hold(rect, near, CHAR, 1.2, sword=False), "no sword, no damage = let it go")
    check(not cf._near_hold(rect, near, CHAR, cb.NEAR_HOLD_SEC, sword=True),
          f"never longer than {cb.NEAR_HOLD_SEC:.0f}s on the cursor alone")
    check(not cf._near_hold(rect, far, CHAR, 1.2, sword=True), "400 px away is not next to us")
    cf.health = types.SimpleNamespace(hp_falling=lambda: True)
    check(cf._near_hold(rect, near, CHAR, 1.2, sword=False), "HP falling keeps it without the cursor")
    # giving up on a near monster while hurt asks for a ring sweep before the next target
    cf._dist, cf._fight_start, cf._box_gone, cf._spells, cf._skipped = 45, time.time(), 1.4, 0, {}
    cf._finish(None, "gone", near, "box gone 1.4s")
    check(ctx.state.get("ring_first"), "gone at 45 px while hurt -> ring before the next acquire")
    src = open(os.path.join(ROOT, "lineage_auto", "runtime", "session.py"), encoding="utf-8").read()
    check('self.ctx.state.get("ring_first")' in src and 'self.ring.sweep(rect, char, "lost_near")' in src,
          "session: the ring sweep runs before acquire")


def test_ring_near_now():
    """PLAN 1.10: 26 ring sightings, 5 hits - the second read (probe) threw 21 swords away."""
    ctx = Ctx("elf")
    ring = rp.RingProbeFeature(ctx, clock=lambda: 1000.0)
    probed = []

    class P:
        def probe(self, points, rect):
            probed.append(list(points))
            return None  # exactly what 001015 did 21 times

    ring.targeting = P()
    ctx.cursors = types.SimpleNamespace(is_attack=lambda h: True, is_corpse=lambda h: False)
    target = ring.sweep(ctx.rect(), CHAR, "idle")
    first = rp.ring_points(CHAR[0], CHAR[1], 1280, 960)[0]
    check(target is not None and target.local == first, "a sword at 45 px is attacked on the ring read")
    check(not probed, "no second read within NEAR_NOW_PX (it also blacklisted the spot)")
    check(rp.NEAR_NOW_PX == 100, "NEAR_NOW_PX = NEAR_KEEP (100 px)")
    # RADII is (45, 90), so only a wider ring reaches past NEAR_NOW_PX: that branch still re-probes.
    ring._last, rings = 0.0, rp.ring_points
    rp.ring_points = lambda cx, cy, gw, gh: [(cx + 300, cy)]
    try:
        check(ring.sweep(ctx.rect(), CHAR, "idle") is None, "farther out: still confirmed by probe")
    finally:
        rp.ring_points = rings
    check(probed == [[(CHAR[0] + 300, CHAR[1])]], "and the probe got that point")


def test_walk_offset():
    """PLAN 1.10 B8: ctx.note_walk saw only the wander clicks and ctx.note_arrival had NO caller, so a melee
    class never accumulated an offset (steps_from_home 0) and never walked home."""
    ctx = Ctx("knight")
    tg = Tg(ctx, (CHAR[0] + 300, CHAR[1]))
    tg.ctx = ctx
    tg.steps_from_home = types.MethodType(TargetingFeature.steps_from_home, tg)
    tg.step_px = types.MethodType(TargetingFeature.step_px, tg)
    check(tg.steps_from_home() == 0.0, "the hunt starts at 0 steps")
    for _ in range(10):  # 192615: 10 walk clicks = 20 steps
        ctx.note_walk(CHAR, (CHAR[0] + ex.WALK_PX, CHAR[1]), ctx.rect())
    check(abs(tg.steps_from_home() - 20) <= 1, f"10 wander clicks = {tg.steps_from_home():.1f} steps (20)")
    ctx.state["offset"] = (0.0, 0.0)
    ctx.note_arrival(CHAR, (CHAR[0] + 300, CHAR[1]))  # one hold+drag chase of 300 px
    step = tg.step_px()
    check(abs(tg.steps_from_home() - 300 / step) < 0.1,
          f"a 300 px chase = {tg.steps_from_home():.1f} steps ({300 / step:.1f})")
    src = open(os.path.join(ROOT, "lineage_auto", "features", "combat.py"), encoding="utf-8").read()
    check("self.ctx.note_arrival(entry_char, entry_anchor)" in src, "combat: the chase feeds the offset")
    check(src.count("self.ctx.note_walk(") == 3,
          "combat: the sidestep / detour clicks and the measured range_walk drift feed it too")
    # the go_home dead zone, and the rule that must not hold a melee class in the field
    check(ex.GO_HOME_START == 4 and ex.GO_HOME_STOP == 1, "go_home: 4 steps out, back to 1 step")
    esrc = open(os.path.join(ROOT, "lineage_auto", "features", "exploration.py"), encoding="utf-8").read()
    check("self.targeting.ranged()" in esrc and "and self._monster_in_reach()" in esrc,
          'the "no walk home while a monster is in reach" rule is for a ranged class only')


def test_pull_melee_classes():
    """PLAN 1.10 (G1RN30H, prince): pulling is for every melee class, not only the knight."""
    from lineage_auto.characters.base import CombatStyle

    for key in ("prince", "knight"):
        cls = get_class(key)
        check(cls.style == CombatStyle.MELEE and cls.attack_range == 1,
              f"{key}: melee style, 1 step by hand")
        ctx = Ctx(key)
        tg = Tg(ctx, (CHAR[0] + 300, CHAR[1]))
        tg.ranged = lambda: ctx.character.style != CombatStyle.MELEE
        tg.from_home = lambda local, char=None: 300.0
        cf = cb.CombatFeature(ctx, targeting=tg)
        ctx.account.scan.hunt_range, ctx.account.scan.pull_mode = 10, True
        check(cf.pulling((CHAR[0] + 300, CHAR[1]), CHAR), f"{key}: a monster 300 px out is a pull trip")
        ctx.account.scan.hunt_range = 0
        check(not cf.pulling((CHAR[0] + 300, CHAR[1]), CHAR), f"{key}: no hunt range = no pull")
    elf_ctx = Ctx("elf")
    elf_tg = Tg(elf_ctx, (CHAR[0] + 300, CHAR[1]))
    elf_tg.from_home = lambda local, char=None: 300.0
    elf_cf = cb.CombatFeature(elf_ctx, targeting=elf_tg)
    elf_ctx.account.scan.hunt_range, elf_ctx.account.scan.pull_mode = 10, True
    check(not elf_cf.pulling((CHAR[0] + 300, CHAR[1]), CHAR), "elf (ranged): shoots, never pulls")


def test_hover_cost_warning():
    """PLAN 1.10: the G1RN30H config had hover_reads 6 / hover_settle 50 ms = 250 ms a hover, worst case,
    against the shipped 160 ms (4 reads / 40 ms) - 1.6x, not the "many times" the report guessed."""
    from lineage_auto.ui.panels.status_panel import HOVER_SLOW_MS

    s = ScanSettings.from_dict({})
    cheap = 1000 * (s.hover_settle + max(0, s.hover_reads - 1) * s.hover_retry)
    bad = ScanSettings.from_dict({"hover_reads": 6, "hover_settle": 0.05, "hover_retry": 0.04})
    costly = 1000 * (bad.hover_settle + max(0, bad.hover_reads - 1) * bad.hover_retry)
    check(cheap <= HOVER_SLOW_MS < costly, f"default {cheap:.0f} ms, G1RN30H {costly:.0f} ms, warn over {HOVER_SLOW_MS}")
    # "Restore defaults" puts every scan field back
    from lineage_auto.ui.panels.scan_panel import FIELDS
    fresh = ScanSettings()
    for name, *_ in FIELDS:
        setattr(bad, name, getattr(fresh, name))
    check(bad.hover_reads == fresh.hover_reads and bad.hover_settle == fresh.hover_settle,
          "every FIELDS entry has a shipped default to restore")


def test_cast_stuck():
    """PLAN 1.10 (20261128_121828, prince): 1916 hovers in a row read the aiming ellipse (fc92..., empty ground
    included), hover_confirm_rate 0, 0 fights with 118 boxes within 230 px - a targeted spell stayed armed."""
    from lineage_auto.features.targeting import CAST_STUCK_READS, TargetingFeature

    class CastTg(Tg):
        _note_cast_stuck = TargetingFeature._note_cast_stuck
        _record_hover = TargetingFeature._record_hover

        def __init__(self, ctx):
            super().__init__(ctx, (CHAR[0] + 45, CHAR[1]))
            self._cast_reads, self.input, self.log = 0, ctx.input, lambda m: None
            self.clock = time.monotonic

    ctx = Ctx("prince")
    ctx.cursors = Cursors()
    ctx.recorder.hover = lambda *a, **k: None
    tg = CastTg(ctx)
    for i in range(CAST_STUCK_READS - 1):
        tg._record_hover((100 + i, 200), "ell")
    check(not ctx.recorder.kinds("cast_stuck"), f"{CAST_STUCK_READS - 1} ellipse reads: still patient")
    tg._record_hover((200, 200), "ell")
    check(len(ctx.recorder.kinds("cast_stuck")) == 1, f"{CAST_STUCK_READS} in a row: one cast_stuck event")
    tg._record_hover((201, 200), "sword")
    check(tg._cast_reads == 0, "a sword read resets the counter")
    # our own cast must never be cancelled
    ctx.state["casting_until"] = time.monotonic() + 5
    for i in range(CAST_STUCK_READS + 3):
        tg._record_hover((300 + i, 200), "ell")
    check(len(ctx.recorder.kinds("cast_stuck")) == 1, "while we are casting, the ellipse is ours")


def test_grid_safe_only():
    """PLAN 1.10: "Grid cursor scan (safe spot only)" was only a label - 20261128_121828 swept 18 times
    (80 points, ~0.93 s) out in the field."""
    from lineage_auto.features import grid_scan as gs

    ctx = Ctx("prince")
    g = gs.GridScanFeature(ctx)
    check(g.safe(), "nothing around: one sweep is allowed")
    check(not g.safe(), f"and not again for {gs.COOLDOWN:.0f}s")
    g._last = -gs.COOLDOWN
    ctx.state["mobs_seen"] = [(700, 400)]
    check(not g.safe(), "a monster in the last detection: no sweep")
    ctx.state["mobs_seen"] = []
    ctx.state["hp_falling"] = True
    check(not g.safe(), "HP falling: no sweep")
    ctx.state["hp_falling"] = False
    check(g.safe(), "quiet again: allowed")
    ctx.account.record.grid_scan = False
    ctx.recorder.hover = lambda *a, **k: None
    ctx.recorder.begin_scan = lambda: None
    g._last = -gs.COOLDOWN
    check(g.sweep(ctx.rect(), CHAR) == 0, "and the checkbox still switches it off entirely")


def test_cancel_aim():
    """PLAN 1.10 (G1RN30H, 20261128_121828 + 123218): the ONLY enabled skill was buff 385 "Shield", page F1
    key F10, self_cast unset - a TARGETED spell pressed twice, so the client stayed in aiming mode."""
    from lineage_auto.features.base import Feature
    from lineage_auto.features import base as fb

    ctx = Ctx("prince")
    ctx.cursors = Cursors()
    ctx.recorder.hover = lambda *a, **k: None
    f = Feature(ctx)
    hashes = ["ground"]
    fb.CursorProbe.current_hash = staticmethod(lambda: hashes[0])
    check(not f.cancel_aim("buff 385"), "no ellipse after the press: nothing to cancel")
    check(not ctx.input.log, "and no right click")
    hashes[0] = "ell"
    check(f.cancel_aim("buff 385"), "ellipse after a self-cast press: cancelled")
    check(any(a[0] == "right" for a in ctx.input.log) or not ctx.input.log,
          "a right click, never a left one (a left click walks the character)")
    check(len(ctx.recorder.kinds("aim_cancel")) == 1, "one aim_cancel event")
    src = open(os.path.join(ROOT, "lineage_auto", "features", "buff.py"), encoding="utf-8").read()
    check("self.cancel_aim(" in src, "buff.tick cancels a stuck aim")
    for name in ("cure_poison", "survival"):
        got = open(os.path.join(ROOT, "lineage_auto", "features", f"{name}.py"), encoding="utf-8").read()
        check("self.cancel_aim(" in got, f"{name} cancels a stuck aim")


def test_pull_interrupt():
    """PLAN 1.10 [a] (20261128_123218, prince, 4 pull_start): only 1 trip finished; 3 were cut by a nearer
    monster at 13.2 / 18.7 / 38.1 s. A nearer monster now gets ONE hit and the trip carries on home; only HP
    falling fights on the spot."""
    src = open(os.path.join(ROOT, "lineage_auto", "features", "combat.py"), encoding="utf-8").read()
    body = src.split("def engage(self")[1]
    check("if closer is not None and pull and not hurt and self._confirm_switch(rect, closer):" in body,
          "pulling + a nearer monster + HP steady = one hit, then home")
    first = body.index("pull and not hurt and self._confirm_switch")
    plain = body.index("if closer is not None and self._confirm_switch(rect, closer):", first)
    check(first < plain, "the pull branch is tested before the plain switch")
    check('self._event("pull_interrupt", why="closer"' in body, "and it records pull_interrupt with the reason")
    check('return self._finish(target, "pulled", closer' in body, "it ends as a pull (walk home + follow watch)")
    from lineage_auto.runtime.stats import KEYS
    check("aim_cancel" in KEYS and "cast_stuck" in KEYS, "both new counters are on the Statistics tab")


def test_reach_142729():
    """PLAN 1.11: how far the elf bow really reaches, measured on 20261128_142729_hunt.

    Each hand attack paired with the fight_end that followed it: killed while standing still out to 367 px (the
    next ones 307 / 296 / 284 / 281), "out of range" at 343 px, and the character walked (range_walk) at 402 /
    428 / 445 px. 17 steps = 340 px (drift.reach_px, the elf class default) sits between those.
    """
    path = os.path.join(ROOT, "records_game", "20261128_142729_hunt", "events.jsonl")
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    pairs = []
    for i, e in enumerate(rows):
        if e["kind"] != "melee_attack":
            continue
        end = next((f for f in rows[i + 1:] if f["kind"] == "fight_end"), None)
        if end is not None:
            pairs.append((e["dist"], tuple(e["target"]), end["outcome"]))
    kills = sorted(d for d, _p, o in pairs if o in ("chat_kill", "corpse_cursor"))
    walked = sorted(d for d, _p, o in pairs if o == "range_walk")
    check(len(pairs) == 118 and kills[-5:] == [281, 284, 296, 307, 367],
          f"{len(pairs)} hand attacks; killed while standing at {kills[-5:]} px")
    near = [e for e in rows if e["kind"] == "range_walk" and e["dist"] <= 100]
    check(walked[-3:] == [402, 428, 445] and len(near) == 22,
          f"the character walked at {walked[-3:]} px; {len(near)} of the {len(walked)} range_walks ended on a "
          f"monster within 100 px (now never one)")
    tg = Tg(Ctx("elf"), pairs[0][1])
    reach = drift.reach_px(17)
    check(tg.attack_steps() == 17 and reach == 340, "the elf class default: 17 steps = 340 px")
    out = [(d, p) for d, p, _o in pairs if not tg.in_hand_reach(p, CHAR, tg.ctx.rect())]
    check(len(out) == 13 and all(d > 340 for d, _p in out),
          f"{len(out)} of the 118 are out of the 340 px reach")
    kept = sorted(d for d, p, o in pairs if tg.in_hand_reach(p, CHAR, tg.ctx.rect())
                  and o in ("chat_kill", "corpse_cursor"))
    check(kept == kills[:-1], f"every kill but the 367 px one is still in reach ({len(kept)} of {len(kills)})")
    check(not any(tg.in_hand_reach(p, CHAR, tg.ctx.rect()) for d, p, o in pairs
                  if o == "range_walk" and d >= 402), "the three real walks (402-445 px) are out of reach")


def test_walk_home_after_fight():
    """PLAN 1.11: 0 go_home in 905 s - wander refuses to walk home while a monster is in reach, and a fight
    ended right next to a monster every time."""
    ctx = Ctx("elf")
    ctx.account.scan.hunt_range = 10
    tg = Tg(ctx, (CHAR[0] + 60, CHAR[1]))
    tg.ctx = ctx
    tg.steps_from_home = types.MethodType(TargetingFeature.steps_from_home, tg)
    tg.step_px = types.MethodType(TargetingFeature.step_px, tg)
    tg.minimap = None
    ctx.state["offset"] = (300.0, 0.0)
    expl = ex.ExplorationFeature(ctx, targeting=tg)
    expl.wander(ctx.rect(), CHAR)
    check(not [x for x in ctx.input.log if x[0] == "click"], "wander: a monster in reach comes before the walk home")
    before = tg.steps_from_home()
    check(expl.walk_home(ctx.rect(), CHAR), "walk_home clicks anyway")
    clicks = [x for x in ctx.input.log if x[0] == "click"]
    check(len(clicks) == 1 and clicks[0][1] < CHAR[0] and tg.steps_from_home() < before,
          f"one click back toward the start: {before:.1f} -> {tg.steps_from_home():.1f} steps")
    src = open(os.path.join(ROOT, "lineage_auto", "runtime", "session.py"), encoding="utf-8").read()
    check("self.exploration.walk_home(" in src and "HOME_AFTER_FIGHT" in src,
          "session._walk_home uses it, and a fight that ends > 2 steps out triggers it")


def main():
    tempfile.tempdir = tempfile.mkdtemp()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"== {name}")
            fn()
    print("attack range tests OK")


if __name__ == "__main__":
    main()
