"""PLAN 3.1 steps 1-2: game-PC hard cases -> statistics + semi-automatic labels for the next model (orc_v4).

Usage:  python train/hard_cases_prep.py [--zips records_game/hard_cases] [--out records_game/hard_cases/work]
                                        [--map fallen_blessed] [--conf 0.05] [--keep-conf 0.3]
                                        [--test-share 0.2] [--normal-share 0.15] [--dry-run]

Input: the "export training data" zips of the game PCs (runtime/hard_cases.export_zip: hc_*.jpg + hard_cases.jsonl
+ stats.json), saved as records_game/hard_cases/<machine>_<date>.zip.

1. Statistics per machine: cases, day / night, source (probe / ring / chat_kill), hunting ground, duplicates
   (the same picture in two exports = md5; the same scene + point = a near duplicate: 64-bit dHash <= DHASH_SAME
   bits apart and the points <= DEDUPE_PX apart).
2. Labels for the unique cases of --map. The cursor point is a SURE monster: the current model at --conf (0.05)
   gives the box that contains the point (the nearest such box) -> status "auto"; none -> the estimated
   HC_BOX around the point -> status "review". The other monsters of the frame are the model's boxes >= --keep-conf.
   Every TEST frame is "review" whatever the model says: a test set labelled by the old model would score the old
   model. Test = the last --test-share of each machine's cases in time (fixed: the same cases on every re-run).
   "Normal" frames (--normal-share of the train cases) come from the already reviewed records of --map (no review).
Output: --out/<machine>/ (pictures + labels.json for tests/label_tool.py --review / tests/export_dataset.py),
--out/normal/, --out/manifest.json. A re-run keeps every frame already reviewed (todo false) as it is.
"""
import argparse
import collections
import glob
import hashlib
import json
import math
import os
import random
import shutil
import sys
import zipfile

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from lineage_auto import monsters  # noqa: E402
from lineage_auto.runtime.hard_cases import DEDUPE_PX, box_of  # noqa: E402

# The hover point is the mouse tip: the sprite that gives the sword is wider than the model's tight box, so on the
# trial set the point sat 7-33 px OUTSIDE the right box. A box within AUTO_GAP_PX (at 1280) of the point counts
# when it is the only one that close (the next box AUTO_ALONE_PX farther), else the frame goes to review.
AUTO_GAP_PX = 24
AUTO_ALONE_PX = 20
DHASH_SAME = 6  # bits of 64: the same scene (camera still, a few px of animation)
REVIEW_SEC = (7.5, 11.1)  # median / mean seconds per frame of the 827 frames reviewed so far (labels.json)


def dhash(img):
    small = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def machine_of(zip_path):
    """records_game/hard_cases/DESKTOP-6TSP63T_20261130.zip -> DESKTOP-6TSP63T"""
    stem = os.path.splitext(os.path.basename(zip_path))[0]
    return stem.rsplit("_", 1)[0] if "_" in stem else stem


def read_zips(paths):
    """[case dict] over every zip: machine, zip, file, bytes, md5 + the hard_cases.jsonl row."""
    cases = []
    for path in paths:
        machine = machine_of(path)
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            rows = {}
            if "hard_cases.jsonl" in names:
                for line in zf.read("hard_cases.jsonl").decode("utf-8").splitlines():
                    if line.strip():
                        row = json.loads(line)
                        rows[row.get("file")] = row
            for name in sorted(n for n in names if n.lower().endswith(".jpg")):
                data = zf.read(name)
                row = rows.get(name, {})
                cases.append({"machine": machine, "zip": os.path.basename(path), "file": name, "bytes": data,
                              "md5": hashlib.md5(data).hexdigest(), "t": row.get("t", 0.0),
                              "point": row.get("point"), "kind": row.get("kind", "?"), "src": row.get("src", ""),
                              "map": row.get("map", ""), "night": row.get("night")})
    return cases


def dedupe(cases):
    """Marks case["dup"] = None / "exact" / "near"; returns the unique ones in time order per machine."""
    seen_md5, kept = set(), []
    for c in sorted(cases, key=lambda c: (c["machine"], c["t"], c["file"])):
        c["img"] = cv2.imdecode(np.frombuffer(c["bytes"], np.uint8), cv2.IMREAD_COLOR)
        if c["md5"] in seen_md5:
            c["dup"] = "exact"
            continue
        seen_md5.add(c["md5"])
        if c["img"] is None or not c["point"]:
            c["dup"] = "unreadable"
            continue
        c["hash"] = dhash(c["img"])
        near = any(bin(c["hash"] ^ k["hash"]).count("1") <= DHASH_SAME
                   and math.dist(c["point"], k["point"]) <= DEDUPE_PX for k in kept[-50:])
        c["dup"] = "near" if near else None
        if not near:
            kept.append(c)
    return kept


