"""PLAN 0.46 / 6c: does a NEW model beat the one in use? Never bless a model by feeling.

Usage: python train/compare_models.py <old.onnx> <new.onnx> [--config <game PC config>] [--map blessed_orc]
       python train/compare_models.py <old.onnx> <new.onnx> --records records_game/20261125_092741_hunt

Fixed test set: tests/data/monster_labels.json over docs/game_reference (hand labels), plus the hand-labelled
frames of the recordings given with --records. Hard-case pictures that were used for training must NEVER be
in it - that is why the set is named here and not discovered.

It prints recall over the whole screen, recall within 150 px of the character (what PLAN 0.46 is about),
false positives per frame and ms per detect, and recommends the swap ONLY when the near recall goes up while
precision does not fall (and ms does not grow more than MS_TOLERANCE).
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from lineage_auto import hunt_maps  # noqa: E402
from lineage_auto.vision import yolox_mobs  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tests"))
import eval_detection  # noqa: E402
import eval_near_recall as near  # noqa: E402

MS_TOLERANCE = 1.2  # a new model may cost 20% more per detect, not more


def _as_model(map_key, path):
    """Put ``path`` where yolox_mobs looks for this map's model and clear the session cache."""
    target = hunt_maps.onnx_path(hunt_maps.get(map_key).key)
    backup = None
    if os.path.exists(target):
        backup = target + ".cmp_backup"
        shutil.move(target, backup)
    shutil.copyfile(path, target)
    yolox_mobs._SESSIONS.clear()
    return target, backup


def _restore(target, backup):
    if os.path.exists(target):
        os.remove(target)
    if backup:
        shutil.move(backup, target)
    yolox_mobs._SESSIONS.clear()


def measure(map_key, model, args):
    """(whole-screen recall %, near recall %, fp/frame, ms) of one model on the fixed test set."""
    target, backup = _as_model(map_key, model)
    try:
        labels = json.load(open(eval_detection.LABELS, encoding="utf-8"))["images"]
        stats, fp, ms = eval_detection.evaluate(map_key, labels, conf=args.conf or None, size=args.size)
        found = sum(v[0] for v in stats.values())
        total = sum(v[1] for v in stats.values())
        table, totals = near.Table(), near.fresh_totals(args)
        for rec in args.records:
            near.run(rec, table, totals, args, source="labels")
        near_pct = (100.0 * totals["near_full"] / totals["near_total"]) if totals["near_total"] else None
        fp_per_frame = fp / max(1, len(labels))
        return {"recall": 100.0 * found / total if total else 0.0, "near": near_pct,
                "fp": fp_per_frame, "ms": ms, "near_n": totals["near_total"]}
    finally:
        _restore(target, backup)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--map", default="blessed_orc")
    ap.add_argument("--config", help="game PC lineage_auto_config.json (takes scan.input_size)")
    ap.add_argument("--conf", type=float, default=0.0)
    ap.add_argument("--size", type=int, default=0)
    ap.add_argument("--near-conf", type=float, default=0.1)
    ap.add_argument("--crop-sizes", default="320")
    ap.add_argument("--max-probe", type=int, default=2)
    ap.add_argument("--hover-slack", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--records", nargs="*", default=["records_game/20261125_092741_hunt"])
    args = ap.parse_args()
    args.crop_sizes = [int(s) for s in args.crop_sizes.split(",") if s]
    if not args.size:
        cfg = json.load(open(args.config, encoding="utf-8")) if args.config else None
        scan = ((cfg or {}).get("accounts") or [{}])[0].get("scan") or {} if cfg else {}
        args.size = int(scan.get("input_size") or 416)
    args.records = [r for r in args.records if os.path.isdir(r)]

    rows = {}
    for name, model in (("old", args.old), ("new", args.new)):
        if not os.path.isfile(model):
            sys.exit(f"model not found: {model}")
        rows[name] = measure(args.map, model, args)
        r = rows[name]
        near_txt = f"{r['near']:.0f}% ({r['near_n']} labels)" if r["near"] is not None else "no near labels"
        print(f"{name:4s} {os.path.basename(model):40s} recall {r['recall']:.0f}%  near {near_txt}  "
              f"fp {r['fp']:.2f}/frame  {r['ms']:.0f} ms")

    old, new = rows["old"], rows["new"]
    print(verdict(old, new))


def verdict(old, new):
    """The PLAN 0.39 / 0.46 rule, as text: swap only on better near recall with no loss of precision."""
    if old["near"] is None or new["near"] is None:
        return "GIỮ model cũ: bộ test không có nhãn nào trong 150 px -> không đo được recall gần"
    if new["near"] <= old["near"]:
        return (f"GIỮ model cũ: recall gần {new['near']:.0f}% <= {old['near']:.0f}%")
    if new["fp"] > old["fp"]:
        return (f"GIỮ model cũ: recall gần tăng ({old['near']:.0f}% -> {new['near']:.0f}%) nhưng box sai "
                f"tăng {old['fp']:.2f} -> {new['fp']:.2f}/frame")
    if new["ms"] > old["ms"] * MS_TOLERANCE:
        return (f"GIỮ model cũ: nhanh hơn không nổi - {new['ms']:.0f} ms > {old['ms']:.0f} ms x "
                f"{MS_TOLERANCE}")
    return (f"ĐỀ XUẤT THAY: recall gần {old['near']:.0f}% -> {new['near']:.0f}%, box sai "
            f"{old['fp']:.2f} -> {new['fp']:.2f}/frame, {old['ms']:.0f} -> {new['ms']:.0f} ms")


if __name__ == "__main__":
    main()
