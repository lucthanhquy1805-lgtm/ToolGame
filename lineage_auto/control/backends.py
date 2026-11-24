r"""Interchangeable input backends.

Interception is the only channel the game reliably accepts; pyautogui stays as
a degraded fallback for testing outside the client.

Needs the ``interception-python`` package (``auto_capture_devices`` / ``move_to``),
not the PyPI ``interception`` cffi bindings. Devices are not hardcoded: capture
scans ``\\.\interception00``–``19`` and keeps the first keyboard and mouse
that report a hardware id. The official ``interception.dll`` is unused — this
stack talks to the kernel driver directly.
"""

import time
from abc import ABC, abstractmethod

import pyautogui


def _usable_interception(module):
    """Reject cffi-only wheels that import as ``interception`` but have no input API."""
    if module is None:
        return None
    if not hasattr(module, "auto_capture_devices") or not hasattr(module, "move_to"):
        return None
    return module


try:
    import interception as _interception_mod
except ImportError:
    _interception_mod = None

interception = _usable_interception(_interception_mod)
INTERCEPTION_AVAILABLE = interception is not None
if _interception_mod is not None and interception is None:
    print(
        "[INPUT] interception package is not interception-python "
        "(missing auto_capture_devices); cannot use driver"
    )


class InputBackend(ABC):
    name = "base"
    trusted = False

    @abstractmethod
    def move(self, x, y):
        pass

    @abstractmethod
    def mouse_down(self, button="left"):
        pass

    @abstractmethod
    def mouse_up(self, button="left"):
        pass

    @abstractmethod
    def click(self, button="left"):
        pass

    @abstractmethod
    def press(self, key):
        pass

    def key_up(self, key):
        """Release a key (PLAN 0.14 stop/exit cleanup). No-op where the backend cannot."""


class InterceptionBackend(InputBackend):
    name = "interception"
    trusted = True

    def __init__(self):
        interception.auto_capture_devices(keyboard=True, mouse=True)

    def move(self, x, y):
        interception.move_to(int(x), int(y))

    def mouse_down(self, button="left"):
        interception.mouse_down(button)

    def mouse_up(self, button="left"):
        interception.mouse_up(button)

    def click(self, button="left"):
        interception.click(button=button, delay=0.04)

    def press(self, key):
        interception.press(str(key).lower())

    def key_up(self, key):
        interception.key_up(str(key).lower())


class PyAutoGuiBackend(InputBackend):
    name = "pyautogui"
    trusted = False

    def move(self, x, y):
        pyautogui.moveTo(int(x), int(y))

    def mouse_down(self, button="left"):
        pyautogui.mouseDown(button=button)

    def mouse_up(self, button="left"):
        pyautogui.mouseUp(button=button)

    def click(self, button="left"):
        pyautogui.click(button=button)
        time.sleep(0.02)

    def press(self, key):
        pyautogui.press(str(key).lower())

    def key_up(self, key):
        pyautogui.keyUp(str(key).lower())


def create_backend():
    """Best available backend. Interception first, pyautogui otherwise."""
    if INTERCEPTION_AVAILABLE:
        try:
            backend = InterceptionBackend()
            keyboard = interception.get_keyboard()
            mouse = interception.get_mouse()
            print(f"[INPUT] interception ready (keyboard={keyboard} mouse={mouse})")
            return backend
        except Exception as exc:
            print(f"[INPUT] interception unavailable: {exc}")
    print("[INPUT] falling back to pyautogui (may be blocked in game)")
    return PyAutoGuiBackend()
