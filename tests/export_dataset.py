"""Export labelled recordings to a YOLOX training set (docs/TRAINING.md, docs/ADD_NEW_MAP.md).

Usage:  python tests/export_dataset.py <out_dir> <record folder> [more folders ...] [--val-every 5] [--keep-hud]
                                       [--map ZONE] [--classes model|group|species|single]
                                       [--split train|test] [--use-suggestions]

Reads <folder>/labels.json (tests/label_tool.py), takes the finished frames only
(todo=false) and their "boxes", and writes:
  out_dir/train2017/*.jpg, out_dir/val2017/*.jpg          images (HUD blanked like the bot does)
  out_dir/annotations/instances_{train,val}2017.json     COCO (YOLOX's own format); each image has "map", "night"
  out_dir/labels/{train,val}2017/*.txt                   YOLO txt (class cx cy w h, 0-1)
  out_dir/classes.txt                                    class names, line n = YOLO id n
  out_dir/manifest.json                                  per image: zone, night, source recording, split
--map ZONE (real_map or catalog key): only frames of that zone. Without it every zone goes into one
  dataset (each image keeps its zone), for a shared model or to split per zone later.
--classes:
  model   (default) the bot's classes: 0 monster, 1 figure (player/NPC), 2 die (corpse)
  group   every monster of a zone -> the zone's "group" (e.g. "orc"), plus corpse / player / npc
  species every catalog class (orc, orc_axe, ...) kept apart, plus corpse / player / npc
  corpse  TWO classes (PLAN 0.30 / 2, orc_v2): 0 = the zone's "group" (every monster species), 1 = corpse
          (orc lying / falling, label_tool --corpse); player / npc boxes are left out
  single  ONE class: every monster of the zone -> the zone's "group" ("orc"); corpse / player / npc boxes are
          dropped (they are background for a one-class model)
--split train|test: only frames tests/prelabel.py picked for that split ("split" in labels.json).
--use-suggestions: PIPELINE TRIAL ONLY - picked frames still todo count as finished with every prelabel
  suggestion accepted unseen (noisy boxes). Never use it for a model that goes to the game PC.
"""
import argparse
import json
import os
import sys

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lineage_auto import monsters  # noqa: E402
from lineage_auto.vision.yolox_mobs import CLASS_NAMES, _blank_play_hud  # noqa: E402

MODEL_LABEL = {0: "monster", 1: "player", 2: "corpse"}  # box without a label (older label_tool)


def box_label(box):
    return box[5] if len(box) > 5 else MODEL_LABEL[box[4] if len(box) > 4 else 0]


def category_of(box, mode, catalog):
    """Class name of one box in the chosen mode (None = not exported)."""
    if mode == "corpse":
        label = box_label(box)
        if label == "corpse":
            return "corpse"
        if label in monsters.COMMON_CLASSES or label == "player":
            return None
        return catalog.group if catalog is not None else "monster"
    if mode == "single":
        label = box_label(box)
        if label in monsters.COMMON_CLASSES or label == "player":
            return None
        return catalog.group if catalog is not None else "monster"
    if mode == "model":
        return CLASS_NAMES[box[4] if len(box) > 4 else 0]
    label = box_label(box)
    if label in monsters.COMMON_CLASSES:
        return label
    if mode == "group":
        return catalog.group if catalog is not None else "monster"
    return label


