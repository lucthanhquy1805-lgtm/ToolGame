"""Per-account execution.

Names are loaded lazily (PEP 562): importing ``lineage_auto.runtime.cursor_profile`` from an
offline tool (tests/analyze_records.py) must not pull in control/ (pyautogui, Interception).
"""
import importlib

_EXPORTS = {
    "BotContext": ".context",
    "CursorProfile": ".cursor_profile",
    "SessionManager": ".manager",
    "AccountSession": ".session",
    "SessionState": ".session",
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    if name in _EXPORTS:
        return getattr(importlib.import_module(_EXPORTS[name], __name__), name)
    raise AttributeError(name)
