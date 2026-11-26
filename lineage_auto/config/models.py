"""Persisted settings.

Settings are per account, not global, so several characters can run side by
side with their own class, cursor hashes and skill layout.
"""

import math
import uuid
from dataclasses import asdict, dataclass, field

from .. import characters, hunt_maps
from ..characters.base import HOTKEYS

# Cursor shapes the bot tells apart. Only "attack" is required.
# PLAN 0.34: "cast" is the aiming ellipse the client shows after a spell hotkey is pressed - seeing it is how
# the bot knows the spell is armed and it may click the monster.
CURSOR_KINDS = ("attack", "corpse", "ground", "npc", "cast")

# v1/v2 config names for the same cursors.
LEGACY_CURSOR_ALIASES = {
    "sword": "attack",
    "cross": "corpse",
    "normal": "ground",
    "npc": "npc",
}

# Cursor registration hotkeys (PLAN 0.11 v5). Never F1-F12 / ESC / Pause (game + bot keys).
DEFAULT_CURSOR_KEYS = {"attack": "Ctrl+Alt+1", "corpse": "Ctrl+Alt+2", "ground": "Ctrl+Alt+3",
                       "npc": "Ctrl+Alt+4", "cast": "Ctrl+Alt+5"}


@dataclass
class SkillSetting:
    enabled: bool = False
    self_cast: bool = False
    role: str = "attack"

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            self_cast=bool(data.get("self_cast", False)),
            role=str(data.get("role", "attack")),
        )


# PLAN 1.6: how the client takes a targeted spell. The user can switch this on the game PC without a rebuild.
# PLAN 0.34, confirmed by the user from the game: press the slot key, the cursor turns into an aiming
# ellipse, then left-click the monster. "key_click" is therefore the default.
CAST_ORDERS = ("key_click", "hover_key_click", "click_key")

# PLAN 0.34: the game has three hotbar pages (F1/F2/F3), each with the eight slots F5-F12. A slot is therefore
# (page, key), not a key: page F1 is full of heal / potions / return scroll / buffs, so attack spells live on F2.
# A config older than v16 has only the key, which always meant the page the player had open: F1.
HOTBAR_PAGES = ("F1", "F2", "F3")


def hotbar_page(value, default=HOTBAR_PAGES[0]):
    page = str(value or "").upper()
    return page if page in HOTBAR_PAGES else default


@dataclass
class AttackSkillSetting:
    """One attack/utility hotkey. PLAN 1.6 adds the gates a spell needs: min MP%, max distance, own cooldown."""

    enabled: bool = False
    skill_id: str = ""
    page: str = HOTBAR_PAGES[0]  # PLAN 0.34: hotbar page this slot sits on
    min_mp: int = 0  # % MP below which this slot is skipped (hand attack instead); 0 = never skip
    range_px: int = 0  # max character->target distance in client px; 0 = any distance
    cooldown: float = 0.0  # s between two uses of this slot; 0 = the class skill_interval

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            skill_id=str(data.get("skill_id", "")),
            page=hotbar_page(data.get("page")),
            min_mp=min(100, max(0, int(data.get("min_mp", 0) or 0))),
            range_px=max(0, int(data.get("range_px", 0) or 0)),
            cooldown=max(0.0, float(data.get("cooldown", 0.0) or 0.0)),
        )


@dataclass
class BuffSkillSetting:
    enabled: bool = False
    duration_min: float = 20.0
    skill_id: str = ""
    page: str = HOTBAR_PAGES[0]

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        duration = float(data.get("duration_min", 20.0))
        return cls(
            enabled=bool(data.get("enabled", False)),
            duration_min=max(0.1, duration),
            skill_id=str(data.get("skill_id", "")),
            page=hotbar_page(data.get("page")),
        )


def _empty_attack_map():
    return {key: AttackSkillSetting() for key in HOTKEYS}


def _empty_buff_map():
    return {key: BuffSkillSetting() for key in HOTKEYS}


def _empty_utility_map():
    """Utility slots reuse AttackSkillSetting (enabled + skill_id, no duration)."""
    return {key: AttackSkillSetting() for key in HOTKEYS}


