"""Pick the frames worth labelling and pre-draw box suggestions (PLAN 0.20, docs/TRAINING.md).

Usage:  python tests/prelabel.py --train <record>[:N] [--train ...] --test <record>[:N] [--test ...]
                                 [--n-train 200] [--n-test 50] [--gap 4] [--map-model KEY] [--yolox-conf C]
                                 [--no-yolox] [--dry-run]
<record>:N = pick N frames from that recording. A recording given to both --train and --test (PLAN 0.22: the
night test set) is split in time: test frames from its last 30 %, train frames end 30 s before that.
Night frames: the green / dark limits of the glow boxes follow the frame brightness.

Needs <record>/labels.json from tests/analyze_records.py (cursor points + monster class read from the name).

1. Suggestions, per frame ("suggest": [[x0, y0, x1, y1, 0, label|null, source, score], ...]):
   - "glow":   the zone's monsters glow yellow-green; a green blob standing on sand/dirt (its ring is not
               green, not dark leaf shadow), upright and solid, of monster size. Finds the orcs on open ground;
               orcs in grass / bushes are missed (the reviewer adds them).
   - "cursor": the attack-cursor point. Inside a glow box -> that box gets the class read from the name;
               else a box under the name over the monster, else a box centred on the point.
   - "yolox":  the current model (--map-model, default dragon_valley) at low conf, kept only when the box is
               green enough (the old models also fire on players).
2. Selection: consecutive frames are near copies, so frames of one recording are taken at least --gap seconds
   apart and must differ (camera moved = 8x6 thumbnail, or a monster box moved / appeared). Best first: more monsters, rarer species (궁수/도끼병),
   a cursor monster that no glow box covers (in grass / covered = the hard cases).
   --train recordings fill "split": "train", --test recordings "split": "test" (keep the test set from another
   day / window size: it is never trained on).
Frames with hand work (boxes) keep them; suggestions overlapping a box are not added.
Then review: python tests/label_tool.py <record> --review
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from lineage_auto import monsters  # noqa: E402

BASE_W = 1187  # sizes below are 1187-wide pixels (game PC 23/11), scaled with the frame width
BOX_W, BOX_H = 48, 76  # an orc standing (label_tool default 44x72 + margin)
GREEN_LO, GREEN_HI = (26, 80, 80), (52, 255, 255)  # HSV of the "polluted" glow / green skin (daylight)
DAY_BRIGHTNESS = 95  # mean BGR of a 오크의 땅 day frame; night frames (43-61) get the value limits scaled down
DARK_V = 75  # ring pixels darker than this (daylight) are leaf shadow
RING_GREEN_MAX = 0.3
RING_DARK_MAX = 0.2
RARE = {"orc_archer": 2.0, "orc_axe": 2.0, "orc": 1.0}
YOLOX_CONF = 0.03
YOLOX_GREEN_MIN = 0.10
THUMB = (8, 6)
THUMB_MIN_DIFF = 6.0


def play_mask(shape):
    """1 where the game world is (not HUD / chat / minimap / skill icons)."""
    h, w = shape[:2]
    m = np.ones((h, w), np.uint8)
    m[int(0.66 * h):, :] = 0
    m[:int(0.21 * h), :int(0.18 * w)] = 0
    m[:, int(0.94 * w):] = 0
    return m


def scale_of(frame):
    return frame.shape[1] / BASE_W


def box_at(cx, cy, f):
    w, h = BOX_W * f, BOX_H * f
    return [int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2)]


def light_of(frame):
    """1.0 by day, down to 0.4 at night: the HSV value limits follow the frame brightness (PLAN 0.22)."""
    return min(1.0, max(0.4, float(frame[::4, ::4].mean()) / DAY_BRIGHTNESS))


def green_range(frame):
    k = light_of(frame)
    return (GREEN_LO[0], round(GREEN_LO[1] * (0.5 + 0.5 * k)), round(GREEN_LO[2] * k)), GREEN_HI


def glow_boxes(frame):
    """[[x0, y0, x1, y1, score]] green blobs standing on open ground (see the module doc)."""
    f = scale_of(frame)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, *green_range(frame)) * play_mask(frame.shape)
    dark_v = DARK_V * light_of(frame)
    blob = cv2.morphologyEx(green, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    blob = cv2.morphologyEx(blob, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, cents = cv2.connectedComponentsWithStats(blob)
    out = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in stats[i])
        # shortcut: orcs side by side make one wide blob and are skipped (splitting it boxed straw and bushes
        # too); the reviewer clicks them in. Revisit with a trained model as the suggestion source.
        if not (10 * f <= w <= 80 * f and 15 * f <= h <= 100 * f and a >= 80 * f * f):
            continue
        if h < 1.1 * w or a / float(w * h) < 0.35:  # orcs stand upright and are solid; leaves are not
            continue
        ys, xs = slice(max(0, y - 20), y + h + 20), slice(max(0, x - 20), x + w + 20)
        comp = (labels[ys, xs] == i).astype(np.uint8)
        ring = (cv2.dilate(comp, np.ones((25, 25), np.uint8)) - comp) > 0
        if not ring.any():
            continue
        ring_green = float((green[ys, xs][ring] > 0).mean())
        ring_dark = float((hsv[ys, xs, 2][ring] < dark_v).mean())
        if ring_green > RING_GREEN_MAX or ring_dark > RING_DARK_MAX:
            continue
        box = box_at(*cents[i], f) + [round(1 - ring_green, 2)]
        if all(iou(box, o) < 0.3 for o in out):  # two blobs of one orc (body + weapon)
            out.append(box)
    return out


def green_share(frame, box):
    x0, y0, x1, y1 = (max(0, int(v)) for v in box[:4])
    roi = frame[y0:y1, x0:x1]
    if roi.size == 0:
        return 0.0
    return float(cv2.inRange(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV), *green_range(frame)).mean() / 255)


def yolox_boxes(frame, map_key, conf=YOLOX_CONF):
    """[[x0, y0, x1, y1, score]] class-0 boxes of a shipped/trained ONNX at a low threshold."""
    from lineage_auto import hunt_maps
    from lineage_auto.vision import yolox_mobs as ym
    hunt = hunt_maps.get(map_key)
    canvas, scale, _dx, _dy = ym.letterbox(ym._blank_play_hud(frame))
    if hunt.channels == "rgb":
        canvas = canvas[:, :, ::-1]
    blob = np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32)
    pred = ym._infer_onnx(blob, map_key)
    rows = pred.reshape(-1, pred.shape[-1])
    scores = rows[:, 4] * rows[:, 5]
    keep = scores >= conf
    rows, scores = rows[keep], scores[keep]
    if not len(rows):
        return []
    rects = [[float(r[0] - r[2] / 2), float(r[1] - r[3] / 2), float(r[2]), float(r[3])] for r in rows]
    idx = cv2.dnn.NMSBoxes(rects, scores.tolist(), conf, 0.45)
    out = []
    for i in np.array(idx).reshape(-1):
        x, y, w, h = (v / scale for v in rects[i])
        out.append([round(x), round(y), round(x + w), round(y + h), round(float(scores[i]), 3)])
    return out


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def contains(box, x, y, pad=0):
    return box[0] - pad <= x <= box[2] + pad and box[1] - pad <= y <= box[3] + pad


def suggest(frame, entry, reader=None, yolox_map=None, yolox_conf=YOLOX_CONF):
    """Suggestions for one frame + the "hard" cursor points (no glow box on them)."""
    f = scale_of(frame)
    glow = glow_boxes(frame)
    out = [[*g[:4], 0, None, "glow", g[4]] for g in glow]
    named = {(p[0], p[1]): p[2] for p in entry.get("monster_names", [])}
    hard = 0
    for x, y in entry.get("monster", []):
        label = named.get((x, y))
        hit = next((s for s in out if contains(s, x, y, pad=10 * f)), None)
        if hit is not None:
            hit[5], hit[6], hit[7] = label, "cursor+glow", 1.0
            continue
        hard += 1
        name = reader.read_near(frame, [x, y]) if reader is not None else None
        if name is not None and abs((name["box"][0] + name["box"][2]) / 2 - x) < 60 * f:
            nx = (name["box"][0] + name["box"][2]) / 2
            top = name["box"][3] + 4 * f
            box = [int(nx - BOX_W * f / 2), int(top), int(nx + BOX_W * f / 2), int(top + BOX_H * f)]
            if not contains(box, x, y, pad=8 * f):
                box = box_at(x, y, f)
        else:
            box = box_at(x, y, f)
        out.append([*box, 0, label, "cursor", 1.0])
    if yolox_map:
        for b in yolox_boxes(frame, yolox_map, yolox_conf):
            if green_share(frame, b) >= YOLOX_GREEN_MIN and all(iou(b, s) < 0.3 for s in out):
                out.append([*b[:4], 0, None, "yolox", b[4]])
    boxes = entry.get("boxes", [])
    out = [s for s in out if all(iou(s, b) < 0.3 for b in boxes)]
    return out, hard


def thumb(frame):
    small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), THUMB, interpolation=cv2.INTER_AREA)
    return small.astype(np.float32)


def frame_score(sugg, hard):
    """Cursor monsters are sure, glow / yolox boxes only likely: a frame full of guesses is not worth more."""
    labels = [s[5] for s in sugg if s[5]]
    sure = sum(1 for s in sugg if s[6].startswith("cursor"))
    guesses = min(4, len(sugg) - sure)
    return 2 * sure + 0.5 * guesses + sum(RARE.get(lab, 0) for lab in labels) + 1.5 * hard


def same_scene(a, b, move_px=25):
    """Near copy: the camera did not move (thumbnail) and every monster box is still where it was."""
    if float(np.abs(a["thumb"] - b["thumb"]).mean()) >= THUMB_MIN_DIFF or len(a["sugg"]) != len(b["sugg"]):
        return False
    centre = [((s[0] + s[2]) / 2, (s[1] + s[3]) / 2) for s in b["sugg"]]
    return all(any(abs((s[0] + s[2]) / 2 - x) + abs((s[1] + s[3]) / 2 - y) < move_px for x, y in centre)
               for s in a["sugg"])


def select(cands, n, gap):
    """Greedy best-first: at least ``gap`` s from every picked frame of the same recording, and different."""
    picked = []
    for c in sorted(cands, key=lambda c: -c["score"]):
        if len(picked) >= n:
            break
        if c["score"] <= 0:
            break  # nothing to label on it
        same = [p for p in picked if p["record"] == c["record"]]
        if any(abs(p["t"] - c["t"]) < gap for p in same):
            continue
        if any(same_scene(p, c) for p in same):
            continue
        picked.append(c)
    return picked


def load_record(folder):
    path = os.path.join(folder, "labels.json")
    if not os.path.exists(path):
        sys.exit(f"{path} missing: run tests/analyze_records.py on {folder} first")
    data = json.load(open(path, encoding="utf-8"))
    times = {}
    frames = os.path.join(folder, "frames.jsonl")
    if os.path.exists(frames):
        with open(frames, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    times[row["file"]] = row.get("t", 0.0)
    return path, data, times


TEST_TAIL = 0.3  # a recording in both sets: its last 30 % gives the test frames
HOLDOUT_GAP = 30.0  # s between any train frame and any test frame of one recording


def parse_record(arg):
    """"folder[:N]" -> (folder, N or None); N = frames to pick from that recording."""
    head, _sep, tail = arg.rpartition(":")
    if head and tail.isdigit() and len(head) > 1:  # "C:" alone is a drive letter
        return head, int(tail)
    return arg, None


def time_window(folder, split, train_dirs, test_dirs, times):
    """(t_min, t_max) allowed for this split; only limits a recording named in both --train and --test."""
    if folder not in train_dirs or folder not in test_dirs or not times:
        return None, None
    cut = max(times.values()) * (1 - TEST_TAIL)
    return (None, cut - HOLDOUT_GAP) if split == "train" else (cut, None)


def run(train, test, n_train=200, n_test=50, gap=4.0, yolox_map="dragon_valley", dry_run=False,
        yolox_conf=YOLOX_CONF):
    """train / test: ["folder[:N]", ...]. Recordings without N share what is left of the set's n by size."""
    from lineage_auto.vision.name_reader import NameReader
    train_specs = [parse_record(a) for a in train]
    test_specs = [parse_record(a) for a in test]
    train_dirs, test_dirs = [f for f, _ in train_specs], [f for f, _ in test_specs]
    summary, stores = {}, {}
    for split, specs, n in (("train", train_specs, n_train), ("test", test_specs, n_test)):
        cands = {}
        for folder, _quota in specs:
            if folder not in stores:
                stores[folder] = load_record(folder)
            _path, data, times = stores[folder]
            images = data["images"]
            zone = next((v.get("map") for v in images.values() if v.get("map")), None)
            catalog = monsters.for_real_map(zone)
            reader = NameReader(catalog) if catalog is not None else None
            t_min, t_max = time_window(folder, split, train_dirs, test_dirs, times)
            mine = []
            for name, entry in sorted(images.items()):
                t = times.get(name, 0.0)
                if (t_min is not None and t < t_min) or (t_max is not None and t > t_max):
                    continue
                frame = cv2.imread(os.path.join(folder, name))
                if frame is None:
                    continue
                sugg, hard = suggest(frame, entry, reader, yolox_map, yolox_conf)
                mine.append({"record": folder, "name": name, "t": t, "sugg": sugg, "hard": hard,
                             "night": bool(light_of(frame) < 0.67), "score": frame_score(sugg, hard),
                             "thumb": thumb(frame)})
            cands[folder] = mine
        left = max(0, n - sum(q for _f, q in specs if q))
        free = sum(len(cands[f]) for f, q in specs if not q)
        picked = []
        for folder, quota in specs:
            want = quota if quota else left * len(cands[folder]) // max(1, free)
            picked += select(cands[folder], want, gap)
        chosen = {(c["record"], c["name"]) for c in picked}
        for folder, _quota in specs:
            for name, entry in stores[folder][1]["images"].items():
                if (folder, name) not in chosen and entry.get("split") == split and entry.get("todo", True):
                    entry.pop("split", None)  # re-run with other settings: drop the old pick
                    entry.pop("suggest", None)
        for c in picked:
            entry = stores[c["record"]][1]["images"][c["name"]]
            entry["split"] = split
            entry["suggest"] = c["sugg"]
        sources, species = {}, {}
        for c in picked:
            for sg in c["sugg"]:
                sources[sg[6]] = sources.get(sg[6], 0) + 1
                if sg[5]:
                    species[sg[5]] = species.get(sg[5], 0) + 1
        summary[split] = {
            "frames": len(picked), "of": sum(len(v) for v in cands.values()),
            "suggestions": sum(len(c["sugg"]) for c in picked), "night": sum(c["night"] for c in picked),
            "hard_points": sum(c["hard"] for c in picked), "sources": sources, "species": species,
            "records": {os.path.basename(os.path.normpath(f)): [sum(c["record"] == f for c in picked),
                                                                sum(len(c["sugg"]) for c in picked if c["record"] == f)]
                        for f, _q in specs},
        }
        sm = summary[split]
        print(f"{split}: {sm['frames']}/{sm['of']} frames ({sm['night']} night), {sm['suggestions']} suggestions "
              f"({sm['suggestions'] / max(1, sm['frames']):.1f}/frame) {sm['sources']}, "
              f"hard cursor points {sm['hard_points']}, species {sm['species']}, "
              f"per record [frames, suggestions] {sm['records']}")
    if not dry_run:
        for path, data, _times in stores.values():
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
    return summary


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--train", action="append", default=[], help="recording for training (repeat)")
    parser.add_argument("--test", action="append", default=[], help="recording kept for measuring (repeat)")
    parser.add_argument("--n-train", type=int, default=200)
    parser.add_argument("--n-test", type=int, default=50)
    parser.add_argument("--gap", type=float, default=4.0, help="seconds between two picked frames of a recording")
    parser.add_argument("--map-model", default="dragon_valley", help="hunt map whose ONNX adds low-conf boxes")
    parser.add_argument("--yolox-conf", type=float, default=YOLOX_CONF,
                        help="threshold of those boxes (0.03 for an old model; ~0.15 for the orc trial model)")
    parser.add_argument("--no-yolox", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="print only, do not write labels.json")
    args = parser.parse_args()
    if not args.train and not args.test:
        sys.exit(__doc__)
    run(args.train, args.test, args.n_train, args.n_test, args.gap, None if args.no_yolox else args.map_model,
        args.dry_run, args.yolox_conf)


if __name__ == "__main__":
    main()
