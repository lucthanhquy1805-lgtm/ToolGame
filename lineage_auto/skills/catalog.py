"""Load shipped skill catalog JSON and pack icons."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np

_CATALOG: SkillCatalog | None = None
_MP_NAMED = re.compile(r"MP\s*(\d+)", re.IGNORECASE)
_HP_NAMED = re.compile(r"HP\s*\d+", re.IGNORECASE)


def parse_mp_cost(cost_text: str | None) -> int:
    """Catalog ``cost_text`` is MP unless it is an HP-only cost."""
    text = str(cost_text or "").strip()
    if not text:
        return 0
    named = _MP_NAMED.search(text)
    if named:
        return int(named.group(1))
    if _HP_NAMED.search(text):
        return 0
    if text.isdigit():
        return int(text)
    return 0


def can_afford_mp(mp_pct, cost: int) -> bool:
    """Block skills with an MP cost only when the MP bar reads empty.

    The HUD gives a percentage; catalog costs are absolute MP. Without max
    MP those cannot be compared, so a missing/unread bar does not block.
    """
    if int(cost or 0) <= 0:
        return True
    if mp_pct is None:
        return True
    return int(mp_pct) > 0


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "skills"


class SkillCatalog:
    def __init__(self, root: Path, skills: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]):
        self._root = root
        self._skills = skills
        self._by_id = by_id
        self._by_class: dict[str, list[str]] = {}

    @classmethod
    def load(cls, root: str | Path | None = None) -> SkillCatalog:
        catalog_root = Path(root) if root is not None else _default_root()
        catalog_path = catalog_root / "skills_catalog.json"
        with open(catalog_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        skills = payload.get("skills", [])
        by_id = {skill["id"]: skill for skill in skills if "id" in skill}
        return cls(catalog_root, skills, by_id)

    def get(self, skill_id: str) -> dict[str, Any] | None:
        return self._by_id.get(str(skill_id))

    def skills_for(self, class_key: str, role: str | None = None) -> list[dict[str, Any]]:
        skill_ids = self._class_skill_ids(class_key)
        result = []
        for skill_id in skill_ids:
            skill = self._by_id.get(skill_id)
            if skill is None:
                continue
            if role is not None and skill.get("role") != role:
                continue
            result.append(skill)
        return result

    def icon_path(self, skill_id: str) -> str | None:
        skill = self.get(skill_id)
        if skill is None:
            return None
        rel_icon = skill.get("icon")
        if not rel_icon:
            return None
        absolute = os.path.abspath(os.path.join(self._root, rel_icon))
        if os.path.isfile(absolute):
            return absolute
        return None

    def mp_cost(self, skill_id: str) -> int:
        skill = self.get(skill_id)
        if skill is None:
            return 0
        return parse_mp_cost(skill.get("cost_text"))

    def default_duration_min(self, skill_id: str) -> float | None:
        skill = self.get(skill_id)
        if skill is None:
            return None
        duration_sec = skill.get("duration_sec")
        if duration_sec is None:
            return None
        return max(0.1, float(duration_sec) / 60.0)

    def load_icon_bgr(self, skill_id: str) -> np.ndarray | None:
        path = self.icon_path(skill_id)
        if path is None:
            return None
        image = cv2.imread(path)
        if image is None:
            return None
        return image

    def _class_skill_ids(self, class_key: str) -> list[str]:
        if class_key not in self._by_class:
            class_path = self._root / "by_class" / f"{class_key}.json"
            if class_path.is_file():
                with open(class_path, encoding="utf-8") as handle:
                    ids = json.load(handle)
                self._by_class[class_key] = [str(skill_id) for skill_id in ids]
            else:
                self._by_class[class_key] = [
                    skill["id"]
                    for skill in self._skills
                    if class_key in skill.get("classes", [])
                ]
        return self._by_class[class_key]


def get_catalog() -> SkillCatalog:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = SkillCatalog.load()
    return _CATALOG