def migrate_legacy_skills(skills_dict):
    """v1/v2 ``{"F5": {"enabled", "self_cast"}}`` -> (attack map, buff map)."""
    attack = _empty_attack_map()
    buff = _empty_buff_map()
    for key, value in (skills_dict or {}).items():
        if key not in attack:
            continue
        raw = value or {}
        enabled = bool(raw.get("enabled", False))
        self_cast = bool(raw.get("self_cast", False))
        if not enabled:
            continue
        if self_cast:
            buff[key] = BuffSkillSetting(enabled=True, duration_min=20.0)
        else:
            attack[key] = AttackSkillSetting(enabled=True)
    return attack, buff


# PLAN 1.4: extra potion slots shown in the HP panel (the main potion stays potion_key).
EXTRA_POTION_SLOTS = 3


@dataclass
class PotionSetting:
    """One extra potion: drink `key` when HP or MP is below `pct`, at most every `cooldown` s."""

    enabled: bool = False
    stat: str = "hp"  # "hp" | "mp"
    key: str = "F7"
    page: str = HOTBAR_PAGES[0]
    pct: int = 50
    cooldown: float = 1.5

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            stat="mp" if data.get("stat") == "mp" else "hp",
            key=str(data.get("key", "F7")),
            page=hotbar_page(data.get("page")),
            pct=min(95, max(5, int(data.get("pct", 50)))),
            cooldown=max(0.2, float(data.get("cooldown", 1.5))),
        )


def _potion_slots(items):
    slots = [PotionSetting.from_dict(d) for d in (items or [])[:EXTRA_POTION_SLOTS]]
    return slots + [PotionSetting() for _ in range(EXTRA_POTION_SLOTS - len(slots))]


@dataclass
class HealthSettings:
    threshold_pct: int = 50
    use_skill: bool = True
    skill_key: str = "F5"
    skill_page: str = HOTBAR_PAGES[0]
    use_potion: bool = True
    potion_key: str = "F6"
    potion_page: str = HOTBAR_PAGES[0]
    # PLAN 0.3: exact "HP:x/y" / "MP:x/y" from the HUD text, bar reading as fallback.
    read_hud_numbers: bool = True
    # PLAN 1.3 (A5): return scroll (귀환 주문서) below this HP, then stop. Off = old behaviour.
    return_town: bool = False
    return_pct: int = 35
    return_key: str = "F8"
    return_page: str = HOTBAR_PAGES[0]
    potions: list = field(default_factory=lambda: _potion_slots(None))

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            threshold_pct=int(data.get("threshold_pct", 50)),
            use_skill=bool(data.get("use_skill", True)),
            skill_key=str(data.get("skill_key", "F5")),
            skill_page=hotbar_page(data.get("skill_page")),
            use_potion=bool(data.get("use_potion", True)),
            potion_key=str(data.get("potion_key", "F6")),
            potion_page=hotbar_page(data.get("potion_page")),
            read_hud_numbers=bool(data.get("read_hud_numbers", True)),
            return_town=bool(data.get("return_town", False)),
            return_pct=min(90, max(5, int(data.get("return_pct", 35)))),
            return_key=str(data.get("return_key", "F8")),
            return_page=hotbar_page(data.get("return_page")),
            potions=_potion_slots(data.get("potions")),
        )


MAX_PROBE_POINTS = 2
INPUT_SIZES = (320, 416, 640)
HUNT_RANGES = (0, 1, 3, 5, 10, 15, 20, 30)  # PLAN 1.2: hunt range in steps; 0 = no limit, 1 = stay put


