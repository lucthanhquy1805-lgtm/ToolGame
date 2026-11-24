"""Game window discovery and geometry."""
import ctypes
import ctypes.wintypes
import os
import time
from dataclasses import dataclass

import win32con
import win32gui
import win32process

GAME_TITLE_HINTS = ("lineage", "리니지")
IDE_TITLE_HINTS = ("cursor", "visual studio", "code", ".py", "pycharm")
# The Lineage Classic client exe (PLAN A10: "Program Files (x86)/NC/Lineage Classic/LC.exe").
GAME_EXE_NAMES = ("lc.exe",)
# Never the game, even with "lineage" in the title (a folder or web page named after it).
NON_GAME_EXE_NAMES = (
    "explorer.exe", "chrome.exe", "msedge.exe", "firefox.exe", "whale.exe", "opera.exe", "brave.exe",
    "teamviewer.exe", "tv_w32.exe", "tv_x64.exe", "notepad.exe", "code.exe", "cursor.exe",
    "python.exe", "pythonw.exe", "main.exe", "windowsterminal.exe", "cmd.exe", "powershell.exe",
)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def process_exe(pid):
    """Lower-case exe file name of a process, "" if unreadable.

    The limited-information right also works on an elevated game client.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.wintypes.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        pass
    return ""


@dataclass(frozen=True)
class ClientRect:
    """Screen position and size of a window's client area."""

    x: int
    y: int
    w: int
    h: int

    def to_monitor(self):
        return {"top": self.y, "left": self.x, "width": self.w, "height": self.h}

    def to_screen(self, local_x, local_y):
        return self.x + int(local_x), self.y + int(local_y)


class WindowPicker:
    @staticmethod
    def _owned_by_us(hwnd):
        """True for our own windows.

        The tool's title contains "Lineage" too, so without this check it can
        pick itself as the game window.
        """
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return pid == os.getpid()
        except Exception:
            return False

    @staticmethod
    def list_windows():
        """Visible top-level windows as {"title (WxH) [exe:pid]": hwnd}, ours excluded.

        The pid keeps two clients with the same title apart (two characters on one PC).
        """
        windows = {}

        def callback(hwnd, _extra):
            if win32gui.IsWindowVisible(hwnd) and not WindowPicker._owned_by_us(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                w, h = right - left, bottom - top
                if title and w > 100 and h > 100:
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    except Exception:
                        pid = 0
                    exe = process_exe(pid) if pid else ""
                    windows[f"{title} ({w}x{h}) [{exe or '?'}:{pid}]"] = hwnd
            return True

        win32gui.EnumWindows(callback, None)
        return windows

    @staticmethod
    def label_exe(label):
        """Exe name from a list_windows label, "" for old labels without one."""
        if not label.endswith("]") or " [" not in label:
            return ""
        return label.rsplit(" [", 1)[1][:-1].rsplit(":", 1)[0].lower()

    @staticmethod
    def guess_game_titles(windows):
        """LC.exe windows; if none, Lineage-looking titles that are not a known non-game app."""
        by_exe = [label for label in windows if WindowPicker.label_exe(label) in GAME_EXE_NAMES]
        if by_exe:
            return by_exe
        picks = []
        for label in windows:
            low = label.lower()
            if WindowPicker.label_exe(label) in NON_GAME_EXE_NAMES:
                continue
            if any(bad in low for bad in IDE_TITLE_HINTS):
                continue
            if any(hint in low for hint in GAME_TITLE_HINTS):
                picks.append(label)
        return picks


class GameWindow:
    """A single game client. One per account."""

    def __init__(self, hwnd=None, title=""):
        self.hwnd = hwnd
        self.title = title

    @property
    def attached(self):
        return bool(self.hwnd)

    def is_alive(self):
        try:
            return bool(self.hwnd) and win32gui.IsWindow(self.hwnd)
        except Exception:
            return False

    def client_rect(self):
        try:
            origin = win32gui.ClientToScreen(self.hwnd, (0, 0))
            _, _, w, h = win32gui.GetClientRect(self.hwnd)
            return ClientRect(origin[0], origin[1], w, h)
        except Exception:
            return ClientRect(0, 0, 1280, 960)

    def activate(self):
        try:
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.05)
            return True
        except Exception:
            return False

    def is_foreground(self):
        try:
            return win32gui.GetForegroundWindow() == self.hwnd
        except Exception:
            return False
