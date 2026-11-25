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
    "20261126_001245_hunt": FALLEN + "봄",
}
# 001245 (hunting, spring): 210/263 read, the rest is the label over white cherry blossoms (never a wrong name)
MIN_SHARE = {"20261126_001245_hunt": 0.6}


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
        assert not wrong and reads.count(expected) >= MIN_SHARE.get(rec, 0.9) * len(reads), (rec, reads)


def test_no_label():
    """A frame without the label (black) reads nothing."""
    import numpy as np
    assert MapNameReader().read(np.zeros((960, 1280, 3), np.uint8))[0] is None


def test_zone_follows_screen():
    """PLAN 0.39 / 7: 001245 hunted the spring map with the zone left on 오크의 땅 (1 kill counted). The map name on
    screen / the hunt map choose the catalog the chat is read with, and the zone is corrected."""
    import types

    import numpy as np
    from lineage_auto.config.models import AccountSettings
    from lineage_auto.runtime.session import AccountSession

    def session(real_map, hunt_map, frame):
        acc = AccountSettings()
        acc.record.real_map, acc.hunt_map = real_map, hunt_map
        s = object.__new__(AccountSession)
        s.account, logs = acc, []
        s.ctx = types.SimpleNamespace(log=logs.append, rect=lambda: None,
                                      grabber=types.SimpleNamespace(grab_bgr=lambda r: frame))
        return s, logs

    orc = "오염된 축복의 땅 - 오크의 땅"
    blank = np.zeros((960, 1280, 3), np.uint8)
    # nothing readable on screen: the hunt map's zone (fallen_blessed), corrected and logged
    s, logs = session(orc, "fallen_blessed", blank)
    assert s._zone_catalog().key == "fallen_blessed" and s.account.record.real_map.startswith("타락한 축복의 땅 ("), logs
    assert any("WARNING" in m for m in logs), logs
    s, logs = session(orc, "blessed_orc_v2", blank)  # zone and model agree (a variant of the same ground): kept
    assert s._zone_catalog().key == "blessed_orc" and s.account.record.real_map == orc and not logs, logs
    frame = os.path.join(ROOT, "records_game", "20261126_001245_hunt", "f_00001.jpg")
    if os.path.exists(frame):  # the real frame: the map name wins whatever the hunt map is
        s, logs = session(orc, "blessed_orc", cv2.imread(frame))
        assert s._zone_catalog().key == "fallen_blessed", logs
        assert any("model is for blessed_orc" in m for m in logs), logs
        s, logs = session("타락한 축복의 땅의 봄 - 요정", "fallen_blessed", cv2.imread(frame))
        assert s._zone_catalog().key == "fallen_blessed_elf" and not logs, logs  # the elf zone is on that map too


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("map name tests OK")
