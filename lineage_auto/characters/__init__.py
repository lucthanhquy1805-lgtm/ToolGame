"""Character class registry.

Register a new class by importing it and adding it to CLASSES.
"""

from .base import (
    HOTKEYS,
    SELF_TARGET_ROLES,
    CharacterClass,
    CombatStyle,
    SkillRole,
    SkillTemplate,
)
from .elf import ELF
from .knight import KNIGHT
from .prince import PRINCE
from .wizard import WIZARD

CLASSES = (PRINCE, KNIGHT, ELF, WIZARD)
DEFAULT_CLASS_KEY = KNIGHT.key

_BY_KEY = {c.key: c for c in CLASSES}


def all_classes():
    return CLASSES


# PLAN 1.10: a display name in the config must not silently read as the default class (and so as its
# attack_range / melee_max_sec). "Elf", "elf", "요정" and "Yêu Tinh" all mean ELF.
_BY_NAME = {n.lower(): c for c in CLASSES
            for n in (c.key, c.name_ko, c.name_en, c.name_vi)}


def get(key):
    return _BY_NAME.get(str(key or "").strip().lower(), _BY_KEY[DEFAULT_CLASS_KEY])


def keys():
    return tuple(_BY_KEY)


__all__ = [
    "CharacterClass",
    "CombatStyle",
    "SkillRole",
    "SkillTemplate",
    "SELF_TARGET_ROLES",
    "HOTKEYS",
    "CLASSES",
    "DEFAULT_CLASS_KEY",
    "all_classes",
    "get",
    "keys",
    "PRINCE",
    "KNIGHT",
    "ELF",
    "WIZARD",
]
