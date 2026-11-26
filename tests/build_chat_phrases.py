"""Cut a chat line out of a recording into a "buff ran out" picture (PLAN 2.1b).

The game announces an expiring buff in the chat, with wording that differs per buff:
  "블레스드 아머: 갑옷에 깃들었던 축복이 사라집니다"
  "쉴드: 쉴드가 사라집니다"
  "인챈트 덱스터리티: 몸놀림이 둔해지는 것이 느껴집니다"   (no 사라집니다 at all)
so the bot matches the WHOLE line against a picture of it, one file per skill:
``lineage_auto/data/chat/buff_gone/<skill_id>[_note].png`` (see vision/name_reader.buff_gone_skill).

Usage (run on a recording that has its frames):
  python tests/build_chat_phrases.py <record dir>                 # contact sheets of every new chat line
  python tests/build_chat_phrases.py <record dir> --save 399 --line 35
The sheets land in <out>/sheet_NN.png, 16 lines each; --line is the global line number printed next to it.
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
from lineage_auto.vision import name_reader as nr  # noqa: E402

PER_SHEET = 16
OUT_DIR = os.path.join(ROOT, "lineage_auto", "data", "chat", nr.BUFF_GONE_DIR)


def read_lines(rec, zone):
    """[(frame file, name, mask)] for every chat line that was new in its frame."""
    reader = nr.NameReader(monsters.for_real_map(zone), "chat")
    frames = [json.loads(line) for line in open(os.path.join(rec, "frames.jsonl"), encoding="utf-8")]
    out, prev = [], None
    for frame in frames:
        img = cv2.imread(os.path.join(rec, frame["file"]))
        if img is None:
            continue
        lines = [(nr.line_sig(mask), name, mask) for mask, name in reader.chat_lines(img)]
        if prev is not None:
            out.extend((frame["file"], name, mask) for _sig, name, mask in nr.scrolled_lines(prev, lines))
        prev = lines
    return out


def sheets(lines, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    width = max(mask.shape[1] for _f, _n, mask in lines)
    for start in range(0, len(lines), PER_SHEET):
        chunk = lines[start:start + PER_SHEET]
        sheet = np.zeros((sum(m.shape[0] + 8 for _f, _n, m in chunk), width), np.uint8)
        y = 0
        for _f, _n, mask in chunk:
            sheet[y:y + mask.shape[0], :mask.shape[1]] = (mask * 255).astype(np.uint8)
            y += mask.shape[0] + 8
        path = os.path.join(out_dir, f"sheet_{start // PER_SHEET:02d}.png")
        cv2.imwrite(path, 255 - sheet)  # dark text on white: easier to read
        print(f"{path}  lines {start}-{start + len(chunk) - 1}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("record")
    ap.add_argument("--zone", default="타락한 축복의 땅의 봄")
    ap.add_argument("--out", default=os.path.join(ROOT, "records_game", "_chat"))
    ap.add_argument("--save", help="skill id: write this line as data/chat/buff_gone/<id>.png")
    ap.add_argument("--line", type=int, help="global line number (from the sheets)")
    ap.add_argument("--note", default="", help="suffix for the file name")
    args = ap.parse_args()

    lines = read_lines(args.record, args.zone)
    print(f"{len(lines)} new chat lines in {os.path.basename(args.record)}")
    if args.save is None:
        sheets(lines, args.out)
        return
    if args.line is None or not 0 <= args.line < len(lines):
        raise SystemExit(f"--line 0..{len(lines) - 1} is required with --save")
    mask = lines[args.line][2]
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{args.save}{('_' + args.note) if args.note else ''}.png")
    cv2.imwrite(path, (mask * 255).astype(np.uint8))
    print(f"saved {path}  ({mask.shape[1]}x{mask.shape[0]} px, from {lines[args.line][0]})")
    nr.buff_gone_templates.cache_clear()
    print("reads back as skill", nr.buff_gone_skill(mask))


if __name__ == "__main__":
    main()