@dataclass
class ScanSettings:
    """Target scan tuning (PLAN 0.1). Timings in seconds."""

    misses_before_wander: int = 2
    max_probe_points: int = 2  # PLAN 0.31: hover-confirm only the 1-2 nearest boxes (MAX_PROBE_POINTS)
    hover_settle: float = 0.04
    hover_retry: float = 0.04
    hover_reads: int = 4
    miss_ttl: float = 4.0
    detect_conf: float = 0.0  # 0 = the hunt map's YOLOX threshold
    # PLAN 0.27: the hunt map detect_conf was typed for. A value from another map (or from a config
    # older than v12, e.g. 0.5 typed for Dragon Valley) is ignored: the zone's model uses its own conf.
    conf_map: str = ""
    # PLAN 0.31: detector thread rate, ONNX input side (model/<name>_<size>.onnx, 640 if not exported), crop the play
    # area around the character, and the longest melee (target < 70 px + attack cursor) before leaving it.
    # PLAN 0.32: the ROI 416 of v14 saw 1.97 boxes/frame against 4.87 for the full 640 frame (it missed far
    # monsters, e.g. the orc at (1150, 300) of 092741/f_00026) -> full frame 640 again, melee cap 10 s.
    # PLAN 0.33: 5/s of full 640 frames cost ~0.9 core non-stop on the game PC and made the client stutter when
    # 10-17 monsters were on screen. 2/s is the cap now; ``adaptive_detect`` crops to the play area while a fight
    # is running (near boxes only are needed then) and drops the rate further when a detect costs more CPU than
    # CPU_SHARE of one core. ``detect_threads`` is onnxruntime's intra_op threads (1 = one core).
    detect_fps: int = 2
    detect_threads: int = 1  # onnxruntime threads while fighting (the cheap crop, next to the game)
    search_threads: int = 2  # PLAN 0.34: full 640 frame while searching; one thread cannot keep 2/s
    adaptive_detect: bool = True
    input_size: int = 640
    detect_roi: bool = False
    melee_max_sec: float = 10.0
    # PLAN 1.2: how far from the start point the bot hunts, in character steps (map tiles): 0 = no limit,
    # 1 = stay put (only monsters that come to us). Needs the game minimap (odometry); without it the range
    # is ignored and the UI says so.
    hunt_range: int = 0

    @staticmethod
    def _detect_v15(data):
        """PLAN 0.32: the v14 trio (416 + ROI + 25 s melee) is read back as "not chosen" and reset.

        It cost ~60% of the boxes and held 16 fights of 092741 standing for 25 s; a config saved by v14 carries
        it even on the game PC. Any other value the user typed is kept."""
        size = int(data.get("input_size", 640))
        roi = bool(data.get("detect_roi", False))
        melee = float(data.get("melee_max_sec", 10.0))
        if size == 416 and roi:
            size, roi = 640, False
        return {"input_size": size if size in INPUT_SIZES else 640, "detect_roi": roi,
                "melee_max_sec": min(120.0, max(5.0, 10.0 if melee == 25.0 else melee))}

    def conf_for(self, map_key):
        """Threshold to pass to detect_centers: 0 (= the map's own conf) unless set for this map."""
        return self.detect_conf if self.detect_conf and self.conf_map == map_key else 0.0

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            misses_before_wander=max(1, int(data.get("misses_before_wander", 2))),
            max_probe_points=min(MAX_PROBE_POINTS, max(1, int(data.get("max_probe_points", 2)))),
            hover_settle=max(0.0, float(data.get("hover_settle", 0.04))),
            hover_retry=max(0.0, float(data.get("hover_retry", 0.04))),
            hover_reads=max(1, int(data.get("hover_reads", 4))),
            miss_ttl=max(0.0, float(data.get("miss_ttl", 4.0))),
            detect_conf=min(1.0, max(0.0, float(data.get("detect_conf", 0.0)))),
            conf_map=str(data.get("conf_map", "")),
            # PLAN 0.33: 5 was the v15 default that pinned two cores -> read back as "not chosen".
            detect_fps=min(15, max(1, 2 if int(data.get("detect_fps", 2)) == 5 else int(data.get("detect_fps", 2)))),
            detect_threads=min(8, max(1, int(data.get("detect_threads", 1)))),
            search_threads=min(8, max(1, int(data.get("search_threads", 2)))),
            adaptive_detect=bool(data.get("adaptive_detect", True)),
            hunt_range=min(HUNT_RANGES[-1], max(0, int(data.get("hunt_range", 0)))),
            **cls._detect_v15(data),
        )


