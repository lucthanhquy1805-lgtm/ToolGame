"""PLAN 3.1 steps 1-2 (train/hard_cases_prep.py), offline with a stub detector: duplicates, auto / review labels, the
fixed test split, a re-run keeps what a person reviewed.
Run: python tests/test_hard_cases_prep.py
"""
import json
import os
import shutil
import sys
import tempfile

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "train"))

import hard_cases_prep as hp  # noqa: E402
from lineage_auto.runtime.hard_cases import HC_BOX_H, HC_BOX_W, HardCases, export_zip  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok", msg)


def scene(seed):
    rng = np.random.default_rng(seed)
    return cv2.GaussianBlur(rng.integers(0, 255, (960, 1280, 3), dtype=np.uint8), (15, 15), 5)


# stub model: boxes per scene seed (read back from the picture's top-left pixel)
BOXES = {
    1: [[600, 300, 650, 390, 0.12]],  # point (620, 350) inside -> auto
    2: [[600, 300, 650, 390, 0.40]],  # point (665, 350): 15 px outside, alone -> auto
    3: [[600, 300, 650, 390, 0.40], [680, 300, 730, 390, 0.40]],  # point (665, 350): two boxes 15 px off -> review
    4: [],  # nothing -> review, estimated box
    5: [[100, 100, 150, 190, 0.9]],  # test split
}


def stub(img, _map, _conf):
    return BOXES.get(int(round(img[:16, :16].mean() / 40)), [])


def make_zip(folder, machine, cases):
    hc = HardCases(root=os.path.join(folder, machine))
    for t, seed, point in cases:
        img = scene(seed)
        img[:16, :16] = seed * 40  # the stub's key (a block: JPEG keeps its mean)
        hc.clock = lambda t=t: t
        assert hc.save(img, point, kind="probe", src="probe", map_key="fallen_blessed")
    path, _info = export_zip(os.path.join(folder, machine), os.path.join(folder, "zips", f"{machine}_20261130.zip"))
    return path


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, "zips"))
        z = make_zip(tmp, "PC-A", [(10, 1, (620, 350)), (20, 2, (665, 350)), (30, 3, (665, 350)),
                                    (40, 4, (300, 500)), (50, 5, (125, 140))])
        shutil.copyfile(z, os.path.join(tmp, "zips", "PC-A_20261201.zip"))  # exported again: exact duplicates
        out = os.path.join(tmp, "work")
        rep = hp.run(sorted(os.path.join(tmp, "zips", f) for f in os.listdir(os.path.join(tmp, "zips"))), out,
                     "fallen_blessed", boxes_fn=stub, test_share=0.2)
        hp.print_report(rep)
        st = rep["stats"]["PC-A"]
        check(st["cases"] == 10 and st["unique"] == 5 and st["dup_exact"] == 5, f"10 cases, 5 exact duplicates {st}")
        images = json.load(open(os.path.join(out, "PC-A", "labels.json"), encoding="utf-8"))["images"]
        by_point = {tuple(e["hc"]["point"]): e for e in images.values()}
        e1, e4, e5 = by_point[(620, 350)], by_point[(300, 500)], by_point[(125, 140)]
        check(e1["hc"]["status"] == "auto" and not e1["todo"] and e1["boxes"][0][:4] == [600, 300, 650, 390],
              "point inside a 0.12 box -> auto, the model's box (no review)")
        check(e4["hc"]["status"] == "review" and e4["todo"] and e4["suggest"][0][6] == "cursor"
              and e4["suggest"][0][2] - e4["suggest"][0][0] == HC_BOX_W
              and e4["suggest"][0][3] - e4["suggest"][0][1] == HC_BOX_H,
              "no box -> review with the estimated 57x95 box as the suggestion")
        check(e5["split"] == "test" and e5["hc"]["status"] == "review" and e5["todo"],
              "the last 20 % in time is the fixed TEST split and always reviewed (even with a 0.9 box)")
        lab = [hp.label_case(np.zeros((960, 1280, 3), np.uint8), (665, 350), "x", 0.05, 0.3,
                             boxes_fn=lambda *a, b=b: b)[0] for b in (BOXES[2], BOXES[3])]
        check(lab == ["auto", "review"], f"15 px outside one box -> auto; between two boxes -> review ({lab})")
        # a person reviews the test frame, then the prep runs again with a new zip
        name5 = next(n for n, e in images.items() if e is e5)
        images[name5].update(todo=False, boxes=[[90, 95, 160, 200, 0, None]])
        with open(os.path.join(out, "PC-A", "labels.json"), "w", encoding="utf-8") as fh:
            json.dump({"images": images}, fh)
        hp.run([z], out, "fallen_blessed", boxes_fn=stub, test_share=0.2)
        again = json.load(open(os.path.join(out, "PC-A", "labels.json"), encoding="utf-8"))["images"]
        check(again[name5]["boxes"] == [[90, 95, 160, 200, 0, None]] and not again[name5]["todo"],
              "a re-run keeps the frame a person reviewed")
        man = json.load(open(os.path.join(out, "manifest.json"), encoding="utf-8"))
        check(man["totals"]["review"] >= 2 and "review_minutes" in man["totals"], f"manifest totals {man['totals']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("hard cases prep tests OK")


if __name__ == "__main__":
    main()
