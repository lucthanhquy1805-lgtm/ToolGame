"""Hide the console window when launched via python.exe."""
import ctypes

SW_HIDE = 0


def hide_console():
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
            return True
    except Exception:
        return False
    return False


# PLAN 0.33: the detector thread runs non-stop next to the game; a below-normal process lets the client keep the
# CPU when 10-17 monsters are on screen (the game stuttered at 11:20 on 25/11 with the bot at ~2 cores).
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000


def set_below_normal_priority():
    try:
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        return bool(ctypes.windll.kernel32.SetPriorityClass(handle, BELOW_NORMAL_PRIORITY_CLASS))
    except Exception:
        return False
