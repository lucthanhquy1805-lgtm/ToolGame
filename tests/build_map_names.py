"""Cut a map-name template (PLAN 1.3b, vision/map_name.py) from a recorded frame.

Usage:  python tests/build_map_names.py <record> <frame> <file key> "<map name>"     (adds it to index.json)
        python tests/build_map_names.py --check <record> [...]                      (read every 10th frame)
"""
import json
import os
import sys
from collections import Counter

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lineage_auto.vision import map_name  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    folder = os.path.join(ROOT, map_name.FOLDER)
    if sys.argv[1] == "--check":
        reader = map_name.MapNameReader(folder)
        for rec in sys.argv[2:]:
            names = sorted(f for f in os.listdir(rec) if f.startswith("f_") and f.endswith(".jpg"))[::10]
            got = Counter(reader.read(cv2.imread(os.path.join(rec, n)))[0] for n in names)
            print(os.path.basename(rec), dict(got))
        return
    record, frame, key, name = sys.argv[1:5]
    frame = frame if frame.endswith(".jpg") else f"f_{int(frame):05d}.jpg"
    crop = map_name.cut_label(cv2.imread(os.path.join(record, frame)))
    if crop is None:
        sys.exit("no text line in the map-name band")
    os.makedirs(folder, exist_ok=True)
    cv2.imencode(".png", crop)[1].tofile(os.path.join(folder, f"{key}.png"))
    index_path = os.path.join(folder, "index.json")
    index = json.load(open(index_path, encoding="utf-8")) if os.path.exists(index_path) else {}
    index[f"{key}.png"] = name
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)
    print(f"{name} -> {key}.png {crop.shape[1]}x{crop.shape[0]}")


if __name__ == "__main__":
    main()
