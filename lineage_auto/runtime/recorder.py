"""Field data recorder (PLAN 0.6): frames + detections (+ hover results) on the game PC.

Layout of one recording, ``records/<YYYYmmdd_HHMMSS>_<mode>/``:
  meta.json      map, threshold, scan settings, window size, mode
  f_00001.jpg    raw client frames (full size), at most one per ``interval``
  frames.jsonl   one line per saved frame: file, t, char, hits, detect_ms, brightness, night, scan,
                 real_map, and (observe) mouse/cursor/hash/md5 of the player's cursor, hp/mp [cur, max],
                 event (corpse / hp0 / kill:<name>), monster_name/monster_class/name_score (name over the
                 monster under an attack cursor, PLAN 0.16), kills (new "아데나 획득" chat lines)
  names/f_xxxxx.png  observe: crop of that monster name (zones with a catalog + name pictures)
  hovers.jsonl   hunt mode: one line per hover: t, scan, frame, point, cursor kind, src (probe/grid), hash
  events.jsonl   hunt mode (PLAN 0.27): t, kind (fight_end / wander / loot), scan, frame + kind's fields
  cursors/<hash>.png  picture of each distinct cursor seen (first time only, PLAN 0.11)
  summary.json   counters and timing averages, written on close
Hovers are free labels: "attack" = real monster, anything else = false detection.
"""

import json
import os
import shutil
import time
from dataclasses import asdict

import cv2

from .. import app_paths, hunt_maps, monsters
from ..vision import drift, minimap, yolox_mobs
from ..vision.name_reader import NIGHT_BRIGHTNESS
from ..winapi.cursor import CursorProbe, image_print, save_png

RECORDS_DIR = "records"
JPEG_QUALITY = 92
# 2 = exact-MD5 / nearest-aHash classifier (PLAN 0.11). Older recordings' cursor labels are not trusted.
CURSOR_CLASSIFIER = 2
# PLAN 0.38 (24/7 runs): a long recording is split into one folder per ROTATE_SEC, and records/ is kept under
# RecordSettings.max_gb by deleting the oldest recordings.
ROTATE_SEC = 15 * 60


def records_root():
    return app_paths.data_path(RECORDS_DIR)


def latest_record(root=None):
    """Newest recording folder, or None."""
    root = root or records_root()
    if not os.path.isdir(root):
        return None
    # Recordings are named <stamp>_<mode>; skip helper folders such as deaths/.
    dirs = [d for d in sorted(os.listdir(root)) if d[:1].isdigit() and os.path.isdir(os.path.join(root, d))]
    return os.path.join(root, dirs[-1]) if dirs else None


def save_snapshot(frame_bgr, folder, root=None, prefix="", png=False):
    """One full frame to records/<folder>/<prefix><stamp>.jpg (e.g. the death screen).

    PLAN 0.3: ``png`` writes the raw picture instead (no JPEG blocks) - the death window is read later."""
    target = os.path.join(root or records_root(), folder)
    os.makedirs(target, exist_ok=True)
    path = os.path.join(target, prefix + time.strftime("%Y%m%d_%H%M%S") + (".png" if png else ".jpg"))
    cv2.imwrite(path, frame_bgr) if png else cv2.imwrite(path, frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return path


def _size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(d, f)) for d, _s, files in os.walk(path) for f in files)


def prune_records(max_bytes, keep=None, root=None):
    """Delete the oldest recordings (<stamp>_* folders and their .zip, in records/ only) until the recordings
    weigh at most ``max_bytes``. ``keep`` (the one being written) is never deleted. Returns the deleted paths."""
    root = root or records_root()
    if not os.path.isdir(root):
        return []
    keep = os.path.normcase(os.path.abspath(keep)) if keep else None
    items = sorted(os.path.join(root, d) for d in os.listdir(root) if d[:1].isdigit())  # stamp order = age
    sizes = {p: _size(p) for p in items}
    total, deleted = sum(sizes.values()), []
    for path in items:
        if total <= max_bytes:
            break
        if os.path.normcase(os.path.abspath(path)) == keep:
            continue
        try:
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
        except OSError:
            continue
        total -= sizes[path]
        deleted.append(path)
    return deleted


def zip_record(path):
    """Zip one recording next to it; returns the .zip path."""
    return shutil.make_archive(path, "zip", root_dir=path)


