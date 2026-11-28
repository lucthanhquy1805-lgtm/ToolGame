"""PLAN 0.46: the near crop, the cursor ring and the hard cases, offline.

python tests/test_near_blind.py   (no game, no model needed for most checks)
"""
import json
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np  # noqa: E402

from lineage_auto.features import combat as combat_mod  # noqa: E402
from lineage_auto.features.ring_probe import RingProbeFeature, ring_points, COOLDOWN  # noqa: E402
from lineage_auto.runtime import hard_cases as hc  # noqa: E402
from lineage_auto.vision import yolox_mobs  # noqa: E402

PASS = []


def ok(name):
    PASS.append(name)
    print(f"OK  {name}")


def check(cond, name, detail=""):
    if not cond:
        raise AssertionError(f"FAIL {name}: {detail}")
    ok(name)


class FakeRect:
    w, h = 1280, 960

    def to_screen(self, x, y):
        return x + 10, y + 20


class FakeInput:
    def __init__(self):
        self.moves = []
        self.released = 0

    def move(self, x, y):
        self.moves.append((x, y))

    def release_left(self):
        self.released += 1


class FakeCursors:
    """Sword at one spot only."""

    def __init__(self, sword_at=None, radius=20):
        self.sword_at, self.radius = sword_at, radius
        self.reads = 0

    def _sword(self, point):
        return self.sword_at is not None and abs(point[0] - self.sword_at[0]) <= self.radius \
            and abs(point[1] - self.sword_at[1]) <= self.radius

    def is_attack(self, cursor):
        return bool(cursor)

    def is_corpse(self, _cursor):
        return False

    def classify(self, cursor):
        return "attack" if cursor else "ground"


class FakeTargeting:
    def __init__(self, hits=()):
        self.hits = list(hits)
        self.probed = []

    def probe(self, points, _rect):
        self.probed += list(points)
        x, y = points[0]
        return types.SimpleNamespace(local=(x, y), local_x=x, local_y=y, screen=(x, y))


class FakeCtx:
    def __init__(self, cursors, account):
        self.cursors = cursors
        self.account = account
        self.input = FakeInput()
        self.running = True
        self.state = {}
        self.recorder = None
        self.logs = []
        self.hard = []

    def log(self, msg):
        self.logs.append(msg)

    def hard_case(self, _rect, point, kind="", src=""):
        self.hard.append((tuple(point), kind, src))
        return "fake.jpg"


def account():
    from lineage_auto.config.models import AccountSettings
    return AccountSettings()


def fake_probe_hash(point, sword_at, radius=20):
    return b"sword" if (abs(point[0] - sword_at[0]) <= radius and abs(point[1] - sword_at[1]) <= radius) else b""


# ---------------------------------------------------------------- ring geometry
def test_ring_points():
    pts = ring_points(640, 380, 1280, 960)
    check(len(pts) == 16, "ring has 8 directions x 2 radii", f"{len(pts)} points")
    import math
    radii = [math.hypot(x - 640, y - 380) for x, y in pts]
    check(all(min(abs(r - 45), abs(r - 90)) <= 2 for r in radii),  # integer pixels: +-2 px
          "ring radii are 45 and 90 px", str(sorted(round(r) for r in radii)))
    edge = ring_points(20, 20, 1280, 960)
    check(all(x > 0 and y > 0 for x, y in edge), "ring points stay inside the play area", str(edge[:3]))


