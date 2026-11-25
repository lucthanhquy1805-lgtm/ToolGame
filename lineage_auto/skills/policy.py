"""Which catalog skills are allowed for auto-use in the current product phase.

Every skill will eventually need its own activation rule (timer, HUD icon,
status effect, target click, …). This module is the single allow-list and the
place to document those rules so later features can branch cleanly per
``skill_id`` instead of treating every buff as “press on a timer”.
"""

from __future__ import annotations

# Basic self-heal (Hồi Máu). The only heal the HP panel drives.
HEAL_SKILL_ID = "383"

# Other recovery skills: catalogued, shown in the Buff tab, not automated yet.
OTHER_HEAL_SKILL_IDS = frozenset({"395", "405", "413", "422", "796", "799"})

# Skills the runtime may press on its own.
AUTO_ENABLED_SKILL_IDS = frozenset({"383", "385", "388", "391", "397"})

# Skills the setup modal lets the user assign to a hotkey.
MODAL_ASSIGNABLE_SKILL_IDS = frozenset({"385", "388", "391", "397"})

# PLAN 1.6: the mechanism every role="attack" skill uses (see AccountSettings.cast_order for the click order).
ATTACK_MECHANISM = {
    "kind": "target_click",
    "summary": "Hover/press the hotkey and click the locked mob; gated by the slot's min MP%, range and cooldown.",
    "runtime": "wired",
}

USE_MECHANISM = {
    "383": {
        "kind": "hp_threshold",
        "summary": "Press heal hotkey when HP% is below the HP panel threshold "
        "(existing HealthFeature). Only skill id 383 — other heals are not wired here.",
    },
    "395": {
        "kind": "advanced_heal",
        "summary": "Greater Heal — different cast rules than 383; not on HP panel. "
        "Parked in Buff tab as WIP.",
        "runtime": "disabled",
    },
    "405": {
        "kind": "advanced_heal",
        "summary": "Greater Heal (catalog twin) — WIP, Buff tab only.",
        "runtime": "disabled",
    },
    "413": {
        "kind": "advanced_heal",
        "summary": "Party heal — WIP, Buff tab only.",
        "runtime": "disabled",
    },
    "422": {
        "kind": "advanced_heal",
        "summary": "Resurrect / revive — WIP, Buff tab only.",
        "runtime": "disabled",
    },
    "799": {
        "kind": "advanced_heal",
        "summary": "Nature's Touch — WIP, Buff tab only.",
        "runtime": "disabled",
    },
    "796": {
        "kind": "advanced_heal",
        "summary": "Natures Blessing — WIP, Buff tab only.",
        "runtime": "disabled",
    },
    "385": {
        "kind": "maintain_buff",
        "summary": "Self-cast on Start; rebuff only when duration expires (no buff-bar icon checks).",
    },
    "391": {
        "kind": "maintain_buff",
        "summary": "Self-cast on Start; rebuff only when duration expires (no buff-bar icon checks).",
    },
    "397": {
        "kind": "maintain_buff",
        "summary": "Self-cast on Start; rebuff only when duration expires (no buff-bar icon checks).",
    },
    "388": {
        "kind": "status_present",
        "summary": "Cast Cure Poison when the HP bar fill turns green (poison tint). Never timer spam.",
        "runtime": "wired",
    },
}


_ATTACK_IDS = None


def attack_skill_ids() -> frozenset:
    """PLAN 1.6: every catalog skill with role "attack" may be cast on the locked target.

    Read from the catalog JSON with plain json so offline tools (and policy's importers) do not pull in cv2.
    All of them use the same mechanism - a key press plus a click on the mob - so a per-id list would only be a
    list of the catalog's own attack role.
    """
    global _ATTACK_IDS
    if _ATTACK_IDS is None:
        import json
        import pathlib

        path = pathlib.Path(__file__).resolve().parent.parent / "data" / "skills" / "skills_catalog.json"
        try:
            with open(path, encoding="utf-8") as handle:
                skills = json.load(handle).get("skills", [])
        except OSError:
            skills = []
        _ATTACK_IDS = frozenset(str(s["id"]) for s in skills if s.get("role") == "attack" and "id" in s)
    return _ATTACK_IDS


def is_auto_enabled(skill_id) -> bool:
    return str(skill_id) in AUTO_ENABLED_SKILL_IDS or str(skill_id) in attack_skill_ids()


def is_modal_assignable(skill_id) -> bool:
    return str(skill_id) in MODAL_ASSIGNABLE_SKILL_IDS or str(skill_id) in attack_skill_ids()


def use_mechanism(skill_id) -> dict:
    if str(skill_id) in attack_skill_ids():
        return dict(ATTACK_MECHANISM)
    return dict(
        USE_MECHANISM.get(
            str(skill_id),
            {
                "kind": "disabled",
                "summary": "Not enabled in this product phase.",
                "runtime": "disabled",
            },
        )
    )
