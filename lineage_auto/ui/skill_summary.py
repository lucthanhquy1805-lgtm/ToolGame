"""Skill setup summary text and modal apply validation."""

from __future__ import annotations

from ..characters.base import HOTKEYS
from ..skills.policy import is_auto_enabled


def _tr(translator, key, default):
    if translator is None:
        return default
    text = translator(key)
    return text if text != key else default


# A buff duration is typed in seconds (27/11, 10 s steps, label "giây"); the setting keeps minutes
# (``BuffSkillSetting.duration_min``), so an older config needs no migration: 11.5 min reads as 690 s.
BUFF_STEP_SEC = 10
BUFF_MIN_SEC = 10
BUFF_MAX_SEC = 86400


def buff_seconds(duration_min):
    """The stored buff duration as whole seconds (what the UI shows)."""
    return int(round(duration_min * 60))


def buff_duration_min(seconds):
    """Seconds typed in the UI back to the stored minutes, clamped to the spinbox range."""
    return max(BUFF_MIN_SEC, min(BUFF_MAX_SEC, float(seconds))) / 60.0


def _format_duration_minutes(duration_min):
    return f"{buff_seconds(duration_min)}s"


def _slot(setting, key):
    """How a slot reads in the summary: always page + key ("F2+F5"), so a wrong page is visible (PLAN 0.34)."""
    return f"{getattr(setting, 'page', 'F1')}+{key}"


def _skill_name(catalog, skill_id):
    entry = catalog.get(skill_id)
    if entry is None:
        return skill_id
    return entry.get("name_vi") or skill_id


HIGH_MIN_MP = 80  # PLAN 0.39: from this MP% a wizard is rarely full enough for the spell to ever fire


def high_min_mp_names(account, catalog):
    """Enabled attack slots whose MP% floor is >= HIGH_MIN_MP, as "F2+F5 name" (empty = nothing to warn)."""
    account.ensure_skill_maps()
    return [f"{_slot(a, key)} {_skill_name(catalog, a.skill_id)}" for key in HOTKEYS
            for a in [account.attack(key)]
            if a.enabled and a.skill_id and is_auto_enabled(a.skill_id) and a.min_mp >= HIGH_MIN_MP]


def format_skill_summary(account, catalog, t=None):
    """Build a compact enabled-slot summary for the account tab.

    Returns an empty string when no attack/buff/utility skills are enabled; the
    caller should show ``skill_summary_empty`` in that case.
    """
    account.ensure_skill_maps()

    buff_parts = []
    attack_parts = []
    utility_parts = []

    for key in HOTKEYS:
        buff = account.buff(key)
        if buff.enabled and buff.skill_id and is_auto_enabled(buff.skill_id):
            name = _skill_name(catalog, buff.skill_id)
            duration = _format_duration_minutes(buff.duration_min)
            buff_parts.append(f"{_slot(buff, key)} {name} ({duration})")

        attack = account.attack(key)
        if (
            attack.enabled
            and attack.skill_id
            and is_auto_enabled(attack.skill_id)
        ):
            name = _skill_name(catalog, attack.skill_id)
            attack_parts.append(f"{_slot(attack, key)} {name}")

        utility = account.utility(key)
        if not utility.enabled:
            continue
        if not utility.skill_id:
            continue
        if not is_auto_enabled(utility.skill_id):
            continue
        name = _skill_name(catalog, utility.skill_id)
        utility_parts.append(f"{_slot(utility, key)} {name}")

    segments = []
    if buff_parts:
        label = _tr(t, "tab_buff", "Buff")
        segments.append(f"{label}: {', '.join(buff_parts)}")
    if attack_parts:
        label = _tr(t, "tab_attack", "Attack")
        segments.append(f"{label}: {', '.join(attack_parts)}")
    if utility_parts:
        label = _tr(t, "tab_utility", "Utility")
        segments.append(f"{label}: {', '.join(utility_parts)}")

    return " · ".join(segments)


def _draft_fkey_map(draft):
    """Map assigned hotbar slots to draft keys for enabled entries.

    PLAN 0.34: a slot is (page, F-key) - F5 on page F1 and F5 on page F2 are different slots."""
    by_slot = {}
    for key, setting in draft.items():
        if not setting.enabled:
            continue
        f_key = key if key in HOTKEYS else getattr(setting, "f_key", "")
        if not f_key or f_key not in HOTKEYS:
            continue
        by_slot.setdefault((getattr(setting, "page", "F1"), f_key), []).append(key)
    return by_slot


def validate_skill_draft(attack_draft, buff_draft, utility_draft=None):
    """Validate modal or account-style draft maps before apply.

    Each draft is ``{key: setting}`` keyed by F-key (account layout) or catalog
    skill id (modal rows with ``setting.f_key``).

    Returns ``None`` when valid, ``"dup"`` when two enabled entries share an
    F-key within one role, or ``"overlap_ab"`` when two roles share an F-key.
    """
    drafts = [attack_draft, buff_draft]
    if utility_draft is not None:
        drafts.append(utility_draft)

    for draft in drafts:
        for keys in _draft_fkey_map(draft).values():
            if len(keys) > 1:
                return "dup"

    fkey_sets = [set(_draft_fkey_map(draft)) for draft in drafts]
    for index, left in enumerate(fkey_sets):
        for right in fkey_sets[index + 1:]:
            if left & right:
                return "overlap_ab"
    return None
