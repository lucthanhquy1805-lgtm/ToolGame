"""Global stop key. Works while the game client has focus.

`keyboard` WH_KEYBOARD_LL and GetAsyncKeyState often miss ESC once Interception
is in the stack or the game is elevated. RegisterHotKey is a true OS hotkey and
does not need the tool window focused. An Interception listen thread sees the
physical ESC even if the driver never injects it into Win32.

PLAN 0.7 (remote control through TeamViewer): a second configurable stop key,
a STOP file next to main.exe, and "the tool window got focus" all stop the bot.
Tested on the dev PC: keys injected with SendInput (what TeamViewer does) reach
both RegisterHotKey and GetAsyncKeyState, so both are used for the stop key.
"""

import os
import threading
import time

from .. import app_paths

VK_ESCAPE = 0x1B
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001
# Interception keyboard scan code / flag for ESC key-down.
ESC_SCAN = 0x01
KEY_UP = 0x01
HOTKEY_ID = 0x0E5C
STOP_HOTKEY_ID = 0x0E5D
STOP_FILE = "STOP"
STOP_FILE_POLL = 0.5
# PLAN 0.28: remote control (TeamViewer) injects input with SendInput; the bot's own input comes from the Interception
# driver and looks like hardware. While the bot holds the left button the game window has the mouse capture, so a
# remote click never reaches the Stop button / the tool window / a desktop shortcut. Injected input = stop.
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01
WM_MOUSEMOVE = 0x0200
REMOTE_MOVE_PX = 30  # injected mouse travel before it counts (a single 1 px nudge does not)
# PLAN 0.30: on the game PC the hooks were on ("remote input watch=True") but TeamViewer moves/clicks/ESC did not
# stop the bot. 1) the first SEEN_LOG_SEC of every hunt every hook event is logged (source, flags, extra info) to
# learn what TeamViewer sends; 2) CursorWatch: the cursor moved while the bot did not move it = someone else.
SEEN_LOG_SEC = 10.0
CURSOR_QUIET = 0.15  # s after the bot's last move before the cursor position is trusted as "where the bot left it"
CURSOR_DRIFT = 40  # px away from that position, with no bot move since = moved by a person (remote or local)


class CursorWatch:
    """Pure logic: feed (now, cursor position, time of the bot's last move); returns a stop reason or None."""

    def __init__(self, quiet=CURSOR_QUIET, drift=CURSOR_DRIFT):
        self.quiet, self.drift = quiet, drift
        self.anchor = None
        self.anchor_move_t = None

    def update(self, now, pos, move_t):
        if pos is None:
            return None
        if self.anchor is None or move_t != self.anchor_move_t:
            if move_t is None or now - move_t >= self.quiet:  # the bot's move has landed
                self.anchor, self.anchor_move_t = pos, move_t
            return None
        d = abs(pos[0] - self.anchor[0]) + abs(pos[1] - self.anchor[1])
        if d > self.drift:
            return f"mouse moved {d}px while the bot did not move it ({self.anchor} -> {tuple(pos)})"
        return None


def cursor_pos():
    try:
        import ctypes
        from ctypes import wintypes

        pt = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return pt.x, pt.y
    except Exception:
        pass
    return None


def key_is_down(vk):
    try:
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