@dataclass
class LootSettings:
    """What to do for the drops after each kill (PLAN 1.5, 0.27 / 7).

    mode "auto": the server puts drops straight into the bag ("아데나 (n) 획득: <monster>" in the chat at the kill)
    -> nothing to do (default; the orc server of the game PC). "walk_f4" / "walk_click": drops lie at the corpse ->
    walk there (not farther than max_dist, not behind a wall on the minimap), press ``key`` ``presses`` times or
    click the shining items, then wait up to ``wait`` s for a chat line. ``enabled`` mirrors mode != "auto" for
    configs written before v12 (enabled=True then meant "press F4" -> walk_f4)."""

    enabled: bool = False
    key: str = "F4"
    presses: int = 2
    gap: float = 0.3
    mode: str = "auto"
    max_dist: int = 300  # client px
    wait: float = 2.0

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        enabled = bool(data.get("enabled", False))
        mode = data.get("mode")
        if mode not in LOOT_MODES:
            mode = "walk_f4" if enabled else "auto"
        return cls(
            enabled=mode != "auto",
            key=str(data.get("key", "F4")),
            presses=min(10, max(1, int(data.get("presses", 2)))),
            gap=min(2.0, max(0.05, float(data.get("gap", 0.3)))),
            mode=mode,
            max_dist=min(800, max(50, int(data.get("max_dist", 300)))),
            wait=min(10.0, max(0.0, float(data.get("wait", 2.0)))),
        )


LOOT_MODES = ("auto", "walk_f4", "walk_click")


OLD_DEFAULT_MAX_FRAMES = 600


def _max_frames(value):
    """0 = automatic; the old default 600 (v3-v8 configs) also becomes automatic."""
    value = max(0, int(value))
    return 0 if value == OLD_DEFAULT_MAX_FRAMES else value


@dataclass
class RecordSettings:
    """Field data recording on the game PC (PLAN 0.6) + remote-safe stop (PLAN 0.7)."""

    while_hunting: bool = False
    interval_sec: float = 3.0
    # 0 = automatic (PLAN 0.19): auto_stop_min * 60 / interval regular frames, so the cap never ends a
    # recording before the timer (event frames do not count). 600 was the old default and stopped at 10 min.
    max_frames: int = 0
    real_map: str = ""  # where the player really is (Korean name); independent of the model
    no_model: bool = False  # observe mode: frames + cursor only, no YOLOX
    grid_scan: bool = False  # hunt mode: hover a grid when YOLOX finds nothing (labels only, no click)
    grid_step: int = 40
    grid_radius: int = 200
    # Applies to hunting and observing, recording or not (PLAN 0.7). 0 = off = hunt 24/7 (PLAN 0.38 default).
    auto_stop_min: int = 0
    stop_key: str = "Pause"
    # PLAN 0.38: records/ never grows past this; the oldest recordings go first (a long run rotates its
    # recording into a new folder every recorder.ROTATE_SEC).
    max_gb: float = 5.0

    def frame_cap(self):
        """Regular frames before the RECORDING stops (PLAN 0.38: a hunt goes on without it). None = no cap."""
        if self.max_frames > 0:
            return self.max_frames
        if self.auto_stop_min > 0:
            return max(1, math.ceil(self.auto_stop_min * 60 / self.interval_sec))
        return None

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            while_hunting=bool(data.get("while_hunting", False)),
            interval_sec=max(0.5, float(data.get("interval_sec", 3.0))),
            max_frames=_max_frames(data.get("max_frames", 0)),
            real_map=str(data.get("real_map", "")).strip(),
            no_model=bool(data.get("no_model", False)),
            grid_scan=bool(data.get("grid_scan", False)),
            grid_step=min(200, max(10, int(data.get("grid_step", 40)))),
            grid_radius=min(600, max(40, int(data.get("grid_radius", 200)))),
            auto_stop_min=min(600, max(0, int(data.get("auto_stop_min", 0)))),
            stop_key=str(data.get("stop_key", "Pause")) if data.get("stop_key") in STOP_KEYS else "Pause",
            max_gb=min(500.0, max(0.5, float(data.get("max_gb", 5.0)))),
        )


# Second stop key (PLAN 0.7). F5-F12 are excluded: the bot presses them itself.
STOP_KEYS = {"Pause": 0x13, "ScrollLock": 0x91, "Insert": 0x2D}
# Hunting grounds offered in the record panel (typing another name is allowed).
REAL_MAPS = ("오염된 축복의 땅", "풍룡의 상흔", "버림받은자들의 땅", "타락한자의 땅 정령방", "오만의탑")


