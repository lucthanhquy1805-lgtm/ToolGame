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
        self.fps = max(1, scan.detect_fps)
        self.period = 1.0 / self.fps
        sess = yolox_mobs.ensure_session(self.map_key, scan.input_size)
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
                yolox_mobs.ensure_session(self.map_key, self.fight_size)
        self.adaptive = bool(scan.adaptive_detect) and self.fight_size != self.size
        self.latest = None
        self._cond = threading.Condition()
        self._stop = False
        self._thread = None
        self._errors_t = 0.0
        self._stepped = False  # the automatic step down is tried once, at the first log line

    def describe(self):
        fight = f" fight {self.fight_size}+roi every 2nd" if self.adaptive else ""
        return (f"size {self.size} roi {'on' if self.roi else 'off'} threads {yolox_mobs.ort_threads()} "
                f"max {self.fps}/s{fight}")

    def _mode(self, seq):
        """(input size, crop the play area) for this cycle: every other detect of a fight is the cheap one."""
        if self.adaptive and seq % 2 and self.ctx.state.get("fight_until", 0.0) > time.monotonic():
            return self.fight_size, True
        return self.size, self.roi

    def _slow_down(self, avg_ms, achieved_fps):
        """PLAN 0.33: drop 1/s while the detector costs more than CPU_SHARE of a core."""
        duty = avg_ms / 1000.0 * achieved_fps * yolox_mobs.ort_threads()
        if duty > CPU_SHARE and self.fps > 1:
            self.fps -= 1
            self.period = 1.0 / self.fps
            self.ctx.log(f"[detect] {duty * 100:.0f}% of a core > {CPU_SHARE * 100:.0f}% -> {self.fps}/s")
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
        if self._stepped or avg_ms <= max(SLOW_MS, 1000 * self.period) or not smaller:
            self._stepped = True
            return
        self._stepped = True
        old, self.size = self.size, max(smaller)
        self.ctx.log(f"[detect] {avg_ms:.0f} ms > {SLOW_MS:.0f} ms at {old} -> input {self.size} "
                     f"(scan.input_size stays {self.ctx.account.scan.input_size})")

    def _run(self):
        ctx = self.ctx
        seq, n, total, boxes = 0, 0, 0.0, 0
        log_t = time.monotonic() - LOG_EVERY + FIRST_LOG  # first line soon after the start, then every minute
        cpu_t = time.process_time()  # whole-process CPU seconds: no psutil needed for the bot's CPU %
        try:
            while not self._stop and ctx.running:
                start = time.perf_counter()
                try:
                    rect = ctx.rect()
                    char = ctx.char_pos(rect)
                    frame = ctx.grabber.grab_bgr(rect)
                    size, roi = self._mode(seq)
                    t0 = time.perf_counter()
                    hits, figures, dies = yolox_mobs.detect(
                        frame, char[0], char[1], play_max_radius(rect.w, rect.h, char[0], char[1]),
                        map_key=self.map_key, conf=self.conf, size=size, roi=roi)
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
                n, total, boxes = n + 1, total + ms, boxes + len(hits)
                now = time.monotonic()
                if now - log_t >= LOG_EVERY:
                    # PLAN 0.33: one line a minute with the bot's own CPU %, the rate it really keeps and how
                    # many boxes a frame it sees, so a field recording shows whether the game had room to run.
                    window = now - log_t
                    cpu_now = time.process_time()
                    cpu_pct = 100.0 * (cpu_now - cpu_t) / window
                    avg_ms, real_fps, per_frame = total / n, n / window, boxes / n
                    ctx.log(f"[detect] {self.describe()}: {avg_ms:.0f} ms avg, {real_fps:.1f}/s, "
                            f"cpu {cpu_pct:.0f}%, {per_frame:.2f} boxes/frame")
                    duty = self._slow_down(avg_ms, real_fps)
                    self._step_down(avg_ms)
                    rec = ctx.recorder
                    if rec is not None:
                        rec.event("detect_stats", ms=round(avg_ms), fps=round(real_fps, 2),
                                  cpu_pct=round(cpu_pct), boxes_per_frame=round(per_frame, 2),
                                  duty=round(duty, 2), size=self.size, fight_size=self.fight_size,
                                  threads=yolox_mobs.ort_threads(), max_fps=self.fps)
                    n, total, boxes, log_t, cpu_t = 0, 0.0, 0, now, cpu_now
                rest = self.period - (time.perf_counter() - start)
                if rest > 0:
                    time.sleep(rest)
        finally:
            ctx.grabber.close_thread()
            with self._cond:
                self._stop = True
                self._cond.notify_all()