def own_window_focused():
    """True when the foreground window belongs to this process (the tool UI)."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
        return pid.value == os.getpid()
    except Exception:
        return False


def stop_file_path():
    return app_paths.data_path(STOP_FILE)


def escape_is_down():
    return key_is_down(VK_ESCAPE)


def is_escape_key_down(scan_code, flags):
    """True for an Interception ESC make (not break)."""
    return int(scan_code) == ESC_SCAN and (int(flags) & KEY_UP) == 0


def poll_escape(ctx):
    """Request a session stop if ESC is held or the tool window took focus. Safe on mock contexts.

    Focus: the bot re-activates the game every loop and keeps moving the mouse, so a remote user
    could not click the Stop button (PLAN 0.7). Bringing the tool to the front now stops the bot.
    ``ctx.state["focus_stop_after"]`` (monotonic) arms it once the game had time to take focus.
    """
    if escape_is_down():
        reason = "ESC"
    else:
        armed = (getattr(ctx, "state", None) or {}).get("focus_stop_after")
        if armed is None or time.monotonic() < armed or not own_window_focused():
            return
        reason = "tool window focused"
    request = getattr(ctx, "request_stop", None)
    if callable(request):
        if getattr(ctx, "running", False) and callable(getattr(ctx, "log", None)):
            ctx.log(f"stop: {reason}")
        request()


class RemoteInputWatch:
    """Low-level mouse + keyboard hooks on the calling thread (it must pump messages, the hotkey loop does).

    ``fired`` becomes a reason string at the first injected click / key, or once injected mouse moves add up to
    REMOTE_MOVE_PX. The callbacks only set it: stopping happens on the pumping thread after PeekMessage."""

    def __init__(self):
        self.fired = None
        self._user32 = None
        self._hooks = []
        self._procs = []
        self._moved = 0
        self._last = None
        self.seen = []  # (kind, msg, flags, extra) while logging (PLAN 0.30)
        self.log_until = 0.0

    def install(self):
        import ctypes
        from ctypes import wintypes

        # Private DLL objects: setting argtypes on the shared ctypes.windll ones would clash with the
        # `keyboard` package, which declares the same functions with its own callback type.
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        lresult = ctypes.c_ssize_t
        proc_t = ctypes.WINFUNCTYPE(lresult, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.SetWindowsHookExW.argtypes = (ctypes.c_int, proc_t, wintypes.HINSTANCE, wintypes.DWORD)
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.restype = lresult
        user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)

        class MSLL(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long), ("data", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        class KBDLL(ctypes.Structure):
            _fields_ = [("vk", wintypes.DWORD), ("scan", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        def on_mouse(code, wparam, lparam):
            if code >= 0 and self.fired is None:
                info = ctypes.cast(lparam, ctypes.POINTER(MSLL)).contents
                if time.monotonic() < self.log_until:
                    self.seen.append(("mouse", int(wparam), int(info.flags), int(info.extra)))
                if info.flags & LLMHF_INJECTED:
                    if wparam != WM_MOUSEMOVE:
                        self.fired = "remote mouse click (injected input, e.g. TeamViewer)"
                    else:
                        if self._last is not None:
                            self._moved += abs(info.x - self._last[0]) + abs(info.y - self._last[1])
                        self._last = (info.x, info.y)
                        if self._moved >= REMOTE_MOVE_PX:
                            self.fired = "remote mouse move (injected input, e.g. TeamViewer)"
            return user32.CallNextHookEx(None, code, wparam, lparam)

        def on_key(code, wparam, lparam):
            if code >= 0 and self.fired is None:
                info = ctypes.cast(lparam, ctypes.POINTER(KBDLL)).contents
                if time.monotonic() < self.log_until:
                    self.seen.append((f"key 0x{info.vk:02X}", int(wparam), int(info.flags), int(info.extra)))
                if info.flags & LLKHF_INJECTED and not info.flags & 0x80:  # injected key-down
                    self.fired = f"remote key 0x{info.vk:02X} (injected input, e.g. TeamViewer)"
            return user32.CallNextHookEx(None, code, wparam, lparam)

        module = kernel32.GetModuleHandleW(None)
        for kind, fn in ((WH_MOUSE_LL, on_mouse), (WH_KEYBOARD_LL, on_key)):
            proc = proc_t(fn)
            hook = user32.SetWindowsHookExW(kind, proc, module, 0)
            if hook:
                self._procs.append(proc)
                self._hooks.append(hook)
            else:
                print(f"[HOTKEY] remote input hook {kind} failed: error {ctypes.get_last_error()}")
        self._user32 = user32
        return len(self._hooks) == 2

    def uninstall(self):
        try:
            for hook in self._hooks:
                self._user32.UnhookWindowsHookEx(hook)
        except Exception:
            pass
        self._hooks, self._procs = [], []
        self.fired, self._moved, self._last = None, 0, None
        self.seen, self.log_until = [], 0.0

    def flush_seen(self):
        """One log line per second while logging: what the hooks saw, grouped (PLAN 0.30)."""
        if not self.seen:
            return
        seen, self.seen = self.seen, []
        groups = {}
        for item in seen:
            groups[item] = groups.get(item, 0) + 1
        text = ", ".join(f"{k} msg=0x{m:04X} flags=0x{f:X} extra=0x{e:X} x{n}" for (k, m, f, e), n in groups.items())
        print(f"[HOTKEY] input seen: {text}")


def install_escape_hotkey(hotkey_id=HOTKEY_ID, vk=VK_ESCAPE):
    """Register a thread-local OS hotkey. Call from the pump thread."""
    try:
        import ctypes

        return bool(ctypes.windll.user32.RegisterHotKey(None, hotkey_id, 0, vk))
    except Exception:
        return False


def uninstall_escape_hotkey(hotkey_id=HOTKEY_ID):
    try:
        import ctypes

        ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)
    except Exception:
        return


def pump_escape_hotkey():
    """Drain WM_HOTKEY for this thread. Returns the set of hotkey ids that fired."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        msg = wintypes.MSG()
        fired = set()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            if msg.message == WM_HOTKEY:
                fired.add(int(msg.wParam))
            else:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        return fired
    except Exception:
        return set()


