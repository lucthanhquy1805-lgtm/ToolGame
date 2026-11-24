"""Kỵ Sĩ — 기사 / Knight.

Behaviour is v1's, identical to the other three classes. Per-class tuning goes
here once it is specified: override skill_interval, max_attack_bursts,
attack_cursor_label or add SkillTemplate entries.
"""

from .base import CharacterClass, CombatStyle

KNIGHT = CharacterClass(
    key="knight",
    name_ko="기사",
    name_en="Knight",
    name_vi="Kỵ Sĩ",
    style=CombatStyle.MELEE,
)
