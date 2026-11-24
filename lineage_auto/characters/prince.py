"""Quân Chủ — 군주 / Prince (Princess).

Behaviour is v1's, identical to the other three classes. Per-class tuning goes
here once it is specified: override skill_interval, max_attack_bursts,
attack_cursor_label or add SkillTemplate entries.
"""

from .base import CharacterClass, CombatStyle

PRINCE = CharacterClass(
    key="prince",
    name_ko="군주",
    name_en="Prince",
    name_vi="Quân Chủ",
    style=CombatStyle.MELEE,
)