def test_ring_sweep_and_cooldown():
    from lineage_auto.winapi.cursor import CursorProbe
    acc = account()
    acc.scan.hover_settle = 0.0
    sword_at = (640 + 90, 380)
    cursors = FakeCursors(sword_at)
    ctx = FakeCtx(cursors, acc)
    clock = [100.0]
    ring = RingProbeFeature(ctx, clock=lambda: clock[0])
    ring.targeting = FakeTargeting()
    original = CursorProbe.current_hash
    CursorProbe.current_hash = staticmethod(
        lambda: fake_probe_hash((ctx.input.moves[-1][0] - 10, ctx.input.moves[-1][1] - 20), sword_at))
    try:
        target = ring.sweep(FakeRect(), (640, 380), "idle")
        check(target is not None, "ring finds the monster the model has no box for")
        # PLAN 1.10 #5: a sword within NEAR_NOW_PX (every ring point is 45 / 90 px) is attacked on the ring read
        check(not ring.targeting.probed and target.local == sword_at,
              "a ring hit within NEAR_NOW_PX is taken without a second probe", str(ring.targeting.probed))
        check(ctx.input.released == 1, "the ring releases the mouse first")
        check(ctx.hard and ctx.hard[0][1] == "ring", "a ring hit saves a hard case", str(ctx.hard))
        check(ring.sweep(FakeRect(), (640, 380), "idle") is None, "a second ring inside the cooldown is blocked")
        clock[0] += COOLDOWN
        check(ring.sweep(FakeRect(), (640, 380), "idle") is not None, "after the cooldown the ring runs again")
        # nothing there: no target, no hard case
        ctx.hard.clear()
        clock[0] += COOLDOWN
        CursorProbe.current_hash = staticmethod(lambda: b"")
        check(ring.sweep(FakeRect(), (640, 380), "idle") is None, "no sword anywhere = no target")
        check(not ctx.hard, "no sword = no hard case")
    finally:
        CursorProbe.current_hash = original


# ---------------------------------------------------------------- the ring fight lives on the cursor
def test_ring_fight_rules():
    check(combat_mod.RING_CHECK_SEC == 0.5, "the cursor is re-read every 0.5 s")
    check(combat_mod.RING_CHECK_STRIKES == 2, "two reads without a sword end a ring fight")
    src = open(os.path.join(ROOT, "lineage_auto", "features", "combat.py"), encoding="utf-8").read()
    check("now - box_t >= BOX_GONE_SEC and not ring" in src,
          "a ring fight is NOT ended by BOX_GONE_SEC (it never had a box)")
    check("now - sword_t >= NO_SWORD_SEC and not ring" in src,
          "a ring fight is NOT ended by NO_SWORD_SEC")
    check('"ring_gone"' in src, "a ring fight has its own outcome")


# ---------------------------------------------------------------- hard cases
def test_hard_cases():
    frame = np.full((960, 1280, 3), 80, np.uint8)
    with tempfile.TemporaryDirectory() as root:
        store = hc.HardCases(root=root, clock=lambda: 1000.0)
        path = store.save(frame, (700, 400), kind="ring", src="idle", map_key="blessed_orc")
        check(path and os.path.isfile(path), "a hard case writes a picture", str(path))
        txt = path[:-4] + ".txt"
        cls, xc, yc, bw, bh = open(txt, encoding="utf-8").read().split()
        check(cls == "0" and abs(float(xc) - 700 / 1280) < 0.01 and abs(float(yc) - 400 / 960) < 0.01,
              "the YOLO label is centred on the cursor point", open(txt, encoding="utf-8").read())
        check(abs(float(bw) * 1280 - hc.HC_BOX_W) < 1 and abs(float(bh) * 960 - hc.HC_BOX_H) < 1,
              "the YOLO box is the estimated monster size")
        images = json.load(open(os.path.join(store.dir, "labels.json"), encoding="utf-8"))["images"]
        entry = images[os.path.basename(path)]
        check(entry["todo"] and entry["monster"] == [[700, 400]] and len(entry["boxes"]) == 1,
              "label_tool sees the case with its estimated box, marked todo", str(entry))
        rows = [json.loads(l) for l in open(os.path.join(store.dir, "hard_cases.jsonl"), encoding="utf-8")]
        check(len(rows) == 1 and rows[0]["kind"] == "ring", "hard_cases.jsonl has one line per case")
        # dedupe: same spot right away
        check(store.save(frame, (710, 405), kind="ring", map_key="blessed_orc") is None,
              "the same spot within 2 s is not saved twice")

        # a clamped point still produces a valid label
        p2 = hc.HardCases(root=root, clock=lambda: 2000.0).save(frame, (5, 950), map_key="blessed_orc")
        line = open(p2[:-4] + ".txt", encoding="utf-8").read().split()
        check(all(0.0 <= float(v) <= 1.0 for v in line[1:]), "a point at the edge stays inside the picture", str(line))


