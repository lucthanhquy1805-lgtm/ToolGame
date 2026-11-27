"""PLAN 0.31: YOLOX on its own thread, non-stop, so the hunt never waits for a detect.

The thread grabs the client and runs the detector at most ``scan.detect_fps`` times a second; targeting reads the
newest result (TargetingFeature._detect). Size / ROI / onnxruntime threads and the measured ms go to the log
(every LOG_EVERY s) and to the recording (counts "detections", avg_ms "detect_ms").
"""

import threading
import time
from dataclasses import dataclass

from ..vision import yolox_mobs
from ..vision.geometry import play_max_radius

LOG_EVERY = 60.0
FIRST_LOG = 10.0
# PLAN 0.31: slower than this on average over the first FIRST_LOG s -> next smaller exported input, once.
# PLAN 0.32: only when it cannot even keep scan.detect_fps (the default 640 full frame costs ~165 ms on the game
# PC, which is still 5/s; stepping down to 416 would cost a quarter of the boxes).
SLOW_MS = 80.0
ERROR_PAUSE = 0.5
# PLAN 0.33: the detector may cost this share of ONE core on average; above it the rate drops by 1/s (min 1/s).
# 5/s of full 640 frames was ~0.9 core non-stop on the game PC and the client stuttered with 10-17 monsters up.
CPU_SHARE = 0.30
# PLAN 0.34: the rate may never fall below this while the bot is LOOKING for a monster - a slow search is what
# makes the bot stand around. A fight may go down to 1/s: it only has to follow a box next to the character.
FPS_FLOOR = {"search": 2, "fight": 1}
# PLAN 0.43: a fight must still see the WHOLE screen at least this often, whatever the rate has fallen to
# (seq % 2 gave ~1/s at 2/s, but nothing at all once the CPU guard dropped a fight to 1/s).
FULL_EVERY = 1.0


@dataclass(frozen=True)
class Detection:
    seq: int
    t: float
    frame: object
    char: tuple
    hits: list
    figures: list
    dies: list
    ms: float


