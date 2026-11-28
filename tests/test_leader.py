"""3.0-L v2 / rc11, offline: home = the party leader's crown on the minimap.

- vision/party_minimap.read: the crown's 3 points (+ its dark outline) -> recall over EVERY frame of the rc10 field
  records m6TSP63T/r010326 (elf) + mG1RN30H/r010322 (prince) + r232815 (labels below, checked by eye), >= 95 %
  where the crown is shown, 0 reads where it is not, 0 on solo hunts; the leader = the crown's marker (elf
  t=132-142: the crown on OUR arrow = 0 steps; rc10 read 31.9 W off another member's dot)
- party_minimap.self_is_leader: the party panel's small crown on our own row (the real frames: never; a frame with
  the crown moved to row 1: yes) -> LeaderHome.self_leader; no other way to get there
- LeaderHome: offset = character - leader; arrival 2 reads <= 2.5 steps; away > 4 (hysteresis); crown unseen
  > LOST_SEC = leader_lost (no walking: wander, _walk_home and the lure stand)
- session._walk_home: to the crown, 0.7 s per click, a ranged class gives up after HOME_MAX_CLICKS
- lure: leader_range, lure_home leader_steps
- m6TSP63T/r232626 + r010326 (elf): clicks only on the attack cursor, hover spots over the box, a monster in melee
  reach is hit without it; the hand reach learned from range_walk
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

from test_attack_range import (CHAR, Ctx, Tg, _elf_fight, _lure_ctx, _start_trip, check, shifted,  # noqa: E402
                               texture)
from lineage_auto.features import combat as cb  # noqa: E402
from lineage_auto.features import exploration as ex  # noqa: E402
from lineage_auto.features import leader as ld  # noqa: E402
from lineage_auto.features.leader import LeaderHome  # noqa: E402
from lineage_auto.features.targeting import TargetingFeature  # noqa: E402
from lineage_auto.vision import minimap, party_minimap  # noqa: E402

RG = os.path.join(ROOT, "records_game")
R232815 = os.path.join(RG, "mG1RN30H", "r232815")
ELF = os.path.join(RG, "m6TSP63T", "r010326")
PRINCE = os.path.join(RG, "mG1RN30H", "r010322")
R232626 = os.path.join(RG, "m6TSP63T", "r232626")
# Crown shown on the minimap (checked by eye on montages, rc11): every elf frame; prince f_00001-00144 (from 145
# the leader is off the minimap); r232815 f_00001 (mostly under the stacked dots), f_00027, f_00030.
CROWN = {ELF: lambda n: True, PRINCE: lambda n: n <= 144, R232815: lambda n: n != 21}


def frame(rec, n):
    return cv2.imread(os.path.join(rec, f"f_{n:05d}.jpg"))


def steps(vec):
    return math.hypot(*vec) / minimap.STEP_MM


def have(rec):
    if glob.glob(os.path.join(rec, "f_*.jpg")):
        return True
    print(f"skip: {os.path.relpath(rec, ROOT)} frames are not on this machine")
    return False


def test_crown_recall():
    shown = found = false = 0
    for rec, label in CROWN.items():
        if not have(rec):
            continue
        r_shown = r_found = r_false = 0
        for f in sorted(glob.glob(os.path.join(rec, "f_*.jpg"))):
            n = int(os.path.basename(f)[2:7])
            got = party_minimap.read(cv2.imread(f)) is not None
            if label(n):
                r_shown += 1
                r_found += got
            else:
                r_false += got
        print(f"   {os.path.relpath(rec, RG)}: crown found {r_found}/{r_shown}, read where none: {r_false}")
        shown, found, false = shown + r_shown, found + r_found, false + r_false
    if not shown:
        return
    check(found >= 0.95 * shown and false == 0,
          f"crown recall {found}/{shown} = {100 * found / shown:.1f} % (>= 95 %), {false} false reads")


def test_crown_positions():
    if not (have(ELF) and have(R232815)):
        return
    elf = [party_minimap.read(frame(ELF, n)) for n in range(35, 39)]
    check(all(v is not None and steps(v) <= 1.0 for v in elf),
          f"elf f_00035-38 (t=132-142): the crown is on OUR arrow -> {[round(steps(v), 1) for v in elf]} steps "
          f"(rc10 read 31.9 W: another member's dot)")
    v27 = party_minimap.read(frame(R232815, 27))
    check(v27 is not None and 24 <= steps(v27) <= 27 and v27[0] < 0 and abs(v27[1]) < abs(v27[0]),
          f"r232815 f_00027: leader {steps(v27):.1f} steps W ({v27[0]:.0f}, {v27[1]:.0f})")


def test_no_crown_solo():
    seen = bad = 0
    for d in sorted(glob.glob(os.path.join(RG, "2026112*_hunt"))):
        for f in sorted(glob.glob(os.path.join(d, "f_*.jpg")))[::4][:150]:
            img = cv2.imread(f)
            if img is None or minimap.read(img) is None:
                continue
            seen += 1
            bad += party_minimap.read(img) is not None
    if not seen:
        print("skip: no solo hunt frames with the minimap here")
        return
    check(bad == 0, f"no crown on {seen} minimap frames of solo hunts (grass specks, thatch, yellow names)")


def _panel_moved(img):
    """The panel crown of row 2 (the wizard) moved onto row 1 (us)."""
    out = img.copy()
    crown = img[337:355, 18:40].copy()
    out[337:355, 18:40] = img[337:355, 0:22]
    out[288:306, 18:40] = crown
    return out


def test_party_panel():
    if not (have(ELF) and have(PRINCE)):
        return
    reads = [party_minimap.self_is_leader(cv2.imread(f))
             for rec in (ELF, PRINCE) for f in sorted(glob.glob(os.path.join(rec, "f_*.jpg")))]
    check(reads and all(r is False for r in reads), f"{len(reads)} real frames: the crown is on another row")
    moved = _panel_moved(frame(ELF, 1))
    check(party_minimap.self_is_leader(moved) is True, "crown moved to our own row -> we lead")
    ctx, _lure, _clock, lh = _leader_ctx()
    lh.update(moved, 1280)
    check(not lh.self_leader, "one panel read is not enough")
    lh.update(moved, 1280)
    check(lh.self_leader and not lh.wanted() and ctx.recorder.kinds("leader_self")[-1]["source"] == "party_panel",
          "two reads -> self_leader (start point), event leader_self source=party_panel")
    ctx, _lure, _clock, lh = _leader_ctx()
    for n in range(35, 39):  # rc10 set leader_self here (elf t=156, prince t=51.8): never from the minimap now
        for _ in range(3):
            lh.update(frame(ELF, n), 1280)
            ctx.note_walk(CHAR, (CHAR[0] + 160, CHAR[1]), ctx.rect())
    check(not lh.self_leader and not ctx.recorder.kinds("leader_self"),
          "the crown on our arrow while we walk is NOT taken for 'we lead' any more")


def _leader_ctx(cls="knight"):
    ctx, lure, clock = _lure_ctx(cls, lure_steps=10)
    return ctx, lure, clock, LeaderHome(ctx, clock=lambda: clock[0])


def test_leader_home():
    if not (have(R232815) and have(ELF)):
        return
    ctx, lure, clock, lh = _leader_ctx()
    lh.update(frame(ELF, 1), 1280)
    check(ctx.recorder.kinds("leader_seen") and ctx.state["leader_mode"] and lh.steps() <= 1.0,
          "elf f_00001: leader_seen, the leader is on us")
    lh.update(frame(ELF, 1), 1280)
    check(lh.arrived(), "2 reads <= 2.5 steps = at the leader")
    _start_trip(ctx, lure, clock)
    lh.update(frame(R232815, 27), 1280)
    s = TargetingFeature.steps_from_home(types.SimpleNamespace(ctx=ctx, step_px=ctx.step_px))
    check(abs(s - lh.steps()) < 0.2 and 24 <= s <= 27 and ctx.offset()[0] > 0 and not lh.arrived(),
          f"r232815 f_00027: steps_from_home = {s:.1f} = the leader, we are E of it")
    check(lure.return_why(100) == "leader_range", "a trip 25 steps from the leader (lure_steps 10): leader_range")
    lure.go_home(lure.return_why(100))
    check(ctx.recorder.kinds("lure_return")[-1]["why"] == "leader_range", "lure_return why=leader_range")
    ctx2, lure2, clock2, lh2 = _leader_ctx()
    lh2.update(frame(ELF, 1), 1280)
    _start_trip(ctx2, lure2, clock2)
    lh2.update(frame(R232815, 21), 1280)
    check(lh2.vec is None and lure2.return_why(100) == "leader_range",
          "r232815 f_00021: the crown left the minimap on a trip -> leader_range at once")
    # the session's walk home: to the crown, re-read after each click, 0.7 s per click
    from lineage_auto.runtime.session import AccountSession
    tg = _tg(ctx, lh)
    ctx.frames = [frame(R232815, 27), frame(R232815, 30), frame(ELF, 1), frame(ELF, 1)]
    naps = []
    ctx.sleep = lambda t: naps.append(t) or True
    expl = ex.ExplorationFeature(ctx, targeting=tg)
    st = types.SimpleNamespace(ctx=ctx, account=ctx.account, targeting=tg, exploration=expl, lure=lure)
    ctx.input.log.clear()
    AccountSession._walk_home(st, ctx.rect())
    clicks = [x for x in ctx.input.log if x[0] == "click"]
    check(len(clicks) == 2 and all(x[1] < CHAR[0] for x in clicks) and lh.arrived(),
          f"walk_home: {len(clicks)} clicks west to the crown, then 2 reads at it without a click")
    check(naps.count(ex.HOME_CLICK_SEC) == len(clicks) + 1, "one walk click per 0.7 s (no stacked clicks)")
    home = ctx.recorder.kinds("lure_home")
    check(home and home[-1]["leader_steps"] is not None and home[-1]["leader_steps"] <= 2.5,
          f"lure_home carries leader_steps {home[-1:]}")


def _tg(ctx, lh, ranged=False):
    tg = Tg(ctx, (CHAR[0] + 60, CHAR[1]))
    tg.ctx, tg.leader, tg.minimap = ctx, lh, None
    tg.steps_from_home = types.MethodType(TargetingFeature.steps_from_home, tg)
    tg.step_px = types.MethodType(TargetingFeature.step_px, tg)
    tg.ranged = lambda: ranged
    tg.last_monsters = []
    return tg


def test_leader_lost():
    if not have(ELF):
        return
    from lineage_auto.runtime.session import AccountSession
    ctx, lure, clock, lh = _leader_ctx()
    lh.update(frame(ELF, 40), 1280)  # leader 14 steps E
    check(ctx.offset()[0] < 0, "elf f_00040: the leader is 14 steps away")
    none = shifted(frame(ELF, 40), 0, 400)  # the minimap without its crown
    clock[0] += 2
    lh.update(none, 1280)
    check(not ctx.state["leader_lost"], "crown gone 2 s: not lost yet (walk on toward where it was)")
    clock[0] += 1.5
    lh.update(none, 1280)
    check(ctx.state["leader_lost"], "crown gone 3.5 s: leader_lost")
    tg = _tg(ctx, lh)
    expl = ex.ExplorationFeature(ctx, targeting=tg)
    ctx.input.log.clear()
    expl.wander(ctx.rect(), CHAR)
    check(not [x for x in ctx.input.log if x[0] == "click"], "lost: wander stands (no walk by counted clicks)")
    clock[0] += 20
    check(not lure.tick(ctx.rect(), CHAR, 100) and not lure.active, "lost: the knight starts no trip")
    ctx.frames = [none]
    ctx.state["go_home"] = True
    st = types.SimpleNamespace(ctx=ctx, account=ctx.account, targeting=tg, exploration=expl, lure=lure)
    AccountSession._walk_home(st, ctx.rect())
    check(not [x for x in ctx.input.log if x[0] == "click"], "lost: _walk_home does not walk either")


def test_hysteresis_and_cap():
    if not have(ELF):
        return
    from lineage_auto.runtime.session import AccountSession, HOME_MAX_CLICKS
    ctx, _lure, clock, lh = _leader_ctx("elf")
    lh.update(frame(ELF, 1), 1280)
    tg = _tg(ctx, lh, ranged=True)
    expl = ex.ExplorationFeature(ctx, targeting=tg)
    for away, want in ((3.0, False), (4.5, True)):
        ctx.state["offset"] = (away * ctx.step_px(), 0.0)
        ctx.input.log.clear()
        expl._home_t = None
        expl._homing = False
        expl.wander(ctx.rect(), CHAR)
        clicked = bool([x for x in ctx.input.log if x[0] == "click"])
        check(clicked == want, f"leader mode, {away} steps off: {'walk back' if want else 'stay (<= 4)'}")
    # the crown never gets nearer (r010326 t=25.8-45.3: 21 clicks at 2.1 steps): a ranged class stops at 5
    real_read = party_minimap.read
    party_minimap.read = lambda fr: (7.0, 0.0)  # 3 steps E, every read
    try:
        ctx.frames = [frame(ELF, 1)]
        ctx.state["go_home"] = True
        ctx.input.log.clear()
        ctx.sleep = lambda t: True
        st = types.SimpleNamespace(ctx=ctx, account=ctx.account, targeting=tg, exploration=expl, lure=_lure)
        AccountSession._walk_home(st, ctx.rect())
    finally:
        party_minimap.read = real_read
    clicks = [x for x in ctx.input.log if x[0] == "click"]
    check(len(clicks) == HOME_MAX_CLICKS, f"elf walk home gives up after {len(clicks)} clicks, then shoots again")
    check(ld.ARRIVE_STEPS == 2.5 and ld.LEAVE_STEPS == 4.0, "arrive <= 2.5, leave > 4")


def _events(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def _hand_fight(point, sword_at, kill_after=4):
    """An elf hand attack where the sword shows only when the mouse is within 6 px of ``sword_at`` (or nowhere)."""
    ctx = Ctx("elf")
    ctx.account.scan.hunt_range, ctx.account.scan.melee_max_sec = 10, 3.0
    ctx.account.health.use_skill = False
    ctx.frames = [texture()]
    mouse = [None]
    real_move = ctx.input.move

    def move(x, y):
        mouse[0] = (x, y)
        real_move(x, y)
    ctx.input.move = move
    tg = Tg(ctx, point, kill_after=kill_after)
    tg.ctx = ctx
    target = ctx.rect().to_screen(*sword_at) if sword_at else None
    cb.CursorProbe.current_hash = staticmethod(
        lambda: "sword" if target and mouse[0] and math.dist(mouse[0], target) <= 6 else "ground")
    cf = cb.CombatFeature(ctx, targeting=tg)
    cf.engage(types.SimpleNamespace(local=point, screen=ctx.rect().to_screen(*point)), ctx.rect(), CHAR)
    cb.CursorProbe.current_hash = staticmethod(lambda: "sword")
    return ctx, cf


def test_hand_cursor():
    far = (CHAR[0] + 150, CHAR[1] + 40)
    ctx, cf = _hand_fight(far, None, kill_after=None)
    check(not [x for x in ctx.input.log if x[0] == "click"] and cf.last_outcome == "lost"
          and cf._skipped.get("no_sword") == cb.HAND_NO_SWORD,
          f"no sword anywhere on a box 155 px off: hovers only, 0 clicks, the lock dropped ({cf.last_outcome})")
    head = (far[0], far[1] - 34)
    ctx, cf = _hand_fight(far, head)
    clicks = [x[1:] for x in ctx.input.log if x[0] == "click"]
    check(clicks and all(c == ctx.rect().to_screen(*head) for c in clicks),
          f"sword only on the head spot: {len(clicks)} clicks, all on the head (not the box centre)")
    near = (CHAR[0] + 40, CHAR[1] + 10)  # r010326: 33-103 px, centre over our own character
    ctx, cf = _hand_fight(near, None)
    check([x for x in ctx.input.log if x[0] == "click"],
          "a monster within MELEE_DIST without the sword is hit anyway (a click there cannot walk)")
    moves = [x[1:] for x in ctx.input.log if x[0] == "move"]
    check(all(math.dist(m, ctx.rect().to_screen(*CHAR)) > cb.SELF_BOX_R for m in moves[:4]),
          "hover spots on our own character are skipped")


def test_r232626_reach():
    ev_path = os.path.join(R232626, "events.jsonl")
    if not os.path.exists(ev_path):
        print("skip: m6TSP63T/r232626 not on this machine")
        return
    rows = _events(ev_path)
    ends = [e for e in rows if e["kind"] == "fight_end"]
    walks = [e["dist"] for e in rows if e["kind"] == "range_walk"]
    check(len(ends) == 38 and all(e["cursor_last"] is None for e in ends) and len(walks) == 7,
          f"r232626: {len(ends)} fights, cursor_last None in all, {len(walks)} range_walks at {sorted(walks)} px")
    first = walks[0]
    img = texture()
    walk = [img] + [shifted(img, 40 * n, -20 * n) for n in range(1, 8)]
    point = (CHAR[0] + first, CHAR[1])
    ctx, cf, tg = _elf_fight(point, frames=list(walk))
    learned = ctx.account.scan.attack_range_px_learned
    check(cf.last_outcome == "range_walk" and learned == int(0.9 * first),
          f"first range_walk at {first} px -> reach learned {learned} px")
    hits = [tuple(h) for r in _events(os.path.join(R232626, "frames.jsonl")) for h in r.get("hits", [])]
    tgf = TargetingFeature(ctx)
    tgf.char = CHAR
    d = lambda p: math.hypot(p[0] - CHAR[0], p[1] - CHAR[1])  # noqa: E731
    out = [p for p in hits if tgf.out_of_range(p, CHAR)]
    check(out and all(d(p) > learned for p in out) and all(d(p) <= learned for p in hits if p not in out),
          f"{len(out)} of the record's {len(hits)} boxes are past {learned} px now -> out_of_range_skip")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"== {name}")
            fn()
    print("leader tests OK")


if __name__ == "__main__":
    main()
