"""PLAN 0.46 / 5: frames where the cursor (or a kill line) proves a monster the detector has no box for.

Written to records/hard_cases/ whatever the recording setting says - it is the training set for the next
model, and the user may hunt with recording off for days. Each case is one JPEG plus:
  * <name>.txt      YOLO label, one box of HC_BOX_W x HC_BOX_H around the point (an ESTIMATE, see below)
  * hard_cases.jsonl one line of context per case
  * labels.json      the same case in the format tests/label_tool.py reads, with todo=true

The box size is the median of the 3100 hand-labelled boxes of the existing recordings (57 x 95 px at
1280x960). It is good enough to review and fix in the label tool, and NOT good enough to train on blindly.
"""
import json
import os
import time

import cv2

from .. import app_paths
from ..vision.name_reader import is_night_frame

HARD_DIR = "hard_cases"
JPEG_QUALITY = 92
# Estimated monster box around the cursor point (median of the hand labels). Review before training.
HC_BOX_W = 57
HC_BOX_H = 95
# The user's cap: 500 pictures or 200 MB, oldest deleted first.
MAX_N = 500
MAX_MB = 200
# The same spot within this many seconds / pixels is the same monster, not a new case.
DEDUPE_SEC = 2.0
DEDUPE_PX = 48


def hard_dir(root=None):
    from .recorder import records_root
    return os.path.join(root or records_root(), HARD_DIR)


def yolo_line(point, w, h, cls=0):
    """YOLO label line for the estimated box around ``point``, clamped to the picture."""
    x0 = max(0.0, min(point[0] - HC_BOX_W / 2, w - HC_BOX_W))
    y0 = max(0.0, min(point[1] - HC_BOX_H / 2, h - HC_BOX_H))
    bw, bh = min(HC_BOX_W, w), min(HC_BOX_H, h)
    return f"{cls} {(x0 + bw / 2) / w:.6f} {(y0 + bh / 2) / h:.6f} {bw / w:.6f} {bh / h:.6f}"


def box_of(point, w, h):
    """The estimated box as label_tool stores it: [x0, y0, x1, y1]."""
    x0 = int(max(0, min(point[0] - HC_BOX_W // 2, w - HC_BOX_W)))
    y0 = int(max(0, min(point[1] - HC_BOX_H // 2, h - HC_BOX_H)))
    return [x0, y0, x0 + min(HC_BOX_W, w), y0 + min(HC_BOX_H, h)]


class HardCases:
    """One folder for every hunt, with a cap. Never raises into the hunt loop."""

    def __init__(self, root=None, clock=time.time):
        self.dir = hard_dir(root)
        self.clock = clock
        self.saved = 0
        self._last = []  # [(t, point)] of the recent cases, for the dedupe

    def _recent(self, point):
        now = self.clock()
        self._last = [(t, p) for t, p in self._last if now - t <= DEDUPE_SEC]
        return any(abs(p[0] - point[0]) <= DEDUPE_PX and abs(p[1] - point[1]) <= DEDUPE_PX
                   for _t, p in self._last)

    def _prune(self):
        """Keep at most MAX_N pictures and MAX_MB, oldest first; a dropped picture loses its label too."""
        try:
            files = sorted((e.stat().st_mtime, e.stat().st_size, e.name)
                           for e in os.scandir(self.dir) if e.name.endswith(".jpg"))
        except OSError:
            return
        total = sum(size for _t, size, _n in files)
        labels = self._labels()
        changed = False
        while files and (len(files) > MAX_N or total > MAX_MB * 1024 * 1024):
            _t, size, name = files.pop(0)
            for path in (os.path.join(self.dir, name), os.path.join(self.dir, name[:-4] + ".txt")):
                try:
                    os.remove(path)
                except OSError:
                    pass
            total -= size
            changed = labels.pop(name, None) is not None or changed
        if changed:
            self._save_labels(labels)

    def _labels_path(self):
        return os.path.join(self.dir, "labels.json")

    def _labels(self):
        try:
            with open(self._labels_path(), encoding="utf-8") as fh:
                return (json.load(fh) or {}).get("images") or {}
        except (OSError, ValueError):
            return {}

    def _save_labels(self, images):
        data = {"_doc": "PLAN 0.46 hard cases: boxes are ESTIMATES around a cursor hit - review with "
                         "tests/label_tool.py before training", "images": images}
        with open(self._labels_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)

    def save(self, frame, point, kind="cursor", src="", map_key="", extra=None):
        """Write one hard case. Returns its path, or None when it was skipped."""
        if frame is None or getattr(frame, "size", 0) == 0 or self._recent(point):
            return None
        os.makedirs(self.dir, exist_ok=True)
        h, w = frame.shape[:2]
        name = f"hc_{time.strftime('%Y%m%d_%H%M%S')}_{self.saved % 1000:03d}.jpg"
        path = os.path.join(self.dir, name)
        if not cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]):
            return None
        point = (int(point[0]), int(point[1]))
        night = bool(is_night_frame(frame))
        with open(path[:-4] + ".txt", "w", encoding="utf-8") as fh:
            fh.write(yolo_line(point, w, h) + "\n")
        with open(os.path.join(self.dir, "hard_cases.jsonl"), "a", encoding="utf-8") as fh:
            row = {"t": round(self.clock(), 2), "file": name, "point": list(point), "kind": kind, "src": src,
                   "map": map_key, "night": night}
            row.update(extra or {})
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        images = self._labels()
        images[name] = {"night": night, "map": map_key, "monster": [list(point)], "monster_names": [],
                        "boxes": [box_of(point, w, h)], "ignore": [], "todo": True}
        self._save_labels(images)
        self._last.append((self.clock(), point))
        self.saved += 1
        self._prune()
        return path


def stats(root=None):
    """(n, mb, by map, by day/night, reviewed) of the stored hard cases - for the UI and the export zip."""
    folder = hard_dir(root)
    out = {"n": 0, "mb": 0.0, "by_map": {}, "night": 0, "day": 0, "todo": 0, "reviewed": 0, "dir": folder}
    try:
        files = [e for e in os.scandir(folder) if e.name.endswith(".jpg")]
    except OSError:
        return out
    out["n"] = len(files)
    out["mb"] = round(sum(e.stat().st_size for e in files) / (1024 * 1024), 1)
    try:
        with open(os.path.join(folder, "labels.json"), encoding="utf-8") as fh:
            images = (json.load(fh) or {}).get("images") or {}
    except (OSError, ValueError):
        images = {}
    for name, lab in images.items():
        key = lab.get("map") or "?"
        out["by_map"][key] = out["by_map"].get(key, 0) + 1
        out["night" if lab.get("night") else "day"] += 1
        out["todo" if lab.get("todo") else "reviewed"] += 1
    return out


def export_zip(root=None, out_path=None):
    """Zip the whole hard_cases folder plus its stats. Returns (zip path, stats) or (None, stats)."""
    import zipfile
    info = stats(root)
    folder = info["dir"]
    if not info["n"]:
        return None, info
    out_path = out_path or os.path.join(root or app_paths.data_path("records"),
                                        f"hard_cases_{time.strftime('%Y%m%d_%H%M%S')}.zip")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(os.scandir(folder), key=lambda e: e.name):
            if entry.is_file():
                zf.write(entry.path, entry.name)
        zf.writestr("stats.json", json.dumps(info, ensure_ascii=False, indent=1))
    return out_path, info
