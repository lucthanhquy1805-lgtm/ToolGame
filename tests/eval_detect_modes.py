"""PLAN 0.33: boxes per frame, v15 default against the adaptive two-tier scheme.

v15 ran the full frame at 640, 5 times a second: ~180 ms a detect on the game PC, two onnxruntime threads, so
~0.9 of a core non-stop, and the client stuttered when 10-17 monsters were on screen (20261125_112040_hunt).
v16 keeps the full 640 frame while the bot is LOOKING for a monster (the only moment a far box matters). While a
FIGHT is running it ALTERNATES: one full 640 frame, then one play-area crop at 416 (~35 ms instead of ~180 ms).
A fight only reads boxes next to the character - the lock to follow and a nearer monster to switch to - and the
full frame every other detect still shows the far ones, so nothing is lost for longer than half a second.

This measures what that costs in boxes, on the saved frames of real hunts:
  * search frames  - identical by construction (same size, same crop), printed as a check;
  * fight frames   - full 640 against 416 + ROI, both overall and for boxes within NEAR_PX of the character
                     (the ones the fight actually reads);
  * whole run      - the mix the adaptive scheme would really see (every other fight frame cropped), against
                     v15 everywhere.
A fight frame = its timestamp falls inside a fight window of events.jsonl (fight_end t minus its seconds).

Usage: python tests/eval_detect_modes.py [<record dir> ...]   (default: the two v15/v14 orc hunts)
A recording whose frames are not on this machine is skipped.
"""
import json
import os
import sys

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from lineage_auto.vision import yolox_mobs  # noqa: E402
from lineage_auto.vision.geometry import play_max_radius  # noqa: E402

DEFAULT_RECORDS = ("records_game/20261125_092741_hunt", "records_game/20261125_112040_hunt")
MAP_KEY = "blessed_orc"
NEAR_PX = 120  # a fight reads the lock (chase radius) and a switch candidate (< 70 px); 120 covers both
MIN_SHARE = 0.9  # the user's bar: the adaptive mix must keep 90% of the boxes v15 saw


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def fight_windows(rec):
    """(start, end) of every fight of the recording, from the fight_end events."""
    out = []
    for e in read_jsonl(os.path.join(rec, "events.jsonl")):
        if e.get("kind") == "fight_end":
            end = float(e.get("t") or 0.0)
            out.append((end - float(e.get("seconds") or 0.0), end))
    return out


def count(frame, char, size, roi):
    """(all boxes, boxes within NEAR_PX of the character) for one input size / crop."""
    h, w = frame.shape[:2]
    hits, _figures, _dies = yolox_mobs.detect(
        frame, char[0], char[1], play_max_radius(w, h, char[0], char[1]),
        map_key=MAP_KEY, size=size, roi=roi)
    near = sum(1 for x, y in hits if (x - char[0]) ** 2 + (y - char[1]) ** 2 <= NEAR_PX ** 2)
    return len(hits), near


def mean(values):
    return sum(values) / len(values) if values else 0.0


def report(rec):
    frames = [f for f in read_jsonl(os.path.join(rec, "frames.jsonl"))
              if os.path.exists(os.path.join(rec, f["file"]))]
    if not frames:
        print(f"skipped: {rec} has no frames on this machine")
        return None
    windows = fight_windows(rec)
    rows = {"fight": {"full": [], "roi": [], "full_near": [], "roi_near": []},
            "search": {"full": [], "roi": [], "full_near": [], "roi_near": []}}
    for f in frames:
        image = cv2.imread(os.path.join(rec, f["file"]))
        if image is None:
            continue
        char = tuple(f.get("char") or (image.shape[1] // 2, int(image.shape[0] * 0.4)))
        t = float(f.get("t") or 0.0)
        where = "fight" if any(a <= t <= b for a, b in windows) else "search"
        full, full_near = count(image, char, 640, False)
        roi, roi_near = count(image, char, 416, True)
        rows[where]["full"].append(full)
        rows[where]["roi"].append(roi)
        rows[where]["full_near"].append(full_near)
        rows[where]["roi_near"].append(roi_near)

    name = os.path.basename(rec.rstrip("/\\"))
    n_fight, n_search = len(rows["fight"]["full"]), len(rows["search"]["full"])
    print(f"== {name}: {n_fight + n_search} frames ({n_fight} during a fight, {n_search} searching), "
          f"{len(windows)} fights")
    v15 = mean(rows["fight"]["full"] + rows["search"]["full"])
    # Alternating: every other fight detect is the full frame again.
    alternating = [(roi if i % 2 else full) for i, (full, roi)
                   in enumerate(zip(rows["fight"]["full"], rows["fight"]["roi"]))]
    v16 = mean(alternating + rows["search"]["full"])
    print(f"   search frames (640 both ways): {mean(rows['search']['full']):.2f} boxes/frame")
    if n_fight:
        print(f"   fight frames : 640 full {mean(rows['fight']['full']):.2f} -> 416+roi "
              f"{mean(rows['fight']['roi']):.2f} -> alternating {mean(alternating):.2f} boxes/frame")
        print(f"   fight frames, boxes within {NEAR_PX} px of the character (what the fight reads): "
              f"640 {mean(rows['fight']['full_near']):.2f} -> 416+roi {mean(rows['fight']['roi_near']):.2f}")
    share = v16 / v15 if v15 else 1.0
    print(f"   whole run    : v15 (640 everywhere) {v15:.2f} -> v16 adaptive {v16:.2f} boxes/frame "
          f"({share - 1:+.0%})")
    return {"name": name, "v15": v15, "v16": v16, "share": share,
            "near_full": mean(rows["fight"]["full_near"]), "near_roi": mean(rows["fight"]["roi_near"]),
            "fight_frames": n_fight}


def main(argv):
    records = argv[1:] or [os.path.join(ROOT, p) for p in DEFAULT_RECORDS]
    results = [r for r in (report(rec) for rec in records if os.path.isdir(rec)) if r]
    if not results:
        print("no recording with frames on this machine")
        return 0
    bad = [r for r in results if r["share"] < MIN_SHARE]
    for r in bad:
        print(f"FAIL {r['name']}: {r['share'] - 1:+.0%} boxes/frame, more than the {1 - MIN_SHARE:.0%} allowed")
    # The near boxes are the ones a fight uses; losing those would be the real regression.
    lost_near = [r for r in results if r["fight_frames"] and r["near_roi"] < MIN_SHARE * r["near_full"]]
    for r in lost_near:
        print(f"FAIL {r['name']}: boxes near the character during a fight {r['near_full']:.2f} -> {r['near_roi']:.2f}")
    print("detect modes OK" if not (bad or lost_near) else "detect modes NOT OK")
    return 1 if (bad or lost_near) else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
