"""Screen capture and image analysis.

Names load lazily (PEP 562, like winapi/__init__) so offline tools that only need one submodule
(tests/analyze_records.py on Linux) do not pull mss through capture.py (PLAN 0.27d).
"""
import importlib

_EXPORTS = {
    "DEFAULT_BUFF_VISION": ".buff_icons",
    "MissStreak": ".buff_icons",
    "best_match_score": ".buff_icons",
    "buff_bar_roi": ".buff_icons",
    "crop_hotbar_icon": ".buff_icons",
    "hotbar_slot_rect": ".buff_icons",
    "icon_present_in_buff_bar": ".buff_icons",
    "merge_buff_vision": ".buff_icons",
    "ScreenGrabber": ".capture",
    "DeathWatch": ".motion_watch",
    "roi_motion_score": ".motion_watch",
    "Nameplate": ".nameplate",
    "NameplateScanner": ".nameplate",
    "motion_centroids": ".play_motion",
    "track_white_name": ".play_motion",
    "CONF_THRESH": ".yolox_mobs",
    "DETECT_CONF": ".yolox_mobs",
    "IOU_THRESH": ".yolox_mobs",
    "detect_centers": ".yolox_mobs",
    "DEFAULT_POISON_VISION": ".poison",
    "PresentStreak": ".poison",
    "character_roi": ".poison",
    "merge_poison_vision": ".poison",
    "poison_green_ratio": ".poison",
    "sprite_poison_candidate": ".poison",
    "BarColor": ".stat_bar",
    "StatBarReader": ".stat_bar",
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    if name in _EXPORTS:
        return getattr(importlib.import_module(_EXPORTS[name], __name__), name)
    raise AttributeError(name)
