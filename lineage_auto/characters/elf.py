"""Yêu Tinh / Tiên — 요정 / Elf.

Behaviour is v1's, identical to the other three classes. Per-class tuning goes
here once it is specified: override skill_interval, max_attack_bursts,
attack_cursor_label or add SkillTemplate entries.

Known future difference: with a bow equipped the attack cursor is an arrow, so
this class may point attack_cursor_label at "cursor_attack_bow" later. Until
then the cursor is registered per account, which already covers any shape.
"""

from .base import CharacterClass, CombatStyle

ELF = CharacterClass(
    key="elf",
    name_ko="요정",
    name_en="Elf",
    name_vi="Yêu Tinh",
    style=CombatStyle.HYBRID,
)
