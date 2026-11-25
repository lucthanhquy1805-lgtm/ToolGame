"""Monster catalogs per hunting zone (PLAN 0.16) — data, not code.

One file per zone: ``lineage_auto/data/monsters/<key>.json``
  key        file-safe id (also the folder of the name pictures: names/<key>/<class>.png)
  real_map   the zone name picked in the record panel ("실제 사냥터"), Korean as in game
  real_maps  optional: several zone names sharing this catalog (the 4 seasons of 타락한 축복의 땅, PLAN 0.37)
  zone_name  optional: what the zone box offers (PLAN 0.37: one map holds several monster kinds - spring has
             the purple orcs AND the elves - so the user picks the monster kind, not the map name)
  hunt_map   hunt_maps key of the YOLOX model for this zone, or null = no model yet (collect data)
  group      label used when every monster of the zone is merged into one class (e.g. "orc")
  monsters   [{name (Korean, as in game), class (label), level, attack melee/ranged,
               npc / boss / no_attack flags, template (default <class>.png), note}]
Adding a zone = adding a file (+ a few name pictures); see docs/ADD_NEW_MAP.md.
"""

import json
import os

from .app_paths import asset_path

CATALOG_DIR = os.path.join("lineage_auto", "data", "monsters")
# Labels every zone has besides its monsters.
COMMON_CLASSES = ("corpse", "player", "npc")


class Catalog:
    def __init__(self, data, folder):
        self.key = data["key"]
        self.real_maps = tuple(data.get("real_maps") or ([data["real_map"]] if data.get("real_map") else []))
        self.real_map = self.real_maps[0] if self.real_maps else ""
        self.zone_name = data.get("zone_name") or self.real_map
        self.name_en = data.get("name_en", self.key)
        self.hunt_map = data.get("hunt_map")
        self.group = data.get("group") or "monster"
        self.monsters = []
        for m in data.get("monsters", []):
            m = dict(m)
            m.setdefault("template", f"{m['class']}.png")
            self.monsters.append(m)
        self.names_dir = os.path.join(folder, "names", self.key)

    @property
    def has_model(self):
        """A model is named AND its ONNX is there (a build without the zone's model = data collection)."""
        from . import hunt_maps
        return bool(self.hunt_map) and self.hunt_map in {m.key for m in hunt_maps.all_maps()}             and hunt_maps.model_exists(self.hunt_map)

    def monster_classes(self):
        """Labels of the huntable monsters (no NPC / boss / no_attack), catalog order."""
        out = []
        for m in self.monsters:
            if not (m.get("npc") or m.get("boss") or m.get("no_attack")) and m["class"] not in out:
                out.append(m["class"])
        return out

    def label_classes(self):
        """Every label of this zone: monsters, then the others (boss...), then COMMON_CLASSES."""
        out = self.monster_classes()
        for m in self.monsters:
            if m["class"] not in out and m["class"] not in COMMON_CLASSES:
                out.append(m["class"])
        return out + [c for c in COMMON_CLASSES if c not in out]

    def by_name(self, name):
        return next((m for m in self.monsters if m["name"] == name), None)

    def by_class(self, cls):
        return next((m for m in self.monsters if m["class"] == cls), None)

    def is_monster(self, cls):
        return cls in self.monster_classes()


def catalog_dir():
    return asset_path(CATALOG_DIR)


def load_all(folder=None):
    folder = folder or catalog_dir()
    out = []
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        if name.endswith(".json"):
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                out.append(Catalog(json.load(fh), folder))
    return out


def real_maps(folder=None):
    return tuple(z for c in load_all(folder) for z in c.real_maps)


def zone_names(folder=None):
    """One entry per catalog (= per monster kind) for the zone box."""
    return tuple(c.zone_name for c in load_all(folder) if c.zone_name)


def fits_map_name(catalog, name):
    """PLAN 0.39 / 7: the map name read on screen (vision.map_name) belongs to this catalog: one of its maps, or
    the start of one ("오염된 축복의 땅" is printed for every "오염된 축복의 땅 - ..." area)."""
    return catalog is not None and bool(name) and any(z == name or z.startswith(name) for z in catalog.real_maps)


def for_hunt_map(key, folder=None):
    """First catalog (file order) whose model is this hunt map, or None."""
    return next((c for c in load_all(folder) if key and c.hunt_map == key), None)


def for_real_map(real_map, folder=None):
    """Catalog whose zone is ``real_map`` (its key, its zone_name, or one of its maps), or None.
    A map shared by several catalogs (타락한 축복의 땅의 봄) gives the first in file order (fallen_blessed before
    fallen_blessed_elf): recordings name their catalog with "zone" (the key) to be exact."""
    real_map = (real_map or "").strip()
    if not real_map:
        return None
    cats = load_all(folder)
    return (next((c for c in cats if real_map in (c.key, c.zone_name)), None)
            or next((c for c in cats if real_map in c.real_maps), None))
