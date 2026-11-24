"""Filesystem locations.

Resolved relative to the executable when frozen by PyInstaller, otherwise to
the project root, so packaging does not change where users find their files.
"""

import os
import sys


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset_dir():
    """Read-only files shipped with the tool (templates)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", base_dir())
    return base_dir()


def data_path(name):
    return os.path.join(base_dir(), name)


def asset_path(name):
    """Sidecar next to the EXE wins so a dropped ``mp_template.png`` is used."""
    sidecar = data_path(name)
    if os.path.exists(sidecar):
        return sidecar
    packaged = os.path.join(asset_dir(), name)
    if os.path.exists(packaged):
        return packaged
    return sidecar


CONFIG_FILE = "lineage_auto_config.json"
LEGACY_CONFIG_FILE = "bot_config.json"
LOG_FILE = "session_log.txt"
HP_TEMPLATE = "hp_template.png"
MP_TEMPLATE = "mp_template.png"
