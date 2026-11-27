"""Character class model.

Right now all four classes behave exactly like auto_lineage_classic_v1.py:
same skill cadence, same attack length, same empty hotkey layout. A class is
only an identity plus a set of tuning values, so giving one class its own
behaviour later means changing values in that one file — nothing in features/
or ui/ has to change.

The per-class values live in the class files rather than here so the diff for
"Wizard now casts faster" is a single line in wizard.py.
"""

from dataclasses import dataclass, field
from enum import Enum

# v1 timing, shared by every class until one gets its own numbers.
V1_SKILL_INTERVAL = 2.2
V1_MAX_ATTACK_BURSTS = 30
# v1 registers one attack cursor per account; a class may later point at a
# different label (an Elf with a bow shows an arrow instead of a sword).
V1_ATTACK_CURSOR_LABEL = "cursor_attack"


class CombatStyle(Enum):
    """Descriptive only. No feature reads this yet."""

    MELEE = "melee"
    ARCHER = "archer"
    CASTER = "caster"
    HYBRID = "hybrid"


class SkillRole(Enum):
    ATTACK = "attack"
    BUFF = "buff"
    HEAL = "heal"
    SUMMON = "summon"
    DEBUFF = "debuff"
    UTILITY = "utility"


SELF_TARGET_ROLES = (SkillRole.BUFF, SkillRole.HEAL, SkillRole.SUMMON)

HOTKEYS = tuple(f"F{i}" for i in range(5, 13))


@dataclass(frozen=True)
class SkillTemplate:
    """Suggested purpose of one hotkey for a class.

    No class ships templates yet, matching v1 where every hotkey starts off and
    the user decides what it does.
    """

    key: str
    role: SkillRole = SkillRole.ATTACK
    enabled: bool = False
    note_ko: str = ""
    note_en: str = ""

    @property
    def self_cast(self):
        return self.role in SELF_TARGET_ROLES


@dataclass(frozen=True)
class CharacterClass:
    key: str
    name_ko: str
    name_en: str
    name_vi: str

    style: CombatStyle

    attack_cursor_label: str = V1_ATTACK_CURSOR_LABEL
    # Seconds between attack-skill presses while locked on a target.
    skill_interval: float = V1_SKILL_INTERVAL
    # Upper bound of attack beats before the lock is dropped.
    max_attack_bursts: int = V1_MAX_ATTACK_BURSTS
    skills: tuple = field(default_factory=tuple)
    # PLAN 1.9: steps this class hits from by hand without walking (scan.attack_range 0 = this). 1 = next to it.
    attack_range: int = 1

    # Fields that change what the bot does (as opposed to how it is labelled).
    BEHAVIOUR_FIELDS = ("attack_cursor_label", "skill_interval", "max_attack_bursts", "skills")

    def display_name(self, lang="en"):
        return {"ko": self.name_ko, "vi": self.name_vi}.get(lang, self.name_en)

    def behaviour(self):
        """The tuning values that affect bot behaviour, for comparison."""
        return {name: getattr(self, name) for name in self.BEHAVIOUR_FIELDS}

    def skill_defaults(self):
        """{"F5": {"enabled": bool, "self_cast": bool, "role": str}} for all hotkeys."""
        by_key = {s.key: s for s in self.skills}
        defaults = {}
        for key in HOTKEYS:
            template = by_key.get(key)
            if template is None:
                defaults[key] = {
                    "enabled": False,
                    "self_cast": False,
                    "role": SkillRole.ATTACK.value,
                }
            else:
                defaults[key] = {
                    "enabled": template.enabled,
                    "self_cast": template.self_cast,
                    "role": template.role.value,
                }
        return defaults

    def note_for(self, key, lang="en"):
        for skill in self.skills:
            if skill.key == key:
                return skill.note_ko if lang == "ko" else skill.note_en
        return ""