def test_hard_case_cap():
    frame = np.full((120, 160, 3), 60, np.uint8)
    with tempfile.TemporaryDirectory() as root:
        store = hc.HardCases(root=root, clock=lambda: 0.0)
        hc_max, hc.MAX_N = hc.MAX_N, 3
        try:
            paths = []
            for i in range(6):
                store.clock = lambda i=i: 100.0 * i  # outside the dedupe window
                store._last = []
                paths.append(store.save(frame, (20 + i, 30), map_key="blessed_orc"))
            jpgs = sorted(f for f in os.listdir(store.dir) if f.endswith(".jpg"))
            check(len(jpgs) == 3, "the cap keeps at most MAX_N pictures", str(jpgs))
            check(all(os.path.basename(p) not in jpgs for p in paths[:3]),
                  "the oldest pictures are the ones deleted")
            images = json.load(open(os.path.join(store.dir, "labels.json"), encoding="utf-8"))["images"]
            check(sorted(images) == jpgs, "a deleted picture loses its label line too", str(sorted(images)))
            check(not [f for f in os.listdir(store.dir)
                       if f.endswith(".txt") and f[:-4] + ".jpg" not in jpgs],
                  "no orphan YOLO label is left behind")
        finally:
            hc.MAX_N = hc_max


def test_hard_case_stats_and_zip():
    frame = np.full((120, 160, 3), 60, np.uint8)
    with tempfile.TemporaryDirectory() as root:
        store = hc.HardCases(root=root, clock=lambda: 0.0)
        for i, map_key in enumerate(("blessed_orc", "blessed_orc", "fallen_blessed")):
            store.clock = lambda i=i: 100.0 * i
            store._last = []
            store.save(frame, (20 + i, 30), map_key=map_key)
        info = hc.stats(root)
        check(info["n"] == 3 and info["by_map"] == {"blessed_orc": 2, "fallen_blessed": 1},
              "the export stats count pictures per hunting ground", str(info))
        check(info["todo"] == 3 and info["reviewed"] == 0, "unreviewed cases are counted", str(info))
        check(info["day"] + info["night"] == 3, "every case is day or night", str(info))
        archive, info2 = hc.export_zip(root)
        import zipfile
        names = zipfile.ZipFile(archive).namelist()
        check("stats.json" in names and any(n.endswith(".jpg") for n in names),
              "the zip carries the pictures and stats.json", str(names[:5]))
        packed = json.loads(zipfile.ZipFile(archive).read("stats.json"))
        check(packed["n"] == 3, "stats.json in the zip matches", str(packed))
        empty, info3 = hc.export_zip(tempfile.mkdtemp())
        check(empty is None and info3["n"] == 0, "nothing to export = no zip")


def test_ctx_hard_case_needs_a_blind_model():
    """ctx.hard_case must drop a point the detector DID see (PLAN 0.46 / 5)."""
    from lineage_auto.runtime.context import BotContext
    frame = np.full((960, 1280, 3), 70, np.uint8)
    with tempfile.TemporaryDirectory() as root:
        ctx = BotContext.__new__(BotContext)  # no window, no input: only the hard-case path is exercised
        ctx.account = account()
        ctx.state = {"mobs_seen": [(700, 400)]}
        ctx.recorder = None
        ctx.stats = None
        ctx.hard_cases = hc.HardCases(root=root, clock=lambda: 0.0)
        ctx.grabber = types.SimpleNamespace(grab_bgr=lambda _rect: frame)
        ctx.log = lambda msg: None
        check(ctx.hard_case(FakeRect(), (705, 402)) is None, "a point the model has a box for is not a hard case")
        check(ctx.hard_case(FakeRect(), (300, 300)) is not None, "a point with no box nearby is a hard case")


# ---------------------------------------------------------------- the near crop
def test_near_crop_geometry():
    x0, y0, side = yolox_mobs.near_crop_box(1280, 960, 640, 380)
    check(side == yolox_mobs.NEAR_CROP and (x0, y0) == (440, 180), "the near crop is centred on the character",
          f"{x0},{y0},{side}")
    x0, y0, side = yolox_mobs.near_crop_box(1280, 960, 20, 940)
    check(x0 == 0 and y0 == 960 - side, "the crop is clamped into the frame", f"{x0},{y0},{side}")
    x0, y0, side = yolox_mobs.near_crop_box(300, 200, 150, 100)
    check(side == 200, "a small window shrinks the crop instead of failing", f"{side}")


