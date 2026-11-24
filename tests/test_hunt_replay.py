"""PLAN 0.20: the hunt's targeting with the orc model, replayed on saved recordings (no game).

For every reviewed TEST frame of the orc recordings (day 193903, night 133425) TargetingFeature.acquire runs as in
the hunt loop: grab = the saved picture, the mouse move is recorded, and the cursor read after a hover is "attack"
when the mouse sits inside a reviewed orc box (what the game shows), else "ground".
Usage:  python tests/test_hunt_replay.py   (skipped when the recordings are not on this machine)
"""
import json
import os
import sys
import types

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

RECORDS = ["20261123_193903_observe", "20261124_133425_observe"]


def inside(boxes, x, y):
    return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes)


def replay(folder):
    from lineage_auto.config.models import AccountSettings
    from lineage_auto.features.targeting import TargetingFeature
    from lineage_auto.vision.geometry import char_anchor
    from lineage_auto.winapi import cursor as wc
    from lineage_auto.winapi.window import ClientRect

    labels = json.load(open(os.path.join(folder, "labels.json"), encoding="utf-8"))["images"]
    frames = [(k, v) for k, v in labels.items() if v.get("split") == "test" and not v.get("todo")]
    account = AccountSettings()
    account.hunt_map = "blessed_orc"
    account.scan.hover_settle = account.scan.hover_retry = 0
    state = {"boxes": [], "mouse": None, "frame": None}
    moves = []

    def move(x, y):
        state["mouse"] = (x, y)
        moves.append((x, y))

    ctx = types.SimpleNamespace(account=account, running=True, recorder=None, state={},
                                input=types.SimpleNamespace(move=move), log=lambda m: None,
                                grabber=types.SimpleNamespace(grab_bgr=lambda _r: state["frame"]),
                                cursors=types.SimpleNamespace(is_attack=lambda h: h == "attack",
                                                              is_corpse=lambda h: False, get=lambda k: "",
                                                              classify=lambda h, m="": h))
    wc.CursorProbe.current_hash = staticmethod(
        lambda: "attack" if state["mouse"] and inside(state["boxes"], *state["mouse"]) else "ground")
    found = with_orc = first_hit = 0
    for name, lab in frames:
        boxes = [b[:4] for b in lab["boxes"]]
        frame = cv2.imread(os.path.join(folder, name))
        h, w = frame.shape[:2]
        state.update(boxes=boxes, mouse=None, frame=frame)
        targeting = TargetingFeature(ctx)  # fresh: no miss memory carried across unrelated frames
        moves.clear()
        target = targeting.acquire(ClientRect(0, 0, w, h), char_anchor(w, h))
        if not boxes:
            continue
        with_orc += 1
        if target:
            assert inside(boxes, *target.local), (name, target)
            found += 1
            first_hit += inside(boxes, *moves[0])
    return found, with_orc, first_hit


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    from lineage_auto import hunt_maps
    assert hunt_maps.model_exists("blessed_orc"), "model/yolox_tiny_blessed_orc.onnx missing"
    for rec in RECORDS:
        folder = os.path.join(ROOT, "records_game", rec)
        if not os.path.isdir(folder):
            print(f"skipped: {folder} not here")
            continue
        found, total, first = replay(folder)
        print(f"{rec}: target on {found}/{total} frames with an orc ({100 * found // max(total, 1)}%), "
              f"first hover on an orc {first}/{found}")
        assert found >= 0.8 * total, (found, total)  # the cursor confirms; a miss only means one more scan
    print("hunt replay OK")


if __name__ == "__main__":
    main()
