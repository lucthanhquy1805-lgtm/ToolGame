"""3.0-L v2, offline: home = the party leader's crown on the minimap; elf hand attack only on the attack cursor;
the hand reach learned from range_walk.

- vision/party_minimap on records_game/mG1RN30H/r232815 (f_00001 stacked ~0 steps, f_00027 / f_00030 ~19-22
  steps W, f_00021 no crown) and no crown on 350 minimap frames of other records (skipped without frames)
- features/leader.LeaderHome: the offset is set from the crown, arrival = 2 reads <= 2 steps, the crown staying
  on us while we walk 8 steps = we are the leader -> start point; lure_return "leader_range", lure_home
  leader_steps; session._walk_home walks to the crown (one click per 0.7 s), not by counted clicks
- m6TSP63T/r232626 (elf Lv27, cursor_last None in all 38 fights, range_walk at 140-217 px): no click without the
  attack cursor; after the first range_walk the reach shrinks and the farther boxes of the record are skipped
Run: python tests/test_leader.py
"""
import glob
import json
import math
import os
import sys
import types

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_attack_range import CHAR, Ctx, Tg, _elf_fight, _lure_ctx, _start_trip, check, shifted, texture  # noqa: E402
from lineage_auto.features import combat as cb  # noqa: E402
from lineage_auto.features import exploration as ex  # noqa: E402
from lineage_auto.features.leader import LeaderHome  # noqa: E402
from lineage_auto.features.targeting import TargetingFeature  # noqa: E402
from lineage_auto.vision import minimap, party_minimap  # noqa: E402

REC = os.path.join(ROOT, "records_game", "mG1RN30H", "r232815")
R232626 = os.path.join(ROOT, "records_game", "m6TSP63T", "r232626")


def frame(n):
    return cv2.imread(os.path.join(REC, f"f_{n:05d}.jpg"))


def steps(vec):
    return math.hypot(*vec) / minimap.STEP_MM


def have_frames():
    if os.path.exists(os.path.join(REC, "f_00027.jpg")):
        return True
    print("skip: records_game/mG1RN30H/r232815 frames are not on this machine")
    return False


def test_crown_r232815():
    if not have_frames():
        return
    v1, v21, v27, v30 = (party_minimap.read(frame(n)) for n in (1, 21, 27, 30))
    check(v1 is not None and steps(v1) <= 2.5, f"f_00001: everyone stacked, leader {steps(v1):.1f} steps")
    check(v21 is None, "f_00021: the crown is off the minimap -> None")
    for name, v in (("f_00027", v27), ("f_00030", v30)):
        # the dot, not the crown (the crown is drawn ~8 px beside it): 19-22 steps, not the 25-27 eyeballed
        check(v is not None and 17 <= steps(v) <= 27 and v[0] < 0 and abs(v[1]) < abs(v[0]),
              f"{name}: leader {steps(v):.1f} steps W-WSW ({v[0]:.0f}, {v[1]:.0f}) minimap px")


def test_no_crown_elsewhere():
    files = []
    for d in sorted(glob.glob(os.path.join(ROOT, "records_game", "2026112*_hunt"))):
        files += sorted(glob.glob(os.path.join(d, "f_*.jpg")))[::10][:40]
    seen = bad = 0
    for f in files:
        img = cv2.imread(f)
        if img is None or minimap.read(img) is None:
            continue
        seen += 1
        if party_minimap.read(img) is not None:
            bad += 1
    if not seen:
        print("skip: no minimap frames of solo hunts on this machine")
        return
    check(bad == 0, f"no crown on {seen} minimap frames of solo hunts (grass / yellow names seen through it)")


def _leader_ctx(cls="knight"):
    ctx, lure, clock = _lure_ctx(cls, lure_steps=10)
    return ctx, lure, clock, LeaderHome(ctx)


def test_leader_home():
    if not have_frames():
        return
    ctx, lure, clock, lh = _leader_ctx()
    lh.update(frame(1), 1280)
    check(ctx.recorder.kinds("leader_seen") and ctx.state["leader_mode"] and lh.steps() <= 2.5,
          "f_00001: leader_seen, the offset is the leader (all stacked)")
    lh.update(frame(1), 1280)
    check(lh.arrived(), "2 reads <= 2 steps = at the leader")
    _start_trip(ctx, lure, clock)
    lh.update(frame(27), 1280)
    s = TargetingFeature.steps_from_home(types.SimpleNamespace(ctx=ctx, step_px=ctx.step_px))
    check(abs(s - lh.steps()) < 0.2 and 17 <= s <= 27 and ctx.offset()[0] > 0 and not lh.arrived(),
          f"f_00027: steps_from_home = {s:.1f} = the leader (the old click count said 0), we are E of it")
    check(lure.return_why(100) == "leader_range", "a trip 22 steps from the leader (lure_steps 10): leader_range")
    lure.go_home(lure.return_why(100))
    check(ctx.recorder.kinds("lure_return")[-1]["why"] == "leader_range", "lure_return why=leader_range")
    ctx2, lure2, clock2, lh2 = _leader_ctx()
    lh2.update(frame(1), 1280)
    _start_trip(ctx2, lure2, clock2)
    lh2.update(frame(21), 1280)
    check(lh2.vec is None and lure2.return_why(100) == "leader_range",
          "f_00021: the crown left the minimap on a trip -> leader_range")
    # the session's walk home: to the crown, re-read after each click, 0.7 s per click
    from lineage_auto.runtime.session import AccountSession
    tg = Tg(ctx, (CHAR[0] + 60, CHAR[1]))
    tg.ctx, tg.leader, tg.minimap = ctx, lh, None
    tg.steps_from_home = types.MethodType(TargetingFeature.steps_from_home, tg)
    tg.step_px = types.MethodType(TargetingFeature.step_px, tg)
    ctx.frames = [frame(27), frame(30), frame(1), frame(1)]
    naps = []
    ctx.sleep = lambda t: naps.append(t) or True
    expl = ex.ExplorationFeature(ctx, targeting=tg)
    st = types.SimpleNamespace(ctx=ctx, account=ctx.account, targeting=tg, exploration=expl, lure=lure)
    ctx.input.log.clear()
    AccountSession._walk_home(st, ctx.rect())
    clicks = [x for x in ctx.input.log if x[0] == "click"]
    check(len(clicks) == 3 and all(x[1] < CHAR[0] for x in clicks) and lh.arrived(),
          f"walk_home: {len(clicks)} clicks west to the crown, stops on 2 reads at it")
    check(naps.count(ex.HOME_CLICK_SEC) == len(clicks), "one walk click per 0.7 s (no stacked clicks)")
    home = ctx.recorder.kinds("lure_home")
    check(home and home[-1]["leader_steps"] is not None and home[-1]["leader_steps"] <= 2.5,
          f"lure_home carries leader_steps {home[-1:]}")


