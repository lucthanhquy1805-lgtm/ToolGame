"""Monster catalogs per hunting zone (PLAN 0.16) — data, not code.

One file per zone: ``lineage_auto/data/monsters/<key>.json``
  key        file-safe id (also the folder of the name pictures: names/<key>/<class>.png)
  real_map   the zone name picked in the record panel ("실제 사냥터"), Korean as in game
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
        self.real_map = data.get("real_map", "")
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
    return tuple(c.real_map for c in load_all(folder) if c.real_map)


def for_real_map(real_map, folder=None):
    """Catalog whose zone is ``real_map`` (exact, or its key), or None."""
    real_map = (real_map or "").strip()
    if not real_map:
        return None
    return next((c for c in load_all(folder) if real_map in (c.real_map, c.key)), None)
