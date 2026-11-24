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
