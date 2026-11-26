"""Minimap odometry + step measurement on a real walk (PLAN 1.2b).

records_game/20261126_192615_observe (1280x960, minimap on): standing, 5 steps up-right, standing, 5 steps up-left,
standing. The map marks move (+4,-2) px per step, then (-4,-2): the character (odometry = minus the map shift)
ends walk 1 at (-20,+10) and walk 2 at (0,+20). The minimap is see-through, so the old raw-gray correlation lost
8 of the 10 steps there.
Run: python tests/test_odometry.py   (skipped when the frames are not on this machine)
"""
import json
import math
import os
import sys
import types

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lineage_auto.config.models import ScanSettings  # noqa: E402
from lineage_auto.vision import minimap  # noqa: E402

REC = os.path.join(ROOT, "records_game", "20261126_192615_observe")
WALK1_END, WALK2_END = "f_00013.jpg", "f_00023.jpg"  # both are standing frames after the walk


def track():
    """{frame file: odometry position} over the whole recording."""
    odo, out = minimap.Odometry(), {}
    for line in open(os.path.join(REC, "frames.jsonl"), encoding="utf-8"):
        name = json.loads(line)["file"]
        mm = minimap.read(cv2.imread(os.path.join(REC, name)))
        assert mm is not None, f"no minimap on {name}"
        out[name] = odo.update(mm)
    return out


def near(p, q, tol=1.5):
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= tol


def test_walk(pos):
    p1, p2 = pos[WALK1_END], pos[WALK2_END]
    print(f"   walk 1 ends at ({p1[0]:+.1f},{p1[1]:+.1f}), walk 2 at ({p2[0]:+.1f},{p2[1]:+.1f})")
    assert near(p1, (-20, 10)), p1
    assert near(p2, (0, 20)), p2


def test_measure(pos):
    """The Hunt tab's Done on walk 1 (5 steps) saves ~4.5 minimap px per step."""
    from lineage_auto.ui.panels import scan_panel as sp

    saved = []
    label = types.SimpleNamespace(text="", config=lambda **k: setattr(label, "text", k.get("text", label.text)))
    fake = types.SimpleNamespace(
        _measure=None, _odo=types.SimpleNamespace(pos=pos[WALK1_END]), _scale=10.0,
        account=types.SimpleNamespace(scan=ScanSettings()), tab=types.SimpleNamespace(request_save=lambda: saved.append(1)),
        btn_step=types.SimpleNamespace(config=lambda **k: None), lbl_step=label,
        t=lambda key, **kw: f"{key} {kw}")
    old, sp.MEASURE_STEPS = sp.MEASURE_STEPS, 5
    try:
        sp.ScanPanel._finish_measure(fake)
    finally:
        sp.MEASURE_STEPS = old
    step = fake.account.scan.step_mm
    print(f"   measured step {step} minimap px, saved {bool(saved)}")
    assert 4.0 <= step <= 5.0 and saved, (step, saved)
    back = ScanSettings.from_dict(fake.account.scan.__dict__)
    assert back.step_mm == step, back.step_mm


def test_reject():
    """A read that does not match the last one (peak under MIN_RESPONSE) keeps the position."""
    img = cv2.imread(os.path.join(REC, WALK1_END))
    odo = minimap.Odometry()
    odo.update(minimap.read(img))
    before = odo.update(minimap.read(img))
    noise = minimap.read(img)
    noise.gray = np.random.default_rng(1).integers(0, 256, noise.gray.shape, dtype=np.uint8)
    assert odo.update(noise) == before, (before, odo.pos)


def test_saved_values():
    assert ScanSettings.from_dict({"step_px": 48.0}).step_mm == 0.0  # v21rc1 client px: not read
    assert ScanSettings.from_dict({"step_mm": 4.5}).step_mm == 4.5
    assert ScanSettings.from_dict({"step_mm": 33.0}).step_mm == 0.0  # outside 1-20: a misread
    assert ScanSettings.from_dict({"step_mm": 0.4}).step_mm == 0.0


if __name__ == "__main__":
    test_saved_values()
    if not os.path.isfile(os.path.join(REC, WALK2_END)):  # frames are not in git (.gitignore)
        print(f"SKIP: the frames of {REC} are not on this machine")
    else:
        positions = track()
        test_walk(positions)
        test_measure(positions)
        test_reject()
    print("odometry tests OK")
