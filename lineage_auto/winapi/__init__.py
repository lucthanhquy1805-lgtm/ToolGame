"""Thin wrappers over the Windows APIs the bot depends on.

Names are loaded lazily (PEP 562) and structs.py does not touch ``ctypes.windll`` off Windows, so offline
tools (tests/analyze_records.py on Linux) can import winapi.cursor helpers without Windows (PLAN 0.16).
"""
import importlib

_EXPORTS = {
    "hide_console": ".console",
    "CursorProbe": ".cursor",
    "ClientRect": ".window",
    "GameWindow": ".window",
    "WindowPicker": ".window",
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    if name in _EXPORTS:
        return getattr(importlib.import_module(_EXPORTS[name], __name__), name)
    raise AttributeError(name)