def test_self_leader():
    if not have_frames():
        return
    ctx, lure, clock, lh = _leader_ctx()
    for _ in range(6):
        lh.update(frame(1), 1280)
        ctx.note_walk(CHAR, (CHAR[0] + 160, CHAR[1]), ctx.rect())  # 2 steps E, the crown stays on us
    lh.update(frame(1), 1280)
    check(lh.self_leader and not lh.wanted() and not ctx.state["leader_mode"] and ctx.recorder.kinds("leader_self"),
          "the crown walked 8+ steps with us -> we are the leader: home_mode start, event leader_self")
    check(ctx.offset()[0] > 8 * ctx.step_px(), f"the trip is dead reckoned again ({ctx.offset()[0]:.0f} px E)")
    ctx.account.scan.home_mode = "start"
    lh2 = LeaderHome(ctx)
    lh2.update(frame(27), 1280)
    check(not lh2.seen and ctx.state.get("leader") is None, "home_mode start: the crown is not used")


def _events(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def test_r232626_elf():
    """No click without the attack cursor; the first range_walk shrinks the reach; farther boxes are skipped."""
    ev_path = os.path.join(R232626, "events.jsonl")
    if not os.path.exists(ev_path):
        print("skip: m6TSP63T/r232626 not on this machine")
        return
    rows = _events(ev_path)
    ends = [e for e in rows if e["kind"] == "fight_end"]
    walks = [e["dist"] for e in rows if e["kind"] == "range_walk"]
    check(len(ends) == 38 and all(e["cursor_last"] is None for e in ends) and len(walks) == 7,
          f"r232626: {len(ends)} fights, cursor_last None in all, {len(walks)} range_walks at {sorted(walks)} px")
    # no attack cursor on the box: hover only, never a click (a click on the ground walks)
    far = (CHAR[0] + 150, CHAR[1] + 40)
    cb.CursorProbe.current_hash = staticmethod(lambda: "ground")
    ctx = Ctx("elf")
    ctx.account.scan.hunt_range, ctx.account.scan.melee_max_sec = 10, 5.0
    ctx.account.health.use_skill = False
    ctx.frames = [texture()]
    tg = Tg(ctx, far)
    tg.ctx = ctx
    cf = cb.CombatFeature(ctx, targeting=tg)
    cf.engage(types.SimpleNamespace(local=far, screen=ctx.rect().to_screen(*far)), ctx.rect(), CHAR)
    check(not [x for x in ctx.input.log if x[0] == "click"] and [x for x in ctx.input.log if x[0] == "move"]
          and cf.last_outcome == "lost" and cf._skipped.get("no_sword") == cb.HAND_NO_SWORD,
          f"cursor 'ground': {cf._skipped.get('no_sword')} hovers, 0 clicks, the lock dropped ({cf.last_outcome})")
    # the sword is there: the hand attack clicks; it walks off at the first range_walk distance -> learn
    first = walks[0]
    img = texture()
    walk = [img] + [shifted(img, 40 * n, -20 * n) for n in range(1, 8)]
    point = (CHAR[0] + first, CHAR[1])
    ctx, cf, tg = _elf_fight(point, frames=list(walk))
    learned = ctx.account.scan.attack_range_px_learned
    check(cf.last_outcome == "range_walk" and learned == int(0.9 * first) and [x for x in ctx.input.log
                                                                                if x[0] == "click"],
          f"first range_walk at {first} px -> reach learned {learned} px")
    hits = [tuple(h) for r in _events(os.path.join(R232626, "frames.jsonl")) for h in r.get("hits", [])]
    tgf = TargetingFeature(ctx)
    tgf.char = CHAR
    d = lambda p: math.hypot(p[0] - CHAR[0], p[1] - CHAR[1])  # noqa: E731
    out = [p for p in hits if tgf.out_of_range(p, CHAR)]
    check(out and all(d(p) > learned for p in out) and all(d(p) <= learned for p in hits if p not in out),
          f"{len(out)} of the record's {len(hits)} boxes are past {learned} px now -> out_of_range_skip")
    cb.CursorProbe.current_hash = staticmethod(lambda: "sword")


def main():
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"== {name}")
            fn()
    print("leader tests OK")


if __name__ == "__main__":
    main()
