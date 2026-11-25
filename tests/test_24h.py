"""PLAN 0.38: running 24/7.

- the recording frame cap ends the RECORDING, the hunt goes on; a long recording rotates every ROTATE_SEC and the
  cap counts all its folders;
- records/ is kept under max_gb (oldest recordings first, the live one and other files never);
- session_log.txt rotates past MAX_BYTES and keeps KEEP files;
- a loop error restarts the loop (too many = stop), the HUD gone for HUD_LOST_SEC = safe stop, RSS logged.
Usage:  python tests/test_24h.py      (any OS)
"""
import os
import sys
import tempfile
import time
import types

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lineage_auto import logging_setup  # noqa: E402
from lineage_auto.config.models import AccountSettings, RecordSettings  # noqa: E402
from lineage_auto.runtime import recorder as recmod  # noqa: E402
from lineage_auto.runtime import session as sessmod  # noqa: E402

IMG = np.zeros((8, 8, 3), np.uint8)


class Clock:
    def __init__(self):
        self.now = 1_700_000_000.0

    def __call__(self):
        return self.now


def fake_session(account, root, clock):
    """Just what the recording / watch helpers of AccountSession touch."""
    logs = []
    ctx = types.SimpleNamespace(recorder=None, log=logs.append, rect=lambda: None, state={})
    sess = types.SimpleNamespace(account=account, ctx=ctx, _mem_next=0.0, _mem_last=None, _mem_rises=0,
                                 _hud_seen=None)
    for name in ("_recording_tick", "_close_recorder", "_prune_records", "_watch_memory", "_hud_lost"):
        setattr(sess, name, types.MethodType(getattr(sessmod.AccountSession, name), sess))
    real = recmod.Recorder
    sessmod.Recorder = lambda acc, mode, rect=None, prior_frames=0: real(acc, mode, rect=rect, root=root,
                                                                       clock=clock, prior_frames=prior_frames)
    return sess, logs


def test_cap_stops_recording_not_hunt():
    root, clock = tempfile.mkdtemp(), Clock()
    account = AccountSettings(name="t")
    account.record = RecordSettings.from_dict({"max_frames": 20, "interval_sec": 1, "auto_stop_min": 75})
    sess, logs = fake_session(account, root, clock)
    sess.ctx.recorder = sessmod.Recorder(account, "hunt")
    for i in range(12):
        sess.ctx.recorder.frame(IMG, [], force=True)
    clock.now += recmod.ROTATE_SEC + 1  # rotation: a new folder, the 12 frames still count
    sess._recording_tick()
    rec2 = sess.ctx.recorder
    assert rec2 is not None and rec2.prior_frames == 12 and any("rotated" in m for m in logs), logs
    for i in range(8):
        rec2.frame(IMG, [], force=True)
    assert rec2.full
    sess._limit_reached = types.MethodType(sessmod.AccountSession._limit_reached, sess)
    sess._deadline = None
    assert not sess._limit_reached()  # a hunt never stops on the cap
    sess._recording_tick()
    assert sess.ctx.recorder is None and "recording cap reached, hunting continues" in logs
    assert len([d for d in os.listdir(root) if d.endswith("_hunt")]) == 2
    # observe: the cap still ends the session (there is nothing else to do)
    obs = recmod.Recorder(account, "observe", root=root, clock=clock, prior_frames=20)
    sess.ctx.recorder = obs
    assert sess._limit_reached()
    # 24/7 default: no cap at all
    account.record = RecordSettings.from_dict({})
    assert recmod.Recorder(account, "hunt", root=root, clock=clock).full is False


def test_prune_records_oldest_first():
    root = tempfile.mkdtemp()
    for stamp in ("20261101_000000_hunt", "20261102_000000_hunt", "20261103_000000_hunt"):
        os.makedirs(os.path.join(root, stamp))
        with open(os.path.join(root, stamp, "f.jpg"), "wb") as fh:
            fh.write(b"x" * 1000)
    with open(os.path.join(root, "20261101_000000_hunt.zip"), "wb") as fh:
        fh.write(b"x" * 500)
    os.makedirs(os.path.join(root, "deaths"))  # helper folder: never touched
    with open(os.path.join(root, "deaths", "a.jpg"), "wb") as fh:
        fh.write(b"x" * 5000)
    live = os.path.join(root, "20261101_000000_hunt")  # pretend the oldest is the one being written
    gone = recmod.prune_records(2500, keep=live, root=root)  # 3500 bytes: zip (500) + 02 (1000) go
    names = sorted(os.listdir(root))
    assert [os.path.basename(p) for p in gone] == ["20261101_000000_hunt.zip", "20261102_000000_hunt"], gone
    assert names == ["20261101_000000_hunt", "20261103_000000_hunt", "deaths"], names


def test_log_rotation():
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "session_log.txt")
    old = logging_setup.MAX_BYTES, logging_setup.CHECK_EVERY
    logging_setup.MAX_BYTES, logging_setup.CHECK_EVERY = 2000, 5
    try:
        log = logging_setup.FileLogger(path)
        for i in range(400):
            log.write(f"line {i} " + "x" * 40)
    finally:
        logging_setup.MAX_BYTES, logging_setup.CHECK_EVERY = old
    files = sorted(os.listdir(folder))
    assert files == ["session_log.1.txt", "session_log.2.txt", "session_log.txt"], files
    assert all(os.path.getsize(os.path.join(folder, f)) < 2000 + 60 * 5 for f in files)
    assert "line 399" in open(path, encoding="utf-8").read()


def test_hud_lost_and_memory():
    account = AccountSettings(name="t")
    sess, logs = fake_session(account, tempfile.mkdtemp(), Clock())
    assert not sess._hud_lost()  # never read the HUD (numbers off): never a disconnect
    sess.ctx.state["hp_abs"] = (100, 190)
    assert not sess._hud_lost()
    sess.ctx.state["hp_abs"] = None
    assert not sess._hud_lost()
    sess._hud_seen = time.monotonic() - sessmod.HUD_LOST_SEC - 1
    assert sess._hud_lost() and "safe stop" in logs[-1]
    sessmod.rss_mb = iter([100.0] + [100.0 + 10 * i for i in range(1, 8)]).__next__
    for _ in range(8):
        sess._mem_next = 0.0
        sess._watch_memory()
    mem = [m for m in logs if m.startswith("memory: RSS")]
    assert len(mem) == 8 and "WARNING" not in mem[4] and "WARNING: grew 6" in mem[6], mem


def test_loop_error_restarts():
    """A bad beat is logged and the loop goes on; LOOP_ERRORS_MAX of them in the window stop it."""
    src = open(sessmod.__file__, encoding="utf-8").read()
    assert "restarting the loop" in src and "if len(errors) >= LOOP_ERRORS_MAX:" in src


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("24h tests OK")