@dataclass
class AccountSettings:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "Account 1"
    window_title: str = ""
    character_class: str = characters.DEFAULT_CLASS_KEY
    hunt_map: str = hunt_maps.DEFAULT_MAP_KEY
    cursor_hashes: dict = field(default_factory=lambda: {k: "" for k in CURSOR_KINDS})
    health: HealthSettings = field(default_factory=HealthSettings)
    scan: ScanSettings = field(default_factory=ScanSettings)
    loot: LootSettings = field(default_factory=LootSettings)
    record: RecordSettings = field(default_factory=RecordSettings)
    attack_skills: dict = field(default_factory=_empty_attack_map)
    buff_skills: dict = field(default_factory=_empty_buff_map)
    utility_skills: dict = field(default_factory=_empty_utility_map)
    buff_vision: dict = field(default_factory=dict)
    cursor_keys: dict = field(default_factory=lambda: dict(DEFAULT_CURSOR_KEYS))
    cast_order: str = CAST_ORDERS[0]  # PLAN 1.6
    # PLAN 0.35: the game PC measured the aiming ellipse appearing a good second after the slot key (v16
    # waited 0.3 s and threw every cast away). Seconds to keep polling the cursor before clicking anyway.
    aim_wait_sec: float = 1.8
    # PLAN 0.34: page to go back to when a fight ends (the page with heal / potions). "" = stay where we are.
    home_page: str = HOTBAR_PAGES[0]

    def __post_init__(self):
        for kind in CURSOR_KINDS:
            self.cursor_hashes.setdefault(kind, "")
        self.hunt_map = hunt_maps.get(self.hunt_map).key
        self.ensure_skill_maps()
        self.enforce_skill_exclusivity()

    @property
    def character(self):
        return characters.get(self.character_class)

    def ensure_skill_maps(self):
        for key in HOTKEYS:
            if key not in self.attack_skills:
                self.attack_skills[key] = AttackSkillSetting()
            if key not in self.buff_skills:
                self.buff_skills[key] = BuffSkillSetting()
            if key not in self.utility_skills:
                self.utility_skills[key] = AttackSkillSetting()

    def attack(self, key):
        self.ensure_skill_maps()
        return self.attack_skills[key]

    def buff(self, key):
        self.ensure_skill_maps()
        return self.buff_skills[key]

    def utility(self, key):
        self.ensure_skill_maps()
        return self.utility_skills[key]

    def clear_attack(self, key):
        self.attack(key).enabled = False

    def clear_buff(self, key):
        self.buff(key).enabled = False

    def clear_utility(self, key):
        self.utility(key).enabled = False

    def enforce_skill_exclusivity(self):
        """One hotbar SLOT may only be enabled in one of attack / buff / utility.

        PLAN 0.34: a slot is (page, key), so F5 on page F1 (heal) and F5 on page F2 (a spell) live side by side.
        Priority when conflicts exist: buff keeps, then utility, attack cleared.
        """
        for key in HOTKEYS:
            self.ensure_skill_maps()
            enabled = [
                name
                for name, mapping in (
                    ("buff", self.buff_skills),
                    ("utility", self.utility_skills),
                    ("attack", self.attack_skills),
                )
                if mapping[key].enabled
            ]
            pages = {
                name: mapping[key].page
                for name, mapping in (("buff", self.buff_skills), ("utility", self.utility_skills),
                                      ("attack", self.attack_skills))
            }
            enabled = [name for name in enabled if sum(pages[n] == pages[name] for n in enabled) > 1]
            if len(enabled) <= 1:
                continue
            keep = enabled[0]
            if keep != "attack":
                self.attack_skills[key].enabled = False
            if keep != "utility":
                self.utility_skills[key].enabled = False
            if keep != "buff":
                self.buff_skills[key].enabled = False

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "window_title": self.window_title,
            "character_class": self.character_class,
            "hunt_map": self.hunt_map,
            "cursor_hashes": dict(self.cursor_hashes),
            "health": asdict(self.health),
            "scan": asdict(self.scan),
            "loot": asdict(self.loot),
            "record": asdict(self.record),
            "attack_skills": {k: asdict(v) for k, v in self.attack_skills.items()},
            "buff_skills": {k: asdict(v) for k, v in self.buff_skills.items()},
            "utility_skills": {k: asdict(v) for k, v in self.utility_skills.items()},
            "buff_vision": dict(self.buff_vision),
            "cursor_keys": dict(self.cursor_keys),
            "cast_order": self.cast_order,
            "aim_wait_sec": self.aim_wait_sec,
            "home_page": self.home_page,
        }

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        hashes = {}
        for raw_key, value in (data.get("cursor_hashes") or {}).items():
            hashes[LEGACY_CURSOR_ALIASES.get(raw_key, raw_key)] = value or ""

        if data.get("attack_skills") or data.get("buff_skills") or data.get("utility_skills"):
            attack_skills = {
                k: AttackSkillSetting.from_dict(v)
                for k, v in (data.get("attack_skills") or {}).items()
                if k in HOTKEYS
            }
            buff_skills = {
                k: BuffSkillSetting.from_dict(v)
                for k, v in (data.get("buff_skills") or {}).items()
                if k in HOTKEYS
            }
            utility_skills = {
                k: AttackSkillSetting.from_dict(v)
                for k, v in (data.get("utility_skills") or {}).items()
                if k in HOTKEYS
            }
        elif data.get("skills"):
            attack_skills, buff_skills = migrate_legacy_skills(data.get("skills"))
            utility_skills = _empty_utility_map()
        else:
            attack_skills = _empty_attack_map()
            buff_skills = _empty_buff_map()
            utility_skills = _empty_utility_map()

        hunt_map = hunt_maps.get(data.get("hunt_map")).key

        account = cls(
            id=str(data.get("id") or uuid.uuid4().hex[:8]),
            name=str(data.get("name", "Account 1")),
            window_title=str(data.get("window_title", "")),
            character_class=str(data.get("character_class", characters.DEFAULT_CLASS_KEY)),
            hunt_map=hunt_map,
            cursor_hashes=hashes,
            health=HealthSettings.from_dict(data.get("health")),
            scan=ScanSettings.from_dict(data.get("scan")),
            loot=LootSettings.from_dict(data.get("loot")),
            record=RecordSettings.from_dict(data.get("record")),
            attack_skills=attack_skills,
            buff_skills=buff_skills,
            utility_skills=utility_skills,
            buff_vision=dict(data.get("buff_vision") or {}),
            cursor_keys={k: str((data.get("cursor_keys") or {}).get(k) or v) for k, v in DEFAULT_CURSOR_KEYS.items()},
            cast_order=(str(data.get("cast_order", "")) if str(data.get("cast_order", "")) in CAST_ORDERS
                        else CAST_ORDERS[0]),
            aim_wait_sec=max(0.0, min(5.0, float(data.get("aim_wait_sec", 1.8) or 0.0))),
            home_page=("" if data.get("home_page") == "" else hotbar_page(data.get("home_page"))),
        )
        return account


