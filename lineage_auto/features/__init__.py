"""Bot behaviours.

Each feature lives in its own module and only talks to the BotContext it is
given. New behaviour = a new module here plus a call site in
runtime/session.py. Buff upkeep: BuffFeature. Skills that cost MP
are gated by ``BotContext.can_cast``.
"""

from .base import Feature
from .buff import BuffFeature
from .combat import CombatFeature
from .cure_poison import CurePoisonFeature
from .exploration import ExplorationFeature
from .loot import LootFeature
from .survival import HealthFeature
from .targeting import Target, TargetingFeature, pick_retarget_stage

FEATURES = (HealthFeature, TargetingFeature, CombatFeature, ExplorationFeature)

__all__ = [
    "Feature",
    "BuffFeature",
    "CurePoisonFeature",
    "HealthFeature",
    "TargetingFeature",
    "CombatFeature",
    "ExplorationFeature",
    "LootFeature",
    "Target",
    "pick_retarget_stage",
    "FEATURES",
]