def _listen_interception_escape(stop_event, on_escape, active=None):
    """Pump the same Interception context the bot sends on, only while ``active()`` (hunting).

    PLAN 0.14: the filter is held only while a hunt runs (observe mode never captures keys), and it
    takes key-down AND key-up so every stroke goes back out through one queue in its original order
    (down-only filtering let the up overtake the down). Every stroke is forwarded.
    """
    try:
        from interception.constants import FilterKeyFlag
        from interception.inputs import _g_context
        from interception.strokes import KeyStroke
    except Exception:
        return
    if not getattr(_g_context, "valid", False):
        return
    active = active or (lambda: True)
    filtering = False

    def set_filter(on):
        try:
            flag = FilterKeyFlag.FILTER_KEY_ALL if on else FilterKeyFlag.FILTER_KEY_NONE
            _g_context.set_filter(_g_context.is_keyboard, flag)
            return on
        except Exception:
            return False

    try:
        while not stop_event.is_set():
            try:
                want = bool(active())
                if want != filtering:
                    filtering = set_filter(want)
                if not filtering:
                    stop_event.wait(0.1)
                    continue
                device = _g_context.await_input(timeout_milliseconds=50)
                if device is None:
                    continue
                stroke = _g_context.devices[device].receive()
                if stroke is None:
                    continue
                # Forward first: the filter captured the key, dropping or delaying it would eat input.
                try:
                    _g_context.send(device, stroke)
                except Exception:
                    pass
                if isinstance(stroke, KeyStroke) and is_escape_key_down(stroke.code, stroke.flags):
                    try:
                        on_escape("ESC (Interception keyboard)")
                    except Exception:
                        pass
            except Exception:
                stop_event.wait(0.1)
    finally:
        set_filter(False)


def start_escape_threads(on_escape, closing, stop_vk=None, on_stop=None, active=None, remote=None,
                         bot_move_t=None):
    """OS hotkey pump + optional Interception listen. Returns a stop Event.

    ``on_escape(reason)`` stops the hunt. ``remote()`` = injected input should stop it (PLAN 0.28: only with the
    Interception backend; the pyautogui fallback injects the bot's own input); hooks are on only while hunting.
    ``bot_move_t()`` = monotonic time of the bot's last mouse move (CursorWatch, PLAN 0.30).

    ``stop_vk()`` gives the current second stop key (re-registered when it changes);
    ``on_stop(reason)`` fires for that key and for the STOP file, which is then deleted.
    ``active()`` = a hunt is running. ESC is a hotkey only then: RegisterHotKey swallows the key,
    and the player needs ESC in game while the tool is idle or only observing (PLAN 0.14).
    """
    stop_event = threading.Event()
    active = active or (lambda: True)

    def hotkey_loop():
        vk_now, next_file_check, esc_want = 0, 0.0, False
        watch, watching = RemoteInputWatch(), False
        cursor_watch, next_flush = CursorWatch(), 0.0
        try:
            while not closing() and not stop_event.is_set():
                try:
                    want = bool(active())
                    want_watch = want and bool(remote and remote())
                    if want_watch != watching:
                        if want_watch:
                            print(f"[HOTKEY] remote input watch={watch.install()} (input seen is logged "
                                  f"{SEEN_LOG_SEC:.0f}s; cursor watch={'on' if bot_move_t else 'off'})")
                            watch.log_until = time.monotonic() + SEEN_LOG_SEC
                            cursor_watch = CursorWatch()
                        else:
                            watch.uninstall()
                        watching = want_watch
                    if want != esc_want:
                        esc_want = want
                        if want:
                            print(f"[HOTKEY] ESC registered={install_escape_hotkey()}")
                        else:
                            uninstall_escape_hotkey()
                            print("[HOTKEY] ESC released (not hunting)")
                    vk = (stop_vk() if stop_vk else 0) or 0
                    if vk != vk_now:
                        uninstall_escape_hotkey(STOP_HOTKEY_ID)
                        ok = install_escape_hotkey(STOP_HOTKEY_ID, vk) if vk else False
                        print(f"[HOTKEY] stop key 0x{vk:02X} registered={ok}")
                        vk_now = vk
                    fired = pump_escape_hotkey()
                    now = time.monotonic()
                    if watching and now >= next_flush:
                        next_flush = now + 1.0
                        watch.flush_seen()
                    if watching and bot_move_t and not watch.fired:
                        watch.fired = cursor_watch.update(now, cursor_pos(), bot_move_t())
                    if watching and watch.fired:
                        watch.flush_seen()
                        reason, watch.fired = watch.fired, None
                        watch.uninstall()
                        watching = False
                        on_escape(reason)
                        time.sleep(0.3)
                    if HOTKEY_ID in fired or (esc_want and escape_is_down()):
                        on_escape("ESC hotkey" if HOTKEY_ID in fired else "ESC (polled)")
                        time.sleep(0.3)
                    if on_stop and vk_now and (STOP_HOTKEY_ID in fired or key_is_down(vk_now)):
                        on_stop("stop key" if STOP_HOTKEY_ID in fired else "stop key (polled)")
                        time.sleep(0.3)
                    now = time.monotonic()
                    if on_stop and now >= next_file_check:
                        next_file_check = now + STOP_FILE_POLL
                        path = stop_file_path()
                        if os.path.exists(path):
                            on_stop("STOP file")
                            try:
                                os.remove(path)
                            except OSError:
                                pass
                except Exception:
                    pass
                time.sleep(0.02)
        finally:
            watch.uninstall()
            uninstall_escape_hotkey()
            uninstall_escape_hotkey(STOP_HOTKEY_ID)

    threading.Thread(target=hotkey_loop, daemon=True, name="esc-hotkey").start()
    threading.Thread(
        target=_listen_interception_escape,
        args=(stop_event, on_escape, active),
        daemon=True,
        name="esc-interception",
    ).start()
    return stop_event