UI_TABS = ("main", "hunt", "heal", "skills", "cursor", "data", "stats")  # PLAN 4.1: "stats" added in v21
RUN_MODES = ("hunt", "observe")


@dataclass
class UiSettings:
    """Window state (UI v7): open tab, geometry "WxH+X+Y", always-on-top, Start button mode."""

    tab: str = "main"
    geometry: str = ""
    topmost: bool = False
    mode: str = "hunt"

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            tab=data.get("tab") if data.get("tab") in UI_TABS else "main",
            geometry=str(data.get("geometry") or ""),
            topmost=bool(data.get("topmost", False)),
            mode=data.get("mode") if data.get("mode") in RUN_MODES else "hunt",
        )


@dataclass
class AppSettings:
    lang: str = "ko"
    accounts: list = field(default_factory=list)
    ui: UiSettings = field(default_factory=UiSettings)

    def __post_init__(self):
        if not self.accounts:
            self.accounts = [AccountSettings()]

    def find(self, account_id):
        for account in self.accounts:
            if account.id == account_id:
                return account
        return None

    def add_account(self, name=None):
        account = AccountSettings(name=name or f"Account {len(self.accounts) + 1}")
        self.accounts.append(account)
        return account

    def remove_account(self, account_id):
        if len(self.accounts) <= 1:
            return False
        self.accounts = [a for a in self.accounts if a.id != account_id]
        return True

    def to_dict(self):
        return {
            "version": 3,
            "lang": self.lang,
            "ui": asdict(self.ui),
            "accounts": [a.to_dict() for a in self.accounts],
        }

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        accounts = [AccountSettings.from_dict(a) for a in (data.get("accounts") or [])]
        lang = data.get("lang") if data.get("lang") in ("ko", "en", "vi") else "ko"
        return cls(lang=lang, accounts=accounts, ui=UiSettings.from_dict(data.get("ui")))
