"""PLAN 0.21: kills read from the chat while OBSERVING (live), not only offline.

Replays the saved frames of records_game/20261124_130457_observe through AccountSession._run_observe itself
(grab = the saved picture, cursor read = the recorded hash/mouse) and checks the kills it writes against
the offline reading (tests/analyze_records.py found 8 there).
Usage:  python tests/test_observe_kills.py [record]   (skipped when the recording is not on this machine)
"""
import json
import os
import sys
import tempfile

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

RECORD = os.path.join(ROOT, "records_game", "20261124_130457_observe")
OFFLINE_KILLS = 8


class FakeWindow:
    def is_alive(self):
        return True


class FakeRect:
    def __init__(self, w, h):
        self.x, self.y, self.w, self.h = 0, 0, w, h


class FakeGrabber:
    """Hands out the saved frames one by one; the last grab ends the replay."""

    def __init__(self, ctx, folder, rows):
        self.ctx, self.folder, self.rows, self.i = ctx, folder, rows, 0

    def grab_bgr(self, _rect):
        row = self.rows[self.i]
        self.i += 1
        if self.i >= len(self.rows):
            self.ctx.running = False
        return cv2.imread(os.path.join(self.folder, row["file"]))

    def close_thread(self):
        pass


def replay(folder):
    from lineage_auto.config.models import AccountSettings
    from lineage_auto.runtime import session as sm
    from lineage_auto.runtime.recorder import Recorder
    from lineage_auto.runtime.stats import Stats
    from lineage_auto.winapi import cursor as wc

    rows = [json.loads(line) for line in open(os.path.join(folder, "frames.jsonl"), encoding="utf-8") if line.strip()]
    meta = json.load(open(os.path.join(folder, "meta.json"), encoding="utf-8"))
    account = AccountSettings()
    account.record.real_map = meta["real_map"]
    account.record.no_model = True
    account.record.interval_sec = 0.0  # every loop saves a frame, like one replayed frame per recorded one
    account.record.max_frames = len(rows) + 10
    account.record.auto_stop_min = 0

    class Ctx:
        running = True
        state = {}
        seen = None
        stats = Stats()

        def rect(self):
            return FakeRect(*meta["window"])

        def read_hud(self, _rect):
            return {"hp": None, "mp": None}

        def sleep(self, _s):
            pass

        def char_pos(self, rect):
            return rect.w // 2, rect.h // 2

        def log(self, msg):
            print("log:", msg)

        def request_stop(self):
            self.running = False

    ctx = Ctx()
    ctx.window = FakeWindow()
    ctx.grabber = FakeGrabber(ctx, folder, rows)
    ctx.cursors = type("C", (), {"classify": staticmethod(lambda h, m="": "ground")})()
    pos = iter(r.get("mouse") for r in rows)
    wc.CursorProbe.read = staticmethod(lambda: ("x", "", None, next(pos, None)))
    out = tempfile.mkdtemp()
    ctx.recorder = Recorder(account, "observe", rect=ctx.rect(), root=out)
    path = ctx.recorder.path
    sess = object.__new__(sm.AccountSession)
    sess.ctx, sess.account, sess.on_state_change = ctx, account, None
    sess.state, sess._thread, sess._deadline = sm.SessionState.OBSERVING, None, None
    sess._run_observe()
    saved = [json.loads(line) for line in open(os.path.join(path, "frames.jsonl"), encoding="utf-8")]
    summary = json.load(open(os.path.join(path, "summary.json"), encoding="utf-8"))
    raw = sorted(os.listdir(os.path.join(path, "raw")))
    return saved, ctx.state.get("kills", 0), summary, raw


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    folder = sys.argv[1] if len(sys.argv) > 1 else RECORD
    if not os.path.isdir(folder):
        print(f"skipped: {folder} not here")
        return
    saved, counted, summary, raw = replay(folder)
    kills = [(f["file"], f["kills"]) for f in saved if f.get("kills")]
    events = [f["event"] for f in saved if str(f.get("event", "")).startswith("kill:")]
    print(f"{len(saved)} frames replayed, kills {counted}: {kills}")
    assert counted == sum(len(k) for _f, k in kills) == OFFLINE_KILLS, counted
    assert len(events) == len(kills), events
    counts = summary["counts"]
    assert counts["chat_frames"] == len(saved) and counts["chat_lines"] > 3 * len(saved), counts
    assert raw[0] == "f_00001.png" and len(raw) == (len(saved) + 99) // 100, raw
    print(f"chat lines/frame {counts['chat_lines'] / counts['chat_frames']:.1f}, raw PNG {len(raw)}")
    print("observe kills OK")


if __name__ == "__main__":
    main()