def light_night(img):
    from lineage_auto.vision.name_reader import is_night_frame
    return bool(is_night_frame(img))


def stats(cases):
    out = {}
    for c in cases:
        m = out.setdefault(c["machine"], collections.Counter())
        m["cases"] += 1
        if c.get("dup"):
            m[f"dup_{c['dup']}"] += 1
            continue
        night = c["night"] if c["night"] is not None else light_night(c["img"])
        m["unique"] += 1
        m["night" if night else "day"] += 1
        m[f"src_{c['kind']}"] += 1
        m[f"map_{c['map'] or '?'}"] += 1
    return {k: dict(v) for k, v in out.items()}


def gap(box, pt):
    """px from the point to the box (0 inside)."""
    dx = max(box[0] - pt[0], 0, pt[0] - box[2])
    dy = max(box[1] - pt[1], 0, pt[1] - box[3])
    return math.hypot(dx, dy)


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def label_case(img, point, map_key, conf, keep_conf, boxes_fn=None):
    """(status, boxes, suggestions, hard_score): the hard monster's box + the frame's other model boxes."""
    if boxes_fn is None:
        from prelabel import yolox_boxes as boxes_fn  # tests/prelabel.py: class-0 boxes of the map's ONNX
    found = boxes_fn(img, map_key, conf)
    h, w = img.shape[:2]
    f = w / 1280.0
    near = sorted(found, key=lambda b: (gap(b, point), math.dist(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), point)))
    first = gap(near[0], point) if near else None
    # inside a box: that one (the nearest centre); just outside: only when no other box is about as close
    alone = len(near) < 2 or gap(near[1], point) > first + AUTO_ALONE_PX * f
    if near and (first == 0 or (first <= AUTO_GAP_PX * f and alone)):
        hard = near[0]
        status, hard_box, score = "auto", [int(v) for v in hard[:4]], hard[4]
    else:
        status, hard_box, score = "review", box_of(point, w, h), None
    others = [b for b in found if b[4] >= keep_conf and iou(b, hard_box) < 0.5]
    boxes = [[*hard_box, 0, None]] + [[*(int(v) for v in b[:4]), 0, None] for b in others]
    sugg = ([[*hard_box, 0, None, "cursor" if status == "review" else "yolox", score]]
            + [[*(int(v) for v in b[:4]), 0, None, "yolox", b[4]] for b in found
               if iou(b, hard_box) < 0.5])
    return status, boxes, sugg, score


def zone_of(map_key):
    cat = monsters.for_hunt_map(map_key)
    return (cat.real_maps[0] if getattr(cat, "real_maps", None) else getattr(cat, "zone_name", None)) or map_key


def reviewed_frames(map_key):
    """(folder, name, entry) of every reviewed frame (todo false, train split) of the records of this zone."""
    cat = monsters.for_hunt_map(map_key)
    names = set(getattr(cat, "real_maps", []) or []) | {getattr(cat, "zone_name", None), map_key}
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "records_game", "*", "labels.json"))):
        try:
            images = json.load(open(path, encoding="utf-8"))["images"]
        except (OSError, ValueError, KeyError):
            continue
        folder = os.path.dirname(path)
        for name, e in images.items():
            if (not e.get("todo", True) and e.get("split") == "train" and e.get("map") in names
                    and os.path.exists(os.path.join(folder, name))):
                out.append((folder, name, e))
    return out


def run(zips, out, map_key, conf=0.05, keep_conf=0.3, test_share=0.2, normal_share=0.15, dry_run=False,
        boxes_fn=None, seed=7):
    cases = read_zips(zips)
    unique = dedupe(cases)
    st = stats(cases)
    mine = [c for c in unique if c["map"] == map_key]
    zone = zone_of(map_key)
    report = {"zips": [os.path.basename(z) for z in zips], "map": map_key, "stats": st, "machines": {}}
    plan = []
    for machine in sorted({c["machine"] for c in mine}):
        rows = sorted((c for c in mine if c["machine"] == machine), key=lambda c: (c["t"], c["file"]))
        n_test = int(round(len(rows) * test_share))
        for i, c in enumerate(rows):
            c["split"] = "test" if i >= len(rows) - n_test else "train"
            status, boxes, sugg, score = label_case(c["img"], c["point"], map_key, conf, keep_conf, boxes_fn)
            if c["split"] == "test":
                status = "review"  # the fixed test set is reviewed by a person, never scored on the old model
            c.update(status=status, boxes=boxes, sugg=sugg, score=score)
            plan.append(c)
        mrep = collections.Counter((c["split"], c["status"]) for c in rows)
        report["machines"][machine] = {f"{s}_{st_}": n for (s, st_), n in mrep.items()}
    n_train = sum(1 for c in plan if c["split"] == "train")
    pool = reviewed_frames(map_key)
    random.Random(seed).shuffle(pool)
    normal = pool[:int(round(n_train * normal_share))]
    review = [c for c in plan if c["status"] == "review"]
    report["totals"] = {
        "unique_cases": len(unique), "for_map": len(plan), "train": n_train,
        "auto": sum(c["status"] == "auto" for c in plan), "review": len(review),
        "review_train": sum(c["split"] == "train" for c in review), "review_test": sum(c["split"] == "test" for c in review),
        "normal_frames": len(normal), "normal_pool": len(pool),
        "review_minutes": [round(len(review) * s / 60, 1) for s in REVIEW_SEC]}
    if not dry_run and plan:
        _write(out, plan, normal, zone, map_key)
        with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
    return report


