"""PLAN 1.3b: the map name bottom-left (vision/map_name.py) on real frames of every window size.

Usage:  python tests/test_map_name.py      (frames not on this machine are skipped)
"""
import os
import sys

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lineage_auto.vision.map_name import MapNameReader  # noqa: E402

FALLEN = "타락한 축복의 땅의 "
CASES = {  # record -> map shown (checked by eye); 1187x890, 1302x976, 1280x960, 1334x1008
    "20261123_193903_observe": "오염된 축복의 땅",
    "20261124_133425_observe": "오염된 축복의 땅",
    "20261125_092741_hunt": "오염된 축복의 땅",
    "20261124_235143_observe_spring_day": FALLEN + "봄",
    "20261124_230953_observe_spring_day_elf": FALLEN + "봄",
    "20261125_001022_observe_summer_day": FALLEN + "여름",
    "20261125_012808_observe_summer_night": FALLEN + "여름",
    "20261125_003058_observe_autumn_day": FALLEN + "가을",
    "20261125_015330_observe_autumn_night": FALLEN + "가을",
    "20261125_005357_observe_winter_day": FALLEN + "겨울",
    "20261125_021734_observe_winter_night": FALLEN + "겨울",
}


def test_map_names():
    reader = MapNameReader()
    assert reader.available
    for rec, expected in CASES.items():
        folder = os.path.join(ROOT, "records_game", rec)
        if not os.path.isdir(folder):
            continue
        names = sorted(f for f in os.listdir(folder) if f.startswith("f_") and f.endswith(".jpg"))[::25]
        reads = [reader.read(cv2.imread(os.path.join(folder, n)))[0] for n in names]
        wrong = [r for r in reads if r is not None and r != expected]
        assert not wrong and reads.count(expected) >= 0.9 * len(reads), (rec, reads)


def test_no_label():
    """A frame without the label (black) reads nothing."""
    import numpy as np
    assert MapNameReader().read(np.zeros((960, 1280, 3), np.uint8))[0] is None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("map name tests OK")
