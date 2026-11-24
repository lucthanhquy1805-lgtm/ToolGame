"""Skill catalog helpers: duration parsing, class normalization, role classification."""

from __future__ import annotations

import re
import unicodedata

_ALL_CLASSES = ("prince", "knight", "elf", "wizard")

_CLASS_TOKENS: dict[str, str] = {
    "prince": "prince",
    "lord": "prince",
    "quân vương": "prince",
    "quan vuong": "prince",
    "knight": "knight",
    "kỵ sĩ": "knight",
    "ky si": "knight",
    "elf": "elf",
    "yêu tinh": "elf",
    "yeu tinh": "elf",
    "wizard": "wizard",
    "pháp sư": "wizard",
    "phap su": "wizard",
}

_ALL_TOKENS = frozenset({"all", "tất cả", "tat ca"})

_HEAL_NAME_MARKERS = (
    "hồi máu",
    "hoi mau",
    "hồi sinh",
    "hoi sinh",
    "chạm tự nhiên",
    "cham tu nhien",
    "phúc lành tự nhiên",
    "phuc lanh tu nhien",
)

_UTILITY_KEYWORDS = (
    "dịch chuyển",
    "dich chuyen",
    "teleport",
    "phát hiện",
    "phat hien",
    "thuần hóa",
    "thuan hoa",
    "giải độc",
    "giai doc",
    "giải lời",
    "giai loi",
    "hủy phép",
    "huy phep",
    "trả về",
    "tra ve",
)

_UTILITY_EXACT_NAMES = frozenset({"anh sang"})

_UTILITY_NAME_KEYWORDS = ("triệu hồi", "trieu hoi")

_DEBUFF_KEYWORDS = (
    "nguyền",
    "nguyen",
    "làm chậm",
    "lam cham",
    "suy yếu",
    "suy yeu",
    "bệnh",
    "benh",
    "trói",
    "troi",
    "làm mù",
    "lam mu",
    "câm lặng",
    "cam lang",
    "tê liệt",
    "te liet",
    "phá vũ khí",
    "pha vu khi",
    "giảm mr",
    "giam mr",
    "giảm hit",
    "giam hit",
    "giảm phòng",
    "giam phong",
)

_BUFF_KEYWORDS = (
    "khiên",
    "khien",
    "kháng",
    "khang",
    "cường hóa",
    "cuong hoa",
    "tăng sức",
    "tang suc",
    "tăng nhanh",
    "tang nhanh",
    "tăng tốc",
    "tang toc",
    "haste",
    "vũ khí thánh",
    "vu khi thanh",
    "phước lành",
    "phuoc lanh",
    "da đất",
    "da dat",
    "bước gió",
    "buoc gio",
)


def _fold(text: str) -> str:
    """Lowercase and strip accents for fuzzy Vietnamese matching."""
    text = text.lower().strip().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def slug_id(name_kr: str, icon_id: int) -> str:
    """Stable skill id; icon_id matches CDN SpellIcon file names."""
    return str(icon_id)


def parse_duration_sec(text: str) -> float | None:
    """Parse duration text from the skill catalog page."""
    raw = text.strip()
    folded = _fold(raw)
    if folded in ("tuc thi", "duy tri"):
        return None
    if raw.startswith("≤") or raw.startswith("<="):
        return None
    match = re.search(r"([\d,]+)\s*s?\s*$", raw, re.IGNORECASE)
    if not match:
        return None
    digits = match.group(1).replace(",", "")
    return float(digits)


def normalize_classes(raw: str) -> list[str]:
    """Map Vietnamese/English class labels to canonical character keys."""
    if _fold(raw) in _ALL_TOKENS:
        return list(_ALL_CLASSES)
    seen = set()
    result = []
    for part in re.split(r"[,/;|]+", raw):
        token = part.strip()
        if not token:
            continue
        if _fold(token) in _ALL_TOKENS:
            return list(_ALL_CLASSES)
        key = _CLASS_TOKENS.get(_fold(token))
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    folded = _fold(text)
    return any(kw in folded for kw in keywords)


def classify_role(name_vi: str, desc_vi: str, duration_sec: float | None) -> str:
    """Classify a skill as heal, buff, attack, or utility.

    ``heal`` is reserved for the basic self-heal (**Hồi Máu** / Heal) used on
    the HP panel. Other recovery skills (Greater Heal, party heal, Nature's
    Touch, …) classify as ``buff`` for now so they appear in the Buff tab as
    WIP — their cast logic differs from HP-threshold 383.
    """
    combined = f"{name_vi} {desc_vi}"
    folded_name = _fold(name_vi)

    if folded_name in ("hoi mau", "heal"):
        return "heal"

    if _contains_any(name_vi, _HEAL_NAME_MARKERS):
        return "buff"

    if _contains_any(combined, _UTILITY_KEYWORDS):
        return "utility"

    if folded_name in _UTILITY_EXACT_NAMES:
        return "utility"

    if _contains_any(name_vi, _UTILITY_NAME_KEYWORDS):
        return "utility"

    if _contains_any(combined, _DEBUFF_KEYWORDS):
        return "attack"

    if duration_sec is not None and duration_sec >= 30:
        return "buff"

    if _contains_any(combined, _BUFF_KEYWORDS):
        return "buff"

    return "attack"
