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
SLOW_MS = 80.0
ERROR_PAUSE = 0.5


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
        self.period = 1.0 / max(1, scan.detect_fps)
        sess = yolox_mobs.ensure_session(self.map_key, scan.input_size)
        self.size = yolox_mobs.session_size(sess)  # 640 when this map has no export at input_size
        self.latest = None
        self._cond = threading.Condition()
        self._stop = False
        self._thread = None
        self._errors_t = 0.0
        self._stepped = False  # the automatic step down is tried once, at the first log line

    def describe(self):
        return (f"size {self.size} roi {'on' if self.roi else 'off'} threads {yolox_mobs.ort_threads()} "
                f"max {1 / self.period:.0f}/s")

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
        if self._stepped or avg_ms <= SLOW_MS or not smaller:
            self._stepped = True
            return
        self._stepped = True
        old, self.size = self.size, max(smaller)
        self.ctx.log(f"[detect] {avg_ms:.0f} ms > {SLOW_MS:.0f} ms at {old} -> input {self.size} "
                     f"(scan.input_size stays {self.ctx.account.scan.input_size})")

    def _run(self):
        ctx = self.ctx
        seq, n, total = 0, 0, 0.0
        log_t = time.monotonic() - LOG_EVERY + FIRST_LOG  # first line soon after the start, then every minute
        try:
            while not self._stop and ctx.running:
                start = time.perf_counter()
                try:
                    rect = ctx.rect()
                    char = ctx.char_pos(rect)
                    frame = ctx.grabber.grab_bgr(rect)
                    t0 = time.perf_counter()
                    hits, figures, dies = yolox_mobs.detect(
                        frame, char[0], char[1], play_max_radius(rect.w, rect.h, char[0], char[1]),
                        map_key=self.map_key, conf=self.conf, size=self.size, roi=self.roi)
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
                n, total = n + 1, total + ms
                now = time.monotonic()
                if now - log_t >= LOG_EVERY:
                    ctx.log(f"[detect] {self.describe()}: {total / n:.0f} ms avg, {n / (now - log_t):.1f}/s")
                    self._step_down(total / n)
                    n, total, log_t = 0, 0.0, now
                rest = self.period - (time.perf_counter() - start)
                if rest > 0:
                    time.sleep(rest)
        finally:
            ctx.grabber.close_thread()
            with self._cond:
                self._stop = True
                self._cond.notify_all()
