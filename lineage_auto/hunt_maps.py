"""Hunt-map registry for per-map YOLOX weights.

One ONNX per hunting ground. Selecting a map in the UI loads that file;
dropping a correctly named .onnx into model/ is enough — no code change.
"""

import os
from dataclasses import dataclass

from .app_paths import asset_path

DEFAULT_MAP_KEY = "abandoned"
NEW_MODEL_CHANNELS = "bgr"  # fixed standard for every model trained from now on (docs/TRAINING.md)


@dataclass(frozen=True)
class HuntMap:
    key: str
    name_ko: str
    name_en: str
    onnx_rel: str
    # YOLOX score threshold; tuned with tests/eval_detection.py (PLAN 0.5).
    conf: float = 0.15
    # Colour order the ONNX expects. The shipped models get "rgb" (what the bot always fed them);
    # models trained with docs/TRAINING.md use NEW_MODEL_CHANNELS (official YOLOX loads images with cv2 = BGR).
    channels: str = "rgb"
    # PLAN 0.20: trained on unreviewed suggestion boxes to test the training pipeline. Usable on the dev PC
    # (eval_detection), never packed into a build; set False once a model trained on reviewed labels replaces it.
    trial: bool = False
    # PLAN 0.36: another model for the same ground, picked in Scan > Advanced ("Model"). Not listed as a map of
    # its own; ``variant`` is the label shown there.
    variant_of: str = ""
    variant: str = ""
    # PLAN 0.40: a ground where MP runs out (20261126_101941: heal spells took MP 84 -> 2 %). The UI asks for
    # an MP potion when it is selected.
    mp_hungry: bool = False

    def display_name(self, lang="en"):
        if lang == "vi":
            return f"{self.name_ko} ({self.name_en})"  # in-game names are Korean
        return self.name_ko if lang == "ko" else self.name_en


MAPS = (
    HuntMap(
        key="abandoned",
        name_ko="버림받은자들의 땅",
        name_en="Abandoned Land",
        onnx_rel=os.path.join("model", "yolox_tiny_game.onnx"),
    ),
    HuntMap(
        key="fallen_spirit",
        name_ko="타락한자의 땅 정령방",
        name_en="Fallen Land Spirit Room",
        onnx_rel=os.path.join("model", "yolox_tiny_fallen_spirit.onnx"),
    ),
    HuntMap(
        key="toi",
        name_ko="오만의탑",
        name_en="Tower of Insolence",
        onnx_rel=os.path.join("model", "yolox_tiny_toi.onnx"),
    ),
    HuntMap(
        key="dragon_valley",
        name_ko="풍룡의 산맥",
        name_en="Dragon Valley",
        onnx_rel=os.path.join("model", "yolox_tiny_dragon_valley.onnx"),
        # 0.15 -> 0.02: recall 38% -> 76% on docs/game_reference (fp 1 -> 6, the cursor rejects those).
        conf=0.02,
    ),
    HuntMap(
        key="blessed_orc",
        name_ko="오염된 축복의 땅 - 오크의 땅",
        name_en="Blessed Land (polluted) - Orc area",
        onnx_rel=os.path.join("model", "yolox_tiny_blessed_orc.onnx"),
        # orc_v1 (reviewed labels, docs/TRAINING.md 6.5/6.10). PLAN 0.39: default again from v20 - at the game PC's
        # input 416 it beats orc_v2@0.3 (day 72% vs 68%, night 67% vs 58%); v19 on orc_v2 found 2.3 box/frame, v17 5.7.
        conf=0.2,
        channels=NEW_MODEL_CHANNELS,
        variant="orc_v1",
    ),
    HuntMap(
        key="blessed_orc_v2",
        name_ko="오염된 축복의 땅 - 오크의 땅",
        name_en="Blessed Land (polluted) - Orc area",
        onnx_rel=os.path.join("model", "yolox_tiny_blessed_orc_v2.onnx"),
        # orc_v2 (PLAN 0.36, docs/TRAINING.md 6.8): only better at 640; ships at 640 (a variant), so picking it runs 640
        conf=0.3,
        channels=NEW_MODEL_CHANNELS,
        variant_of="blessed_orc",
        variant="orc_v2",
    ),
    HuntMap(
        key="fallen_blessed",
        name_ko="타락한 축복의 땅 - 오크",
        name_en="Fallen Blessed Land - corrupted orcs",
        onnx_rel=os.path.join("model", "yolox_tiny_fallen_blessed.onnx"),
        mp_hungry=True,
        # orc_v3 (PLAN 0.37, docs/TRAINING.md 6.9): one orc model (오크의 땅 + the 4 purple seasons). At 0.3 the
        # seasons give 78-91% / P91-100%; at 오크의 땅 it was not better than orc_v2 everywhere -> separate map.
        conf=0.3,
        channels=NEW_MODEL_CHANNELS,
    ),
)

_BY_KEY = {m.key: m for m in MAPS}
# v18-v19 saved orc_v1 as the variant "blessed_orc_v1"; it is the ground's default from v20 (PLAN 0.39)
_BY_KEY["blessed_orc_v1"] = _BY_KEY["blessed_orc"]


def all_maps():
    return tuple(m for m in MAPS if not m.variant_of)


def base_key(key):
    """The listed map a key belongs to (a model variant -> its ground)."""
    return get(key).variant_of or get(key).key


def variants(key):
    """[HuntMap] of every model for this ground, the default first (one item = nothing to choose)."""
    base = base_key(key)
    return [m for m in MAPS if m.key == base or m.variant_of == base]


def get(key):
    return _BY_KEY.get(key, _BY_KEY[DEFAULT_MAP_KEY])


def onnx_path(key):
    return asset_path(get(key).onnx_rel)


def model_exists(key):
    return os.path.isfile(onnx_path(key))


def pyinstaller_onnx_datas(model_dir="model"):
    """PyInstaller datas tuples for every .onnx in model_dir.

    Packs the weights of every non-trial map present at build time, plus the smaller input sizes
    (<name>_<size>.onnx) of the default models only: a variant ships at 640 (PLAN 0.36). Anything else in
    model_dir (old copies, experiments) stays out of the build.
    """
    if not os.path.isdir(model_dir):
        return []
    wanted = set()
    for m in MAPS:
        if not m.trial:
            name = os.path.basename(m.onnx_rel)
            wanted.add(name)
            if not m.variant_of:
                wanted.update(f"{os.path.splitext(name)[0]}_{size}.onnx" for size in (416, 320))
    entries = []
    for name in sorted(os.listdir(model_dir)):
        if name in wanted:
            entries.append((os.path.join(model_dir, name), "model"))
    return entries