# ---- cursor registration hotkeys (PLAN 0.11 v5) ----
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
# Game / bot keys that must never become a registration hotkey.
_FORBIDDEN = {f"f{n}" for n in range(1, 13)} | {"esc", "escape", "pause"}


def parse_hotkey(text):
    """'Ctrl+Alt+1' -> (mods, vk). None for an empty/invalid key, a key without Ctrl/Alt,
    or F1-F12 / ESC / Pause (used by the game and the bot)."""
    parts = [p.strip().lower() for p in str(text or "").split("+") if p.strip()]
    if not parts:
        return None
    *mods, key = parts
    if key in _FORBIDDEN or any(m not in _MODS for m in mods):
        return None
    flags = 0
    for m in mods:
        flags |= _MODS[m]
    if not flags & (MOD_CONTROL | MOD_ALT):
        return None  # a bare digit/letter would fire while typing in the game chat
    if len(key) == 1 and key.isalnum():
        return flags, ord(key.upper())
    if key.startswith("num") and len(key) == 4 and key[3].isdigit():
        return flags, 0x60 + int(key[3])
    return None


class HotkeyListener:
    """OS hotkeys on their own thread (RegisterHotKey is per thread); ``on_fire(name)`` runs there.

    bindings: {name: "Ctrl+Alt+1"}. After start(), ``registered`` lists the names the OS accepted."""

    BASE_ID = 0x0E60

    def __init__(self, bindings, on_fire):
        self.bindings = dict(bindings)
        self.on_fire = on_fire
        self.registered = []
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cursor-hotkeys")

    def start(self):
        self._thread.start()
        self._ready.wait(1.0)
        return self.registered

    def stop(self):
        self._stop.set()
        self._thread.join(1.0)

    def _loop(self):
        ids = {}
        try:
            for index, (name, text) in enumerate(self.bindings.items()):
                parsed = parse_hotkey(text)
                if parsed is None:
                    continue
                hid = self.BASE_ID + index
                try:
                    import ctypes

                    ok = bool(ctypes.windll.user32.RegisterHotKey(None, hid, parsed[0] | MOD_NOREPEAT, parsed[1]))
                except Exception:
                    ok = False
                if ok:
                    ids[hid] = name
                    self.registered.append(name)
            self._ready.set()
            while not self._stop.is_set():
                for hid in pump_escape_hotkey():
                    if hid in ids:
                        try:
                            self.on_fire(ids[hid])
                        except Exception as exc:
                            print(f"[HOTKEY] cursor hotkey error: {exc}")
                time.sleep(0.02)
        finally:
            self._ready.set()
            for hid in ids:
                uninstall_escape_hotkey(hid)


def beep(ok=True):
    try:
        import winsound

        winsound.Beep(1200 if ok else 400, 120)
    except Exception:
        pass
