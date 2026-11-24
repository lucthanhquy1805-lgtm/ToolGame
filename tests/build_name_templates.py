"""Cut monster-name pictures (templates) from a recording (PLAN 0.16, docs/ADD_NEW_MAP.md).

Usage:  python tests/build_name_templates.py <record folder> <zone> <frame>:<class> [...] [--check]
        python tests/build_name_templates.py <record folder> <zone> --chat <frame>:<class>[:<n>] [...] [--check]

<zone>: real_map or key of a lineage_auto/data/monsters/<key>.json catalog.
<frame>:<class>: a frame (e.g. f_00230.jpg or 230) whose mouse was on a monster of that class
(pick frames where the name sits on plain ground, nothing white behind it).
Writes lineage_auto/data/monsters/names/<key>/<template>.png = the whiteness of the name text.
--chat: cut the chat template instead (<class>_chat.png) from the n-th kill line counted from the bottom
of the chat box (default 1 = newest): "아데나 (n) 획득: <name>" -> everything from the 4th word on.
Look at the result (it must start with the name, not "획득:").
--check: then read every attack-cursor frame of the record and print the names found
(with --chat: print the kills found from frame to frame).
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lineage_auto import monsters  # noqa: E402
from lineage_auto.vision.name_reader import (  # noqa: E402
    CHAT_BASE_W, NEAR_BOX, KillWatcher, NameReader, chat_bands, name_box_near, template_file, whiteness, words)


def frame_rows(folder):
    with open(os.path.join(folder, "frames.jsonl"), encoding="utf-8") as fh:
        return {r["file"]: r for r in (json.loads(line) for line in fh if line.strip())}


def cut(frame, mouse):
    """Whiteness crop (uint8) of the name text nearest above the mouse, or None.

    Frames of other window sizes are brought back to 1187 wide first, like NameReader.read_near."""
    h, w = frame.shape[:2]
    f = w / CHAT_BASE_W
    x0, y0 = max(0, mouse[0] + round(NEAR_BOX[0] * f)), max(0, mouse[1] + round(NEAR_BOX[1] * f))
    x1, y1 = min(w, mouse[0] + round(NEAR_BOX[2] * f)), min(h, mouse[1] + round(NEAR_BOX[3] * f))
    crop = frame[y0:y1, x0:x1]
    if abs(f - 1) > 0.02:
        crop = cv2.resize(crop, None, fx=1 / f, fy=1 / f, interpolation=cv2.INTER_AREA)
    else:
        f = 1.0
    white = whiteness(crop)
    box = name_box_near(white, (mouse[0] - x0) / f, (mouse[1] - y0) / f)
    if box is None:
        return None
    bx0, by0, bx1, by1 = box
    return (white[max(0, by0 - 1):by1 + 1, max(0, bx0 - 1):bx1 + 1] * 255).astype(np.uint8)


def cut_chat(frame, n=1):
    """Whiteness crop of the name in the n-th chat line from the bottom that has >= 4 words, or None."""
    kills = [core for _band, core in chat_bands(frame) if len(words(core)) >= 4]
    if len(kills) < n:
        return None
    core = kills[-n]
    ws = words(core)
    return (core[:, ws[3][0]:ws[-1][1] + 1] * 255).astype(np.uint8)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("record")
    parser.add_argument("zone")
    parser.add_argument("samples", nargs="*")
    parser.add_argument("--chat", action="store_true", help="cut chat-line templates")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    catalog = monsters.for_real_map(args.zone)
    if catalog is None:
        sys.exit(f"no catalog for {args.zone!r}")
    rows = frame_rows(args.record)
    os.makedirs(catalog.names_dir, exist_ok=True)
    for sample in args.samples:
        frame_name, cls, *nth = sample.split(":")
        if frame_name.isdigit():
            frame_name = f"f_{int(frame_name):05d}.jpg"
        monster = catalog.by_class(cls)
        row = rows.get(frame_name)
        if monster is None or row is None or (not args.chat and not row.get("mouse")):
            print(f"skip {sample}: unknown class, frame or no mouse")
            continue
        frame = cv2.imread(os.path.join(args.record, frame_name))
        crop = cut_chat(frame, int(nth[0]) if nth else 1) if args.chat else cut(frame, row["mouse"])
        if crop is None:
            print(f"skip {sample}: no such text line")
            continue
        path = os.path.join(catalog.names_dir, template_file(monster, "chat" if args.chat else "name"))
        cv2.imencode(".png", crop)[1].tofile(path)
        print(f"{monster['name']} -> {path} {crop.shape[1]}x{crop.shape[0]}")
    if args.check and args.chat:
        watcher = KillWatcher(NameReader(catalog, "chat"))
        for name in sorted(rows):
            kills = watcher.update(cv2.imread(os.path.join(args.record, name)))
            if kills:
                print(name, kills)
    elif args.check:
        reader = NameReader(catalog)
        for name, row in sorted(rows.items()):
            if row.get("cursor") == "attack" and row.get("mouse"):
                hit = reader.read_near(cv2.imread(os.path.join(args.record, name)), row["mouse"])
                print(name, hit and (hit["name"], hit["score"]))


if __name__ == "__main__":
    main()