class DetectorThread:
    def __init__(self, ctx):
        self.ctx = ctx
        scan = ctx.account.scan
        self.map_key = ctx.account.hunt_map
        self.conf = scan.conf_for(self.map_key)
        self.roi = scan.detect_roi
        yolox_mobs.THREADS = scan.detect_threads  # before the first session: opts.intra_op_num_threads
        # PLAN 0.34: searching runs the full 640 frame, which one core cannot do twice a second, so it gets
        # its own thread count; a fight runs the cheap crop and keeps one thread next to the game.
        self.threads = {"search": max(1, scan.search_threads), "fight": max(1, scan.detect_threads)}
        self.fps = {mode: max(FPS_FLOOR[mode], scan.detect_fps) for mode in FPS_FLOOR}
        sess = yolox_mobs.ensure_session(self.map_key, scan.input_size, self.threads["search"])
        self.size = yolox_mobs.session_size(sess)  # 640 when this map has no export at input_size
        # PLAN 0.33: while a fight runs only boxes next to the character matter, so EVERY OTHER detect crops the
        # play area and uses the next smaller export when the map has one (~35 ms instead of ~180 ms); the full
        # frame in between still shows far monsters. Searching always keeps the full frame at self.size.
        # Measured on the saved frames of 092741 + 112040 (tests/eval_detect_modes.py): cropping every fight
        # frame costs 17% of the boxes, alternating costs 8%, which is inside the 10% the user allowed. The 416 +
        # ROI *default* of v14 is still wrong (PLAN 0.32) - this is only the second tier of a fight.
        self.fight_size = self.size
        if scan.adaptive_detect:
            smaller = [z for z in yolox_mobs.EXPORT_SIZES
                       if z < self.size and yolox_mobs.model_path(self.map_key, z)]
            if smaller:
                self.fight_size = max(smaller)
                yolox_mobs.ensure_session(self.map_key, self.fight_size, self.threads["fight"])
        yolox_mobs.ensure_session(self.map_key, self.size, self.threads["fight"])  # full frame inside a fight
        self.adaptive = bool(scan.adaptive_detect) and self.fight_size != self.size
        self.latest = None
        self._cond = threading.Condition()
        self._stop = False
        self._thread = None
        self._errors_t = 0.0
        self._stepped = False  # the automatic step down is tried once, at the first log line
        self._full_t = 0.0  # when the last WHOLE-screen detect ran (PLAN 0.43)

    def describe(self):
        fight = f" fight {self.fight_size}+roi, full frame every {FULL_EVERY:.0f}s" if self.adaptive else ""
        return (f"size {self.size} roi {'on' if self.roi else 'off'} "
                f"threads {self.threads['search']}/{self.threads['fight']} search/fight "
                f"max {self.fps['search']}/{self.fps['fight']}/s{fight}")

    def fighting(self):
        return self.ctx.state.get("fight_until", 0.0) > time.monotonic()

    def _mode(self, seq):
        """(input size, crop the play area, onnx threads, mode) for this cycle.

        Searching is always the full frame (a far monster is the whole point); every other detect of a fight is
        the cheap crop, and a fight keeps one thread so the client has the rest."""
        if not self.fighting():
            self._full_t = time.monotonic()
            return self.size, self.roi, self.threads["search"], "search"
        now = time.monotonic()
        if self.adaptive and now - self._full_t < FULL_EVERY:
            return self.fight_size, True, self.threads["fight"], "fight"
        self._full_t = now
        return self.size, self.roi, self.threads["fight"], "fight"

    def period(self, mode):
        return 1.0 / self.fps[mode]

    def _slow_down(self, mode, avg_ms, achieved_fps):
        """PLAN 0.33/0.34: drop 1/s while this mode costs more than CPU_SHARE of a core, never below its floor."""
        duty = avg_ms / 1000.0 * achieved_fps * self.threads[mode]
        if duty > CPU_SHARE and self.fps[mode] > FPS_FLOOR[mode]:
            self.fps[mode] -= 1
            self.ctx.log(f"[detect] {mode} {duty * 100:.0f}% of a core > {CPU_SHARE * 100:.0f}% "
                         f"-> {self.fps[mode]}/s")
        return duty

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="detector")
        self._thread.start()

    def stop(self):
        self._stop = True
        with self._cond:
            self._cond.notify_all()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)

    def newest(self, seen_seq, wait=0.0):
        """Newest Detection, waiting up to ``wait`` s for one newer than ``seen_seq`` (None before the first)."""
        with self._cond:
            if wait > 0 and not self._stop:
                self._cond.wait_for(lambda: self._stop or (self.latest is not None and self.latest.seq > seen_seq),
                                    timeout=wait)
            elif self.latest is None and not self._stop:
                self._cond.wait_for(lambda: self._stop or self.latest is not None, timeout=1.0)
            return self.latest

    def _step_down(self, avg_ms):
        smaller = [s for s in yolox_mobs.EXPORT_SIZES if s < self.size and yolox_mobs.model_path(self.map_key, s)]
        if self._stepped or avg_ms <= max(SLOW_MS, 1000 * self.period("search")) or not smaller:
            self._stepped = True
            return
        self._stepped = True
        old, self.size = self.size, max(smaller)
        self.ctx.log(f"[detect] {avg_ms:.0f} ms > {SLOW_MS:.0f} ms at {old} -> input {self.size} "
                     f"(scan.input_size stays {self.ctx.account.scan.input_size})")

    def _run(self):
        ctx = self.ctx
        seq = 0
        stats = {mode: {"n": 0, "ms": 0.0, "boxes": 0} for mode in FPS_FLOOR}
        log_t = time.monotonic() - LOG_EVERY + FIRST_LOG  # first line soon after the start, then every minute
        cpu_t = time.process_time()  # whole-process CPU seconds: no psutil needed for the bot's CPU %
        try:
            while not self._stop and ctx.running:
                start = time.perf_counter()
                try:
                    rect = ctx.rect()
                    char = ctx.char_pos(rect)
                    frame = ctx.grabber.grab_bgr(rect)
                    size, roi, threads, mode = self._mode(seq)
                    t0 = time.perf_counter()
                    hits, figures, dies = yolox_mobs.detect(
                        frame, char[0], char[1], play_max_radius(rect.w, rect.h, char[0], char[1]),
                        map_key=self.map_key, conf=self.conf, size=size, roi=roi, threads=threads)
                    ms = 1000 * (time.perf_counter() - t0)
                except Exception as exc:
                    if time.monotonic() - self._errors_t > 10:
                        self._errors_t = time.monotonic()
                        ctx.log(f"[detect] error: {exc}")
                    time.sleep(ERROR_PAUSE)
                    continue
                seq += 1
                with self._cond:
                    self.latest = Detection(seq, time.time(), frame, tuple(char), hits, figures, dies, ms)
                    self._cond.notify_all()
                rec = ctx.recorder
                if rec is not None:
                    rec.count("detections")
                    rec.timing("detect_ms", ms)
                bucket = stats[mode]
                bucket["n"], bucket["ms"], bucket["boxes"] = bucket["n"] + 1, bucket["ms"] + ms, \
                    bucket["boxes"] + len(hits)
                now = time.monotonic()
                if now - log_t >= LOG_EVERY:
                    # PLAN 0.33/0.34: one line a minute per mode (searching vs fighting) with the rate really
                    # kept, the cost of a detect and the boxes it sees, plus the whole process's CPU %, so a
                    # field recording shows whether the game had room to run.
                    window = now - log_t
                    cpu_now = time.process_time()
                    cpu_pct = 100.0 * (cpu_now - cpu_t) / window
                    rec = ctx.recorder
                    parts, data = [], {}
                    for name, b in stats.items():
                        if not b["n"]:
                            continue
                        avg_ms, real_fps = b["ms"] / b["n"], b["n"] / window
                        per_frame = b["boxes"] / b["n"]
                        duty = self._slow_down(name, avg_ms, real_fps)
                        parts.append(f"{name} {avg_ms:.0f} ms {real_fps:.1f}/s {duty * 100:.0f}%core "
                                     f"{per_frame:.2f} boxes")
                        data[name] = {"ms": round(avg_ms), "fps": round(real_fps, 2), "duty": round(duty, 2),
                                      "boxes_per_frame": round(per_frame, 2), "threads": self.threads[name],
                                      "max_fps": self.fps[name]}
                    ctx.log(f"[detect] {self.describe()}: " + " | ".join(parts) + f" | process cpu {cpu_pct:.0f}%")
                    if stats["search"]["n"]:
                        self._step_down(stats["search"]["ms"] / stats["search"]["n"])
                    if rec is not None:
                        rec.event("detect_stats", cpu_pct=round(cpu_pct), size=self.size,
                                  fight_size=self.fight_size, **data)
                    stats = {mode_: {"n": 0, "ms": 0.0, "boxes": 0} for mode_ in FPS_FLOOR}
                    log_t, cpu_t = now, cpu_now
                rest = self.period(mode) - (time.perf_counter() - start)
                if rest > 0:
                    time.sleep(rest)
        finally:
            ctx.grabber.close_thread()
            with self._cond:
                self._stop = True
                self._cond.notify_all()