def test_near_crop_blanks_before_cropping():
    """The bug this cost a measurement round: _blank_play_hud works in fractions of the image it gets."""
    src = open(os.path.join(ROOT, "lineage_auto", "vision", "yolox_mobs.py"), encoding="utf-8").read()
    body = src[src.index("def detect_near("):src.index("def detect_centers(")]
    check(body.index("_blank_play_hud(frame_bgr)") < body.index("img[y0:y0 + side"),
          "the HUD is blanked on the whole frame BEFORE the crop is taken")
    check("blank=False" in body, "the crop itself is not blanked again")


def test_near_boxes_are_candidates_only():
    """A low-confidence near box may be hovered, but must never feed the danger / wall rules (PLAN 0.43)."""
    src = open(os.path.join(ROOT, "lineage_auto", "features", "targeting.py"), encoding="utf-8").read()
    detect = src[src.index("def _detect("):src.index("def candidates(")]
    for field in ('self.ctx.state["mobs_near"]', 'self.ctx.state["mobs_seen"]'):
        after = detect[detect.index(field):]
        check("last_near" not in after.split("return")[0] or "hits" in after.split("=")[1],
              f"{field} is built from real boxes only")
    cand = src[src.index("def candidates("):src.index("def track_current(")]
    check(cand.index("self.last_monsters = list(unique)") < cand.index("extras = ["),
          "last_monsters (closer_than / crowd) is set before the near extras are appended")
    check("(unique + extras)[:self.scan.max_probe_points]" in cand,
          "normal boxes come first when the candidate list is cut")


def test_near_conf_setting():
    from lineage_auto.config.models import ScanSettings
    check(ScanSettings().near_conf == 0.1, "near_conf defaults to 0.1")
    check(ScanSettings.from_dict({}).near_conf == 0.1, "an old config reads near_conf 0.1")
    check(ScanSettings.from_dict({"near_conf": 0.0}).near_conf == 0.0, "near_conf 0 turns the pass off")
    check(ScanSettings.from_dict({"near_conf": 5}).near_conf == 1.0, "near_conf is clamped to 1.0")


def test_detect_stats_carries_crop_ms():
    src = open(os.path.join(ROOT, "lineage_auto", "runtime", "detector.py"), encoding="utf-8").read()
    check('"near_ms"' in src and "near_size=" in src,
          "detect_stats carries the near crop's real ms (measured on the game PC after the build)")
    # PLAN 0.47: "ms" is the full detect again, the near crop is counted apart and still fed to the guard
    check('self._slow_down(name, (b["ms"] + b["near_ms"]) / b["n"]' in src, "the CPU guard counts the near crop's ms")


# ---------------------------------------------------------------- compare_models verdict
def test_compare_verdict():
    sys.path.insert(0, os.path.join(ROOT, "train"))
    from compare_models import verdict
    old = {"near": 90.0, "fp": 0.20, "ms": 30.0}
    check(verdict(old, {"near": 94.0, "fp": 0.20, "ms": 31.0}).startswith("ĐỀ XUẤT THAY"),
          "better near recall at the same precision = swap")
    check(verdict(old, {"near": 94.0, "fp": 0.30, "ms": 30.0}).startswith("GIỮ"),
          "better near recall but worse precision = keep")
    check(verdict(old, {"near": 88.0, "fp": 0.10, "ms": 30.0}).startswith("GIỮ"),
          "worse near recall = keep")
    check(verdict(old, {"near": 95.0, "fp": 0.20, "ms": 50.0}).startswith("GIỮ"),
          "much slower = keep")
    check(verdict({"near": None, "fp": 0.2, "ms": 30}, {"near": None, "fp": 0.1, "ms": 30}).startswith("GIỮ"),
          "no near labels = keep")


def main():
    test_ring_points()
    test_ring_sweep_and_cooldown()
    test_ring_fight_rules()
    test_hard_cases()
    test_hard_case_cap()
    test_hard_case_stats_and_zip()
    test_ctx_hard_case_needs_a_blind_model()
    test_near_crop_geometry()
    test_near_crop_blanks_before_cropping()
    test_near_boxes_are_candidates_only()
    test_near_conf_setting()
    test_detect_stats_carries_crop_ms()
    test_compare_verdict()
    print(f"\nALL {len(PASS)} CHECKS PASSED")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