class Recorder:
    def __init__(self, account, mode, rect=None, root=None, clock=time.time, prior_frames=0):
        self.clock = clock
        self.mode = mode
        self.interval = account.record.interval_sec
        self.max_frames = account.record.frame_cap()
        self.prior_frames = prior_frames  # PLAN 0.38: regular frames of the earlier folders of this run
        self.event_frames = 0  # corpse / kill / HP 0 frames: outside the regular cap (PLAN 0.19)
        self.real_map = account.record.real_map
        self.started = clock()
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(self.started))
        self.path = os.path.join(root or records_root(), f"{stamp}_{mode}")
        os.makedirs(self.path, exist_ok=True)
        self.frames = 0
        self.scan = 0
        self._last_frame_t = None
        self._scan_frame = None
        self.counts = {}
        self._fights = {}  # outcome -> [n, seconds, is_kill] (PLAN 0.28)
        self._timings = {}
        self._cursors_saved = set()
        hunt = hunt_maps.get(account.hunt_map)
        self._write_json("meta.json", {
            "mode": mode,
            "started": stamp,
            "account": account.name,
            "class": account.character_class,
            "hunt_map": hunt.key,
            "model": None if mode == "observe" and account.record.no_model else hunt.key,
            "real_map": self.real_map,
            "zone": getattr(monsters.for_real_map(self.real_map), "key", None),  # PLAN 0.37: the monster catalog
            "channels": hunt.channels,
            "conf": account.scan.conf_for(hunt.key) or hunt.conf,  # the threshold really used (PLAN 0.27)
            "scan": asdict(account.scan),  # detect_fps / input_size / detect_roi (PLAN 0.31)
            "record": asdict(account.record),
            "window": [rect.w, rect.h] if rect is not None else None,
            "cursor_classifier": CURSOR_CLASSIFIER,
            "provider": yolox_mobs.LAST_DEVICE,  # PLAN 0.48: where the model really runs (scan has the choice)
            # PLAN 1.10: the range the bot really used, in steps AND px (scan.attack_range 0 reads as the class
            # default, which is what 20261128_001015's "attack_range: 0" hid).
            "attack_range": {
                "steps": account.attack_steps(),
                # PLAN 1.11: the reach on SCREEN (steps * 20 px, vision/drift.reach_px - the old figure here
                # read the MINIMAP step), plus whatever the "measure the attack range" button last measured.
                "px": round(drift.reach_px(account.attack_steps(), rect.w if rect is not None else None)),
                "measured_px": account.scan.attack_range_px or None,
                "from": "config" if account.scan.attack_range else f"class {account.character.key}",
            },
            "melee_max_sec": account.melee_cap(),  # PLAN 1.10: 0 in scan = the class default
            "provider_probe": {os.path.basename(p): ms for p, ms in yolox_mobs.PROBES.items()},  # (DML, CPU) ms
        })

    @property
    def regular_frames(self):
        """Regular frames of the whole run (this folder + the folders it rotated from)."""
        return self.prior_frames + self.frames - self.event_frames

    @property
    def full(self):
        return self.max_frames is not None and self.regular_frames >= self.max_frames

    @property
    def due_rotation(self):
        return self.clock() - self.started >= ROTATE_SEC

    def count(self, name, n=1):
        self.counts[name] = self.counts.get(name, 0) + n

    def timing(self, name, ms):
        total, n = self._timings.get(name, (0.0, 0))
        self._timings[name] = (total + ms, n + 1)

    def fight(self, outcome, seconds, kill=False):
        """One finished fight: summary "fights" = count + mean length per ending, and per group."""
        n, total, _k = self._fights.get(outcome, (0, 0.0, kill))
        self._fights[outcome] = (n + 1, total + seconds, kill)

    def fight_summary(self):
        per = {k: {"n": n, "avg_s": round(t / n, 1)} for k, (n, t, _kill) in self._fights.items()}
        groups = {}
        kill_kind = {"chat_kill": "kill_chat", "corpse_cursor": "kill_corpse_cursor"}  # PLAN 0.30 / 1
        for k, (n, t, kill) in self._fights.items():
            if kill:
                g = kill_kind.get(k, "kill_fall")  # die_box / vanished / frozen: the body fell / vanished
            else:
                g = k if k in ("gone", "unreachable", "wall", "danger", "no_progress", "cap", "lost", "switch") else "other"
            gn, gt = groups.get(g, (0, 0.0))
            groups[g] = (gn + n, gt + t)
        return per, {g: {"n": n, "avg_s": round(t / n, 1)} for g, (n, t) in groups.items()}

    def begin_scan(self):
        """New detection pass; hovers until the next call belong to it."""
        self.scan += 1
        self._scan_frame = None
        self.count("scans")

    def frame(self, frame_bgr, hits, char=None, detect_ms=None, force=False, extra=None):
        """Save the frame if ``interval`` passed (or force). Returns the file name or None.

        ``extra`` is merged into the frames.jsonl row (cursor label, event, grid sweep)."""
        if detect_ms is not None:
            self.timing("detect_ms", detect_ms)
        now = self.clock()
        if self.full or frame_bgr is None:
            return None
        if not force and self._last_frame_t is not None and now - self._last_frame_t < self.interval:
            return None
        self._last_frame_t = now
        self.frames += 1
        self.event_frames += bool((extra or {}).get("event"))
        name = f"f_{self.frames:05d}.jpg"
        cv2.imwrite(os.path.join(self.path, name), frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        self._scan_frame = name
        self._save_cursor((extra or {}).get("hash"))
        brightness = round(float(frame_bgr.mean()), 1)
        self._append("frames.jsonl", {
            "file": name,
            "t": round(now - self.started, 2),
            "scan": self.scan,
            "char": list(char) if char else None,
            "hits": [list(h) for h in hits],
            "detect_ms": round(detect_ms, 1) if detect_ms is not None else None,
            "brightness": brightness,
            "night": brightness < NIGHT_BRIGHTNESS,
            "real_map": self.real_map,
            **(extra or {}),
        })
        return name

    def hover(self, local_xy, kind, src="probe", cursor=None):
        """One hover result. kind: attack / corpse / ground / npc / unknown; src: probe or grid."""
        # Grid hovers get their own counters so hover_confirm_rate stays about YOLOX detections.
        self.count(f"{'hover' if src == 'probe' else src}_{kind}")
        self._save_cursor(cursor)
        self._append("hovers.jsonl", {
            "t": round(self.clock() - self.started, 2),
            "scan": self.scan,
            "frame": self._scan_frame,
            "point": [int(local_xy[0]), int(local_xy[1])],
            "kind": kind,
            "src": src,
            "hash": cursor,
        })

    def event(self, kind, **data):
        """One decision of the hunt (fight end, wander direction, loot) for later measuring (PLAN 0.27)."""
        self._append("events.jsonl", {"t": round(self.clock() - self.started, 2), "kind": kind, "scan": self.scan,
                                      "frame": self._scan_frame, **data})

    def _save_cursor(self, cursor_hash):
        """cursors/<hash>.png once per hash, from the probe read that produced the hash."""
        if not cursor_hash or cursor_hash in self._cursors_saved:
            return
        with CursorProbe.lock:
            image = CursorProbe.last_image if CursorProbe.last_print == cursor_hash else None
        if image_print(image) != cursor_hash:  # PLAN 0.17: never store another cursor's picture
            return
        if save_png(os.path.join(self.path, "cursors", f"{cursor_hash}.png"), image):
            self._cursors_saved.add(cursor_hash)

    def summary(self):
        hovers = sum(v for k, v in self.counts.items() if k.startswith("hover_"))
        attack = self.counts.get("hover_attack", 0)
        return {
            "mode": self.mode,
            "duration_sec": round(self.clock() - self.started, 1),
            "frames_saved": self.frames,
            "counts": dict(self.counts),
            "hover_confirm_rate": round(attack / hovers, 3) if hovers else None,
            "fights": self.fight_summary()[1],
            "fight_endings": self.fight_summary()[0],
            "chat_kill_lines": self.counts.get("chat_kill_lines", 0),  # every kill line the chat showed
            # PLAN 0.31 / 3: kills = one per kill line + one per body/cursor kill no line confirmed
            "kills_chat": self.counts.get("kills_chat", 0),
            "kills_corpse_only": self.counts.get("kills_corpse_only", 0),
            "kills_total": self.counts.get("kills_chat", 0) + self.counts.get("kills_corpse_only", 0),
            "detections_per_min": round(60 * self.counts.get("detections", 0) / max(1e-6, self.clock() - self.started), 1),
            "avg_ms": {k: round(total / n, 1) for k, (total, n) in self._timings.items() if n},
        }

    def close(self):
        summary = self.summary()
        self._write_json("summary.json", summary)
        return summary

    def _append(self, name, row):
        with open(os.path.join(self.path, name), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_json(self, name, data):
        with open(os.path.join(self.path, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