def export(out_dir, folders, val_every=5, keep_hud=False, zone=None, mode="model", split_only=None,
           use_suggestions=False):
    only = monsters.for_real_map(zone) if zone else None
    only_map = only.real_map if only else zone
    only_maps = {*only.real_maps, only.key, only.zone_name} if only else {zone}
    items = []  # (folder, name, lab, zone)
    for folder in folders:
        labels = json.load(open(os.path.join(folder, "labels.json"), encoding="utf-8"))["images"]
        for name, lab in sorted(labels.items()):
            if split_only and lab.get("split") != split_only:
                continue
            if use_suggestions and lab.get("split") and lab.get("todo", True):
                lab = dict(lab, boxes=list(lab.get("boxes", [])) + [s[:4] + [s[4]] + ([s[5]] if s[5] else [])
                                                                    for s in lab.get("suggest", [])], todo=False)
            if lab.get("todo", True):
                continue
            where = lab.get("map", "")
            if only_map and where not in only_maps:
                continue
            items.append((folder, name, lab, where))

    if mode == "model":
        names = list(CLASS_NAMES)
    elif mode == "corpse":
        groups = [monsters.for_real_map(i[3]).group if monsters.for_real_map(i[3]) else "monster" for i in items]
        names = list(dict.fromkeys(groups))[:1] or ["monster"]
        names.append("corpse")
    elif mode == "single":
        names = list(dict.fromkeys((monsters.for_real_map(i[3]).group if monsters.for_real_map(i[3]) else "monster")
                                   for i in items)) or ["monster"]
    else:
        names = []
        for where in dict.fromkeys(i[3] for i in items):  # catalog order first, zone by zone
            catalog = monsters.for_real_map(where)
            if catalog is not None:
                wanted = [catalog.group] if mode == "group" else catalog.label_classes()
                for n in wanted + list(monsters.COMMON_CLASSES):
                    if n not in names:
                        names.append(n)
        for folder, _name, lab, where in items:  # labels outside any catalog go last
            for box in lab.get("boxes", []):
                n = category_of(box, mode, monsters.for_real_map(where))
                if n not in names:
                    names.append(n)

    coco = {split: {"images": [], "annotations": [],
                    "categories": [{"id": i + 1, "name": n} for i, n in enumerate(names)]}
            for split in ("train", "val")}
    manifest = {}
    ann_id, n = 0, 0
    for folder, name, lab, where in items:
        img = cv2.imread(os.path.join(folder, name))
        if img is None:
            continue
        catalog = monsters.for_real_map(where)
        n += 1
        split = "val" if n % val_every == 0 else "train"
        h, w = img.shape[:2]
        if not keep_hud:
            img = _blank_play_hud(img)  # the detector never sees the HUD, so training must not either
        prefix = os.path.basename(os.path.normpath(folder))
        file_name = f"{prefix}_{os.path.splitext(name)[0]}.jpg"
        for sub in (f"{split}2017", os.path.join("labels", f"{split}2017"), "annotations"):
            os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
        cv2.imwrite(os.path.join(out_dir, f"{split}2017", file_name), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        image_id = len(coco["train"]["images"]) + len(coco["val"]["images"]) + 1
        night = bool(lab.get("night"))
        coco[split]["images"].append({"id": image_id, "file_name": file_name, "width": w, "height": h,
                                      "map": where, "night": night})
        manifest[file_name] = {"map": where, "night": night, "record": prefix, "frame": name, "split": split}
        lines = []
        for box in lab.get("boxes", []):
            x0, y0, x1, y1 = box[:4]
            category = category_of(box, mode, catalog)
            if category is None:
                continue
            # corpse mode: every monster species of every zone is class 0 (the group name only labels it)
            class_id = (1 if category == "corpse" else 0) if mode == "corpse" else names.index(category)
            ann_id += 1
            bw, bh = x1 - x0, y1 - y0
            coco[split]["annotations"].append({
                "id": ann_id, "image_id": image_id, "category_id": class_id + 1,
                "bbox": [x0, y0, bw, bh], "area": bw * bh, "iscrowd": 0,
            })
            lines.append(f"{class_id} {(x0 + bw / 2) / w:.6f} {(y0 + bh / 2) / h:.6f} {bw / w:.6f} {bh / h:.6f}")
        txt = os.path.join(out_dir, "labels", f"{split}2017", os.path.splitext(file_name)[0] + ".txt")
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + ("\n" if lines else ""))
    os.makedirs(os.path.join(out_dir, "annotations"), exist_ok=True)
    for split, data in coco.items():
        with open(os.path.join(out_dir, "annotations", f"instances_{split}2017.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh)  # ASCII: pycocotools opens it with the Windows codepage
    with open(os.path.join(out_dir, "classes.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(names) + "\n")
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"classes": names, "mode": mode, "zone": only_map, "images": manifest}, fh,
                  ensure_ascii=False, indent=1)
    counts = {s: (len(d["images"]), len(d["annotations"])) for s, d in coco.items()}
    print(f"exported to {out_dir} ({mode}: {', '.join(names)}): train {counts['train'][0]} images / "
          f"{counts['train'][1]} boxes, val {counts['val'][0]} images / {counts['val'][1]} boxes")
    return counts


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out_dir")
    parser.add_argument("folders", nargs="+")
    parser.add_argument("--val-every", type=int, default=5, help="every Nth finished frame goes to val")
    parser.add_argument("--keep-hud", action="store_true", help="do not blank the HUD (not what the bot sees)")
    parser.add_argument("--map", help="only this zone (real_map or catalog key)")
    parser.add_argument("--classes", choices=("model", "group", "species", "single", "corpse"), default="model")
    parser.add_argument("--split", choices=("train", "test"), help="only frames picked for this split")
    parser.add_argument("--use-suggestions", action="store_true", help="pipeline trial only (see above)")
    args = parser.parse_args()
    export(args.out_dir, args.folders, args.val_every, args.keep_hud, args.map, args.classes, args.split,
           args.use_suggestions)


if __name__ == "__main__":
    main()
