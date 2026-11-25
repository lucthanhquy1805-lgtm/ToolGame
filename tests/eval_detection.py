"""Detection benchmark (PLAN 0.5): recall / false positives / ms per frame.

Usage:  python tests/eval_detection.py [--maps abandoned,toi] [--conf 0.15] [--size 416] [--roi] [--config X] [-v]
PLAN 0.39 rule: a new model becomes a default only after it is scored at the input the game PC runs:
--config <game PC lineage_auto_config.json> (records/<hunt>/ carries a copy) takes size and roi from its scan settings.
Labels: tests/data/monster_labels.json (images in docs/game_reference/).
Runs the same code path as the bot (yolox_mobs.detect_centers, radius from the
character), so every detection change must report these numbers before/after.
"""
import argparse
import json
import math
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from lineage_auto import hunt_maps  # noqa: E402
from lineage_auto.vision import yolox_mobs  # noqa: E402
from lineage_auto.vision.geometry import char_anchor, play_max_radius  # noqa: E402

LABELS = os.path.join(ROOT, "tests", "data", "monster_labels.json")
IMAGES = os.path.join(ROOT, "docs", "game_reference")
# A detection within this many px of a label counts as that label (box center vs body center).
MATCH_R = 60


def score(hits, monsters, ignore):
    """Greedy nearest match. Returns (true positives, false positives)."""
    left = [tuple(m) for m in monsters]
    tp = fp = 0
    for x, y in hits:
        best = min(left, key=lambda m: math.hypot(m[0] - x, m[1] - y), default=None)
        if best is not None and math.hypot(best[0] - x, best[1] - y) <= MATCH_R:
            left.remove(best)
            tp += 1
        elif not any(math.hypot(ix - x, iy - y) <= MATCH_R for ix, iy in ignore):
            fp += 1
    return tp, fp


def evaluate(map_key, labels, verbose=False, conf=None, images=IMAGES, size=640, roi=False):
    yolox_mobs.ensure_session(map_key, size)
    stats = {"day": [0, 0], "night": [0, 0]}  # [found, total]
    fp_total, ms = 0, []
    for name, lab in labels.items():
        frame = cv2.imread(os.path.join(images, name))
        # Character and radius from the real frame size (game PC records are 1187x890, references 1280x960).
        h, w = frame.shape[:2]
        char = char_anchor(w, h)
        t = time.perf_counter()
        hits = yolox_mobs.detect_centers(frame, *char, radius=play_max_radius(w, h, *char), map_key=map_key, conf=conf,
                                         size=size, roi=roi)
        ms.append(1000 * (time.perf_counter() - t))
        tp, fp = score(hits, lab["monster"], lab.get("ignore", []))
        bucket = stats["night" if lab.get("night") else "day"]
        bucket[0] += tp
        bucket[1] += len(lab["monster"])
        fp_total += fp
        if verbose:
            print(f"    {name:28s} found {tp}/{len(lab['monster'])} fp {fp}  hits={hits}")
    ms = sorted(ms[1:] or ms)  # first call warms the session up
    return stats, fp_total, ms[len(ms) // 2]


def pct(found, total):
    return f"{found}/{total} ({100 * found / total:.0f}%)" if total else "-"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--maps", default=",".join(m.key for m in hunt_maps.all_maps()))
    parser.add_argument("--conf", type=float, default=None, help="override every map's threshold")
    parser.add_argument("--labels", default=LABELS, help="labels json (e.g. from analyze_records.py)")
    parser.add_argument("--images", default=IMAGES, help="folder holding the labelled images")
    parser.add_argument("--size", type=int, default=640, help="ONNX input side (PLAN 0.31: model/<name>_<size>.onnx)")
    parser.add_argument("--roi", action="store_true", help="crop the play area around the character first")
    parser.add_argument("--config", help="game PC lineage_auto_config.json: size/roi = its scan.input_size/detect_roi")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--split", help="only frames tests/prelabel.py picked for this split (e.g. test)")
    args = parser.parse_args()
    if args.config:
        scan = json.load(open(args.config, encoding="utf-8"))["accounts"][0]["scan"]
        args.size, args.roi = int(scan.get("input_size", 640)), bool(scan.get("detect_roi", False))
    elif args.size == 640:
        print("note: 640 - a default must also be scored at the game PC input (--config, PLAN 0.39)")
    labels = json.load(open(args.labels, encoding="utf-8"))["images"]
    if args.split:
        labels = {n: lab for n, lab in labels.items() if lab.get("split") == args.split}
    todo = [n for n, lab in labels.items() if lab.get("todo")]
    if todo:
        print(f"warning: {len(todo)} frames still marked todo (recall is not meaningful until labelled)")
    print(f"size={args.size} roi={args.roi} conf={args.conf or 'per map'} images={len(labels)} match_r={MATCH_R}px")
    # precision = found / (found + fp): only meaningful on reviewed frames (todo=false: every monster has a label)
    print(f"{'model':16s} {'conf':>5s} {'recall all':>14s} {'day':>14s} {'night':>12s} {'fp':>4s} {'precision':>9s} "
          f"{'ms/frame':>9s}")
    for key in args.maps.split(","):
        if not hunt_maps.model_exists(key):
            print(f"{key:16s} model missing")
            continue
        stats, fp, med = evaluate(key, labels, args.verbose, args.conf, args.images, args.size, args.roi)
        found = stats["day"][0] + stats["night"][0]
        total = stats["day"][1] + stats["night"][1]
        print(f"{key:16s} {args.conf or hunt_maps.get(key).conf:5.2f} {pct(found, total):>14s} {pct(*stats['day']):>14s} {pct(*stats['night']):>12s} "
              f"{fp:>4d} {(found / (found + fp) if found + fp else 0):>9.0%}{'?' if todo else ' '} {med:>8.0f}")


if __name__ == "__main__":
    main()
