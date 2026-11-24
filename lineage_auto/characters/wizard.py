"""Pháp Sư — 마법사 / Wizard.

Behaviour is v1's, identical to the other three classes. Per-class tuning goes
here once it is specified: override skill_interval, max_attack_bursts,
attack_cursor_label or add SkillTemplate entries.
"""

from .base import CharacterClass, CombatStyle

WIZARD = CharacterClass(
    key="wizard",
    name_ko="마법사",
    name_en="Wizard",
    name_vi="Pháp Sư",
    style=CombatStyle.CASTER,
)