def _write(out, plan, normal, zone, map_key):
    for machine in sorted({c["machine"] for c in plan}):
        folder = os.path.join(out, machine)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "labels.json")
        old = json.load(open(path, encoding="utf-8"))["images"] if os.path.exists(path) else {}
        images = {}
        for c in (c for c in plan if c["machine"] == machine):
            name = c["file"]
            with open(os.path.join(folder, name), "wb") as fh:
                fh.write(c["bytes"])
            if name in old and not old[name].get("todo", True):
                images[name] = old[name]  # reviewed by a person: never overwritten
                continue
            night = c["night"] if c["night"] is not None else light_night(c["img"])
            e = {"night": night, "map": zone, "ignore": [], "split": c["split"],
                 "hc": {"kind": c["kind"], "src": c["src"], "point": c["point"], "status": c["status"],
                        "score": c["score"], "zip": c["zip"]}}
            if c["status"] == "auto":
                e.update(boxes=c["boxes"], monster=[[(b[0] + b[2]) // 2, (b[1] + b[3]) // 2] for b in c["boxes"]],
                         todo=False)
            else:
                e.update(boxes=[], monster=[list(c["point"])], suggest=c["sugg"], todo=True)
            images[name] = e
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"_doc": f"PLAN 3.1 hard cases of {machine} ({map_key}); hc.status auto = model box around "
                               f"the cursor point, review = estimated box, label_tool --review",
                       "images": images}, fh, ensure_ascii=False, indent=1)
    folder = os.path.join(out, "normal")
    os.makedirs(folder, exist_ok=True)
    images = {}
    for src, name, e in normal:
        new = f"{os.path.basename(src)}_{name}"
        shutil.copyfile(os.path.join(src, name), os.path.join(folder, new))
        images[new] = dict(e, split="train")
    with open(os.path.join(folder, "labels.json"), "w", encoding="utf-8") as fh:
        json.dump({"_doc": "PLAN 3.1: reviewed frames of the zone's records, the non-hard share", "images": images},
                  fh, ensure_ascii=False, indent=1)


def print_report(rep):
    print(f"zips: {', '.join(rep['zips']) or '(none)'}   map: {rep['map']}")
    for machine, s in sorted(rep["stats"].items()):
        srcs = {k[4:]: v for k, v in s.items() if k.startswith("src_")}
        maps = {k[4:]: v for k, v in s.items() if k.startswith("map_")}
        print(f"  {machine}: {s.get('cases', 0)} cases, {s.get('unique', 0)} unique (exact dup "
              f"{s.get('dup_exact', 0)}, near dup {s.get('dup_near', 0)}, unreadable {s.get('dup_unreadable', 0)}); "
              f"day {s.get('day', 0)} / night {s.get('night', 0)}; source {srcs}; ground {maps}")
    for machine, s in sorted(rep["machines"].items()):
        print(f"  {machine} labels: {s}")
    t = rep.get("totals", {})
    if t:
        print(f"  total for {rep['map']}: {t['for_map']} cases (train {t['train']}): auto {t['auto']}, to review "
              f"{t['review']} (train {t['review_train']}, test {t['review_test']}) ~ {t['review_minutes'][0]}-"
              f"{t['review_minutes'][1]} min; normal frames {t['normal_frames']} (of {t['normal_pool']} reviewed)")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--zips", default=os.path.join(ROOT, "records_game", "hard_cases"))
    p.add_argument("--out", default=None)
    p.add_argument("--map", default="fallen_blessed")
    p.add_argument("--conf", type=float, default=0.05)
    p.add_argument("--keep-conf", type=float, default=0.3)
    p.add_argument("--test-share", type=float, default=0.2)
    p.add_argument("--normal-share", type=float, default=0.15)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    zips = sorted(glob.glob(os.path.join(a.zips, "*.zip"))) if os.path.isdir(a.zips) else [a.zips]
    if not zips:
        print(f"no zip in {a.zips} - put the game PCs' exports there as <machine>_<date>.zip")
        return 1
    rep = run(zips, a.out or os.path.join(a.zips, "work"), a.map, a.conf, a.keep_conf, a.test_share,
              a.normal_share, a.dry_run)
    print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
