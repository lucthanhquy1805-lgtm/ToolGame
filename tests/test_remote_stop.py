"""PLAN 0.28: stopping a hunt over TeamViewer, simulated with SendInput (what TeamViewer uses) on this PC.

Runs the real winapi.hotkeys.start_escape_threads loop as while hunting with the Interception backend, then
  1. moves the mouse 40 px with SendInput   -> "remote mouse move" (the path that works while the bot holds the
     left button and the game owns the mouse capture, so no click can reach the tool);
  2. presses ESC with SendInput              -> RegisterHotKey "ESC hotkey" (or the injected-key hook).
The mouse goes back where it was. Windows only; it really moves the cursor and sends one ESC (swallowed by the hotkey).
Usage: python tests/test_remote_stop.py
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE = 0x0001
KEYEVENTF_KEYUP = 0x0002


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    return ctypes.windll.user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def mouse_move(dx, dy):
    i = INPUT(type=INPUT_MOUSE)
    i.u.mi = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, 0)
    return send(i)


def key(vk):
    down, up = INPUT(type=INPUT_KEYBOARD), INPUT(type=INPUT_KEYBOARD)
    down.u.ki = KEYBDINPUT(vk, 0, 0, 0, 0)
    up.u.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)
    return send(down, up)


def wait_for(pred, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def main():
    if os.name != "nt":
        print("skipped: Windows only")
        return
    from lineage_auto.winapi import hotkeys as hk

    hk._listen_interception_escape = lambda *a: None  # no driver on the dev PC
    # PLAN 0.30: CursorWatch (pure): the bot's own moves never count, a drift with no bot move does.
    cw = hk.CursorWatch()
    assert cw.update(0.0, (100, 100), None) is None                # anchored
    assert cw.update(0.1, (100, 120), None) is None                # 20 px: below the drift
    assert cw.update(0.2, (500, 300), 0.19) is None                # the bot moved: re-anchor after CURSOR_QUIET
    assert cw.update(0.25, (520, 300), 0.19) is None and cw.update(0.4, (520, 300), 0.19) is None
    assert cw.update(0.5, (600, 360), 0.19) is not None            # moved 140 px, the bot did not
    print("cursor watch logic OK")
    reasons, state = [], {"closing": False}
    move_t = {"t": time.monotonic()}
    ev = hk.start_escape_threads(reasons.append, lambda: state["closing"], active=lambda: True, remote=lambda: True,
                                 bot_move_t=lambda: move_t["t"])
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    try:
        time.sleep(0.5)  # hooks + hotkey installed by the loop
        t0 = time.time()
        for _ in range(4):
            mouse_move(10, 0)
            time.sleep(0.01)
        assert wait_for(lambda: any("remote mouse" in r for r in reasons)), reasons
        print(f"SendInput mouse 40 px -> {reasons[-1]!r} in {1000 * (time.time() - t0):.0f} ms")
        time.sleep(0.6)  # loop re-arms the watch (still "hunting" here)
        n = len(reasons)
        key(hk.VK_ESCAPE)
        assert wait_for(lambda: len(reasons) > n), reasons
        print(f"SendInput ESC -> {reasons[n:]}")
        # Not injected at all (SetCursorPos; like a driver-level remote tool or a person at the PC): CursorWatch.
        time.sleep(0.6)
        n = len(reasons)
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt2 := wintypes.POINT()))
        ctypes.windll.user32.SetCursorPos(pt2.x + 60, pt2.y + 40)
        assert wait_for(lambda: len(reasons) > n), reasons
        print(f"SetCursorPos +100 px (no injected flag) -> {reasons[n:]}")
    finally:
        ctypes.windll.user32.SetCursorPos(pt.x, pt.y)
        state["closing"] = True
        ev.set()
        time.sleep(0.1)
    print("remote stop OK")


if __name__ == "__main__":
    main()
