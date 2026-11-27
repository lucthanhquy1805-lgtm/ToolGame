"""PLAN 0.43: how often a monster NEAR the character is passed over, on the saved frames of real hunts.

The user's report: a monster right next to the character is missed, not picked up again, or the bot switches to
another one. Three numbers per recording, so a change can be compared before / after:

  A "acquire": of the boxes within NEAR_PX of the character in a frame, how many ``TargetingFeature.candidates``
    does NOT offer as a target, and WHY (corpse / miss_ttl / blacklist / out of range / deduped / cut by
    scan.max_probe_points).
  B "while fighting another one": a frame inside a simulated fight with a box at least SHARE times closer to the
    character than the lock, which the bot did not point at within ATTEND_SEC (the "it beats the wrong one"
    report; combat only switches to a box inside MELEE_DIST, so this is where that rule shows).
  C "wrong switch": fights that ended as ``switch`` although the old lock still had a real box in that frame.

Truth = the current detector on the WHOLE frame (what the bot could see at best), not the game PC's recorded
boxes (those were detected at its own size / crop).

Usage: python tests/test_near_miss.py [<record name or dir> ...]   (default: the four hunts of PLAN 0.43)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math  # noqa: E402
from collections import Counter  # noqa: E402

import cv2  # noqa: E402
from test_hunt_records import CHAR, ROOT, Replay, read_jsonl  # noqa: E402

NEAR_PX = 150  # "a monster at close range" in the report
MATCH_PX = 48  # the same monster in two lists (targeting.TRACK_MATCH_PX)
ATTEND_SEC = 2.0  # the bot has this long to point at a near box before it counts as passed over
SHARE = 0.5  # "much closer than the lock" (features/targeting.SWITCH_SHARE)
STEP = 2  # every 2nd frame: one detect per frame is the cost of this test

RECORDS = ("20261126_101941_hunt", "20261126_090350_hunt", "20261126_225217_hunt", "20261127_003555_hunt")
MAPS = {"20261127_003555_hunt": ("fallen_blessed", "타락한 축복의 땅의 봄")}


def near(points, origin=CHAR, radius=NEAR_PX):
    return [p for p in points if math.hypot(p[0] - origin[0], p[1] - origin[1]) <= radius]


def measure(rec):
    from lineage_auto.features import targeting as tg
    from lineage_auto.vision.yolox_mobs import detect_centers

    hunt_map, zone = MAPS.get(os.path.basename(rec), ("blessed_orc", None))
    r = Replay(rec, hunt_map=hunt_map, **({"zone": zone} if zone else {}))
    moves, switches = [], []
    inp = r.ctx.input
    base_move = inp.move
    inp.move = lambda x, y: (moves.append((r.clock.now, x, y)), base_move(x, y))
    r.ctx.recorder = None

    # B / C need the simulated hunt: every fight the v11 bot started, replayed with today's logic.
    windows = r.fights()
    for a, b, outcome in windows:
        if outcome == "switch":
            switches.append((a, b))

    frames = r.frames[::STEP]
    truth = {}
    for f in frames:
        frame = cv2.imread(os.path.join(rec, f["file"]))
        hits = detect_centers(frame, CHAR[0], CHAR[1], radius=900, map_key=hunt_map)
        truth[f["t"]] = near([p for p in hits if math.hypot(p[0] - CHAR[0], p[1] - CHAR[1]) > tg.SELF_R])

    # A: what the live targeting code offers as candidates for the same frame, and why a box is left out.
    tgt = tg.TargetingFeature(r.ctx, clock=r.clock.time)
    tgt.minimap = None
    tgt.char = CHAR
    skipped = 0
    total_a = 0
    why = Counter()
    for f in frames:
        boxes = truth[f["t"]]
        if not boxes:
            continue
        r.clock.now = f["t"]
        points, _ = tgt.candidates(r.rect, CHAR)
        offered = tgt.last_monsters  # before the max_probe_points cut
        for box in boxes:
            total_a += 1
            if any(math.hypot(box[0] - x, box[1] - y) <= MATCH_PX for x, y in points):
                continue
            skipped += 1
            if any(math.hypot(box[0] - x, box[1] - y) <= MATCH_PX for x, y in offered):
                why["cut by max_probe_points"] += 1
            elif any(math.hypot(box[0] - dx, box[1] - dy) < tg.CORPSE_SKIP_RADIUS for dx, dy in tgt.last_dies):
                why["corpse"] += 1
            elif tgt.out_of_range(box, CHAR):
                why["out of range"] += 1
            elif tgt._recent_miss(box):
                why["miss_ttl"] += 1
            elif tgt.is_blocked(box):
                why["blacklist"] += 1
            else:
                why["deduped / other"] += 1

    # B: inside a fight, a box much closer to the character than the lock that the bot never pointed at.
    unattended = total_b = 0
    for t, boxes in truth.items():
        if not any(a <= t <= b for a, b, _o in windows):
            continue
        pointed = [(x, y) for mt, x, y in moves if t <= mt <= t + ATTEND_SEC]
        lock = next(((x, y) for mt, x, y in reversed(moves) if mt <= t), None)
        if lock is None:
            continue
        lock_d = math.hypot(lock[0] - CHAR[0], lock[1] - CHAR[1])
        for box in boxes:
            d = math.hypot(box[0] - CHAR[0], box[1] - CHAR[1])
            if d >= SHARE * lock_d:
                continue  # not "much closer": the bot is right to keep its lock
            total_b += 1
            if not any(math.hypot(box[0] - x, box[1] - y) <= MATCH_PX for x, y in pointed):
                unattended += 1

    # C: a switch while the old lock still had a real box in that frame.
    wrong = 0
    for a, b in switches:
        key = min(truth, key=lambda t: abs(t - b))
        if any(math.hypot(x - CHAR[0], y - CHAR[1]) <= NEAR_PX for x, y in truth[key]):
            wrong += 1

    name = os.path.basename(rec)
    print(f"== {name}: {len(frames)} frames, {sum(len(v) for v in truth.values())} near boxes, "
          f"{len(windows)} fights")
    print(f"   A acquire: {skipped}/{total_a} near boxes not offered as a candidate "
          f"({100.0 * skipped / max(1, total_a):.0f}%) {dict(why)}")
    print(f"   B much closer than the lock: {unattended}/{total_b} never pointed at within {ATTEND_SEC:.0f}s "
          f"({100.0 * unattended / max(1, total_b):.0f}%)")
    print(f"   C switches with the old box still there: {wrong}/{len(switches)}")
    return {"a": (skipped, total_a), "b": (unattended, total_b), "c": (wrong, len(switches))}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    names = sys.argv[1:] or list(RECORDS)
    for name in names:
        rec = name if os.path.isdir(name) else os.path.join(ROOT, "records_game", name)
        first = read_jsonl(os.path.join(rec, "frames.jsonl"))[:1]
        if not first or not os.path.exists(os.path.join(rec, first[0]["file"])):
            print(f"skipped: {rec} has no frames on this machine")
            continue
        measure(rec)
    print("near miss measurement done")


if __name__ == "__main__":
    main()
