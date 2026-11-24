"""Every distinct cursor seen inside the game window (PLAN 0.11 v5).

The player plays normally (or loads a recording), then assigns a kind to each picture in the
"cursors seen" box — no need to catch a corpse within a few seconds.

Folder layout: index.json {hash: {count, md5, png, pos, record, frame}} + <hash>.png.
"""

import json
import os
import threading
import time

from ..winapi.cursor import image_print, is_windows_cursor, save_png

SAVE_EVERY = 5.0


class CursorCollection:
    def __init__(self, folder):
        self.folder = folder
        self._lock = threading.RLock()
        self._items = {}
        self._dirty = False
        self._saved_at = 0.0
        self.load()

    def load(self):
        try:
            with open(os.path.join(self.folder, "index.json"), encoding="utf-8") as fh:
                self._items = json.load(fh)
        except (OSError, ValueError):
            self._items = {}
        self._drop_wrong_pictures()

    def _drop_wrong_pictures(self):
        """PLAN 0.17: a picture must BE its hash. v5/v6 could store another cursor's bitmap under a hash
        (threads sharing CursorProbe.last_image), so the grid showed e.g. a Windows arrow on the sword tile."""
        import cv2
        import numpy as np

        for value, item in self._items.items():
            if is_windows_cursor(value) and "ignored" not in item:
                item["ignored"] = True
                self._dirty = True
            path = self.png_path(value)
            if not path:
                continue
            try:
                image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            except (OSError, cv2.error):
                image = None
            if image_print(image) != value:
                print(f"[CURSOR] seen: picture of {value} is another cursor -> dropped")
                item["png"] = None
                self._dirty = True
                try:
                    os.remove(path)
                except OSError:
                    pass

    def save(self, force=True):
        with self._lock:
            if not self._dirty or (not force and time.monotonic() - self._saved_at < SAVE_EVERY):
                return
            os.makedirs(self.folder, exist_ok=True)
            tmp = os.path.join(self.folder, "index.json.tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._items, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, os.path.join(self.folder, "index.json"))
            self._dirty, self._saved_at = False, time.monotonic()

    def add(self, cursor_hash, md5=None, image=None, pos=None, record=None, frame=None):
        """Count one sighting. Call only while the mouse is inside the game window."""
        if not cursor_hash:
            return
        with self._lock:
            item = self._items.get(cursor_hash)
            if item is None:
                item = self._items[cursor_hash] = {"count": 0, "md5": None, "png": None,
                                                   "pos": None, "record": None, "frame": None}
                if is_windows_cursor(cursor_hash):
                    item["ignored"] = True  # Windows pointer over the tool window, never a game kind
            item["count"] += 1
            if md5 and not item["md5"]:
                item["md5"] = md5
            # Keep the first example that has a saved frame (to look at what was under the mouse).
            if pos and (not item["pos"] or (frame and not item["frame"])):
                item["pos"], item["record"], item["frame"] = list(pos), record, frame
            if image is not None and not item["png"] and image_print(image) == cursor_hash:
                name = f"{cursor_hash}.png"
                if save_png(os.path.join(self.folder, name), image):
                    item["png"] = name
            self._dirty = True
        self.save(force=False)

    def load_record(self, record_dir):
        """Import a recording: frames.jsonl hash (+md5) / mouse and cursors/<hash>.png. Returns rows used."""
        try:
            with open(os.path.join(record_dir, "frames.jsonl"), encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh if line.strip()]
        except OSError:
            return 0
        import cv2
        import numpy as np

        used = 0
        for row in rows:
            value = row.get("hash")
            if not value or not row.get("mouse"):
                continue  # mouse outside the game window: Windows' own cursors
            image = None
            png = os.path.join(record_dir, "cursors", f"{value}.png")
            if not (self._items.get(value) or {}).get("png") and os.path.exists(png):
                image = cv2.imdecode(np.fromfile(png, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            self.add(value, md5=row.get("md5"), image=image, pos=row["mouse"],
                     record=os.path.abspath(record_dir), frame=row.get("file"))
            used += 1
        self.save()
        return used

    def entries(self):
        """[(hash, item)] most seen first."""
        with self._lock:
            return sorted(((h, dict(i)) for h, i in self._items.items()), key=lambda kv: -kv[1]["count"])

    def suggest_ground(self):
        """The most frequent cursor inside the game is almost always the plain ground one."""
        items = self.entries()
        if not items or (len(items) > 1 and items[0][1]["count"] == items[1][1]["count"]):
            return None
        return items[0][0]

    def signature(self, cursor_hash):
        item = self._items.get(cursor_hash) or {}
        return ",".join(t for t in (cursor_hash, item.get("md5")) if t)

    def png_path(self, cursor_hash):
        item = self._items.get(cursor_hash) or {}
        return os.path.join(self.folder, item["png"]) if item.get("png") else None

    def mark_ignored(self, cursor_hash, ignored):
        with self._lock:
            if cursor_hash in self._items:
                self._items[cursor_hash]["ignored"] = bool(ignored)
                self._dirty = True
        self.save()

    def clear(self):
        with self._lock:
            self._items = {}
            self._dirty = True
        self.save()
