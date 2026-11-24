"""Rebuild lineage_auto/data/hud_glyphs/*.png from labelled HUD frames (PLAN 0.3).

Usage:  python tests/build_hud_glyphs.py
Each glyph is the mean of every occurrence in TRUTH (known "HP:x/y" / "MP:x/y" text).
Add frames from the game PC (records/*.jpg) to TRUTH to get crisper templates.
"""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lineage_auto.vision import hud_numbers as hn  # noqa: E402

IMAGES = os.path.join(ROOT, "docs", "game_reference")
# frame -> (HP text, MP text) as shown on the HUD
TRUTH = {
    "frame_0030s.png": ("356/432", "36/221"),
    "frame_0090s.png": ("382/432", "40/221"),
    "frame_0270s.png": ("312/432", "48/221"),
    "frame_0345s.png": ("364/432", "50/221"),
    "frame_0735s.png": ("342/432", "23/221"),
    "night_A0060s.png": ("324/432", "41/221"),
    "arrow_attack_B0400s.png": ("355/432", "37/221"),
    "buff_tooltip_A0940s.png": ("368/402", "38/221"),
    "chat_buff_msg_B0420s.png": ("303/432", "39/221"),
    "hotbar_A1040s.png": ("345/402", "46/221"),
}
# Prefix positions in frame_0030s.png (1280x960 client), found by eye on a pixel grid.
HP_PREFIX_XY = (438, 765)
MP_PREFIX_XY = (686, 765)


def main():
    P, H = hn.PITCH, hn.HEIGHT
    first = cv2.cvtColor(cv2.imread(os.path.join(IMAGES, "frame_0030s.png")), cv2.COLOR_BGR2GRAY)
    prefixes = {
        "hp": first[HP_PREFIX_XY[1]:HP_PREFIX_XY[1] + H, HP_PREFIX_XY[0]:HP_PREFIX_XY[0] + 3 * P],
        "mp": first[MP_PREFIX_XY[1]:MP_PREFIX_XY[1] + H, MP_PREFIX_XY[0]:MP_PREFIX_XY[0] + 3 * P],
    }
    samples = {}
    for name, texts in TRUTH.items():
        gray = cv2.cvtColor(cv2.imread(os.path.join(IMAGES, name)), cv2.COLOR_BGR2GRAY)
        for kind, text in zip(("hp", "mp"), texts):
            found = hn.find_prefix(gray.astype(np.float32), prefixes[kind].astype(np.float32), kind)
            assert found is not None, (name, kind)
            x0, y0 = found[1]
            for k, ch in enumerate(text):
                x = x0 + 3 * P + k * P
                samples.setdefault(ch, []).append(gray[y0:y0 + H, x:x + P].astype(np.float32))
    os.makedirs(hn.GLYPH_DIR, exist_ok=True)
    for kind, img in prefixes.items():
        cv2.imwrite(os.path.join(hn.GLYPH_DIR, f"{kind}.png"), img)
    for ch, crops in sorted(samples.items()):
        cv2.imwrite(os.path.join(hn.GLYPH_DIR, hn.glyph_file(ch)), np.mean(crops, 0).round().astype(np.uint8))
        print(f"{ch!r}: {len(crops)} samples")
    missing = set(hn.CHARS) - set(samples)
    print("written to", hn.GLYPH_DIR, "missing:", missing or "none")


if __name__ == "__main__":
    main()
